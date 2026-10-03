"""
drawdown_stop_judge.py -- stage 5 of experiments/DRAWDOWN_STOP_PREREG.txt: judge v5 and
v6 against the committed band, and print the reported-only figures.

    ./venv/bin/python results/drawdown_stop_judge.py

Reads what `run.py --universe all --arm v5,v6` wrote under each of the four settings
(research and tradeable, tax off and on, cadence 20), the published v1 and v3 curves,
and experiments/DRAWDOWN_STOP_BAND.csv. Writes nothing; everything is printed.

Metrics are computed from the equity curves with the band writer's raw_metrics, so d
is measured exactly as the band was. d = stop arm metric - parent metric.

Criteria, word for word from the pre-registration:
    1. MaxDD shallower than the parent's by more than the band in >= 18 of 24 cells,
       and deeper by more than the band in none.
    2. Calmar higher by more than the band in >= 15 of 24 cells.
    3. CAGR lower by more than the band in <= 6 of 24 cells.
    4. In >= 4 of the 6 judged universes, exits in >= 2 separate episodes of the
       parent's research, tax-off, cadence-20 curve (episodes of 20% or deeper).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "results"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd

import arms.registry as arm_reg
from config import read_table
from drawdown_stop_band import raw_metrics, setting_suffix, SETTINGS
from universes.registry import REGISTRY

JUDGED = ("nifty50", "midcap50", "midcap100", "nifty100", "midcap150", "smallcap250")
REPORTED = ("nifty200", "nifty500")
PAIRS = (("v5", "v1"), ("v6", "v3"))
EPISODE_DEPTH = 0.20
NEED = {1: 18, 2: 15, 3: 6, 4: 4}


def setting_name(profile, tax):
    return f"{profile}/{'on' if tax else 'off'}"


def curves(tag, profile, tax):
    """{arm: equity Series} for v1, v3 (published files) and v5, v6 (stop files)."""
    M = REGISTRY[tag].metrics_dir
    sfx = setting_suffix(profile, tax)
    core = read_table(M / f"v34_equity{sfx}.csv", parse_dates=["date"]).set_index("date")
    stop = read_table(M / f"v34_stop_equity{sfx}.csv", parse_dates=["date"]).set_index("date")
    out = {a: core[arm_reg.ARMS[a].equity_column] for a in ("v1", "v3")}
    out.update({a: stop[arm_reg.STOP_ARMS[a].equity_column] for a in ("v5", "v6")})
    out["bh"] = stop["buyhold"]
    return out


def events(tag, arm, profile, tax):
    import audit_step
    import cadence
    import profiles
    import tax as tax_axis
    profiles.set_selection(profile)
    tax_axis.set_selection(tax)
    cadence.set_selection(None)
    try:
        t = audit_step.artefact_tag(REGISTRY[tag], arm_reg.STOP_ARMS[arm])
    finally:
        profiles.set_selection(None)
        tax_axis.set_selection(False)
    p = REGISTRY[tag].metrics_dir / f"daily_stop_events_{t}.csv"
    return p, read_table(p, parse_dates=["date"])


def episodes(eq):
    """Episodes of a curve: (peak date, trough date, depth, next all-time-high date).

    An episode runs from an all-time high to the next all-time high. Only those
    falling EPISODE_DEPTH or more below the high are returned."""
    out = []
    peak_v, peak_d, low_v, low_d = eq.iloc[0], eq.index[0], eq.iloc[0], eq.index[0]
    for d, v in eq.items():
        if v > peak_v:
            if low_v / peak_v - 1 <= -EPISODE_DEPTH:
                out.append((peak_d, low_d, low_v / peak_v - 1, d))
            peak_v, peak_d, low_v, low_d = v, d, v, d
        elif v < low_v:
            low_v, low_d = v, d
    if low_v / peak_v - 1 <= -EPISODE_DEPTH:
        out.append((peak_d, low_d, low_v / peak_v - 1, None))
    return out


def episode_of(date, eps):
    """Index of the episode an exit on `date` falls in, or None. An episode covers
    [peak date, next all-time-high date)."""
    for k, (p, _t, _dep, rec) in enumerate(eps):
        if date >= p and (rec is None or date < rec):
            return k
    return None


def cash_days(ev, index):
    """Trading days with the book flat: from each 'flat' event to the next re-entry
    fill, exclusive, or to the end of the window."""
    n = 0
    flats = list(ev.loc[ev["event"] == "flat", "date"])
    fills = list(ev.loc[ev["event"] == "re-entry filled", "date"])
    for f in flats:
        nxt = [x for x in fills if x > f]
        end = nxt[0] if nxt else None
        sel = (index >= f) & ((index < end) if end is not None else True)
        n += int(sel.sum())
    return n


def fmt(x, nd=3):
    return f"{x:+.{nd}f}"


def main():
    band = read_table(ROOT / "experiments" / "DRAWDOWN_STOP_BAND.csv", comment="#")
    band = band.set_index(["universe", "profile", "tax", "comparison", "metric"])["band"]

    C = {(t, p, x): curves(t, p, x) for t in JUDGED + REPORTED for p, x in SETTINGS}
    verdicts = {}
    for stop, parent in PAIRS:
        comp = f"{stop} - {parent}"
        print("=" * 100)
        print(f"{stop} AGAINST {parent}")
        print("=" * 100)
        counts = {}
        for crit, metric, test in ((1, "MaxDD%", "shallower"), (2, "Calmar", "higher"),
                                   (3, "CAGR%", "lower")):
            print(f"\nCriterion {crit}: {metric}, counted when the stop arm is {test} than "
                  f"the parent by more than the band")
            print(f"  {'universe':<12} {'setting':<15} {'parent':>10} {'stop':>10} {'d':>9} "
                  f"{'band':>8}  counts")
            n_good, n_bad = 0, 0
            for t in JUDGED:
                for p, x in SETTINGS:
                    m_par = raw_metrics(C[(t, p, x)][parent])[metric]
                    m_stp = raw_metrics(C[(t, p, x)][stop])[metric]
                    d = m_stp - m_par
                    b = band[(t, p, "on" if x else "off", comp, metric)]
                    if crit == 3:
                        hit = d < -b
                    else:
                        hit = d > b
                    deeper = crit == 1 and d < -b
                    n_good += hit
                    n_bad += deeper
                    tag = "yes" if hit else ("DEEPER BY MORE THAN BAND" if deeper else "no")
                    print(f"  {t:<12} {setting_name(p, x):<15} {m_par:>10.3f} {m_stp:>10.3f} "
                          f"{fmt(d):>9} {b:>8.3f}  {tag}")
            if crit == 1:
                ok = n_good >= NEED[1] and n_bad == 0
                print(f"  COUNT: shallower by more than the band in {n_good} of 24 (need >= 18); "
                      f"deeper by more than the band in {n_bad} (need 0) -> "
                      f"{'PASS' if ok else 'FAIL'}")
            elif crit == 2:
                ok = n_good >= NEED[2]
                print(f"  COUNT: {n_good} of 24 (need >= 15) -> {'PASS' if ok else 'FAIL'}")
            else:
                ok = n_good <= NEED[3]
                print(f"  COUNT: {n_good} of 24 (need <= 6) -> {'PASS' if ok else 'FAIL'}")
            counts[crit] = ok

        print("\nSharpe, not a criterion; d and band for reference")
        for t in JUDGED:
            for p, x in SETTINGS:
                m_par = raw_metrics(C[(t, p, x)][parent])["Sharpe"]
                m_stp = raw_metrics(C[(t, p, x)][stop])["Sharpe"]
                b = band[(t, p, "on" if x else "off", comp, "Sharpe")]
                print(f"  {t:<12} {setting_name(p, x):<15} {m_par:>8.3f} {m_stp:>8.3f} "
                      f"{fmt(m_stp - m_par):>8} {b:>7.3f}")

        print(f"\nCriterion 4: exits mapped to {parent}'s research, tax-off episodes "
              f"of 20% or deeper")
        c4 = {}
        for p, x in SETTINGS:
            n_univ = 0
            print(f"  setting {setting_name(p, x)}")
            for t in JUDGED:
                eps = episodes(C[(t, "research", False)][parent])
                _, ev = events(t, stop, p, x)
                exits = list(ev.loc[ev["event"] == "trigger", "date"])
                fills = list(ev.loc[ev["event"] == "exit fills", "date"])
                mapped = [episode_of(d, eps) for d in exits]
                # An exit triggers at a close and fills at the next open. Both dates
                # must fall in the same parent episode, or the mapping is ambiguous.
                by_fill = [episode_of(d, eps) for d in fills]
                if by_fill != mapped[:len(by_fill)]:
                    print(f"    {t}: AMBIGUOUS -- trigger dates map to {mapped}, fill "
                          f"dates to {by_fill}")
                distinct = sorted({m for m in mapped if m is not None})
                n_univ += len(distinct) >= 2
                desc = ", ".join(
                    f"{d.date()}->" + (f"ep{m + 1}({eps[m][0].date()} {eps[m][2] * 100:.1f}%)"
                                       if m is not None else "none")
                    for d, m in zip(exits, mapped))
                print(f"    {t:<12} triggers {len(exits)}, fills {len(fills)}, distinct episodes "
                      f"{len(distinct)}  {'counts' if len(distinct) >= 2 else ''}")
                print(f"      {desc or '(no exit)'}")
            ok = n_univ >= NEED[4]
            c4[(p, x)] = ok
            print(f"    COUNT: {n_univ} of 6 universes (need >= 4) -> {'PASS' if ok else 'FAIL'}")

        print("\n  Parent episodes used (research, tax off):")
        for t in JUDGED:
            for k, (pk, tr, dep, rec) in enumerate(episodes(C[(t, "research", False)][parent])):
                print(f"    {t:<12} ep{k + 1}  {pk.date()}  {tr.date()}  {dep * 100:.1f}%  "
                      f"{rec.date() if rec is not None else 'not recovered'}")

        c4_vals = set(c4.values())
        if len(c4_vals) > 1:
            verdict = "CRITERION 4 DIFFERS ACROSS SETTINGS -- NOT DECIDED"
        elif not c4_vals.pop():
            verdict = "ONE EPISODE, UNJUDGEABLE"
        elif all(counts[k] for k in (1, 2, 3)):
            verdict = "ACCEPT"
        else:
            verdict = "REJECT"
        verdicts[stop] = (counts, c4, verdict)
        print(f"\nVERDICT {stop}: {verdict}  (criteria 1-3: "
              + ", ".join(f"{k} {'PASS' if counts[k] else 'FAIL'}" for k in (1, 2, 3))
              + "; criterion 4: "
              + ", ".join(f"{setting_name(p, x)} {'PASS' if v else 'FAIL'}"
                          for (p, x), v in c4.items()) + ")")

    print("\n" + "=" * 100)
    print("REPORTED, NOT JUDGED")
    print("=" * 100)
    print("\nnifty200 and nifty500, d = stop - parent (no band exists for these)")
    for t in REPORTED:
        for p, x in SETTINGS:
            for stop, parent in PAIRS:
                a = raw_metrics(C[(t, p, x)][parent])
                s = raw_metrics(C[(t, p, x)][stop])
                print(f"  {t:<10} {setting_name(p, x):<15} {stop}-{parent}  " + "  ".join(
                    f"{m} {a[m]:.3f}->{s[m]:.3f} ({fmt(s[m] - a[m])})"
                    for m in ("MaxDD%", "CAGR%", "Sharpe", "Calmar")))

    print("\nStop arms against the equal-weight buy & hold")
    for t in JUDGED + REPORTED:
        for p, x in SETTINGS:
            bh = raw_metrics(C[(t, p, x)]["bh"])
            for stop in ("v5", "v6"):
                s = raw_metrics(C[(t, p, x)][stop])
                print(f"  {t:<12} {setting_name(p, x):<15} {stop}  " + "  ".join(
                    f"{m} {s[m]:.2f} vs {bh[m]:.2f}" for m in ("CAGR%", "MaxDD%", "Sharpe",
                                                             "Calmar")))

    print("\nSub-periods (v34_stop_subperiods), stop arms and buy & hold")
    for t in JUDGED + REPORTED:
        for p, x in SETTINGS:
            M = REGISTRY[t].metrics_dir
            sp = read_table(M / f"v34_stop_subperiods{setting_suffix(p, x)}.csv")
            for _, r in sp.iterrows():
                nm = r["Config"].split(" ")[0] if r["Config"].startswith("v") else "bh"
                print(f"  {t:<12} {setting_name(p, x):<15} {r['Period']} {nm:<3} "
                      f"CAGR {r['CAGR%']:>7.2f}  Sharpe {r['Sharpe']:>5.2f}  "
                      f"MaxDD {r['MaxDD%']:>7.2f}")

    print("\nExits, re-entries, days in cash, and the true drawdown from the all-time peak "
          "(the stop's peak resets at re-entry; this one does not)")
    for t in JUDGED + REPORTED:
        for p, x in SETTINGS:
            for stop in ("v5", "v6"):
                path, ev = events(t, stop, p, x)
                eq = C[(t, p, x)][stop]
                n_ex = int((ev["event"] == "exit fills").sum())
                n_re = int((ev["event"] == "re-entry filled").sum())
                cd = cash_days(ev, eq.index)
                true_dd = raw_metrics(eq)["MaxDD%"]
                print(f"  {t:<12} {setting_name(p, x):<15} {stop}  exits {n_ex}  re-entries "
                      f"{n_re}  days in cash {cd:>4} of {len(eq)}  true MaxDD "
                      f"{true_dd:.2f}%")

    print("\nSUMMARY")
    for stop, (counts, c4, verdict) in verdicts.items():
        print(f"  {stop}: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
