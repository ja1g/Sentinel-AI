from pathlib import Path
import csv
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FORWARD = Path("crypto_universe_forward_test.csv")
PRICE = Path("crypto_universe_prices.csv")
HOST, PORT = "127.0.0.1", 8765

ASSETS = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LINK", "AVAX", "DOT", "LTC"]


def read_csv(path):
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def snapshot():
    forward = read_csv(FORWARD)
    prices = read_csv(PRICE)
    latest = {}
    for row in prices:
        latest[row["asset"]] = row

    stats = {}
    for asset in ASSETS:
        rows = [r for r in forward if r["asset"] == asset]
        completed = [r for r in rows if r.get("outcome") in ("WIN", "LOSS", "FLAT")]
        wins = sum(r["outcome"] == "WIN" for r in completed)
        avg = None
        if completed:
            avg = sum(float(r["directional_return_pct"]) for r in completed) / len(completed)
        stats[asset] = {
            "price": latest.get(asset, {}).get("price"),
            "signal": rows[-1].get("signal", "WAIT") if rows else "WAIT",
            "score": rows[-1].get("score", "50") if rows else "50",
            "completed": len(completed),
            "win_rate": (wins / len(completed) * 100) if completed else None,
            "avg": avg,
        }

    last_ts = prices[-1]["timestamp"] if prices else None
    return stats, last_ts


def page():
    stats, last_ts = snapshot()
    rows = []
    for asset in ASSETS:
        s = stats[asset]
        price = f"£{float(s['price']):,.6f}" if s["price"] else "—"
        wr = f"{s['win_rate']:.1f}%" if s["win_rate"] is not None else "—"
        avg = f"{s['avg']:+.4f}%" if s["avg"] is not None else "—"
        signal = s["signal"]
        cls = "buy" if signal == "BUY" else "sell" if signal == "SELL" else "wait"
        rows.append(f"<tr><td><b>{asset}</b></td><td>{price}</td><td class='{cls}'>{signal}</td><td>{s['score']}</td><td>{s['completed']}</td><td>{wr}</td><td>{avg}</td></tr>")

    refreshed = last_ts or "waiting for first observation"
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="60"><title>Sentinel Crypto Dashboard V1</title>
<style>
body{{font-family:Arial,sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:32px}} .wrap{{max-width:1250px;margin:auto}} h1{{margin:0 0 6px;font-size:30px}} .sub{{color:#8b949e;margin-bottom:24px}} .grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}} .card{{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:18px}} .label{{color:#8b949e;font-size:12px;text-transform:uppercase}} .value{{font-size:24px;font-weight:bold;margin-top:8px}} .safe{{font-size:16px}} table{{width:100%;border-collapse:collapse;background:#161b22;border:1px solid #30363d;border-radius:10px;overflow:hidden}} th,td{{padding:13px 14px;border-bottom:1px solid #30363d;text-align:right}} th:first-child,td:first-child{{text-align:left}} th{{color:#8b949e;font-size:12px;text-transform:uppercase}} .buy{{font-weight:bold}} .sell{{font-weight:bold}} .wait{{color:#8b949e}} .note{{margin-top:18px;color:#8b949e;font-size:13px}}
</style></head><body><div class='wrap'>
<h1>Sentinel Crypto Dashboard V1</h1><div class='sub'>Evidence first · isolated crypto research · auto-refresh 60 seconds</div>
<div class='grid'><div class='card'><div class='label'>Collection</div><div class='value'>RUNNING</div></div><div class='card'><div class='label'>Universe</div><div class='value'>{len(ASSETS)} assets</div></div><div class='card'><div class='label'>Forward horizon</div><div class='value'>60 min</div></div><div class='card'><div class='label'>Real money</div><div class='value safe'>OFF</div></div></div>
<div class='card' style='margin-bottom:18px'><div class='label'>Latest data</div><div style='margin-top:8px'>{refreshed}</div></div>
<table><thead><tr><th>Asset</th><th>Price</th><th>Signal</th><th>Score</th><th>Completed</th><th>Win rate</th><th>Avg directional return</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<div class='note'>V1 is a baseline research harness. No orders are placed. Promotion requires adequate sample size, realistic costs, multiple periods/regimes, out-of-sample validation and reproducibility.</div>
</div></body></html>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = page().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    print(f"Sentinel Crypto Dashboard V1: http://{HOST}:{PORT}")
    print("Dashboard is read-only and isolated from the existing Sentinel dashboards.")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
