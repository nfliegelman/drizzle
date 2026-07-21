# Drizzle (Kalshi Daily Rain): AI Handoff / Technical Spec

**Purpose of this file:** you are an AI assistant helping the owner (a hobbyist prediction-market bettor, not a professional developer) modify this program. This document tells you what the program is, how it is built, and which decisions are deliberate so you do not undo them. Read it fully before proposing changes. `README.md` is for the owner (setup). `FUTURE.md` is the phase roadmap and known weaknesses. This file is for you.

**Doc version:** 2026-07-21 (d1.1). Drizzle is the sibling of Nimbus (github.com/nfliegelman/nimbus), forked from its fully audited v12 chassis. Nimbus's HANDOFF.md and 12-batch audit register are the deep background; every guard here is a Nimbus guard wearing rain clothes, and the burden of proof for removing one is the same: do not.

---

## 0. THE ONE RULE THAT PREVENTS CONFUSION

Every time you change the code, hand the owner back BOTH the updated `drizzle.py` AND an updated `HANDOFF.md` with a new changelog entry, and tell them to commit both together. Handbacks are the complete repo as a zip, always full files, never diffs, and NEVER include `drizzle_state.json` (it is the entire track record; the workflow commits it back, git history is its backup). Never use em dashes anywhere: not in code, comments, UI text, or chat replies. Surgical edits only.

## 1. Prime directives

1. **Do not rebuild from scratch.** Prefer surgical edits; say so explicitly if you believe a rewrite is warranted.
2. **Honesty over polish.** "No plays today" is a correct, valuable output. Never manufacture signals or inflate sizes. Roughly 3 of the deepest failures in the sibling project's history were fake edges that looked real.
3. **Real data only.** Every probability traces to an actual ensemble forecast; every win/loss traces to Kalshi's official settlement. Unavailable source = honest sit-out, never an estimate presented as fact.
4. **Serve the underlying goal, not just the literal request.** Propose smarter framings; ask clarifying questions when they improve the result. The owner explicitly values this.
5. **Phase discipline.** Phase 2 and 3 features (calibration learners, nowcasting) have pre-registered activation gates in FUTURE.md. Do not turn them on early because the data "looks ready".

## 2. What the market is (Phase 0 facts, verified live)

- One **binary** market per city per day: "precipitation recorded at `<station>` on `<date>` is strictly greater than 0 inches". Series `KXRAIN*` (and a legacy no-KX generation in the catalog).
- **Trace settles YES.** Proven two independent ways: (a) empirically, 60 joined days of Kalshi settlements vs the official climate record: 7/7 Trace days YES, 29/29 dry days NO, zero mismatches (2026-07-06); (b) the live `rules_secondary` states it outright: Expiration Value T (Trace) or R (Record) resolves YES (re-verified 2026-07-07). **The event is "the gauge records ANYTHING at all", not "measurable rain". This asymmetry is the entire model.**
- Settlement source: the **NWS Climatological Report (CLI)** for the station (NYC = Central Park, product CLINYC via OKX). Fallback in rules: the NWS observation time series. Same LST day convention as Nimbus.
- `expiration_value` on settled markets is a STRING: `"1.03"`, `"0.00"`, or `"T"`. `parse_exp_value` handles all three; do not float() it blind.
- Fee: `fee_type quadratic, fee_multiplier 1` read live from the series endpoint, identical to Nimbus. Rate for the cost gate, trade-level ceil at resolution.
- Markets open **14:00 UTC the day before** the target and close 03:59 UTC (23:59 ET) on the target day; they expire at the first 10:00 ET after the CLI releases.
- **Universe as of 2026-07-07: NYC only.** SEA/MIA and legacy series exist in the catalog but list no events (seasonal or dormant). `CITIES` carries them with provisional station keywords; auto-onboarding verifies the rules text names the expected station and quarantines on mismatch. When a new city goes live, VERIFY its settlement station against `rules_secondary` before trusting its plays, exactly like the Nimbus batch 1 station audit (which caught Houston settling at Hobby, not IAH).
- **API field generations.** The rain series serves dollars-string quote fields (`yes_bid_dollars`, `open_interest_fp`, `fractional_trading_enabled: true`), NOT the integer-cent fields Nimbus reads. `qdollar`/`qfloat` parse both generations defensively. This is the KXHIGH/KXHIGHT lesson in a new hat; do not simplify to one generation.

## 3. The model (rain-specific core)

1. **Members:** the Nimbus ensemble exactly: Open-Meteo `gfs025 + ecmwf_ifs025 + icon_seamless + gem_global`, hourly `precipitation`, ~143 members, summed per member over the **NWS CLI day in Local Standard Time year-round** (during DST that is 1:00 AM to 12:59 AM clock time; `fetch_members` shifts timestamps back by the DST offset before grouping, same settlement-correctness guard as Nimbus).
2. **Raw probability:** `p_raw` = fraction of members whose daily total exceeds `T_STAR_MM` (0.1 mm prior, deliberately below the 0.01 in CLI floor because Trace also settles YES). The full wet-fraction **curve across 6 thresholds is logged on every record** so the Phase 2 learner can pick per-city t-star retroactively without refetching anything.
3. **Trace floor (the thesis):** `p = p_raw + (1 - p_raw) * trace_p(city)`. Grid QPF calls a drizzle-mist-trace day zero; the gauge does not. Priors: NYC 0.15 (seeded from the 60-day join), others seeded climatologically, default 0.10. Phase 2 learns these from settlements at 30+ per city.
4. **Decision clamp:** decision probability clamped into `[POP_CLAMP, 1 - POP_CLAMP]` (0.03), the binary cousin of Nimbus's TAIL_FLOOR. Logged `p` stays raw so calibration sees the true model.
5. **References (evidence only):** NBM hourly PoP and precip logged per record (`nbm_pop_max`, `nbm_pop_day` = 1 minus the product of hourly dry probabilities, `nbm_precip`). They appear in the Forecast sources Brier table and must never touch scoring, sizing, or guards until the pre-registered Phase 2 promotion decision.

## 4. The guards (DELIBERATE, do not remove)

- **Realized guard / lead window.** Phase 1 trades lead 1 to `MAX_LEAD_DAYS` (2) ONLY. A same-day rain market is partially realized from local midnight; lead-0 records are deliberately not even logged (partial-information contamination). Lead comes from the CITY's clock via Open-Meteo `utc_offset_seconds`, never the runner's (GitHub runners are UTC; this bug killed Nimbus evening logging for 3 versions).
- **Integrity gate (quarantine semantics).** Per city-date: market structure must be exactly one binary market, `strike_type greater`, floor 0; the rules text must contain the expected station keyword AND "strictly greater than 0"; pooled members >= `GATE_MIN_MEMBERS` (90); models present >= `GATE_MIN_MODELS` (3 of 4). Failures log a full record with a `gated` reason, carry no plays, are excluded from every report aggregate and (Phase 2) from learning, resolve normally so every exclusion can be judged against the settlement later, and NEVER overwrite a record holding frozen plays.
- **Divergence guard (uncalibrated-era humility).** Until a city has `DIV_GUARD_MIN_N` (15) non-gated settlements, a model-vs-market gap wider than `DIVERGENCE_GUARD` (0.35) suppresses plays (logged with a `suppressed` reason, fully reconstructible). Rationale: with zero settled history, a 40-point disagreement is more likely our trace prior being wrong for that city than the market being asleep. Auto-expires per city as settlements accrue. This is the binary cousin of the Nimbus bias guard.
- **Cost gate.** Net = p_win minus ask-side entry minus exact fee rate minus 1 cent buffer, must clear `PLAY_NET_EDGE` (0.05, deliberately above Nimbus's 0.04: rain books are wider). Entry must sit inside `[0.05, 0.95]`; OI must clear `MIN_OI` (300, parsed from `open_interest_fp`).
- **Sizing constitution** (`size_play`): edge bands (1u at net >= 0.05; 1.5u needs net >= 0.10 AND p_win >= 0.55), `SUSPECT_EDGE` 0.20 plausibility cap to 1u (a 20+ point edge on a weather binary is a red flag, not a green light), favorite-longshot cap (p_win < 0.30 capped at 1u), and **2u does not exist in Phase 1** (no proven cities). Do not invert any of these.
- **Play freeze.** First non-empty `plays` log wins forever (`plays_lead`, `plays_logged_at`, `plays_model_version` stamp the decision moment); later runs refresh `p`, quotes, and refs but never the frozen plays. Verified by test and by live double-run.
- **Exposure caps, SEEDED.** `DAILY_UNIT_CAP` 4.0 per target date and `EVENT_UNIT_CAP` 1.5 per market, budgets pre-charged with every already-frozen play for the target before any new play may freeze (the Nimbus deploy-day capseed lesson, inherited on day one rather than relearned).
- **Fail loudly.** Crash exits 1; zero rain markets from Kalshi exits 2 (never publish a fake quiet day); corrupt or malformed state exits 3 and refuses to run rather than wipe the track record. `fget` retries with backoff because Kalshi intermittently 503s bursty callers (observed during this build; a swallowed 503 briefly looked like a zero-market day).
- **Stale-board banner.** Pages embed their build epoch and self-flag past 16 hours. Do not bet from a flagged board.

## 5. File structure (single file: drizzle.py)

| Section | What |
|---|---|
| knobs + CONFIG_HASH | all tunables; 8-hex fingerprint stamped on every record |
| CITIES | code -> (lat, lon, tz, std offset, label, series generations, station keyword, trace prior). Coordinates are Kalshi settlement stations from the Nimbus batch 1 CLI audit |
| helpers | fget (retrying), fee, _wilson, qdollar/qfloat (dual-generation quotes), parse_date_code, parse_exp_value |
| data fetch | pull_rain_markets (series scan + structure + rules verification), fetch_members (LST-day member precip totals), fetch_ref (NBM, evidence only), fetch_settled_market |
| model | wet_curve, rain_prob (trace floor), decision_prob |
| sizing | size_play |
| engine | score (gate, guard, freeze, seeded caps) |
| resolution | resolve_pending (result + expiration_value incl Trace, trade-fee ceil, CLV) |
| reporting | compute_report (Brier vs market, Wilson calibration bins, per-city, sources table, honesty tiles, deterministic day-block bootstrap ROI CI, CLV, eras, alarms) |
| render | CSS, render_bets (cards, YES green / NO red), render_results, svg_line, stale banner |
| notify | Telegram, secrets-gated, non-fatal |
| main | load, resolve, score, report, save, render |

Stdlib only (a security control on a contents:write public workflow, per the Nimbus batch 12 verdict). No frameworks, no chart libraries, charts are inline SVG. Python pinned 3.12; no backslashes inside f-string expressions.

**Repository hygiene.** A `.gitignore` ignores `__pycache__/` and `*.pyc`; never commit compiled bytecode (a stray `drizzle.cpython-312.pyc` and an empty accidental `.github/workflows/test` file were both purged in d1.1). Two files ARE tracked on purpose and must never be added to `.gitignore`: `drizzle_state.json` (the track record; git history is its backup) and `docs/` (the deployed Pages site the workflow regenerates every run). Generated markup is authored in `_page`, which emits `<html lang='en'>` for accessibility; the `docs/*.html` snapshots pick up that markup on the next scheduled run, so a code-only diff that leaves the committed pages behind is expected, not a mismatch.

## 6. State schema (drizzle_state.json)

`predictions[key]`, key = `CODE|YYYY-MM-DD`: code, target, event_ticker, ticker, series, logged_at, first_logged, lead, members, models{model:{n,wet}}, p_raw, p, curve{threshold:frac}, trace_p, ref{}, yb, ya, mid, oi, offset, model_version, cfg, p_hist (last 6 [stamp, p] revision pairs), plays[]; optional: gated, suppressed; once plays freeze: plays_lead, plays_logged_at, plays_model_version.

`plays[i]`: ticker, side, entry, net, edge, units, stake, p_win, prob, mid, why. Resolved plays add: won, contracts, pnl, close_mid, clv, outcome, target, lead, model_version.

`resolved[i]`: everything above plus outcome (0/1), exp_val (raw string), amount, trace (bool). Gated and suppressed records resolve normally, flagged.

Contract: every reader of old records uses `.get` with fallbacks; adding a REQUIRED field without a migration note here is forbidden. Never delete or overwrite `drizzle_state.json`.

## 7. Validate before handing back

1. `python -c "import py_compile; py_compile.compile('drizzle.py', doraise=True)"` passes.
2. `python test_drizzle.py` passes (16 tests, network-free; CI runs it before every board and blocks publish on failure).
3. `CI=true python drizzle.py` runs twice; the double run must show zero freeze violations and both docs pages written. Zero plays is a legitimate outcome.
4. No em dashes introduced anywhere; no backslash inside any f-string expression.
5. No guard removed, no sizing cap inverted, no learner activated ahead of its gate.
6. Changelog entry added here; owner told to commit code + HANDOFF together.

## Changelog

- **d1.1 (2026-07-21), HYGIENE + ACCESSIBILITY, MODEL_VERSION UNCHANGED (`2026-07-07.d1-phase1`), CONFIG_HASH UNCHANGED:** Generated-default residue sweep. No model, scoring, sizing, guard, or knob touched, so MODEL_VERSION and CONFIG_HASH deliberately do not move and the track record does not fragment. Changes: (1) added `.gitignore` and purged two tracked artifacts that were never source of truth: a committed `__pycache__/drizzle.cpython-312.pyc` and an empty `.github/workflows/test` file (created accidentally via the web UI; GitHub Actions only runs `*.yml`, so it never did anything). (2) `_page` now emits `<html lang='en'>` (WCAG 3.1.1, Language of Page). (3) Raw-settlements P&L for no-play rows renders the neutral `.small` class instead of loss-red `.neg`, so a settled day the model correctly sat out no longer reads as a loss. Validation: 16/16 offline tests pass; both pages re-rendered offline from the real state and asserted for the `lang` attribute and the neutral dash; live end-to-end double-run NOT performed (this environment's network policy blocks the Kalshi and Open-Meteo hosts). See `REMEDIATION.md` for the full audit, sources, and rollback.
- **d1.0 (2026-07-07), PHASE 1 SHIP, MODEL_VERSION `2026-07-07.d1-phase1`:** Full Phase 1 build on the Nimbus v12 chassis. Phase 0 re-verified live same day: Trace-YES now explicit in rules_secondary (corroborating the 60-day empirical proof), fee quadratic x1, NYC-only live universe, dollars-string API generation discovered and handled (`qdollar`). Engine: LST-day member precip totals from the 4-model 143-member ensemble, trace-floor probability with logged threshold curves, NBM evidence refs, divergence guard, integrity gate with quarantine, play freeze, seeded exposure caps, exact fee gate with trade-level ceil, CLV capture, Trace-aware resolution. Report: Brier model vs market, Wilson-barred calibration bins, per-city with trace counts, forecast sources Brier table, honesty tiles, deterministic day-block bootstrap ROI CI, era table, alarms. 16-test CI suite. Validation: 16/16 tests; live double-run against real Kalshi/Open-Meteo (143 members fetched, freeze held, both pages rendered); first live board correctly produced a candidate edge (NYC Jul 8: model 22.7% vs market 7.5%) and correctly refused it on thin OI (55 vs 300 floor) two hours after listing. Build incident logged: burst probing drew Kalshi 503s that a swallowed exception turned into a zero-market abort; fget now retries with backoff and series probes are spaced.

## Decision log

| Date | Change | Basis | Version |
|---|---|---|---|
| 2026-07-06 | Trace-YES adopted as the model thesis | 60-day empirical join, 0 mismatches | d1 |
| 2026-07-07 | Thesis corroborated by rules text | rules_secondary states T/R resolve YES | d1 |
| 2026-07-07 | PLAY_NET_EDGE 0.05 (vs Nimbus 0.04) | rain books wider; hurdle must be too | d1 |
| 2026-07-07 | DIVERGENCE_GUARD 0.35 until n=15/city | zero settled history; humility before market | d1 |
| 2026-07-07 | Lead 0 unlogged, lead 1-2 tradeable | partial realization from local midnight | d1 |
| 2026-07-07 | Caps seeded from day one | Nimbus deploy-day capseed lesson, inherited | d1 |
| 2026-07-07 | Dual-generation quote parser | KXRAIN serves dollars-string fields | d1 |
| 2026-07-21 | `.gitignore`; purged committed `.pyc` and stray workflow file | build artifacts are not source of truth; keep the repo authored | d1.1 |
| 2026-07-21 | `<html lang='en'>` on generated pages | WCAG 3.1.1; screen readers and translation | d1.1 |
| 2026-07-21 | No-play P&L dash neutral, not loss-red | a sat-out day is not a loss; honesty over color noise | d1.1 |

---

*When you finish a change: bump the doc version, add a changelog entry saying what changed and why, update any section that no longer matches the code, and remind the owner to commit both `drizzle.py` and `HANDOFF.md` together.*
