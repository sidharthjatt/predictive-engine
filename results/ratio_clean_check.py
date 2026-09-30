"""
ratio_clean_check.py -- count what the ratio cleaning changes, and check none is left.

    ./venv/bin/python results/ratio_clean_check.py            # count and check
    ./venv/bin/python results/ratio_clean_check.py --count    # count only

The rule is experiments/DATA_CLEANING_SPEC.txt, implemented in results/ratio_clean.py.
For every registered universe it reads each constituent file the way
engine_core.build_panel does (PRICE_COLS, dropna, sorted by date), and:

    COUNT   events and rows ratio_clean.clean changes, per universe, split by
            event length 1..5, over all history and inside the backtest window
            (an event is inside when its first session is; its rows are
            counted by their own dates).
    CHECK   runs clean, then engine_core.canonical_price, then the same scan over
            the ratio the engine uses (canonical close / raw close). Exit 1 if any
            reverting event of MAX_LEN sessions or fewer starts inside the
            backtest window, in any universe.

Reads the raw files; writes nothing.
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "results"))

import numpy as np                                                  # noqa: E402
import config                                                       # noqa: E402
from paths import list_dir
import engine_core as ec                                            # noqa: E402
import ratio_clean as rc                                            # noqa: E402
from universes.registry import gated                                # noqa: E402

LO, HI = config.BT_START_DATE, config.BT_END_DATE


def load(f):
    """The frame build_panel hands canonical_price, before any cleaning."""
    raw = config.read_price_csv(f).sort_values("date")
    return raw[ec.PRICE_COLS].dropna()


def universe(u, cal, check):
    n = {"rows_window": 0, "files": 0,
         "ev_all": [0] * (rc.MAX_LEN + 1), "rows_all": [0] * (rc.MAX_LEN + 1),
         "ev_win": [0] * (rc.MAX_LEN + 1), "rows_win": [0] * (rc.MAX_LEN + 1),
         "sym_win": set(), "left": [], "keys": set()}
    for f in list_dir(u.prepare_data_dir(), "*.csv"):
        d = load(f)
        n["files"] += 1
        dt = d["date"]
        n["rows_window"] += int((dt.isin(cal) & (dt >= LO) & (dt <= HI)).sum())
        cleaned, exempt, events = rc.clean(d, cal)
        dates = list(d["date"])
        pos = {x: i for i, x in enumerate(dates)}
        sess = np.flatnonzero(d["date"].isin(cal).to_numpy())
        where = {int(p): j for j, p in enumerate(sess)}
        for start, k, _p in events:
            n["ev_all"][k] += 1
            n["rows_all"][k] += k
            j0 = where[pos[start]]
            rows = [dates[sess[j]] for j in range(j0, j0 + k)]
            in_win = [LO <= x <= HI for x in rows]
            if LO <= start <= HI:
                n["ev_win"][k] += 1
                n["sym_win"].add(f.stem)
            n["rows_win"][k] += sum(in_win)
            n["keys"].update((f.stem, x) for x, w in zip(rows, in_win) if w)
        if check:
            canon, _nfb = ec.canonical_price(cleaned, exempt=exempt)
            left = rc.remaining_events(canon, d["close"].to_numpy(),
                                       rc.fallback_mask(d), cal)
            n["left"] += [(f.stem, x, k) for x, k in left if LO <= x <= HI]
    return n


def main(argv):
    check = "--count" not in argv
    cal = ec._load_calendar()
    L = range(1, rc.MAX_LEN + 1)
    print(f"ratio cleaning (experiments/DATA_CLEANING_SPEC.txt): TOL {rc.TOL}, "
          f"MAX_LEN {rc.MAX_LEN}, backtest window {LO.date()} to {HI.date()}")
    print()
    hdr = ("universe", "files", "rows in window", *[f"ev{k}" for k in L], "events",
           *[f"rows{k}" for k in L], "rows", "share", "symbols")
    print("inside the backtest window (event counted by its first session, rows by their own date)")
    print(" | ".join(hdr))
    res, keys, bad = {}, set(), []
    for u in gated():
        n = universe(u, cal, check)
        res[u.tag] = n
        keys |= n["keys"]
        bad += [(u.tag, *x) for x in n["left"]]
        ev, rw = n["ev_win"], n["rows_win"]
        print(" | ".join(str(x) for x in (
            u.tag, n["files"], f"{n['rows_window']:,}", *[ev[k] for k in L], sum(ev),
            *[rw[k] for k in L], sum(rw), f"{sum(rw) / n['rows_window']:.2%}",
            len(n["sym_win"]))))
    print()
    print("all history")
    print(" | ".join(("universe", *[f"ev{k}" for k in L], "events",
                      *[f"rows{k}" for k in L], "rows")))
    for t, n in res.items():
        ev, rw = n["ev_all"], n["rows_all"]
        print(" | ".join(str(x) for x in (t, *[ev[k] for k in L], sum(ev),
                                           *[rw[k] for k in L], sum(rw))))
    print()
    print(f"distinct symbol-days changed inside the window, across universes: {len(keys):,} "
          f"on {len({s for s, _ in keys})} symbols")
    if not check:
        print("RESULT: COUNT ONLY -- the check was not run (--count)")
        return 0
    if bad:
        print(f"RESULT: FAIL -- {len(bad)} reverting ratio event(s) of {rc.MAX_LEN} "
              f"sessions or fewer remain inside the backtest window after cleaning:")
        for t, s, x, k in bad[:20]:
            print(f"    {t} {s} {str(x)[:10]} length {k}")
        return 1
    print(f"RESULT: PASS -- after cleaning, 0 reverting ratio events of {rc.MAX_LEN} "
          f"sessions or fewer start inside the backtest window, in "
          f"{len(res)} universes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
