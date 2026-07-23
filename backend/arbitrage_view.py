"""Helpers for presenting the best quote even when it is not yet profitable."""


def select_best_check(checks):
    valid = [item for item in checks if float(item.get("total_cost", 0) or 0) > 0]
    if not valid:
        return None
    best = min(valid, key=lambda item: float(item["total_cost"]))
    result = dict(best)
    result["margin"] = 1.0 - float(result["total_cost"])
    result["is_arbitrage"] = result["margin"] > 0
    return result
