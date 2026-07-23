from execution_prices import (
    kalshi_outcome_fill_price,
    polymarket_fill_price,
    result_fill_price,
)


def test_kalshi_yes_cost_uses_actual_average_fill_price():
    assert kalshi_outcome_fill_price({"average_fill_price": "0.325"}, "yes", 0.31) == 0.325


def test_kalshi_no_cost_converts_yes_book_fill_to_no_outcome_cost():
    assert kalshi_outcome_fill_price({"average_fill_price": "0.68"}, "no", 0.31) == 0.32


def test_polymarket_cost_uses_actual_paid_amount_per_share():
    assert polymarket_fill_price({"makingAmount": "3.05", "takingAmount": "5"}, 0.60) == 0.61


def test_history_price_prefers_fill_and_falls_back_to_plan():
    result = {"ks": {"avg_outcome_price": 0.325}, "ks_plan": {"price": 0.31}}
    assert result_fill_price(result, "ks") == 0.325
    assert result_fill_price({"ks_plan": {"price": 0.31}}, "ks") == 0.31
