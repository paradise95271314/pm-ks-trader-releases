"""Small, testable policy gates used before live depth validation."""


def profit_meets_threshold(profit_cents, threshold_cents):
    return float(profit_cents) + 1e-9 >= float(threshold_cents)


def effective_profit_floor(config):
    target = float(config.get("min_profit_cents", 8) or 0)
    tolerance = max(0.0, float(config.get("profit_tolerance_cents", 1) or 0))
    return max(0.0, target - tolerance)


def hourly_group_allowed(completed_groups, max_groups):
    return int(completed_groups) < max(1, int(max_groups))
