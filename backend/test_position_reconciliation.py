from position_reconciliation import (
    kalshi_position_sizes,
    polymarket_position_sizes,
    reconcile_positions,
)
from position_snapshot import TrustedPositionSnapshot


def _trade():
    return {
        "success": True, "hedged_qty": 5, "token_id": "pm-token",
        "ks_ticker": "KS-TICKER", "ks_side": "yes", "coin": "BTC",
    }


def test_zero_live_positions_remove_stale_history_position():
    assert reconcile_positions([_trade()], pm_live={}, ks_live={}) == []


def test_live_positions_set_each_platform_remaining_amount():
    positions = reconcile_positions(
        [_trade()], pm_live={"pm-token": 2.5}, ks_live={("KS-TICKER", "yes"): 3})
    assert positions[0]["pm_remaining"] == 2.5
    assert positions[0]["ks_remaining"] == 3


def test_exchange_payloads_are_normalized_by_direction():
    assert polymarket_position_sizes([{"asset": "a", "size": "5"}]) == {"a": 5}
    sizes = kalshi_position_sizes({"market_positions": [
        {"ticker": "Y", "position": 4}, {"ticker": "N", "position": -3}]})
    assert sizes[("Y", "yes")] == 4
    assert sizes[("N", "no")] == 3


def test_kalshi_fixed_point_position_fields_are_supported():
    sizes = kalshi_position_sizes({"market_positions": [
        {"ticker": "YES-FP", "position_fp": "5.00"},
        {"market_ticker": "NO-FP", "position_fp": "-2.00"},
    ]})

    assert sizes[("YES-FP", "yes")] == 5
    assert sizes[("NO-FP", "no")] == 2


def test_failed_live_lookup_falls_back_to_local_close_tracking():
    trade = _trade()
    trade["pm_closed_qty"] = 5
    positions = reconcile_positions([trade], pm_live=None, ks_live=None)
    assert positions[0]["pm_remaining"] == 0
    assert positions[0]["ks_remaining"] == 5


def test_failed_refresh_cannot_replace_last_complete_position_snapshot():
    snapshot = TrustedPositionSnapshot()
    trusted = [{"coin": "BTC", "pm_remaining": 5, "ks_remaining": 5}]

    snapshot.store(trusted)
    shown, stale = snapshot.resolve(
        [{"coin": "BTC"}, {"coin": "BTC"}, {"coin": "BTC"}], complete=False
    )

    assert shown == trusted
    assert stale is True


def test_first_failed_refresh_does_not_show_local_history_as_live_positions():
    snapshot = TrustedPositionSnapshot()

    shown, stale = snapshot.resolve([{"coin": "BTC"}], complete=False)

    assert shown == []
    assert stale is True
