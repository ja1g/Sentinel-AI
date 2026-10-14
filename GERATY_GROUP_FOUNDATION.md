# Sentinel AI — Geraty Group foundation

This branch adds the first isolated, persistent **paper-fund ledger** for Sentinel.
It is additive and does not modify the existing market watcher or research files.

## Current scope

- SQLite persistence for decisions, paper fills and price marks.
- A virtual starting balance of £100,000.
- Deterministic risk gates for per-position notional, gross exposure, stop-risk,
  available cash and sell quantity.
- Explicit paper-only status. No broker integration, API keys or live order path.
- Recent decision audit trail and portfolio snapshot.

## Run the tests

From the repository root, with Python 3.11+:

```powershell
py -m unittest discover -s tests -v
```

## Important limitations

This is a foundation, not yet an autonomous profitable hedge fund. It does not
yet include an AI model adapter, live market-data ingestion, fee/slippage modelling,
daily-loss baseline enforcement, independent portfolio valuation, walk-forward
validation, a broker adapter, or the full command-centre dashboard. The next
increments must add these with tests. Never infer profitability from paper fills
at supplied reference prices.

Real-money trading is intentionally unavailable in this branch.
