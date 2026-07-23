import ast
from pathlib import Path

from trading_policy import effective_profit_floor, hourly_group_allowed, profit_meets_threshold


AUTO_TRADE_SOURCE = Path(__file__).with_name("auto_trade.py").read_text(encoding="utf-8")
SETTINGS_SOURCE = Path(__file__).with_name("settings_manager.py").read_text(encoding="utf-8")


def _default_config():
    tree = ast.parse(SETTINGS_SOURCE)
    node = next(item for item in tree.body if isinstance(item, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "DEFAULT_CONFIG" for target in item.targets))
    return ast.literal_eval(node.value)


def _function_source(name):
    tree = ast.parse(AUTO_TRADE_SOURCE)
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == name)
    return ast.get_source_segment(AUTO_TRADE_SOURCE, node)


def test_default_profit_floor_is_eight_cents_per_share():
    assert _default_config()["min_profit_cents"] == 8


def test_five_share_order_only_requires_five_executable_shares():
    assert _default_config()["liquidity_buffer"] == 1.0


def test_default_hourly_group_limit_is_configurable_five():
    assert _default_config()["max_trades_per_hour"] == 5


def test_second_through_fifth_groups_are_allowed_then_sixth_is_blocked():
    assert hourly_group_allowed(1, 5)
    assert hourly_group_allowed(4, 5)
    assert not hourly_group_allowed(5, 5)


def test_hour_boundary_never_blocks_a_profitable_trade():
    source = _function_source("_is_after_start_delay")
    assert "return True" in source
    assert "datetime" not in source


def test_candidate_selection_no_longer_uses_pm_price_range():
    source = _function_source("_decide_best_opp")
    assert "price_min_cents" not in source
    assert "price_max_cents" not in source


def test_eight_cent_target_allows_one_cent_downward_tolerance():
    threshold = effective_profit_floor(_default_config())
    assert threshold == 7
    assert profit_meets_threshold(8.0, threshold)
    assert profit_meets_threshold(7.9, threshold)
    assert profit_meets_threshold(7.0, threshold)
    assert not profit_meets_threshold(6.9, threshold)
