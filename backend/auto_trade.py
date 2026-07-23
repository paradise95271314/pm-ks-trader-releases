"""
PM-Kalshi 套利自动交易引擎
从 bot_config.json 读取配置，支持动态修改
"""
import sys, os, json, threading, time, datetime
from app_paths import AUTO_STATE_FILE, AUTO_STATUS_FILE, HISTORY_FILE
from settings_manager import DEFAULT_CONFIG, load_config, save_config
from get_current_markets import get_coin_market_urls
from coin_config import get_supported_coins
from fetch_current_polymarket import fetch_polymarket_data_struct
from fetch_current_kalshi import fetch_kalshi_data_struct
from execute_arb import execute_arb, get_ks_ticker

_config = load_config()
ENABLED_COINS = _config["enabled_coins"]

# ======== 全局状态 ========
_lock = threading.Lock()
_STATUS_FILE = str(AUTO_STATUS_FILE)
_HISTORY_FILE = str(HISTORY_FILE)
_STATE_FILE = str(AUTO_STATE_FILE)

def _load_enabled():
    try: return open(_STATUS_FILE).read().strip() == "1"
    except: return False

def _save_enabled(v):
    try:
        with open(_STATUS_FILE, "w") as f: f.write("1" if v else "0")
    except: pass

_enabled = _load_enabled()
_last_trade_time = 0
_last_trade_result = {}
_trade_count = 0
_consecutive_fails = 0
def _load_history():
    try:
        with open(_HISTORY_FILE) as f: return json.load(f)
    except: return []

def _save_history(h):
    try:
        with open(_HISTORY_FILE, "w") as f: json.dump(h, f)
    except: pass

def _save_state():
    try:
        with open(_STATE_FILE, "w") as f:
            json.dump({"hourly_trades": _hourly_trades, "residual_positions": {k: dict(v) for k, v in _residual_positions.items()}, "active_positions": {k: v for k, v in _active_positions.items()},
                       "last_trade_hour": _last_trade_hour,
                       "last_trade_time": _last_trade_time, "trade_count": _trade_count,
                       "consecutive_fails": _consecutive_fails}, f)
    except: pass

def _load_state():
    try:
        with open(_STATE_FILE) as f:
            s = json.load(f)
            _hourly_trades.update(s.get("hourly_trades", {}))
            _active_positions.clear()
            for k, v in s.get("active_positions", {}).items():
                if time.time() - v < 4500:
                    _active_positions[k] = v
            _residual_positions.clear()
            for k, v in s.get("residual_positions", {}).items():
                if time.time() - v.get("time", 0) < 7200:
                    _residual_positions[k] = dict(v)
            return s.get("last_trade_hour"), s.get("last_trade_time", 0), s.get("trade_count", 0), s.get("consecutive_fails", 0)
    except:
        return None, 0, 0, 0
    return None, 0, 0, 0

_trade_history = _load_history()
_current_profit_threshold = _config["min_profit_cents"]
_last_trade_hour = None
_hourly_trades = {}  # coin -> count for current hour
_active_positions = {}  # coin -> timestamp when position was opened
_residual_positions = {}  # coin -> dict: qty, token_id, time (PM残留) (用于持仓判断)
# Load state from disk
__import__("time").sleep(1)  # let _load_state func definition settle
_restored = _load_state()
if _restored[0] is not None:
    _last_trade_hour = _restored[0]
    _last_trade_time = _restored[1]
    _trade_count = _restored[2]
    _consecutive_fails = _restored[3]
    print("[AutoTrade] 恢复状态: hour=%s trades=%d last=%.0f fails=%d" % _restored)
_consecutive_fails = 0

def get_config():
    return load_config()

def reload_config():
    global _config, _current_profit_threshold, ENABLED_COINS

    _config = load_config()
    ENABLED_COINS = _config["enabled_coins"]
    _current_profit_threshold = _config["min_profit_cents"]
def _fetch_balances():
    """获取两边余额，失败返回 -1"""
    import sys as _sys
    try:
        from py_clob_client_v2 import ClobClient
        from py_clob_client_v2.clob_types import BalanceAllowanceParams
        from kalshi_auth import get_private_key as _gk, fetch_with_auth as _fwa
        key = os.environ.get("POLYMARKET_PRIVATE_KEY") or os.environ.get("PRIVATE_KEY")
        funder = os.environ.get("POLYMARKET_FUNDER")
        sig_type = int(os.environ.get("POLYMARKET_SIGNATURE_TYPE", "0"))
        bc = ClobClient("https://clob.polymarket.com", key=key, chain_id=137, signature_type=sig_type, funder=funder)
        creds = bc.derive_api_key()
        bc.set_api_creds(creds)
        pm_b = float(bc.get_balance_allowance(BalanceAllowanceParams(asset_type="COLLATERAL")).get("balance", 0)) / 1_000_000
    except Exception:
        pm_b = -1
    try:
        kk = _gk()
        ks_b = float(_fwa(kk, "/portfolio/balance").get("balance_dollars", 0))
    except Exception:
        ks_b = -1
    return pm_b, ks_b



# ==================== 每小时只下一单 相关逻辑 ====================

def can_trade_this_hour(coin: str) -> bool:
    """判断这个币种本小时是否还能下单"""
    cfg = _config
    max_trades = cfg.get("max_trades_per_hour", 1)

    # 1. 已有未结算持仓 → 拒绝
    if coin in _active_positions:
        age = time.time() - _active_positions[coin]
        if age < 4500:  # 1小时15分钟内视为还在持仓
            print(f"[AutoTrade] [限制] {coin} 本小时已有持仓（{age:.0f}秒前），跳过")
            return False
        else:
            del _active_positions[coin]

    # 2. 本小时下单次数达到上限（持仓已结算时自动清空）
    current_count = _hourly_trades.get(coin, 0)
    if current_count >= max_trades:
        if coin not in _active_positions:
            _hourly_trades[coin] = 0
            print(f"[AutoTrade] [限制] {coin} 持仓已结算，重置小时计数")
            return True
        print(f"[AutoTrade] [限制] {coin} 本小时已下 {current_count} 单，达到上限 {max_trades}")
        return False

    return True


def _check_balances_before_trade(pm_price_cents, ks_price_cents):
    """交易前余额检查：不够则skip，总余额过低则停"""
    global _consecutive_fails
    pm_bal, ks_bal = _fetch_balances()
    min_shares = _config["min_shares"]
    order_shares = max(int(_config.get("order_shares", 0) or 0), int(min_shares))
    min_total = _config["min_total_balance"]
    pm_cost = order_shares * (pm_price_cents / 100)
    ks_cost = order_shares * (ks_price_cents / 100)
    total = (max(pm_bal, 0) + max(ks_bal, 0)) if pm_bal >= 0 or ks_bal >= 0 else 0

    print("[AutoTrade] 余额检查: PM=$%.2f KS=$%.2f 总计=$%.2f (最低$%.2f)  需PM$%.2f+KS$%.2f" % (max(pm_bal,0), max(ks_bal,0), total, min_total, pm_cost, ks_cost))

    if 0 < total < min_total:
        print("[AutoTrade] 总余额$%.2f < $%.2f，余额耗尽，自动停止" % (total, min_total))
        stop()
        return False

    if pm_bal >= 0 and pm_bal < pm_cost:
        print("[AutoTrade] ❌ PM余额$%.2f不足以支付$%.2f，请充值！自动停止" % (pm_bal, pm_cost))
        stop()
        return False
    if ks_bal >= 0 and ks_bal < ks_cost:
        print("[AutoTrade] ❌ KS余额$%.2f不足以支付$%.2f，请充值！自动停止" % (ks_bal, ks_cost))
        stop()
        return False

    _consecutive_fails = 0
    return True


def get_status():
    with _lock:
        remaining = max(0, _config["cooldown"] - (time.time() - _last_trade_time))
        cfg = load_config()
        return {
            "enabled": _enabled,
            "cooldown_remaining": round(remaining, 1),
            "last_trade_time": _last_trade_time,
            "last_trade_result": _last_trade_result,
            "trade_count": _trade_count,
            "trade_history": _trade_history[-50:],
            "config": {
                "poll_interval": cfg["poll_interval"],
                "cooldown": cfg["cooldown"],
                "min_profit_cents": cfg["min_profit_cents"],
                "price_min_cents": cfg["price_min_cents"],
                "price_max_cents": cfg["price_max_cents"],
                "start_delay_mins": cfg["start_delay_mins"],
                "min_shares": cfg["min_shares"],
                "order_shares": cfg.get("order_shares", 0),
                "min_total_balance": cfg["min_total_balance"],
                "target_usd": cfg["target_usd"],
            },
        }

def start():
    global _enabled
    with _lock:
        _enabled = True
        _save_enabled(True)
        print("[AutoTrade] 自动交易已开启")

def stop():
    global _enabled
    with _lock:
        _enabled = False
        _save_enabled(False)
        print("[AutoTrade] 自动交易已停止")


def _is_after_start_delay():
    if not _config.get("market_start_time", ""):
        minute = datetime.datetime.now().minute
        sd = _config["start_delay_mins"]
        if minute < sd or minute >= 60 - sd:
            return False
        return True
    try:
        start = datetime.datetime.fromisoformat(_config["market_start_time"]).timestamp()
        return time.time() >= start + _config["start_delay_mins"] * 60
    except:
        return True


def _decide_best_opp():
    if not _is_after_start_delay():
        return None

    urls = get_coin_market_urls()
    best = None
    best_margin = 0
    cfg = _config
    threshold = _current_profit_threshold

    for symbol in ENABLED_COINS:
        info = urls.get(symbol)
        if not info:
            continue

        poly, perr = fetch_polymarket_data_struct(info["polymarket_slug"], info["binance_symbol"])
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

        kalshi, kerr = fetch_kalshi_data_struct(info["kalshi_event_ticker"], info["binance_symbol"])
        if not kalshi:
            continue
        if kalshi.get("isFinished", False):
            continue

        pmin = cfg["price_min_cents"]
        pmax = cfg["price_max_cents"]

        kalshi_markets = kalshi.get("markets", [])
        for km in kalshi_markets:
            ks = km["strike"]
            # Buying must be priced from asks. Using bids creates false
            # opportunities and IOC orders that cannot cross the spread.
            ky_cents = km["yes_ask"] * 100
            kn_cents = km["no_ask"] * 100
            ticker = km.get("ticker", "")

            if pstrike > ks:
                cost = poly_down_cents + ky_cents
                profit = 100 - cost
                if not (pmin <= poly_down_cents <= pmax):
                    continue
                if profit < threshold:
                    continue
                margin = profit / cost
                if margin > best_margin:
                    best = {"coin": symbol, "poly_leg": "Down", "ks_ticker": ticker,
                            "total_cost_cents": cost, "kalshi_strike": ks, "profit_cents": profit,
                            "pm_price_cents": poly_down_cents, "ks_price_cents": ky_cents, "ks_price": ky_cents / 100.0,
                            "ks_side": "yes", "token_id": None}
                    best_margin = margin

            elif pstrike < ks:
                cost = poly_up_cents + kn_cents
                profit = 100 - cost
                if not (pmin <= poly_up_cents <= pmax):
                    continue
                if profit < threshold:
                    continue
                margin = profit / cost
                if margin > best_margin:
                    best = {"coin": symbol, "poly_leg": "Up", "ks_ticker": ticker,
                            "total_cost_cents": cost, "kalshi_strike": ks, "profit_cents": profit,
                            "pm_price_cents": poly_up_cents, "ks_price_cents": kn_cents, "ks_price": kn_cents / 100.0,
                            "ks_side": "no", "token_id": None}
                    best_margin = margin

            else:
                cost1 = poly_down_cents + ky_cents
                cost2 = poly_up_cents + kn_cents
                for cost, leg in [(cost1, "Down"), (cost2, "Up")]:
                    profit = 100 - cost
                    pm_cents = poly_down_cents if leg == "Down" else poly_up_cents
                    if not (pmin <= pm_cents <= pmax):
                        continue
                    if profit < threshold:
                        continue
                    margin = profit / cost
                    if margin > best_margin:
                        best = {"coin": symbol, "poly_leg": leg, "ks_ticker": ticker,
                                "total_cost_cents": cost, "kalshi_strike": ks, "profit_cents": profit,
                                "pm_price_cents": pm_cents, "ks_price_cents": ky_cents if leg == "Down" else kn_cents, "ks_price": (ky_cents if leg == "Down" else kn_cents) / 100.0,
                                "ks_side": "yes" if leg == "Down" else "no",
                                "token_id": None}
                        best_margin = margin

    if best:
        try:
            import requests as _req
            _bslug = urls.get(best["coin"], {}).get("polymarket_slug", "")
            if _bslug:
                _gr = _req.get("https://gamma-api.polymarket.com/events?slug=" + _bslug, timeout=5).json()
                _gm = _gr[0]["markets"][0]
                _cids = json.loads(_gm.get("clobTokenIds", "[]"))
                _outs = json.loads(_gm.get("outcomes", "[]"))
                for _oc, _cid in zip(_outs, _cids):
                    if _oc.upper() == best["poly_leg"].upper():
                        best["token_id"] = _cid
                        break
        except Exception:
            pass
    if not best and ENABLED_COINS:
        _prices = []
        for _sym in ENABLED_COINS:
            _u = urls.get(_sym, {})
            if _u:
                try:
                    _p, _ = fetch_polymarket_data_struct(_u["polymarket_slug"], _u["binance_symbol"])
                    if _p:
                        _prices.append("%s: Up=%.0f Down=%.0f" % (_sym, _p["prices"]["Up"]*100, _p["prices"]["Down"]*100))
                except:
                    pass
        if _prices:
            print("[AutoTrade] 扫描完成: 无有效套利, %s" % " | ".join(_prices))
    return best


def _loop():
    global _last_trade_time, _last_trade_result, _trade_count, _current_profit_threshold, _last_trade_hour, _consecutive_fails, _hourly_trades, _active_positions, _residual_positions
    cfg = _config
    print("[AutoTrade] 后台引擎已启动 (min_profit=%d¢, price_range=%d-%d¢)" % (
        cfg["min_profit_cents"], cfg["price_min_cents"], cfg["price_max_cents"]))
    while True:
        try:
            cfg = _config
            if not _enabled:
                _current_profit_threshold = cfg["min_profit_cents"]
                time.sleep(cfg["poll_interval"])
                continue

            now = time.time()
            current_hour = datetime.datetime.now().hour
            if _last_trade_hour is None:
                _last_trade_hour = current_hour
            elif current_hour != _last_trade_hour:
                _current_profit_threshold = cfg["min_profit_cents"]
                _last_trade_hour = current_hour
                print("[AutoTrade] 新小时开始，利润门槛重置为 %d¢" % cfg["min_profit_cents"])
                _hourly_trades.clear()
                # PM结算约整点后10-15分钟，15分钟后清持仓
                if datetime.datetime.now().minute >= 15:
                    _active_positions.clear()
                _save_state()

            if now - _last_trade_time < cfg["cooldown"]:
                time.sleep(cfg["poll_interval"])
                continue

            # ===== 整点前后8分钟内不下单 =====
            minute = datetime.datetime.now().minute
            if minute < 8 or minute >= 52:
                time.sleep(cfg["poll_interval"])
                continue
            # ==================================

            opp = _decide_best_opp()
            if not opp:
                time.sleep(cfg["poll_interval"])
                continue

            print("[AutoTrade] 发现机会: %s %s cost=%.1f¢ profit=%.1f¢ ks_strike=%s" % (
                opp["coin"], opp["poly_leg"], opp["total_cost_cents"],
                opp["profit_cents"], opp["kalshi_strike"]))

            if not _check_balances_before_trade(opp["pm_price_cents"], opp["ks_price_cents"]):
                time.sleep(cfg["poll_interval"])
                continue

            # ===== 每小时只下一单检查 =====
            coin = opp["coin"]
            if not can_trade_this_hour(coin):
                time.sleep(cfg["poll_interval"])
                continue
            # ==================================

            print("[AutoTrade] 下单参数: %s %s strike=%.0f ks_price=%.4f token_id=%s target=%.1f" % (
                opp["coin"], opp["poly_leg"], opp["kalshi_strike"],
                opp["ks_price"], opp.get("token_id", "")[:20],
                cfg.get("target_usd", 10.0)))
            result = execute_arb(
                coin=opp["coin"],
                pm_direction=opp["poly_leg"],
                ks_ticker=opp["ks_ticker"],
                ks_side=opp.get("ks_side", "yes"),
                ks_price=opp["ks_price"],
                token_id=opp.get("token_id", ""),
                target_usd=cfg.get("target_usd", 10.0),
                min_shares=cfg.get("min_shares", 0),
                ks_strike=opp.get("kalshi_strike", 0),
                min_profit_cents=cfg.get("min_profit_cents", 0),
                fixed_shares=cfg.get("order_shares", 0),
                liquidity_buffer=cfg.get("liquidity_buffer", 2.0),
            )

            if result is None:
                result = {"success": False, "error": "execute_arb返回None（内部bug）"}

            with _lock:
                _last_trade_time = time.time()
                _last_trade_result = {
                    "time": datetime.datetime.now().isoformat(),
                    "coin": opp["coin"],
                    "poly_leg": opp["poly_leg"],
                    "kalshi_leg": "Yes" if opp.get("ks_side", "yes") == "yes" else "No",
                    "kalshi_strike": opp["kalshi_strike"],
                    "total_cost_cents": opp["total_cost_cents"],
                    "profit_cents": opp["profit_cents"],
                    "success": result.get("success", False),
                    "error": result.get("error", ""),
                }
                if result.get("success"):
                    _active_positions[coin] = time.time()
                    _hourly_trades[coin] = _hourly_trades.get(coin, 0) + 1
                    _trade_count += 1
                # 记录残留PM持仓（卖回失败剩余的token）
                _pm_close = result.get("pm_close", {})
                _pm_remaining = float(_pm_close.get("remaining", 0))
                if _pm_remaining > 0.01:
                    _residual_positions[coin] = {
                        "qty": _pm_remaining,
                        "token_id": opp.get("token_id", ""),
                        "time": time.time(),
                        "coin": coin,
                        "poly_leg": opp.get("poly_leg", ""),
                    }
                    print("[AutoTrade] [残留] %s 仍有%.1f张PM token未卖出" % (coin, _pm_remaining))
                _save_state()
                _trade_history.append({
                    "time": datetime.datetime.now().isoformat(),
                    "coin": opp["coin"],
                    "poly_leg": opp["poly_leg"],
                    "kalshi_leg": "Yes" if opp.get("ks_side", "yes") == "yes" else "No",
                    "kalshi_strike": opp["kalshi_strike"],
                    "total_cost_cents": opp["total_cost_cents"],
                    "profit_cents": opp["profit_cents"],
                    "success": result.get("success", False),
                    "error": result.get("error", ""),
                    "pm_filled_qty": result.get("pm", {}).get("filled_qty", 0),
                    "ks_fill_count": result.get("ks", {}).get("fill_count", 0),
                    "hedged_qty": result.get("hedged_qty", 0),
                    "pm_price": result.get("pm_plan", {}).get("price", 0),
                    "ks_price": result.get("ks_plan", {}).get("price", 0),
                    "token_id": result.get("token_id", opp.get("token_id", "")),
                    "ks_ticker": result.get("ks_ticker", opp.get("ks_ticker", "")),
                    "ks_side": opp.get("ks_side", "yes"),
                    "size_warning": result.get("size_warning", ""),
                    "pm_close_status": result.get("pm_close", {}).get("status", ""),
                    "ks_close_status": result.get("ks_close", {}).get("status", ""),
                })
                _save_history(_trade_history)

            if (result.get("unhedged_qty", 0) or 0) > 0 and cfg.get("stop_on_unhedged", True):
                print("[AutoTrade] [熔断] 检测到%s单腿残留%.2f张，自动交易已停止" % (
                    result.get("unhedged_platform", "未知"), float(result.get("unhedged_qty", 0))))
                stop()

            if result.get("success"):
                print("[AutoTrade] ✅ 成功: %s %s KS=%s (利润%.1f¢)" % (
                    opp["coin"], opp["poly_leg"], opp.get("ks_side", "?").upper(), opp["profit_cents"]))
            else:
                _consecutive_fails += 1
                extra_wait = min(cfg["fail_cooldown_base"] * _consecutive_fails, cfg["fail_cooldown_max"])
                print("[AutoTrade] ❌ 失败(第%d次连续): %s  额外冷却%d秒" % (_consecutive_fails, result.get("error", ""), extra_wait))
                with _lock:
                    _last_trade_time = time.time() - cfg["cooldown"] + extra_wait
                    _save_state()

        except Exception as e:
            import traceback; print("[AutoTrade] 异常:\n" + traceback.format_exc())

        time.sleep(cfg["poll_interval"])


_thread = threading.Thread(target=_loop, daemon=True)
_thread.start()

if __name__ == '__main__':
    while True:
        try:
            __import__('time').sleep(60)
        except KeyboardInterrupt:
            break
