import datetime
import pytz
from find_new_market import generate_market_url as generate_polymarket_url
from find_new_kalshi_market import generate_kalshi_url
from coin_config import COINS

def get_current_market_urls():
    """
    Returns a dictionary with the current active market URLs for Polymarket and Kalshi.
    'Current' is defined as the market expiring/resolving at the top of the next hour.
    """
    now = datetime.datetime.now(pytz.utc)
    
    # Target time is the current full hour
    # Example: If now is 12:15, target is 12:00.
    target_time = now.replace(minute=0, second=0, microsecond=0)
    
    polymarket_url = generate_polymarket_url(target_time)
    
    # Kalshi seems to use the *next* hour for the current market identifier
    # If it's 13:XX, the market is ...14
    kalshi_target_time = target_time + datetime.timedelta(hours=1)
    kalshi_url = generate_kalshi_url(kalshi_target_time)
    
    return {
        "polymarket": polymarket_url,
        "kalshi": kalshi_url,
        "target_time_utc": target_time,
        "target_time_et": target_time.astimezone(pytz.timezone('US/Eastern'))
    }


def get_coin_market_urls():
    """Returns market URLs for ALL supported coins."""
    now = datetime.datetime.now(pytz.utc)
    target_time = now.replace(minute=0, second=0, microsecond=0)
    kalshi_target_time = target_time + datetime.timedelta(hours=1)
    et_tz = pytz.timezone('US/Eastern')

    result = {}
    for symbol, config in COINS.items():
        pname = config["polymarket_name"]
        kseries = config["kalshi_series"]

        et_time = target_time.astimezone(et_tz)
        month = et_time.strftime("%B").lower()
        day = et_time.day
        year = et_time.year
        hour_int = int(et_time.strftime("%I"))
        am_pm = et_time.strftime("%p").lower()
        poly_slug = f"{pname}-up-or-down-{month}-{day}-{year}-{hour_int}{am_pm}-et"

        ks_et = kalshi_target_time.astimezone(et_tz)
        ks_year = ks_et.strftime("%y")
        ks_month = ks_et.strftime("%b").upper()
        ks_day = ks_et.strftime("%d")
        ks_hour = ks_et.strftime("%H")
        ks_ticker = f"{kseries}-{ks_year}{ks_month}{ks_day}{ks_hour}"

        result[symbol] = {
            "polymarket_slug": poly_slug,
            "kalshi_event_ticker": ks_ticker,
            "binance_symbol": config["binance_symbol"],
        }
    return result


if __name__ == "__main__":
    urls = get_current_market_urls()
    
    print(f"Current Time (UTC): {datetime.datetime.now(pytz.utc)}")
    print(f"Target Market Time (ET): {urls['target_time_et']}")
    print("-" * 50)
    print(f"Polymarket: {urls['polymarket']}")
    print(f"Kalshi:     {urls['kalshi']}")
