# Drizzle

Sibling of [Nimbus](https://github.com/nfliegelman/nimbus), same constitution, new market: **Kalshi daily rain**. One binary market per city per day ("will it rain in NYC?"), settled by the official NWS climate report. Runs itself on GitHub three times a day; you just open two web pages on your phone.

**The thesis in one line:** Kalshi's rain markets settle YES on ANY recorded precipitation, including Trace (proven empirically on 60 days of settlements, and stated in the rules text). Weather models forecast rain amounts; they call a drizzle-mist-trace day zero. The gauge does not. Drizzle prices that gap.

## What you get
- **Today's plays** (`index.html`): each play sized 1.5u / 1u / no bet, with the full board underneath showing the model vs the market for every open city, including the raw ensemble probability and the trace-floored one, so you can see the thesis working (or not) on every line.
- **Results tracker** (`results.html`): win/loss and P&L in units, Brier vs market, a Wilson-barred calibration table, per-city trace-day counts, a forecast-sources scoreboard (pooled model vs raw model vs NBM vs the market), CLV, honesty tiles, and a raw settlement table. Wins come from Kalshi's official settlement, never a guess.

## One-time setup (about 5 minutes)
1. Create a new GitHub repo (public is fine for the paper phase) and upload every file in this folder keeping the structure (`drizzle.py`, `.github/workflows/run.yml`, `test_drizzle.py`, the .md files).
2. Repo Settings -> Pages: Source = Deploy from a branch, Branch = `main`, folder = `/docs`. Save.
3. Repo Settings -> Actions -> General: Workflow permissions = Read and write. Save.
4. Actions tab -> drizzle -> Run workflow for the first run.
5. Optional phone pings: add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` repo secrets (same bot as Nimbus works). Leave absent and the notifier is a silent no-op.
6. Edit `DRIZZLE_PAGE_URL` in `run.yml` to your Pages URL.

Pages: `https://<you>.github.io/<repo>/` and `.../results.html`. Add both to your iPhone home screen.

## Schedule
Three runs daily, minutes deliberately off the hour (GitHub delays :00 crons the most): ~7:17 AM Dallas (morning board + settle yesterday), ~4:38 PM (capture run: tomorrow's market listed at 14:00 UTC and the full 12z model cycle is in), ~9:07 PM (evening board, 18z GFS in, and the OI that was too thin at listing has usually built). A 14-test suite runs before every board and blocks publishing on failure.

## Honesty features (inherited from the Nimbus audit, on from day one)
- **Frozen plays:** the tracker forever scores the first board that showed each play.
- **Quarantine, not deletion:** a city failing a data or structure check is sat out, named in the header, and still logged so the exclusion can be judged against the settlement later.
- **Divergence guard:** until a city has 15 settlements, a model-vs-market gap over 35 points is treated as our miscalibration, not their error. No play, logged and reconstructible.
- **Exposure caps:** at most 4 units per day, 1.5 per market, counted cumulatively across runs.
- **Loud failures:** a broken fetch is a red run that publishes nothing; the stale-board banner flags any page older than 16 hours. Do not bet from a flagged board.

## Honest use
Paper trade until the Results tab shows the model Brier below the market Brier and green P&L over a real sample. NYC is currently the only live rain city (~1 settlement/day), so the calibration gates take about a month. That is the plan, not a problem.

## Your data is safe when the code changes
All results live in `drizzle_state.json`, never included in code handbacks. The workflow commits it back after every run; git history is the backup. Never delete it.
