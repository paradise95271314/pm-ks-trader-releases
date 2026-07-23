import sys
import types

from esports_arbitrage import _event_teams, _is_match_winner, _pair_score, execute_opportunity


def test_match_winner_filter_excludes_map_markets():
    title = "Counter-Strike: Spirit vs OG (BO3) - BLAST Bounty"
    assert _event_teams(title) == ("Spirit", "OG")
    assert _is_match_winner(title, title)
    assert not _is_match_winner("Counter-Strike: Spirit vs OG - Map 1 Winner", title)


def test_team_order_can_be_reversed_between_platforms():
    pm = {"teams": ["G2 Esports", "Movistar KOI"]}
    ks = {"teams": ["Movistar KOI", "G2 Esports"]}
    score, reversed_order = _pair_score(pm, ks)
    assert reversed_order is True
    assert score > 0.95


def test_execution_uses_exact_prevalidated_market_ids(monkeypatch):
    captured = {}

    def fake_execute_arb(**kwargs):
        captured.update(kwargs)
        return {"success": True}

    monkeypatch.setitem(sys.modules, "execute_arb", types.SimpleNamespace(execute_arb=fake_execute_arb))
    result = execute_opportunity({
        "title": "LoL: A vs B (BO3)", "pm_slug": "lol-a-b",
        "pm_team": "A", "pm_token_id": "123", "ks_ticker": "KXLOLGAME-X-B",
        "ks_side": "yes",
    }, shares=5, min_profit_cents=10, fee_buffer_cents=2, liquidity_buffer=2)
    assert result["success"] is True
    assert captured["pm_slug"] == "lol-a-b"
    assert captured["token_id"] == "123"
    assert captured["exact_ks_ticker"] is True
    assert captured["fixed_shares"] == 5
    assert captured["min_profit_cents"] == 12
