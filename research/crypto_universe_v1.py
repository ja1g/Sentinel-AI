"""
Sentinel Crypto Universe V1

ISOLATED RESEARCH ONLY.
- Does not modify the existing BTC forward test.
- Does not modify the existing multi-market test.
- Does not place orders.
- Writes only crypto_universe_forward_test.csv and crypto_universe_prices.csv.

Purpose:
Collect the same style of short-horizon directional evidence across a controlled
set of liquid GBP-quoted crypto assets. BTC is treated as one asset in the
universe rather than as a special case.

The V1 signal is intentionally simple and transparent: 15m and 60m momentum
plus a 5/20 minute moving-average confirmation. It is a research baseline,
not the final Sentinel strategy engine.
"""

import csv
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path

import requests


BASE_URL = "https://api.coinbase.com/v2"
POLL_SECONDS = 60
FORWARD_MINUTES = 60

# Controlled initial universe. The collector only activates assets that
# Coinbase exposes as GBP spot products at runtime.
PREFERRED_ASSETS = [
    "BTC",
    "ETH",
    "SOL",
    "XRP",
    "ADA",
    "DOGE",
    "LINK",
    "AVAX",
    "DOT",
    "LTC",
]

FORWARD_FILE = Path("crypto_universe_forward_test.csv")
PRICE_FILE = Path("crypto_universe_prices.csv")

session = requests.Session()
session.headers.update({"User-Agent": "Sentinel-Crypto-Universe-V1/1.0"})

prices = defaultdict(lambda: deque(maxlen=180))


FORWARD_FIELDS = [
    "timestamp",
    "asset",
    "product_id",
    "price",
    "signal",
    "score",
    "outcome_at",
    "forward_price",
    "raw_return_pct",
    "directional_return_pct",
    "outcome",
]

PRICE_FIELDS = ["timestamp", "asset", "product_id", "price"]


def ensure_file(path, fields):
    if not path.exists() or path.stat().st_size == 0:
        with path.open("w", newline="") as f:
            csv.writer(f).writerow(fields)


def discover_products():
    """Return preferred assets that currently have a GBP spot product."""
    response = session.get(f"{BASE_URL}/products", timeout=15)
    response.raise_for_status()
    products = response.json().get("data", [])

    available = {}
    for product in products:
        pid = product.get("id", "")
        if pid.endswith("-GBP") and product.get("base_currency") in PREFERRED_ASSETS:
            available[product["base_currency"]] = pid

    return {asset: available[asset] for asset in PREFERRED_ASSETS if asset in available}


def fetch_spot(product_id):
    response = session.get(
        f"{BASE_URL}/prices/{product_id}/spot",
        timeout=10,
    )
    response.raise_for_status()
    return float(response.json()["data"]["amount"])


def append_row(path, row):
    with path.open("a", newline="") as f:
        csv.writer(f).writerow(row)


def recent_price(asset, seconds_ago):
    target = datetime.now() - timedelta(seconds=seconds_ago)
    history = prices[asset]
    if not history:
        return None

    closest = min(history, key=lambda x: abs(x[0] - target))
    tolerance = max(90, seconds_ago * 0.25)
    if abs((closest[0] - target).total_seconds()) <= tolerance:
        return closest[1]
    return None


def movement(asset, seconds_ago):
    old = recent_price(asset, seconds_ago)
    if old is None or old == 0:
        return None
    current = prices[asset][-1][1]
    return ((current - old) / old) * 100


def ma(asset, seconds):
    cutoff = datetime.now() - timedelta(seconds=seconds)
    values = [price for ts, price in prices[asset] if ts >= cutoff]
    if not values:
        return None
    return sum(values) / len(values)


def baseline_signal(asset):
    """Transparent V1 signal; no look-ahead and no capital deployment."""
    m15 = movement(asset, 15 * 60)
    m60 = movement(asset, 60 * 60)
    ma5 = ma(asset, 5 * 60)
    ma20 = ma(asset, 20 * 60)

    if None in (m15, m60, ma5, ma20):
        return "WAIT", 50

    if m15 > 0 and m60 > 0 and ma5 > ma20:
        strength = min(45, 10 + abs(m15) * 8 + abs(m60) * 3)
        return "BUY", round(50 + strength, 2)

    if m15 < 0 and m60 < 0 and ma5 < ma20:
        strength = min(45, 10 + abs(m15) * 8 + abs(m60) * 3)
        return "SELL", round(50 - strength, 2)

    return "WAIT", 50


def resolve_due_rows(now, latest_prices):
    """Resolve 60m outcomes for previously recorded signals."""
    if not FORWARD_FILE.exists() or FORWARD_FILE.stat().st_size == 0:
        return

    with FORWARD_FILE.open("r", newline="") as f:
        rows = list(csv.DictReader(f))

    changed = False
    for row in rows:
        if row["outcome"] != "PENDING":
            continue

        outcome_at = datetime.fromisoformat(row["outcome_at"])
        if now < outcome_at:
            continue

        asset = row["asset"]
        forward = latest_prices.get(asset)
        if forward is None:
            continue

        entry = float(row["price"])
        raw = ((forward - entry) / entry) * 100
        signal = row["signal"]

        if signal == "BUY":
            directional = raw
        elif signal == "SELL":
            directional = -raw
        else:
            directional = 0.0

        if signal == "WAIT":
            outcome = "NOT_TESTED"
        elif directional > 0:
            outcome = "WIN"
        elif directional < 0:
            outcome = "LOSS"
        else:
            outcome = "FLAT"

        row["forward_price"] = f"{forward:.10f}"
        row["raw_return_pct"] = f"{raw:.6f}"
        row["directional_return_pct"] = f"{directional:.6f}"
        row["outcome"] = outcome
        changed = True

    if changed:
        temp = FORWARD_FILE.with_suffix(".tmp")
        with temp.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FORWARD_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        temp.replace(FORWARD_FILE)


def print_summary(active_assets):
    if not FORWARD_FILE.exists() or FORWARD_FILE.stat().st_size == 0:
        return

    completed = defaultdict(list)
    with FORWARD_FILE.open("r", newline="") as f:
        for row in csv.DictReader(f):
            if row["outcome"] in {"WIN", "LOSS", "FLAT"}:
                completed[row["asset"]].append(row)

    print("\nCRYPTO UNIVERSE EVIDENCE")
    print("Asset  Completed  Win rate  Avg directional return")
    print("-----  ---------  --------  ----------------------")
    for asset in active_assets:
        rows = completed[asset]
        if not rows:
            print(f"{asset:<5}  {0:>9}  {'-':>8}  {'-':>22}")
            continue
        wins = sum(r["outcome"] == "WIN" for r in rows)
        avg = sum(float(r["directional_return_pct"]) for r in rows) / len(rows)
        print(f"{asset:<5}  {len(rows):>9}  {wins / len(rows) * 100:>7.1f}%  {avg:>21.4f}%")


def main():
    ensure_file(FORWARD_FILE, FORWARD_FIELDS)
    ensure_file(PRICE_FILE, PRICE_FIELDS)

    products = discover_products()
    if not products:
        raise RuntimeError("No preferred GBP crypto products are currently available.")

    print("Sentinel Crypto Universe V1")
    print("RESEARCH / PAPER TESTING ONLY — REAL MONEY OFF")
    print("Active universe:", ", ".join(products))
    print("Existing Sentinel processes are not touched by this program.")

    while True:
        started = time.time()
        now = datetime.now()
        latest = {}

        for asset, product_id in products.items():
            try:
                price = fetch_spot(product_id)
                prices[asset].append((now, price))
                latest[asset] = price

                append_row(
                    PRICE_FILE,
                    [now.isoformat(timespec="seconds"), asset, product_id, f"{price:.10f}"],
                )

                signal, score = baseline_signal(asset)
                outcome_at = now + timedelta(minutes=FORWARD_MINUTES)
                append_row(
                    FORWARD_FILE,
                    [
                        now.isoformat(timespec="seconds"),
                        asset,
                        product_id,
                        f"{price:.10f}",
                        signal,
                        f"{score:.2f}",
                        outcome_at.isoformat(timespec="seconds"),
                        "",
                        "",
                        "",
                        "PENDING" if signal != "WAIT" else "NOT_TESTED",
                    ],
                )

                print(f"{asset:<5} £{price:>12,.6f}  {signal:<4}  score={score:>5}")

            except Exception as exc:
                print(f"{asset:<5} ERROR: {exc}")

        resolve_due_rows(now, latest)
        print_summary(products)

        elapsed = time.time() - started
        time.sleep(max(1, POLL_SECONDS - elapsed))


if __name__ == "__main__":
    main()
