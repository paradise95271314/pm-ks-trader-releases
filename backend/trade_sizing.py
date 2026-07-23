"""Pure sizing rules shared by live execution and tests."""

import math


def calculate_hedge_shares(pm_price, target_usd, min_shares, fixed_shares=0):
    pm_price = float(pm_price)
    if not 0 < pm_price < 1:
        raise ValueError("PM price must be between 0 and 1")
    minimum = max(math.ceil(float(min_shares or 0)), 1)
    if fixed_shares and int(fixed_shares) > 0:
        return max(int(fixed_shares), minimum), "fixed"
    target_usd = max(float(target_usd), 1.0)
    return max(math.ceil(target_usd / pm_price), minimum), "target_usd"
