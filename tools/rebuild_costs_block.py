"""
rebuild_costs_block.py -- rewrite the COSTS block of saved runs whose tax total left
out the 4% cess, from each run's own saved fills and tax years. No backtest is run.

    ./venv/bin/python tools/rebuild_costs_block.py --check                 # steps 1 and 3, write nothing
    ./venv/bin/python tools/rebuild_costs_block.py --write --commit HASH   # rewrite what passes

From 2026-10-14 (commit b61621b) tax_util charged the cess, but cost_report's
strategy_totals printed short + long tax, so the COSTS block's "tax, total", its gross
profit, "all costs" and every "of gross" percentage left the cess out. The fix is in
cost_report.py. This tool corrects the copies already on disk:

    results_<u>/metrics/COST_SUMMARY_<tag>.txt and the totals block of DAILY_LOG_<tag>.txt
    the same two files inside every run folder, runs/<ts>/results_<u>/metrics/
    each COSTS block in runs/<ts>/run.log

A file is a target only if its COST_TAX_YEARS has a cess and its printed tax total is
short + long. Nothing else is touched: a tax-off run, or one on the ledger from before
the cess (no cess column), is left as it is.

THE PROOF, per file:
  1. The block is rebuilt with cost_report as it was at OLD_COMMIT, from the saved
     COSTS_<tag>.csv, COST_TAX_YEARS_<tag>.csv, the run's own equity curve and the
     buy & hold recomputed from the cached price panel. It must equal the block on
     disk byte for byte, or the file is not rewritten and is listed.
  2. The block is rebuilt with the current cost_report from the same inputs.
  3. Every rupee figure the block prints, read back with summary_figures, is
     unchanged except the tax total, the gross profit and all costs, plus the new cess
     rows. The new tax total equals COST_TAX_YEARS total_tax summed and, under tax on,
     FY_TAX_STATEMENT's assessed total_tax; the new gross profit equals final -
     start + charges + slippage (+ impact) + the tax total. In run.log and DAILY_LOG,
     the bytes outside the block are unchanged.

Each rewritten block is followed by one line saying it was rebuilt, when, and from
which commit's cost_report. Reads the cached panels; never reads or writes data/.
"""
import argparse
import datetime as dt
import importlib.util
import io
import contextlib
import itertools
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "results"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd

import config
from config import read_table
import arms.registry as arm_reg
from universes.registry import REGISTRY, pit_variant
import cost_report as NEW

OLD_COMMIT = "6ab7c55"   # the last commit with the cess-free tax total
NOTE = ("COSTS block rebuilt on {date} from this run's saved fills and tax years: the tax "
        "total now includes the 4% cess (cost_report fix, commit {commit}). Nothing else in "
        "this file changed.")
HEADER = re.compile(r"^ COSTS -- (\S+) (\S+)\s+cadence (\d+), profile (\S+), tax (on|off)$", re.M)


def load_old():
    src = subprocess.run(["git", "-C", str(ROOT), "show", f"{OLD_COMMIT}:results/cost_report.py"],
                         capture_output=True, text=True, check=True).stdout
    path = Path(tempfile.mkdtemp()) / "cost_report_old.py"
    path.write_text(src)
    spec = importlib.util.spec_from_file_location("cost_report_old", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


OLD = load_old()

_PANELS, _BH = {}, {}
_STATIC = dict(REGISTRY)   # the static rows, as imported
_MEMBERSHIP = {}


def panel(tag, pit):
    key = (tag, pit)
    if key not in _PANELS:
        base = _STATIC[tag]
        u = pit_variant(base) if pit else base
        # require_cache accepts only the panel of a row in REGISTRY, so the row is
        # swapped for the read, as run.py's use_pit swaps it, and put back.
        REGISTRY[tag] = u
        try:
            p = read_table(config.require_cache(u.score_cache, what=f"{tag} score panel"),
                           parse_dates=["date"])
        finally:
            REGISTRY[tag] = base
        _PANELS[key] = (p.pivot_table(index="date", columns="symbol", values="close").ffill(),
                        p.pivot_table(index="date", columns="symbol", values="open").ffill())
    return _PANELS[key]


def bh_for(mod, tag, pit, bd, capital, tax_on):
    key = (mod.__name__, tag, pit, bd[0], bd[-1], len(bd), capital, tax_on)
    if key not in _BH:
        px, op = panel(tag, pit)
        # bh_held.held_lots buys with capital_axis.selected(), so the run's capital
        # is selected for the call, as run.py --capital selects it.
        # In a pit run the basket is the members on the first day (bh_held via
        # engine_core.MEMBERSHIP), loaded as tools/pit_noise_band.select_pit loads it.
        import capital_axis
        import engine_core as ec
        import survivorship as sv
        import survivorship_axis
        capital_axis.set_selection(None if capital == capital_axis.DEFAULT else int(capital))
        if pit:
            u = pit_variant(_STATIC[tag])
            REGISTRY[tag] = u
            survivorship_axis.set_selection("pit")
            if tag not in _MEMBERSHIP:
                with contextlib.redirect_stdout(io.StringIO()):
                    _MEMBERSHIP[tag] = sv.load(u.membership_file, index_name=u.tag,
                                               price_dir=u.raw_data_dir, allow_invalid=True)
            ec.PIT_MEMBERSHIPS[tag] = _MEMBERSHIP[tag]
            ec.MEMBERSHIP = ec.membership_for(u)
        try:
            _BH[key] = mod.bh_costs(px, op, bd, capital, tax_on)
        finally:
            capital_axis.set_selection(None)
            if pit:
                ec.MEMBERSHIP = None
                survivorship_axis.set_selection("static")
                REGISTRY[tag] = _STATIC[tag]
    return _BH[key]


def selections():
    names = list(arm_reg.ARMS)
    out = [""]
    for k in range(1, len(names) + 1):
        for c in itertools.combinations(names, k):
            out.append(arm_reg.selection_suffix(list(c)))
    return list(dict.fromkeys(out))


SELS = selections()


def curves(M, arm, tail):
    """Every saved full-precision curve of this arm at these axes, in M."""
    col = arm_reg.ALL_ARMS[arm].equity_column
    names = [f"v2FINAL_equity{tail}.csv"] + [f"v34_equity{s}{tail}.csv" for s in SELS] \
        + [f"v34_stop_equity_{arm}{tail}.csv"]
    out = []
    for nm in names:
        f = M / nm
        if f.exists():
            d = read_table(f, parse_dates=["date"]).set_index("date")
            if col in d.columns:
                out.append((nm, d[col].astype(float)))
    return out


def saved_inputs(M, tag):
    fills, years = NEW.read_run_costs(M, tag)
    fills["charges"] = fills["charges_total"]
    years["deducted_on"] = pd.to_datetime(years["deducted_on"])
    return fills, years


def is_target(text, years):
    if "cess" not in years.columns or float(years["cess"].sum()) <= 0:
        return False
    m = re.search(r"^  tax, total\s+([-\d,.]+)", text, re.M)
    pre = float((years["stcg_tax"] + years["ltcg_tax"]).sum())
    return m is not None and abs(float(m.group(1).replace(",", "")) - pre) < 0.006


def figures(text):
    f = NEW.summary_figures(text)
    return {k: float(v.replace(",", "")) for k, v in f.items()}


def step3(old_text, new_text, years, fills, final, start, M, tag, tax_on):
    """The figure-level proof. Returns a list of problems, empty when it holds."""
    a, b = figures(old_text), figures(new_text)
    bad = []
    moved = {"strategy/tax", "strategy/gross", "strategy/all_costs"}
    for k, v in a.items():
        if k not in moved and b.get(k) != v:
            bad.append(f"{k} moved from {v} to {b.get(k)}")
    want_tax = float(years["total_tax"].sum())
    if abs(b["strategy/tax"] - want_tax) > 0.01:
        bad.append(f"tax total {b['strategy/tax']} is not total_tax {want_tax}")
    if abs(b.get("strategy/cess", -1) - float(years["cess"].sum())) > 0.01:
        bad.append("the cess row is not COST_TAX_YEARS cess")
    if tax_on:
        st = M / f"FY_TAX_STATEMENT_{tag}.csv"
        if st.exists():
            s = read_table(st)
            paid = float(s.loc[s["assessed"].astype(bool), "total_tax"].sum())
            if abs(b["strategy/tax"] - paid) > 0.01:
                bad.append(f"tax total {b['strategy/tax']} is not FY_TAX_STATEMENT's {paid}")
    imp = float(fills["impact_rs"].sum()) if "impact_rs" in fills.columns else 0.0
    gross = final - start + b["strategy/charges"] + b["strategy/slippage"] + imp + want_tax
    if abs(b["strategy/gross"] - gross) > 0.03:
        bad.append(f"gross {b['strategy/gross']} is not {gross:.2f}")
    return bad


def rebuild_dir(M, run_log, date, commit, write, report):
    """Every target COST_SUMMARY in metrics dir M, its DAILY_LOG, and its block in run_log."""
    log_text = run_log.read_text() if run_log is not None else None
    log_new = log_text
    for f in sorted(M.glob("COST_SUMMARY_*.txt")):
        tag = f.stem[len("COST_SUMMARY_"):]
        text = f.read_text()
        try:
            fills, years = saved_inputs(M, tag)
        except FileNotFoundError as e:
            report.append(("skipped", str(f.relative_to(ROOT)), f"input missing: {e}"))
            continue
        if not is_target(text, years):
            continue
        m = HEADER.search(text)
        utag, arm, rebal, profile, tax_on = m.group(1), m.group(2), int(m.group(3)), m.group(4), m.group(5) == "on"
        if "_dd" in tag:
            report.append(("skipped", str(f.relative_to(ROOT)), "drawdown-limit run: its block needs the overlay's events, not saved"))
            continue
        prefix = utag if arm == "v2" else f"{utag}_{arm}"
        tail = tag[len(prefix):]
        pit = "pit" in tail.split("_")
        start = float(re.search(r"starting capital Rs ([\d,.]+)", text).group(1).replace(",", ""))
        cm = re.search(r"participation cap cut ([\d,]+) order", text)
        cap_cuts = int(cm.group(1).replace(",", "")) if cm else 0
        stop_arm = "of which drawdown exits" in text
        label = f"{utag} {arm}"
        found = None
        for nm, eq in curves(M, arm, tail):
            bd = eq.index
            days = pd.DataFrame(index=range(len(bd)))
            with contextlib.redirect_stdout(io.StringIO()):
                old_lines = OLD.summary_block(label, profile, tax_on, rebal, start, eq, fills, years,
                                              days, bh_for(OLD, utag, pit, bd, start, tax_on),
                                              cap_cuts=cap_cuts, stop_arm=stop_arm, dd=None)
            if "\n".join(old_lines) + "\n" == text:
                found = (nm, eq, bd, days)
                break
        if found is None:
            report.append(("skipped", str(f.relative_to(ROOT)),
                           "step 1: no saved curve reproduces the block byte for byte"))
            continue
        nm, eq, bd, days = found
        bh_new = bh_for(NEW, utag, pit, bd, start, tax_on)
        new_lines = NEW.summary_block(label, profile, tax_on, rebal, start, eq, fills, years, days,
                                      bh_new, cap_cuts=cap_cuts, stop_arm=stop_arm, dd=None)
        new_text = "\n".join(new_lines) + "\n"
        problems = step3(text, new_text, years, fills, float(eq.iloc[-1]), start, M, tag, tax_on)
        if problems:
            report.append(("skipped", str(f.relative_to(ROOT)), "step 3: " + "; ".join(problems)))
            continue
        note = NOTE.format(date=date, commit=commit) + "\n"
        # THE DAILY LOG's totals block, step 1 against the summary still on disk.
        dl = M / f"DAILY_LOG_{tag}.txt"
        dl_new = None
        if dl.exists():
            dtext = dl.read_text()
            wm = re.search(r"^(=+)\n COST TOTALS", dtext, re.M)
            if wm is None:
                report.append(("skipped", str(dl.relative_to(ROOT)), "no COST TOTALS block"))
            else:
                width = len(wm.group(1))
                with contextlib.redirect_stdout(io.StringIO()):
                    old_dl = "\n".join(OLD.daily_log_totals(M, tag, arm, float(eq.iloc[-1]),
                                                            bh_for(OLD, utag, pit, bd, start, tax_on),
                                                            start, tax_on, width))
                if dtext.count(old_dl) != 1:
                    report.append(("skipped", str(dl.relative_to(ROOT)),
                                   "step 1: the totals block does not reproduce byte for byte"))
                else:
                    new_dl = "\n".join(NEW.daily_log_totals(M, tag, arm, float(eq.iloc[-1]), bh_new,
                                                            start, tax_on, width,
                                                            summary_text=new_text))
                    i = dtext.index(old_dl)
                    dl_new = dtext[:i] + new_dl + "\n" + note.rstrip("\n") + dtext[i + len(old_dl):]
                    if dl_new[:i] != dtext[:i] or not dl_new.endswith(dtext[i + len(old_dl):]):
                        report.append(("skipped", str(dl.relative_to(ROOT)), "step 3: bytes outside the block moved"))
                        dl_new = None
        # THE RUN LOG's copy of this block.
        if log_new is not None:
            n = log_new.count(text)
            if n != 1:
                report.append(("skipped", f"{run_log.relative_to(ROOT)} [{tag}]",
                               f"step 1: the block appears {n} times, not once"))
            else:
                i = log_new.index(text)
                log_new = log_new[:i] + new_text + note + log_new[i + len(text):]
                report.append(("rewritten", f"{run_log.relative_to(ROOT)} [{tag}]", nm))
        if write:
            f.write_text(new_text + note)
        report.append(("rewritten", str(f.relative_to(ROOT)), nm))
        if dl_new is not None:
            if write:
                dl.write_text(dl_new)
            report.append(("rewritten", str(dl.relative_to(ROOT)), nm))
    if write and run_log is not None and log_new != log_text:
        run_log.write_text(log_new)


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--write", action="store_true")
    ap.add_argument("--commit", default=None, help="the commit of the cost_report fix")
    ap.add_argument("--report", default=None, help="write the per-file outcome to this CSV")
    a = ap.parse_args()
    if a.write and not a.commit:
        ap.error("--write needs --commit, the hash the rebuilt line names")
    date = dt.date.today().isoformat()
    commit = a.commit or "<not written>"
    report = []
    for M in sorted(ROOT.glob("results_*/metrics")):
        rebuild_dir(M, None, date, commit, a.write, report)
    for folder in sorted(p for p in (ROOT / "runs").iterdir() if re.match(r"^\d{8}T\d{6}_", p.name)):
        log = folder / "run.log"
        dirs = sorted(folder.glob("results_*/metrics"))
        if not dirs:
            continue
        for k, M in enumerate(dirs):
            rebuild_dir(M, log if log.exists() else None, date, commit, a.write, report)
    df = pd.DataFrame(report, columns=["outcome", "file", "detail"])
    if a.report:
        # naming: axis-free -- one record of a maintenance pass over every run on disk
        df.to_csv(a.report, index=False)
    kind = df["file"].map(lambda s: "run.log block" if "run.log" in s else
                          ("COST_SUMMARY" if "COST_SUMMARY" in s else "DAILY_LOG"))
    where = df["file"].map(lambda s: "run folder" if s.startswith("runs/") else "canonical")
    print(pd.crosstab([where, kind], df["outcome"]).to_string())
    for _, r in df[df.outcome == "skipped"].iterrows():
        print(f"  skipped: {r.file}: {r.detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
