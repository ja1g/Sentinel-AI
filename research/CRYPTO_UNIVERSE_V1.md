# Sentinel Crypto Universe V1

## Objective
Expand Sentinel from a BTC-centric research target into a controlled crypto universe while leaving all currently running Sentinel processes untouched.

## Initial universe
BTC, ETH, SOL, XRP, ADA, DOGE, LINK, AVAX, DOT, LTC — restricted to GBP spot products available from the data venue at runtime.

## Isolation
- Existing `main.py` and `bitcoin_history.csv` are not modified.
- Existing BTC forward testing is not modified.
- Existing multi-market testing is not modified.
- No exchange orders are implemented.
- No real capital is enabled.
- Research outputs are separate: `crypto_universe_prices.csv` and `crypto_universe_forward_test.csv`.

## Baseline experiment
At each polling interval, record each asset's spot price and a transparent baseline signal using 15-minute momentum, 60-minute momentum and a 5/20-minute moving-average confirmation. A non-WAIT signal is evaluated over the next 60 minutes.

For BUY, directional return = future return. For SELL, directional return = negative future return. This creates a comparable metric across direction.

## Admission discipline
The baseline is a candidate generator, not proof of an edge. Promotion requires adequate sample size, multiple market periods/regimes, out-of-sample validation, realistic spread/fee/slippage assumptions, reproducibility, and comparison against appropriate baselines.

## Next research questions
1. Does the same signal behave differently across BTC, ETH and major altcoins?
2. Does BTC lead or confirm moves in other crypto assets?
3. Does cross-asset confirmation improve signal quality without overfitting?
4. Which regimes, if any, produce persistent edge?
5. Does any observed edge survive realistic costs?
6. Does the apparent edge survive an untouched out-of-sample period?

## Safety verdict
**NOT READY FOR REAL CAPITAL.**
