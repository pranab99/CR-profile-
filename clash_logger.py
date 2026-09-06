"""
clash_logger.py

Pulls the last ~25 ladder battles from the Clash Royale API (via the
RoyaleAPI proxy, which is required for calls made from GitHub Actions
since runner IPs aren't static and can't be whitelisted on your API key)
and appends any battles not already in clash_royale_ladder.db.

Run on a schedule (see .github/workflows/static.yml) so the battle
log accumulates over time instead of only holding the last 25 games.

Env vars required:
  CR_PLAYER_TAG    e.g. "#2Y8V0PJGV" (URL-encoding of '#' is handled here)
  CR_BEARER_TOKEN  API key generated at developer.clashroyale.com,
                    with 45.79.218.79 whitelisted when using RoyaleAPI proxy
"""

import json
import os
import sqlite3
from datetime import datetime
from urllib.parse import quote

import requests

PLAYER_TAG_RAW = os.environ.get("CR_PLAYER_TAG", "#8LCULCYUP").strip()
BEARER_TOKEN = os.environ.get("CR_BEARER_TOKEN", "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiIsImtpZCI6IjI4YTMxOGY3LTAwMDAtYTFlYi03ZmExLTJjNzQzM2M2Y2NhNSJ9.eyJpc3MiOiJzdXBlcmNlbGwiLCJhdWQiOiJzdXBlcmNlbGw6Z2FtZWFwaSIsImp0aSI6ImU0NjE4OTQ0LWM1MjktNGU4Zi1iMWY2LWRiMWMxZjczYTBiOSIsImlhdCI6MTc4ODcxODIwMywic3ViIjoiZGV2ZWxvcGVyL2VhOGYwYjY3LTExYWMtNDRmMi1iN2VmLTBlY2U3ZjA2M2RkYyIsInNjb3BlcyI6WyJyb3lhbGUiXSwibGltaXRzIjpbeyJ0aWVyIjoiZGV2ZWxvcGVyL3NpbHZlciIsInR5cGUiOiJ0aHJvdHRsaW5nIn0seyJjaWRycyI6WyI0NS43OS4yMTguNzkiLCIwLjAuMC4wIl0sInR5cGUiOiJjbGllbnQifV19.Xtc4e0GN3sVk1Z1PfReRKDIXLt92ReSHle2_1L5gS3qYcELt9Co2uoc70t6i7ZC2uiJ9esmz1bOZhN6EjZqs_A").strip()
API_BASE_URL = os.environ.get("CR_API_BASE_URL", "https://proxy.royaleapi.dev/v1").rstrip("/")
# PLAYER_TAG_URL = quote(PLAYER_TAG_RAW, safe="")
DB_PATH = "clash_royale_ladder.db"

PLAYER_TAG_URL = PLAYER_TAG_RAW.replace('#', '%23')
TARGET_PLAYER_TAG = os.environ.get("TARGET_PLAYER_TAG", "#YJPUJ9PU").strip()
TARGET_PLAYER_ALIAS = os.environ.get("TARGET_PLAYER_ALIAS", "King007").strip()

print(f"[DEBUG] PLAYER_TAG_RAW = {PLAYER_TAG_RAW!r}")
print(f"[DEBUG] PLAYER_TAG_URL (encoded) = {PLAYER_TAG_URL!r}")
print(f"[DEBUG] TARGET_PLAYER_TAG = {TARGET_PLAYER_TAG!r}")
print(f"[DEBUG] TARGET_PLAYER_ALIAS = {TARGET_PLAYER_ALIAS!r}")
print(f"[DEBUG] BEARER_TOKEN set = {bool(BEARER_TOKEN)} (len={len(BEARER_TOKEN)})")
print(f"[DEBUG] API_BASE_URL = {API_BASE_URL!r}")
print(f"[DEBUG] DB_PATH = {DB_PATH!r}")


def normalize_tag(tag):
    if not tag:
        return ""
    return tag.lstrip("#").upper()


def is_target_player(player_data):
    if not player_data:
        return False
    tag = normalize_tag(player_data.get("tag", ""))
    target_tag = normalize_tag(TARGET_PLAYER_TAG)
    name = (player_data.get("name") or "").strip().lower()
    target_name = TARGET_PLAYER_ALIAS.strip().lower()
    return (bool(target_tag) and tag == target_tag) or (bool(target_name) and name == target_name)


def is_target_battle(battle):
    for opp in battle.get("opponent", []):
        if is_target_player(opp):
            return True
    for tm in battle.get("team", []):
        if is_target_player(tm):
            return True
    return False

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

SCHEMA_MIGRATIONS = {
    "gameMode": "ALTER TABLE ladder_battles ADD COLUMN gameMode TEXT",
    "opponent_crowns": "ALTER TABLE ladder_battles ADD COLUMN opponent_crowns INTEGER",
}


def init_database():
    print(f"[DEBUG] init_database() called")
    conn = sqlite3.connect(DB_PATH)
    print(f"[DEBUG] Connected to DB at {DB_PATH}")
    conn.execute(SCHEMA)
    print(f"[DEBUG] Ensured ladder_battles table exists")
    existing_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(ladder_battles)").fetchall()
    }
    print(f"[DEBUG] Existing columns: {sorted(existing_columns)}")
    for column, statement in SCHEMA_MIGRATIONS.items():
        if column not in existing_columns:
            print(f"[DEBUG] Column '{column}' missing, running migration: {statement}")
            conn.execute(statement)
        else:
            print(f"[DEBUG] Column '{column}' already present, skipping migration")
    conn.commit()
    conn.close()
    print(f"[DEBUG] init_database() complete, connection closed")


def format_deck(cards):
    print(f"[DEBUG] format_deck() called with {len(cards) if cards else 0} cards")
    if not cards:
        print(f"[DEBUG] No cards provided, returning empty string")
        return ""
    deck_str = " | ".join(sorted(card["name"] for card in cards))
    print(f"[DEBUG] Formatted deck: {deck_str}")
    return deck_str


def fetch_and_process_battles():
    print(f"[DEBUG] fetch_and_process_battles() called")
    api_url = f"{API_BASE_URL}/players/{PLAYER_TAG_URL}/battlelog"
    headers = {"Accept": "application/json", "Authorization": f"Bearer {BEARER_TOKEN}"}
    print(f"[DEBUG] Request URL: {api_url}")
    print(f"[DEBUG] Request headers: {{'Accept': 'application/json', 'Authorization': 'Bearer ***'}}")
    print(f"[{datetime.now()}] Fetching battle log for {PLAYER_TAG_RAW}...")

    response = requests.get(api_url, headers=headers, timeout=30)
    print(f"[DEBUG] Response status code: {response.status_code}")
    print(f"[DEBUG] Response headers: {dict(response.headers)}")
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text[:500].strip()
        print(f"[DEBUG] HTTPError caught: {exc}")
        print(f"[DEBUG] Response body (first 500 chars): {detail}")
        if response.status_code == 403 and "proxy.royaleapi.dev" in API_BASE_URL:
            detail = (
                f"{detail}\n\n"
                "403 from RoyaleAPI proxy usually means the Clash Royale API key "
                "does not whitelist the proxy IP. Create a new key at "
                "developer.clashroyale.com with allowed IP 45.79.218.79, then "
                "save that token as the CR_BEARER_TOKEN GitHub Actions secret."
            )
            print(f"[DEBUG] Detected 403 from RoyaleAPI proxy, appending IP whitelist hint")
        raise RuntimeError(f"Clash Royale API request failed: {exc}\n{detail}") from exc

    battles = response.json()
    print(f"[DEBUG] Raw battles fetched from API: {len(battles)}")

    processed = []
    for i, battle in enumerate(battles):
        mode = battle.get("gameMode", {}).get("name", "")
        if not mode:
            mode = battle.get("type", "Unknown")

        is_ladder = mode in ("Ladder", "Ladder_CrownRush", "Ranked1v1")
        is_target = is_target_battle(battle)
        print(f"[DEBUG] Battle {i}: battleTime={battle.get('battleTime')}, gameMode={mode}, is_ladder={is_ladder}, is_target={is_target}")

        # Collect ladder / trophy road battles, and ANY battle played with King007 irrespective of battle type
        if not (is_ladder or is_target):
            print(f"[DEBUG] Battle {i}: skipped (mode '{mode}' not ladder and rival {TARGET_PLAYER_ALIAS} not involved)")
            continue

        player = battle["team"][0] if battle.get("team") else {}

        # Prioritize target rival if present in opponent list (e.g. 1v1 or 2v2)
        opponents = battle.get("opponent", [])
        opponent = {}
        for opp in opponents:
            if is_target_player(opp):
                opponent = opp
                break
        if not opponent and opponents:
            opponent = opponents[0]
        elif not opponent:
            # Check team list for target rival (e.g. 2v2 partner/rival)
            for tm in battle.get("team", []):
                if is_target_player(tm):
                    opponent = tm
                    break

        print(f"[DEBUG] Battle {i}: player={player.get('name')}, opponent={opponent.get('name')} ({opponent.get('tag')})")

        trophy_change = player.get("trophyChange") if is_ladder else 0
        player_crowns = player.get("crowns", 0)
        opp_crowns = opponent.get("crowns", 0)

        # In non-ladder (friendly/party/challenge), trophyChange is absent or 0.
        # Fall back to crowns and tower HP for accurate Win/Loss determination.
        if trophy_change is not None and trophy_change > 0:
            result = "Win"
        elif trophy_change is not None and trophy_change < 0:
            result = "Loss"
        elif player_crowns > opp_crowns:
            result = "Win"
        elif player_crowns < opp_crowns:
            result = "Loss"
        else:
            player_king = player.get("kingTowerHP") if "kingTowerHP" in player else player.get("kingTowerHitPoints") or 0
            opp_king = opponent.get("kingTowerHP") if "kingTowerHP" in opponent else opponent.get("kingTowerHitPoints") or 0
            if player_king > opp_king:
                result = "Win"
            elif player_king < opp_king:
                result = "Loss"
            else:
                result = "Draw"
        print(f"[DEBUG] Battle {i}: trophyChange={trophy_change}, player_crowns={player_crowns}, opp_crowns={opp_crowns}, result={result}")

        # Set current_trophies to None for non-ladder matches to prevent distorting trophy charts
        if is_ladder:
            starting_trophies = player.get("startingTrophies")
            if starting_trophies is not None and trophy_change is not None:
                current_trophies = starting_trophies + trophy_change
            elif starting_trophies is not None:
                current_trophies = starting_trophies
            else:
                current_trophies = None
        else:
            current_trophies = None
        print(f"[DEBUG] Battle {i}: is_ladder={is_ladder}, startingTrophies={player.get('startingTrophies')}, currentTrophies={current_trophies}")

        row = (
            battle.get("battleTime"),
            mode,
            result,
            trophy_change if trophy_change is not None else 0,
            current_trophies,
            format_deck(player.get("cards")),
            player.get("crowns", 0),
            player.get("elixirLeaked"),
            player.get("kingTowerHP") if "kingTowerHP" in player else player.get("kingTowerHitPoints"),
            json.dumps(player.get("princessTowersHitPoints", [])),
            opponent.get("tag"),
            opponent.get("name"),
            format_deck(opponent.get("cards")),
            opponent.get("crowns", 0),
            opponent.get("kingTowerHP") if "kingTowerHP" in opponent else opponent.get("kingTowerHitPoints"),
            json.dumps(opponent.get("princessTowersHitPoints", [])),
        )
        print(f"[DEBUG] Battle {i}: row built = {row}")
        processed.append(row)

    print(f"Found {len(processed)} battles matching criteria in this fetch.")
    return processed


def save_to_sqlite(rows):
    print(f"[DEBUG] save_to_sqlite() called with {len(rows)} row(s)")
    if not rows:
        print("No battles fetched, nothing to save.")
        return

    conn = sqlite3.connect(DB_PATH)
    print(f"[DEBUG] Connected to DB at {DB_PATH} for writing")
    cursor = conn.cursor()
    new_rows = 0
    for i, row in enumerate(rows):
        print(f"[DEBUG] Inserting row {i}: battleTime={row[0]}, gameMode={row[1]}")
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
            print(f"[DEBUG] Row {i}: cursor.rowcount = {cursor.rowcount} (1 = inserted, 0 = duplicate ignored)")
            new_rows += cursor.rowcount
        except sqlite3.Error as e:
            print(f"DB error on row: {e}")
            print(f"[DEBUG] Row {i} that caused error: {row}")

    conn.commit()
    print(f"[DEBUG] Transaction committed")
    conn.close()
    print(f"[DEBUG] DB connection closed")
    print(f"Saved {new_rows} new row(s)." if new_rows else "No new unique battles.")


if __name__ == "__main__":
    print(f"[DEBUG] Script started at {datetime.now()}")
    if not PLAYER_TAG_RAW or not BEARER_TOKEN:
        print(f"[DEBUG] Missing required env vars — PLAYER_TAG_RAW set: {bool(PLAYER_TAG_RAW)}, BEARER_TOKEN set: {bool(BEARER_TOKEN)}")
        raise SystemExit("CR_PLAYER_TAG or CR_BEARER_TOKEN environment variables are not set.")

    init_database()
    battles = fetch_and_process_battles()
    print(f"[DEBUG] Reversing battle order (oldest-first) — count before reverse: {len(battles)}")
    battles.reverse()  # oldest-first so autoincrement ids stay chronological
    save_to_sqlite(battles)
    print("--- Done ---")