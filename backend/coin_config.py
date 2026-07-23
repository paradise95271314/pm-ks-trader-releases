"""
Coin configuration for multi-coin arbitrage monitoring.
"""
COINS = {
    "BTC": {
        "polymarket_name": "bitcoin",
        "kalshi_series": "KXBTCD",
        "binance_symbol": "BTCUSDT",
    },
    "ETH": {
        "polymarket_name": "ethereum",
        "kalshi_series": "KXETHD",
        "binance_symbol": "ETHUSDT",
    },
}


def get_supported_coins():
    return list(COINS.keys())

def get_coin_config(symbol):
    return COINS.get(symbol.upper())
