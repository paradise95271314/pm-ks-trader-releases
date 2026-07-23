"""对冲执行模块 — 面板点击"买入"后自动下 PM + KS 两腿"""
import math, json, requests, uuid, urllib.request, base64, time, os, sys, re

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from dotenv import load_dotenv
load_dotenv(override=False)
_legacy_env = "/home/ubuntu/polymarketLP/.env"
if os.path.exists(_legacy_env):
    load_dotenv(_legacy_env, override=False)
from py_clob_client_v2 import ClobClient
from py_clob_client_v2.clob_types import OrderArgsV2, MarketOrderArgsV2, BalanceAllowanceParams, OrderType, OrderType
try:
    from kalshi_auth import fetch_with_auth, get_api_key_id, get_private_key
    _LEGACY_KH = ""
except ImportError:
    from kalshi_auth import KH as _LEGACY_KH, fetch_with_auth, load_key

    def get_api_key_id():
        return _LEGACY_KH

    def get_private_key():
        return load_key(os.path.join(BASE, "kalshi_key.pem"))
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding as pad
from get_current_markets import get_coin_market_urls
from kalshi_order_mapping import build_buy_quote, build_close_quote
from trade_sizing import calculate_hedge_shares

KB = "https://api.elections.kalshi.com/trade-api/v2"
UA = "Mozilla/5.0"


class _LazyKalshiKey:
    def __getattr__(self, name):
        return getattr(get_private_key(), name)


# Preserve imports used by the Linux API without loading credentials at import time.
KKEY = _LazyKalshiKey()
KH = _LEGACY_KH


def _kalshi_resting_volume(orderbook, outcome_side, limit_price):
    """Return contracts executable at or better than an outcome price."""
    book = (orderbook or {}).get("orderbook_fp", orderbook or {})
    outcome_side = str(outcome_side).lower()
    limit_price = float(limit_price)
    if outcome_side == "yes":
        # A YES purchase crosses resting NO bids; YES cost = 1 - NO bid.
        threshold = 1.0 - limit_price
        levels = book.get("no_dollars", []) or []
    elif outcome_side == "no":
        # A NO purchase crosses resting YES bids; NO cost = 1 - YES bid.
        threshold = 1.0 - limit_price
        levels = book.get("yes_dollars", []) or []
    else:
        return 0.0
    total = 0.0
    for level in levels:
        try:
            price, size = float(level[0]), float(level[1])
        except (TypeError, ValueError, IndexError):
            continue
        if price + 1e-9 >= threshold:
            total += size
    return total


def _pm_ask_volume(asks, max_price):
    total = 0.0
    for level in asks or []:
        try:
            price, size = float(level["price"]), float(level["size"])
        except (KeyError, TypeError, ValueError):
            continue
        if price <= float(max_price) + 1e-9:
            total += size
    return total


def get_ks_ticker(event_ticker, strike):
    """从 event_ticker 和 strike 获取完整 KS market ticker"""
    markets = fetch_with_auth(get_private_key(), "/markets?event_ticker=" + event_ticker + "&limit=100")
    for m in markets.get("markets", []):
        sub = m.get("subtitle", "")
        ms = re.search(r'\$([\d,]+)', sub)
        if ms:
            ms_v = float(ms.group(1).replace(",", ""))
            if abs(ms_v - strike) < 1.0:
                return m["ticker"]
    return event_ticker + "-B" + str(int(strike + 50))


def execute_arb(coin, pm_direction, ks_ticker, ks_side="yes", ks_price=None, target_usd=10.0, token_id="", min_shares=0, ks_strike=0.0, min_profit_cents=0.0, fixed_shares=0, liquidity_buffer=2.0, pm_slug="", exact_ks_ticker=False):
    """
    执行对冲：先成交较薄的KS腿，再刷新并成交PM腿
    target_usd: 目标以 PM 价为基准的名义金额（美元），对冲两腿用相同份数

    对冲原理：PM 和 KS 每份/contract 到期都付 $1
      买 N 份 PM + N 份 KS → 任一行情下收到 $N
      成本 = N × (PM_price + KS_price)
      利润 = N × (1 - PM_price - KS_price)  （当 PM_price + KS_price < 1 时）
    """
    result = {"success": False, "pm": {}, "ks": {}, "error": ""}
    ks_side = str(ks_side).strip().lower()
    if ks_side not in ("yes", "no"):
        result["error"] = "KS方向必须是yes或no: " + str(ks_side)
        return result
    try:
        kalshi_key = get_private_key()
        kalshi_api_key_id = get_api_key_id()
    except Exception as exc:
        result["error"] = str(exc)
        return result

    # 查余额（仅供显示，不阻止下单）
    try:
        key = os.environ.get("POLYMARKET_PRIVATE_KEY") or os.environ.get("PRIVATE_KEY")
        funder = os.environ.get("POLYMARKET_FUNDER")
        sig_type = int(os.environ.get("POLYMARKET_SIGNATURE_TYPE", "0"))
        bc = ClobClient("https://clob.polymarket.com", key=key, chain_id=137,
                         signature_type=sig_type, funder=funder)
        creds = bc.derive_api_key()
        bc.set_api_creds(creds)
        pm_bal = float(bc.get_balance_allowance(BalanceAllowanceParams(asset_type="COLLATERAL")).get("balance", 0))
    except Exception:
        pm_bal = -1
    try:
        ks_bal = float(fetch_with_auth(kalshi_key, "/portfolio/balance").get("balance_dollars", 0))
    except Exception:
        ks_bal = -1
    result["balances"] = {"pm": pm_bal, "ks": ks_bal}

    # PM slug：币价模式动态获取；电竞等外部市场可传入已校验的精确slug。
    slug = str(pm_slug or "").strip()
    if not slug:
        try:
            urls = get_coin_market_urls()
            slug = urls.get(coin, {}).get("polymarket_slug", "")
        except Exception as e:
            result["error"] = "获取PM slug失败: " + str(e)[:100]
            return result
    if not slug:
        result["error"] = "未知币种或slug为空: " + coin
        return result

    # PM gamma
    try:
        r = requests.get("https://gamma-api.polymarket.com/events?slug=" + slug,
                         timeout=10, headers={"User-Agent": UA})
        ev = r.json()[0]
        m = ev.get("markets", [{}])[0]
        cids = json.loads(m.get("clobTokenIds", "[]"))
        outs = json.loads(m.get("outcomes", "[]"))
    except Exception as e:
        result["error"] = "PM gamma获取失败: " + str(e)[:100]
        return result

    tid = token_id
    if not tid:
        for oc, cid in zip(outs, cids):
            if oc.upper() == pm_direction.upper():
                tid = cid
                break
        if not tid:
            result["error"] = "PM %s tokenId不存在" % pm_direction
            return result

    # PM CLOB 盘口 — 取最低卖价及可用量
    try:
        b = requests.get("https://clob.polymarket.com/book?token_id=" + tid,
                         timeout=10).json()
        asks = sorted(b.get("asks", []), key=lambda x: float(x["price"]))
    except Exception as e:
        result["error"] = "PM盘口获取失败: " + str(e)[:100]
        return result

    if not asks:
        result["error"] = "PM盘口无卖单"
        return result

    pm_price = float(asks[0]["price"])
    pm_avail = float(asks[0]["size"])
    # ── 对冲份数计算 ──
    # PM最低名义金额 $1，但从目标金额算份数（方便调大）
    # 对冲：PM 和 KS 用相同份数（每份都付 $1）
    if target_usd < 1.0:
        target_usd = 1.0
    hedge_shares, sizing_mode = calculate_hedge_shares(
        pm_price, target_usd, min_shares, fixed_shares)
    required_depth = hedge_shares * max(float(liquidity_buffer or 1.0), 1.0)
    if pm_avail + 1e-9 < required_depth:
        result["error"] = "PM卖一深度不足: 下单%d张, 安全要求%.1f张, 当前仅%.2f张" % (
            hedge_shares, required_depth, pm_avail)
        return result
    # 用固定 target_usd 下单，不按余额调整
    if pm_bal > 0 and hedge_shares * pm_price > pm_bal / 1_000_000:
        result["error"] = "PM余额$%.2f不足以支付$%.2f" % (pm_bal / 1_000_000, hedge_shares * pm_price)
        return result

    result["pm_plan"] = {"price": pm_price, "size": hedge_shares,
                         "notional": round(pm_price * hedge_shares, 2),
                         "sizing_mode": sizing_mode, "order_type": "FOK"}
    result["token_id"] = tid

    # --- KS检查：用event_ticker重新解析正确ticker ---
    try:
        import re as _re
        _found = None
        if exact_ks_ticker:
            _payload = fetch_with_auth(kalshi_key, "/markets/" + ks_ticker)
            _found = _payload.get("market", _payload)
            _et = str(_found.get("event_ticker", ""))
        else:
            _m = _re.match(r'^([A-Z0-9-]+?)-T\d', ks_ticker)
            _et = _m.group(1) if _m else ks_ticker
            _km = fetch_with_auth(kalshi_key, "/markets?event_ticker=" + _et + "&limit=100")
            _kl = _km.get("markets", [])
            for _mk in _kl:
                if _mk.get("ticker") == ks_ticker:
                    _found = _mk
                    break
                _sub = _mk.get("subtitle", "")
                _ms = _re.search(r'\$([\d,]+)', _sub)
                if _ms:
                    _ms_v = float(_ms.group(1).replace(",", ""))
                    if ks_strike > 0 and abs(_ms_v - ks_strike) < 1.0:
                        _found = _mk
                        break
        if not _found:
            result["error"] = "KS ticker重解析失败: event=" + _et + " strike=" + str(ks_strike)
            return result
        # 使用重新解析的正确ticker（修复Kalshi ticker映射问题）
        ks_ticker = _found["ticker"]
        result["ks_ticker"] = ks_ticker
        ks_quote = build_buy_quote(ks_side, _found)
        ks_book_side = ks_quote["book_side"]
        ks_book_price = float(ks_quote["book_price"])
        ks_outcome_price = float(ks_quote["outcome_price"])
        if ks_price is not None and abs(float(ks_price) - ks_outcome_price) >= 0.0001:
            print("[execute_arb] KS报价更新: 扫描=%.4f 实时ask=%.4f" % (float(ks_price), ks_outcome_price))
        ks_price = ks_outcome_price
        live_profit_cents = (1.0 - pm_price - ks_outcome_price) * 100.0
        if live_profit_cents + 1e-9 < float(min_profit_cents):
            result["error"] = "KS报价变化后利润不足: PM=%.2f KS=%.2f profit=%.1f¢ < %.1f¢" % (
                pm_price, ks_outcome_price, live_profit_cents, float(min_profit_cents))
            return result
        result["ks_plan"] = {
            "price": ks_outcome_price,
            "book_price": ks_book_price,
            "book_side": ks_book_side,
            "outcome_side": ks_side,
            "size": hedge_shares,
            "notional": round(ks_outcome_price * hedge_shares, 2),
        }
        ks_orderbook = fetch_with_auth(
            kalshi_key, "/markets/" + ks_ticker + "/orderbook?depth=100")
        ks_available = _kalshi_resting_volume(ks_orderbook, ks_side, ks_outcome_price)
        result["ks_plan"]["available"] = round(ks_available, 4)
        result["ks_plan"]["required_depth"] = round(required_depth, 4)
        if ks_available + 1e-9 < required_depth:
            result["error"] = "KS真实盘口深度不足: 下单%d张, 安全要求%.1f张, 当前仅%.2f张" % (
                hedge_shares, required_depth, ks_available)
            return result
        print("[execute_arb] KS ticker=%s outcome=%s book=%s price=%.4f cost=%.4f 尝试下单%d张" % (
            ks_ticker, ks_side.upper(), ks_book_side, ks_book_price, ks_outcome_price, hedge_shares))
    except Exception as e:
        result["error"] = "KS ticker解析失败: " + str(e)[:80]
        return result

    # --- KS先成交，再刷新PM盘口。KS是更薄的一腿；KS拒单时绝不暴露PM单腿。 ---
    key = os.environ.get("POLYMARKET_PRIVATE_KEY") or os.environ.get("PRIVATE_KEY")
    funder = os.environ.get("POLYMARKET_FUNDER")
    sig_type = int(os.environ.get("POLYMARKET_SIGNATURE_TYPE", "0"))
    client = ClobClient("https://clob.polymarket.com", key=key, chain_id=137,
                         signature_type=sig_type, funder=funder)
    creds = client.derive_api_key()
    client.set_api_creds(creds)
    # KS V2 quotes a single YES book: bid buys YES, ask buys NO.
    ol = {"orders": [{"ticker": ks_ticker, "side": ks_book_side, "count": str(hedge_shares),
        "price": "%.4f" % ks_book_price,
        "time_in_force": "fill_or_kill",
        "self_trade_prevention_type": "taker_at_cross",
        "client_order_id": str(uuid.uuid4())}]}
    fp = "/portfolio/events/orders/batched"
    full_sig_path = "/trade-api/v2" + fp

    def _post_ks(payload, timeout=15):
        ks_ts = str(int(time.time() * 1000))
        ks_msg = ks_ts + "POST" + full_sig_path
        ks_sig = kalshi_key.sign(ks_msg.encode(),
            pad.PSS(mgf=pad.MGF1(hashes.SHA256()), salt_length=pad.PSS.MAX_LENGTH),
            hashes.SHA256())
        ks_headers = {"Content-Type": "application/json", "KALSHI-ACCESS-KEY": kalshi_api_key_id,
                      "KALSHI-ACCESS-SIGNATURE": base64.b64encode(ks_sig).decode(),
                      "KALSHI-ACCESS-TIMESTAMP": ks_ts}
        request = urllib.request.Request(KB + fp, data=json.dumps(payload).encode(), headers=ks_headers)
        return json.loads(urllib.request.urlopen(request, timeout=timeout).read())

    def _place_pm():
        nonlocal pm_price
        live_book = requests.get(
            "https://clob.polymarket.com/book?token_id=" + tid, timeout=10).json()
        live_asks = sorted(live_book.get("asks", []), key=lambda x: float(x["price"]))
        if not live_asks:
            raise RuntimeError("KS成交后PM盘口无卖单")
        max_pm_price = 1.0 - ks_outcome_price - float(min_profit_cents) / 100.0
        executable = [a for a in live_asks if float(a["price"]) <= max_pm_price + 1e-9]
        live_volume = _pm_ask_volume(executable, max_pm_price)
        if live_volume + 1e-9 < hedge_shares:
            raise RuntimeError("KS成交后PM可盈利深度不足: 需要%d张, 当前%.2f张" % (
                hedge_shares, live_volume))
        cumulative = 0.0
        limit_price = 0.0
        for level in executable:
            cumulative += float(level["size"])
            limit_price = float(level["price"])
            if cumulative + 1e-9 >= hedge_shares:
                break
        pm_price = limit_price
        result["pm_plan"].update({
            "price": pm_price,
            "notional": round(pm_price * hedge_shares, 2),
            "available": round(live_volume, 4),
        })
        pmr = client.create_and_post_order(OrderArgsV2(
            token_id=tid, price=round(pm_price, 2), size=float(hedge_shares), side="BUY"),
            order_type=OrderType.FOK)
        return pmr

    def _place_ks():
        return _post_ks(ol)

    pm_res = None
    ks_raw = None
    pm_exc = None
    ks_exc = None
    try:
        ks_raw = _place_ks()
    except Exception as e:
        ks_exc = e

    # === 解析KS结果 ===
    ks_success = False
    ks_fill_count = 0
    ks_order = {}
    if ks_raw and ks_raw.get("orders"):
        ks_order = ks_raw.get("orders", [{}])[0]
        ks_order_error = str(ks_order.get("error"))[:300] if ks_order.get("error") else ""
        # Kalshi V2 events API返回格式: fill_count="0.00"字符串, remaining_count="10.00",
        # average_fill_price只在有成交时出现
        try:
            ks_fill_count = int(float(ks_order.get("fill_count", "0")))
        except (ValueError, TypeError):
            ks_fill_count = 0
        # FOK必须完整成交；不能仅凭average_fill_price推断成交数量。
        ks_success = ks_fill_count >= hedge_shares
        # 调试: 记录原始响应关键字段
        result["ks_debug"] = {"fill_count_raw": str(ks_order.get("fill_count", "N/A")),
                               "remaining_count": str(ks_order.get("remaining_count", "N/A")),
                               "avg_price": str(ks_order.get("average_fill_price", "N/A")),
                               "order_id": str(ks_order.get("order_id", "N/A")),
                               "success": ks_success}
        result["ks"] = {"order_id": ks_order.get("order_id", "?"),
                         "fill_count": ks_fill_count,
                         "filled": ks_success,
                         "avg_price": str(ks_order.get("average_fill_price", "?")),
                         "outcome_side": ks_side,
                         "book_side": ks_book_side}
        if ks_order_error:
            result["ks"]["error"] = ks_order_error
        if ks_success and ks_order.get("order_id"):
            try:
                detail = fetch_with_auth(kalshi_key, "/portfolio/orders/" + str(ks_order["order_id"]))
                actual = str(detail.get("order", {}).get("outcome_side", "")).lower()
                result["ks"]["direction_verified"] = (actual == ks_side)
                result["ks"]["actual_outcome_side"] = actual
                if actual and actual != ks_side:
                    result["direction_alert"] = "KS方向异常: expected=%s actual=%s" % (ks_side, actual)
                    ks_success = False
                    result["ks"]["filled"] = False
            except Exception as e:
                result["ks"]["direction_verify_error"] = str(e)[:100]
    elif ks_exc:
        result["ks"] = {"error": str(ks_exc)[:200]}
    else:
        result["ks"] = {"error": "KS无响应", "filled": False, "fill_count": 0}

    if ks_success:
        try:
            pm_res = _place_pm()
        except Exception as e:
            pm_exc = e

    # === 解析PM结果（必须在KS成交并提交PM之后） ===
    pm_success = False
    pm_filled_qty = 0.0
    if pm_res and pm_res.get("status") == "matched":
        pm_status = pm_res.get("status", "")
        pm_filled_qty = float(pm_res.get("takingAmount", "0") or "0")
        pm_success = pm_filled_qty > 0
        result["pm"] = {"order_id": pm_res.get("order_id", "?"),
                         "status": pm_status, "filled": pm_success,
                         "filled_qty": pm_filled_qty}
        if abs(pm_filled_qty - hedge_shares) >= 0.01:
            result["pm"]["warning"] = "PM价格改善导致数量变化: 请求%d张, 实成%.2f张" % (
                hedge_shares, pm_filled_qty)
    elif pm_exc:
        result["pm"] = {"error": str(pm_exc)[:200], "filled": False, "filled_qty": 0}
        result["error"] = "PM下单失败: " + str(pm_exc)[:100]
    else:
        result["pm"] = {"status": pm_res.get("status", "?") if pm_res else "not_submitted",
                        "filled": False, "filled_qty": 0}

    # === 单腿保护：如果一边失败，卖回另一边 ===
    if pm_success and not ks_success:
        # 只有PM成交，卖回PM — FAK分批卖出
        pm_close_price = 0.0
        pm_close_status = "?"
        pm_close_size = 0.0
        pm_close_remaining = float(pm_filled_qty)
        try:
            __import__("time").sleep(1)
            remaining = float(pm_filled_qty)
            retries = 0
            bids_by_price = {}
            try:
                book = requests.get("https://clob.polymarket.com/book?token_id=" + tid, timeout=10).json()
                for b in book.get("bids", []):
                    bp = float(b["price"])
                    bs = float(b["size"])
                    bids_by_price[bp] = bids_by_price.get(bp, 0) + bs
            except:
                pass
            while remaining > 0.01 and retries < 5 and bids_by_price:
                # 从买入价（pm_price）向下扫，找第一个有量的BID价位
                sp = max(0.01, float(pm_price))
                for tick in range(200):
                    trial = round(sp - tick * 0.01, 2)
                    if trial < 0.01:
                        break
                    if trial in bids_by_price and bids_by_price[trial] >= 0.01:
                        sp = trial
                        break
                if sp < 0.01:
                    break
                pm_close_price = sp
                bid_sz = bids_by_price.get(sp, 0)
                sell_sz = min(remaining, bid_sz)
                if sell_sz < 0.01:
                    break
                sr = None
                for _ in range(3):
                    try:
                        sr = client.create_and_post_order(OrderArgsV2(
                            token_id=tid, price=sp, size=sell_sz, side="SELL"),
                            order_type=OrderType.FAK)
                        break
                    except Exception:
                        __import__("time").sleep(2)
                pm_close_status = sr.get("status", "?") if sr else "?"
                fill = float(sr.get("takingAmount", "0") or "0") if sr else 0
                remaining -= fill
                pm_close_size = float(pm_filled_qty) - remaining
                retries += 1
                if fill <= 0:
                    __import__("time").sleep(1)
            pm_close_remaining = round(remaining, 4)
            if pm_close_remaining > 0.01 and retries >= 5:
                pm_close_status = "FAILED_NO_BIDS"
        except Exception as e:
            pm_close_status = "EXCEPTION"
            pm_close_remaining = float(pm_filled_qty)
            result["pm_close"] = {"error": str(e)[:100], "status": pm_close_status, "remaining": pm_close_remaining}
        else:
            result["pm_close"] = {"price": pm_close_price, "status": pm_close_status, "size": pm_close_size, "remaining": pm_close_remaining}
        if not result.get("error") and pm_close_remaining > 0.01:
            result["error"] = "KS未成交，PM卖回失败(剩余%.1f张)" % pm_close_remaining
            result["unhedged_platform"] = "PM"
            result["unhedged_qty"] = pm_close_remaining
        elif not result.get("error"):
            result["error"] = "KS未成交，已卖回PM"
    elif ks_fill_count > 0 and not pm_success:
        # 只有KS成交，强制卖回KS
        print("[execute_arb] [单腿] KS成交但PM失败，开始强制卖回KS...")
        ks_close_status = "?"
        try:
            close_quote = build_close_quote(ks_side, _found)
            close_side = close_quote["book_side"]
            close_base = float(close_quote["book_price"])
            for discount in [0.05, 0.15, 0.30, 0.50, 0.90]:
                close_price = (max(0.0001, close_base - discount)
                               if close_side == "ask"
                               else min(0.9999, close_base + discount))
                sell_ol = {
                    "orders": [{
                        "ticker": ks_ticker,
                        "side": close_side,
                        "count": str(ks_fill_count),
                        "price": f"{close_price:.4f}",
                        "time_in_force": "immediate_or_cancel",
                        "self_trade_prevention_type": "taker_at_cross",
                        "client_order_id": str(uuid.uuid4())
                    }]
                }
                sell_rj = _post_ks(sell_ol, timeout=12)
                sell_o = sell_rj.get("orders", [{}])[0]
                fill = int(float(sell_o.get("fill_count", 0)))
                print(f"[execute_arb] [单腿] KS卖回尝试 {close_side} 价格{close_price:.4f}, 成交{fill}")
                if fill >= ks_fill_count * 0.9:
                    result["error"] = f"PM未成交，已卖回KS {fill}份"
                    result["ks_close"] = {"fill_count": fill, "price": close_price}
                    break
                time.sleep(0.8)
            else:
                result["error"] = "PM未成交，KS卖回失败"
                result["ks_close"] = {"status": "FAILED", "fill_count": 0}
                result["unhedged_platform"] = "KS"
                result["unhedged_qty"] = ks_fill_count
        except Exception as e:
            result["error"] = f"KS卖回异常: {str(e)[:80]}"
            result["ks_close"] = {"error": str(e)[:80], "fill_count": "0"}
            result["unhedged_platform"] = "KS"
            result["unhedged_qty"] = ks_fill_count
    elif pm_success and ks_success:
        # 两边都成 — 校验数量匹配
        pm_actual = pm_filled_qty  # float — FAK可能部分成交
        ks_actual = float(ks_fill_count)
        hedged_qty = min(pm_actual, ks_actual)
        result["hedged_qty"] = hedged_qty
        if abs(pm_actual - ks_actual) < 0.01:
            result["success"] = True
        else:
            result["success"] = True
            result["size_mismatch"] = {"pm": pm_actual, "ks": ks_actual, "hedged": hedged_qty}
            # PM多出 → 卖回PM
            if pm_actual > ks_actual + 0.01:
                excess = pm_actual - ks_actual
                try:
                    __import__("time").sleep(2)
                    rem_e = float(excess)
                    ret_e = 0
                    while rem_e > 0.01 and ret_e < 5:
                        book = requests.get("https://clob.polymarket.com/book?token_id=" + tid, timeout=10).json()
                        bids = sorted(book.get("bids", []), key=lambda x: float(x["price"]), reverse=True)
                        if not bids:
                            break
                        sp2 = max(0.01, float(bids[0]["price"]))
                        bid_sz2 = float(bids[0]["size"])
                        sell_sz2 = min(rem_e, bid_sz2)
                        if sell_sz2 < 0.01:
                            break
                        sr2 = client.create_and_post_order(OrderArgsV2(
                            token_id=tid, price=round(sp2, 2), size=sell_sz2, side="SELL"),
                            order_type=OrderType.FAK)
                        fill2 = float(sr2.get("takingAmount", "0") or "0") if sr2 else 0
                        rem_e -= fill2
                        ret_e += 1
                        if fill2 <= 0:
                            __import__("time").sleep(1)
                    result["pm_close_excess"] = {"price": sp2, "size": float(excess) - rem_e, "remaining": round(rem_e, 4)}
                except Exception:
                    pass
            # KS多出 → 卖回KS（整数份）
            if ks_actual > pm_actual + 0.01:
                excess = int(ks_actual - pm_actual)
                try:
                    __import__("time").sleep(2)
                    close_quote2 = build_close_quote(ks_side, _found)
                    close_side2 = close_quote2["book_side"]
                    close_price2 = float(close_quote2["book_price"])
                    sell_ol2 = {"orders": [{"ticker": ks_ticker, "side": close_side2, "count": str(excess),
                        "price": "%.4f" % close_price2,
                        "time_in_force": "immediate_or_cancel",
                        "self_trade_prevention_type": "taker_at_cross",
                        "client_order_id": str(uuid.uuid4())}]}
                    sell_rj2 = _post_ks(sell_ol2, timeout=15)
                    sell_o2 = sell_rj2.get("orders", [{}])[0]
                    result["ks_close_excess"] = {"status": sell_o2.get("status", "?"), "fill_count": str(sell_o2.get("fill_count", "0")), "size": excess}
                except Exception:
                    pass
            # PM小数残余卖回
            pm_residual = pm_actual - int(pm_actual)
            if pm_residual > 0.01:
                try:
                    book_res = requests.get("https://clob.polymarket.com/book?token_id=" + tid, timeout=10).json()
                    bids_res = sorted(book_res.get("bids", []), key=lambda x: float(x["price"]), reverse=True)
                    if bids_res:
                        sp_res = max(0.01, float(bids_res[0]["price"]))
                        sr_res = client.create_and_post_order(OrderArgsV2(
                            token_id=tid, price=round(sp_res, 2), size=float(pm_residual), side="SELL"),
                            order_type=OrderType.FAK)
                        fill_res = float(sr_res.get("takingAmount", "0") or "0") if sr_res else 0
                        result["pm_close_residual"] = {"size": pm_residual, "filled": fill_res, "remaining": round(pm_residual - fill_res, 4)}
                except Exception:
                    pass

    return result
