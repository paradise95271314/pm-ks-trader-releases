from coin_config import get_supported_coins


def test_only_btc_is_supported():
    assert get_supported_coins() == ["BTC"]
