"""Polymarket x Kalshi esports match-winner arbitrage scanner and executor."""

from __future__ import annotations

import datetime as dt
import difflib
import json
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests


UA = "Mozilla/5.0"
PM_EVENTS = "https://gamma-api.polymarket.com/events"
PM_BOOK = "https://clob.polymarket.com/book"
KS_BASE = "https://api.elections.kalshi.com/trade-api/v2"

GAME_SERIES = {
    "cs2": ["KXCS2GAME", "KXCSGOGAME"],
    "lol": ["KXLOLGAME"],
    "dota2": ["KXDOTA2GAME"],
    "valorant": ["KXVALORANTGAME"],
}

_catalog_lock = threading.Lock()
_catalog_cache: dict[str, Any] = {"time": 0.0, "pairs": []}


def _loads(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _norm(value: str, remove_generic: bool = False) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    words = re.findall(r"[a-z0-9]+", text)
    if remove_generic:
        words = [w for w in words if w not in {"team", "gaming", "esports", "club"}]
    return " ".join(words)


def _team_score(left: str, right: str) -> float:
    scores = []
    for generic in (False, True):
        a, b = _norm(left, generic), _norm(right, generic)
        if not a or not b:
            continue
        if a == b:
            return 1.0
        scores.append(difflib.SequenceMatcher(None, a, b).ratio())
        aw, bw = set(a.split()), set(b.split())
        if aw and bw:
            scores.append(len(aw & bw) / max(len(aw), len(bw)))
    return max(scores or [0.0])


def _game_from_title(title: str) -> str:
    value = _norm(title)
    if "counter strike" in value or re.search(r"\bcs2\b", value):
        return "cs2"
    if "league of legends" in value or value.startswith("lol "):
        return "lol"
    if "dota 2" in value or "dota2" in value:
        return "dota2"
    if "valorant" in value:
        return "valorant"
    return ""


def _event_teams(title: str) -> tuple[str, str] | None:
    text = re.sub(r"^[^:]+:\s*", "", str(title or "")).strip()
    text = re.split(r"\s+\((?:BO|best of)\d+\)", text, maxsplit=1, flags=re.I)[0]
    parts = re.split(r"\s+vs\.?\s+", text, maxsplit=1, flags=re.I)
    if len(parts) != 2:
        return None
    right = re.split(r"\s+-\s+", parts[1], maxsplit=1)[0].strip()
    return parts[0].strip(), right


def _is_match_winner(question: str, event_title: str) -> bool:
    q = str(question or "")
    lowered = q.lower()
    excluded = ("map 1", "map 2", "map 3", "game 1", "game 2", "game 3",
                "handicap", "total", "first", "round", "kills", "baron", "dragon")
    if any(word in lowered for word in excluded):
        return False
    return _norm(q) == _norm(event_title) or bool(re.search(r"\bbo\d+\b", lowered))


def _fetch_pm_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for offset in range(0, 500, 100):
        response = requests.get(PM_EVENTS, params={
            "active": "true", "closed": "false", "limit": 100,
            "offset": offset, "tag_slug": "esports",
        }, timeout=25, headers={"User-Agent": UA})
        response.raise_for_status()
        page = response.json()
        if not isinstance(page, list):
            break
        events.extend(page)
        if len(page) < 100:
            break
    return events


def _pm_matches() -> list[dict[str, Any]]:
    now = dt.datetime.now(dt.timezone.utc)
    result = []
    for event in _fetch_pm_events():
        game = _game_from_title(event.get("title", ""))
        teams = _event_teams(event.get("title", ""))
        if not game or not teams:
            continue
        try:
            end = dt.datetime.fromisoformat(str(event.get("endDate", "")).replace("Z", "+00:00"))
            if end < now - dt.timedelta(hours=12) or end > now + dt.timedelta(days=14):
                continue
        except Exception:
            continue
        for market in event.get("markets", []):
            if market.get("closed") or not market.get("active", True):
                continue
            if not _is_match_winner(market.get("question", ""), event.get("title", "")):
                continue
            outcomes, tokens = _loads(market.get("outcomes")), _loads(market.get("clobTokenIds"))
            if len(outcomes) != 2 or len(tokens) != 2:
                continue
            direct = min(_team_score(outcomes[0], teams[0]), _team_score(outcomes[1], teams[1]))
            reverse = min(_team_score(outcomes[0], teams[1]), _team_score(outcomes[1], teams[0]))
            if max(direct, reverse) < 0.76:
                continue
            result.append({
                "game": game, "slug": event.get("slug", ""), "title": event.get("title", ""),
                "question": market.get("question", ""), "end_time": event.get("endDate", ""),
                "teams": [str(outcomes[0]), str(outcomes[1])],
                "tokens": [str(tokens[0]), str(tokens[1])],
            })
            break
    return result


def _fetch_ks_markets(series: str) -> list[dict[str, Any]]:
    response = requests.get(KS_BASE + "/markets", params={
        "series_ticker": series, "status": "open", "limit": 1000,
    }, timeout=25, headers={"User-Agent": UA})
    response.raise_for_status()
    return response.json().get("markets", [])


def _ks_matches() -> list[dict[str, Any]]:
    all_markets: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_fetch_ks_markets, series) for values in GAME_SERIES.values() for series in values]
        for future in as_completed(futures):
            try:
                all_markets.extend(future.result())
            except Exception:
                continue
    grouped: dict[str, list[dict[str, Any]]] = {}
    for market in all_markets:
        grouped.setdefault(str(market.get("event_ticker", "")), []).append(market)
    result = []
    for event_ticker, markets in grouped.items():
        by_team = {}
        for market in markets:
            team = str(market.get("yes_sub_title") or "").strip()
            if team and market.get("ticker"):
                by_team[team] = market
        if len(by_team) != 2:
            continue
        teams = list(by_team)
        title = str(markets[0].get("title", ""))
        game = _game_from_title(title)
        if not game:
            for key, series_values in GAME_SERIES.items():
                if any(event_ticker.startswith(series + "-") for series in series_values):
                    game = key
                    break
        if not game:
            continue
        result.append({"game": game, "event_ticker": event_ticker, "title": title,
                       "teams": teams, "markets": by_team})
    return result


def _pair_score(pm: dict[str, Any], ks: dict[str, Any]) -> tuple[float, bool]:
    a, b = pm["teams"]
    x, y = ks["teams"]
    direct = (_team_score(a, x) + _team_score(b, y)) / 2
    reverse = (_team_score(a, y) + _team_score(b, x)) / 2
    return (direct, False) if direct >= reverse else (reverse, True)


def _build_pairs() -> list[dict[str, Any]]:
    pm_matches, ks_matches = _pm_matches(), _ks_matches()
    pairs = []
    used_ks = set()
    for pm in pm_matches:
        candidates = []
        for ks in ks_matches:
            if pm["game"] != ks["game"] or ks["event_ticker"] in used_ks:
                continue
            score, reversed_order = _pair_score(pm, ks)
            if score >= 0.84:
                candidates.append((score, reversed_order, ks))
        if not candidates:
            continue
        score, reversed_order, ks = max(candidates, key=lambda item: item[0])
        ordered_ks_teams = list(reversed(ks["teams"])) if reversed_order else list(ks["teams"])
        individual = [_team_score(pm["teams"][i], ordered_ks_teams[i]) for i in (0, 1)]
        if min(individual) < 0.76:
            continue
        used_ks.add(ks["event_ticker"])
        pairs.append({**pm, "ks_event_ticker": ks["event_ticker"], "ks_title": ks["title"],
                      "ks_teams": ordered_ks_teams, "ks_markets": ks["markets"],
                      "match_score": round(score, 4)})
    return pairs


def _catalog() -> list[dict[str, Any]]:
    with _catalog_lock:
        if time.time() - float(_catalog_cache["time"]) < 60:
            return list(_catalog_cache["pairs"])
        pairs = _build_pairs()
        _catalog_cache.update({"time": time.time(), "pairs": pairs})
        return list(pairs)


def _pm_quote(token_id: str) -> dict[str, float]:
    response = requests.get(PM_BOOK, params={"token_id": token_id}, timeout=10)
    response.raise_for_status()
    asks = sorted(response.json().get("asks", []), key=lambda row: float(row["price"]))
    if not asks:
        return {"price": 0.0, "size": 0.0}
    return {"price": float(asks[0]["price"]), "size": float(asks[0]["size"])}


def scan(min_profit_cents: float = 10.0, fee_buffer_cents: float = 2.0) -> dict[str, Any]:
    pairs = _catalog()
    quotes: dict[str, dict[str, float]] = {}
    tokens = sorted({token for pair in pairs for token in pair["tokens"]})
    with ThreadPoolExecutor(max_workers=16) as pool:
        future_map = {pool.submit(_pm_quote, token): token for token in tokens}
        for future in as_completed(future_map):
            try:
                quotes[future_map[future]] = future.result()
            except Exception:
                quotes[future_map[future]] = {"price": 0.0, "size": 0.0}
    opportunities = []
    for pair in pairs:
        for pm_index in (0, 1):
            opposite = 1 - pm_index
            pm_team, ks_opponent = pair["teams"][pm_index], pair["ks_teams"][opposite]
            pm_quote = quotes.get(pair["tokens"][pm_index], {})
            ks_market = pair["ks_markets"].get(ks_opponent, {})
            ks_yes = float(ks_market.get("yes_ask_dollars", 0) or 0)
            own_ks_market = pair["ks_markets"].get(pair["ks_teams"][pm_index], {})
            ks_no = float(own_ks_market.get("no_ask_dollars", 0) or 0)
            choices = []
            if 0 < ks_yes < 1:
                choices.append((ks_yes, ks_market, "yes", ks_opponent))
            if 0 < ks_no < 1:
                choices.append((ks_no, own_ks_market, "no", pair["ks_teams"][pm_index]))
            if not choices or not 0 < float(pm_quote.get("price", 0)) < 1:
                continue
            ks_price, selected_market, ks_side, ks_team = min(choices, key=lambda item: item[0])
            total = float(pm_quote["price"]) + ks_price
            gross = (1.0 - total) * 100.0
            estimated_net = gross - float(fee_buffer_cents)
            if estimated_net + 1e-9 < float(min_profit_cents):
                continue
            opportunities.append({
                "id": pair["slug"] + ":" + str(pm_index) + ":" + str(selected_market.get("ticker", "")),
                "game": pair["game"], "title": pair["title"], "pm_slug": pair["slug"],
                "pm_team": pm_team, "pm_token_id": pair["tokens"][pm_index],
                "pm_price": float(pm_quote["price"]), "pm_top_size": float(pm_quote.get("size", 0)),
                "ks_team": ks_team, "ks_side": ks_side,
                "ks_ticker": selected_market.get("ticker", ""), "ks_price": ks_price,
                "total_cost": round(total, 4), "gross_profit_cents": round(gross, 2),
                "fee_buffer_cents": float(fee_buffer_cents),
                "estimated_profit_cents": round(estimated_net, 2),
                "match_score": pair["match_score"], "ks_event_ticker": pair["ks_event_ticker"],
            })
    opportunities.sort(key=lambda item: item["estimated_profit_cents"], reverse=True)
    return {"time": dt.datetime.now().isoformat(), "matched_markets": len(pairs),
            "opportunities": opportunities, "total": len(opportunities)}


def execute_opportunity(opportunity: dict[str, Any], shares: int = 5,
                        min_profit_cents: float = 10.0, fee_buffer_cents: float = 2.0,
                        liquidity_buffer: float = 2.0) -> dict[str, Any]:
    required = ("pm_slug", "pm_team", "pm_token_id", "ks_ticker", "ks_side")
    if any(not opportunity.get(field) for field in required):
        return {"success": False, "error": "电竞套利参数不完整"}
    from execute_arb import execute_arb
    result = execute_arb(
        coin="ESPORTS", pm_direction=str(opportunity["pm_team"]),
        pm_slug=str(opportunity["pm_slug"]), token_id=str(opportunity["pm_token_id"]),
        ks_ticker=str(opportunity["ks_ticker"]), ks_side=str(opportunity["ks_side"]),
        fixed_shares=max(1, int(shares)), min_shares=max(1, int(shares)),
        min_profit_cents=float(min_profit_cents) + float(fee_buffer_cents),
        liquidity_buffer=max(1.0, float(liquidity_buffer)), exact_ks_ticker=True,
    )
    result["mode"] = "esports"
    result["title"] = opportunity.get("title", "")
    result["estimated_fee_buffer_cents"] = float(fee_buffer_cents)
    return result


class EsportsAutoTrader:
    def __init__(self) -> None:
        self.enabled = False
        self.thread: threading.Thread | None = None
        self.last_result: dict[str, Any] | None = None
        self.last_scan: dict[str, Any] | None = None
        self.trade_count = 0
        self.traded_events: set[str] = set()
        self.lock = threading.Lock()

    def start(self) -> None:
        with self.lock:
            if self.enabled:
                return
            self.enabled = True
            self.thread = threading.Thread(target=self._loop, daemon=True, name="esports-arbitrage")
            self.thread.start()

    def stop(self) -> None:
        self.enabled = False

    def status(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "trade_count": self.trade_count,
                "last_result": self.last_result, "last_scan": self.last_scan,
                "traded_events": len(self.traded_events)}

    def _loop(self) -> None:
        from settings_manager import load_config
        while self.enabled:
            try:
                cfg = load_config()
                min_profit = float(cfg.get("esports_min_profit_cents", 10))
                fee_buffer = float(cfg.get("esports_fee_buffer_cents", 2))
                self.last_scan = scan(min_profit, fee_buffer)
                candidates = [o for o in self.last_scan.get("opportunities", [])
                              if o.get("ks_event_ticker") not in self.traded_events]
                if candidates:
                    selected = candidates[0]
                    print("[Esports] 发现锁利机会: %s PM=%s KS=%s 净利润约%.1f¢" % (
                        selected.get("title", ""), selected.get("pm_team", ""),
                        selected.get("ks_team", ""), selected.get("estimated_profit_cents", 0)))
                    self.last_result = execute_opportunity(
                        selected, shares=int(cfg.get("esports_order_shares", 5)),
                        min_profit_cents=min_profit, fee_buffer_cents=fee_buffer,
                        liquidity_buffer=float(cfg.get("liquidity_buffer", 2.0)))
                    if self.last_result.get("success"):
                        self.trade_count += 1
                        self.traded_events.add(str(selected.get("ks_event_ticker", "")))
                    if self.last_result.get("unhedged_platform"):
                        print("[Esports] 检测到单腿残留，自动停止电竞交易")
                        self.enabled = False
                        break
            except Exception as exc:
                self.last_result = {"success": False, "error": str(exc)[:300]}
            for _ in range(max(1, int(float(load_config().get("esports_poll_interval", 5)) * 2))):
                if not self.enabled:
                    break
                time.sleep(0.5)


AUTO = EsportsAutoTrader()
