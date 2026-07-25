# Drizzle: Phase Roadmap and Future Inclusions

**Purpose:** the phased buildout plan with pre-registered activation gates, plus the running list of known weaknesses. When an item ships, move it to the HANDOFF.md changelog. Phases are ordered; do not skip ahead: each is gated on settled history that does not exist yet.

---

> ## ⚠️ SUPERSEDED BY THE 2026-07-16 RULES CHANGE
>
> Kalshi consolidated every city into the `KXRAIN` series and inverted the settlement rule: trace now counts as 0 inches and settles **NO**. The Phase 0 finding below is a true record of the OLD market and is kept as history — it is **no longer the rules in force**. Phases 1 and 2 as originally written assumed the trace edge and have been rewritten accordingly. Full evidence: [RULES_CHANGE.md](RULES_CHANGE.md).

## Phase 0: Rules and settlement recon (COMPLETE, 2026-07-06, re-verified 07-07 — **superseded 07-16**)

- [x] Settlement semantics proven empirically: 60 joined days, Trace 7/7 YES, dry 29/29 NO, zero mismatches. **(True of the retired per-city series. Reversed on 2026-07-16.)**
- [x] Corroborated in the live rules text: Expiration Value T or R resolves YES. **(The live text now says the opposite.)**
- [x] Fee structure verified (quadratic x1, same as Nimbus). Universe mapped (NYC live; SEA/MIA/legacy series dormant in catalog). Station verified for NYC (Central Park). API dollars-field generation discovered. **(Fees and the dollars-field finding still hold. The universe is now 20 cities in one series; Chicago moved to O'Hare and Houston to Bush Intercontinental.)**

## Phase 1: Paper engine, lead 1-2, fixed priors (SHIPPED 2026-07-07 — **thesis retired 2026-07-16**)

Ran 2026-07-07 to 07-15 and produced 8 settlements under the old rules. Those are a real record of a market that no longer exists; they are era-separated by `model_version` and must never be pooled with new-rule settlements.

## Phase 1R: Re-establish whether ANY edge exists (CURRENT, gate: nothing may trade until this answers)

The old edge is gone and nothing has replaced it. `RESEARCH_MODE` is on: boards publish, predictions log, **no plays are sized**. The backtest that motivated the `T_STAR` recalibration establishes *model* bias, not *market* mispricing — those are different claims and only the second one is tradeable.

- [ ] **Accumulate new-rule settlements.** 20 cities now list (when Kalshi lists at all), so this accrues far faster than the old NYC-only ~1/day. The full wet-fraction curve is logged every run, so `T_STAR` can be re-fit from live ensemble data without a backfill.
- [ ] **Capture closing prices per market-day.** Currently missing, and it is the binding constraint: bias must be scored against what was actually tradeable. Right now six of twenty cities show a mid of exactly 0.44, which is what an empty book produces — **`mid` is not yet a market probability.**
- [ ] **Beat NBM PoP or stop.** PoP is defined as P(≥0.01in), which *already matches the new rule*. If PoP prices this market correctly, there is no edge left and the honest move is to shut the project down. That is an acceptable outcome and should not be argued around.
- [ ] **Re-fit `T_STAR` on live ensemble data.** The current 1.0mm is provisional, fitted on deterministic models as a proxy because Open-Meteo retains only ~3 days of past ensemble members.
- [ ] Confirm each newly-listed city onboards cleanly (not gated) and spot-check its rules text once.

## Phase 2: Calibration learners (gate: 30+ non-gated NEW-RULE settlements per city)

Pre-registered design, constants already in the code (`CAL_MIN_N`, `CAL_LOOKBACK`):

- [ ] **Per-city t-star:** pick the threshold from the LOGGED wet-fraction curves that minimizes Brier against realized outcomes over the lookback, out-of-sample by date split. The curve logging exists precisely so this needs zero refetching.
- [x] ~~**Per-city trace floor:** replace the seeded prior with the realized P(YES | model dry)~~ **CANCELLED 2026-07-16.** Trace settles NO, so this would learn a coefficient on an outcome that never pays. The floor is pinned at zero and a test enforces it. Revive only if the rules flip back — which `trace_rule_ok` will catch on the first run after it happens.
- [ ] **Reliability recalibration:** if the calibration bins show a stable monotone distortion at 60+ settlements, fit a two-parameter shift-and-scale in log-odds; one knob family per checkpoint, Decision Log entry, MODEL_VERSION bump.
- [ ] **NBM promotion decision** at 50+ ref-bearing settlements: if NBM PoP beats the pooled model on Brier with a 95% bound excluding zero at 150+ paired records, test blending; below that, keep logging only.
- [ ] Retune governance is inherited from Nimbus verbatim: pre-registered experiments only, n-gates never lowered, at most one knob family per checkpoint, "no change" is a successful checkpoint, every change gets a Decision Log row.

**Kill criteria (pre-registered now):** at 100+ resolved plays, if the day-block bootstrap 90% CI on fees-inclusive ROI sits entirely below -8%, OR the model-vs-market Brier gap is still positive (worse) at 150+ non-gated events, stop scaling and return the model to the lab.

## Phase 3: Same-day nowcasting (gate: Phase 2 live AND 30-event shadow log)

The rain analog of Nimbus's top value-of-information item, and stronger here: rain observation is BINARY and ABSORBING. Once the settlement station records any precipitation, YES is certain; there is nothing to forecast anymore.

- [ ] **Observation lock:** poll `api.weather.gov/stations/{id}/observations` for the settlement station from local midnight; on the first nonzero precip (or precip-type METAR code), the market is a settled YES trading below 100. This is the cleanest edge in the whole design and also the most crowded; measure before trusting.
- [ ] **Conditional dry pricing:** while unlocked, P(rain rest-of-day) from members truncated to remaining hours.
- [ ] Requires midday/evening crons and a station->METAR id map (NYC: KNYC). SHADOW-LOG for 30+ same-day events before any play sizes on it, exactly the Nimbus nowcasting gate.

## Phase 4: Live trading

Governed by Nimbus's LIVE_TRADING_SPEC entry gates wholesale (paper gate, 14-day shadow, always-on runner, secrets, private repo). No order code exists or may exist until then. Do not duplicate the spec here; inherit it.

## Known weaknesses (honest list, keep current)

- **~~One-city universe~~ → 20 cities, but irregular listing.** `KXRAIN` covers 20 cities, so settlements accrue ~20x faster. The new constraint is that Kalshi lists the series irregularly: 2026-07-16 and 07-18 through 07-21 were never listed at all. An empty board is now a normal day.
- **~~The trace floor is a prior, not a measurement.~~ RETIRED.** Trace settles NO as of 2026-07-16; the floor is zero everywhere and tested.
- **The `T_STAR` fix is provisional.** 1.0mm was fitted on deterministic models as a proxy — a true ensemble backtest is impossible because Open-Meteo retains only ~3 days of past members. Direction is not in doubt (same sign in all 6 cities); the exact value is. Part of the measured bias is grid-cell-versus-point-gauge mismatch, not model error, and that part will not recalibrate away.
- **No edge is currently established.** This is the headline weakness. The bot measures and does not bet, and "there is no edge left" remains a live possible answer.
- **Wide books, thin OI at listing.** The first hours after the 14:00 UTC listing show 5c spreads and double-digit OI; the cost gate and MIN_OI will sit out many mornings. The evening board is the real board.
- **Correlated weather.** If MIA/HOU onboard, Gulf moisture correlates their outcomes; the daily cap (4u) is the blunt tool until cross-city concordance can be measured, exactly as Nimbus batch 8 did.
- **Rule risk. This one fired, and it was the expensive kind.** On 2026-07-16 Kalshi changed the series, the settlement stations for two cities, the settlement source, AND the trace rule at once. The structure and station gates behaved correctly — they refused to publish — but nothing was watching a red run, so the boards were dark for nine days before anyone noticed. Two lessons now in the code: the trace clause is re-read from the live rules text every run (`trace_rule_ok`), and an empty listing is distinguished from an unreadable one so real breakage stays loud instead of being drowned in routine red runs. **The remaining gap is alerting: a red run still only shows up in the Actions tab.**
- **Schedule reliability.** GitHub crons drift (measured +1.4h to +3.8h on Nimbus); off-hour minutes and the 16h stale banner mitigate. Fine for paper, unacceptable for live.

---

*Maintenance rule: any AI making changes reads this file along with HANDOFF.md and moves shipped items into the HANDOFF changelog.*
