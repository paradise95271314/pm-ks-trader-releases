"""
PM+KS 对冲下单（修复版）
使用方法：修改 COIN / SLUG / PM_DIRECTION / KS_EVENT / KS_STRIKE 后运行
"""
import json, requests, sys, uuid, urllib.request, base64, time, os

# ===== 配置 =====
COIN = "BTC"
SLUG = "bitcoin-up-or-down-july-15-2026-10am-et"
PM_DIRECTION = "DOWN"
KS_EVENT = "KXBTC-26JUL1511"
KS_STRIKE = "B64750"
KS_SIZE = 1
# ================

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kalshi_auth import fetch_with_auth, get_api_key_id, get_private_key
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding as pad
from dotenv import load_dotenv
load_dotenv(override=False)
from py_clob_client_v2 import ClobClient
from py_clob_client_v2.clob_types import OrderArgsV2

# ---- 1. PM 盘口 ----
print("=== PM: %s %s ===" % (COIN, PM_DIRECTION))
r = requests.get("https://gamma-api.polymarket.com/events?slug=" + SLUG, timeout=10,
                 headers={"User-Agent": "Mozilla/5.0"})
m = r.json()[0].get("markets", [{}])[0]
cids = json.loads(m.get("clobTokenIds", "[]"))
outs = json.loads(m.get("outcomes", "[]"))
prices = m.get("outcomePrices", ["?", "?"])
print("Gamma prices:", prices)

tid = ""
for oc, cid in zip(outs, cids):
    if oc.upper() == PM_DIRECTION.upper():
        tid = cid
        break
print("%s tokenId:" % PM_DIRECTION, tid[:24] if tid else "NOT FOUND")

# 排序 ask，取最低价
b = requests.get("https://clob.polymarket.com/book?token_id=" + tid, timeout=10).json()
asks = sorted(b.get("asks", []), key=lambda x: float(x["price"]))

if asks:
    pm_price = float(asks[0]["price"])
    pm_avail = float(asks[0]["size"])
    print("PM best ask: %.4f (available: %s)" % (pm_price, pm_avail))

    min_notional = 1.0
    pm_min_size = int(min_notional / pm_price) + 1
    pm_size = max(pm_min_size, 1)
    if pm_size > pm_avail:
        print("ERROR: 需 %d 张但只有 %s 张" % (pm_size, pm_avail))
        sys.exit(1)
    print("PM下单: BUY %s %d @ %.4f (notional=%.2f)" % (PM_DIRECTION, pm_size, pm_price, pm_price*pm_size))
else:
    print("ERROR: PM 盘口无卖单")
    sys.exit(1)

# ---- 2. KS ----
ks_ticker = KS_EVENT + "-" + KS_STRIKE
print("\n=== KS: %s ===" % ks_ticker)
kkey = get_private_key()
KB = "https://api.elections.kalshi.com/trade-api/v2"
KH = get_api_key_id()

mkt = fetch_with_auth(kkey, "/markets/" + ks_ticker)
ya = mkt.get("market", {}).get("yes_ask_dollars", "?")
print("KS yes_ask: %s" % ya)

# ---- 3. 下 PM ----
print("\n--- PM下单 ---")
key = os.environ.get("POLYMARKET_PRIVATE_KEY") or os.environ.get("PRIVATE_KEY")
funder_hex = os.environ.get("POLYMARKET_FUNDER")
sig_type = int(os.environ.get("POLYMARKET_SIGNATURE_TYPE", "0"))
client = ClobClient("https://clob.polymarket.com", key=key, chain_id=137,
                     signature_type=sig_type, funder=funder_hex)
creds = client.derive_api_key()
client.set_api_creds(creds)

pm_result = client.create_and_post_order(OrderArgsV2(
    token_id=tid, price=round(pm_price, 2), size=float(pm_size), side="BUY"))
print("PM: id=%s status=%s" % (pm_result.get("order_id","?")[:24], pm_result.get("status","?")))

# ---- 4. 下 KS ----
print("\n--- KS下单 ---")
ol = {"orders": [{"ticker": ks_ticker, "side": "bid", "count": str(KS_SIZE),
    "price": str(ya) if "." in ya else ya + ".0000",
    "time_in_force": "good_till_canceled",
    "self_trade_prevention_type": "taker_at_cross",
    "client_order_id": str(uuid.uuid4())}]}
body = json.dumps(ol)
fp = "/portfolio/events/orders/batched"
full_sig_path = "/trade-api/v2" + fp
ts = str(int(time.time() * 1000))
msg = ts + "POST" + full_sig_path
sig = kkey.sign(msg.encode(), pad.PSS(
    mgf=pad.MGF1(hashes.SHA256()), salt_length=pad.PSS.MAX_LENGTH), hashes.SHA256())
sb64 = base64.b64encode(sig).decode()
req = urllib.request.Request(KB + fp, data=body.encode(),
    headers={"Content-Type": "application/json", "KALSHI-ACCESS-KEY": KH,
             "KALSHI-ACCESS-SIGNATURE": sb64, "KALSHI-ACCESS-TIMESTAMP": ts})
try:
    rj = json.loads(urllib.request.urlopen(req, timeout=15).read())
    o = rj.get("orders", [{}])[0]
    print("KS: id=%s status=%s fill=%s price=%s" % (
        o.get("order_id","?")[:24], o.get("status","?"),
        o.get("fill_count","0"), o.get("average_fill_price","?")))
except Exception as e:
    print("KS ERR:", str(e)[:300])
