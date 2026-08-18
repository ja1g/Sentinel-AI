import requests
import time
import csv
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from plyer import notification

history_file = Path("bitcoin_history.csv")

# Pullback state memory
pullback_required = False
overbought_high = None
overbought_time = None

print("Sentinel AI is starting...")
print("Watching Bitcoin with multi-timeframe intelligence.")
print("Market regime engine: ACTIVE")
print("Pullback confirmation engine: ACTIVE")
print("Strategy engine: ACTIVE")
print("Press Ctrl + C to stop.\n")


def send_notification(title, message):
    notification.notify(title=title, message=message, timeout=10)


def load_history():
    history = []

    if history_file.exists():
        with open(history_file, "r") as file:
            reader = csv.DictReader(file)
            for row in reader:
                history.append({
                    "timestamp": datetime.strptime(
                        row["timestamp"], "%Y-%m-%d %H:%M:%S"
                    ),
                    "price": float(row["price"])
                })

    return history


def get_price_from_minutes_ago(history, minutes, current_time):
    if not history:
        return None

    target_time = current_time - timedelta(minutes=minutes)

    closest = min(
        history,
        key=lambda row: abs(row["timestamp"] - target_time)
    )

    # Allow a wider time window for gaps in data collection
    tolerance = max(3, minutes * 0.2)

    if abs(closest["timestamp"] - target_time) <= timedelta(minutes=tolerance):
        return closest["price"]

    return None
def movement_percent(current_price, old_price):
    if old_price is None or old_price == 0:
        return None

    return ((current_price - old_price) / old_price) * 100


def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None

    series = pd.Series(prices)
    delta = series.diff()

    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)

    average_gain = gains.rolling(period).mean().iloc[-1]
    average_loss = losses.rolling(period).mean().iloc[-1]

    if average_loss == 0:
        return 100

    rs = average_gain / average_loss
    return 100 - (100 / (1 + rs))


def get_trend(prices, short_period=5, long_period=20):
    if len(prices) < long_period:
        return "COLLECTING", None, None

    series = pd.Series(prices)

    short_ma = series.rolling(short_period).mean().iloc[-1]
    long_ma = series.rolling(long_period).mean().iloc[-1]

    if short_ma > long_ma:
        return "BULLISH", short_ma, long_ma
    elif short_ma < long_ma:
        return "BEARISH", short_ma, long_ma

    return "NEUTRAL", short_ma, long_ma


def get_timeframe_prices(history, minutes):
    if not history:
        return []

    dataframe = pd.DataFrame(history)
    dataframe = dataframe.set_index("timestamp")

    sampled = dataframe["price"].resample(
        f"{minutes}min"
    ).last().dropna()

    return sampled.tolist()


def calculate_volatility(prices, period=20):
    if len(prices) < period + 1:
        return None

    series = pd.Series(prices[-(period + 1):])
    returns = series.pct_change().dropna()

    return returns.std() * 100


def get_market_regime(trends, change_15, change_60, volatility):
    if "COLLECTING" in trends.values():
        return "COLLECTING DATA", "Not enough multi-timeframe data yet"

    bullish_count = list(trends.values()).count("BULLISH")
    bearish_count = list(trends.values()).count("BEARISH")

    if volatility is not None and volatility > 0.35:
        return "HIGH VOLATILITY", (
            f"recent volatility is elevated ({volatility:.2f}%)"
        )

    if (
        bullish_count >= 3
        and change_15 is not None
        and change_60 is not None
        and change_15 > 0
        and change_60 > 0
    ):
        return "TRENDING BULLISH", (
            "multiple timeframes and momentum are bullish"
        )

    if (
        bearish_count >= 3
        and change_15 is not None
        and change_60 is not None
        and change_15 < 0
        and change_60 < 0
    ):
        return "TRENDING BEARISH", (
            "multiple timeframes and momentum are bearish"
        )

    if (
        change_15 is not None
        and change_60 is not None
        and abs(change_15) < 0.30
        and abs(change_60) < 0.50
    ):
        return "RANGING", (
            "price movement is limited"
        )

    return "UNCLEAR", "market conditions do not strongly match one regime"


def update_pullback_state(price, rsi, trends, timestamp):
    global pullback_required
    global overbought_high
    global overbought_time

    status = "NO PULLBACK SETUP"
    pullback_percent = None

    # Detect overbought conditions
    if rsi is not None and rsi >= 80:
        if not pullback_required:
            pullback_required = True
            overbought_high = price
            overbought_time = timestamp

        elif price > overbought_high:
            overbought_high = price
            overbought_time = timestamp

        return "OVERBOUGHT - WAIT FOR PULLBACK", None

    if pullback_required and overbought_high is not None:
        pullback_percent = (
            (price - overbought_high) / overbought_high
        ) * 100

        bullish_count = list(trends.values()).count("BULLISH")

        if pullback_percent <= -0.5:
            status = "PULLBACK DETECTED - WAIT FOR CONFIRMATION"

            if (
                rsi is not None
                and rsi < 65
                and trends["1m"] == "BULLISH"
                and bullish_count >= 3
            ):
                pullback_required = False

                return (
                    "PULLBACK CONFIRMED - BULLISH RE-ENTRY",
                    pullback_percent
                )

        else:
            status = "WAITING FOR DEEPER PULLBACK"

    return status, pullback_percent


# ============================================================
# STRATEGY ENGINE V1
# ============================================================

def trend_strategy(trends, regime):
    score = 50

    bullish_count = list(trends.values()).count("BULLISH")
    bearish_count = list(trends.values()).count("BEARISH")

    if bullish_count == 4:
        score = 90
        signal = "BULLISH"
    elif bullish_count == 3:
        score = 75
        signal = "BULLISH"
    elif bearish_count == 4:
        score = 10
        signal = "BEARISH"
    elif bearish_count == 3:
        score = 25
        signal = "BEARISH"
    else:
        score = 50
        signal = "WAIT"

    # Reduce confidence in unclear conditions
    if regime == "UNCLEAR":
        score = 50
        signal = "WAIT"

    return signal, score


def pullback_strategy(pullback_status, trends):
    if pullback_status == "PULLBACK CONFIRMED - BULLISH RE-ENTRY":
        return "BULLISH", 90

    if pullback_status == "PULLBACK DETECTED - WAIT FOR CONFIRMATION":
        return "WAIT", 55

    if pullback_status in [
        "OVERBOUGHT - WAIT FOR PULLBACK",
        "WAITING FOR DEEPER PULLBACK"
    ]:
        return "WAIT", 30

    return "WAIT", 50


def momentum_strategy(change_15, change_60, trends):
    score = 50

    bullish_count = list(trends.values()).count("BULLISH")
    bearish_count = list(trends.values()).count("BEARISH")

    if (
        change_15 is not None
        and change_60 is not None
    ):
        if (
            change_15 > 0.30
            and change_60 > 0.50
            and bullish_count >= 2
        ):
            return "BULLISH", 85

        if (
            change_15 > 0
            and change_60 > 0
            and bullish_count >= 2
        ):
            return "BULLISH", 70

        if (
            change_15 < -0.30
            and change_60 < -0.50
            and bearish_count >= 2
        ):
            return "BEARISH", 15

        if (
            change_15 < 0
            and change_60 < 0
            and bearish_count >= 2
        ):
            return "BEARISH", 30

    return "WAIT", score


def get_best_strategy(strategies):
    """
    Choose the strategy with the strongest conviction away from neutral.
    """
    best_name = "NONE"
    best_strength = -1

    for name, data in strategies.items():
        signal = data["signal"]
        score = data["score"]

        strength = abs(score - 50)

        if signal != "WAIT" and strength > best_strength:
            best_name = name
            best_strength = strength

    return best_name


def get_sentinel_verdict(
    rsi,
    trends,
    change_15,
    change_60,
    regime,
    pullback_status,
    strategies
):
    score = 50
    reasons = []

    bullish_count = list(trends.values()).count("BULLISH")
    bearish_count = list(trends.values()).count("BEARISH")

    # Base multi-timeframe analysis
    if bullish_count == 4:
        score += 30
        reasons.append("all timeframes are bullish")
    elif bullish_count == 3:
        score += 20
        reasons.append("most timeframes are bullish")
    elif bullish_count == 2:
        score += 10
        reasons.append("short-term bullish confirmation")
    elif bearish_count == 4:
        score -= 30
        reasons.append("all timeframes are bearish")
    elif bearish_count == 3:
        score -= 20
        reasons.append("most timeframes are bearish")
    elif bearish_count == 2:
        score -= 10
        reasons.append("bearish confirmation across timeframes")

    # RSI
    if rsi is not None:
        if trends["1m"] == "BULLISH":
            if rsi < 35:
                score += 20
                reasons.append("strong pullback within bullish trend")
            elif rsi < 50:
                score += 15
                reasons.append("healthy pullback within bullish trend")
            elif rsi <= 70:
                score += 10
                reasons.append("healthy bullish momentum")
            elif rsi <= 80:
                score -= 5
                reasons.append("market becoming overextended")
            else:
                score -= 15
                reasons.append("extremely overbought")

        elif trends["1m"] == "BEARISH":
            if rsi >= 40:
                score -= 10
                reasons.append("short-term bearish momentum")
            elif rsi < 30:
                score += 5
                reasons.append("oversold - possible bounce")

    # Momentum
    if change_15 is not None:
        if change_15 > 0.3 and bullish_count >= 2:
            score += 5
            reasons.append("15-minute momentum confirms bulls")
        elif change_15 < -0.3 and bearish_count >= 2:
            score -= 5
            reasons.append("15-minute momentum confirms bears")

    if change_60 is not None:
        if change_60 > 0.5 and bullish_count >= 2:
            score += 10
            reasons.append("1-hour momentum confirms bulls")
        elif change_60 < -0.5 and bearish_count >= 2:
            score -= 10
            reasons.append("1-hour momentum confirms bears")

    # Strategy agreement bonus
    bullish_strategies = sum(
        1 for data in strategies.values()
        if data["signal"] == "BULLISH"
    )

    bearish_strategies = sum(
        1 for data in strategies.values()
        if data["signal"] == "BEARISH"
    )

    if bullish_strategies >= 2:
        score += 10
        reasons.append("multiple strategies agree on bullish conditions")

    if bearish_strategies >= 2:
        score -= 10
        reasons.append("multiple strategies agree on bearish conditions")

    # Regime protection
    if regime == "HIGH VOLATILITY":
        score -= 5
        reasons.append("high volatility increases risk")

    elif regime == "UNCLEAR":
        reasons.append("unclear market regime - avoid forcing trades")

    score = max(0, min(100, score))

    # Verdict safety rules
    if "COLLECTING" in trends.values():
        verdict = "PRELIMINARY - COLLECTING DATA"

    elif pullback_status in [
        "OVERBOUGHT - WAIT FOR PULLBACK",
        "WAITING FOR DEEPER PULLBACK",
        "PULLBACK DETECTED - WAIT FOR CONFIRMATION"
    ]:
        verdict = "BULLISH - WAIT FOR PULLBACK"

    elif regime == "UNCLEAR":
        verdict = "NO TRADE - UNCLEAR"

    elif pullback_status == "PULLBACK CONFIRMED - BULLISH RE-ENTRY":
        verdict = "STRONG BUY SETUP"
        reasons.append("bullish pullback confirmed")

    elif score >= 80 and bullish_strategies >= 2:
        verdict = "STRONG BUY SETUP"

    elif score >= 65:
        verdict = "BULLISH BIAS"

    elif score <= 20 and bearish_strategies >= 2:
        verdict = "STRONG SELL / AVOID"

    elif score <= 40:
        verdict = "BEARISH BIAS"

    else:
        verdict = "WAIT"

    return score, verdict, reasons


history = load_history()

print(f"Loaded {len(history)} previous price readings.\n")

while True:
    try:
        url = "https://api.coinbase.com/v2/prices/BTC-GBP/spot"
        response = requests.get(url, timeout=10)
        data = response.json()

        price = float(data["data"]["amount"])
        timestamp = datetime.now()

        history.append({
            "timestamp": timestamp,
            "price": price
        })

        with open(history_file, "a", newline="") as file:
            writer = csv.writer(file)

            if history_file.stat().st_size == 0:
                writer.writerow(["timestamp", "price"])

            writer.writerow([
                timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                price
            ])

        print("\n" + "=" * 60)
        print(timestamp.strftime("%Y-%m-%d %H:%M:%S"))
        print(f"BITCOIN: £{price:,.2f}")
        print("-" * 60)

        # Movements
        movements = {}

        for minutes, label in [(15, "15m"), (60, "1h"), (1440, "24h")]:
            old_price = get_price_from_minutes_ago(
                history,
                minutes,
                timestamp
            )

            movements[label] = movement_percent(price, old_price)

            if movements[label] is not None:
                print(
                    f"{label} movement: "
                    f"{movements[label]:+.2f}%"
                )
            else:
                print(f"{label} movement: Waiting for data")

        # Timeframes
        prices_1m = [row["price"] for row in history]
        prices_5m = get_timeframe_prices(history, 5)
        prices_15m = get_timeframe_prices(history, 15)
        prices_60m = get_timeframe_prices(history, 60)

        rsi = calculate_rsi(prices_1m)
        volatility = calculate_volatility(prices_1m)

        trends = {}
        trends["1m"], _, _ = get_trend(prices_1m)
        trends["5m"], _, _ = get_trend(prices_5m)
        trends["15m"], _, _ = get_trend(prices_15m)
        trends["1h"], _, _ = get_trend(prices_60m)

        # Regime
        regime, regime_reason = get_market_regime(
            trends,
            movements["15m"],
            movements["1h"],
            volatility
        )

        # Pullback
        pullback_status, pullback_percent = update_pullback_state(
            price,
            rsi,
            trends,
            timestamp
        )

        # Strategies
        strategies = {}

        trend_signal, trend_score = trend_strategy(
            trends,
            regime
        )

        strategies["TREND"] = {
            "signal": trend_signal,
            "score": trend_score
        }

        pullback_signal, pullback_score = pullback_strategy(
            pullback_status,
            trends
        )

        strategies["PULLBACK"] = {
            "signal": pullback_signal,
            "score": pullback_score
        }

        momentum_signal, momentum_score = momentum_strategy(
            movements["15m"],
            movements["1h"],
            trends
        )

        strategies["MOMENTUM"] = {
            "signal": momentum_signal,
            "score": momentum_score
        }

        best_strategy = get_best_strategy(strategies)

        # Final decision
        score, verdict, reasons = get_sentinel_verdict(
            rsi,
            trends,
            movements["15m"],
            movements["1h"],
            regime,
            pullback_status,
            strategies
        )

        # Output
        print("\n--- MULTI-TIMEFRAME INTELLIGENCE ---")

        if rsi is not None:
            print(f"RSI (1m): {rsi:.1f}")
        else:
            print("RSI: Collecting")

        if volatility is not None:
            print(f"Volatility: {volatility:.3f}%")
        else:
            print("Volatility: Collecting")

        print()
        print(f"1m Trend:  {trends['1m']}")
        print(f"5m Trend:  {trends['5m']}")
        print(f"15m Trend: {trends['15m']}")
        print(f"1h Trend:  {trends['1h']}")

        print("\n--- MARKET REGIME ---")
        print(f"Regime: {regime}")
        print(f"Reason: {regime_reason}")

        print("\n--- PULLBACK ENGINE ---")
        print(f"Status: {pullback_status}")

        if pullback_percent is not None:
            print(
                f"Pullback from overbought high: "
                f"{pullback_percent:.2f}%"
            )

        print("\n--- STRATEGY INTELLIGENCE ---")

        for name, data in strategies.items():
            print(
                f"{name.title()} Strategy: "
                f"{data['signal']} | "
                f"Score: {data['score']}/100"
            )

        print(f"\nBEST STRATEGY: {best_strategy}")

        print("\n" + "=" * 60)
        print(f"SENTINEL SCORE: {score}/100")
        print(f"VERDICT: {verdict}")

        if reasons:
            print("\nWHY:")
            for reason in reasons:
                print(f"- {reason}")

        print("=" * 60)

        # Alerts
        if verdict in [
            "STRONG BUY SETUP",
            "STRONG SELL / AVOID"
        ]:
            message = (
                f"{verdict} | Score: {score}/100 | "
                f"BTC: £{price:,.0f} | "
                f"Best: {best_strategy}"
            )

            send_notification(
                "Sentinel AI Signal",
                message
            )

    except Exception as error:
        print(f"Error getting Bitcoin price: {error}")

    time.sleep(60)