"""Sentinel paper-fund foundation.

This module is deliberately paper-only. It provides a persistent portfolio ledger
and deterministic risk gates; it does not call a broker or place live orders.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class RiskLimits:
    starting_cash: float = 100_000.0
    max_position_fraction: float = 0.10
    max_gross_exposure_fraction: float = 0.50
    max_trade_risk_fraction: float = 0.01
    max_daily_loss_fraction: float = 0.02


@dataclass(frozen=True)
class Decision:
    symbol: str
    side: str
    quantity: float
    reference_price: float
    rationale: str
    stop_price: Optional[float] = None


class PaperFund:
    """SQLite-backed paper portfolio with a deterministic risk gate."""

    def __init__(self, db_path: str | Path = "sentinel_paper_fund.sqlite3",
                 limits: RiskLimits = RiskLimits()):
        self.db_path = str(db_path)
        self.limits = limits
        self._init_db()

    def _connect(self):
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def _init_db(self):
        with self._connect() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS fund_meta (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL, symbol TEXT NOT NULL,
                    side TEXT NOT NULL, quantity REAL NOT NULL,
                    reference_price REAL NOT NULL, rationale TEXT NOT NULL,
                    accepted INTEGER NOT NULL, rejection_reason TEXT
                );
                CREATE TABLE IF NOT EXISTS fills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL, symbol TEXT NOT NULL,
                    side TEXT NOT NULL, quantity REAL NOT NULL,
                    price REAL NOT NULL, notional REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS marks (
                    symbol TEXT PRIMARY KEY, price REAL NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)
            con.execute(
                "INSERT OR IGNORE INTO fund_meta(key,value) VALUES('starting_cash',?)",
                (str(self.limits.starting_cash),)
            )
            con.execute(
                "INSERT OR IGNORE INTO fund_meta(key,value) VALUES('live_trading_enabled','false')"
            )

    def mark_price(self, symbol: str, price: float):
        if price <= 0:
            raise ValueError("Price must be positive")
        with self._connect() as con:
            con.execute("""
                INSERT INTO marks(symbol,price,updated_at) VALUES(?,?,?)
                ON CONFLICT(symbol) DO UPDATE SET price=excluded.price, updated_at=excluded.updated_at
            """, (symbol.upper(), price, self._now()))

    def _now(self):
        return datetime.now(timezone.utc).isoformat()

    def snapshot(self):
        with self._connect() as con:
            starting_cash = float(con.execute(
                "SELECT value FROM fund_meta WHERE key='starting_cash'"
            ).fetchone()[0])
            fills = con.execute("SELECT * FROM fills ORDER BY id").fetchall()
            marks = {r["symbol"]: r["price"] for r in con.execute("SELECT * FROM marks")}
            decisions = con.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT 20").fetchall()

        cash = starting_cash
        positions = {}
        for f in fills:
            signed = f["quantity"] if f["side"] == "BUY" else -f["quantity"]
            cash -= signed * f["price"]
            positions[f["symbol"]] = positions.get(f["symbol"], 0.0) + signed
        positions = {s:q for s,q in positions.items() if abs(q) > 1e-10}
        position_rows = []
        gross = 0.0
        market_value = 0.0
        for symbol, quantity in positions.items():
            price = marks.get(symbol)
            if price is None:
                # Last fill is a safe fallback, explicitly not a live quote.
                candidates = [f["price"] for f in fills if f["symbol"] == symbol]
                price = candidates[-1] if candidates else 0.0
            value = quantity * price
            market_value += value
            gross += abs(value)
            position_rows.append({
                "symbol": symbol, "quantity": quantity, "mark_price": price,
                "market_value": value, "mark_is_stale_fallback": symbol not in marks,
            })
        equity = cash + market_value
        return {
            "as_of": self._now(), "mode": "PAPER ONLY",
            "live_trading_enabled": False, "starting_cash": starting_cash,
            "cash": cash, "equity": equity, "pnl": equity - starting_cash,
            "return_pct": ((equity / starting_cash) - 1) * 100 if starting_cash else 0,
            "gross_exposure": gross,
            "gross_exposure_pct": gross / equity * 100 if equity else 0,
            "positions": position_rows,
            "recent_decisions": [dict(r) for r in decisions],
            "limits": asdict(self.limits),
        }

    def evaluate(self, decision: Decision):
        symbol = decision.symbol.strip().upper()
        side = decision.side.strip().upper()
        reason = None
        if not symbol or side not in {"BUY", "SELL"}:
            reason = "Invalid symbol or side"
        elif decision.quantity <= 0 or decision.reference_price <= 0:
            reason = "Quantity and reference price must be positive"
        elif not decision.rationale.strip():
            reason = "A written rationale is required"
        elif decision.stop_price is not None and (
            decision.stop_price <= 0 or
            (side == "BUY" and decision.stop_price >= decision.reference_price) or
            (side == "SELL" and decision.stop_price <= decision.reference_price)
        ):
            reason = "Stop price is inconsistent with trade direction"

        snap = self.snapshot()
        notional = decision.quantity * decision.reference_price
        if reason is None and notional > snap["equity"] * self.limits.max_position_fraction:
            reason = "Position exceeds per-position notional limit"
        if reason is None and snap["gross_exposure"] + notional > (
            snap["equity"] * self.limits.max_gross_exposure_fraction
        ):
            reason = "Trade exceeds gross exposure limit"
        if reason is None and decision.stop_price is not None:
            risk = decision.quantity * abs(decision.reference_price - decision.stop_price)
            if risk > snap["equity"] * self.limits.max_trade_risk_fraction:
                reason = "Estimated stop loss exceeds per-trade risk limit"
        return reason is None, reason

    def submit_paper_decision(self, decision: Decision):
        accepted, reason = self.evaluate(decision)
        now = self._now()
        with self._connect() as con:
            con.execute("""
                INSERT INTO decisions(created_at,symbol,side,quantity,reference_price,
                  rationale,accepted,rejection_reason) VALUES(?,?,?,?,?,?,?,?)
            """, (now, decision.symbol.upper(), decision.side.upper(),
                  decision.quantity, decision.reference_price, decision.rationale,
                  int(accepted), reason))
            if accepted:
                # This is an explicit paper fill at the supplied reference price,
                # not a claim of a real market fill.
                con.execute("""
                    INSERT INTO fills(created_at,symbol,side,quantity,price,notional)
                    VALUES(?,?,?,?,?,?)
                """, (now, decision.symbol.upper(), decision.side.upper(),
                      decision.quantity, decision.reference_price,
                      decision.quantity * decision.reference_price))
                con.execute("""
                    INSERT INTO marks(symbol,price,updated_at) VALUES(?,?,?)
                    ON CONFLICT(symbol) DO UPDATE SET price=excluded.price, updated_at=excluded.updated_at
                """, (decision.symbol.upper(), decision.reference_price, now))
        return {"accepted": accepted, "reason": reason, "snapshot": self.snapshot()}

    def report(self):
        snap = self.snapshot()
        return json.dumps(snap, indent=2)
