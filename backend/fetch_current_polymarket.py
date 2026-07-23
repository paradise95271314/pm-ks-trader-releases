import requests
import time
import datetime
import pytz
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from get_current_markets import get_current_market_urls

# Configuration
POLYMARKET_API_URL = "https://gamma-api.polymarket.com/events"
BINANCE_PRICE_URL = "https://api.binance.com/api/v3/ticker/price"
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
CLOB_API_URL = "https://clob.polymarket.com/book"
REQUEST_TIMEOUT = (3, 4)
_MARKET_METADATA_CACHE = {}
_MARKET_METADATA_LOCK = threading.Lock()


def _get_market_metadata(slug):
    """Load immutable token metadata once per hourly market, retrying a transient Gamma timeout."""
    with _MARKET_METADATA_LOCK:
        cached = _MARKET_METADATA_CACHE.get(slug)
        if cached:
            return cached

        last_error = None
        for attempt in range(2):
            try:
                response = requests.get(
                    POLYMARKET_API_URL, params={"slug": slug}, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                data = response.json()
                if not data:
                    raise RuntimeError("Event not found")
                markets = data[0].get("markets", [])
                if not markets:
                    raise RuntimeError("Markets not found in event")
                market = markets[0]
                token_ids = json.loads(market.get("clobTokenIds", "[]"))
                outcomes = json.loads(market.get("outcomes", "[]"))
                if len(token_ids) != 2 or len(outcomes) != 2:
                    raise RuntimeError("Unexpected number of tokens")
                cached = (token_ids, outcomes)
                _MARKET_METADATA_CACHE[slug] = cached
                return cached
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(0.15)
        raise last_error

def get_clob_price(token_id):
    try:
        response = requests.get(CLOB_API_URL, params={"token_id": token_id}, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        
        # data structure: {'bids': [{'price': '0.38', 'size': '...'}, ...], 'asks': ...}
        bids = data.get('bids', [])
        asks = data.get('asks', [])
        
        best_bid = 0.0
        best_ask = 0.0
        
        if bids:
            # Bids: We want the HIGHEST price someone is willing to pay
            best_bid = max(float(b['price']) for b in bids)
            
        if asks:
            # Asks: We want the LOWEST price someone is willing to sell for
            best_ask = min(float(a['price']) for a in asks)
            
        return best_ask if best_ask > 0 else 0.0 # Return Ask as the "Buy" price
    except Exception as e:
        return None

def get_polymarket_data(slug):
    try:
        # Token IDs do not change during an hourly market. Gamma is only needed
        # once; live prices below always come directly from the CLOB orderbook.
        clob_token_ids, outcomes = _get_market_metadata(slug)
            
        # 2. Fetch Price for each Token from CLOB
        prices = {}
        # Assuming order is [Up, Down] or matches outcomes
        # Usually outcomes are ["Up", "Down"] and clobTokenIds correspond.
        
        with ThreadPoolExecutor(max_workers=2) as pool:
            price_futures = [pool.submit(get_clob_price, token_id) for token_id in clob_token_ids]
        for outcome, future in zip(outcomes, price_futures):
            price = future.result()
            if price is not None:
                prices[outcome] = price
            else:
                prices[outcome] = 0.0
            
        return {
            "prices": prices,
            "token_ids": dict(zip(outcomes, clob_token_ids)),
        }, None
    except Exception as e:
        return None, str(e)

def get_binance_current_price(symbol="BTCUSDT"):
    try:
        response = requests.get(BINANCE_PRICE_URL, params={"symbol": symbol}, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        return float(data["price"]), None
    except Exception as e:
        return None, str(e)

def get_binance_open_price(target_time_utc, symbol="BTCUSDT"):
    try:
        # Timestamp in milliseconds
        timestamp_ms = int(target_time_utc.timestamp() * 1000)
        
        # Fetch 1h kline for the specific timestamp
        params = {
            "symbol": symbol,
            "interval": "1h",
            "startTime": timestamp_ms,
            "limit": 1
        }
        response = requests.get(BINANCE_KLINES_URL, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        
        if not data:
            return None, "Candle not found yet"
            
        # Kline format: [Open time, Open, High, Low, Close, Volume, ...]
        open_price = float(data[0][1])
        return open_price, None
    except Exception as e:
        return None, str(e)

def fetch_polymarket_data_struct(slug_override=None, binance_symbol="BTCUSDT"):
    """
    Fetches current Polymarket data and returns a structured dictionary.
    """
    try:
        # Get current market info
        if slug_override:
            slug = slug_override
        else:
            market_info = get_current_market_urls()
            slug = market_info["polymarket"].split("/")[-1]

        # Compute target time for binance open price
        import datetime, pytz
        target_time_utc = datetime.datetime.now(pytz.utc).replace(minute=0, second=0, microsecond=0)

        # Fetch Data
        with ThreadPoolExecutor(max_workers=3) as pool:
            poly_future = pool.submit(get_polymarket_data, slug)
            current_future = pool.submit(get_binance_current_price, binance_symbol)
            beat_future = pool.submit(get_binance_open_price, target_time_utc, binance_symbol)
            poly_payload, poly_err = poly_future.result()
            current_price, curr_err = current_future.result()
            price_to_beat, beat_err = beat_future.result()
        
        if poly_err:
            return None, f"Polymarket Error: {poly_err}"
            
        # Accept the old plain-price shape in tests and legacy callers.
        if isinstance(poly_payload, dict) and "prices" in poly_payload:
            poly_prices = poly_payload["prices"]
            token_ids = poly_payload.get("token_ids", {})
        else:
            poly_prices = poly_payload
            token_ids = {}
        return {
            "price_to_beat": price_to_beat,
            "current_price": current_price,
            "prices": poly_prices, # {'Up': 0.xx, 'Down': 0.xx}
            "token_ids": token_ids,
            "slug": slug,
            "target_time_utc": target_time_utc
        }, None
        
    except Exception as e:
        return None, str(e)

def main():
    data, err = fetch_polymarket_data_struct()
    
    if err:
        print(f"Error: {err}")
        return

    print(f"Fetching data for: {data['slug']}")
    print(f"Target Time (UTC): {data['target_time_utc']}")
    print("-" * 50)
    
    if data['price_to_beat'] is None:
         print("PRICE TO BEAT: Error")
    else:
        print(f"PRICE TO BEAT: ${data['price_to_beat']:,.2f}")

    if data['current_price'] is None:
        print("CURRENT PRICE: Error")
    else:
        print(f"CURRENT PRICE: ${data['current_price']:,.2f}")
    
    up_price = data['prices'].get("Up", 0)
    down_price = data['prices'].get("Down", 0)
    print(f"BUY: UP ${up_price:.3f} & DOWN ${down_price:.3f}")

if __name__ == "__main__":
    main()
