"""
tradability_causality_test.py -- no trade on day i may depend on a row dated after day i.

    ./venv/bin/python tradability_causality_test.py          # every case, with its figures
    ./venv/bin/python tradability_causality_test.py --quiet  # PASS/FAIL lines only
    ./venv/bin/python tradability_causality_test.py --real   # also the KAMAHOLD replay

A synthetic universe of 20 names on real NSE calendar sessions, written as price
files to a temporary folder and loaded through engine_core.set_tradeability, the
way every engine run loads it. Each case runs test_exposure.backtest_exposure.

    1. causality: a held name has no row on two sessions. Removing every row of that
       name dated after day i must leave every trade and holding up to day i
       unchanged, for each day i around the gap and around each case below. The
       engine before 2026-10-16 fails this: it sold the name at the open of the
       session before the gap, because the next session had no row.
    2. a sale due on a session with no row is owed, and fills at the open of the
       next session with a row; that session is the first row after a gap
    3. a capped owed sale leaves the rest owed; the next decision that keeps the
       name cancels it, and the rest stays held
    4. a name whose file ends is never sold and is held at its last close
    5. a buy due on a session with no row is not made, and is logged
    6. with no rule loaded, the engine is unchanged (every session tradeable)

--real replays mcap5001to10000 v1 on the delivered data: KAMAHOLD has no row on
2019-03-18 and 2019-03-19. Cutting its file after 2019-03-15 must leave every trade
up to 2019-03-15 unchanged. Needs data/raw and the cached panel; about 2 minutes.

Nothing in the repository is written. Exit 0 when every case passes, 1 otherwise.
"""
import shutil
import sys
import tempfile
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent
for _p in (ROOT, ROOT / "results", ROOT / "nautilus"):
    sys.path.insert(0, str(_p))

import numpy as np
import pandas as pd

import engine_core
from config import read_table  # the one CSV/parquet reader: config.read_table
import slippage
from engine_core import precompute
from test_exposure import backtest_exposure

QUIET = "--quiet" in sys.argv
RESULTS = []
SYMS = [f"S{k:02d}" for k in range(20)]
CAL = sorted(d for d in engine_core._load_calendar()
             if pd.Timestamp("2020-06-01") <= d <= pd.Timestamp("2021-12-31"))
DATES = [d for d in CAL if d >= pd.Timestamp("2021-01-01")]


def D(i):
    return DATES[i]


def case(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail and not QUIET else ""))


class _Fixture:
    """A universe for engine_core.set_tradeability: a tag and a folder of price files."""
    def __init__(self, tag, folder):
        self.tag, self._folder = tag, Path(folder)

    def prepare_data_dir(self):
        return self._folder


def frames():
    """Every name's full rows: close, open and a score, on every session of CAL."""
    n = len(CAL)
    t = np.arange(n)
    out = {}
    for k, s in enumerate(SYMS):
        close = 100.0 * (1 + 0.01 * k) * np.cumprod(np.r_[1.0, np.full(n - 1, 1.0004)]) \
            * (1 + 0.02 * np.sin(t / (k + 3)))
        out[s] = pd.DataFrame({"date": CAL, "open": close * 0.999, "close": close,
                               "score": float(len(SYMS) - k)})
    return out


def special(fr):
    """The cases' rows and scores, by the indices into DATES named in the docstring."""
    def drop(s, idx):
        fr[s] = fr[s][~fr[s]["date"].isin([D(i) for i in idx])]

    def score(s, lo, hi, v):
        m = (fr[s]["date"] >= D(lo)) & (fr[s]["date"] <= D(hi))
        fr[s].loc[m, "score"] = v
    drop("S00", [30, 31])                    # case 1: held through a two-session gap
    score("S01", 35, len(DATES) - 1, -1.0)   # case 2: ranked out at decision 40 ...
    drop("S01", [41, 42])                    # ... whose execution day has no row
    score("S02", 95, 114, -2.0)              # case 3: out at decision 100, back at 120
    drop("S02", [101])
    fr["S03"] = fr["S03"][fr["S03"]["date"] <= D(150)]  # case 4: the file ends
    score("S12", 60, 60, 100.0)              # case 5: a buy due on D61 ...
    drop("S12", [61])                        # ... which has no row
    return fr


VOL20 = {"S02": {d: 10.0 for d in DATES[99:]}}   # case 3's cap: 10 shares a session


def truncate(fr, sym, i):
    """The same rows with every row of `sym` dated after D(i) removed."""
    out = dict(fr)
    out[sym] = fr[sym][fr[sym]["date"] <= D(i)]
    return out


# naming: axis-free -- fixture price files in a temporary folder, removed after the run
def write(fr, folder):
    for s, f in fr.items():
        pd.DataFrame({"date": f["date"].dt.strftime("%d-%m-%Y"), "open": f["open"],
                      "high": f[["open", "close"]].max(axis=1),
                      "low": f[["open", "close"]].min(axis=1), "close": f["close"],
                      "adj_close": f["close"], "volume": 1_000_000.0}).to_csv(
            Path(folder) / f"{s}.csv", index=False)


def run(fr, rule=True):
    """(audit, equity) for one fixture. The rule is loaded from the written files."""
    long = pd.concat([f.assign(symbol=s) for s, f in fr.items()])
    px = long.pivot_table(index="date", columns="symbol", values="close").reindex(CAL).ffill()
    op = long.pivot_table(index="date", columns="symbol", values="open").reindex(CAL).ffill()
    sc = long.pivot_table(index="date", columns="symbol", values="score").reindex(CAL)
    tmp = tempfile.mkdtemp(prefix="causality_")
    try:
        write(fr, tmp)
        if rule:
            engine_core.set_tradeability(_Fixture("causality", tmp))
        else:
            engine_core.set_tradeability(None, enabled=False)
        audit = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions",
                                 "skipped")}
        eq, *_ = backtest_exposure(px, op, sc, DATES, precompute(px), px / px.shift(20) - 1,
                                   mode="none", sizing="invvol", audit=audit, rebal=20,
                                   participation_cap=1.0, vol20=VOL20,
                                   drawdown_stop=None, dd_overlay=None,
                                   fixed_capital=False)
        return audit, eq, op
    finally:
        engine_core.set_tradeability(None, enabled=False)
        shutil.rmtree(tmp, ignore_errors=True)


def upto(rows, cut):
    return [tuple(sorted(r.items())) for r in rows if pd.Timestamp(r["date"]) <= cut]


def trades(audit, sym):
    return [r for r in audit["trades"] if r["symbol"] == sym]


def main():
    fr = special(frames())
    full, eq, op = run(fr)

    # 1 ----------------------------------------------------------------------
    cuts = [("S00", i) for i in range(25, 36)] + [("S01", i) for i in (39, 40, 41, 42)] \
        + [("S02", i) for i in (100, 101, 102, 119, 120)] + [("S12", i) for i in (59, 60, 61)]
    bad = []
    for sym, i in cuts:
        cut, _, _ = run(truncate(fr, sym, i))
        for k in ("trades", "holdings"):
            if upto(full[k], D(i)) != upto(cut[k], D(i)):
                bad.append(f"{sym} after {D(i).date()} ({k})")
                break
    case("1 causality: rows after day i change nothing up to day i", not bad,
         f"{len(cuts)} cuts; differing: {bad[:4]}")

    # 2 ----------------------------------------------------------------------
    t = trades(full, "S01")
    sells = [r for r in t if r["action"] == "SELL"]
    want = round(slippage.sell_price(float(op.loc[D(43), "S01"]), 0, None, None), 2)
    owed = [r for r in full["skipped"] if r["symbol"] == "S01"
            and str(r["reason"]).startswith("untradeable: no row this session, sale owed")]
    case("2 owed sale fills at the next row's open",
         len(sells) == 1 and pd.Timestamp(sells[0]["date"]) == D(43)
         and sells[0]["price"] == want and [pd.Timestamp(r["date"]) for r in owed] == [D(41)],
         f"sells {[(str(pd.Timestamp(r['date']).date()), r['price']) for r in sells]}, "
         f"expected {D(43).date()} at {want}; owed logged on {[str(pd.Timestamp(r['date']).date()) for r in owed]}")

    # 3 ----------------------------------------------------------------------
    t = trades(full, "S02")
    s3 = [r for r in t if r["action"] == "SELL"]
    held_after = [r for r in full["holdings"] if r["symbol"] == "S02"
                  and pd.Timestamp(r["date"]) == D(121)]
    ok3 = (s3 and all(r["qty"] == 10 for r in s3)
           and all(D(102) <= pd.Timestamp(r["date"]) <= D(120) for r in s3)
           and len(held_after) == 1 and held_after[0]["qty"] > 0)
    case("3 capped owed sale: rest stays owed, cancelled when kept again", ok3,
         f"{len(s3)} sells of {[r['qty'] for r in s3][:3]}... from "
         f"{pd.Timestamp(s3[0]['date']).date() if s3 else '-'} to "
         f"{pd.Timestamp(s3[-1]['date']).date() if s3 else '-'}; held on {D(121).date()}: "
         f"{held_after[0]['qty'] if held_after else 0}")

    # 4 ----------------------------------------------------------------------
    t = trades(full, "S03")
    late = [r for r in t if pd.Timestamp(r["date"]) > D(150)]
    end = [r for r in full["holdings"] if r["symbol"] == "S03"
           and pd.Timestamp(r["date"]) == DATES[-1]]
    last_close = round(float(fr["S03"]["close"].iloc[-1]), 2)
    case("4 a name whose file ends is held at its last close",
         not late and len(end) == 1 and round(float(end[0]["price"]), 2) == last_close,
         f"trades after {D(150).date()}: {len(late)}; held at the end: "
         f"{end[0]['qty'] if end else 0} at {end[0]['price'] if end else '-'} "
         f"(last close {last_close})")

    # 5 ----------------------------------------------------------------------
    refused = [r for r in full["skipped"] if r["symbol"] == "S12" and r["side"] == "BUY"
               and str(r["reason"]).startswith("untradeable: no row this session")]
    bought = [r for r in trades(full, "S12") if r["action"] == "BUY"
              and pd.Timestamp(r["date"]) == D(61)]
    case("5 a buy due on a session with no row is not made",
         not bought and [pd.Timestamp(r["date"]) for r in refused] == [D(61)],
         f"refused on {[str(pd.Timestamp(r['date']).date()) for r in refused]}")

    # 6 ----------------------------------------------------------------------
    base = frames()
    a_rule, e_rule, _ = run(base)
    a_none, e_none, _ = run(base, rule=False)
    case("6 every session has a row: the rule changes nothing",
         bool((e_rule == e_none).all()) and a_rule["trades"] == a_none["trades"],
         f"final equity {e_rule.iloc[-1]:,.2f} and {e_none.iloc[-1]:,.2f}")

    if "--real" in sys.argv:
        real()

    print(f"\nRESULT: {'PASS' if all(RESULTS) else 'FAIL'} -- {sum(RESULTS)} of {len(RESULTS)} cases")
    return 0 if all(RESULTS) else 1


def real():
    """mcap5001to10000 v1 on the delivered data, KAMAHOLD cut after 2019-03-15."""
    import audit_step
    from arms.registry import ARMS
    from universes.registry import REGISTRY
    u = REGISTRY["mcap5001to10000"]
    px, op, sc, bd = audit_step.prices(u)
    cut_day = pd.Timestamp("2019-03-15")

    def one(farm, px_, op_, sc_):
        engine_core.set_tradeability(_Fixture(u.tag, farm))
        try:
            audit = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions",
                                     "skipped")}
            backtest_exposure(px_, op_, sc_, bd, precompute(px_), px_ / px_.shift(20) - 1,
                              audit=audit, **ARMS["v1"].kwargs, value_at_open=True,
                              tax_enabled=False, rebal=20, participation_cap=None,
                              drawdown_stop=None, dd_overlay=None, fixed_capital=False)
            return audit
        finally:
            engine_core.set_tradeability(None, enabled=False)

    full = one(u.prepare_data_dir(), px, op, sc)
    tmp = Path(tempfile.mkdtemp(prefix="kamahold_"))
    try:
        for f in Path(u.prepare_data_dir()).glob("*.csv"):
            if f.stem != "KAMAHOLD":
                (tmp / f.name).symlink_to(f.resolve())
        k = read_table(Path(u.prepare_data_dir()) / "KAMAHOLD.csv")
        kd = pd.to_datetime(k["date"], format="%d-%m-%Y")
        # naming: axis-free -- a cut copy of one raw file in a temporary folder
        k[kd <= cut_day].to_csv(tmp / "KAMAHOLD.csv", index=False)
        px_c, op_c, sc_c = px.copy(), op.copy(), sc.copy()
        after = px_c.index > cut_day
        px_c.loc[after, "KAMAHOLD"] = px.loc[cut_day, "KAMAHOLD"]
        op_c.loc[after, "KAMAHOLD"] = op.loc[cut_day, "KAMAHOLD"]
        sc_c.loc[sc_c.index > cut_day, "KAMAHOLD"] = np.nan
        cut = one(tmp, px_c, op_c, sc_c)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    same = upto(full["trades"], cut_day) == upto(cut["trades"], cut_day)
    kama = [r for r in full["trades"] if r["symbol"] == "KAMAHOLD"
            and pd.Timestamp(r["date"]) <= pd.Timestamp("2019-05-31")]
    case("real: mcap5001to10000 v1, KAMAHOLD cut after 2019-03-15", same,
         f"KAMAHOLD trades to 2019-05-31 on the full data: "
         f"{[(str(pd.Timestamp(r['date']).date()), r['action'], r['qty'], r['price']) for r in kama]}")


if __name__ == "__main__":
    sys.exit(main())
