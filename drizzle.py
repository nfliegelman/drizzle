#!/usr/bin/env python3
"""
DRIZZLE: Kalshi daily rain markets, paper trading, honest measurement first.

Sibling of Nimbus (github.com/nfliegelman/nimbus), forked from its audited v12
chassis on 2026-07-07. Same constitution: freeze what you claimed, quarantine
what you exclude, cap what you risk, pre-register what you will tune, and never
let a broken fetch publish as a quiet day.

THE ORIGINAL THESIS IS DEAD. READ THIS BEFORE CHANGING ANYTHING.

Phase 1 (2026-07-07 to 2026-07-15) traded one series per city (KXRAINNYC etc)
whose rules said an Expiration Value of T (Trace) or R (Record) resolves YES.
The whole edge was that the gauge records trace on days every grid ensemble
calls dry, so YES was systematically underpriced. That was proven twice: on 60
joined days of settlements, and in the rules text itself.

On 2026-07-16 Kalshi retired those series and consolidated every city into ONE
series, KXRAIN, with one market per city per event (KXRAIN-26JUL24-NYC). The
new rules text INVERTS the settlement rule that the edge rested on:

    "Trace amounts (T) and missing daily precipitation values are counted
     as 0 inches."

Since the payout criterion is still "strictly greater than 0 inches", a trace
day now settles NO. It used to settle YES. Verified the same way the original
thesis was: on 60 settled market-days of the new series, Kalshi's own results
agree with the new rule 40/40 where gauge data was joinable, and all three
trace days found (AUS, HOU, MIN on 2026-07-17, GHCN measurement flag "T")
settled NO. The settlement source also moved from the NWS CLI report to The
Weather Company feed at weather.com/kalshi.

Consequence: the trace floor (p = p_raw + (1-p_raw)*trace_p) now ADDS
probability to an outcome that no longer pays. Applying it would systematically
overpay for YES. It is therefore set to ZERO for every city, and the rules text
is re-verified on every run: a city whose rules do not say trace counts as zero
is quarantined rather than traded, because that would mean the regime moved
again.

Current scope is RESEARCH MODE: the board is published and every prediction is
logged so calibration rebuilds under the new rules, but NO plays are sized.
Pre-2026-07-16 settlements belong to the old regime and must never be pooled
with new ones; they are separated by model_version era in the report.
"""
import json, math, os, sys, time, hashlib, datetime as dt
import urllib.request, urllib.error
from collections import defaultdict

# ------------------------------ identity -------------------------------
# Era bump is mandatory, not cosmetic: the report pools settlements by
# model_version, and pooling old-rule (trace=YES) days with new-rule
# (trace=NO) days would silently corrupt every calibration number.
MODEL_VERSION = "2026-07-24.d2-newrules"
APP = "Drizzle"

# RESEARCH MODE: log and publish, never size a play. On until the rebuilt
# calibration under the new rules justifies a bet. The old edge was deleted by
# Kalshi on 2026-07-16 (see module docstring); trading before re-measuring
# would just be betting an inverted thesis.
RESEARCH_MODE = True

# ------------------------------- knobs ---------------------------------
# Sizing is in UNITS end to end (owner directive 2026-07-06): no bankroll
# assumption anywhere. BASE_UNIT_USD exists only because Kalshi contracts
# settle in dollars, so paper stakes need a basis; every display divides it
# back out. When a real unit is chosen, this one constant changes.
BASE_UNIT_USD  = 10.0
PLAY_NET_EDGE  = 0.05      # rain books are wide; the hurdle must be too
EDGE_1_5U      = 0.10      # 1.5u needs a double hurdle: edge AND p_win
PWIN_1_5U      = 0.55
LONGSHOT_PWIN  = 0.30      # below this, size is capped at 1u (favorite-longshot)
SUSPECT_EDGE   = 0.20      # a 20+ point edge on a binary is a red flag, cap 1u
MIN_OI         = 300.0
MAX_LEAD_DAYS  = 2         # Phase 1 trades lead 1-2 only; lead 0 is Phase 3
PRICE_RAIL_LO  = 0.05      # never play entries outside [0.05, 0.95]
PRICE_RAIL_HI  = 0.95
DAILY_UNIT_CAP = 4.0       # per target date, CUMULATIVE frozen (Nimbus capseed)
EVENT_UNIT_CAP = 1.5       # one binary market per event; hard per-play ceiling

# Rain model priors (Phase 2 learns these per city; constants pre-registered)
# Member wet threshold (mm). RECALIBRATED for the new rules on 2026-07-24.
#
# The Phase 1 value was 0.1mm ~ 0.004in, chosen deliberately BELOW the 0.01in
# gauge floor because trace also settled YES. That made "member > T_STAR" mean
# "trace or more", which is exactly what the old market paid on -- and it was
# well calibrated to it: measured against the OLD rule, mean p_raw 0.4229 vs
# observed 0.4072, bias only +0.0157.
#
# The new market pays only on MEASURABLE precip (>=0.01in = 0.254mm). Scored
# against that, the same threshold over-forecasts badly: mean p_raw 0.4229 vs
# observed 0.2895, bias +0.1335 over 2,387 city-days (6 cities, 2025-06-19 to
# 2026-07-21, as-issued lead-1 forecasts), over-forecasting in every bucket
# above 0.1 and in all 6 cities. In the drizzle regime the old edge lived in
# (0.1 <= p_raw < 0.5) it over-forecasts by 3.2x: predicted 0.239, observed
# 0.075 -- while old-rule observed there is 0.236, essentially equal to the
# forecast. The threshold was measuring a question Kalshi stopped asking.
#
# 0.254mm is the DEFINITIONAL value (the gauge floor). 1.0mm is the EMPIRICAL
# one: it minimises Brier (0.0919 vs 0.1228) and nearly zeroes the bias
# (+0.0112), because a grid cell is an areal average and over-produces light
# precip against a point gauge. The extra headroom absorbs that.
#
# PROVISIONAL: fitted on DETERMINISTIC models as a proxy, because Open-Meteo
# retains only ~3 days of past ensemble members, so a true EPS backtest is
# impossible. Direction is not in doubt (same sign in all 6 cities, stable
# across halves); the exact value is. The full wet-fraction curve is logged
# every run at THRESHOLDS_MM precisely so live new-rule settlements can revise
# this without a backfill. Discrimination is not the problem and the model
# should not be discarded: AUC 0.9344.
T_STAR_MM      = 1.0
THRESHOLDS_MM  = [0.05, 0.1, 0.2, 0.5, 1.0, 2.0]   # logged curve for Phase 2
# Trace no longer settles YES (Kalshi rules change 2026-07-16, see docstring).
# The floor is therefore ZERO: adding it would price an outcome that does not
# pay. Kept as a named constant rather than deleted so the report can show the
# retired term and the tests can assert it stays at zero while the new rules
# hold.
DEFAULT_TRACE_P = 0.0      # retired: trace settles NO under the KXRAIN rules
POP_CLAMP      = 0.03      # decision prob clamped into [0.03, 0.97]
# Uncalibrated-era humility: until a city has DIV_GUARD_MIN_N settlements, a
# model-vs-market gap wider than DIVERGENCE_GUARD is more likely our
# miscalibration than the market's error. No plays there. Auto-expires.
DIVERGENCE_GUARD = 0.35
DIV_GUARD_MIN_N  = 15

# Integrity gate (Nimbus 0.8 lineage, quarantine semantics)
GATE_MIN_MEMBERS = 90
GATE_MIN_MODELS  = 3

# Phase 2 learner activation gates (pre-registered now, inert in Phase 1)
CAL_MIN_N    = 30
CAL_LOOKBACK = 60

ENSEMBLE_MODELS = ["gfs025", "ecmwf_ifs025", "icon_seamless", "gem_global"]
MODEL_TAGS = {"gefs": "gfs025", "ecmwf": "ecmwf_ifs025",
              "icon": "icon_seamless", "gem": "gem_global"}

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drizzle_state.json")
DOCS_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
PAGE_URL   = os.environ.get("DRIZZLE_PAGE_URL", "")

_cfg_blob = repr((BASE_UNIT_USD, PLAY_NET_EDGE, EDGE_1_5U, PWIN_1_5U, LONGSHOT_PWIN,
                  SUSPECT_EDGE, MIN_OI, MAX_LEAD_DAYS, DAILY_UNIT_CAP, EVENT_UNIT_CAP,
                  T_STAR_MM, DEFAULT_TRACE_P, POP_CLAMP, DIVERGENCE_GUARD,
                  DIV_GUARD_MIN_N, GATE_MIN_MEMBERS, GATE_MIN_MODELS))
CONFIG_HASH = hashlib.sha1(_cfg_blob.encode()).hexdigest()[:8]

# ------------------------------- cities --------------------------------
# Kalshi consolidated every city into ONE series on 2026-07-16. The per-city
# series generations (KXRAINNYC / RAINNYC ...) are dead: they still exist in
# the catalog but have carried no open event since 2026-07-15. Cities are now
# identified by the market ticker SUFFIX inside a shared event, e.g.
# KXRAIN-26JUL24-NYC, so the old per-city series list is gone from this table.
RAIN_SERIES = "KXRAIN"
#
# code: (lat, lon, tz, std_offset_h, label, cli_station, trace_p)
# cli_station is the NWS CLI identifier the market rules name as the
# settlement station; it MUST appear in rules_primary or the city is
# quarantined. Two of these moved with the consolidation and are easy to get
# wrong: Chicago now settles on O'Hare (CLIORD), not Midway, and Houston on
# Bush Intercontinental (CLIIAH), not Hobby. Forecasting the old airport would
# quietly mis-price both.
#
# Coordinates are the GHCN-Daily station coordinates for exactly those gauges
# (ghcnd-stations.txt), not city centroids, so the ensemble is sampled where
# the settling gauge actually sits.
#
# trace_p is 0.0 everywhere: trace settles NO under the new rules.
CITIES = {
    "NYC":  (40.7789,  -73.9692,  "America/New_York",    -5, "New York City",  "CLINYC", 0.0),
    "CHI":  (41.9603,  -87.9317,  "America/Chicago",     -6, "Chicago",        "CLIORD", 0.0),
    "AUS":  (30.1831,  -97.6800,  "America/Chicago",     -6, "Austin",         "CLIAUS", 0.0),
    "MIA":  (25.7881,  -80.3169,  "America/New_York",    -5, "Miami",          "CLIMIA", 0.0),
    "DEN":  (39.8467, -104.6561,  "America/Denver",      -7, "Denver",         "CLIDEN", 0.0),
    "PHIL": (39.8733,  -75.2269,  "America/New_York",    -5, "Philadelphia",   "CLIPHL", 0.0),
    "LAX":  (33.9381, -118.3867,  "America/Los_Angeles", -8, "Los Angeles",    "CLILAX", 0.0),
    "LV":   (36.0719, -115.1633,  "America/Los_Angeles", -8, "Las Vegas",      "CLILAS", 0.0),
    "NOLA": (29.9975,  -90.2778,  "America/Chicago",     -6, "New Orleans",    "CLIMSY", 0.0),
    "SFO":  (37.6197, -122.3656,  "America/Los_Angeles", -8, "San Francisco",  "CLISFO", 0.0),
    "DC":   (38.8472,  -77.0344,  "America/New_York",    -5, "Washington DC",  "CLIDCA", 0.0),
    "SEA":  (47.4447, -122.3144,  "America/Los_Angeles", -8, "Seattle",        "CLISEA", 0.0),
    "BOS":  (42.3606,  -71.0097,  "America/New_York",    -5, "Boston",         "CLIBOS", 0.0),
    # Phoenix does not observe DST: America/Phoenix is -7 year round, so the
    # LST shift in fetch_members is a no-op there by construction.
    "PHX":  (33.4278, -112.0036,  "America/Phoenix",     -7, "Phoenix",        "CLIPHX", 0.0),
    "ATL":  (33.6297,  -84.4422,  "America/New_York",    -5, "Atlanta",        "CLIATL", 0.0),
    "MIN":  (44.8853,  -93.2314,  "America/Chicago",     -6, "Minneapolis",    "CLIMSP", 0.0),
    "DAL":  (32.8975,  -97.0219,  "America/Chicago",     -6, "Dallas",         "CLIDFW", 0.0),
    "SATX": (29.5442,  -98.4839,  "America/Chicago",     -6, "San Antonio",    "CLISAT", 0.0),
    "HOU":  (29.9844,  -95.3608,  "America/Chicago",     -6, "Houston",        "CLIIAH", 0.0),
    "OKC":  (35.3883,  -97.6003,  "America/Chicago",     -6, "Oklahoma City",  "CLIOKC", 0.0),
}

DOT = "\u00b7"
TODAY = dt.datetime.now(dt.timezone.utc).date()   # tests may override

# ------------------------------ helpers --------------------------------

def fget(url, timeout=40, tries=3):
    """GET with retry: Kalshi intermittently 503s bursty callers, and a
    swallowed 503 once turned a healthy market day into a zero-market abort
    during the Phase 1 build. Backoff 2s then 5s, then raise."""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "drizzle/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except Exception as ex:
            last = ex
            if i < tries - 1:
                time.sleep(2 if i == 0 else 5)
    raise last


def fee(p):
    """Kalshi quadratic taker fee RATE per contract (series verified fee_type
    quadratic, multiplier 1, same as Nimbus). Trade-level ceil applied at
    resolution."""
    return 0.07 * p * (1.0 - p)


def _wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    ph = k / n
    d = 1 + z * z / n
    c = ph + z * z / (2 * n)
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def qdollar(m, base):
    """Quote parser spanning BOTH Kalshi API generations: integer cents
    (`yes_bid`: 65) and dollars strings (`yes_bid_dollars`: "0.6500"). The rain
    series serves the dollars generation as of 2026-07-07; reading only the old
    fields returns None for every quote (the KXHIGH/KXHIGHT lesson, new hat)."""
    v = m.get(base + "_dollars")
    if v is not None:
        try:
            return float(v)
        except (TypeError, ValueError):
            pass
    v = m.get(base)
    if v is None:
        return None
    try:
        return float(v) / 100.0
    except (TypeError, ValueError):
        return None


def qfloat(m, *keys):
    for k in keys:
        v = m.get(k)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def parse_date_code(code):
    """'26JUL08' -> date(2026, 7, 8)."""
    mons = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
            "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}
    yy = int(code[:2]); mon = mons[code[2:5]]; dd = int(code[5:7])
    return dt.date(2000 + yy, mon, dd)


def parse_exp_value(raw):
    """Kalshi expiration_value for rain: '1.03', '0.00', or 'T' (Trace).
    Returns (amount_inches_float, is_trace)."""
    s = (str(raw) if raw is not None else "").strip()
    if s.upper().startswith("T"):
        return 0.0, True
    try:
        return float(s), False
    except ValueError:
        return None, False


def now_iso():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def state_key(code, target):
    return code + "|" + target

# ----------------------------- data fetch ------------------------------

def trace_rule_ok(rules):
    """True when the rules text still says trace counts as ZERO.

    This is the load-bearing check of the whole rewrite. The Phase 1 edge was
    'trace settles YES'; Kalshi inverted it on 2026-07-16. If Kalshi ever
    inverts it back, every probability this model produces is wrong again, so
    the regime is re-read from the live text on every run instead of being
    assumed. Unrecognised wording quarantines the city: silence is not
    consent."""
    r = " ".join((rules or "").lower().split())
    says_zero = ("counted as 0 inches" in r or "counted as zero inches" in r
                 or "count as 0 inches" in r)
    says_yes = ("for trace" in r and "resolves to yes" in r) or \
               ("trace" in r and "resolves to yes" in r and "counted as 0" not in r)
    return says_zero and not says_yes


def pull_rain_markets():
    """Pull open events from the consolidated KXRAIN series.

    One event per day holds one market per city (KXRAIN-26JUL24-NYC), so the
    city is read off the ticker SUFFIX rather than the series. Structural and
    rules verification happens here so the gate can quarantine on hard
    evidence, and a Kalshi city we have no coordinates for is skipped rather
    than guessed at.

    Raises on transport failure: main() must be able to tell 'Kalshi listed
    nothing today' (legitimate, this series lists irregularly) apart from 'we
    could not see', which must never publish as a quiet day."""
    d = fget("https://api.elections.kalshi.com/trade-api/v2/events"
             "?series_ticker=%s&status=open&with_nested_markets=true" % RAIN_SERIES)
    time.sleep(0.6)   # politeness: burst probing draws Kalshi 503s
    out = []
    for e in d.get("events", []):
        et = e.get("event_ticker", "")
        try:
            target = parse_date_code(et.rsplit("-", 1)[-1])
        except Exception:
            continue
        for m in e.get("markets", []):
            code = (m.get("ticker", "") or "").rsplit("-", 1)[-1]
            if code not in CITIES:
                continue   # Kalshi added a city we have no settlement gauge for
            station = CITIES[code][5]
            rules_p = m.get("rules_primary") or ""
            rules_s = m.get("rules_secondary") or ""
            rules = rules_p + " " + rules_s
            # Structure is now per-market inside a multi-city event: the binary
            # must still be the 'strictly greater than 0' leg.
            structure_ok = (m.get("strike_type") == "greater"
                            and float(m.get("floor_strike") or 0) == 0.0)
            traceok = trace_rule_ok(rules)
            station_ok = (station.lower() in rules.lower()
                          and "strictly greater than 0" in rules)
            out.append({
                "code": code, "series": RAIN_SERIES, "date": target,
                "event_ticker": et, "ticker": m.get("ticker", ""),
                "yb": qdollar(m, "yes_bid"), "ya": qdollar(m, "yes_ask"),
                "oi": qfloat(m, "open_interest_fp", "open_interest") or 0.0,
                "structure_ok": structure_ok, "station_ok": station_ok,
                "trace_rule_ok": traceok,
            })
    return out


def fetch_members(lat, lon, tz, stdh):
    """Per-member DAILY precip totals over the NWS CLI day (Local Standard
    Time midnight to midnight, year round; during DST that is 1:00 AM to
    12:59 AM clock time). Returns (totals_by_date {date: [mm,...]},
    utc_offset_seconds, per_model {model: {date: [mm,...]}})."""
    url = ("https://ensemble-api.open-meteo.com/v1/ensemble?latitude=%s&longitude=%s"
           "&hourly=precipitation&models=%s&timezone=%s&forecast_days=4"
           % (lat, lon, ",".join(ENSEMBLE_MODELS), tz.replace("/", "%2F")))
    d = fget(url)
    blocks = d if isinstance(d, list) else [d]
    totals = defaultdict(list)
    per_model = defaultdict(lambda: defaultdict(list))
    offset = None
    for b in blocks:
        off = b.get("utc_offset_seconds", stdh * 3600)
        if offset is None:
            offset = off
        shift_h = int(round((off - stdh * 3600) / 3600.0))   # DST shift back to LST
        h = b.get("hourly", {})
        times = h.get("time", [])
        for key, series in h.items():
            if not key.startswith("precipitation"):
                continue
            model = None
            for tag, name in MODEL_TAGS.items():
                if tag in key:
                    model = name
                    break
            if model is None:
                model = ENSEMBLE_MODELS[0]   # merged-block plain key fallback
            day_sum = defaultdict(float)
            ok = defaultdict(bool)
            for t, v in zip(times, series):
                if v is None:
                    continue
                ts = dt.datetime.fromisoformat(t) - dt.timedelta(hours=shift_h)
                day_sum[ts.date().isoformat()] += float(v)
                ok[ts.date().isoformat()] = True
            for day, s in day_sum.items():
                if ok[day]:
                    totals[day].append(s)
                    per_model[model][day].append(s)
    pm = {m: {d2: v for d2, v in days.items()} for m, days in per_model.items()}
    return dict(totals), (offset if offset is not None else stdh * 3600), pm


def fetch_ref(lat, lon, tz, stdh):
    """Evidence-only references (never touch scoring, sizing, or guards until
    a pre-registered promotion decision): NBM hourly PoP and precip. Returns
    {date: {nbm_pop_max, nbm_pop_day, nbm_precip}}."""
    try:
        url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
               "&hourly=precipitation_probability,precipitation&models=ncep_nbm_conus"
               "&timezone=%s&forecast_days=4" % (lat, lon, tz.replace("/", "%2F")))
        d = fget(url)
    except Exception:
        return {}
    h = d.get("hourly", {})
    off = d.get("utc_offset_seconds", stdh * 3600)
    shift_h = int(round((off - stdh * 3600) / 3600.0))
    out = defaultdict(lambda: {"pops": [], "precip": 0.0, "n": 0})
    for t, pop, pr in zip(h.get("time", []), h.get("precipitation_probability", []),
                          h.get("precipitation", [])):
        ts = dt.datetime.fromisoformat(t) - dt.timedelta(hours=shift_h)
        day = ts.date().isoformat()
        rec = out[day]
        if pop is not None:
            rec["pops"].append(float(pop) / 100.0)
        if pr is not None:
            rec["precip"] += float(pr)
        rec["n"] += 1
    res = {}
    for day, rec in out.items():
        if rec["n"] < 18 or not rec["pops"]:
            continue
        prod = 1.0
        for p in rec["pops"]:
            prod *= (1.0 - min(0.99, p))
        res[day] = {"nbm_pop_max": round(max(rec["pops"]), 3),
                    "nbm_pop_day": round(1.0 - prod, 3),
                    "nbm_precip": round(rec["precip"], 2)}
    return res


def fetch_settled_market(ticker):
    """Return (result, exp_value_raw) for a settled market, or None."""
    try:
        d = fget("https://api.elections.kalshi.com/trade-api/v2/markets/%s" % ticker)
        m = d.get("market", {})
        if m.get("status") == "settled" or m.get("result") in ("yes", "no"):
            if m.get("result") in ("yes", "no"):
                return m["result"], m.get("expiration_value", "")
    except Exception:
        pass
    return None

# ------------------------------- model ---------------------------------

def wet_curve(member_totals):
    """Fraction of members exceeding each logged threshold."""
    n = len(member_totals)
    if n == 0:
        return {}
    return {str(t): round(sum(1 for v in member_totals if v > t) / n, 4)
            for t in THRESHOLDS_MM}


def rain_prob(member_totals, trace_p):
    """p_raw = wet fraction at the T_STAR prior; final p adds the trace floor:
    P(record) = P(model wet) + P(model dry) x P(gauge records something anyway).

    The floor was the whole model in one line while trace settled YES. Under
    the rules in force since 2026-07-16 trace settles NO, so trace_p is 0 for
    every city and this reduces to p = p_raw. The term is kept (not deleted)
    because it is exactly what a future rules flip would need to switch back
    on, and because the report still scores the retired 'pooled + trace floor'
    source against the plain one."""
    n = len(member_totals)
    if n == 0:
        return None, None
    p_raw = sum(1 for v in member_totals if v > T_STAR_MM) / n
    p = p_raw + (1.0 - p_raw) * trace_p
    return round(p_raw, 4), round(min(1.0, p), 4)


def decision_prob(p):
    return min(1.0 - POP_CLAMP, max(POP_CLAMP, p))


def settled_count(state, code):
    return sum(1 for r in state.get("resolved", [])
               if r.get("code") == code and not r.get("gated"))

# ------------------------------- sizing --------------------------------

def size_play(net, p_win):
    """Nimbus sizing constitution on a binary: edge bands set the base, then
    plausibility and favorite-longshot caps shrink it. 2u does not exist in
    Phase 1 (no proven cities yet)."""
    if net < PLAY_NET_EDGE:
        return 0.0, "below edge floor"
    units, why = 1.0, "edge band"
    if net >= EDGE_1_5U and p_win >= PWIN_1_5U:
        units, why = 1.5, "strong edge + favorite"
    if net >= SUSPECT_EDGE:
        return 1.0, "suspect edge cap"
    if p_win < LONGSHOT_PWIN:
        return min(units, 1.0), "longshot cap"
    return units, why

# ------------------------------- engine --------------------------------

def score(state):
    """Build today's board. Returns (rows, plays, health)."""
    markets = pull_rain_markets()
    health = {"markets": len(markets), "cities": 0, "gated": [], "suppressed": [],
              "capped": 0, "failures": []}
    rows, plays = [], []
    frozen_this_run = set()

    # Seed cap budgets with EVERY already-frozen play per target (capseed):
    # the budgets bound cumulative frozen exposure, never per-run exposure.
    day_budget = defaultdict(float)
    for v in state["predictions"].values():
        for pl in v.get("plays", []):
            day_budget[v["target"]] += pl.get("units", 0.0)

    by_city = defaultdict(list)
    for m in markets:
        by_city[m["code"]].append(m)

    member_cache = {}
    for code, mkts in by_city.items():
        lat, lon, tz, stdh, label, station, trace_p = CITIES[code]
        try:
            if code not in member_cache:
                member_cache[code] = (fetch_members(lat, lon, tz, stdh),
                                      fetch_ref(lat, lon, tz, stdh))
            (totals, offset, per_model), refs = member_cache[code]
        except Exception as ex:
            health["failures"].append("%s fetch: %s" % (code, ex))
            continue
        health["cities"] += 1
        local_today = (dt.datetime.now(dt.timezone.utc)
                       + dt.timedelta(seconds=offset)).date()

        for m in sorted(mkts, key=lambda x: x["date"]):
            target = m["date"].isoformat()
            lead = (m["date"] - local_today).days
            if lead < 1 or lead > MAX_LEAD_DAYS:
                continue   # lead 0 is partially realized; deliberately unlogged
            key = state_key(code, target)
            mem = totals.get(target, [])
            models_present = sum(1 for mdl in ENSEMBLE_MODELS
                                 if per_model.get(mdl, {}).get(target))
            gated = None
            if not m["structure_ok"]:
                gated = "market structure"
            elif not m["station_ok"]:
                gated = "station rules text"
            elif not m.get("trace_rule_ok", False):
                # The settlement regime moved out from under the model: the
                # rules no longer say trace counts as zero. Every probability
                # here assumes it does, so sit the city out loudly rather than
                # price an event whose definition we can no longer read.
                gated = "trace rule changed"
            elif len(mem) < GATE_MIN_MEMBERS:
                gated = "thin ensemble (%d members)" % len(mem)
            elif models_present < GATE_MIN_MODELS:
                gated = "missing models (%d/4)" % models_present

            p_raw, p = rain_prob(mem, trace_p) if mem else (None, None)
            yb, ya = m["yb"], m["ya"]
            mid = round((yb + ya) / 2.0, 4) if yb is not None and ya is not None else None

            prev = state["predictions"].get(key)
            rec = prev if (prev and not prev.get("gated")) or (prev and gated) else None
            if rec is None:
                rec = {"code": code, "target": target, "first_logged": now_iso(),
                       "plays": [], "p_hist": []}
            if gated and rec.get("plays"):
                # never let a degraded rerun overwrite a record holding frozen
                # plays; keep the healthy record, skip this refresh entirely
                health["gated"].append("%s %s (frozen, refresh skipped: %s)" % (code, target, gated))
                continue
            rec.update({
                "event_ticker": m["event_ticker"], "ticker": m["ticker"],
                "series": m["series"], "logged_at": now_iso(), "lead": lead,
                "members": len(mem), "models": {mdl: {"n": len(per_model.get(mdl, {}).get(target, [])),
                                                       "wet": round(sum(1 for v in per_model.get(mdl, {}).get(target, []) if v > T_STAR_MM) / max(1, len(per_model.get(mdl, {}).get(target, []))), 4)}
                                                 for mdl in ENSEMBLE_MODELS},
                "p_raw": p_raw, "p": p, "curve": wet_curve(mem), "trace_p": trace_p,
                "ref": refs.get(target, {}), "yb": yb, "ya": ya, "mid": mid,
                "oi": m["oi"], "offset": offset, "model_version": MODEL_VERSION,
                "cfg": CONFIG_HASH,
            })
            if gated:
                rec["gated"] = gated
                rec["plays"] = rec.get("plays", [])
                health["gated"].append("%s %s (%s)" % (code, target, gated))
            else:
                rec.pop("gated", None)
            hist = rec.get("p_hist", [])
            if p is not None:
                hist.append([now_iso(), p])
                rec["p_hist"] = hist[-6:]
            state["predictions"][key] = rec
            if gated or p is None or mid is None:
                continue

            dp = decision_prob(p)
            n_set = settled_count(state, code)
            suppressed = None
            if n_set < DIV_GUARD_MIN_N and abs(dp - mid) > DIVERGENCE_GUARD:
                suppressed = "divergence %.2f at n=%d" % (abs(dp - mid), n_set)
                rec["suppressed"] = suppressed
                health["suppressed"].append("%s %s (%s)" % (code, target, suppressed))
            else:
                rec.pop("suppressed", None)

            # candidate plays, both sides, priced at the ask like Nimbus
            cands = []
            if ya is not None and PRICE_RAIL_LO <= ya <= PRICE_RAIL_HI:
                net = dp - ya - fee(ya) - 0.01
                cands.append(("Buy YES", ya, dp, net))
            if yb is not None:
                no_entry = round(1.0 - yb, 4)
                if PRICE_RAIL_LO <= no_entry <= PRICE_RAIL_HI:
                    net = (1.0 - dp) - no_entry - fee(no_entry) - 0.01
                    cands.append(("Buy NO", no_entry, round(1.0 - dp, 4), net))
            best = max(cands, key=lambda c: c[3]) if cands else None

            row = {"code": code, "label": label, "target": target, "lead": lead,
                   "p": p, "p_raw": p_raw, "mid": mid, "yb": yb, "ya": ya,
                   "oi": m["oi"], "members": len(mem), "gated": None,
                   "suppressed": suppressed, "ticker": m["ticker"],
                   "net": best[3] if best else None,
                   "side": best[0] if best else None}
            rows.append(row)

            if RESEARCH_MODE:
                # Log the prediction (above) but never size a play: the old
                # edge was deleted by the rules change and the new regime has
                # no calibration yet. The board still shows model vs market.
                continue
            if suppressed or best is None or m["oi"] < MIN_OI:
                continue
            side, entry, p_win, net = best
            units, why = size_play(net, p_win)
            if units <= 0:
                continue
            if rec.get("plays"):
                continue   # frozen: first non-empty log wins forever
            units = min(units, EVENT_UNIT_CAP)
            room = DAILY_UNIT_CAP - day_budget[target]
            if room <= 1e-9:
                health["capped"] += 1
                continue
            units = min(units, room)
            stake = round(units * BASE_UNIT_USD, 2)
            play = {"ticker": m["ticker"], "side": side, "entry": entry,
                    "net": round(net, 4), "edge": round(p_win - entry, 4),
                    "units": units, "stake": stake, "p_win": round(p_win, 4),
                    "prob": p, "mid": mid, "why": why}
            rec["plays"] = [play]
            rec["plays_lead"] = lead
            rec["plays_logged_at"] = now_iso()
            rec["plays_model_version"] = MODEL_VERSION
            frozen_this_run.add(key)
            day_budget[target] += units
            plays.append(dict(play, code=code, label=label, target=target,
                              date=target, lead=lead))
    plays.sort(key=lambda p: (-p["units"], -p["p_win"], -p["net"], p["ticker"]))
    return rows, plays, health

# ----------------------------- resolution ------------------------------

def resolve_pending(state):
    done = []
    for key, rec in list(state["predictions"].items()):
        target = dt.date.fromisoformat(rec["target"])
        if target >= TODAY:
            continue
        settled = fetch_settled_market(rec["ticker"])
        if not settled:
            continue
        result, exp_raw = settled
        amount, trace = parse_exp_value(exp_raw)
        outcome = 1 if result == "yes" else 0
        res = {"code": rec["code"], "target": rec["target"], "lead": rec.get("lead"),
               "outcome": outcome, "exp_val": str(exp_raw), "amount": amount,
               "trace": trace, "p": rec.get("p"), "p_raw": rec.get("p_raw"),
               "curve": rec.get("curve", {}), "trace_p": rec.get("trace_p"),
               "members": rec.get("members"), "models": rec.get("models", {}),
               "ref": rec.get("ref", {}), "mid": rec.get("mid"),
               "model_version": rec.get("model_version"),
               "first_logged": rec.get("first_logged"), "cfg": rec.get("cfg"),
               "p_hist": rec.get("p_hist", []), "plays": []}
        if rec.get("gated"):
            res["gated"] = rec["gated"]
        if rec.get("suppressed"):
            res["suppressed"] = rec["suppressed"]
        for pl in rec.get("plays", []):
            won = (outcome == 1) if pl["side"] == "Buy YES" else (outcome == 0)
            contracts = int(pl["stake"] // pl["entry"]) if pl["entry"] > 0 else 0
            trade_fee = math.ceil(0.07 * contracts * pl["entry"] * (1 - pl["entry"]) * 100) / 100.0
            pnl = round(contracts * (1 - pl["entry"]) - trade_fee, 2) if won \
                else round(-contracts * pl["entry"] - trade_fee, 2)
            close_mid = rec.get("mid")
            clv = None
            if close_mid is not None and pl.get("mid") is not None:
                mv = close_mid - pl["mid"]
                clv = round(mv if pl["side"] == "Buy YES" else -mv, 4)
            res["plays"].append(dict(pl, won=won, contracts=contracts, pnl=pnl,
                                     close_mid=close_mid, clv=clv,
                                     outcome=outcome, target=rec["target"],
                                     lead=rec.get("plays_lead", rec.get("lead")),
                                     model_version=rec.get("plays_model_version",
                                                           rec.get("model_version"))))
        state["resolved"].append(res)
        done.append(key)
    for key in done:
        del state["predictions"][key]
    return len(done)

# ------------------------------ reporting ------------------------------

def _bootstrap_roi(day_pnls, day_stakes, B=800):
    """Deterministic block bootstrap BY TARGET DAY (Nimbus batch 8/10 standard).
    Seeded from the data itself so identical state gives identical intervals."""
    days = sorted(day_pnls)
    if len(days) < 3:
        return None
    seed = int(hashlib.sha1(json.dumps([(d, day_pnls[d]) for d in days]).encode())
               .hexdigest()[:12], 16)
    rois = []
    s = seed
    for _ in range(B):
        tot_p = tot_s = 0.0
        for _ in range(len(days)):
            s = (s * 6364136223846793005 + 1442695040888963407) % (1 << 64)
            d = days[(s >> 16) % len(days)]
            tot_p += day_pnls[d]; tot_s += day_stakes[d]
        rois.append(tot_p / tot_s if tot_s else 0.0)
    rois.sort()
    return (round(rois[int(0.05 * B)] * 100, 1), round(rois[int(0.95 * B)] * 100, 1))


def compute_report(state):
    res = [r for r in state.get("resolved", []) if not r.get("gated")]
    rep = {"n_events": len(res), "n_gated": len(state.get("resolved", [])) - len(res)}
    if not res:
        return rep
    # Brier, model vs market
    bm = [(r["p"] - r["outcome"]) ** 2 for r in res if r.get("p") is not None]
    bk = [(r["mid"] - r["outcome"]) ** 2 for r in res if r.get("mid") is not None]
    if bm:
        rep["brier_model"] = round(sum(bm) / len(bm), 4)
    if bk:
        rep["brier_market"] = round(sum(bk) / len(bk), 4)
    # calibration bins with Wilson
    bins = defaultdict(lambda: [0, 0, 0.0])
    for r in res:
        if r.get("p") is None:
            continue
        b = min(9, int(r["p"] * 10))
        bins[b][0] += 1; bins[b][1] += r["outcome"]; bins[b][2] += r["p"]
    rep["bins"] = []
    for b in sorted(bins):
        n, k, ps = bins[b]
        lo, hi = _wilson(k, n)
        stated = ps / n
        rep["bins"].append({"bin": "%d0-%d9%%" % (b, b), "n": n, "stated": round(stated, 3),
                            "actual": round(k / n, 3), "wlo": round(lo, 3),
                            "whi": round(hi, 3), "flag": not (lo <= stated <= hi)})
    # per city
    perc = defaultdict(lambda: {"n": 0, "wet": 0, "trace": 0, "psum": 0.0,
                                "bm": 0.0, "bk": 0.0, "nb": 0})
    for r in res:
        c = perc[r["code"]]
        c["n"] += 1; c["wet"] += r["outcome"]; c["trace"] += 1 if r.get("trace") else 0
        if r.get("p") is not None:
            c["psum"] += r["p"]
        if r.get("p") is not None and r.get("mid") is not None:
            c["bm"] += (r["p"] - r["outcome"]) ** 2
            c["bk"] += (r["mid"] - r["outcome"]) ** 2
            c["nb"] += 1
    rep["by_city"] = {k: {"n": v["n"], "wet_rate": round(v["wet"] / v["n"], 3),
                          "trace": v["trace"], "mean_p": round(v["psum"] / v["n"], 3),
                          "brier_gap": round((v["bm"] - v["bk"]) / v["nb"], 4) if v["nb"] else None}
                      for k, v in perc.items()}
    # forecast sources Brier (evidence table for the Phase 2 promotion decision)
    src = defaultdict(lambda: [0.0, 0])
    for r in res:
        o = r["outcome"]
        if r.get("p") is not None:
            src["Pooled + trace floor"][0] += (r["p"] - o) ** 2; src["Pooled + trace floor"][1] += 1
        if r.get("p_raw") is not None:
            src["Pooled raw"][0] += (r["p_raw"] - o) ** 2; src["Pooled raw"][1] += 1
        nb = (r.get("ref") or {}).get("nbm_pop_day")
        if nb is not None:
            src["NBM PoP (day)"][0] += (nb - o) ** 2; src["NBM PoP (day)"][1] += 1
        for mdl, mv in (r.get("models") or {}).items():
            if mv.get("n"):
                src[mdl][0] += (mv["wet"] - o) ** 2; src[mdl][1] += 1
        if r.get("mid") is not None:
            src["Market mid"][0] += (r["mid"] - o) ** 2; src["Market mid"][1] += 1
    rep["sources"] = sorted(((k, round(s / n, 4), n) for k, (s, n) in src.items() if n),
                            key=lambda x: x[1])
    # plays
    pls = [p for r in res for p in r.get("plays", [])]
    rep["n_plays"] = len(pls)
    if pls:
        w = sum(1 for p in pls if p["won"])
        stake = sum(p["stake"] for p in pls); pnl = sum(p["pnl"] for p in pls)
        rep["record"] = "%d-%d" % (w, len(pls) - w)
        rep["units_risked"] = round(stake / BASE_UNIT_USD, 2)
        rep["units_net"] = round(pnl / BASE_UNIT_USD, 2)
        rep["roi"] = round(pnl / stake * 100, 1) if stake else 0.0
        # honesty pair: stated post-cost edge vs realized, cents per contract
        st_c = [p["net"] * 100 for p in pls]
        rl_c = [p["pnl"] / p["contracts"] * 100 for p in pls if p.get("contracts")]
        rep["edge_stated"] = round(sum(st_c) / len(st_c), 2)
        rep["edge_realized"] = round(sum(rl_c) / len(rl_c), 2) if rl_c else None
        # CLV
        cl = [p["clv"] for p in pls if p.get("clv") is not None]
        rep["clv"] = {"n": len(cl),
                      "beat": round(sum(1 for c in cl if c > 0) / len(cl), 3) if cl else None,
                      "avg": round(sum(cl) / len(cl), 4) if cl else None}
        dp, ds = defaultdict(float), defaultdict(float)
        for p in pls:
            dp[p.get("target", "?")] += p["pnl"]; ds[p.get("target", "?")] += p["stake"]
        rep["roi_ci"] = _bootstrap_roi(dp, ds)
        eras = defaultdict(lambda: [0, 0, 0.0, 0.0])
        for p in pls:
            e = eras[p.get("model_version") or "unknown"]
            e[0] += 1; e[1] += 1 if p["won"] else 0; e[2] += p["stake"]; e[3] += p["pnl"]
        rep["eras"] = sorted(
            (("Drizzle v1+" if str(k).startswith("2026") else str(k),
              n, w2, round(s / BASE_UNIT_USD, 1), round(pn / BASE_UNIT_USD, 2))
             for k, (n, w2, s, pn) in eras.items()), key=lambda x: x[0])
    # cumulative units series for the chart
    series, cum = [], 0.0
    for r in sorted(res, key=lambda r: r["target"]):
        for p in r.get("plays", []):
            cum += p["pnl"] / BASE_UNIT_USD
        series.append(cum)
    rep["cum_units"] = [round(x, 2) for x in series]
    # alarms
    alarms = []
    for b in rep.get("bins", []):
        if b["flag"] and b["n"] >= 25:
            alarms.append("bin %s off stated (n=%d)" % (b["bin"], b["n"]))
    trn = sum(1 for r in res if r.get("trace"))
    if len(res) >= 20:
        lo, hi = _wilson(trn, len(res))
        # trace share sanity vs the seeded priors, coarse first pass
        if lo > 0.35 or hi < 0.02:
            alarms.append("trace share %.0f%% outside prior band" % (trn / len(res) * 100))
    rep["alarms"] = alarms
    return rep

# ------------------------------- render --------------------------------

CSS = """
:root{--bg:#0d1117;--card:#161b22;--line:#21262d;--txt:#e6edf3;--dim:#8b949e;
--green:#3fb950;--red:#f85149;--amber:#d29922;--gold:#e3b341;--blue:#58a6ff;}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--txt);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;padding:12px;max-width:760px;margin:0 auto}
a{color:var(--blue);text-decoration:none}
h1{font-size:22px;margin:4px 0} .sub{color:var(--dim);font-size:12px;margin-bottom:10px}
.nav{display:flex;gap:8px;margin:10px 0}
.nav a{background:var(--card);border:1px solid var(--line);padding:7px 14px;border-radius:8px;font-size:14px}
.nav a.on{border-color:var(--blue);color:var(--txt)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin:10px 0}
.range{font-size:20px;font-weight:700}
.side{font-size:26px;font-weight:800;letter-spacing:1px}
.side.yes{color:var(--green)} .side.no{color:var(--red)}
.bar{display:flex;gap:14px;align-items:center;margin:8px 0;font-size:15px}
.units{font-weight:700;padding:2px 10px;border-radius:6px;background:#1f2937}
.u15{color:var(--gold)} .u10{color:var(--amber)}
.small{color:var(--dim);font-size:12px}
.banner{background:#7a2d00;color:#ffd8a8;border:1px solid #b35900;border-radius:10px;padding:10px;margin:10px 0;font-size:14px;display:none}
.chip{display:inline-block;background:#1f2937;border:1px solid var(--line);border-radius:20px;padding:3px 10px;font-size:12px;color:var(--dim);margin:2px 4px 2px 0}
.chip.warn{color:var(--amber);border-color:var(--amber)}
table{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0}
th,td{padding:6px 8px;text-align:left;border-bottom:1px solid var(--line)}
th{color:var(--dim);font-weight:600}
.pos{color:var(--green)} .neg{color:var(--red)} .flag{color:var(--red);font-weight:700}
.tile{display:inline-block;background:#10161d;border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:4px 6px 4px 0;min-width:120px}
.tile .v{font-size:20px;font-weight:700} .tile .k{color:var(--dim);font-size:11px}
"""

STALE_JS = """<script>
(function(){var e=%d,h=(Date.now()/1000-e)/3600;
if(h>16){var b=document.getElementById('stale');b.style.display='block';
b.textContent='This board was built '+h.toFixed(0)+' hours ago. A run or deploy failed. Do not bet from it.';}})();
</script>"""


def _page(title, body, epoch):
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>%s</title><style>%s</style></head><body>"
            "<div id='stale' class='banner'></div>%s%s</body></html>"
            % (title, CSS, body, STALE_JS % epoch))


def _nav(on):
    return ("<div class='nav'><a href='index.html' class='%s'>Today's plays</a>"
            "<a href='results.html' class='%s'>Results</a></div>"
            % ("on" if on == "bets" else "", "on" if on == "results" else ""))


def render_bets(rows, plays, health, rep):
    epoch = int(dt.datetime.now(dt.timezone.utc).timestamp())
    h = ["<h1>Drizzle %s daily rain</h1>" % DOT,
         "<div class='sub'>%s %s %s %s cfg %s</div>"
         % (now_iso(), DOT, MODEL_VERSION, DOT, CONFIG_HASH), _nav("bets")]
    chips = ["<span class='chip'>%d markets</span>" % health["markets"],
             "<span class='chip'>%d cities</span>" % health["cities"]]
    for g in health["gated"]:
        chips.append("<span class='chip warn'>sat out: %s</span>" % g)
    for s in health["suppressed"]:
        chips.append("<span class='chip warn'>guarded: %s</span>" % s)
    if health["capped"]:
        chips.append("<span class='chip warn'>cap trimmed %d</span>" % health["capped"])
    for f in health["failures"]:
        chips.append("<span class='chip warn'>%s</span>" % f)
    h.append("<div>%s</div>" % "".join(chips))
    # The page must say out loud that the thesis it was built on is gone.
    # Anyone opening this on a phone should not have to read the source to
    # learn that no plays are coming and why.
    if RESEARCH_MODE:
        h.append(
            "<div class='card'><b>Research mode %s no plays</b>"
            "<div class='small'>Kalshi replaced the per-city rain series with "
            "the shared KXRAIN series on 2026-07-16 and inverted the "
            "settlement rule: &ldquo;Trace amounts (T) and missing daily "
            "precipitation values are counted as 0 inches&rdquo;, so a trace "
            "day now settles NO. It used to settle YES, and that was this "
            "model's entire edge. The trace floor is switched off and no plays "
            "are sized until calibration has been rebuilt under the new rules. "
            "The board below is model vs market for measurement only %s do not "
            "bet it.</div></div>" % (DOT, DOT))
    if health.get("no_listing"):
        h.append("<div class='card'><b>No markets listed</b><div class='small'>"
                 "Kalshi published no open rain event for today. The KXRAIN "
                 "series lists irregularly (2026-07-16 and 07-18 to 07-21 were "
                 "never listed). This is an empty board, not a quiet-day "
                 "claim and not a failed fetch.</div></div>")
    if plays:
        for p in plays:
            cls = "yes" if p["side"] == "Buy YES" else "no"
            ucls = "u15" if p["units"] >= 1.5 else "u10"
            h.append(
                "<div class='card'><div class='range'>%s rain %s %s (lead %d)</div>"
                "<div class='side %s'>%s</div>"
                "<div class='bar'><span class='units %s'>%.1fu</span>"
                "<span>@ %d\u00a2</span><span>win %d%%</span></div>"
                "<div class='small'>model %d%% (raw %d%%) %s market %d%% %s net +%.1f\u00a2 %s OI %d %s %s</div></div>"
                % (p["label"], DOT, p["target"], p["lead"], cls, p["side"].upper(),
                   ucls, p["units"], round(p["entry"] * 100), round(p["p_win"] * 100),
                   round(p["prob"] * 100), round(next((r["p_raw"] for r in rows if r["ticker"] == p["ticker"]), 0) * 100),
                   DOT, round(p["mid"] * 100), DOT, p["net"] * 100, DOT,
                   int(next((r["oi"] for r in rows if r["ticker"] == p["ticker"]), 0)), DOT, p["why"]))
    else:
        h.append("<div class='card'><b>No plays today.</b><div class='small'>"
                 "A sit-out day is a correct, valuable output. The board below shows why.</div></div>")
    h.append("<h1 style='font-size:16px;margin-top:16px'>Full board</h1><table>"
             "<tr><th>City</th><th>Date</th><th>Model</th><th>Raw</th><th>Market</th>"
             "<th>Best net</th><th>OI</th><th>Note</th></tr>")
    for r in sorted(rows, key=lambda r: (r["target"], r["code"])):
        note = r["suppressed"] or ("-" if r["net"] is None else r["side"] or "-")
        h.append("<tr><td>%s</td><td>%s</td><td>%d%%</td><td>%d%%</td><td>%d%%</td>"
                 "<td>%s</td><td>%d</td><td class='small'>%s</td></tr>"
                 % (r["code"], r["target"][5:], round((r["p"] or 0) * 100),
                    round((r["p_raw"] or 0) * 100), round((r["mid"] or 0) * 100),
                    ("%.1f\u00a2" % (r["net"] * 100)) if r["net"] is not None else "-",
                    int(r["oi"]), note))
    h.append("</table><div class='small'>Trace floor is RETIRED: Kalshi's rules "
             "changed on 2026-07-16 and trace now counts as 0 inches, so a "
             "trace day settles NO. Model %% is the plain ensemble wet "
             "fraction with nothing added. No plays are sized while the "
             "calibration is rebuilt under the new rules.</div>")
    return _page("Drizzle %s plays" % DOT, "".join(h), epoch)


def svg_line(vals, w=680, hgt=120):
    if len(vals) < 2:
        return "<div class='small'>Chart appears after 2+ settled days.</div>"
    lo, hi = min(vals + [0]), max(vals + [0])
    rng = (hi - lo) or 1
    pts = " ".join("%.1f,%.1f" % (i * w / (len(vals) - 1),
                                  hgt - (v - lo) / rng * (hgt - 10) - 5)
                   for i, v in enumerate(vals))
    zero = hgt - (0 - lo) / rng * (hgt - 10) - 5
    return ("<svg viewBox='0 0 %d %d' style='width:100%%;height:auto'>"
            "<line x1='0' y1='%.1f' x2='%d' y2='%.1f' stroke='#30363d'/>"
            "<polyline points='%s' fill='none' stroke='#58a6ff' stroke-width='2'/></svg>"
            % (w, hgt, zero, w, zero, pts))


def render_results(state, rep):
    epoch = int(dt.datetime.now(dt.timezone.utc).timestamp())
    h = ["<h1>Drizzle %s results</h1>" % DOT,
         "<div class='sub'>%s %s %s %s cfg %s</div>"
         % (now_iso(), DOT, MODEL_VERSION, DOT, CONFIG_HASH), _nav("results")]
    for a in rep.get("alarms", []):
        h.append("<span class='chip warn'>%s</span>" % a)
    if not rep.get("n_events"):
        h.append("<div class='card'>No settled events yet. Results appear the "
                 "morning after each market's target day, from Kalshi's official "
                 "settlement.</div>")
        return _page("Drizzle results", "".join(h), epoch)
    t = []
    def tile(k, v, cls=""):
        t.append("<span class='tile'><div class='v %s'>%s</div><div class='k'>%s</div></span>" % (cls, v, k))
    tile("Settled events", rep["n_events"])
    if rep.get("brier_model") is not None and rep.get("brier_market") is not None:
        gap = rep["brier_model"] - rep["brier_market"]
        tile("Brier model", "%.4f" % rep["brier_model"], "pos" if gap < 0 else "neg")
        tile("Brier market", "%.4f" % rep["brier_market"])
    if rep.get("n_plays"):
        tile("Record", rep["record"])
        tile("Net units", "%+.2fu" % rep["units_net"],
             "pos" if rep["units_net"] >= 0 else "neg")
        tile("ROI", "%+.1f%%" % rep["roi"], "pos" if rep["roi"] >= 0 else "neg")
        if rep.get("roi_ci"):
            tile("ROI 90% CI", "%s%% to %s%%" % rep["roi_ci"])
        if rep.get("edge_realized") is not None:
            tile("Stated edge/ct", "%+.1f\u00a2" % rep["edge_stated"])
            tile("Realized/ct", "%+.1f\u00a2" % rep["edge_realized"],
                 "pos" if rep["edge_realized"] >= 0 else "neg")
        clv = rep.get("clv", {})
        if clv.get("n"):
            tile("CLV beat rate", "%d%% (n=%d)" % (round((clv["beat"] or 0) * 100), clv["n"]))
            tile("Avg CLV", "%+.1f\u00a2" % ((clv["avg"] or 0) * 100))
    h.append("<div>%s</div>" % "".join(t))
    h.append("<div class='card'><b>Cumulative units</b>%s</div>"
             % svg_line(rep.get("cum_units", [])))
    if rep.get("bins"):
        h.append("<div class='card'><b>Calibration</b> <span class='small'>stated "
                 "probability vs realized rain frequency, Wilson 95%</span><table>"
                 "<tr><th>Bin</th><th>n</th><th>Stated</th><th>Actual</th><th>Wilson</th></tr>")
        for b in rep["bins"]:
            h.append("<tr><td>%s</td><td>%d</td><td%s>%d%%</td><td>%d%%</td>"
                     "<td class='small'>%d-%d%%</td></tr>"
                     % (b["bin"], b["n"], " class='flag'" if b["flag"] else "",
                        round(b["stated"] * 100), round(b["actual"] * 100),
                        round(b["wlo"] * 100), round(b["whi"] * 100)))
        h.append("</table></div>")
    if rep.get("by_city"):
        h.append("<div class='card'><b>By city</b><table><tr><th>City</th><th>n</th>"
                 "<th>Wet rate</th><th>Trace days</th><th>Mean model</th><th>Brier gap</th></tr>")
        for c, v in sorted(rep["by_city"].items()):
            g = v["brier_gap"]
            h.append("<tr><td>%s</td><td>%d</td><td>%d%%</td><td>%d</td><td>%d%%</td>"
                     "<td class='%s'>%s</td></tr>"
                     % (c, v["n"], round(v["wet_rate"] * 100), v["trace"],
                        round(v["mean_p"] * 100),
                        "pos" if (g or 0) < 0 else "neg",
                        ("%+.4f" % g) if g is not None else "-"))
        h.append("</table><div class='small'>Negative Brier gap = model beating "
                 "the market. Trace days USED to be the thesis; under the "
                 "rules in force since 2026-07-16 they settle NO, so the trace "
                 "column now counts days the old model would have won and the "
                 "new one must not bet.</div></div>")
    if rep.get("sources"):
        h.append("<div class='card'><b>Forecast sources</b> <span class='small'>"
                 "Brier per source; the Phase 2 promotion decision reads from here"
                 "</span><table><tr><th>Source</th><th>Brier</th><th>n</th></tr>")
        for k, v, n in rep["sources"]:
            h.append("<tr><td>%s</td><td>%.4f</td><td>%d</td></tr>" % (k, v, n))
        h.append("</table></div>")
    if rep.get("eras"):
        h.append("<div class='card'><b>By model era</b><table><tr><th>Era</th>"
                 "<th>Plays</th><th>W</th><th>Risked</th><th>Net</th></tr>")
        for e, n, w, s, pn in rep["eras"]:
            h.append("<tr><td>%s</td><td>%d</td><td>%d</td><td>%.1fu</td>"
                     "<td class='%s'>%+.2fu</td></tr>"
                     % (e, n, w, s, "pos" if pn >= 0 else "neg", pn))
        h.append("</table></div>")
    # raw table
    h.append("<div class='card'><b>Raw settlements</b><table><tr><th>Date</th>"
             "<th>City</th><th>Model</th><th>Mkt</th><th>Result</th><th>Amount</th>"
             "<th>Play</th><th>P&L</th></tr>")
    for r in sorted(state.get("resolved", []), key=lambda r: r["target"], reverse=True)[:60]:
        pl = r["plays"][0] if r.get("plays") else None
        h.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                 "<td class='%s'>%s%s</td><td>%s</td><td>%s</td><td class='%s'>%s</td></tr>"
                 % (r["target"][5:], r["code"],
                    ("%d%%" % round(r["p"] * 100)) if r.get("p") is not None else "-",
                    ("%d%%" % round(r["mid"] * 100)) if r.get("mid") is not None else "-",
                    "pos" if r["outcome"] else "neg",
                    "RAIN" if r["outcome"] else "DRY",
                    " (T)" if r.get("trace") else "",
                    r.get("exp_val", "-"),
                    (pl["side"] + " %.1fu" % pl["units"]) if pl else
                    ("gated" if r.get("gated") else ("guarded" if r.get("suppressed") else "-")),
                    ("pos" if pl["pnl"] >= 0 else "neg") if pl else "small",
                    ("%+.2fu" % (pl["pnl"] / BASE_UNIT_USD)) if pl else "-"))
    h.append("</table></div>")
    return _page("Drizzle results", "".join(h), epoch)

# ------------------------------- notify --------------------------------

def notify(plays, rep):
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        return
    try:
        if plays:
            top = plays[0]
            msg = ("Drizzle: %d play(s). Top: %s %s %s %.1fu @ %d\u00a2 (win %d%%). %s"
                   % (len(plays), top["label"], top["side"], top["target"],
                      top["units"], round(top["entry"] * 100),
                      round(top["p_win"] * 100), PAGE_URL))
        else:
            msg = "Drizzle: no plays today. %s" % PAGE_URL
        data = json.dumps({"chat_id": chat, "text": msg}).encode()
        req = urllib.request.Request(
            "https://api.telegram.org/bot%s/sendMessage" % tok, data=data,
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=15)
    except Exception:
        pass   # notifier failures are never fatal

# -------------------------------- state --------------------------------

def load_state():
    if not os.path.exists(STATE_PATH):
        return {"predictions": {}, "resolved": []}
    try:
        with open(STATE_PATH) as f:
            st = json.load(f)
    except Exception:
        print("FATAL: drizzle_state.json is corrupted. Restore it from git "
              "history; refusing to run rather than wipe the track record.")
        sys.exit(3)
    if not isinstance(st.get("predictions"), dict) or not isinstance(st.get("resolved"), list):
        print("FATAL: drizzle_state.json has the wrong shape. Restore from git history.")
        sys.exit(3)
    return st


def save_state(st):
    with open(STATE_PATH, "w") as f:
        json.dump(st, f, indent=1)

# --------------------------------- main ---------------------------------

def main():
    ci = os.environ.get("CI") == "true"
    state = load_state()
    n_res = resolve_pending(state)
    try:
        rows, plays, health = score(state)
    except Exception as ex:
        # Could not see the market at all. This is the case the original
        # zero-market abort existed for, and it stays fatal.
        print("FATAL: could not read the Kalshi rain series (%s). Refusing to "
              "publish a fake quiet day." % ex)
        sys.exit(2)
    # A successful read that returns no open events is NOT a failure: the
    # consolidated KXRAIN series lists irregularly (2026-07-16 and 07-18..07-21
    # were never listed at all, 404 on the event). Treating that as fatal is
    # what kept the run red for days. Publish an explicitly empty board
    # instead, so the page says 'Kalshi listed nothing' rather than inventing
    # a quiet day or failing silently.
    if health["markets"] == 0:
        if health["failures"]:
            print("FATAL: rain markets unreadable: %s" % "; ".join(health["failures"]))
            sys.exit(2)
        health["no_listing"] = True
        print("No open rain markets listed by Kalshi for today. "
              "Publishing an empty board (this series lists irregularly).")
    rep = compute_report(state)
    save_state(state)
    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(os.path.join(DOCS_DIR, "index.html"), "w") as f:
        f.write(render_bets(rows, plays, health, rep))
    with open(os.path.join(DOCS_DIR, "results.html"), "w") as f:
        f.write(render_results(state, rep))
    notify(plays, rep)
    print("Drizzle %s %s cfg %s" % (MODEL_VERSION, DOT, CONFIG_HASH))
    print("resolved %d %s markets %d %s plays %d %s gated %d %s suppressed %d"
          % (n_res, DOT, health["markets"], DOT, len(plays), DOT,
             len(health["gated"]), DOT, len(health["suppressed"])))
    for p in plays:
        print("  %s %s %s %s %.1fu @ %.0fc win %.0f%%"
              % (p["code"], p["target"], p["side"], DOT, p["units"],
                 p["entry"] * 100, p["p_win"] * 100))
    if not ci:
        import webbrowser
        webbrowser.open("file://" + os.path.join(DOCS_DIR, "index.html"))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as ex:
        print("FATAL: %s" % ex)
        sys.exit(1)
