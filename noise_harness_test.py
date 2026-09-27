#!/usr/bin/env python3
"""noise_harness_test.py -- results/noise_parallel.py on synthetic draws.

    ./venv/bin/python noise_harness_test.py

Runs the harness's real scheduler (cmd_run), baseline gate, resume, stale-key
check and analysis (cmd_analyse) on fabricated draws in a temporary directory.
subprocess.Popen inside noise_parallel is replaced by a stub that writes the
draw's result file at once instead of computing it; nothing is fitted and nothing
under the repository is written. Exit 1 names every case that failed.

    failed baseline   a universe whose baseline fails gets none of its draws
    resume            a second identical run starts nothing
    stale key         a draw or baseline with another panel_code is re-run
    void              a draw with another harness hash voids its universe
    verdicts          the rule and the nt_verify label, on a supported cell that
                      verifies and one that does not
"""
import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for _p in (ROOT, ROOT / "results"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import argparse                                                # noqa: E402

import noise_parallel as npar                                  # noqa: E402

FAILS = []
LAUNCHED = []
# universe -> (baseline passes?, v1 gap under both profiles on every draw)
PLAN = {"nifty50": (True, 0.5), "midcap50": (False, 0.5), "midcap100": (True, 0.5)}


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        FAILS.append(name)


def fabricate(tag, seed):
    ok, v1_gap = PLAN[tag]
    bh = 20.0
    arms = {}
    for prof in npar.PROFILES:
        for i, a in enumerate(npar.ARM_NAMES):
            # v1 beats the buy & hold by v1_gap plus a small seed-dependent wiggle;
            # the other arms lose to it.
            gap = (v1_gap + 0.01 * (seed % 7)) if a == "v1" else (-1.0 - i)
            arms[f"{a}@{prof}"] = {"arm": a, "profile": prof, "cagr": bh + gap,
                                   "final_equity": 1e6, "tax": 0.0, "trades": 1,
                                   "cap_binds": 0, "seconds": 0.0}
    rec = {"tag": tag, "sigma": 0.0 if seed == 0 else npar.SIGMA, "noise_seed": seed,
           "bh_cagr": bh, "bh_final_equity": 1e6, "bh_seconds": 0.0, "arms": arms,
           "rows": 1, "bound_crossings": 0, "minutes_total": 0.0, "minutes_perturb": 0.0,
           "minutes_panel": 0.0, "minutes_arms": 0.0, "loky_workers": 1,
           "run_date": "synthetic", "script_sha256": npar._SCRIPT_SHA,
           "perturb_sha256": npar._SCRIPT_SHA, **npar.current_key(tag)}
    if seed == 0:
        rec["baseline"] = {"ok": ok, "failures": [] if ok else ["synthetic failure"],
                           "tolerance": npar.BASELINE_TOL}
    return rec


class FakeProc:
    pid = 0

    def poll(self):
        return 0


def fake_popen(cmd, stdout=None, stderr=None, cwd=None):
    i = cmd.index("one")
    tag = cmd[cmd.index("--universe", i) + 1]
    seed = int(cmd[cmd.index("--seed", i) + 1])
    out = cmd[cmd.index("--out", i) + 1]
    LAUNCHED.append((tag, seed))
    npar.write_atomic(npar.result_path(out, tag, seed), json.dumps(fabricate(tag, seed)))
    return FakeProc()


def run(out, tags):
    LAUNCHED.clear()
    a = argparse.Namespace(universe=",".join(tags),
                           seeds=",".join(str(s) for s in npar.NOISE_SEEDS),
                           baseline=True, workers=2, loky=1, out=str(out),
                           work=str(out / "work"))
    with redirect_stdout(io.StringIO()):
        npar.cmd_run(a)
    return list(LAUNCHED)


def analyse(out, tmp):
    npar.REPORT, npar.RUNS_CSV = tmp / "report.txt", tmp / "runs.csv"
    with redirect_stdout(io.StringIO()):
        npar.cmd_analyse(argparse.Namespace(out=str(out)))
    return npar.REPORT.read_text()


def main():
    print("noise_harness_test -- the cleaned-noise harness on synthetic draws")
    npar.subprocess.Popen = fake_popen
    npar._tree_rss = lambda: (lambda pid: 0)
    npar.time.sleep = lambda s: None
    tags = list(PLAN)
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        out = tmp / "out"
        first = run(out, tags)
        check("failed baseline: midcap50 ran its baseline and none of its draws",
              [x for x in first if x[0] == "midcap50"] == [("midcap50", 0)])
        check("passing baselines: nifty50 and midcap100 ran the baseline and 10 draws each",
              all(sum(1 for x in first if x[0] == u) == 11 for u in ("nifty50", "midcap100")))
        check("a baseline runs before its universe's draws",
              all(first.index((u, 0)) < min(first.index((u, s)) for s in npar.NOISE_SEEDS)
                  for u in ("nifty50", "midcap100")))
        check("resume: an identical second run starts nothing", run(out, tags) == [])

        f = npar.result_path(out, "nifty50", 303)
        rec = json.loads(f.read_text()); rec["panel_code"] = "sha256:other"
        f.write_text(json.dumps(rec))
        check("stale key: exactly the stale draw is re-run",
              run(out, tags) == [("nifty50", 303)])
        f = npar.result_path(out, "midcap100", 0)
        rec = json.loads(f.read_text()); rec["source_digest"] = "sha256:other"
        f.write_text(json.dumps(rec))
        check("stale key: a stale baseline is re-run and its draws are not",
              run(out, tags) == [("midcap100", 0)])

        text = analyse(out, tmp)
        check("verdict: nifty50 v1 is SUPPORTED (verifies in nt_verify)",
              "v1 VERDICT: SUPPORTED (research passes, tradeable passes; nt_verify VERIFIED)"
              in text.split("nifty50\n", 1)[1].split("\n\n", 1)[0])
        check("verdict: midcap100 v1 is SUPPORTED, NOT PORT-VERIFIED",
              "v1 VERDICT: SUPPORTED, NOT PORT-VERIFIED" in
              text.split("midcap100\n", 1)[1].split("\n\n", 1)[0])
        check("verdict: an arm that loses to the buy & hold is NOT SUPPORTED",
              "v2 VERDICT: NOT SUPPORTED" in text.split("nifty50\n", 1)[1])
        check("failed baseline: midcap50 is reported as stopped",
              "baseline FAILED" in text.split("midcap50\n", 1)[1].split("\n\n", 1)[0])
        check("the registration's two statements are in the report",
              "32 cells are tested" in text and "not to be read as an edge" in text
              and "UNGATED" in text)

        f = npar.result_path(out, "nifty50", 505)
        rec = json.loads(f.read_text()); rec["script_sha256"] = "0000000000000000"
        f.write_text(json.dumps(rec))
        text = analyse(out, tmp)
        check("void: a draw with another harness hash voids its universe",
              "VOID" in text.split("nifty50\n", 1)[1].split("\n\n", 1)[0]
              and "VOID" not in text.split("midcap100\n", 1)[1].split("\n\n", 1)[0])
    if FAILS:
        print(f"RESULT: FAIL -- {len(FAILS)} case(s): " + "; ".join(FAILS))
        return 1
    print("RESULT: PASS -- scheduler, baseline gate, resume, stale key, void and verdicts "
          "behave as registered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
