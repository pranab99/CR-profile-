# Ladder Log — Clash Royale battle analytics

A self-updating Clash Royale ladder dashboard: a GitHub Action pulls your
battle log every 30 minutes into a SQLite file committed to your repo, and
a single static HTML page (deployed on Vercel) loads that file straight
from GitHub and renders win rate, trophy trend, deck performance, and more
— entirely client-side, no backend.

## 1. Get a Clash Royale API key

1. Go to https://developer.clashroyale.com and sign in / register.
2. Create a new API key.
3. **Allowed IP address:** enter `45.79.218.79`.
   GitHub Actions runners don't have static IPs, so the logger calls
   `https://proxy.royaleapi.dev` instead of the API directly. RoyaleAPI's
   proxy forwards the request from `45.79.218.79`, so that exact IP must be
   whitelisted on the key.
4. Copy the key (a long JWT string) — this is your `CR_BEARER_TOKEN`.
5. Your player tag (e.g. `#2Y8V0PJGV`) is your `CR_PLAYER_TAG`. Find it in-game
   under your profile.

## 2. Create the GitHub repo

1. Create a new **public** repo (raw.githubusercontent.com only serves public
   repos for free, unbounded requests).
2. Push everything in this folder to it:
   ```
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```
3. In the repo, go to **Settings → Secrets and variables → Actions** and add:
   - `CR_PLAYER_TAG` — your player tag, including the `#`
   - `CR_BEARER_TOKEN` — your API key

4. Go to the **Actions** tab and manually run "Update Clash Royale ladder DB"
   once (workflow_dispatch) to create `clash_royale_ladder.db` for the first
   time. After that it runs automatically every 30 minutes and commits new
   battles as they happen.

## 3. Point the dashboard at your repo

Open `index.html` and edit the top of the `<script>` block:

```js
const DEFAULT_OWNER = "your-github-username";
const DEFAULT_REPO  = "your-repo-name";
const DEFAULT_BRANCH = "main";
```

(Or skip this — if you leave the placeholder, the page will show a small
form on first load asking for owner/repo/branch and remember it in your
browser.)

## 4. Deploy to Vercel

```
npm i -g vercel   # if you don't have it
vercel
```

Or connect the GitHub repo at https://vercel.com/new — it's a static site
(`vercel.json` disables the build step), so no framework setup is needed.
Every time you push, Vercel redeploys; the dashboard itself always fetches
the *latest* `.db` from `main` at page load, so you don't even need to
redeploy for new battle data to show up.

## What's in the box

| File | Purpose |
|---|---|
| `clash_logger.py` | Fetches your last ~25 battles from the CR API, collecting all Trophy Road / Ladder battles plus any battles with rival **King007** (`#YJPUJ9PU`) across all modes (Friendly, Ladder, 2v2), appending new ones to `clash_royale_ladder.db` (dedupes on player+battleTime) |
| `.github/workflows/static.yml` | Runs the logger every 30 min and commits the updated DB |
| `index.html` | The dashboard — loads the DB with sql.js (SQLite compiled to WASM) directly in the browser, featuring ladder analytics and a dedicated King007 Head-to-Head section |
| `vercel.json` | Tells Vercel this is a static site, no build step |

## Calculations the dashboard shows

### Ladder / Trophy Road Dashboard
- Win rate, W/L/D record, current and best win streak (range-filterable: 7D/30D/90D/all)
- Trophy trend over time
- Performance index (Form score, consistency, tilt risk, best play hours)
- Average crown differential, average elixir leaked, net trophy change, average king tower HP held, close-game win rate
- Deck win rate and matchup radar
- Games-by-hour-of-day heatmap
- Scrollable recent battle log filtered to Ladder / Trophy Road matches

### Head-to-Head Rivalry: King007 (`#YJPUJ9PU`)
- All-time and range-filtered head-to-head match analytics
- Win rate %, W/L/D record, and active win/loss streak against King007
- Total crowns scored vs crowns conceded & average crown differential
- Most played battle type breakdown (Friendly, Ladder, 2v2, etc.)
- Deck matchup breakdown: your most used decks vs King007's most used decks
- Full match history with mode badges, date, crown scores, and deck card lists

## Rival Target Configuration

By default, the logger and dashboard track `#YJPUJ9PU` alias `King007`. You can optionally customize this via GitHub Action secrets / environment variables in `clash_logger.py`:
- `TARGET_PLAYER_TAG` (default: `#YJPUJ9PU`)
- `TARGET_PLAYER_ALIAS` (default: `King007`)

## Notes

- The battle log API only returns your **last ~25 games** per call — history
  accumulates over time because the Action runs regularly and stores rows
  in the DB, so the longer this runs, the richer the analysis gets.
- Everything in `index.html` computes client-side from the raw rows, so it's
  easy to add your own stats — look for the `render...()` functions near
  the bottom of the file.
