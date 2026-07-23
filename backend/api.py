from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from app_paths import HISTORY_FILE, LOG_FILE, bundled_frontend_dir, ensure_data_dir
from credential_store import apply_credentials_to_environment, credential_status, import_transfer_bundle, load_credentials, save_credentials

ensure_data_dir()
apply_credentials_to_environment()
from fetch_current_polymarket import fetch_polymarket_data_struct
from fetch_current_kalshi import fetch_kalshi_data_struct
from get_current_markets import get_coin_market_urls

# Suppress py_clob_client_v2 connection error noise
import logging
logging.getLogger("py_clob_client_v2").setLevel(logging.CRITICAL)

# Also suppress print-based noise from py_clob_client_v2
import builtins
_orig_print = builtins.print
def _filtered_print(*args, **kw):
    if args and isinstance(args[0], str) and "py_clob_client_v2" in args[0]:
        return  # suppress
    _orig_print(*args, **kw)
builtins.print = _filtered_print

# ====== 日志重定向到本机应用数据目录 ======
import sys as _sys
_LOG_FILE = str(LOG_FILE)
_log_fh = open(_LOG_FILE, "a", buffering=1)
_old_stdout = _sys.stdout
_old_stderr = _sys.stderr
class _TeeLogger:
    def __init__(self):
        self.terminal_out = _old_stdout
        self.terminal_err = _old_stderr
    def write(self, text):
        _log_fh.write(text)
        if self.terminal_out is not None:
            try:
                self.terminal_out.write(text)
            except UnicodeEncodeError:
                encoding = getattr(self.terminal_out, "encoding", None) or "utf-8"
                self.terminal_out.write(text.encode(encoding, errors="replace").decode(encoding))
    def flush(self):
        _log_fh.flush()
        if self.terminal_out is not None:
            self.terminal_out.flush()
    def isatty(self): return self.terminal_out.isatty() if self.terminal_out is not None else False
_sys.stdout = _TeeLogger()
_sys.stderr = _TeeLogger()
print("[API] 日志已重定向到 %s" % _LOG_FILE)
# ===================================

from coin_config import get_supported_coins
from execute_arb import execute_arb, get_ks_ticker
import auto_trade
from update_manager import check_update, get_manifest_url, stage_update
from esports_arbitrage import AUTO as esports_auto, execute_opportunity as execute_esports_opportunity, scan as scan_esports
from pydantic import BaseModel
import datetime
import time, os, json, sys
import re
from typing import Any

# 设置管理
from settings_manager import load_config, save_config as sc

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class ExecuteRequest(BaseModel):
    coin: str
    poly_leg: str
    kalshi_leg: str = ""
    kalshi_strike: float
    target_usd: float = 10.0
    pm_slug: str = ""
    ks_ticker: str = ""
    shares: int | None = None

class SellRequest(BaseModel):
    coin: str
    platform: str              # "PM" or "KS"
    token_id: str = ""
    pm_price: float = 0
    amount: float = 0
    ks_ticker: str = ""
    ks_price: float = 0
    ks_side: str = "yes"


class SettingsRequest(BaseModel):
    poll_interval: float | None = None
    cooldown: int | None = None
    min_profit_cents: int | None = None
    price_min_cents: int | None = None
    price_max_cents: int | None = None
    min_shares: int | None = None
    order_shares: int | None = None
    min_total_balance: float | None = None
    target_usd: float | None = None
    start_delay_mins: int | None = None
    fail_cooldown_base: int | None = None
    fail_cooldown_max: int | None = None
    liquidity_buffer: float | None = None
    stop_on_unhedged: bool | None = None
    enabled_coins: list[str] | None = None
    max_trades_per_hour: int | None = None
    esports_min_profit_cents: int | None = None
    esports_fee_buffer_cents: int | None = None
    esports_order_shares: int | None = None
    esports_poll_interval: float | None = None
    update_manifest_url: str | None = None


class EsportsExecuteRequest(BaseModel):
    opportunity_id: str
    shares: int | None = None


class UpdateApplyRequest(BaseModel):
    update: dict[str, Any]


class CredentialsRequest(BaseModel):
    polymarket_private_key: str | None = None
    polymarket_funder: str | None = None
    polymarket_signature_type: str | None = None
    kalshi_api_key_id: str | None = None
    kalshi_private_key_pem: str | None = None


class CredentialImportRequest(BaseModel):
    bundle: str
    password: str


def _restart_worker():
    """后台重启 api.py 进程"""
    import time
    time.sleep(1.5)  # 等HTTP响应发送完成
    os.execl(sys.executable, sys.executable, *sys.argv)


@app.get("/arbitrage")
def get_arbitrage_data():
    response = {"timestamp": datetime.datetime.now().isoformat(), "coins": {}, "errors": []}
    coin_urls = get_coin_market_urls()
    enabled_coins = set(auto_trade.get_config().get("enabled_coins", get_supported_coins()))
    for symbol in get_supported_coins():
        if symbol not in enabled_coins:
            continue
        info = coin_urls.get(symbol)
        if not info:
            continue
        coin_result = {"polymarket": None, "kalshi": None, "checks": [], "opportunities": [], "errors": []}
        poly_data, poly_err = fetch_polymarket_data_struct(info["polymarket_slug"], info["binance_symbol"])
        kalshi_data, kalshi_err = fetch_kalshi_data_struct(info["kalshi_event_ticker"], info["binance_symbol"])
        if poly_err:
            coin_result["errors"].append("Polymarket: " + poly_err)
        if kalshi_err:
            coin_result["errors"].append("Kalshi: " + kalshi_err)
        coin_result["polymarket"] = poly_data
        coin_result["kalshi"] = kalshi_data
        if not poly_data or not kalshi_data:
            response["coins"][symbol] = coin_result
            continue
        poly_strike = poly_data["price_to_beat"]
        poly_up_cost = poly_data["prices"].get("Up", 0.0)
        poly_down_cost = poly_data["prices"].get("Down", 0.0)
        if poly_strike is None:
            coin_result["errors"].append("Polymarket Strike is None")
            response["coins"][symbol] = coin_result
            continue
        kalshi_markets = kalshi_data.get("markets", [])
        kalshi_markets.sort(key=lambda x: x["strike"])

        closest_idx = 0
        min_diff = float('inf')
        for i, m in enumerate(kalshi_markets):
            diff = abs(m['strike'] - poly_strike)
            if diff < min_diff:
                min_diff = diff
                closest_idx = i
        start_idx = max(0, closest_idx - 4)
        end_idx = min(len(kalshi_markets), closest_idx + 5)
        selected_markets = kalshi_markets[start_idx:end_idx]

        for km in selected_markets:
            ks = km["strike"]
            ky = km["yes_ask"]
            kn = km["no_ask"]

            if poly_strike > ks:
                chk = {"kalshi_strike": ks, "poly_strike": poly_strike,
                       "kalshi_yes": ky, "kalshi_no": kn,
                       "type": "Poly > Kalshi", "poly_leg": "Down", "kalshi_leg": "Yes",
                       "poly_cost": poly_down_cost, "kalshi_cost": ky,
                       "total_cost": poly_down_cost + ky,
                       "is_arbitrage": False, "margin": 0,
                       "pm_slug": info["polymarket_slug"], "ks_ticker": km.get("ticker", "")}
            elif poly_strike < ks:
                chk = {"kalshi_strike": ks, "poly_strike": poly_strike,
                       "kalshi_yes": ky, "kalshi_no": kn,
                       "type": "Poly < Kalshi", "poly_leg": "Up", "kalshi_leg": "No",
                       "poly_cost": poly_up_cost, "kalshi_cost": kn,
                       "total_cost": poly_up_cost + kn,
                       "is_arbitrage": False, "margin": 0,
                       "pm_slug": info["polymarket_slug"], "ks_ticker": km.get("ticker", "")}
            else:
                chk1 = {"kalshi_strike": ks, "poly_strike": poly_strike,
                        "kalshi_yes": ky, "kalshi_no": kn,
                        "type": "Equal", "poly_leg": "Down", "kalshi_leg": "Yes",
                        "poly_cost": poly_down_cost, "kalshi_cost": ky,
                        "total_cost": poly_down_cost + ky,
                        "is_arbitrage": False, "margin": 0,
                        "pm_slug": info["polymarket_slug"], "ks_ticker": km.get("ticker", "")}
                chk2 = {"kalshi_strike": ks, "poly_strike": poly_strike,
                        "kalshi_yes": ky, "kalshi_no": kn,
                        "type": "Equal", "poly_leg": "Up", "kalshi_leg": "No",
                        "poly_cost": poly_up_cost, "kalshi_cost": kn,
                        "total_cost": poly_up_cost + kn,
                        "is_arbitrage": False, "margin": 0,
                        "pm_slug": info["polymarket_slug"], "ks_ticker": km.get("ticker", "")}
                if chk1["total_cost"] < 1.00:
                    chk1["is_arbitrage"] = True
                    chk1["margin"] = 1.00 - chk1["total_cost"]
                    coin_result["opportunities"].append(chk1)
                coin_result["checks"].append(chk1)
                if chk2["total_cost"] < 1.00:
                    chk2["is_arbitrage"] = True
                    chk2["margin"] = 1.00 - chk2["total_cost"]
                    coin_result["opportunities"].append(chk2)
                coin_result["checks"].append(chk2)
                continue

            if chk["total_cost"] < 1.00:
                chk["is_arbitrage"] = True
                chk["margin"] = 1.00 - chk["total_cost"]
                coin_result["opportunities"].append(chk)
            coin_result["checks"].append(chk)

        response["coins"][symbol] = coin_result
    return response


@app.post("/execute")
def execute_trade(req: ExecuteRequest):
    try:
        if not req.ks_ticker:
            from get_current_markets import get_coin_market_urls
            urls = get_coin_market_urls()
            info = urls.get(req.coin, {})
            et = info.get("kalshi_event_ticker", "")
            if et:
                resolved = get_ks_ticker(et, req.kalshi_strike)
                if resolved:
                    req.ks_ticker = resolved
        configured_shares = int(load_config().get("order_shares", 5) or 5)
        requested_shares = max(int(req.shares or configured_shares), int(load_config().get("min_shares", 5) or 5))
        result = execute_arb(
            coin=req.coin,
            pm_direction=req.poly_leg,
            ks_ticker=req.ks_ticker,
            ks_side="no" if req.kalshi_leg.strip().lower() == "no" else "yes",
            target_usd=req.target_usd,
            ks_strike=req.kalshi_strike,
            fixed_shares=requested_shares,
            min_shares=requested_shares,
            liquidity_buffer=float(load_config().get("liquidity_buffer", 2.0)),
            min_profit_cents=float(load_config().get("min_profit_cents", 10)),
        )

        try:
            hist = json.load(HISTORY_FILE.open(encoding="utf-8")) if HISTORY_FILE.exists() else []
            hist.append({
                'time': datetime.datetime.now().isoformat(),
                'coin': req.coin,
                'poly_leg': req.poly_leg,
                'kalshi_leg': req.kalshi_leg,
                'kalshi_strike': req.kalshi_strike,
                'total_cost_cents': result.get('total_cost_cents', 0),
                'profit_cents': result.get('profit_cents', 0),
                'success': result.get('success', False),
                'error': result.get('error', ''),
                'pm_filled_qty': result.get('pm', {}).get('filled_qty', 0),
                'ks_fill_count': result.get('ks', {}).get('fill_count', 0),
                'hedged_qty': result.get('hedged_qty', 0),
                'pm_price': result.get('pm_plan', {}).get('price', 0),
                'ks_price': result.get('ks_plan', {}).get('price', 0),
                'token_id': result.get('token_id', ''),
                'size_warning': result.get('size_warning', ''),
                'ks_ticker': result.get('ks_ticker', req.ks_ticker),
                'ks_side': req.kalshi_leg.strip().lower(),
            })
            with HISTORY_FILE.open('w', encoding="utf-8") as fh:
                json.dump(hist[-500:], fh, ensure_ascii=False)
        except Exception:
            pass
        return result
    except Exception as e:
        return {"success": False, "error": str(e)[:500]}


@app.get("/esports/arbitrage")
def get_esports_arbitrage():
    try:
        cfg = load_config()
        return scan_esports(
            min_profit_cents=float(cfg.get("esports_min_profit_cents", 10)),
            fee_buffer_cents=float(cfg.get("esports_fee_buffer_cents", 2)),
        )
    except Exception as e:
        return {"time": datetime.datetime.now().isoformat(), "matched_markets": 0,
                "opportunities": [], "total": 0, "error": str(e)[:300]}


@app.post("/esports/execute")
def execute_esports_trade(req: EsportsExecuteRequest):
    try:
        cfg = load_config()
        scan_result = scan_esports(
            min_profit_cents=float(cfg.get("esports_min_profit_cents", 10)),
            fee_buffer_cents=float(cfg.get("esports_fee_buffer_cents", 2)),
        )
        selected = next((item for item in scan_result.get("opportunities", [])
                         if item.get("id") == req.opportunity_id), None)
        if not selected:
            return {"success": False, "error": "机会已消失或实时利润低于阈值，未下单"}
        shares = max(1, int(req.shares or cfg.get("esports_order_shares", 5)))
        result = execute_esports_opportunity(
            selected, shares=shares,
            min_profit_cents=float(cfg.get("esports_min_profit_cents", 10)),
            fee_buffer_cents=float(cfg.get("esports_fee_buffer_cents", 2)),
            liquidity_buffer=float(cfg.get("liquidity_buffer", 2.0)),
        )
        try:
            hist = json.load(HISTORY_FILE.open(encoding="utf-8")) if HISTORY_FILE.exists() else []
            hist.append({
                "time": datetime.datetime.now().isoformat(), "coin": "ESPORTS",
                "title": selected.get("title", ""), "poly_leg": selected.get("pm_team", ""),
                "kalshi_leg": selected.get("ks_team", ""), "success": result.get("success", False),
                "error": result.get("error", ""), "total_cost_cents": selected.get("total_cost", 0) * 100,
                "profit_cents": selected.get("estimated_profit_cents", 0),
                "pm_filled_qty": result.get("pm", {}).get("filled_qty", 0),
                "ks_fill_count": result.get("ks", {}).get("fill_count", 0),
                "hedged_qty": result.get("hedged_qty", 0), "token_id": selected.get("pm_token_id", ""),
                "ks_ticker": selected.get("ks_ticker", ""), "ks_side": selected.get("ks_side", "yes"),
                "pm_price": result.get("pm_plan", {}).get("price", selected.get("pm_price", 0)),
                "ks_price": result.get("ks_plan", {}).get("price", selected.get("ks_price", 0)),
            })
            with HISTORY_FILE.open("w", encoding="utf-8") as fh:
                json.dump(hist[-500:], fh, ensure_ascii=False)
        except Exception:
            pass
        return result
    except Exception as e:
        return {"success": False, "error": str(e)[:500]}


@app.get("/esports/auto")
def esports_auto_status():
    return esports_auto.status()


@app.post("/esports/auto/start")
def esports_auto_start():
    esports_auto.start()
    return esports_auto.status()


@app.post("/esports/auto/stop")
def esports_auto_stop():
    esports_auto.stop()
    return esports_auto.status()


@app.post("/sell")
def sell_position(req: SellRequest):
    result = {"success": False, "coin": req.coin, "platform": req.platform}
    try:
        if req.platform == "PM":
            from py_clob_client_v2 import ClobClient
            from py_clob_client_v2.clob_types import MarketOrderArgsV2, OrderType, BalanceAllowanceParams
            key = os.environ.get("POLYMARKET_PRIVATE_KEY") or os.environ.get("PRIVATE_KEY")
            funder = os.environ.get("POLYMARKET_FUNDER")
            sig_type = int(os.environ.get("POLYMARKET_SIGNATURE_TYPE", "0"))
            bc = ClobClient("https://clob.polymarket.com", key=key, chain_id=137, signature_type=sig_type, funder=funder)
            creds = bc.derive_api_key()
            bc.set_api_creds(creds)
            import requests
            book = requests.get("https://clob.polymarket.com/book?token_id=" + req.token_id, timeout=10).json()
            bids_by_price = {}
            for b in book.get("bids", []):
                bp = float(b["price"])
                bs = float(b["size"])
                bids_by_price[bp] = bids_by_price.get(bp, 0) + bs
            sell_price = 0.01
            remaining = float(req.amount)
            filled = 0.0
            total_price = 0.0
            if bids_by_price:
                sp = max(0.01, float(req.pm_price))
                for tick in range(200):
                    trial = round(sp - tick * 0.01, 2)
                    if trial < 0.01:
                        break
                    if trial in bids_by_price and bids_by_price[trial] >= 0.01:
                        sell_price = trial
                        break
            if remaining > 0.01 and sell_price >= 0.01:
                try:
                    pmr = bc.create_and_post_market_order(MarketOrderArgsV2(
                        token_id=req.token_id, price=sell_price, amount=round(min(remaining, bids_by_price.get(sell_price, 999)), 2), side="SELL"),
                        order_type=OrderType.FAK)
                    if isinstance(pmr, dict):
                        sz = float(pmr.get("size", pmr.get("amount", pmr.get("filled", 0))))
                        filled += sz
                        total_price += sz * sell_price
                except Exception as e:
                    result["sell_error"] = str(e)[:200]
            result["success"] = filled > 0.001
            result["filled"] = round(filled, 2)
            result["price"] = sell_price
            result["total"] = round(total_price, 2)
            result["error"] = "" if filled > 0.001 else "PM卖回未成交"

        elif req.platform == "KS":
            from execute_arb import KB
            from kalshi_auth import fetch_with_auth, get_api_key_id, get_private_key
            from kalshi_order_mapping import build_close_quote
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding as pad
            import uuid, base64, urllib.request
            fp = "/portfolio/events/orders/batched"
            full_sig_path = "/trade-api/v2" + fp
            ks_ticker = req.ks_ticker
            ks_amount = int(float(req.amount))
            if ks_amount < 1:
                result["error"] = "KS份数必须>=1"
                return result
            ks_side = req.ks_side.strip().lower()
            if ks_side not in ("yes", "no"):
                result["error"] = "KS持仓方向必须是yes或no"
                return result
            kalshi_key = get_private_key()
            market_payload = fetch_with_auth(kalshi_key, "/markets/" + ks_ticker)
            market = market_payload.get("market", market_payload)
            close_quote = build_close_quote(ks_side, market)
            ks_sell_fill = 0
            ks_sell_side = close_quote["book_side"]
            ks_sell_price = float(close_quote["book_price"])
            if ks_sell_price <= 0:
                result["error"] = "KS当前没有可用平仓报价"
                return result
            ts = str(int(time.time() * 1000))
            msg = (ts + "POST" + full_sig_path).encode()
            sig = kalshi_key.sign(msg, pad.PSS(mgf=pad.MGF1(hashes.SHA256()), salt_length=pad.PSS.MAX_LENGTH), hashes.SHA256())
            sb64 = base64.b64encode(sig).decode()
            ks_headers = {"Content-Type": "application/json", "KALSHI-ACCESS-KEY": get_api_key_id(), "KALSHI-ACCESS-SIGNATURE": sb64, "KALSHI-ACCESS-TIMESTAMP": ts}
            sell_ol = {"orders": [{"ticker": ks_ticker, "side": ks_sell_side, "count": str(ks_amount), "price": "%.4f" % ks_sell_price, "time_in_force": "immediate_or_cancel", "self_trade_prevention_type": "taker_at_cross", "client_order_id": str(uuid.uuid4())}]}
            sell_body = json.dumps(sell_ol)
            sell_req = urllib.request.Request(KB + fp, data=sell_body.encode(), headers=ks_headers)
            sell_rj = json.loads(urllib.request.urlopen(sell_req, timeout=15).read())
            sell_o = sell_rj.get("orders", [{}])[0]
            try: ks_sell_fill = int(float(sell_o.get("fill_count", "0")))
            except: ks_sell_fill = 0
            if ks_sell_fill == 0:
                __import__("time").sleep(0.5)
                ts2 = str(int(time.time() * 1000))
                msg2 = (ts2 + "POST" + full_sig_path).encode()
                sig2 = kalshi_key.sign(msg2, pad.PSS(mgf=pad.MGF1(hashes.SHA256()), salt_length=pad.PSS.MAX_LENGTH), hashes.SHA256())
                sb64_2 = base64.b64encode(sig2).decode()
                retry_ol = {"orders": [{"ticker": ks_ticker, "side": ks_sell_side, "count": str(ks_amount), "price": "%.4f" % ks_sell_price, "time_in_force": "immediate_or_cancel", "self_trade_prevention_type": "taker_at_cross", "client_order_id": str(uuid.uuid4())}]}
                retry_headers = {"Content-Type": "application/json", "KALSHI-ACCESS-KEY": get_api_key_id(), "KALSHI-ACCESS-SIGNATURE": sb64_2, "KALSHI-ACCESS-TIMESTAMP": ts2}
                retry_req = urllib.request.Request(KB + fp, data=json.dumps(retry_ol).encode(), headers=retry_headers)
                retry_rj = json.loads(urllib.request.urlopen(retry_req, timeout=15).read())
                retry_o = retry_rj.get("orders", [{}])[0]
                try: ks_sell_fill = int(float(retry_o.get("fill_count", "0")))
                except: ks_sell_fill = 0
            result["success"] = ks_sell_fill > 0
            result["filled"] = ks_sell_fill
            result["side"] = ks_side
            result["book_side"] = ks_sell_side
            result["price"] = ks_sell_price
            result["total"] = round(ks_sell_fill * ks_sell_price, 4)
            result["error"] = "" if ks_sell_fill > 0 else "KS卖回未成交"
        else:
            result["error"] = "platform must be PM or KS"
    except Exception as e:
        result["error"] = "卖回异常: " + str(e)[:300]
        result["success"] = False
    if result.get("success"):
        _mark_position_closed(req, float(result.get("filled", 0) or 0))
    return result


def _mark_position_closed(req: SellRequest, filled: float) -> None:
    try:
        hist = json.load(HISTORY_FILE.open(encoding="utf-8")) if HISTORY_FILE.exists() else []
        remaining = max(filled, 0.0)
        for item in reversed(hist):
            if not item.get("success") or remaining <= 0:
                continue
            if req.platform == "PM":
                matches, field = bool(req.token_id and item.get("token_id") == req.token_id), "pm_closed_qty"
            else:
                matches, field = bool(req.ks_ticker and item.get("ks_ticker") == req.ks_ticker), "ks_closed_qty"
            if not matches:
                continue
            qty = float(item.get("hedged_qty") or item.get("pm_filled_qty") or item.get("ks_fill_count") or 0)
            closed = float(item.get(field, 0) or 0)
            delta = min(max(qty - closed, 0.0), remaining)
            item[field] = round(closed + delta, 4)
            remaining -= delta
        with HISTORY_FILE.open("w", encoding="utf-8") as fh:
            json.dump(hist[-500:], fh, ensure_ascii=False)
    except Exception:
        pass


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.datetime.now().isoformat()}


@app.get("/update/check")
def update_check():
    try:
        cfg = load_config()
        return check_update(get_manifest_url(cfg))
    except Exception as exc:
        return {"configured": True, "current_version": "1.3.0", "available": False,
                "error": "检查更新失败: " + str(exc)[:200]}


@app.post("/update/apply")
def update_apply(data: UpdateApplyRequest):
    try:
        return stage_update(data.update, os.getpid())
    except Exception as exc:
        return {"staged": False, "error": "下载更新失败: " + str(exc)[:200]}


@app.get("/auto")
def auto_status():
    return auto_trade.get_status()


@app.post("/auto/start")
def auto_start():
    auto_trade.start()
    return {"enabled": True}


@app.post("/auto/stop")
def auto_stop():
    auto_trade.stop()
    return {"enabled": False}


@app.get("/api/status")
def api_status():
    import auto_trade
    from fetch_current_polymarket import fetch_polymarket_data_struct as fpm
    from fetch_current_kalshi import fetch_kalshi_data_struct as fks
    from get_current_markets import get_coin_market_urls
    from coin_config import get_supported_coins
    urls = get_coin_market_urls()
    coins = get_supported_coins()

    poly_result = {}
    kalshi_result = {}
    best_profit = 0
    best_desc = "无套利机会"
    signal_action = "none"
    signal_reason = "无套利机会"

    for sym in coins:
        info = urls.get(sym)
        if not info:
            continue
        p, _ = fpm(info["polymarket_slug"], info["binance_symbol"])
        k, _ = fks(info["kalshi_event_ticker"], info["binance_symbol"])
        if p:
            poly_up = p["prices"].get("Up", 0) * 100
            poly_dn = p["prices"].get("Down", 0) * 100
            poly_result[sym] = {
                "upCents": round(poly_up),
                "downCents": round(poly_dn),
                "hasLiquidity": p.get("hasLiquidity", False) == True,
                "fetchedAt": int(datetime.datetime.now().timestamp() * 1000),
            }
            if k:
                for km in k.get("markets", []):
                    ky = km["yes_ask"] * 100
                    kn = km["no_ask"] * 100
                    if p["price_to_beat"] and p["price_to_beat"] > km["strike"]:
                        tc = poly_dn + ky
                    elif p["price_to_beat"] and p["price_to_beat"] < km["strike"]:
                        tc = poly_up + kn
                    else:
                        tc = min(poly_dn + ky, poly_up + kn)
                    profit = 100 - tc
                    if tc < 100 and profit > best_profit:
                        best_profit = profit
                        best_desc = "%s 套利利润 %.1f gap=%.0f" % (sym, profit, abs(p["price_to_beat"] - km["strike"]))
                        if profit >= 10:
                            signal_action = "arb_up" if p["price_to_beat"] < km["strike"] else "arb_down"
            if k:
                _clst = min(k["markets"], key=lambda m: abs(m["strike"] - (p.get("price_to_beat", 0) or 0))) if k["markets"] else None
                kalshi_result[sym] = {
                    "yesCents": round(_clst["yes_ask"] * 100) if _clst else None,
                    "noCents": round(_clst["no_ask"] * 100) if _clst else None,
                    "status": k.get("status", "active"),
                    "isFinished": k.get("isFinished", False),
                    "fetchedAt": int(datetime.datetime.now().timestamp() * 1000),
                }
    ats = auto_trade.get_status()
    return {
        "tradingEnabled": ats["enabled"],
        "polyTradingEnabled": True,
        "kalshiTradingEnabled": True,
        "afterStartWindow": True,
        "lastTickAt": datetime.datetime.now().isoformat(),
        "polymarket": poly_result.get("BTC"),
        "kalshi": kalshi_result.get("BTC"),
        "signal": {
            "action": signal_action,
            "reason": signal_reason,
        } if signal_action != "none" else {"action": "none", "reason": signal_reason},
        "best_profit_cents": round(best_profit, 1),
        "best_profit_desc": best_desc,
        "auto_config": ats.get("config", {}),
        "cooldown_remaining": ats.get("cooldown_remaining", 0),
        "trade_count": ats.get("trade_count", 0),
    }


@app.get("/pm_positions")
def get_pm_positions():
    """返回auto_trade记录的残留PM持仓"""
    try:
        from auto_trade import _residual_positions
    except:
        return {"positions": [], "total": 0}
    result = []
    now = time.time()
    for coin, info in dict(_residual_positions).items():
        age = now - info.get("time", 0)
        if age < 7200:
            result.append({
                "coin": coin,
                "poly_leg": info.get("poly_leg", ""),
                "qty": info.get("qty", 0),
                "token_id": info.get("token_id", ""),
                "elapsed_sec": int(age),
                "expire_in_sec": max(0, 7200 - int(age)),
            })
    return {"positions": result, "total": len(result)}

@app.get("/positions")
def get_positions():
    try:
        hist = json.load(HISTORY_FILE.open(encoding="utf-8"))
    except:
        hist = []
    cutoff = time.time() - 24 * 3600
    def parse_ts(ts):
        try: return datetime.datetime.fromisoformat(ts).timestamp()
        except: return 0
    positions = []
    for t in hist:
        if not t.get("success"):
            continue
        ts = parse_ts(t.get("time", ""))
        if ts <= cutoff:
            continue
        qty = float(t.get("hedged_qty") or t.get("pm_filled_qty") or t.get("ks_fill_count") or 0)
        item = dict(t)
        item["pm_remaining"] = round(max(0.0, qty - float(item.get("pm_closed_qty", 0) or 0)), 4)
        item["ks_remaining"] = round(max(0.0, qty - float(item.get("ks_closed_qty", 0) or 0)), 4)
        if item["pm_remaining"] > 0.01 or item["ks_remaining"] > 0.01:
            positions.append(item)
    return {"positions": positions, "total": len(positions)}


@app.get("/history")
def get_history(hours: int = 1):
    try:
        hist = json.load(HISTORY_FILE.open(encoding="utf-8"))
    except:
        hist = []
    cutoff = time.time() - hours * 3600
    def parse_ts(ts):
        try: return datetime.datetime.fromisoformat(ts).timestamp()
        except: return 0
    recent = [t for t in hist if parse_ts(t.get("time", "")) > cutoff]
    return {"total": len(hist), "in_range": len(recent), "hours": hours, "trades": recent}


@app.get("/balance")
def get_balance():
    result = {"pm": None, "ks": None}
    try:
        from py_clob_client_v2 import ClobClient
        from py_clob_client_v2.clob_types import BalanceAllowanceParams
        key = os.environ.get("POLYMARKET_PRIVATE_KEY") or os.environ.get("PRIVATE_KEY")
        funder = os.environ.get("POLYMARKET_FUNDER")
        sig_type = int(os.environ.get("POLYMARKET_SIGNATURE_TYPE", "0"))
        bc = ClobClient("https://clob.polymarket.com", key=key, chain_id=137,
                         signature_type=sig_type, funder=funder)
        creds = bc.derive_api_key()
        bc.set_api_creds(creds)
        result["pm"] = float(bc.get_balance_allowance(BalanceAllowanceParams(asset_type="COLLATERAL")).get("balance", 0))
    except Exception as e:
        result["pm_error"] = str(e)[:100]
    try:
        from kalshi_auth import fetch_with_auth, get_private_key
        ks_bal = float(fetch_with_auth(get_private_key(), "/portfolio/balance").get("balance_dollars", 0))
        result["ks"] = ks_bal
    except Exception as e:
        result["ks_error"] = str(e)[:100]
    return result


# ======== 凭据接口 ========
@app.get("/api/credentials")
@app.get("/credentials")
def get_credentials_status():
    return credential_status()


@app.post("/api/credentials")
@app.post("/credentials")
def update_credentials(data: CredentialsRequest):
    updates = {k: v for k, v in data.model_dump(exclude_none=True).items() if str(v).strip()}
    if not updates:
        return {"saved": False, "error": "没有输入新的凭据"}
    pm_key = str(updates.get("polymarket_private_key", "")).removeprefix("0x")
    if pm_key and not re.fullmatch(r"[0-9a-fA-F]{64}", pm_key):
        return {"saved": False, "error": "Polymarket私钥必须是64位十六进制"}
    funder = str(updates.get("polymarket_funder", ""))
    if funder and not re.fullmatch(r"0x[0-9a-fA-F]{40}", funder):
        return {"saved": False, "error": "Funder地址格式不正确"}
    signature_type = str(updates.get("polymarket_signature_type", ""))
    if signature_type and signature_type not in {"0", "1", "2", "3"}:
        return {"saved": False, "error": "签名类型只能是0、1、2或3"}
    pem = str(updates.get("kalshi_private_key_pem", ""))
    if pem and ("-----BEGIN" not in pem or "PRIVATE KEY-----" not in pem):
        return {"saved": False, "error": "Kalshi私钥必须是PEM格式"}
    try:
        credentials = save_credentials(updates)
        return {"saved": True, "status": credential_status(), "configured_fields": sorted(credentials.keys())}
    except Exception as exc:
        return {"saved": False, "error": str(exc)[:200]}


@app.post("/api/credentials/import")
@app.post("/credentials/import")
def import_credentials(data: CredentialImportRequest):
    try:
        credentials = import_transfer_bundle(data.bundle, data.password)
        return {"imported": True, "status": credential_status(),
                "configured_fields": sorted(credentials.keys())}
    except Exception as exc:
        return {"imported": False, "error": str(exc)[:200]}


@app.post("/api/credentials/test")
@app.post("/credentials/test")
def test_credentials():
    result = {"polymarket": {"ok": False}, "kalshi": {"ok": False}}
    try:
        from py_clob_client_v2 import ClobClient
        from py_clob_client_v2.clob_types import BalanceAllowanceParams
        key = os.environ.get("POLYMARKET_PRIVATE_KEY", "")
        funder = os.environ.get("POLYMARKET_FUNDER", "")
        sig_type = int(os.environ.get("POLYMARKET_SIGNATURE_TYPE", "0"))
        bc = ClobClient("https://clob.polymarket.com", key=key, chain_id=137, signature_type=sig_type, funder=funder)
        bc.set_api_creds(bc.derive_api_key())
        balance = bc.get_balance_allowance(BalanceAllowanceParams(asset_type="COLLATERAL"))
        result["polymarket"] = {"ok": True, "balance": round(float(balance.get("balance", 0)) / 1_000_000, 4)}
    except Exception as exc:
        result["polymarket"]["error"] = str(exc)[:180]
    try:
        from kalshi_auth import fetch_with_auth, get_private_key
        balance = fetch_with_auth(get_private_key(), "/portfolio/balance")
        result["kalshi"] = {"ok": True, "balance": round(float(balance.get("balance_dollars", 0)), 4)}
    except Exception as exc:
        result["kalshi"]["error"] = str(exc)[:180]
    result["ok"] = result["polymarket"]["ok"] and result["kalshi"]["ok"]
    return result


# ======== 设置接口 ========
@app.get("/settings")
def get_settings():
    """返回当前所有配置"""
    return load_config()


@app.post("/settings")
def save_settings(data: SettingsRequest):
    """保存配置并热加载自动交易参数，不重启桌面窗口"""
    updates = {k: v for k, v in data.model_dump(exclude_none=True).items()}
    ok = sc(updates)
    if ok:
        auto_trade.reload_config()
        return {"saved": True, "restarting": False, "settings": load_config()}
    return {"saved": False, "error": "保存失败"}



# ==== 日志接口 ====
LOG_FILE = str(LOG_FILE)

@app.get("/api/log")
@app.get("/log")
def get_log(lines: int = 80):
    """返回最近的日志行"""
    try:
        with open(LOG_FILE) as f:
            content = f.read()
            all_lines = [l for l in content.splitlines() if "HTTP/1.1" not in l]
            tail = all_lines[-lines:]
            return {"lines": tail, "total": len(all_lines), "showing": len(tail)}
    except Exception as e:
        return {"lines": ["[日志读取失败] " + str(e)[:100]], "total": 0, "showing": 0}


_FRONTEND_DIR = bundled_frontend_dir()
if _FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765, access_log=False)
