# Ladder Log — Clash Royale battle analytics

A self-updating Clash Royale ladder dashboard: a GitHub Action pulls your
battle log every 30 minutes into a SQLite file committed to your repo, and
a single static HTML page (deployed on Vercel) loads that file straight
from GitHub and renders win rate, trophy trend, deck performance, and more
— entirely client-side, no backend.

## 1. Get a Clash Royale API key

1. Go to https://developer.clashroyale.com and sign in / register.
2. Create a new API key.
3. **IP address:** leave this key with **no IP restriction** (or a wide-open one).
   GitHub Actions runners don't have static IPs, so a locked-down key won't
   work — that's why the logger calls `https://proxy.royaleapi.dev` instead
   of the API directly. The proxy forwards your key from a fixed IP range
   that's pre-whitelisted by Supercell.
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
| `clash_logger.py` | Fetches your last ~25 ladder battles from the CR API, appends new ones to `clash_royale_ladder.db` (dedupes on player+battleTime) |
| `.github/workflows/update-db.yml` | Runs the logger every 30 min and commits the updated DB |
| `index.html` | The dashboard — loads the DB with sql.js (SQLite compiled to WASM) directly in the browser |
| `vercel.json` | Tells Vercel this is a static site, no build step |

## Calculations the dashboard shows

- Win rate, W/L/D record, current and best win streak (range-filterable: 7D/30D/90D/all)
- Trophy trend over time
- Average crown differential, average elixir leaked, net trophy change, average king tower HP held
- Deck win rate (grouped by exact 8-card deck, min. 3 games)
- Most-faced opponent cards
- Games-by-hour-of-day heatmap
- Scrollable recent battle log

## Notes

- The battle log API only returns your **last ~25 games** per call — history
  accumulates over time because the Action runs regularly and stores rows
  in the DB, so the longer this runs, the richer the analysis gets.
- Everything in `index.html` computes client-side from the raw rows, so it's
  easy to add your own stats — look for the `render...()` functions near
  the bottom of the file.
