import requests
import datetime
import pytz
import re
from get_current_markets import get_current_market_urls
import kalshi_auth as ka

def get_kalshi_markets(event_ticker):
    try:
        key = ka.get_private_key()
        data = ka.fetch_with_auth(key, "/markets?event_ticker=" + event_ticker + "&limit=100")
        return data.get('markets', []), None
    except Exception as e:
        return None, str(e)

def parse_strike(subtitle):
    match = re.search(r'\$([\d,]+)', subtitle)
    if match:
        return float(match.group(1).replace(',', ''))
    return 0.0

def fetch_kalshi_data_struct(event_override=None, binance_symbol="BTCUSDT"):
    try:
        if event_override:
            event_ticker = event_override
        else:
            market_info = get_current_market_urls()
            kalshi_url = market_info["kalshi"]
            event_ticker = kalshi_url.split("/")[-1].upper()

        current_price = None
        try:
            r = requests.get("https://api.binance.com/api/v3/ticker/price", params={"symbol": binance_symbol}, timeout=10)
            current_price = float(r.json()["price"])
        except:
            pass

        markets, err = get_kalshi_markets(event_ticker)
        if err:
            return None, "Kalshi Error: " + err
        if not markets:
            return {"event_ticker": event_ticker, "current_price": current_price, "markets": []}, None

        market_data = []
        for m in markets:
            strike = parse_strike(m.get('subtitle', ''))
            if strike > 0:
                ya_s = m.get("yes_ask_dollars", "?")
                na_s = m.get("no_ask_dollars", "?")
                yb_s = m.get("yes_bid_dollars", "?")
                nb_s = m.get("no_bid_dollars", "?")
                if not (ya_s and na_s and yb_s and nb_s) or "?" in (ya_s, na_s, yb_s, nb_s):
                    continue
                yd = float(ya_s)
                nd = float(na_s)
                yb = float(yb_s)
                nb = float(nb_s)
                if yb == 0.0 and nb == 0.0:
                    continue
                if yd == 0.0:
                    yd = float(m.get("yes_ask", 0)) / 100.0
                if nd == 0.0:
                    nd = float(m.get("no_ask", 0)) / 100.0

                market_data.append({
                    'strike': strike,
                    'yes_ask': yd,
                    'no_ask': nd,
                    'yes_bid': yb,
                    'no_bid': nb,
                    'subtitle': m.get('subtitle', ''),
                    'ticker': m.get('ticker', ''),
                })

        market_data.sort(key=lambda x: x['strike'])
        # 检查市场是否已收盘
        is_finished = False
        try:
            import datetime
            t = datetime.datetime.now(datetime.timezone.utc)
            ts = t.strftime("%Y-%m-%dT%H:%M:%SZ")
            _kk = ka.get_private_key()
            close_check = ka.fetch_with_auth(_kk, "/markets?event_ticker=" + event_ticker + "&limit=1")
            m0 = close_check.get("markets", [{}])[0]
            ct = m0.get("close_time", "")
            if ct and ct < ts:
                is_finished = True
        except:
            pass
        return {"event_ticker": event_ticker, "current_price": current_price, "markets": market_data,
                "isFinished": is_finished}, None

    except Exception as e:
        return None, "Kalshi Error: " + str(e)
