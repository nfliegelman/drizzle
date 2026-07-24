# The 2026-07-16 rules change: what happened, what it cost, what to do next

Written 2026-07-24, after the boards had been dark for nine days.

## Summary

Kalshi changed the daily rain market in two ways on 2026-07-16. One broke the
bot mechanically. The other deleted its edge. The mechanical break is fixed.
The edge is gone and has not been replaced, so the bot is in research mode and
sizes no plays.

## 1. What broke mechanically

The per-city series (`KXRAINNYC`, `KXRAINSEA`, ...) were retired. They still
exist in the catalog but have carried no open event since 2026-07-15. Every
city moved into ONE consolidated series, `KXRAIN`, with one market per city per
event:

```
old:  KXRAINNYC-26JUL15-T0        one series per city, one market per event
new:  KXRAIN-26JUL24-NYC          one series, 20 city markets per event
```

The bot kept polling the dead series, correctly refused to publish a board it
could not source, and exited 2. Every scheduled run from 2026-07-16 onward
failed. The failure was accurate; it just had no reader.

Two other things moved at the same time and are easy to miss:

- **Settlement stations changed for two cities.** Chicago now settles on
  O'Hare (`CLIORD`), not Midway. Houston settles on Bush Intercontinental
  (`CLIIAH`), not Hobby. The bot had both wrong after the migration and was
  forecasting the wrong airport until this was fixed.
- **`KXRAIN` lists irregularly.** 2026-07-16 and 07-18 through 07-21 were
  never listed at all (`/events/KXRAIN-26JUL18` 404s). "No open event" is
  therefore a normal day, not a failure, and must not be a red run.

## 2. What broke strategically

The old rules text said an Expiration Value of `T` (Trace) or `R` (Record)
resolves YES. The new text says:

> "Trace" amounts (T) and missing daily precipitation values are counted as 0
> inches.

The payout criterion is still "strictly greater than 0 inches", so **a trace
day now settles NO.** The settlement source also moved from the NWS CLI report
to The Weather Company feed at `weather.com/kalshi`.

The entire Phase 1 thesis was that trace days settle YES and no grid ensemble
prices them. That thesis is dead.

### Verified, not assumed

Held to the same standard the original thesis was (60 joined days of
settlements):

- Across the 60 settled market-days of `KXRAIN` (3 event days x 20 cities),
  Kalshi's own results agree with the new rule **40/40** wherever GHCN gauge
  data was joinable.
- **All three trace days found settled NO**: AUS, HOU and MIN on 2026-07-17,
  each with GHCN measurement flag `T`. Under the old rule all three would have
  been YES.

### What it cost

Trace days, as a share of all days (GHCN-Daily, 10-year window 2016-2025):

| Station | P(measurable) = new YES | P(trace) = YES mass removed |
|---|---|---|
| Chicago O'Hare | 34.96% | **14.92pp** |
| Austin | 21.98% | 14.10pp |
| Denver | 20.91% | 13.96pp |
| Miami | 39.36% | 13.22pp |
| Washington DCA | 33.00% | 13.12pp |
| Boston | 35.59% | 12.18pp |
| Houston | 29.85% | 12.08pp |
| Philadelphia | 33.94% | 11.83pp |
| Atlanta | 31.95% | 11.25pp |
| NYC Central Park | 35.61% | 9.58pp |
| Dallas | 23.22% | 9.61pp |
| Seattle | 42.50% | 8.83pp |
| LAX | 9.66% | 5.31pp |
| Phoenix | 8.65% | 4.85pp |
| San Francisco | 16.56% | 4.27pp |

Median 11.83pp. The relative bite is worst in semi-arid cities: Denver loses
**40%** of its YES mass, Austin 39%, Phoenix 36%.

Seasonality is not the obvious story. Chicago's trace rate peaks in **January
(25.16%)** and bottoms in September (8.67%). NYC runs the **opposite** way,
peaking in **June (12.67%)** and bottoming in December (5.81%) on summer
convective sprinkles clipping the park. A winter-trace heuristic would be
backwards in NYC.

## 3. The model was calibrated to the dead rule

`T_STAR_MM = 0.1` (~0.004in) sits deliberately below the 0.01in gauge floor, so
"member > T_STAR" meant "trace or more" -- precisely the old settlement event.
Backtested over 2,387 city-days (6 cities, 2025-06-19 to 2026-07-21, as-issued
lead-1 forecasts):

| Scored against | mean p_raw | observed | bias |
|---|---|---|---|
| OLD rule (trace counts) | 0.4229 | 0.4072 | **+0.0157** |
| NEW rule (measurable only) | 0.4229 | 0.2895 | **+0.1335** |

The model was well calibrated to the question Kalshi stopped asking, and is
badly biased on the one it now asks. It over-forecasts in every reliability
bucket above 0.1 and in all 6 cities.

Sharpest in the drizzle regime the old edge lived in, `0.1 <= p_raw < 0.5`
(n=572): predicted **0.239**, observed **0.075** -- over-forecast by **3.2x**.
Old-rule observed in that same slice is 0.236, essentially equal to the
forecast.

**Fix applied:** `T_STAR_MM` 0.1 -> **1.0**, which minimises Brier (0.0919 vs
0.1228) and nearly zeroes the bias (+0.0112). 0.254mm is the definitional
value (the gauge floor); 1.0mm is the empirical one, and the extra headroom
absorbs the fact that a grid cell is an areal average that over-produces light
precip against a point gauge.

**Discrimination was never the problem: AUC 0.9344.** This is a calibration
failure, not a broken model. Do not discard it.

### Limits of that backtest

- **The ensemble is a proxy.** Open-Meteo retains only ~3 days of past
  ensemble members, so a true 143-member EPS backtest is impossible; the study
  used 4-9 deterministic models. Direction is not in doubt (same sign in all 6
  cities, stable across halves: +0.1341 / +0.1328). The exact magnitude is.
- **Lead time is real, not a proxy**: as-issued lead-1 archived runs,
  empirically distinguished from latest-run hindcast (77.7% hour agreement;
  438.0mm vs 347.4mm over 120 days).
- **Grid-vs-point mismatch is inside the measured bias.** Miami's +0.238 is
  largely this, and it is the single biggest contributor to the pooled number.
  Read +0.134 as "grid forecast vs point gauge", which is the operationally
  relevant comparison but is not proof of a thermodynamic wet bias.
- **Effective sample is much smaller than 2,387**: only 398 independent days,
  and the cities are correlated on synoptic timescales. All CIs are optimistic.

## 4. Is there a new edge? Not established.

The backtest establishes **model bias, not market mispricing**. There are no
usable market prices behind it, and the obvious null hypothesis is live: if the
market anchors to **NWS PoP**, which is already defined as P(>=0.01in) and
therefore already matches the new rule, there may be **no edge at all**.

A second problem is visible on the live board: on 2026-07-25, six of twenty
cities showed a mid of exactly **0.44**, which is what an empty book produces
(`yb=0.01, ya=0.87`). **Mid is not a market probability on these markets yet.**
Open interest is frequently 12-200 against a `MIN_OI` of 300. Any edge
measurement that reads `mid` as the market's belief will be measuring the
spread, not the market.

### What would actually settle the question

1. Log new-rule settlements until there are enough to calibrate on **live
   ensemble** data rather than a deterministic proxy. Research mode is doing
   this now; the full threshold curve is logged every run so `T_STAR` can be
   revised without a backfill.
2. Capture **closing prices** per market-day, so bias can be scored against
   what was actually tradeable instead of against a wide mid.
3. Compare the model against **NBM PoP** specifically. If PoP already prices
   the new rule correctly, the honest conclusion is that this market has no
   edge left and the project is finished. That is an acceptable answer.

Until then: **no plays.** The bot publishes, logs and measures.
