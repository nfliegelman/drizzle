"""Drizzle self-test suite (Phase 1).

Nimbus pattern: every assertion the build proved by hand lives in a committed,
network-free harness that CI runs BEFORE every board generation. If any test
fails, the workflow goes red and nothing publishes. Zero network: every fetcher
is monkeypatched; anything that slips through raises loudly.

Run: python test_drizzle.py       (stdlib unittest only, ~1 second)
"""
import unittest, os, sys, json, math, tempfile, datetime as dtm

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drizzle as dz


def _no_network(*a, **k):
    raise AssertionError("network call escaped the test harness")


class TestMath(unittest.TestCase):
    def test_fee_rate_exact(self):
        self.assertAlmostEqual(dz.fee(0.5), 0.0175, places=6)
        self.assertAlmostEqual(dz.fee(0.3), 0.07 * 0.3 * 0.7, places=6)

    def test_wilson(self):
        lo, hi = dz._wilson(7, 10)
        self.assertTrue(0.39 < lo < 0.42 and 0.88 < hi < 0.92)

    def test_trace_floor(self):
        # 100 members, 40 wet at t*: p_raw 0.40; trace floor 0.15 lifts the dry
        # remainder: p = 0.40 + 0.60 * 0.15 = 0.49
        mem = [1.0] * 40 + [0.0] * 60
        p_raw, p = dz.rain_prob(mem, 0.15)
        self.assertAlmostEqual(p_raw, 0.40, places=4)
        self.assertAlmostEqual(p, 0.49, places=4)
        # all-dry members: the floor IS the probability
        p_raw2, p2 = dz.rain_prob([0.0] * 100, 0.15)
        self.assertEqual(p_raw2, 0.0)
        self.assertAlmostEqual(p2, 0.15, places=4)

    def test_decision_clamp(self):
        self.assertEqual(dz.decision_prob(0.001), dz.POP_CLAMP)
        self.assertEqual(dz.decision_prob(0.999), 1 - dz.POP_CLAMP)
        self.assertEqual(dz.decision_prob(0.5), 0.5)

    def test_exp_value_parsing(self):
        self.assertEqual(dz.parse_exp_value("1.03"), (1.03, False))
        self.assertEqual(dz.parse_exp_value("T"), (0.0, True))
        self.assertEqual(dz.parse_exp_value(" t "), (0.0, True))
        self.assertEqual(dz.parse_exp_value("0.00"), (0.0, False))

    def test_date_code(self):
        self.assertEqual(dz.parse_date_code("26JUL08"), dtm.date(2026, 7, 8))
        self.assertEqual(dz.parse_date_code("27JAN01"), dtm.date(2027, 1, 1))


class TestQuoteParsing(unittest.TestCase):
    def test_dual_generation_quotes(self):
        # dollars-string generation (live on KXRAIN as of 2026-07-07)
        m = {"yes_bid_dollars": "0.6500", "yes_ask_dollars": "0.6700",
             "open_interest_fp": "10495.04"}
        self.assertAlmostEqual(dz.qdollar(m, "yes_bid"), 0.65)
        self.assertAlmostEqual(dz.qdollar(m, "yes_ask"), 0.67)
        self.assertAlmostEqual(dz.qfloat(m, "open_interest_fp", "open_interest"), 10495.04)
        # integer-cents generation (Nimbus-era fields)
        m2 = {"yes_bid": 65, "yes_ask": 67, "open_interest": 500}
        self.assertAlmostEqual(dz.qdollar(m2, "yes_bid"), 0.65)
        self.assertAlmostEqual(dz.qfloat(m2, "open_interest_fp", "open_interest"), 500.0)
        # absent quotes stay None, never zero
        self.assertIsNone(dz.qdollar({}, "yes_bid"))


class TestSizing(unittest.TestCase):
    def test_bands_and_caps(self):
        self.assertEqual(dz.size_play(0.03, 0.60)[0], 0.0)     # below floor
        self.assertEqual(dz.size_play(0.06, 0.60)[0], 1.0)     # base band
        self.assertEqual(dz.size_play(0.12, 0.60)[0], 1.5)     # strong + favorite
        self.assertEqual(dz.size_play(0.12, 0.45)[0], 1.0)     # edge without p_win
        u, why = dz.size_play(0.25, 0.70)                       # suspect edge
        self.assertEqual((u, why), (1.0, "suspect edge cap"))
        u, why = dz.size_play(0.12, 0.20)                       # longshot
        self.assertEqual(u, 1.0)


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self._saved = (dz.pull_rain_markets, dz.fetch_members, dz.fetch_ref,
                       dz.fetch_settled_market, dz.fget, dz.TODAY, dz.RESEARCH_MODE)
        dz.fget = _no_network
        # The sizing/freezing/capping machinery is dormant under RESEARCH_MODE
        # but must stay under test, or it will have rotted by the time the
        # rebuilt calibration justifies turning trading back on.
        dz.RESEARCH_MODE = False
        self.tom = (dtm.datetime.now(dtm.timezone.utc) + dtm.timedelta(days=1)).date()
        self.day = self.tom.isoformat()

    def tearDown(self):
        (dz.pull_rain_markets, dz.fetch_members, dz.fetch_ref,
         dz.fetch_settled_market, dz.fget, dz.TODAY, dz.RESEARCH_MODE) = self._saved

    def _mkt(self, code, ok=True, station=True, yb=0.30, ya=0.32, oi=900.0, date=None,
             trace_rule=True):
        return {"code": code, "series": dz.RAIN_SERIES, "date": date or self.tom,
                "event_ticker": "KXRAIN-X", "ticker": "KXRAIN-X-%s" % code,
                "yb": yb, "ya": ya, "oi": oi, "structure_ok": ok, "station_ok": station,
                "trace_rule_ok": trace_rule}

    def _members(self, wet_frac=0.55, n=120):
        wet = int(n * wet_frac)
        mem = [2.0] * wet + [0.0] * (n - wet)
        per_model = {}
        chunk = n // 4
        for i, mdl in enumerate(dz.ENSEMBLE_MODELS):
            per_model[mdl] = {self.day: mem[i * chunk:(i + 1) * chunk]}
        return {self.day: mem}, -18000, per_model

    def _wire(self, mkts, members=None):
        dz.pull_rain_markets = lambda: mkts
        dz.fetch_members = lambda *a: members or self._members()
        dz.fetch_ref = lambda *a: {self.day: {"nbm_pop_max": 0.6, "nbm_pop_day": 0.7,
                                              "nbm_precip": 3.2}}

    def test_gate_quarantine_paths(self):
        thin = self._members()
        thin[0][self.day] = thin[0][self.day][:50]     # 50 pooled members
        mkts = [self._mkt("NYC"), self._mkt("SEA", ok=False),
                self._mkt("MIA", station=False),
                self._mkt("BOS", trace_rule=False)]
        def fm(lat, lon, tz, stdh):
            if abs(lat - 25.7906) < 0.01 or abs(lat - 47.4444) < 0.01:
                return self._members()
            return self._members()
        self._wire(mkts, None)
        dz.fetch_members = fm
        state = {"predictions": {}, "resolved": []}
        rows, plays, health = dz.score(state)
        sea = state["predictions"]["SEA|" + self.day]
        mia = state["predictions"]["MIA|" + self.day]
        bos = state["predictions"]["BOS|" + self.day]
        self.assertEqual(sea["gated"], "market structure")
        self.assertEqual(mia["gated"], "station rules text")
        # a city whose rules stopped saying 'trace counts as zero' is sat out:
        # the model's whole probability definition depends on that clause
        self.assertEqual(bos["gated"], "trace rule changed")
        self.assertEqual(sea["plays"], [])
        self.assertEqual(bos["plays"], [])
        nyc = state["predictions"]["NYC|" + self.day]
        self.assertIsNone(nyc.get("gated"))
        self.assertEqual(len(health["gated"]), 3)
        self.assertTrue(all(v.get("cfg") == dz.CONFIG_HASH
                            for v in state["predictions"].values()))

    def test_play_freeze_and_divergence_guard(self):
        # model 55% + trace floor vs market 31c: net edge clears, play freezes
        self._wire([self._mkt("NYC")])
        state = {"predictions": {}, "resolved": []}
        rows, plays, health = dz.score(state)
        self.assertEqual(len(plays), 1)
        rec = state["predictions"]["NYC|" + self.day]
        before = json.loads(json.dumps(rec["plays"]))
        stamp = rec["plays_logged_at"]
        # rerun with a wildly different forecast: frozen plays must not move
        self._wire([self._mkt("NYC", yb=0.10, ya=0.12)],
                   ({self.day: [0.0] * 120}, -18000,
                    {m: {self.day: [0.0] * 30} for m in dz.ENSEMBLE_MODELS}))
        dz.score(state)
        rec2 = state["predictions"]["NYC|" + self.day]
        self.assertEqual(rec2["plays"], before)
        self.assertEqual(rec2["plays_logged_at"], stamp)
        # divergence guard: uncalibrated city, |p - mid| > 0.35 suppresses
        self._wire([self._mkt("SEA", yb=0.05, ya=0.07)])   # model ~0.62 vs mid 0.06
        st2 = {"predictions": {}, "resolved": []}
        rows, plays2, health2 = dz.score(st2)
        self.assertEqual(plays2, [])
        self.assertTrue(st2["predictions"]["SEA|" + self.day].get("suppressed"))
        self.assertEqual(len(health2["suppressed"]), 1)

    def test_caps_seeded_with_frozen_units(self):
        # a target already holding 3.5 frozen units leaves room for only 0.5
        self._wire([self._mkt("NYC")])
        state = {"predictions": {"ZZZ|" + self.day: {
            "code": "ZZZ", "target": self.day, "ticker": "Z", "event_ticker": "EZ",
            "logged_at": "x", "lead": 1, "p": 0.5, "mid": 0.5, "plays_lead": 1,
            "plays_logged_at": "x", "plays_model_version": "legacy",
            "plays": [{"ticker": "Z", "side": "Buy YES", "entry": 0.5, "net": 0.06,
                       "edge": 0.06, "units": 3.5, "stake": 35.0, "p_win": 0.6,
                       "prob": 0.55, "mid": 0.5, "why": "x"}]}},
            "resolved": []}
        rows, plays, health = dz.score(state)
        self.assertEqual(len(plays), 1)
        self.assertAlmostEqual(plays[0]["units"], 0.5)
        total = sum(pl["units"] for v in state["predictions"].values()
                    for pl in v.get("plays", []) if v["target"] == self.day)
        self.assertLessEqual(total, dz.DAILY_UNIT_CAP + 1e-9)

    def test_lead_zero_never_logged(self):
        today_local = dtm.date.today()   # offset -18000 keeps this close enough
        self._wire([self._mkt("NYC", date=today_local)])
        state = {"predictions": {}, "resolved": []}
        rows, plays, health = dz.score(state)
        self.assertNotIn("NYC|" + today_local.isoformat(), state["predictions"])

    def test_resolution_fee_clv_and_trace(self):
        state = {"predictions": {
            "NYC|2026-07-01": {
                "code": "NYC", "target": "2026-07-01", "ticker": "A",
                "event_ticker": "E", "logged_at": "x", "lead": 1, "plays_lead": 1,
                "p": 0.55, "p_raw": 0.40, "mid": 0.50, "cfg": "deadbeef",
                "curve": {}, "trace_p": 0.15, "members": 120, "models": {},
                "ref": {"nbm_pop_day": 0.6}, "model_version": "t",
                "plays_model_version": "t",
                "plays": [{"ticker": "A", "side": "Buy YES", "entry": 0.42,
                           "net": 0.05, "edge": 0.06, "units": 1.0, "stake": 10.0,
                           "p_win": 0.55, "prob": 0.55, "mid": 0.44, "why": "x"}]},
            "SEA|2026-07-01": {
                "code": "SEA", "target": "2026-07-01", "ticker": "B",
                "event_ticker": "E2", "logged_at": "x", "lead": 1,
                "p": 0.30, "mid": 0.25, "gated": "thin ensemble", "plays": [],
                "model_version": "t"}},
            "resolved": []}
        dz.fetch_settled_market = lambda t: ("yes", "T") if t == "A" else ("no", "0.00")
        dz.TODAY = dtm.date(2026, 7, 3)
        n = dz.resolve_pending(state)
        self.assertEqual(n, 2)
        r = next(r for r in state["resolved"] if r["code"] == "NYC")
        self.assertEqual(r["outcome"], 1)
        self.assertTrue(r["trace"])                    # T settles YES: the thesis
        self.assertEqual(r["amount"], 0.0)
        pl = r["plays"][0]
        contracts = int(10.0 // 0.42)
        trade_fee = math.ceil(0.07 * contracts * 0.42 * 0.58 * 100) / 100
        self.assertEqual(pl["contracts"], contracts)
        self.assertEqual(pl["pnl"], round(contracts * (1 - 0.42) - trade_fee, 2))
        self.assertAlmostEqual(pl["clv"], 0.06)        # mid 0.44 -> close 0.50
        self.assertAlmostEqual(pl["close_mid"], 0.50)
        self.assertEqual(r.get("cfg"), "deadbeef")
        gated = next(r for r in state["resolved"] if r["code"] == "SEA")
        self.assertEqual(gated.get("gated"), "thin ensemble")
        rep = dz.compute_report(state)
        self.assertEqual(rep["n_events"], 1)           # quarantine excluded
        self.assertEqual(rep["n_gated"], 1)
        self.assertTrue(any("NBM" in k for k, _, _ in rep["sources"]))

    def test_no_side_pnl(self):
        state = {"predictions": {"NYC|2026-07-01": {
            "code": "NYC", "target": "2026-07-01", "ticker": "A", "event_ticker": "E",
            "logged_at": "x", "lead": 1, "plays_lead": 1, "p": 0.20, "mid": 0.30,
            "model_version": "t", "plays_model_version": "t",
            "plays": [{"ticker": "A", "side": "Buy NO", "entry": 0.70, "net": 0.05,
                       "edge": 0.10, "units": 1.0, "stake": 10.0, "p_win": 0.80,
                       "prob": 0.20, "mid": 0.30, "why": "x"}]}}, "resolved": []}
        dz.fetch_settled_market = lambda t: ("no", "0.00")
        dz.TODAY = dtm.date(2026, 7, 3)
        dz.resolve_pending(state)
        pl = state["resolved"][0]["plays"][0]
        self.assertTrue(pl["won"])                     # dry day, NO wins
        contracts = int(10.0 // 0.70)
        self.assertEqual(pl["contracts"], contracts)
        self.assertGreater(pl["pnl"], 0)
        self.assertAlmostEqual(pl["clv"], 0.0)


class TestReport(unittest.TestCase):
    def _state(self):
        res = []
        for i in range(9):
            d = "2026-07-0%d" % (i % 3 + 1)
            res.append({"code": "NYC", "target": d, "outcome": i % 2, "p": 0.55,
                        "p_raw": 0.5, "mid": 0.5, "trace": (i == 1),
                        "models": {}, "ref": {"nbm_pop_day": 0.5},
                        "plays": [{"ticker": "T", "side": "Buy YES", "entry": 0.5,
                                   "net": 0.05, "edge": 0.05, "units": 1.0,
                                   "stake": 10.0, "p_win": 0.55, "prob": 0.55,
                                   "mid": 0.5, "won": bool(i % 2), "contracts": 20,
                                   "pnl": 9.3 if i % 2 else -10.35, "close_mid": 0.5,
                                   "clv": 0.0, "outcome": i % 2, "target": d,
                                   "model_version": "2026-07-07.d1-phase1"}]})
        return {"resolved": res, "predictions": {}}

    def test_report_bins_eras_bootstrap_determinism(self):
        r1 = dz.compute_report(self._state())
        r2 = dz.compute_report(self._state())
        self.assertEqual(r1.get("roi_ci"), r2.get("roi_ci"))   # replay guarantee
        self.assertTrue(r1.get("bins"))
        self.assertEqual(r1["eras"][0][0], "Drizzle v1+")
        self.assertIn("edge_stated", r1)
        self.assertEqual(r1["clv"]["n"], 9)
        self.assertTrue(any(b["n"] for b in r1["bins"]))


class TestSettlementRegime(unittest.TestCase):
    """Guards on the 2026-07-16 Kalshi rules change.

    The Phase 1 edge was 'trace settles YES'. Kalshi inverted it. These tests
    exist so the retired trace floor cannot creep back in unnoticed, and so a
    future flip of the rules text is caught by the suite rather than by a
    losing position."""

    NEW_RULES = ("If the total precipitation at CLINYC in New York City in Jul 24, 2026 "
                 "is strictly greater than 0 inches, then the market resolves to Yes. "
                 "Data for CLINYC can be found by clicking the following URL: "
                 "https://weather.com/kalshi. “Trace” amounts (T) and missing daily "
                 "precipitation values are counted as 0 inches.")
    OLD_RULES = ("If the number of inches of precipitation recorded at Central Park, New "
                 "York on July 15, 2026 is strictly greater than 0, then the market "
                 "resolves to Yes. If the Expiration Value is T (when the target is 0) "
                 "for Trace or R for Record, then the market resolves to Yes.")

    def test_trace_rule_reads_live_text(self):
        self.assertTrue(dz.trace_rule_ok(self.NEW_RULES))
        # the old trace-settles-YES regime must NOT pass as the current one
        self.assertFalse(dz.trace_rule_ok(self.OLD_RULES))
        # unreadable/absent wording is quarantine, not consent
        self.assertFalse(dz.trace_rule_ok(""))
        self.assertFalse(dz.trace_rule_ok("resolves to Yes if it rains"))

    def test_trace_floor_is_zero_for_every_city(self):
        # a nonzero floor prices trace days that now settle NO
        for code, cfg in dz.CITIES.items():
            self.assertEqual(cfg[6], 0.0, "%s still carries a trace floor" % code)
        self.assertEqual(dz.DEFAULT_TRACE_P, 0.0)

    def test_zero_floor_leaves_probability_untouched(self):
        mem = [2.0] * 30 + [0.0] * 70
        p_raw, p = dz.rain_prob(mem, 0.0)
        self.assertAlmostEqual(p_raw, 0.30)
        self.assertAlmostEqual(p, 0.30)   # no free probability added

    def test_research_mode_ships_on(self):
        # trading stays off until the new regime has its own calibration
        self.assertTrue(dz.RESEARCH_MODE)

    def test_every_city_maps_to_a_distinct_cli_station(self):
        stations = [cfg[5] for cfg in dz.CITIES.values()]
        self.assertEqual(len(stations), len(set(stations)))
        for code, cfg in dz.CITIES.items():
            self.assertTrue(cfg[5].startswith("CLI"), code)
            self.assertTrue(-180 <= cfg[1] <= 180 and -90 <= cfg[0] <= 90, code)
        # the two stations that moved with the consolidation, pinned by name:
        # forecasting the old airport would quietly mis-price both
        self.assertEqual(dz.CITIES["CHI"][5], "CLIORD")    # O'Hare, not Midway
        self.assertEqual(dz.CITIES["HOU"][5], "CLIIAH")    # Bush, not Hobby


class TestState(unittest.TestCase):
    def test_load_state_refuses_bad_files(self):
        # STATE_PATH is module-relative; monkeypatch to a tempdir, never write
        # where it points (in CI that is the real state file).
        saved = dz.STATE_PATH
        with tempfile.TemporaryDirectory() as td:
            dz.STATE_PATH = os.path.join(td, "drizzle_state.json")
            try:
                self.assertEqual(dz.load_state(), {"predictions": {}, "resolved": []})
                with open(dz.STATE_PATH, "w") as f:
                    f.write("{ corrupt")
                with self.assertRaises(SystemExit):
                    dz.load_state()
                with open(dz.STATE_PATH, "w") as f:
                    json.dump({"predictions": []}, f)
                with self.assertRaises(SystemExit):
                    dz.load_state()
            finally:
                dz.STATE_PATH = saved


if __name__ == "__main__":
    unittest.main(verbosity=1)
