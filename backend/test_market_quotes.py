from market_quotes import has_valid_pm_asks, is_fast_market_rejection


def test_zero_ask_is_not_an_executable_quote():
    assert not has_valid_pm_asks({"Up": 0.01, "Down": 0.0})


def test_two_positive_asks_are_executable_quotes():
    assert has_valid_pm_asks({"Up": 0.45, "Down": 0.56})


def test_fast_market_rejection_does_not_trigger_failure_cooldown():
    assert is_fast_market_rejection("KS真实盘口深度不足: 当前仅0张")
    assert is_fast_market_rejection("KS报价变化后利润不足")
    assert not is_fast_market_rejection("PM下单失败: order rejected")
