# Drizzle

Sibling of [Nimbus](https://github.com/nfliegelman/nimbus), same constitution, new market: **Kalshi daily rain**. One binary market per city per day ("will it rain in NYC?"). Runs itself on GitHub three times a day; you just open two web pages on your phone.

> ## ⚠️ The original thesis is dead (2026-07-16)
>
> **The thesis used to be:** Kalshi's rain markets settle YES on ANY recorded precipitation, including Trace. Weather models call a drizzle-mist-trace day zero; the gauge does not. Drizzle priced that gap.
>
> **What changed:** Kalshi retired the per-city series (`KXRAINNYC`, …) and consolidated every city into one series, `KXRAIN`, with one market per city per event (`KXRAIN-26JUL24-NYC`). The new rules text inverts the settlement rule the edge rested on:
>
> > "Trace amounts (T) and missing daily precipitation values are **counted as 0 inches**."
>
> The payout criterion is still "strictly greater than 0 inches", so **a trace day now settles NO.** It used to settle YES. The settlement source also moved from the NWS CLI report to The Weather Company feed (`weather.com/kalshi`).
>
> **Verified, not assumed** — held to the same standard as the original thesis: across 60 settled market-days of the new series, Kalshi's own results agree with the new rule 40/40 wherever gauge data was joinable, and all three trace days found (AUS, HOU, MIN on 2026-07-17, GHCN measurement flag `T`) settled **NO**.
>
> **Size of the loss:** trace days are 4.3%–14.9% of all days depending on the city (10-year GHCN base rates; median 11.8pp). That is the entire block of probability the old model was paid for, and it is gone.
>
> **Consequence:** the trace floor is switched off, and the bot is in **research mode** — it publishes boards and logs every prediction so calibration rebuilds under the new rules, but **sizes no plays**. Re-enabling trading is a decision to make from the new calibration, not from the old thesis.

## What you get
- **Today's board** (`index.html`): the model vs the market for every open city. While research mode is on, this is measurement only and no plays are sized; the page says so at the top.
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
Three runs daily, minutes deliberately off the hour (GitHub delays :00 crons the most): ~7:17 AM Dallas (morning board + settle yesterday), ~4:38 PM (capture run: tomorrow's market listed at 14:00 UTC and the full 12z model cycle is in), ~9:07 PM (evening board, 18z GFS in, and the OI that was too thin at listing has usually built). A 21-test suite runs before every board and blocks publishing on failure.

Note: `KXRAIN` lists **irregularly** — 2026-07-16 and 07-18 through 07-21 were never listed at all (the event 404s). A run that finds no open event publishes an explicitly empty board instead of failing, because "Kalshi listed nothing" is not the same as "we could not see".

## Honesty features (inherited from the Nimbus audit, on from day one)
- **Frozen plays:** the tracker forever scores the first board that showed each play.
- **Quarantine, not deletion:** a city failing a data or structure check is sat out, named in the header, and still logged so the exclusion can be judged against the settlement later.
- **Divergence guard:** until a city has 15 settlements, a model-vs-market gap over 35 points is treated as our miscalibration, not their error. No play, logged and reconstructible.
- **Exposure caps:** at most 4 units per day, 1.5 per market, counted cumulatively across runs.
- **Loud failures:** a broken fetch is a red run that publishes nothing; the stale-board banner flags any page older than 16 hours. Do not bet from a flagged board.
- **Rules re-read every run:** the settlement regime is verified from the live rules text on every market, every run. A city whose rules stop saying trace counts as zero is quarantined by name ("trace rule changed") rather than traded, because that would mean the regime moved again. The 2026-07-16 change was caught the expensive way — by nine days of red runs — and this check is what makes the next one cheap.
- **Era separation:** settlements are pooled by `model_version`. Old-rule (trace=YES) days are never mixed with new-rule (trace=NO) days, so no calibration number silently spans the regime change.

## Honest use
**Do not bet this right now.** The edge it was built to harvest no longer exists, and nothing has replaced it yet. Research mode logs predictions under the new rules so a real calibration can accumulate; the question to answer from that data is whether the ensemble is biased against *measurable* rain (which would be a NO-side edge), not whether it misses trace.

Old advice still stands for whatever comes next: paper trade until the Results tab shows the model Brier below the market Brier and green P&L over a real sample, keeping in mind the pre-2026-07-16 record was earned under different rules and does not transfer.

## Your data is safe when the code changes
All results live in `drizzle_state.json`, never included in code handbacks. The workflow commits it back after every run; git history is the backup. Never delete it.
