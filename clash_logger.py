"""
clash_logger.py

Pulls the last ~25 ladder battles from the Clash Royale API (via the
RoyaleAPI proxy, which is required for calls made from GitHub Actions
since runner IPs aren't static and can't be whitelisted on your API key)
and appends any battles not already in clash_royale_ladder.db.

Run on a schedule (see .github/workflows/update-db.yml) so the battle
log accumulates over time instead of only holding the last 25 games.

Env vars required:
  CR_PLAYER_TAG    e.g. "#2Y8V0PJGV" (URL-encoding of '#' is handled here)
  CR_BEARER_TOKEN  API key generated at developer.clashroyale.com,
                    with no IP restriction (proxy IPs are dynamic)
"""

import json
import os
import sqlite3
from datetime import datetime

import requests

PLAYER_TAG_RAW = os.getenv("CR_PLAYER_TAG", "")
BEARER_TOKEN = os.getenv("eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiIsImtpZCI6IjI4YTMxOGY3LTAwMDAtYTFlYi03ZmExLTJjNzQzM2M2Y2NhNSJ9.eyJpc3MiOiJzdXBlcmNlbGwiLCJhdWQiOiJzdXBlcmNlbGw6Z2FtZWFwaSIsImp0aSI6ImYxMDU5MmI1LWRmM2EtNDFhYi05ZTk4LTYyZjkxZWYwNTQ1YSIsImlhdCI6MTc4ODI4MzExOCwic3ViIjoiZGV2ZWxvcGVyL2VhOGYwYjY3LTExYWMtNDRmMi1iN2VmLTBlY2U3ZjA2M2RkYyIsInNjb3BlcyI6WyJyb3lhbGUiXSwibGltaXRzIjpbeyJ0aWVyIjoiZGV2ZWxvcGVyL3NpbHZlciIsInR5cGUiOiJ0aHJvdHRsaW5nIn0seyJjaWRycyI6WyIwLjAuMC4wIl0sInR5cGUiOiJjbGllbnQifV19.pHs4ZusffwM_4TQBSKSqhR1_1YsLhYEV7mVOeF-1TimEX-4TvDspRKRZezsb4eUrwVywX3INjSd3A2VuMkaZDg 

this is my JWT for clash royale")
PLAYER_TAG_URL = PLAYER_TAG_RAW.replace("#", "%23")
DB_PATH = "clash_royale_ladder.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS ladder_battles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_tag TEXT NOT NULL,
    battleTime TEXT NOT NULL,
    gameMode TEXT,
    result TEXT,
    trophyChange INTEGER,
    currentTrophies INTEGER,
    deck TEXT,
    crowns INTEGER,
    elixirLeaked REAL,
    kingTowerHP INTEGER,
    princessTowersHP TEXT,
    opponent_tag TEXT,
    opponent_name TEXT,
    opponent_deck TEXT,
    opponent_crowns INTEGER,
    opponent_kingTowerHP INTEGER,
    opponent_princessTowersHP TEXT,
    UNIQUE(player_tag, battleTime)
)
"""


def init_database():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(SCHEMA)
    conn.commit()
    conn.close()


def format_deck(cards):
    if not cards:
        return ""
    return " | ".join(sorted(card["name"] for card in cards))


def fetch_and_process_battles():
    api_url = f"https://proxy.royaleapi.dev/v1/players/{PLAYER_TAG_URL}/battlelog"
    headers = {"Authorization": f"Bearer {BEARER_TOKEN}"}
    print(f"[{datetime.now()}] Fetching battle log for {PLAYER_TAG_RAW}...")

    response = requests.get(api_url, headers=headers, timeout=30)
    response.raise_for_status()
    battles = response.json()

    processed = []
    for battle in battles:
        mode = battle.get("gameMode", {}).get("name", "")
        # Ladder + the modern ranked ladder mode name Supercell uses now
        if mode not in ("Ladder", "Ladder_CrownRush", "Ranked1v1"):
            continue

        player = battle["team"][0]
        opponent = battle["opponent"][0] if battle.get("opponent") else {}

        trophy_change = player.get("trophyChange", 0)
        if trophy_change > 0:
            result = "Win"
        elif trophy_change < 0:
            result = "Loss"
        else:
            result = "Draw"

        current_trophies = player.get("startingTrophies", 0) + trophy_change

        row = (
            battle.get("battleTime"),
            mode,
            result,
            trophy_change,
            current_trophies,
            format_deck(player.get("cards")),
            player.get("crowns", 0),
            player.get("elixirLeaked"),
            player.get("kingTowerHitPoints"),
            json.dumps(player.get("princessTowersHitPoints", [])),
            opponent.get("tag"),
            opponent.get("name"),
            format_deck(opponent.get("cards")),
            opponent.get("crowns", 0),
            opponent.get("kingTowerHitPoints"),
            json.dumps(opponent.get("princessTowersHitPoints", [])),
        )
        processed.append(row)

    print(f"Found {len(processed)} ladder battles in this fetch.")
    return processed


def save_to_sqlite(rows):
    if not rows:
        print("No battles fetched, nothing to save.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    new_rows = 0
    for row in rows:
        try:
            cursor.execute(
                """
                INSERT OR IGNORE INTO ladder_battles
                (player_tag, battleTime, gameMode, result, trophyChange, currentTrophies,
                 deck, crowns, elixirLeaked, kingTowerHP, princessTowersHP,
                 opponent_tag, opponent_name, opponent_deck, opponent_crowns,
                 opponent_kingTowerHP, opponent_princessTowersHP)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (PLAYER_TAG_RAW, *row),
            )
            new_rows += cursor.rowcount
        except sqlite3.Error as e:
            print(f"DB error on row: {e}")

    conn.commit()
    conn.close()
    print(f"Saved {new_rows} new row(s)." if new_rows else "No new unique battles.")


if __name__ == "__main__":
    if not PLAYER_TAG_RAW or not BEARER_TOKEN:
        raise SystemExit("CR_PLAYER_TAG or CR_BEARER_TOKEN environment variables are not set.")

    init_database()
    battles = fetch_and_process_battles()
    battles.reverse()  # oldest-first so autoincrement ids stay chronological
    save_to_sqlite(battles)
    print("--- Done ---")
