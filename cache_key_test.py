#!/usr/bin/env python3
"""cache_key_test.py -- a cache or record from other code or other data must be refused.

    ./venv/bin/python cache_key_test.py

Each case writes a record the way its harness does, once with the current key and
once with a changed or missing one, into a temporary directory, and asserts that
the harness reuses the first and refuses the second. Nothing under the repository
is written. Exit 1 names every case that failed.

    noise_parallel      draw_state, _baseline_state and load_draws on draw JSONs
    price_noise_measure current_runs on runs-CSV rows
    after_tax_noise     current_runs on runs-CSV rows
    seed_cache_key      the /tmp fit caches (validate_engine, validate_sizing,
                        validate_breadth_live, purge_fix_measure) change name when
                        the panel's content changes by one byte
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

import pandas as pd                                            # noqa: E402

import config                                                  # noqa: E402
from universes.registry import REGISTRY                        # noqa: E402

TAG = "nifty50"
FAILS = []


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        FAILS.append(name)


def quiet(fn, *a):
    with redirect_stdout(io.StringIO()):
        return fn(*a)


def noise_parallel_cases(key, tmp):
    import noise_parallel as npar
    out = tmp / "np"
    (out / "draws").mkdir(parents=True)
    base = {"tag": TAG, "sigma": 0.0, "noise_seed": 0, "baseline": {"ok": True}}
    npar.write_atomic(npar.result_path(out, TAG, 0), json.dumps({**base, **key}))
    npar.write_atomic(npar.result_path(out, TAG, 101),
                      json.dumps({**base, "noise_seed": 101, **key,
                                  "panel_code": "sha256:other"}))
    npar.write_atomic(npar.result_path(out, TAG, 202),
                      json.dumps({**base, "noise_seed": 202}))
    check("noise_parallel: a draw with the current key is current",
          npar.draw_state(out, TAG, 0) == "current")
    check("noise_parallel: a draw with another panel_code is stale",
          npar.draw_state(out, TAG, 101) == "stale")
    check("noise_parallel: a draw without key fields is stale",
          npar.draw_state(out, TAG, 202) == "stale")
    check("noise_parallel: a missing draw is missing",
          npar.draw_state(out, TAG, 303) == "missing")
    check("noise_parallel: a current passing baseline passes",
          npar._baseline_state(out, TAG) is True)
    npar.write_atomic(npar.result_path(out, TAG, 0),
                      json.dumps({**base, **key, "source_digest": "sha256:other"}))
    check("noise_parallel: a stale baseline counts as no baseline, even marked ok",
          npar._baseline_state(out, TAG) is None)
    got = quiet(npar.load_draws, out)
    check("noise_parallel: load_draws leaves every stale draw out", got == [])


def runs_csv_cases(key, tmp):
    import price_noise_measure as pnm
    import after_tax_noise as atn
    rows = [{"tag": TAG, "sigma": 0.0001, "noise_seed": 101, **key},
            {"tag": TAG, "sigma": 0.0001, "noise_seed": 202, **key,
             "source_digest": "sha256:other"},
            {"tag": TAG, "sigma": 0.0001, "noise_seed": 303,
             "panel_code": None, "source_digest": None}]
    for mod, attr, label in ((pnm, "RUNS_CSV", "price_noise_measure"),
                             (atn, "RUNS", "after_tax_noise")):
        f = tmp / f"{label}_runs.csv"
        pd.DataFrame(rows).to_csv(f, index=False)
        old = getattr(mod, attr)
        setattr(mod, attr, f)
        try:
            got = quiet(mod.current_runs)
        finally:
            setattr(mod, attr, old)
        check(f"{label}: only the row with the current key is reused",
              sorted(got["noise_seed"].astype(int)) == [101])


def fit_cache_cases(tmp):
    import validate_breadth_live as vbl
    from seed_cache_key import seed_cache_key
    a, b = tmp / "panel_a.csv", tmp / "panel_b.csv"
    a.write_text("date,symbol,close\n2020-01-01,X,1.00\n")
    b.write_text("date,symbol,close\n2020-01-01,X,1.01\n")
    check("validate_breadth_live: the T1 cache name changes with the panel content",
          vbl._t1_cache(TAG, 0, [5, 55, 555], a) != vbl._t1_cache(TAG, 0, [5, 55, 555], b))
    code = [ROOT / "results" / "engine_core.py", ROOT / "config.py"]
    check("seed_cache_key: one byte of panel content changes the key",
          seed_cache_key(code, a, (TAG,)) != seed_cache_key(code, b, (TAG,)))


def main():
    print("cache_key_test -- stale caches and records must be refused")
    key = config.run_key(REGISTRY[TAG])
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        noise_parallel_cases(key, tmp)
        runs_csv_cases(key, tmp)
        fit_cache_cases(tmp)
    if FAILS:
        print(f"RESULT: FAIL -- {len(FAILS)} case(s): " + "; ".join(FAILS))
        return 1
    print("RESULT: PASS -- every stale record and cache was refused, every current one reused")
    return 0


if __name__ == "__main__":
    sys.exit(main())
