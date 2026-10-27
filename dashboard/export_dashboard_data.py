"""
export_dashboard_data.py -- collect every finished run's results into dashboard_data.json.

    ./venv/bin/python dashboard/export_dashboard_data.py      (from the repository root)

Writes dashboard/dashboard_data.json, which .gitignore excludes. Reads only what is
already on disk in the repository and runs nothing. Every figure is either read from
a run's own files or computed the way the repository's own code computes it; the
source of each is named next to it below.

What counts as a run: every directory runs/<timestamp>_<selection>/runs/<universe>/<seg>/
that holds params.json and comparison.csv, inside a run folder whose RUN.txt has a
"finished" line. One run is one universe and one arm under one setting of every
axis.

PUBLISHED OR AD HOC. dashboard/PUBLISHED_RUNS.txt names the run folders behind the
published figures, and the earlier runs of those combinations that they superseded.
A run from a published folder goes in "runs": it is the one run shown for its
combination, and only these runs feed check f and the ladder. A superseded folder is
not shown. A run from any other folder goes in "ad_hoc": it is shown apart, labelled
ad hoc, and never replaces a published cell, even when it holds the same combination.
"""
import argparse
import ast
import datetime as dt
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DEFAULT_REPO = HERE.parent
PUBLISHED_LIST = HERE / "PUBLISHED_RUNS.txt"


def published_list(repo):
    """(published, superseded): the folder names under the [published] and
    [superseded] headings of PUBLISHED_RUNS.txt. Blank lines and # lines are skipped."""
    out, head = {"published": set(), "superseded": set()}, None
    for line in (Path(repo) / "dashboard" / PUBLISHED_LIST.name).read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s in ("[published]", "[superseded]"):
            head = s[1:-1]
            continue
        if head is None:
            raise SystemExit(f"{PUBLISHED_LIST.name}: {s} comes before any heading")
        out[head].add(s)
    both = out["published"] & out["superseded"]
    if both:
        raise SystemExit(f"{PUBLISHED_LIST.name}: listed as both published and superseded: "
                         + ", ".join(sorted(both)))
    return out["published"], out["superseded"]


def read_table(path, **kw):
    """config.read_table, the repository's one CSV reader: floats are parsed
    round-trip, and platform_identity_check fails any other CSV read."""
    import config
    return config.read_table(path, **kw)


# Axis values that take no flag on the command line.
NO_FLAG = {"cadence": {"20"}, "dd": {"off"}, "capital": {"1000000"}, "impact": {"0"},
           "pcap": {"1", "none"}, "start": {"2019-01-01"}}

LABELS = {
    "universe": "Universe",
    "arm": "Arm (strategy variant)",
    "cadence": "Rebalance every N trading days",
    "profile": "Execution profile",
    "tax": "Capital-gains tax",
    "survivorship": "Universe construction (survivorship)",
    "dd": "Drawdown limit, percent",
    "capital": "Starting capital, rupees",
    "impact": "Market impact coefficient k",
    "pcap": "Participation cap, fraction of median volume",
    "fixed": "Fixed capital (profits not reinvested)",
    "start": "Backtest start date",
    "buy_shortfall": "A buy cash cannot fully pay for (trim or refuse)",
}

# Named cells for check f: (universe, arm). Setting: pit, tradeable, tax on,
# cadence 20, Rs 10 lakh, impact 0, the profile's own cap.
CHECK_F_CELLS = (("nifty200", "v3"), ("nifty200", "v1"), ("midcap100", "v1"))


def num(x):
    """A float, or None for NaN and empty values."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def fmt(x):
    """An axis value as the code spells it: 0.003, 0.1, 1, 500000."""
    return f"{float(x):g}"


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, check=True).stdout.strip()


def read_run_txt(p):
    """RUN.txt as a dict of its top-level "key : value" lines (first occurrence wins)."""
    out = {}
    for line in p.read_text().splitlines():
        m = re.match(r"^([a-z][a-z ]*?)\s*:\s*(.*)$", line)
        if m and not line.startswith(" ") and m.group(1) not in out:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


# ---------------------------------------------------------------------------
# The repository's own formulas, copied from where they live.
# ---------------------------------------------------------------------------
def years_between(d0, d1):
    """results/engine_core.py metrics(): calendar days / 365.25."""
    return (d1 - d0).days / 365.25


def cagr_pct(s):
    """results/make_chart.py cagr() and tools/year_by_year.py cagr()."""
    y = years_between(s.index[0], s.index[-1])
    return ((s.iloc[-1] / s.iloc[0]) ** (1 / y) - 1) * 100


def dd_pct(s):
    """results/make_chart.py dd(): percent below the running peak."""
    return (s / s.cummax() - 1) * 100


def yearly_pct(s):
    """tools/year_by_year.py yearly(): each calendar year from the previous year's
    last close (the window's first value for the first year) to its own last close."""
    out, prev = {}, s.iloc[0]
    for y, g in s.groupby(s.index.year):
        out[int(y)] = (g.iloc[-1] / prev - 1) * 100
        prev = g.iloc[-1]
    return out


def deepest_episode(eq):
    """Peak and trough dates of the deepest drawdown, by the episode walk in
    results/drawdown_stop_judge.py: the trough is the lowest point before the curve
    makes a new high, the peak is the high it fell from."""
    peak_v, peak_d, low_v, low_d = eq.iloc[0], eq.index[0], eq.iloc[0], eq.index[0]
    best = (0.0, None, None)
    for d, v in eq.items():
        if v > peak_v:
            if low_v / peak_v - 1 < best[0]:
                best = (low_v / peak_v - 1, peak_d, low_d)
            peak_v, peak_d, low_v, low_d = v, d, v, d
        elif v < low_v:
            low_v, low_d = v, d
    if low_v / peak_v - 1 < best[0]:
        best = (low_v / peak_v - 1, peak_d, low_d)
    return best[1], best[2]


# ---------------------------------------------------------------------------
# nt_verify coverage, read from check_all.py's gate list.
# ---------------------------------------------------------------------------
def nt_verify_cells(repo):
    """(gated cells, ungated cells) as named in check_all.py. The gate runs
    nt_verify at the default cell only: static, research, tax off, cadence 20,
    Rs 10 lakh, no drawdown limit, no impact, no cap."""
    src = (repo / "check_all.py").read_text()
    tree = ast.parse(src)
    ungated = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", "") == "NT_VERIFY_UNGATED" for t in node.targets):
            ungated = {(u, a) for u, a, _ in ast.literal_eval(node.value)}
    start = src.index('("nautilus/nt_verify.py"')
    end = src.index("NT_VERIFY_UNGATED}]", start)
    listed = set(re.findall(r'\("(\w+)", "(v\d)"\)', src[start:end]))
    return listed - ungated, ungated


# ---------------------------------------------------------------------------
# Published figures for check f.
# ---------------------------------------------------------------------------
def published_check_f(repo):
    """README "pit, tradeable profile" table, tax-on headline CAGR and MaxDD, and the
    equal-weight basket CAGR from results_<u>/metrics/v34_comparison_tradeable_tax_pit.csv
    (the canonical output; the README does not print that basket)."""
    lines = (repo / "README.md").read_text().splitlines()
    i = lines.index("**pit, tradeable profile**")
    out = {}
    for line in lines[i + 1:]:
        if line.startswith("**") or line.startswith("#"):
            break
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 6 and (cells[0], cells[1]) in CHECK_F_CELLS:
            out[(cells[0], cells[1])] = {"cagr": float(cells[4]), "max_dd": float(cells[5])}
    for u, a in CHECK_F_CELLS:
        comp = read_table(repo / f"results_{u}" / "metrics" / "v34_comparison_tradeable_tax_pit.csv")
        row = comp[comp["Config"] == "buy & hold equal-weight"].iloc[0]
        out.setdefault((u, a), {})["basket_cagr"] = float(row["CAGR%"])
    return out


# ---------------------------------------------------------------------------
# One run.
# ---------------------------------------------------------------------------
ROUNDED = {}  # column -> decimals seen in the source files, filled as runs are read


def rounded_to(path):
    """Decimals of the rounded figures this run reads from comparison.csv. Recorded
    per run as the most decimals any comparison.csv carries in that column, which is
    the writer's rounding (results/engine_core.py metrics(): round(x, 2)); a single
    value such as "30.0" has dropped its trailing zero and would understate it."""
    import csv
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            for col in ("CAGR%", "MaxDD%", "FinalEquity"):
                v = row.get(col) or ""
                d = len(v.split(".")[1]) if "." in v else 0
                ROUNDED[col] = max(ROUNDED.get(col, 0), d)
    return {"cagr": "CAGR%", "max_dd": "MaxDD%", "end_equity": "FinalEquity",
            "basket_cagr": "CAGR%", "basket_max_dd": "MaxDD%"}


def run_axes(params, run_txt, seg):
    arm = seg.split("@")[0]
    prof = params.get("profile", "research")
    surv = "pit" if "survivorship" in params or "@pit" in seg else "static"
    dd = run_txt.get("dd") or run_txt.get("drawdown limit")
    m = re.search(r"@dd([0-9p]+)", seg)
    dd = fmt(dd) if dd and re.match(r"^[0-9.]+$", dd) else (m.group(1).replace("p", ".") if m else "off")
    cap = run_txt.get("capital")
    m = re.search(r"@cap(\d+)", seg)
    cap = str(int(float(cap))) if cap and re.match(r"^[0-9.]+$", cap) else (m.group(1) if m else "1000000")
    k = params.get("impact_k", 0.0)
    pc = params.get("participation_cap")
    if pc is None:
        pc = None if prof == "research" else 1.0
    return {
        "universe": params["universe_tag"],
        "arm": arm,
        "cadence": str(int(params["rebal"])),
        "profile": prof,
        "tax": params.get("tax", "off"),
        "survivorship": surv,
        "dd": dd,
        "capital": cap,
        "impact": fmt(k),
        "pcap": "none" if pc is None else fmt(pc),
        "fixed": "on" if params.get("fixed_capital") or "@fixed" in seg else "off",
        "start": _start_of(params, seg),
        # Absent from every params file written before 2026-10-27, when every short
        # buy was refused; those runs carry no @refuse segment.
        "buy_shortfall": params.get("buy_shortfall", "refuse"),
    }


def _start_of(params, seg):
    """The run's backtest start as YYYY-MM-DD: params bt_start, else the @s segment,
    else the default. Every run before 2026-10-22 started at the default."""
    if params.get("bt_start"):
        return str(params["bt_start"])
    m = re.search(r"@s(\d{4})(\d{2})(\d{2})", seg)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else "2019-01-01"


def expected_segment(ax, refuse_named=True):
    """The arm directory name naming.path_tail would give these axes.
    refuse_named=False for a run from before 2026-10-27: it refused short buys
    and its name has no @refuse."""
    s = ax["arm"]
    if ax["cadence"] != "20":
        s += f"@r{ax['cadence']}"
    if ax["profile"] != "research":
        s += f"@{ax['profile']}"
    if ax["tax"] == "on":
        s += "@tax"
    if ax["survivorship"] == "pit":
        s += "@pit"
    if ax["dd"] != "off":
        s += "@dd" + ax["dd"].replace(".", "p")
    if ax["capital"] != "1000000":
        s += f"@cap{ax['capital']}"
    if ax["impact"] != "0":
        s += "@impact" + ax["impact"].replace(".", "p")
    if ax["pcap"] not in ("1", "none"):
        s += "@pcap" + ax["pcap"].replace(".", "p")
    if ax["fixed"] == "on":
        s += "@fixed"
    if ax["start"] != "2019-01-01":
        s += "@s" + ax["start"].replace("-", "")
    if ax["buy_shortfall"] == "refuse" and refuse_named:
        s += "@refuse"
    return s


def flags_for(ax, universe_sel, arm_sel):
    """Command-line flags in run.py's argument order. Defaults take no flag."""
    f = [f"--universe {universe_sel}", f"--arm {arm_sel}"]
    if ax["cadence"] not in NO_FLAG["cadence"]:
        f.append(f"--rebal {ax['cadence']}")
    if ax["tax"] == "on":
        f.append("--tax on")
    if ax["profile"] == "tradeable":
        f.append("--profile tradeable")
    if ax["survivorship"] == "pit":
        f.append("--survivorship pit")
    if ax["dd"] not in NO_FLAG["dd"]:
        f.append(f"--dd {ax['dd']}")
    if ax["capital"] not in NO_FLAG["capital"]:
        f.append(f"--capital {ax['capital']}")
    # run.py refuses a capital other than the default without --impact, 0 included.
    if ax["impact"] not in NO_FLAG["impact"] or ax["capital"] not in NO_FLAG["capital"]:
        f.append(f"--impact {ax['impact']}")
    if ax["pcap"] not in NO_FLAG["pcap"]:
        f.append(f"--cap {ax['pcap']}")
    if ax["fixed"] == "on":
        f.append("--fixed-capital")
    if ax["start"] not in NO_FLAG["start"]:
        f.append(f"--start {ax['start']}")
    if ax["buy_shortfall"] == "refuse":
        f.append("--buy-shortfall refuse")
    return " ".join(f)


def cli_command(axes, ax):
    """The flags the exported cli rules give for one run, in axes order."""
    out, by = [], {a["name"]: a for a in axes}
    for a in axes:
        v = ax[a["name"]]
        if a["open_number"]:
            req = a.get("required_with")
            if v not in a["no_flag"] or (req and ax[req] not in by[req]["no_flag"]):
                out.append(a["cli"].replace("{value}", v))
        elif a["cli"].get(v):
            out.append(a["cli"][v])
    return " ".join(out)


def flag_pairs(cmd):
    """{"--flag": "value"} from a flag string. A flag followed by another flag, or
    by nothing, is a switch (--fixed-capital) and maps to ""."""
    t, out, i = cmd.split(), {}, 0
    while i < len(t):
        if i + 1 < len(t) and not t[i + 1].startswith("--"):
            out[t[i]] = t[i + 1]
            i += 2
        else:
            out[t[i]] = ""
            i += 1
    return out


def weekly_index(dates):
    """Positions of the last trading day of each week, plus the first and last day."""
    s = pd.Series(range(len(dates)), index=dates)
    iso = dates.isocalendar()
    keys = list(zip(iso["year"], iso["week"]))
    last = {}
    for i, k in enumerate(keys):
        last[k] = i
    pos = sorted(set(last.values()) | {0, len(dates) - 1})
    return pos, keys


def build_run(repo, folder, udir, seg, run_txt, index_files, checks):
    rdir = folder / "runs" / udir / seg
    params = json.loads((rdir / "params.json").read_text())
    comp = read_table(rdir / "comparison.csv")
    ax = run_axes(params, run_txt, seg)
    _named = "buy_shortfall" in params
    if expected_segment(ax, _named) != seg:
        checks.append(f"Run {folder.name}/{udir}/{seg}: the axes read from params.json "
                      f"and RUN.txt give the directory name {expected_segment(ax, _named)}, "
                      f"not {seg}.")
    u, arm = ax["universe"], ax["arm"]

    # Daily equity: the arm's column and the basket, from the run's own equity.csv.
    eqf = read_table(rdir / "equity.csv", parse_dates=["date"]).set_index("date").sort_index()
    strat_col = [c for c in eqf.columns if c != "buyhold"][0]
    eq = eqf[strat_col].astype(float)
    bask = eqf["buyhold"].astype(float)
    start_eq, start_d, end_d = float(eq.iloc[0]), eq.index[0], eq.index[-1]
    years = years_between(start_d, end_d)

    srow = comp.iloc[0]  # the arm's row comes first
    brow = comp[comp["Config"] == "buy & hold equal-weight"]
    brow = brow.iloc[0] if len(brow) else None

    # The universe's own NSE index, forward-filled onto the run's dates
    # (results/make_chart.py), scaled to the run's start equity.
    idx_s = None
    idx_name = None
    if index_files.get(u):
        name, path, series = index_files[u]
        ix = series.reindex(eq.index.union(series.index)).ffill().reindex(eq.index)
        if ix.notna().all():
            idx_s = start_eq * ix / ix.iloc[0]
            idx_name = name

    mp = folder / f"results_{u}" / "metrics"
    tag = u if arm == "v2" else f"{u}_{arm}"
    tail = seg.split("@", 1)[1].replace("@", "_") if "@" in seg else ""
    tail = ("_" + tail) if tail else ""
    tail = re.sub(r"_r\d+", "", tail)  # the cadence is not in these file names at 20
    if ax["cadence"] != "20":
        tail = f"_r{ax['cadence']}" + tail

    def mfile(stem, ext):
        p = mp / f"{stem}_{tag}{tail}{ext}"
        return p if p.exists() else None

    costs_f, years_f = mfile("COSTS", ".csv"), mfile("COST_TAX_YEARS", ".csv")
    skipped_f = mfile("daily_skipped", ".csv")
    fy_f, log_f = mfile("FY_TAX_STATEMENT", ".csv"), mfile("DAILY_LOG", ".txt")

    costs = {"slippage": None, "charges": None, "impact": None, "tax": None}
    breakdown = None
    if costs_f:
        c = read_table(costs_f)
        costs["slippage"] = float(c["slippage_rs"].sum())
        costs["charges"] = float(c["charges_total"].sum())
        costs["impact"] = float(c["impact_rs"].sum()) if "impact_rs" in c else 0.0
        names = [n for n in ("brokerage", "stt", "exchange_txn", "sebi", "stamp_duty",
                             "ipft", "dp", "gst") if n in c]
        breakdown = {n: float(c[n].sum()) for n in names}
    # CAPACITY (capacity.py): fills against the stock's 20-day average traded value,
    # and what the cap left unfilled. None when the run folder holds no COSTS file.
    capacity = None
    if costs_f:
        import capacity as _capacity
        capacity = _capacity.measure(c, read_table(skipped_f) if skipped_f else None,
                                     RAW_DIRS[(u, ax["survivorship"])], CAP_CACHE)
    if years_f:
        costs["tax"] = float(read_table(years_f)["total_tax"].sum())

    # Tax paid in each calendar year: FY_TAX_STATEMENT total_tax by the date it left
    # cash (assessed_on). With tax off there is no statement and no tax was charged.
    paid = {}
    if fy_f:
        fy = read_table(fy_f, parse_dates=["assessed_on"])
        for d, t in zip(fy["assessed_on"], fy["total_tax"]):
            paid[d.year] = paid.get(d.year, 0.0) + float(t)
    tax_known = fy_f is not None or ax["tax"] == "off"

    rebal = None
    if log_f:
        m = re.search(r"Rebalances\s*:\s*([\d,]+)", log_f.read_text()[:4000])
        rebal = int(m.group(1).replace(",", "")) if m else None

    ys, yb = yearly_pct(eq), yearly_pct(bask)
    yi = yearly_pct(idx_s) if idx_s is not None else {}
    w0 = pd.Timestamp(params.get("window_start", str(start_d.date())))
    w1 = pd.Timestamp(params.get("window_end", str(end_d.date())))
    yearly = [{"year": y,
               "full_year": bool(w0 <= pd.Timestamp(f"{y}-01-01") and w1 >= pd.Timestamp(f"{y}-12-31")),
               "strategy": ys[y], "basket": yb.get(y), "index": yi.get(y),
               "tax_paid": paid.get(y, 0.0) if tax_known else None}
              for y in ys]

    # Weekly lists.
    pos, _ = weekly_index(eq.index)
    # The basket curve is the run's own buyhold column, unscaled: the series the
    # repository's basket CAGR, MaxDD and FinalEquity are computed from. Its first
    # value already includes the window's first day return, so it is not exactly
    # the strategy's start equity.
    bs = bask
    dd_s, dd_b = dd_pct(eq), dd_pct(bask)
    iso = eq.index.isocalendar()
    wk = pd.Series(list(zip(iso["year"], iso["week"])), index=eq.index)
    wmin_s = dd_s.groupby(wk.values).min()
    wmin_b = dd_b.groupby(wk.values).min()
    dates = [eq.index[i] for i in pos]
    equity = {
        "dates": [d.strftime("%Y-%m-%d") for d in dates],
        "strategy": [float(eq.iloc[i]) for i in pos],
        "basket": [float(bs.iloc[i]) for i in pos],
        "index": [float(idx_s.iloc[i]) for i in pos] if idx_s is not None else None,
        # The first point is the run's first day only; it shares its week with the
        # next point, which carries that week's lowest drawdown.
        "drawdown": [float(dd_s.iloc[i]) if i == 0 else float(wmin_s[wk.iloc[i]]) for i in pos],
        "basket_drawdown": [float(dd_b.iloc[i]) if i == 0 else float(wmin_b[wk.iloc[i]]) for i in pos],
    }

    # FIXED-CAPITAL FIGURES, from the run's own fixed.csv and fixed_years.csv
    # (results/fixed_capital.py). Present only in a --fixed-capital arm folder.
    fixed = None
    if (rdir / "fixed.csv").exists():
        fx = read_table(rdir / "fixed.csv")
        fy_ = read_table(rdir / "fixed_years.csv")
        fixed = {}
        for _, row in fx.iterrows():
            yrs = fy_[fy_["Line"] == row["Line"]]
            fixed[row["Line"]] = {
                "config": row["Config"],
                "avg_ann_ret": num(row["AvgAnnRet%"]),
                "mean_full_year": num(row["MeanFullYear%"]),
                "full_years": [int(y) for y in str(row["FullYears"]).split()]
                              if isinstance(row["FullYears"], str) else [],
                "max_dd_rs": num(row["MaxDD_Rs"]),
                "max_dd_base": num(row["MaxDD_base%"]),
                "max_dd_trough": row["MaxDD_trough"],
                "max_invested_base": num(row["MaxInvested_base%"]),
                "max_invested_date": (row["MaxInvested_date"]
                                      if isinstance(row["MaxInvested_date"], str) else None),
                "cagr": num(row[[c for c in fx.columns if c.startswith("CAGR%")][0]]),
                "end_equity": num(row["FinalEquity"]),
                "years": {int(y): {"pnl": num(p), "pct": num(q)}
                          for y, p, q in zip(yrs["Year"], yrs["PnL_Rs"], yrs["Year%"])},
            }

    peak, trough = deepest_episode(eq)
    index_block = None
    if idx_s is not None:
        index_block = {"name": idx_name, "start_equity": float(idx_s.iloc[0]),
                       "cagr": float(cagr_pct(idx_s)),
                       "max_dd": float(dd_pct(idx_s).min()), "end_equity": float(idx_s.iloc[-1])}

    return {
        "id": f"{folder.name}/{udir}/{seg}",
        "path": str(rdir.relative_to(repo)),
        "axes": ax,
        "command": None,  # filled by the caller from the run folder's selection
        "start_date": start_d.strftime("%Y-%m-%d"),
        "end_date": end_d.strftime("%Y-%m-%d"),
        "years": years,
        "start_equity": start_eq,
        "end_equity": num(srow["FinalEquity"]),
        "cagr": num(srow["CAGR%"]),
        "max_dd": num(srow["MaxDD%"]),
        "max_dd_peak": peak.strftime("%Y-%m-%d") if peak is not None else None,
        "max_dd_trough": trough.strftime("%Y-%m-%d") if trough is not None else None,
        "basket": None if brow is None else {
            "name": brow["Config"], "start_equity": float(bask.iloc[0]),
            "cagr": num(brow["CAGR%"]), "max_dd": num(brow["MaxDD%"]),
            "end_equity": float(bask.iloc[-1])},
        "rounded_to": rounded_to(rdir / "comparison.csv"),
        "index": index_block,
        "trades": int(srow["Trades"]) if num(srow["Trades"]) is not None else None,
        "rebalances": rebal,
        "costs": costs,
        "charges_breakdown": breakdown,
        "yearly": yearly,
        "equity": equity,
        "fixed": fixed,
        "capacity": capacity,
        # THE BIAS LABEL of a static-only universe (registry Universe.bias_note), or None.
        "bias_note": getattr(REGISTRY_ROWS.get(u), "bias_note", None),
        "fixed_twin": None,  # filled by the caller: the same run with fixed capital flipped
        "nt_verify": None,  # filled by the caller
        "_folder_ts": folder.name.split("_", 1)[0],
    }


# ---------------------------------------------------------------------------
# Known issues and the ladder.
# ---------------------------------------------------------------------------
def known_issues(repo):
    """Every ### entry of KNOWN_ISSUES.md as written, and the text above the first
    entry under the file's own title. Section headings (##) open no entry."""
    out, title, buf = [], None, []
    lines = (repo / "KNOWN_ISSUES.md").read_text().splitlines()
    for line in lines:
        if line.startswith("# ") and title is None and not out and not buf:
            title = line[2:].strip()
            continue
        if line.startswith("### ") or line.startswith("## "):
            if title is not None and "\n".join(buf).strip():
                out.append({"title": title, "text": "\n".join(buf).strip()})
            title = line.lstrip("#").strip() if line.startswith("### ") else None
            buf = []
            continue
        if title is not None:
            buf.append(line)
    if title is not None and "\n".join(buf).strip():
        out.append({"title": title, "text": "\n".join(buf).strip()})
    return out


def ladder(repo, runs_by_key, checks):
    files = sorted((repo / "diagnostics").glob("capital_ladder_*.csv"))
    if not files:
        checks.append("No capital ladder CSV found in diagnostics/; ladder is empty.")
        return []
    f = files[-1]
    if len(files) > 1:
        checks.append(f"Ladder rows are from {f.name}, the newest of "
                      f"{', '.join(x.name for x in files)}.")
    df = read_table(f)
    out, missing, agree = [], 0, 0
    for r in df.to_dict("records"):
        ax = {"universe": r["universe"], "arm": r["arm"], "cadence": "20",
              "profile": "tradeable", "tax": "on", "survivorship": "pit", "dd": "off",
              "capital": str(int(r["capital"])), "impact": fmt(r["impact_k"]),
              "pcap": fmt(r["pcap"]), "fixed": "off", "start": "2019-01-01",
              "buy_shortfall": "refuse"}
        run = runs_by_key.get(key_of(ax))
        if run is None:
            missing += 1
        elif run["basket"] and abs(run["basket"]["cagr"] - (float(r["cagr"]) - float(r["cagr_minus_basket"]))) <= 0.005:
            agree += 1
        row = {"universe": r["universe"], "arm": r["arm"], "survivorship": "pit",
               "tax": "on", "profile": "tradeable", "cadence": 20,
               "capital": int(r["capital"]), "impact": float(r["impact_k"]),
               "cap": float(r["pcap"]), "cagr": float(r["cagr"]),
               "basket_cagr": (run["basket"]["cagr"] if run and run["basket"]
                               else float(r["cagr"]) - float(r["cagr_minus_basket"])),
               "max_dd": float(r["maxdd"]), "impact_cost": float(r["impact"]),
               "slippage": float(r["slippage"]), "capped_fills": int(r["capped_fills"]),
               "tax_paid": float(r["tax"])}
        for k, v in r.items():  # the CSV's other columns, unchanged
            if k not in ("universe", "arm", "capital", "impact_k", "pcap", "cagr", "maxdd", "tax",
                         "impact", "slippage", "capped_fills"):
                row[k] = v if not isinstance(v, float) or not math.isnan(v) else None
        out.append(row)
    checks.append(f"Ladder: {len(out)} rows from {f.name}; the fixed settings (pit, tradeable, "
                  f"tax on, cadence 20, no drawdown limit) are those tools/capital_ladder.py "
                  f"reads. basket_cagr is the matching run's basket CAGR; for the {missing} "
                  f"rows with no matching run it is the CSV's cagr minus cagr_minus_basket, the "
                  f"basket CAGR tools/capital_ladder.py subtracted. On rows that have a run, the "
                  f"two agree on {agree} of {len(out) - missing}.")
    return out


# The headline figures the staleness check compares, as the run view shows them.
HEADLINE = (("cagr", lambda r: r["cagr"]), ("max_dd", lambda r: r["max_dd"]),
            ("end_equity", lambda r: r["end_equity"]),
            ("basket_cagr", lambda r: r["basket"] and r["basket"]["cagr"]),
            ("tax", lambda r: r["costs"]["tax"]))


def key_of(ax):
    return tuple(ax[a] for a in AXIS_ORDER)


AXIS_ORDER = None  # set in main from naming.AXES
REGISTRY_ROWS = {}  # set in main from universes.registry.REGISTRY
RAW_DIRS = {}  # (universe tag, "static" | "pit") -> raw price directory, set in main
CAP_CACHE = {}  # capacity.py's per-symbol price series, shared by every run of one export


def main():
    global AXIS_ORDER
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(DEFAULT_REPO))
    ap.add_argument("--out", default=str(HERE / "dashboard_data.json"))
    a = ap.parse_args()
    repo = Path(a.repo).expanduser().resolve()
    sys.path.insert(0, str(repo))

    import naming
    import config
    from universes.registry import REGISTRY
    from arms.registry import ARMS

    AXIS_ORDER = ("universe",) + tuple(naming.AXES)
    REGISTRY_ROWS.update(REGISTRY)
    checks = [f"Axes: universe is not in naming.AXES (it is chosen by --universe and "
              f"names the run folder); it is listed first, then naming.AXES in order: "
              f"{', '.join(naming.AXES)}."]

    porcelain = git(repo, "status", "--porcelain")
    repo_info = {"head": git(repo, "rev-parse", "--short", "HEAD"),
                 "branch": git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
                 "clean": porcelain == ""}

    index_files, data_end = {}, None
    for tag, u in REGISTRY.items():
        if u.index_file is not None and Path(u.index_file).exists():
            s = (config.read_price_csv(u.index_file)[["date", "close"]].dropna()
                 .set_index("date")["close"].sort_index())
            index_files[tag] = (u.index_name, u.index_file, s)

    # Price data end: the last date in the score panels the engine reads (static and
    # pit), not the index files, which some universes carry further.
    from universes.registry import pit_variant, has_pit
    import survivorship_axis as _sva
    panel_dates = set()
    for tag, u in REGISTRY.items():
        # A static-only universe has no pit panel (registry.has_pit).
        for v in ((u, pit_variant(u)) if has_pit(u) else (u,)):
            f = Path(v.score_cache)
            if f.exists():
                panel_dates |= set(pd.read_parquet(f, columns=["date"])["date"].unique())
    _sva.set_selection(None)
    for tag, u in REGISTRY.items():
        RAW_DIRS[(tag, "static")] = u.raw_data_dir
        if has_pit(u):
            RAW_DIRS[(tag, "pit")] = pit_variant(u).raw_data_dir
    _sva.set_selection(None)
    panel_dates = sorted(pd.Timestamp(d) for d in panel_dates)
    data_end = panel_dates[-1] if panel_dates else None
    bt0, bt1 = config.BT_START_DATE, config.BT_END_DATE
    cut = [d for d in panel_dates if d > bt1]
    window = {
        "start": bt0.strftime("%Y-%m-%d"), "end": bt1.strftime("%Y-%m-%d"),
        "reason": (f"Every run ends on config.BT_END_DATE, {bt1.date()}, the one backtest "
                   f"window end that every live site imports; config.py notes that "
                   f"price data runs further and that the cut leaves out the last {len(cut)} trading days"
                   + (f" ({cut[0].date()} to {cut[-1].date()})" if cut else "")
                   + ", and gives no reason for choosing that date."),
    }

    gated, ungated = nt_verify_cells(repo)

    published, superseded = published_list(repo)
    runs, ad_hoc, folders = [], [], sorted(p for p in (repo / "runs").iterdir()
                                           if p.is_dir() and re.match(r"^\d{8}T\d{6}_", p.name))
    skipped_unfinished, skipped_superseded, superseded_dirs = [], [], []
    for name in sorted((published | superseded) - {p.name for p in folders}):
        checks.append(f"Published list FAIL: {name} is in {PUBLISHED_LIST.name} but there is "
                      f"no such run folder.")
    for folder in folders:
        rt = folder / "RUN.txt"
        if not rt.exists() or "finished" not in read_run_txt(rt):
            skipped_unfinished.append(folder.name)
            if folder.name in published:
                checks.append(f"Published list FAIL: {folder.name} has no finished line.")
            continue
        if folder.name in superseded:
            skipped_superseded.append(folder.name)
            superseded_dirs.append((folder, read_run_txt(rt)))
            continue
        run_txt = read_run_txt(rt)
        sel = folder.name.split("_", 1)[1]
        uni_sel = "all" if sel.startswith("all_") else ",".join(
            x.strip() for x in run_txt["universes"].split(","))
        arm_sel = "all" if sel.split("_")[1] == "all" else ",".join(
            x.strip() for x in run_txt["arms"].split(","))
        for udir in sorted(p.name for p in (folder / "runs").iterdir() if p.is_dir()):
            for sdir in sorted((folder / "runs" / udir).iterdir()):
                if not ((sdir / "params.json").exists() and (sdir / "comparison.csv").exists()):
                    continue
                r = build_run(repo, folder, udir, sdir.name, run_txt, index_files, checks)
                r["command"] = "./venv/bin/python run.py " + flags_for(r["axes"], uni_sel, arm_sel)
                ax = r["axes"]
                default_cell = (ax["survivorship"] == "static" and ax["profile"] == "research"
                                and ax["tax"] == "off" and ax["cadence"] == "20"
                                and ax["dd"] == "off" and ax["capital"] == "1000000"
                                and ax["impact"] == "0" and ax["fixed"] == "off"
                                and ax["start"] == "2019-01-01")
                cell = (ax["universe"], ax["arm"])
                r["nt_verify"] = ("pass" if default_cell and cell in gated else
                                  "fail" if default_cell and cell in ungated else "not covered")
                (runs if folder.name in published else ad_hoc).append(r)
    if skipped_unfinished:
        checks.append(f"Skipped {len(skipped_unfinished)} run folders with no finished line: "
                      + ", ".join(skipped_unfinished))
    checks.append(f"Published list: {len(published)} run folders in {PUBLISHED_LIST.name} hold "
                  f"the published figures; {len(skipped_superseded)} folders it names as "
                  f"superseded (earlier runs of published combinations) are not shown; "
                  f"{len(ad_hoc)} runs from {len({r['id'].split('/')[0] for r in ad_hoc})} other "
                  f"folders are shown apart as ad hoc and feed neither check f nor the ladder.")

    # One run per combination among the published folders. Two listed folders that
    # hold the same combination are a fault in the list: the newer is kept.
    by_key, dropped = {}, []
    for r in sorted(runs, key=lambda r: r["_folder_ts"]):
        k = key_of(r["axes"])
        if k in by_key:
            dropped.append((by_key[k]["id"], r["id"]))
        by_key[k] = r
    for old, new in dropped:
        checks.append(f"Published list FAIL: two listed folders hold one combination: "
                      f"dropped {old}, kept the newer {new}.")
    runs = sorted(by_key.values(), key=lambda r: key_of(r["axes"]))
    ad_hoc.sort(key=lambda r: (r["_folder_ts"], key_of(r["axes"])))
    ad_hoc_keys = {key_of(r["axes"]) for r in ad_hoc}

    # STALENESS OF THE PUBLISHED LIST, READ ONLY. For every published combination, any
    # run of it in a newer folder (ad hoc or listed as superseded) whose headline
    # figures differ means PUBLISHED_RUNS.txt no longer names the latest result. Only
    # reported; nothing is replaced. A superseded folder's runs are read only when it
    # is newer than the published folder of the same combination.
    later = list(ad_hoc)
    for folder, run_txt in superseded_dirs:
        ts = folder.name.split("_", 1)[0]
        for udir in sorted(p.name for p in (folder / "runs").iterdir() if p.is_dir()):
            for sdir in sorted((folder / "runs" / udir).iterdir()):
                if not ((sdir / "params.json").exists() and (sdir / "comparison.csv").exists()):
                    continue
                pub = by_key.get(key_of(run_axes(json.loads((sdir / "params.json").read_text()),
                                                 run_txt, sdir.name)))
                if pub is not None and ts > pub["_folder_ts"]:
                    later.append(build_run(repo, folder, udir, sdir.name, run_txt, index_files, checks))
    stale = []
    for r in sorted(later, key=lambda r: (key_of(r["axes"]), r["_folder_ts"])):
        pub = by_key.get(key_of(r["axes"]))
        if pub is None or r["_folder_ts"] <= pub["_folder_ts"]:
            continue
        diffs = [f"{name} {f(pub)} vs {f(r)}" for name, f in HEADLINE if f(pub) != f(r)]
        if diffs:
            combo = pub["id"].split("/", 1)[1]
            stale.append(f"{PUBLISHED_LIST.name} needs updating: {combo} is published from "
                         f"{pub['id'].split('/')[0]}, and the newer {r['id'].split('/')[0]} "
                         f"differs ({'; '.join(diffs)}).")
    _cw = [r for r in runs if r["capacity"] and r["capacity"]["warning"]]
    _nm = sum(r["capacity"]["not_measurable_fills"] for r in runs if r["capacity"])
    _nb = sum(r["capacity"]["buy_fills"] for r in runs if r["capacity"])
    checks.append(f"Capacity (capacity.py, NSE rows only): {sum(1 for r in runs if r['capacity'])} of "
                  f"{len(runs)} published runs measured; {_nm:,} of {_nb:,} buy fills not measurable "
                  f"({_nm / _nb * 100 if _nb else 0:.1f}%, no NSE row in their 20 sessions); "
                  f"{len(_cw)} pass a threshold"
                  + (": " + "; ".join(r["id"] for r in _cw) if _cw else "") + ".")
    checks.append(f"Published list staleness: {len(stale)} published combinations have a newer "
                  f"run with different headline figures (CAGR, max drawdown, final value, "
                  f"basket CAGR, tax); {len(later)} newer or unlisted runs compared."
                  + "".join(" STALE: " + s for s in stale))

    # THE FIXED-CAPITAL TWIN: the run with every axis the same and fixed capital
    # flipped. The Return methods view shows a run's fixed-capital figures only when
    # its twin exists.
    n_twin = 0
    for r in runs:
        tw = by_key.get(key_of({**r["axes"], "fixed": "off" if r["axes"]["fixed"] == "on" else "on"}))
        if tw is not None:
            r["fixed_twin"] = tw["id"]
            n_twin += 1
    checks.append(f"Fixed capital: {sum(1 for r in runs if r['axes']['fixed'] == 'on')} runs "
                  f"with --fixed-capital; {n_twin} runs have a twin with fixed capital flipped "
                  f"and every other setting the same.")

    # Arm directories outside any run folder (runs/<universe>/<seg>/) with a
    # combination no run folder holds: not exported, listed here.
    orphan = []
    for p in sorted((repo / "runs").glob("*/*/params.json")):
        if re.match(r"^\d{8}T", p.parts[-3]):
            continue
        prm = json.loads(p.read_text())
        ax = run_axes(prm, {}, p.parent.name)
        if key_of(ax) not in by_key and key_of(ax) not in ad_hoc_keys:
            orphan.append(f"runs/{p.parts[-3]}/{p.parent.name} (written {prm.get('run_date')})")
    if orphan:
        checks.append(f"Not exported: {len(orphan)} arm directories under runs/<universe>/ have "
                      f"params and a summary but belong to no finished run folder (their run "
                      f"folders are gone): " + "; ".join(orphan) + ".")

    # Axes block.
    def seen(name):
        return [v for v in dict.fromkeys(r["axes"][name] for r in runs)]
    uni_vals = list(REGISTRY)
    # The core arms only. The stop arms (v5, v6) have no finished run folder.
    arm_vals = list(ARMS)

    def num_sorted(vals):
        def k(v):
            try:
                return (0, float(v))
            except ValueError:
                return (-1, 0.0)
        return sorted(vals, key=k)
    axes = [
        {"name": "universe", "label": LABELS["universe"], "default": "all",
         "values": uni_vals, "open_number": False,
         "cli": {v: f"--universe {v}" for v in uni_vals}},
    ]
    for name in naming.AXES:
        if name == "arm":
            axes.append({"name": "arm", "label": LABELS["arm"], "default": "all",
                         "values": arm_vals, "open_number": False,
                         "cli": {v: f"--arm {v}" for v in arm_vals}})
        elif name == "profile":
            axes.append({"name": name, "label": LABELS[name], "default": "research",
                         "values": ["research", "tradeable"], "open_number": False,
                         "cli": {"research": "", "tradeable": "--profile tradeable"}})
        elif name == "tax":
            axes.append({"name": name, "label": LABELS[name], "default": "off",
                         "values": ["on", "off"], "open_number": False,
                         "cli": {"on": "--tax on", "off": ""}})
        elif name == "survivorship":
            axes.append({"name": name, "label": LABELS[name], "default": "static",
                         "values": ["static", "pit"], "open_number": False,
                         "cli": {"static": "", "pit": "--survivorship pit"}})
        elif name == "fixed":
            axes.append({"name": name, "label": LABELS[name], "default": "off",
                         "values": ["off", "on"], "open_number": False,
                         "cli": {"off": "", "on": "--fixed-capital"}})
        elif name == "buy_shortfall":
            axes.append({"name": name, "label": LABELS[name], "default": "trim",
                         "values": ["trim", "refuse"], "open_number": False,
                         "cli": {"trim": "", "refuse": "--buy-shortfall refuse"}})
        else:
            flag = {"cadence": "--rebal", "dd": "--dd", "capital": "--capital",
                    "impact": "--impact", "pcap": "--cap", "start": "--start"}[name]
            default = {"cadence": "20", "dd": "off", "capital": "1000000", "impact": "0",
                       "pcap": "1", "start": "2019-01-01"}[name]
            axes.append({"name": name, "label": LABELS[name], "default": default,
                         "values": num_sorted(seen(name)), "open_number": True,
                         "cli": f"{flag} {{value}}",
                         "no_flag": sorted(NO_FLAG[name]),
                         # The flag is given even at a no_flag value when this axis is
                         # off its default: run.py needs --impact with --capital.
                         **({"required_with": "capital"} if name == "impact" else {})})
    checks.append("Open number axes carry a no_flag list: values that take no flag. "
                  "pcap is \"none\" under the research profile (no cap) and \"1\" is "
                  "tradeable's own cap; neither takes --cap.")

    # Strip helper fields.
    for r in runs + ad_hoc:
        r.pop("_folder_ts", None)

    # ---------------- checks a to f ----------------
    # Checks a to e run on the published runs and, apart, on the ad hoc runs.
    for group, rows in (("published", runs), ("ad hoc", ad_hoc)):
        if not rows:
            continue
        fails = {"a": [], "b": [], "c": [], "d": [], "e": []}
        for r in rows:
            if None in (r["start_equity"], r["end_equity"], r["cagr"]):
                fails["a"].append(f"{r['id']}: missing figure")
            else:
                c = ((r["end_equity"] / r["start_equity"]) ** (1 / r["years"]) - 1) * 100
                if abs(c - r["cagr"]) > 0.01:
                    fails["a"].append(f"{r['id']}: recomputed {c:.4f} vs {r['cagr']}")
            lo = min(r["equity"]["drawdown"])
            if r["max_dd"] is None or abs(lo - r["max_dd"]) > 0.01:
                fails["b"].append(f"{r['id']}: weekly lowest {lo:.4f} vs max_dd {r['max_dd']}")
            prod = 1.0
            for y in r["yearly"]:
                prod *= 1 + y["strategy"] / 100
            ratio = r["end_equity"] / r["start_equity"]
            if abs(prod / ratio - 1) > 0.001:
                fails["c"].append(f"{r['id']}: product {prod:.6f} vs {ratio:.6f}")
            if abs(r["equity"]["strategy"][-1] - r["end_equity"]) > 1:
                fails["d"].append(f"{r['id']}: last weekly {r['equity']['strategy'][-1]:.2f} "
                                  f"vs end_equity {r['end_equity']:.2f}")
            built = cli_command(axes, r["axes"])
            own = r["command"].split("run.py ", 1)[1]
            b_tok, o_tok = flag_pairs(built), flag_pairs(own)
            o_uni, o_arm = o_tok.pop("--universe"), o_tok.pop("--arm")
            b_tok.pop("--universe"), b_tok.pop("--arm")
            uni_ok = o_uni == "all" or r["axes"]["universe"] in o_uni.split(",")
            arm_ok = (o_arm == "all" and r["axes"]["arm"] in ("v1", "v2", "v3", "v4")) or \
                r["axes"]["arm"] in o_arm.split(",")
            if b_tok != o_tok or not uni_ok or not arm_ok:
                fails["e"].append(f"{r['id']}: built '{built}' vs own '{own}'")
        names = {
            "a": "CAGR recomputed from start_equity, end_equity and years matches cagr within 0.01",
            "b": "the lowest weekly drawdown equals max_dd within 0.01",
            "c": "the yearly strategy returns multiplied together equal end_equity / start_equity within 0.1%",
            "d": "the last weekly strategy value equals end_equity within Rs 1",
            "e": ("the command built from the axes' cli rules matches the run's own command "
                  "(the same flags and values apart from --universe and --arm, in any order; the "
                  "run's universe and arm inside the command's --universe and --arm selection)"),
        }
        for k in "abcde":
            if fails[k]:
                checks.append(f"Check {k} FAIL on {len(fails[k])} of {len(rows)} {group} runs: {names[k]}. "
                              + " | ".join(fails[k]))
            else:
                checks.append(f"Check {k} pass on all {len(rows)} {group} runs: {names[k]}.")

        # Checks a to d on the basket and the index. The index has no drawdown curve in
        # the export and the repository writes no index max_dd, so b is not run for it.
        for line, curve, dd_key in (("basket", "basket", "basket_drawdown"), ("index", "index", None)):
            f = {"a": [], "b": [], "c": [], "d": []}
            n = 0
            for r in rows:
                blk, ser = r[line], r["equity"][curve]
                if blk is None or ser is None:
                    continue
                n += 1
                st, en = blk["start_equity"], blk["end_equity"]
                c = ((en / st) ** (1 / r["years"]) - 1) * 100
                if abs(c - blk["cagr"]) > 0.01:
                    f["a"].append(f"{r['id']}: recomputed {c:.4f} vs {blk['cagr']}")
                if dd_key:
                    lo = min(r["equity"][dd_key])
                    if abs(lo - blk["max_dd"]) > 0.01:
                        f["b"].append(f"{r['id']}: weekly lowest {lo:.4f} vs max_dd {blk['max_dd']}")
                prod = 1.0
                for y in r["yearly"]:
                    prod *= 1 + y[line] / 100
                if abs(prod / (en / st) - 1) > 0.001:
                    f["c"].append(f"{r['id']}: product {prod:.6f} vs {en / st:.6f}")
                if abs(ser[-1] - en) > 1:
                    f["d"].append(f"{r['id']}: last weekly {ser[-1]:.2f} vs end_equity {en:.2f}")
            for k in "abcd":
                if k == "b" and not dd_key:
                    checks.append(f"Check {k} ({line}) not run: the export has no {line} drawdown "
                                  f"curve and the repository writes no {line} max_dd.")
                elif f[k]:
                    checks.append(f"Check {k} ({line}) FAIL on {len(f[k])} of {n} {group} runs. "
                                  + " | ".join(f[k]))
                else:
                    checks.append(f"Check {k} ({line}) pass on all {n} {group} runs with {"an" if line == "index" else "a"} {line}.")

    # rounded_to: the column names recorded per run become the decimals seen.
    for r in runs + ad_hoc:
        r["rounded_to"] = {k: ROUNDED[col] for k, col in r["rounded_to"].items()}
    checks.append("rounded_to gives, per run, the decimals of the figures read from "
                  "comparison.csv: " + ", ".join(f"{c} {d}" for c, d in sorted(ROUNDED.items()))
                  + " (the most decimals any comparison.csv carries in that column). "
                  "basket.end_equity and the curves are full precision.")

    pub = published_check_f(repo)
    for u, arm in CHECK_F_CELLS:
        ax = {"universe": u, "arm": arm, "cadence": "20", "profile": "tradeable", "tax": "on",
              "survivorship": "pit", "dd": "off", "capital": "1000000", "impact": "0",
              "pcap": "1", "fixed": "off", "start": "2019-01-01",
              "buy_shortfall": "refuse"}
        r = by_key.get(key_of(ax))
        p = pub.get((u, arm), {})
        if r is None:
            checks.append(f"Check f FAIL: no run for {u} {arm} (pit, tradeable, tax on, "
                          f"cadence 20, Rs 10 lakh).")
            continue
        got = {"cagr": r["cagr"], "basket_cagr": r["basket"]["cagr"], "max_dd": r["max_dd"]}
        bad = [f"{k} {got[k]} vs published {p.get(k)}" for k in got
               if p.get(k) is None or abs(got[k] - p[k]) > 0.005]
        checks.append(f"Check f {'FAIL' if bad else 'pass'}: {u} {arm} (pit, tradeable, tax on, "
                      f"cadence 20, Rs 10 lakh): cagr {got['cagr']}, basket cagr "
                      f"{got['basket_cagr']}, max_dd {got['max_dd']}; published (README "
                      f"\"pit, tradeable profile\" table for cagr and max_dd, "
                      f"results_{u}/metrics/v34_comparison_tradeable_tax_pit.csv for the "
                      f"basket) {p.get('cagr')}, {p.get('basket_cagr')}, {p.get('max_dd')}"
                      + (". " + "; ".join(bad) if bad else "."))

    checks.append("nt_verify: \"pass\" for the cells check_all.py gates with nt_verify "
                  f"({len(gated)} cells) and \"fail\" for its NT_VERIFY_UNGATED cells "
                  f"({', '.join(f'{u} {a}' for u, a in sorted(ungated))}); the gate runs only the "
                  "static, research, tax off, cadence 20, Rs 10 lakh cell with no drawdown limit "
                  "or impact. Every other run is \"not covered\". The pass status is the gate's "
                  "last clearing check_all run, not a fresh nt_verify run.")
    checks.append("Yearly tax_paid is FY_TAX_STATEMENT total_tax summed by the calendar year of "
                  "its assessed_on date (the day the tax left cash). It is 0 for tax-off runs.")
    checks.append("index is the universe's own NSE price index file, forward-filled onto the "
                  "run's dates and scaled to the run's start equity (results/make_chart.py); "
                  "its CAGR uses the repository's CAGR formula, its max_dd the running-peak "
                  "drawdown.")

    lad = ladder(repo, by_key, checks)
    ki = known_issues(repo)

    by_profile = {}
    for r in runs:
        by_profile[r["axes"]["profile"]] = by_profile.get(r["axes"]["profile"], 0) + 1

    out = {
        "schema": "pe-dashboard/1",
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "repo": repo_info,
        "data_end": data_end.strftime("%Y-%m-%d") if data_end is not None else None,
        "window": window,
        "command_template": "./venv/bin/python run.py {args}",
        "axes": axes,
        "runs": runs,
        "ad_hoc": ad_hoc,
        "ladder": lad,
        "known_issues": ki,
        "bias_notes": {t: u.bias_note for t, u in REGISTRY.items() if u.bias_note},
        "export_checks": checks,
    }
    # naming: axis-free -- one file covers every run; it varies over no axis
    Path(a.out).write_text(json.dumps(out, allow_nan=False))
    after = git(repo, "status", "--porcelain")
    print(f"runs: {len(runs)} ({', '.join(f'{k} {v}' for k, v in sorted(by_profile.items()))}); "
          f"ad hoc: {len(ad_hoc)}")
    print(f"wrote {a.out}: {Path(a.out).stat().st_size:,} bytes")
    print(f"repository clean before: {porcelain == ''}, after: {after == ''}")
    for c in checks:
        print(" -", c[:400] + (" ..." if len(c) > 400 else ""))
    # run.py's refresh passes these lines on to the run's output.
    for s in stale:
        print(f"WARNING: {s}")


if __name__ == "__main__":
    main()
