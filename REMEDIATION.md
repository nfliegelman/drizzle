# Investigation and Remediation Report

Audit and generated-default residue sweep of the Drizzle repository, executed
2026-07-21 against branch `claude/ai-residue-remediation-svpqbq`. Residue score
is oriented so that **0 = fully authored, no generated-default residue** and
**100 = pure generic template**. Lower is better.

## Result

- Before residue score: **9 / 100** (mean of the category table below)
- After residue score: **6 / 100**
- Evidence confidence: **High** for everything verified offline; **explicitly limited** for anything requiring the live Kalshi or Open-Meteo APIs (this environment's network policy blocks both hosts, confirmed by a `403 to CONNECT` from the agent proxy for `ensemble-api.open-meteo.com` and `api.elections.kalshi.com`).
- Research-completeness gate: **Passed for the layers changed.** For the untouched core data path (ensemble model-key parsing) the gate is **NOT claimed passed**: it needs a live spike this environment cannot run. See Unresolved items.
- Build status: `python -c "import py_compile; py_compile.compile('drizzle.py', doraise=True)"` passes.
- Test status: `python test_drizzle.py` -> **16/16 pass**, network-free, unchanged from baseline.
- Deployment status: not exercised end-to-end (the workflow needs the blocked APIs). The `run.yml` workflow itself is unchanged and valid.
- Highest remaining risk: the `MODEL_TAGS` key-matching in `fetch_members` relies on a fallback rather than a live-validated tag match (latent fragility, not a live bug). Documented below; deliberately not changed without a live spike.

## Product truth

- **Primary user:** the owner, a single hobbyist prediction-market bettor (not a professional developer), reading two pages on an iPhone.
- **Primary workflow:** three times a day a GitHub Actions run settles yesterday's Kalshi rain markets against official settlement, scores today's open markets with an ensemble-plus-trace-floor model, freezes any qualifying paper play, and regenerates two static pages (today's plays, results tracker).
- **Highest-value outcome:** an honest, frozen, reconstructible paper track record that decides whether the trace-floor thesis actually beats the market before any real money is risked.
- **Owner constraints:** surgical edits only, stdlib only (security control on a `contents: write` public workflow), no em dashes anywhere, no guard removed, no learner activated before its pre-registered gate, and the track record (`drizzle_state.json`) is never overwritten or deleted.
- **Security/privacy boundary:** public repo, paper only, no order code, no bankroll assumption; the only secrets are optional Telegram notifier tokens supplied via GitHub Actions secrets and never committed.
- **Key assumptions:** Kalshi rain markets settle YES on any recorded precipitation including Trace (proven two ways in Phase 0); grid QPF under-prices trace/drizzle days; that gap is the entire edge.

## Current-state inventory

| Layer | Before | Provenance | Fit | Research tier |
|---|---|---|---|---|
| Runtime | GitHub Actions cron 3x/day | Authored (Nimbus lineage) | Appropriate | A |
| Language | Python 3.12, stdlib only | Authored | Appropriate | A |
| Server boundary | None (batch job) | Authored | Appropriate | B |
| State store | `drizzle_state.json`, git-tracked | Authored | Appropriate | A |
| Hosting | GitHub Pages, static `docs/` | Authored | Appropriate | B |
| External APIs | Kalshi, Open-Meteo ensemble + NBM | Validated inheritance | Appropriate | A |
| Notifications | Telegram, secrets-gated, non-fatal | Authored | Appropriate | C |
| Styling / UI | Hand-written CSS + inline SVG | Authored | Appropriate | B |
| Testing | 16 network-free unittest cases, CI-gating | Authored | Appropriate | A |
| Build artifacts | committed `__pycache__/*.pyc` | **Accidental** | **Residue** | C |
| CI files | stray empty `.github/workflows/test` | **Accidental** | **Residue** | C |
| Ignore rules | none (`.gitignore` absent) | **Generated default** | **Residue** | C |
| Accessibility | generated HTML lacked `lang` | **Unvalidated inheritance** | **Underbuilt** | B |

## Intensive research completed

### Accessibility: document language (`lang`)

- Candidates: omit (status quo), `<html lang='en'>`, per-string i18n framework.
- Primary sources: WCAG 2.2 Success Criterion 3.1.1 "Language of Page" (Level A); WHATWG HTML Standard `lang` attribute guidance; MDN `<html>` element reference.
- Adversarial findings: an i18n framework would violate stdlib-only and add lock-in for a single-locale personal app; not justified.
- Decision: add `lang='en'` to the one page template (`_page`). Zero dependency, one attribute, satisfies 3.1.1. **Confidence: High** (single-locale English UI is a Verified fact from the copy).
- What could change it: the app becomes multi-locale (not on any roadmap).

### Repository hygiene: bytecode and stray files in version control

- Primary sources: Python docs (`__pycache__` is a regenerated cache, not source); GitHub Actions docs (only `*.yml`/`*.yaml` under `.github/workflows` are executed, so `test` with no extension is inert); `git rm --cached` semantics.
- Operational evidence: `git log` shows the stray file came from a "Create test" commit (the web UI default for an accidental empty file). The `.pyc` matches the committed `drizzle.py` and is reproduced on any import.
- Decision: purge both from tracking, add a `.gitignore`, and pin the intent in HANDOFF so they are not reintroduced. **Confidence: High** (both files are Verified non-source-of-truth).

### Architecture fit (challenged, retained)

- The stack (GitHub Actions + Pages + stdlib Python + a single JSON state file) was challenged against the audit's "is this a generated default" test. It is not: it is a deliberate, documented fit for a zero-cost, self-hosting, phone-readable, single-owner paper-trading tool, with the security rationale (stdlib on a write-scoped public workflow) written down. **Decision: retain.** This is a case of the current choice winning honestly.

## Exclusion log

| Candidate | Layer | Exclusion reason | Evidence | Reconsideration trigger |
|---|---|---|---|---|
| i18n framework | Accessibility | Single-locale app; violates stdlib-only; lock-in | UI copy is English-only | App goes multi-locale |
| SQLite / DB | State | JSON + git history already gives durability, diffability, and free backup at this scale | State file is tiny, append-mostly | State outgrows a single JSON file or needs concurrent writers |
| `html.escape` on `exp_val` | Security | Theoretical only: a single-user page rendering a controlled numeric/"T" Kalshi field | No untrusted free-text is rendered | Any Kalshi free-text field (e.g. rules) starts being rendered into a page |
| Change `gefs` tag to `gfs` in `MODEL_TAGS` | Data path | Current behavior is correct by fallback; a blind change to a Tier A path is riskier than the fragility | Reasoned statically; cannot spike live here | A live Open-Meteo key dump confirms the exact member-key naming |

## Stack and service decisions

| Layer | Before | After | Why | Migration | Rollback | Cost impact |
|---|---|---|---|---|---|---:|
| Ignore rules | none | `.gitignore` | Stop tracking regenerated bytecode | add file | delete file | $0 |
| Build artifacts | `.pyc` tracked | untracked | Not source of truth | `git rm --cached` | `git revert` | $0 |
| CI files | stray `test` | removed | Inert accidental file | `git rm` | `git revert` | $0 |
| Page template | `<html>` | `<html lang='en'>` | WCAG 3.1.1 | one-line edit | `git revert` | $0 |

No technology was replaced. No dependency was added (the project remains stdlib-only).

## Changes implemented

### Product and information architecture
No change. The two-page model (plays / results) is authored and correct.

### Visual system
Raw-settlements P&L for a no-play row now uses the neutral `.small` class instead of loss-red `.neg`, so a day the model correctly sat out no longer renders as if it lost money.

### Interaction states
No structural change; the color fix above is the only interaction-state correction. Loud failures, the stale-board banner, the empty "No plays today" state, and quarantine/guard notes were already present and correct.

### Copy
No change. Copy is domain-specific, honest, and free of marketing filler.

### Frontend and code architecture
Removed committed bytecode and the stray workflow file. The single-file design is deliberate (documented in HANDOFF) and retained.

### Backend, data, authorization, and security
No change. Guards, gates, freeze, seeded caps, and stdlib security posture retained intact.

### Accessibility and performance
Added `lang='en'` to every generated page. Performance already excellent (inline SVG, no libraries, sub-10 KB pages).

### Testing and operations
Added `.gitignore` so caches are not re-committed. Test suite unchanged and green.

## Files changed

| File | Purpose |
|---|---|
| `drizzle.py` | `<html lang='en'>` in `_page`; neutral P&L class for no-play rows in `render_results` |
| `.gitignore` | New; ignores bytecode/caches; documents the two intentionally-tracked paths |
| `.github/workflows/test` | Removed (empty accidental file) |
| `__pycache__/drizzle.cpython-312.pyc` | Removed from tracking (regenerated locally, now ignored) |
| `HANDOFF.md` | Doc version d1.1; changelog + decision-log rows; repository-hygiene section |
| `REMEDIATION.md` | This report |

## Verification performed

| Check | Procedure | Result | Notes |
|---|---|---|---|
| Byte-compile | `py_compile.compile('drizzle.py', doraise=True)` | Pass | |
| Unit/pipeline tests | `python test_drizzle.py` | 16/16 pass | network-free, unchanged |
| Offline render | Loaded real `drizzle_state.json`, ran `compute_report` + `render_results` + `render_bets` into a temp dir | Pass | asserted `<html lang='en'>` in both pages and `<td class='small'>-</td>` for no-play P&L |
| Numbers unchanged | Compared report to committed `results.html` | Pass | Brier model 0.1656, 7 settled events reproduced exactly |
| Em-dash scan | grep for U+2014 across `*.py`, `*.md`, `*.yml` | Clean | constitution preserved |
| State/docs untouched | `git diff --stat drizzle_state.json docs/` | Empty | track record and committed pages not modified |
| Live end-to-end double-run | `CI=true python drizzle.py` twice | **NOT RUN** | needs Kalshi + Open-Meteo; blocked by network policy. Freeze invariant is covered by `test_play_freeze_and_divergence_guard` offline |

## Before-and-after audit

| Category | Before | After | Evidence |
|---|---:|---:|---|
| Product specificity | 3 | 3 | Razor-specific thesis and copy |
| Research integrity | 4 | 4 | Dated, labeled, adversarial evidence throughout HANDOFF/FUTURE |
| Architecture fit | 6 | 6 | Serverless + stdlib fit documented; challenged and retained |
| Visual system | 12 | 8 | No-play dash color corrected; scope attrs still absent |
| Typography / composition | 10 | 10 | System fonts, dense, purposeful; unchanged |
| Interaction states | 10 | 8 | Loud failures + stale banner + empty states present; color fixed |
| Copy | 3 | 3 | Honest, domain-specific |
| Frontend / code architecture | 14 | 6 | Committed `.pyc` and stray file purged |
| Backend / data / authz / security | 8 | 8 | Strong guards retained; one theoretical escape noted and accepted |
| Accessibility | 30 | 14 | `lang` added; header `scope` and a couple minor items remain |
| Performance | 4 | 4 | Inline SVG, no libraries |
| Testing | 6 | 6 | 16 network-free tests gate publish |
| Deployment | 12 | 6 | `.gitignore` added; stray workflow file removed |
| Backup / recovery / docs | 8 | 6 | Excellent docs; `.gitignore` now records tracking intent |

## Deliberately retained common patterns

- **GitHub Actions + Pages + single-file stdlib Python.** Not a generated default: it is the documented best fit for a zero-cost, self-hosting, single-owner, phone-readable paper tool, with the stdlib-only security rationale written down. It wins honestly.
- **JSON state file tracked in git.** Durable, diffable, free backup via history at this scale; a database would add lock-in and operational burden for no benefit.
- **Dark, dense, mobile-first dashboard with system fonts and inline SVG.** Authored for glanceability on a phone; no gradient hero, no bento grid, no stock component shells, no fake social proof. Nothing to remediate.
- **Single-file `drizzle.py`.** Deliberate and documented; fragmenting it would be arbitrary churn, not improvement.

## Unresolved items

| Item | Reason | Risk | Required research or action |
|---|---|---|---|
| `MODEL_TAGS` `gefs` tag never matches Open-Meteo keys; gfs025 members are only captured by the `ENSEMBLE_MODELS[0]` fallback | Correct today by fallback, but fragile; cannot be live-validated here (APIs blocked) | Low; would only bite if Open-Meteo renamed keys or reordered `ENSEMBLE_MODELS` | Dump live ensemble hourly keys, confirm naming, then either change the tag to `gfs` with a test or leave with a comment. Do NOT change blind |
| Table headers lack `scope='col'` | Kept edits surgical; `<th>` in the first row is already announced by most screen readers | Low | Add `scope='col'` if a fuller a11y pass is desired |
| `exp_val` rendered unescaped | Single-user page, controlled numeric field | Negligible | Wrap in `html.escape` only if any free-text Kalshi field is ever rendered |
| Live end-to-end double-run not executed | Network policy blocks Kalshi + Open-Meteo | Low (freeze covered by offline test) | Re-run `CI=true python drizzle.py` twice in an environment with API access before relying on the next board |

## Migration and rollback notes

Every change is additive or a removal of non-source-of-truth files; none touches
the model, the knobs, the state schema, or the track record. `MODEL_VERSION` and
`CONFIG_HASH` are intentionally unchanged, so the era table and calibration
history do not fragment. The committed `docs/*.html` snapshots are left as-is and
will regenerate with the new markup on the next scheduled run.

Full rollback: `git revert <commit>` restores the prior tree exactly. The purged
`.pyc` regenerates on the next `python` invocation; the stray `.github/workflows/test`
was inert, so removing it changes no behavior.

## Updated ADRs and project instructions

`HANDOFF.md` (the AI-facing durable spec) is updated: doc version bumped to d1.1,
a changelog entry and three decision-log rows added, and a new "Repository hygiene"
paragraph records the `.gitignore`, the never-commit-bytecode rule, and the two
paths (`drizzle_state.json`, `docs/`) that are tracked on purpose and must never be
ignored.

## What could change these decisions

- A live Open-Meteo key dump that contradicts the assumed member-key naming would reopen the `MODEL_TAGS` question.
- The app adding a second locale would justify real i18n and change the `lang` decision.
- The app ever rendering untrusted Kalshi free-text into a page would promote the `exp_val` escaping item from "accepted" to "required".
