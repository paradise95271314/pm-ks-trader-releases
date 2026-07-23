from arbitrage_view import select_best_check


def test_best_check_is_visible_when_no_quote_is_profitable():
    best = select_best_check([
        {"total_cost": 1.03, "kalshi_strike": 100},
        {"total_cost": 1.01, "kalshi_strike": 200},
    ])

    assert best["kalshi_strike"] == 200
    assert round(best["margin"], 6) == -0.01
    assert best["is_arbitrage"] is False


def test_best_check_marks_a_positive_spread_as_arbitrage():
    best = select_best_check([{"total_cost": 0.985, "kalshi_strike": 100}])

    assert round(best["margin"], 6) == 0.015
    assert best["is_arbitrage"] is True


def test_best_check_ignores_empty_quotes():
    assert select_best_check([{"total_cost": 0}]) is None
