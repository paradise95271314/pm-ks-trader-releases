#!/usr/bin/env python3
"""Kalshi API authentication helpers for dashboard."""
import base64, json, os, ssl, time, urllib.request
import certifi
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.backends import default_backend
from app_paths import KALSHI_KEY_FILE

KALSHI_API_BASE = "https://api.elections.kalshi.com/trade-api/v2"


def _ssl_context():
    return ssl.create_default_context(cafile=certifi.where())

def get_api_key_id():
    key_id = os.environ.get("KALSHI_API_KEY_ID", "").strip()
    if not key_id:
        raise RuntimeError("未配置Kalshi API Key ID")
    return key_id


def load_key(path=None):
    configured = os.environ.get("KALSHI_PRIVATE_KEY_FILE", "").strip()
    candidate = configured or path or str(KALSHI_KEY_FILE)
    if not os.path.exists(candidate) and KALSHI_KEY_FILE.exists():
        candidate = str(KALSHI_KEY_FILE)
    if not os.path.exists(candidate):
        raise RuntimeError("未配置Kalshi RSA私钥")
    with open(candidate, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())


def get_private_key():
    return load_key()

def sign_request(key, method, path):
    timestamp = str(int(time.time() * 1000))
    # Kalshi requires query parameters to be excluded from the signed path.
    full_path = "/trade-api/v2" + path.split("?", 1)[0]
    msg = (timestamp + method + full_path).encode()
    sig = key.sign(
        msg,
        asym_padding.PSS(
            mgf=asym_padding.MGF1(hashes.SHA256()),
            salt_length=asym_padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    return timestamp, base64.b64encode(sig).decode()

def fetch_with_auth(key, path, timeout=8):
    timestamp, sig = sign_request(key, "GET", path)
    req = urllib.request.Request(
        f"{KALSHI_API_BASE}{path}",
        headers={
            "User-Agent": "Mozilla/5.0",
            "KALSHI-ACCESS-KEY": get_api_key_id(),
            "KALSHI-ACCESS-SIGNATURE": sig,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
        },
    )
    return json.loads(urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()).read())

def discover_current_ticker(key, series="KXBTC15M"):
    data = fetch_with_auth(key, f"/markets?series_ticker={series}&status=open&limit=10")
    markets = data.get("markets", [])
    if not markets:
        return None, None
    best = max(markets, key=lambda m: m.get("close_time", 0))
    return best["ticker"], best

def fetch_price(ticker):
    """Try public endpoint first, fall back to auth if needed."""
    try:
        req = urllib.request.Request(
            f"{KALSHI_API_BASE}/market/{ticker}",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        data = json.loads(urllib.request.urlopen(req, timeout=8, context=_ssl_context()).read())
        return data.get("market", {})
    except urllib.error.HTTPError:
        return {}

if __name__ == "__main__":
    key = get_private_key()
    ticker, info = discover_current_ticker(key)
    print(f"Current ticker: {ticker}")
    if info:
        print(json.dumps(info, indent=2)[:500])
