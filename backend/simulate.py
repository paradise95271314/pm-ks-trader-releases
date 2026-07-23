"""
PM-Kalshi 套利模拟测试
- 使用真实市场数据
- 不执行真实下单
- 记录每一笔模拟交易
- 每小时后检查结算结果
- 运行到 UTC 2026-07-19 12:00
"""
import sys, os, json, time, datetime, requests

BASE = "/home/ubuntu/polymarket-kalshi-btc-arbitrage-bot/backend"
sys.path.insert(0, BASE)
os.chdir(BASE)

from get_current_markets import get_coin_market_urls
from fetch_current_polymarket import fetch_polymarket_data_struct
from fetch_current_kalshi import fetch_kalshi_data_struct
from coin_config import get_supported_coins

POLL_INTERVAL = 3
COOLDOWN = 30
MIN_PROFIT_CENTS = 5
PRICE_MIN_CENTS = 1
PRICE_MAX_CENTS = 99
ENABLED_COINS = ["BTC", "ETH"]
RESULTS_FILE = "/tmp/simulation_results.json"
END_TIME = datetime.datetime(2026, 7, 19, 12, 0, 0, tzinfo=datetime.timezone.utc).timestamp()
HEARTBEAT_INTERVAL = 30


def load_results():
    try:
        with open(RESULTS_FILE) as f:
            return json.load(f)
    except:
        return {"trades": [], "settled": [], "status": "running", "started_at": None}


def save_results(data):
    with open(RESULTS_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def get_current_hour_utc():
    return datetime.datetime.now(datetime.timezone.utc).hour

def get_market_summary():
    parts = []
    try:
        urls = get_coin_market_urls()
        for sym in ENABLED_COINS:
            info = urls.get(sym)
            if not info:
                continue
            poly, _ = fetch_polymarket_data_struct(info['polymarket_slug'], info['binance_symbol'])
            if poly:
                up = poly['prices'].get('Up', 0) * 100
                dn = poly['prices'].get('Down', 0) * 100
                parts.append('%s PM=%d/%d' % (sym, up, dn))
            else:
                parts.append('%s PM=NA' % sym)
            ks, _ = fetch_kalshi_data_struct(info['kalshi_event_ticker'], info['binance_symbol'])
            if ks:
                parts.append('KS=%dm' % len(ks.get('markets', [])))
            else:
                parts.append('KS=NA')
    except:
        parts.append('ERR')
    return ' | '.join(parts)


def decide_best_opp():
    urls = get_coin_market_urls()
    best = None
    best_margin = 0
    for symbol in ENABLED_COINS:
        info = urls.get(symbol)
        if not info:
            continue
        poly, perr = fetch_polymarket_data_struct(
            info["polymarket_slug"], info["binance_symbol"]
        )
        if not poly:
            continue
        pstrike = poly["price_to_beat"]
        if pstrike is None:
            continue
        poly_up_cents = poly["prices"].get("Up", 0) * 100
        poly_down_cents = poly["prices"].get("Down", 0) * 100
        if poly_up_cents == 0 or poly_down_cents == 0:
            continue
        if not poly.get("hasLiquidity", True):
            continue
        kalshi, kerr = fetch_kalshi_data_struct(
            info["kalshi_event_ticker"], info["binance_symbol"]
        )
        if not kalshi:
            continue
        if kalshi.get("isFinished", False):
            continue
        for km in kalshi.get("markets", []):
            ks = km["strike"]
            ky_cents = km["yes_ask"] * 100
            kn_cents = km["no_ask"] * 100
            tk = km.get("ticker", "")
            if pstrike > ks:
                cost = poly_down_cents + ky_cents
                profit = 100 - cost
                if not (PRICE_MIN_CENTS <= poly_down_cents <= PRICE_MAX_CENTS):
                    continue
                if profit < MIN_PROFIT_CENTS:
                    continue
                margin = profit / cost
                if margin > best_margin:
                    best = {
                        "coin": symbol, "poly_leg": "Down", "ks_ticker": tk,
                        "total_cost_cents": cost, "kalshi_strike": ks, "profit_cents": profit,
                        "pm_price_cents": poly_down_cents, "ks_price_cents": ky_cents,
                        "ks_side": "yes",
                    }
                    best_margin = margin
            elif pstrike < ks:
                cost = poly_up_cents + kn_cents
                profit = 100 - cost
                if not (PRICE_MIN_CENTS <= poly_up_cents <= PRICE_MAX_CENTS):
                    continue
                if profit < MIN_PROFIT_CENTS:
                    continue
                margin = profit / cost
                if margin > best_margin:
                    best = {
                        "coin": symbol, "poly_leg": "Up", "ks_ticker": tk,
                        "total_cost_cents": cost, "kalshi_strike": ks, "profit_cents": profit,
                        "pm_price_cents": poly_up_cents, "ks_price_cents": kn_cents,
                        "ks_side": "no",
                    }
                    best_margin = margin
            else:
                for cost, leg in [
                    (poly_down_cents + ky_cents, "Down"),
                    (poly_up_cents + kn_cents, "Up"),
                ]:
                    profit = 100 - cost
                    pm_cents = poly_down_cents if leg == "Down" else poly_up_cents
                    if not (PRICE_MIN_CENTS <= pm_cents <= PRICE_MAX_CENTS):
                        continue
                    if profit < MIN_PROFIT_CENTS:
                        continue
                    margin = profit / cost
                    if margin > best_margin:
                        best = {
                            "coin": symbol, "poly_leg": leg, "ks_ticker": tk,
                            "total_cost_cents": cost, "kalshi_strike": ks,
                            "profit_cents": profit, "pm_price_cents": pm_cents,
                            "ks_price_cents": ky_cents if leg == "Down" else kn_cents,
                            "ks_side": "yes" if leg == "Down" else "no",
                        }
                        best_margin = margin
    return best


def check_settlement(trade):
    result = {
        "trade_idx": trade["idx"], "pm_outcome": None, "ks_result": None,
        "arb_correct": None, "checked_at": None,
    }
    try:
        r = requests.get(
            f"https://gamma-api.polymarket.com/events?slug={trade['pm_slug']}",
            timeout=10,
        )
        if r.ok and r.json():
            m = r.json()[0]["markets"][0]
            result["pm_outcome"] = m.get("outcome")
            result["pm_settled"] = result["pm_outcome"] is not None
    except:
        result["pm_settled"] = False
    try:
        from kalshi_auth import load_key, fetch_with_auth
        kkey = load_key(os.path.join(BASE, "kalshi_key.pem"))
        mkt = fetch_with_auth(kkey, "/markets/" + trade["ks_ticker"])
        m = mkt.get("market", {})
        result["ks_result"] = m.get("result")
        result["ks_settled"] = m.get("settled", False)
    except:
        result["ks_settled"] = False
    if result.get("pm_outcome") and result.get("ks_result") is not None:
        pm_won = result["pm_outcome"].lower() == trade["poly_leg"].lower()
        ks_won = result["ks_result"].lower() == trade["ks_side"].lower()
        result["arb_correct"] = pm_won != ks_won
        result["pm_won"] = pm_won
        result["ks_won"] = ks_won
        result["checked_at"] = time.time()
    return result


def run():
    data = load_results()
    if not data.get("started_at"):
        data["started_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    data["status"] = "running"
    trade_counter = len(data.get("trades", []))
    hour_trade_times = {}
    last_heartbeat = time.time()
    last_settle_check_hour = -1

    print("[SIM] 模拟测试启动 - 运行到 UTC 2026-07-19 12:00")
    print(f"[SIM] 结果保存: {RESULTS_FILE}")
    save_results(data)

    while time.time() < END_TIME:
        try:
            now = time.time()
            current_hour = get_current_hour_utc()
            now_dt = datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc)
            now_minute = now_dt.minute

            # Settlement check at minute 5-7
            if 5 <= now_minute <= 7 and last_settle_check_hour != current_hour:
                last_settle_check_hour = current_hour
                prev_hour = (current_hour - 1) % 24
                changed = False
                for t in data.get("trades", []):
                    if t.get("hour") == prev_hour and not t.get("settled"):
                        print(f"[SIM] 结算检查 第{prev_hour}时...")
                        sett = check_settlement(t)
                        t["settlement"] = sett
                        t["settled"] = True
                        data["settled"].append(sett)
                        if sett.get("arb_correct") is True:
                            t["result"] = "WIN"
                            t["actual_profit_cents"] = t["profit_cents"]
                            print(f"[SIM] OK 第{prev_hour}时 套利正确 profit={t['profit_cents']}cent")
                        elif sett.get("arb_correct") is False:
                            t["result"] = "LOSS"
                            t["actual_profit_cents"] = -100
                            print(f"[SIM] FAIL 第{prev_hour}时 套利错误 两边输")
                        else:
                            t["result"] = "PENDING_SETTLE"
                            print(f"[SIM] WAIT 第{prev_hour}时 未完全结算")
                        changed = True
                if changed:
                    save_results(data)

            # Find arbitrage opportunity
            opp = decide_best_opp()
            if opp:
                last_time = hour_trade_times.get(current_hour, 0)
                if now - last_time >= COOLDOWN:
                    trade_counter += 1
                    trade = {
                        "idx": trade_counter,
                        "time": datetime.datetime.fromtimestamp(
                            now, tz=datetime.timezone.utc
                        ).isoformat(),
                        "hour": current_hour,
                        "coin": opp["coin"],
                        "pm_slug": get_coin_market_urls()
                        .get(opp["coin"], {})
                        .get("polymarket_slug", "?"),
                        "poly_leg": opp["poly_leg"],
                        "ks_ticker": opp["ks_ticker"],
                        "ks_side": opp["ks_side"],
                        "kalshi_strike": opp["kalshi_strike"],
                        "pm_price_cents": opp["pm_price_cents"],
                        "ks_price_cents": opp["ks_price_cents"],
                        "total_cost_cents": opp["total_cost_cents"],
                        "profit_cents": opp["profit_cents"],
                        "settled": False,
                        "result": "PENDING",
                    }
                    data["trades"].append(trade)
                    hour_trade_times[current_hour] = now
                    save_results(data)
                    print(
                        f"[SIM] #{trade_counter} {opp['coin']} {opp['poly_leg']} "
                        f"strike={opp['kalshi_strike']} cost={opp['total_cost_cents']}cent "
                        f"profit={opp['profit_cents']}cent KS={opp['ks_side']}"
                    )

            # Heartbeat every 30s
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                last_heartbeat = now
                total = len(data["trades"])
                wins = sum(1 for t in data["trades"] if t["result"] == "WIN")
                losses = sum(1 for t in data["trades"] if t["result"] == "LOSS")
                unsettled = sum(1 for t in data["trades"] if not t["settled"])
                now_s = datetime.datetime.fromtimestamp(
                    now, tz=datetime.timezone.utc
                ).strftime("%H:%M:%S")
                mkt = get_market_summary()
                print(
                    f"[SIM] {now_s} 交易{total}笔 未结算{unsettled} WIN{wins} LOSS{losses} | {mkt}"
                )

        except Exception as e:
            print(f"[SIM] EXC: {e}")

        time.sleep(POLL_INTERVAL)

    # Done
    data["status"] = "completed"
    data["ended_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save_results(data)

    wins = sum(1 for t in data["trades"] if t["result"] == "WIN")
    losses = sum(1 for t in data["trades"] if t["result"] == "LOSS")
    profit = sum(
        t.get("profit_cents", 0) for t in data["trades"] if t["result"] == "WIN"
    )
    loss_val = sum(
        t.get("actual_profit_cents", -100)
        for t in data["trades"]
        if t["result"] == "LOSS"
    )
    net = profit + loss_val
    print(f"\n[SIM] ====== 完成 ======")
    print(f"[SIM] 总交易: {len(data['trades'])} | WIN{wins} | LOSS{losses}")
    print(f"[SIM] 净利: {net}cent (${net/100:.2f})")


if __name__ == "__main__":
    run()
