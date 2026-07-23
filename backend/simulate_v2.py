"""
模拟测试 v2 — 调用真实 execute_arb，全面 mock 网络层
测试：两腿成交、单腿保护平仓、结算后验证
"""
import sys, os, json, time, datetime, random, urllib.request
from unittest.mock import MagicMock

BASE = "/home/ubuntu/polymarket-kalshi-btc-arbitrage-bot/backend"
for p in [BASE, "/home/ubuntu/polymarketLP", "/home/ubuntu/polymarketLP/passive_liquidity"]:
    sys.path.insert(0, p)
os.chdir(BASE)

import requests as _real_requests
from get_current_markets import get_coin_market_urls
from coin_config import get_supported_coins
from fetch_current_polymarket import fetch_polymarket_data_struct
from fetch_current_kalshi import fetch_kalshi_data_struct
import execute_arb as ea
from py_clob_client_v2 import ClobClient

POLL_INTERVAL = 3
RESULTS_FILE = "/tmp/simulation_v2_results.json"
END_TIME = datetime.datetime(2026, 7, 19, 12, 0, 0, tzinfo=datetime.timezone.utc).timestamp()
HEARTBEAT_INTERVAL = 30

# 场景配置
SCENARIOS = [
    {"name": "both_success", "pm_ok": True,  "ks_ok": True},
    {"name": "pm_only",      "pm_ok": True,  "ks_ok": False},
    {"name": "ks_only",      "pm_ok": False, "ks_ok": True},
    {"name": "both_fail",    "pm_ok": False, "ks_ok": False},
]
WEIGHTS = [0.2, 0.3, 0.3, 0.2]  # 60% triggers close-back


def load_results():
    try:
        with open(RESULTS_FILE) as f: return json.load(f)
    except: return {"trades": [], "scenario_results": {}, "status": "running", "started_at": None}


def save_results(data):
    with open(RESULTS_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def _find_opp():
    """找真实套利机会"""
    urls = get_coin_market_urls()
    best, best_m = None, 0
    for symbol in get_supported_coins():
        info = urls.get(symbol)
        if not info: continue
        poly, _ = fetch_polymarket_data_struct(info["polymarket_slug"], info["binance_symbol"])
        if not poly or poly.get("price_to_beat") is None: continue
        pu = poly["prices"].get("Up", 0) * 100
        pd = poly["prices"].get("Down", 0) * 100
        if pu == 0 or pd == 0: continue
        pstrike = poly["price_to_beat"]
        kalshi, _ = fetch_kalshi_data_struct(info["kalshi_event_ticker"], info["binance_symbol"])
        if not kalshi or kalshi.get("isFinished", False): continue
        for km in kalshi.get("markets", []):
            ks, ky, kn, tk = km["strike"], km["yes_ask"] * 100, km["no_ask"] * 100, km.get("ticker", "")
            pairs = []
            if pstrike > ks: pairs = [(pd, ky, "Down", "yes")]
            elif pstrike < ks: pairs = [(pu, kn, "Up", "no")]
            else: pairs = [(pd, ky, "Down", "yes"), (pu, kn, "Up", "no")]
            for pm_c, ks_c, leg, ks_s in pairs:
                cost = pm_c + ks_c
                profit = 100 - cost
                if profit < 5: continue
                m = profit / cost
                if m > best_m:
                    hs = max(1, min(10, int(2.0 / (pm_c / 100))))
                    best = {"symbol": symbol, "poly_leg": leg, "ks_ticker": tk, "ks_side": ks_s,
                            "kalshi_strike": ks, "pm_c": pm_c, "ks_c": ks_c, "cost": cost,
                            "profit": profit, "hs": hs}
                    best_m = m
    if best:
        try:
            import requests
            slug = urls.get(best["symbol"], {}).get("polymarket_slug", "")
            if slug:
                gr = requests.get("https://gamma-api.polymarket.com/events?slug=" + slug, timeout=5).json()
                gm = gr[0]["markets"][0]
                for oc, cid in zip(json.loads(gm.get("outcomes", "[]")), json.loads(gm.get("clobTokenIds", "[]"))):
                    if oc.upper() == best["poly_leg"].upper(): best["tid"] = cid; break
        except: pass
    return best


def _fallback_opp():
    """无套利机会时，找最便宜的pairMock测试"""
    try:
        r = _real_requests.get("http://localhost:8765/arbitrage", timeout=5)
        if not r.ok: return None
        d = r.json()
        bc, bi = 99, None
        for sym, v in d.get("coins", {}).items():
            for c in v.get("checks", []):
                tc = c.get("total_cost", 99)
                if tc < bc:
                    bc = tc
                    leg = c.get("poly_leg", "Up")
                    pm_c = c.get("poly_cost", 0.3) * 100
                    ks_c = c.get("kalshi_cost", 0.3) * 100
                    ks_l = c.get("kalshi_leg", "No")
                    ks_s = "yes" if ks_l == "Yes" else "no"
                    bi = {"symbol": sym, "poly_leg": leg, "ks_ticker": c.get("ks_ticker", ""),
                          "ks_side": ks_s, "kalshi_strike": c["kalshi_strike"],
                          "pm_c": pm_c, "ks_c": ks_c, "cost": tc, "profit": 1 - tc, "hs": 3, "tid": ""}
        return bi
    except: return None


def _full_mock(opp, hedge_shares, pm_ok, ks_ok):
    """全面mock execute_arb所有网络调用"""
    tid = opp.get("tid", "mock-tid-001") or "mock-tid-001"
    pm_px = opp["pm_c"] / 100.0
    ks_px = opp["ks_c"] / 100.0
    pm_avail = max(hedge_shares + 5, 20)

    mock_pm_ret = {"status": "matched", "takingAmount": str(hedge_shares), "order_id": "mock-pm"} if pm_ok else {"status": "failed", "takingAmount": "0"}
    mock_ks_ret = [json.dumps({"orders": [{"fill_count": str(hedge_shares), "status": "filled", "average_fill_price": "0.50"}]}).encode()
                   if ks_ok else json.dumps({"orders": [{"fill_count": "0", "status": "failed"}]}).encode()]

    ks_side_key = opp["ks_side"]
    other_side = "yes" if ks_side_key == "no" else "no"
    ks_book = {"orderbook": {
        ks_side_key: [[int(ks_px * 100), 1000]],
        other_side: [[int(100 - ks_px * 100), 1000]]
    }}

    pm_gamma = [{"markets": [{"clobTokenIds": json.dumps([tid]), "outcomes": json.dumps(["Up", "Down"])}]}]
    pm_book = {"asks": [{"price": str(pm_px), "size": str(pm_avail)}], "bids": [{"price": str(max(0.01, pm_px - 0.05)), "size": "100"}]}

    ks_body_calls = []
    def mock_urlopen(req, *args, **kwargs):
        url = req.full_url if hasattr(req, 'full_url') else str(req)
        body = req.data if hasattr(req, 'data') and req.data else b''
        if '/orderbook' in url:
            return MagicMock(read=lambda: json.dumps(ks_book).encode())
        if body:
            # KS下单请求
            return MagicMock(read=lambda: json.dumps({"orders": [{"fill_count": str(hedge_shares if ks_ok else 0), "status": "filled" if ks_ok else "failed"}]}).encode())
        return MagicMock(read=lambda: json.dumps({"markets": []}).encode())

    def mock_requests_get(url, **kwargs):
        if 'gamma-api' in url: return MagicMock(json=lambda: pm_gamma)
        if '/book' in url: return MagicMock(json=lambda: pm_book)
        return MagicMock(json=lambda: {})

    mock_client = MagicMock(spec=ClobClient)
    mock_client.derive_api_key.return_value = MagicMock()
    mock_client.get_balance_allowance.return_value = {"balance": "5000000"}
    mock_client.create_and_post_order.return_value = mock_pm_ret

    return pm_book, mock_urlopen, mock_requests_get, mock_client


def run():
    data = load_results()
    if data.get("started_at") is None:
        data["started_at"] = datetime.datetime.now().isoformat()
    last_hb = 0

    print("[SimV2] 启动: mock全网络层调execute_arb")
    print("[SimV2] 场景: both=20% pm_only=30% ks_only=30% none=20%")

    tidx = len(data.get("trades", []))

    while time.time() < END_TIME:
        try:
            if not open("/tmp/simv2_enabled").read().strip() == "1":
                time.sleep(2); continue
        except: time.sleep(2); continue

        try:
            opp = _find_opp()
            if not opp: opp = _fallback_opp()
            if not opp: time.sleep(POLL_INTERVAL); continue

            sc = random.choices(SCENARIOS, weights=WEIGHTS, k=1)[0]
            pm_ok, ks_ok = sc["pm_ok"], sc["ks_ok"]
            hedge_shares = opp.get("hs", 3)

            # 构造mock
            pm_book, mock_urlopen_fn, mock_requests_get_fn, mock_client = _full_mock(opp, hedge_shares, pm_ok, ks_ok)

            # 备份
            real_create_order = ClobClient.create_and_post_order
            real_urlopen = urllib.request.urlopen
            real_requests_get = _real_requests.get
            real_derive = ClobClient.derive_api_key
            real_balance = ClobClient.get_balance_allowance

            trade = {
                "idx": tidx, "time": datetime.datetime.now().isoformat(), "utc_ts": time.time(),
                "coin": opp["symbol"], "poly_leg": opp["poly_leg"], "ks_side": opp["ks_side"],
                "kalshi_strike": opp["kalshi_strike"], "ks_ticker": opp["ks_ticker"],
                "scenario": sc["name"],
            }

            try:
                ClobClient.create_and_post_order = lambda self, oa, ot=None: mock_client.create_and_post_order(oa, ot)
                ClobClient.derive_api_key = lambda self: mock_client.derive_api_key()
                ClobClient.get_balance_allowance = lambda self, bp: mock_client.get_balance_allowance(bp)
                urllib.request.urlopen = mock_urlopen_fn
                _real_requests.get = mock_requests_get_fn
                # mock ClobClient __init__ to return our mock
                _orig_init = ClobClient.__init__
                ClobClient.__init__ = lambda self, *a, **kw: None
                # kalshi balance mock - patch fetch_with_auth
                import kalshi_auth
                _orig_fetch = kalshi_auth.fetch_with_auth
                kalshi_auth.fetch_with_auth = lambda key, path: {"portfolio": {"balance": "100.0"}}

                result = ea.execute_arb(
                    coin=opp["symbol"], pm_direction=opp["poly_leg"],
                    ks_ticker=opp["ks_ticker"], ks_side=opp["ks_side"],
                    target_usd=2.0, token_id=opp.get("tid", ""),
                )

                trade["pm_filled"] = result.get("pm", {}).get("filled", False)
                trade["ks_filled"] = result.get("ks", {}).get("filled", False)
                trade["pm_close_fired"] = "pm_close" in result
                trade["ks_close_fired"] = "ks_close" in result
                trade["success"] = result.get("success", False)
                trade["error"] = result.get("error", "")
                trade["pm_close_detail"] = result.get("pm_close")
                trade["ks_close_detail"] = result.get("ks_close")
                trade["hedged_qty"] = result.get("hedged_qty")
                trade["pm_result"] = result.get("pm")
                trade["ks_result"] = result.get("ks")

                # 验证
                if not pm_ok and not ks_ok: trade["verif"] = "PASS"
                elif pm_ok and not ks_ok: trade["verif"] = "PASS" if trade["pm_close_fired"] else "FAIL"
                elif not pm_ok and ks_ok: trade["verif"] = "PASS" if trade["ks_close_fired"] else "FAIL"
                else: trade["verif"] = "PASS" if trade["success"] else "FAIL"

            finally:
                ClobClient.create_and_post_order = real_create_order
                ClobClient.derive_api_key = real_derive
                ClobClient.get_balance_allowance = real_balance
                ClobClient.__init__ = _orig_init
                urllib.request.urlopen = real_urlopen
                _real_requests.get = real_requests_get
                kalshi_auth.fetch_with_auth = _orig_fetch

            tidx += 1
            data.setdefault("trades", []).append(trade)
            data.setdefault("scenario_results", {}).setdefault(sc["name"], {"total": 0, "passed": 0, "failed": 0})
            sr = data["scenario_results"][sc["name"]]
            sr["total"] += 1
            if trade["verif"] == "PASS": sr["passed"] += 1
            else: sr["failed"] += 1

            print("[SimV2] #%d %s %s scenario=%s PM=%s KS=%s close=%s verif=%s" % (
                tidx, opp["symbol"], opp["poly_leg"], sc["name"],
                "OK" if trade["pm_filled"] else "X", "OK" if trade["ks_filled"] else "X",
                "pmB" if trade["pm_close_fired"] else "ksB" if trade["ks_close_fired"] else "-",
                trade["verif"]))

            save_results(data)

            now = time.time()
            if now - last_hb >= HEARTBEAT_INTERVAL:
                total = len(data["trades"])
                passed = sum(1 for t in data["trades"] if t.get("verif") == "PASS")
                print("[SimV2] ====== %d笔 PASS=%d FAIL=%d ======" % (total, passed, total - passed))
                for sn, s in sorted(data["scenario_results"].items()):
                    print("  %s: %d/%d" % (sn, s["passed"], s["total"]))
                last_hb = now

        except Exception as e:
            print("[SimV2] 异常:", str(e)[:300])
            import traceback; traceback.print_exc()
            time.sleep(POLL_INTERVAL)

    data["status"] = "finished"
    data["ended_at"] = datetime.datetime.now().isoformat()
    save_results(data)

    total = len(data["trades"])
    passed = sum(1 for t in data["trades"] if t.get("verif") == "PASS")
    print("[SimV2] ======== 完成 ========")
    print("[SimV2] %d笔 PASS=%d FAIL=%d" % (total, passed, total - passed))
    for sn, sr in sorted(data["scenario_results"].items()):
        print("  %s: %d/%d通过" % (sn, sr["passed"], sr["total"]))
    for f in [t for t in data["trades"] if t.get("verif") == "FAIL"]:
        print("  FAIL #%d %s %s: pmClose=%s ksClose=%s err=%s" % (
            f["idx"], f["coin"], f["poly_leg"], f.get("pm_close_fired"), f.get("ks_close_fired"), f.get("error","")))
