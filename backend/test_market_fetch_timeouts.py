import fetch_current_polymarket as pm
import requests


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {"price": "1"}


def test_binance_price_request_has_a_timeout(monkeypatch):
    captured = {}

    def fake_get(url, **kwargs):
        captured.update(kwargs)
        return _Response()

    monkeypatch.setattr(pm.requests, "get", fake_get)
    price, error = pm.get_binance_current_price()

    assert price == 1.0
    assert error is None
    assert captured["timeout"] == pm.REQUEST_TIMEOUT


def test_polymarket_fetches_independent_sources_concurrently(monkeypatch):
    class ImmediateFuture:
        def __init__(self, value):
            self.value = value

        def result(self):
            return self.value

    submitted = []

    class FakePool:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def submit(self, fn, *args):
            submitted.append(fn.__name__)
            values = {
                "get_polymarket_data": ({"Up": 0.4, "Down": 0.6}, None),
                "get_binance_current_price": (100.0, None),
                "get_binance_open_price": (99.0, None),
            }
            return ImmediateFuture(values[fn.__name__])

    monkeypatch.setattr(pm, "ThreadPoolExecutor", lambda max_workers: FakePool())
    data, error = pm.fetch_polymarket_data_struct("slug", "BTCUSDT")

    assert error is None
    assert set(submitted) == {
        "get_polymarket_data", "get_binance_current_price", "get_binance_open_price"
    }
    assert data["prices"]["Up"] == 0.4


class _GammaResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return [{"markets": [{
            "clobTokenIds": '["up-token", "down-token"]',
            "outcomes": '["Up", "Down"]',
        }]}]


class _BookResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"asks": [{"price": "0.50", "size": "10"}], "bids": []}


def test_gamma_timeout_is_retried_before_failing_the_market(monkeypatch):
    calls = {"gamma": 0}

    def fake_get(url, **kwargs):
        if url == pm.POLYMARKET_API_URL:
            calls["gamma"] += 1
            if calls["gamma"] == 1:
                raise requests.ReadTimeout("temporary timeout")
            return _GammaResponse()
        return _BookResponse()

    pm._MARKET_METADATA_CACHE.clear()
    monkeypatch.setattr(pm.requests, "get", fake_get)
    monkeypatch.setattr(pm.time, "sleep", lambda _seconds: None)

    data, error = pm.get_polymarket_data("retry-slug")

    assert error is None
    assert data["token_ids"]["Up"] == "up-token"
    assert calls["gamma"] == 2


def test_gamma_metadata_is_cached_but_clob_prices_stay_live(monkeypatch):
    calls = {"gamma": 0, "clob": 0}

    def fake_get(url, **kwargs):
        if url == pm.POLYMARKET_API_URL:
            calls["gamma"] += 1
            return _GammaResponse()
        calls["clob"] += 1
        return _BookResponse()

    pm._MARKET_METADATA_CACHE.clear()
    monkeypatch.setattr(pm.requests, "get", fake_get)

    assert pm.get_polymarket_data("cached-slug")[1] is None
    assert pm.get_polymarket_data("cached-slug")[1] is None

    assert calls["gamma"] == 1
    assert calls["clob"] == 4
