# Drizzle: Phase Roadmap and Future Inclusions

**Purpose:** the phased buildout plan with pre-registered activation gates, plus the running list of known weaknesses. When an item ships, move it to the HANDOFF.md changelog. Phases are ordered; do not skip ahead: each is gated on settled history that does not exist yet.

---

## Phase 0: Rules and settlement recon (COMPLETE, 2026-07-06, re-verified 07-07)

- [x] Settlement semantics proven empirically: 60 joined days, Trace 7/7 YES, dry 29/29 NO, zero mismatches.
- [x] Corroborated in the live rules text: Expiration Value T or R resolves YES.
- [x] Fee structure verified (quadratic x1, same as Nimbus). Universe mapped (NYC live; SEA/MIA/legacy series dormant in catalog). Station verified for NYC (Central Park). API dollars-field generation discovered.

## Phase 1: Paper engine, lead 1-2, fixed priors (SHIPPED 2026-07-07, this build)

Everything in HANDOFF.md. The owner's only jobs now:

- [ ] Paper trade and let settlements accumulate. With NYC-only, expect ~1 settlement/day; the Phase 2 gate (30) is roughly a month out, conveniently landing after the Israel trip.
- [ ] Watch the **Calibration** table. The single most important readout, same as Nimbus.
- [ ] Watch the **By city trace share** against the seeded priors (NYC 0.15). If NYC trace+small-amount days run persistently above the model's stated probabilities in the 10-30% bins, the floor is too low; below, too high. Do not hand-tune it; that is Phase 2's job with data.
- [ ] Watch the **Forecast sources** table: pooled+floor must beat pooled raw for the thesis to be earning anything, and NBM PoP is the benchmark to beat before any promotion talk.
- [ ] When Kalshi lists a new rain city, confirm the header shows it onboarded cleanly (not gated on station text) and spot-check the rules text yourself once.

## Phase 2: Calibration learners (gate: 30+ non-gated settlements per city)

Pre-registered design, constants already in the code (`CAL_MIN_N`, `CAL_LOOKBACK`):

- [ ] **Per-city t-star:** pick the threshold from the LOGGED wet-fraction curves that minimizes Brier against realized outcomes over the lookback, out-of-sample by date split. The curve logging exists precisely so this needs zero refetching.
- [ ] **Per-city trace floor:** replace the seeded prior with the realized P(YES | model dry) from settlements, shrunk toward the prior by n/(n+K), exactly the Nimbus shrinkage pattern. Learn the SIGN carefully: reconstruct raw from logged fields (the Nimbus batch 3 sign bug is the cautionary tale; write the unit test first).
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

- **One-city universe.** NYC-only means ~1 settlement/day: calibration gates take a month, and a single station's quirks dominate everything. More cities onboard automatically when Kalshi lists them; nothing to build, but patience is mandatory.
- **The trace floor is a prior, not a measurement.** 0.15 for NYC comes from a 60-day summer join; winter regimes, drought stretches, and seasonality can move it. The divergence guard and Phase 2 learning are the mitigations. Expect the first live boards to lean on the floor heavily (the very first board did: raw 9%, floored 23%, market 8%).
- **Wide books, thin OI at listing.** The first hours after the 14:00 UTC listing show 5c spreads and double-digit OI; the cost gate and MIN_OI will sit out many mornings. The evening board is the real board.
- **Correlated weather.** If MIA/HOU onboard, Gulf moisture correlates their outcomes; the daily cap (4u) is the blunt tool until cross-city concordance can be measured, exactly as Nimbus batch 8 did.
- **Rule risk.** Kalshi can change stations, thresholds, or sources; the structure and station gates catch the detectable cases. Re-verify rules text whenever a market looks off.
- **Schedule reliability.** GitHub crons drift (measured +1.4h to +3.8h on Nimbus); off-hour minutes and the 16h stale banner mitigate. Fine for paper, unacceptable for live.

---

*Maintenance rule: any AI making changes reads this file along with HANDOFF.md and moves shipped items into the HANDOFF changelog.*
