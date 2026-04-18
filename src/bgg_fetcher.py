"""
BGG XML API v2 client.

Fetches play history and game metadata for a BGG user.
Sleeps ~2 s between requests to stay within BGG's rate limit guidance.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET

import requests

BGG_API = "https://boardgamegeek.com/xmlapi2"

# BGG mechanic link ID for "Cooperative Game"
_COOPERATIVE_MECHANIC_ID = "2023"

# Seconds to wait between API calls
_REQUEST_DELAY = 2.0


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def fetch_all_plays(username: str) -> list[dict]:
    """
    Fetch every play logged by *username* on BGG (all pages).

    Each returned dict has::

        {
            "id":         12345,           # BGG play ID (int)
            "date":       "2024-01-15",    # "YYYY-MM-DD"
            "length":     90,              # minutes (0 = not recorded)
            "incomplete": False,
            "game_id":    266192,          # BGG object ID (int)
            "game_name":  "Wingspan",
            "players": [
                {
                    "name":          "Brian",
                    "score":         "45",
                    "win":           True,
                    "new":           False,
                    "startposition": "1",  # "" when absent
                }
            ],
        }
    """
    plays: list[dict] = []
    page = 1

    while True:
        url = f"{BGG_API}/plays?username={username}&page={page}"
        root = _get_xml(url)

        total = int(root.attrib.get("total", 0))
        page_plays = root.findall("play")
        if not page_plays:
            break

        for play_el in page_plays:
            item = play_el.find("item")
            if item is None:
                continue

            players = [
                {
                    "name":          p.attrib.get("name", ""),
                    "score":         p.attrib.get("score", "") or "",
                    "win":           p.attrib.get("win") == "1",
                    "new":           p.attrib.get("new") == "1",
                    "startposition": p.attrib.get("startposition", "") or "",
                }
                for p in play_el.findall("players/player")
            ]

            plays.append({
                "id":         int(play_el.attrib.get("id", 0)),
                "date":       play_el.attrib.get("date", ""),
                "length":     int(play_el.attrib.get("length", 0) or 0),
                "incomplete": play_el.attrib.get("incomplete") == "1",
                "game_id":    int(item.attrib.get("objectid", 0)),
                "game_name":  item.attrib.get("name", ""),
                "players":    players,
            })

        if len(plays) >= total:
            break

        page += 1
        time.sleep(_REQUEST_DELAY)

    return plays


def fetch_game_details(bgg_ids: list[int]) -> dict[int, dict]:
    """
    Fetch metadata for a list of BGG game IDs (batched in groups of 20).

    Returns ``{bgg_id: {...}}`` where each game dict has::

        {
            "bgg_id":       266192,
            "name":         "Wingspan",
            "bgg_year":     2019,
            "url_thumb":    "https://cf.geekdo-images.com/...",
            "url_image":    "https://cf.geekdo-images.com/...",
            "cooperative":  False,
            "min_players":  1,
            "max_players":  5,
            "min_play_time": 40,
            "max_play_time": 70,
            "designers":    "Elizabeth Hargrave",
        }
    """
    result: dict[int, dict] = {}
    batch_size = 20

    for i in range(0, len(bgg_ids), batch_size):
        batch = bgg_ids[i : i + batch_size]
        ids_str = ",".join(str(bid) for bid in batch)
        url = f"{BGG_API}/thing?id={ids_str}&stats=1"
        root = _get_xml(url)

        for item in root.findall("item"):
            bid = int(item.attrib.get("id", 0))

            # Primary name
            name = ""
            for name_el in item.findall("name"):
                if name_el.attrib.get("type") == "primary":
                    name = name_el.attrib.get("value", "")
                    break

            def _int_val(tag: str) -> int | None:
                el = item.find(tag)
                if el is None:
                    return None
                try:
                    return int(el.attrib.get("value", 0)) or None
                except (ValueError, TypeError):
                    return None

            def _text(tag: str) -> str:
                el = item.find(tag)
                return (el.text or "").strip() if el is not None else ""

            # Cooperative = has mechanic "Cooperative Game" (link id 2023)
            is_coop = any(
                lnk.attrib.get("id") == _COOPERATIVE_MECHANIC_ID
                for lnk in item.findall("link")
                if lnk.attrib.get("type") == "boardgamemechanic"
            )

            designers = ", ".join(
                lnk.attrib.get("value", "")
                for lnk in item.findall("link")
                if lnk.attrib.get("type") == "boardgamedesigner"
                and lnk.attrib.get("value", "").lower() not in ("(uncredited)", "")
            )

            result[bid] = {
                "bgg_id":        bid,
                "name":          name,
                "bgg_year":      _int_val("yearpublished"),
                "url_thumb":     _text("thumbnail"),
                "url_image":     _text("image"),
                "cooperative":   is_coop,
                "min_players":   _int_val("minplayers"),
                "max_players":   _int_val("maxplayers"),
                "min_play_time": _int_val("minplaytime"),
                "max_play_time": _int_val("maxplaytime"),
                "designers":     designers,
            }

        if i + batch_size < len(bgg_ids):
            time.sleep(_REQUEST_DELAY)

    return result


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _get_xml(url: str, max_retries: int = 5) -> ET.Element:
    """
    GET *url* and return parsed XML root.

    Handles HTTP 202 (BGG queue), 429 (rate limit), and 5xx errors with
    exponential back-off.  Raises ``RuntimeError`` after *max_retries*.
    """
    for attempt in range(max_retries):
        resp = requests.get(url, timeout=30)

        if resp.status_code == 200:
            return ET.fromstring(resp.content)

        if resp.status_code == 202:
            # BGG is still processing the request — try again after a delay
            wait = _REQUEST_DELAY * (2 ** attempt)
            time.sleep(wait)
            continue

        if resp.status_code == 429:
            time.sleep(_REQUEST_DELAY * (2 ** attempt))
            continue

        if resp.status_code >= 500:
            time.sleep(_REQUEST_DELAY * (2 ** attempt))
            continue

        resp.raise_for_status()

    raise RuntimeError(f"BGG API did not respond after {max_retries} retries: {url}")
