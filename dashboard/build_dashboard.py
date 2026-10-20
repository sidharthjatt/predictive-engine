"""
build_dashboard.py -- check dashboard_data.json and write dashboard.html with it embedded.

    python3 dashboard/build_dashboard.py      (from the repository root)

Reads dashboard/dashboard_data.json and dashboard/dashboard_template.html, writes
dashboard/dashboard.html. Both generated files are excluded by .gitignore.

Stops with a list of problems if the JSON does not match the pe-dashboard/1 format.
The page is one file: inline CSS and JavaScript, no network access of any kind.
Every number on it comes from the embedded JSON or from a file opened in the page.
The page runs the same format check on a file opened with "Open another file".
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TOP = ("schema", "generated_at", "repo", "data_end", "command_template", "axes", "runs",
       "ladder", "known_issues", "export_checks")
RUN_FIELDS = ("id", "path", "axes", "command", "start_date", "end_date", "years",
              "start_equity", "end_equity", "cagr", "max_dd", "max_dd_peak", "max_dd_trough",
              "basket", "index", "trades", "rebalances", "costs", "charges_breakdown",
              "yearly", "equity", "nt_verify", "rounded_to")
LADDER_FIELDS = ("universe", "arm", "survivorship", "tax", "profile", "cadence", "capital",
                 "impact", "cap", "cagr", "basket_cagr", "max_dd", "impact_cost", "slippage",
                 "capped_fills", "tax_paid")
EQ_FIELDS = ("dates", "strategy", "basket", "index", "drawdown", "basket_drawdown")


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def num_or_null(x):
    return x is None or is_num(x)


def date_or_null(x):
    return x is None or (isinstance(x, str) and DATE.match(x) is not None)


def validate(d):
    """Every problem with the file, as plain sentences. Empty means it passes."""
    p = []
    if not isinstance(d, dict):
        return ["The file is not a JSON object."]
    for k in TOP:
        if k not in d:
            p.append(f"Top-level field \"{k}\" is missing.")
    if p:
        return p
    if d["schema"] != "pe-dashboard/1":
        p.append(f"schema is {d['schema']!r}, expected \"pe-dashboard/1\".")
    r = d["repo"]
    if not (isinstance(r, dict) and isinstance(r.get("head"), str)
            and isinstance(r.get("branch"), str) and isinstance(r.get("clean"), bool)):
        p.append("repo must hold head (string), branch (string) and clean (true or false).")
    if not date_or_null(d["data_end"]):
        p.append("data_end is not a YYYY-MM-DD date.")
    w = d.get("window")
    if "window" in d and not (isinstance(w, dict) and date_or_null(w.get("start"))
                              and date_or_null(w.get("end")) and isinstance(w.get("reason"), str)):
        p.append("window, when present, must hold start, end (dates) and reason (text).")
    if not (isinstance(d["command_template"], str) and "{args}" in d["command_template"]):
        p.append("command_template must be a string containing {args}.")
    names = []
    if not isinstance(d["axes"], list) or not d["axes"]:
        p.append("axes must be a non-empty list.")
    else:
        for i, a in enumerate(d["axes"]):
            w = f"axes[{i}]"
            if not isinstance(a, dict):
                p.append(f"{w} is not an object.")
                continue
            for k in ("name", "label", "default", "values", "open_number", "cli"):
                if k not in a:
                    p.append(f"{w} has no \"{k}\".")
            if not all(k in a for k in ("name", "values", "open_number", "cli")):
                continue
            names.append(a["name"])
            if not (isinstance(a["values"], list) and all(isinstance(v, str) for v in a["values"])):
                p.append(f"{w} ({a['name']}): values must be a list of strings.")
            if not isinstance(a.get("default"), str):
                p.append(f"{w} ({a['name']}): default must be a string.")
            if a["open_number"] is True:
                if not (isinstance(a["cli"], str) and "{value}" in a["cli"]):
                    p.append(f"{w} ({a['name']}): an open number axis needs cli as a string with {{value}}.")
            elif a["open_number"] is False:
                if not (isinstance(a["cli"], dict)
                        and all(isinstance(a["cli"].get(v), str) for v in a["values"])):
                    p.append(f"{w} ({a['name']}): cli must map every value to a flag string.")
            else:
                p.append(f"{w} ({a['name']}): open_number must be true or false.")
    # ad_hoc is optional: runs from folders not in dashboard/PUBLISHED_RUNS.txt, held
    # apart from runs and checked by the same rules. An id is unique across both.
    ids = set()
    for field in ("runs", "ad_hoc"):
        if field == "ad_hoc" and field not in d:
            continue
        if not isinstance(d[field], list):
            p.append(f"{field} must be a list.")
            continue
        for i, run in enumerate(d[field]):
            w = f"{field}[{i}]"
            if not isinstance(run, dict):
                p.append(f"{w} is not an object.")
                continue
            miss = [k for k in RUN_FIELDS if k not in run]
            if miss:
                p.append(f"{w} is missing {', '.join(miss)}.")
                continue
            w = f"run {run['id']}"
            if run["id"] in ids:
                p.append(f"{w}: id appears twice.")
            ids.add(run["id"])
            ax = run["axes"]
            if not isinstance(ax, dict) or any(not isinstance(ax.get(n), str) for n in names):
                p.append(f"{w}: axes must give every axis ({', '.join(names)}) a string value.")
            for k in ("start_date", "end_date", "max_dd_peak", "max_dd_trough"):
                if not date_or_null(run[k]):
                    p.append(f"{w}: {k} is not a YYYY-MM-DD date or null.")
            for k in ("years", "start_equity", "end_equity", "cagr", "max_dd", "trades", "rebalances"):
                if not num_or_null(run[k]):
                    p.append(f"{w}: {k} is not a number or null.")
            if not isinstance(run["command"], str):
                p.append(f"{w}: command is not a string.")
            for b in ("basket", "index"):
                v = run[b]
                if v is None and b == "index":
                    continue
                if not (isinstance(v, dict) and isinstance(v.get("name"), str)
                        and all(num_or_null(v.get(k)) for k in ("start_equity", "cagr", "max_dd", "end_equity"))):
                    p.append(f"{w}: {b} must hold name, start_equity, cagr, max_dd and end_equity.")
            c = run["costs"]
            if not (isinstance(c, dict) and all(k in c and num_or_null(c[k])
                                                for k in ("slippage", "charges", "impact", "tax"))):
                p.append(f"{w}: costs must hold slippage, charges, impact and tax.")
            cb = run["charges_breakdown"]
            if cb is not None and not (isinstance(cb, dict) and all(is_num(v) for v in cb.values())):
                p.append(f"{w}: charges_breakdown must map names to rupees.")
            if not isinstance(run["yearly"], list):
                p.append(f"{w}: yearly is not a list.")
            else:
                for y in run["yearly"]:
                    if not (isinstance(y, dict) and is_num(y.get("year"))
                            and isinstance(y.get("full_year"), bool)
                            and all(num_or_null(y.get(k)) for k in ("strategy", "basket", "index", "tax_paid"))):
                        p.append(f"{w}: a yearly entry is malformed.")
                        break
            e = run["equity"]
            if not (isinstance(e, dict) and all(k in e for k in EQ_FIELDS)):
                p.append(f"{w}: equity must hold {', '.join(EQ_FIELDS)}.")
            else:
                n = len(e["dates"]) if isinstance(e["dates"], list) else -1
                if n < 2 or not all(isinstance(x, str) and DATE.match(x) for x in e["dates"]):
                    p.append(f"{w}: equity.dates must be at least two YYYY-MM-DD dates.")
                for k in EQ_FIELDS[1:]:
                    v = e[k]
                    if v is None and k == "index":
                        continue
                    if not (isinstance(v, list) and len(v) == n and all(is_num(x) for x in v)):
                        p.append(f"{w}: equity.{k} must be {n} numbers.")
            rt = run["rounded_to"]
            if not (isinstance(rt, dict) and all(isinstance(v, int) and not isinstance(v, bool)
                                                 for v in rt.values())):
                p.append(f"{w}: rounded_to must map figure names to whole numbers of decimals.")
            if run["nt_verify"] not in ("pass", "fail", "not covered"):
                p.append(f"{w}: nt_verify must be pass, fail or not covered.")
            if len(p) > 200:
                p.append("More than 200 problems; stopped listing.")
                return p
    if not isinstance(d["ladder"], list):
        p.append("ladder must be a list.")
    else:
        for i, row in enumerate(d["ladder"]):
            miss = [k for k in LADDER_FIELDS if not isinstance(row, dict) or k not in row]
            if miss:
                p.append(f"ladder[{i}] is missing {', '.join(miss)}.")
                break
    if not (isinstance(d["known_issues"], list)
            and all(isinstance(k, dict) and isinstance(k.get("title"), str)
                    and isinstance(k.get("text"), str) for k in d["known_issues"])):
        p.append("known_issues must be a list of {title, text}.")
    if not (isinstance(d["export_checks"], list)
            and all(isinstance(x, str) for x in d["export_checks"])):
        p.append("export_checks must be a list of strings.")
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(HERE / "dashboard_data.json"))
    ap.add_argument("--out", default=str(HERE / "dashboard.html"))
    a = ap.parse_args()
    raw = Path(a.data).read_text()
    try:
        d = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.exit(f"STOPPED: {a.data} is not valid JSON ({e}).")
    problems = validate(d)
    if problems:
        sys.exit("STOPPED: dashboard_data.json does not match the pe-dashboard/1 format.\n"
                 + "\n".join(f"  - {x}" for x in problems))
    # Inside <script>, "</" must not appear, and U+2028/9 are escaped for safety.
    embedded = (json.dumps(d, separators=(",", ":"), allow_nan=False)
                .replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))
    tpl = (HERE / "dashboard_template.html").read_text()
    html = tpl.replace("/*__DATA__*/null", embedded, 1)
    # naming: axis-free -- one file covers every run; it varies over no axis
    Path(a.out).write_text(html)
    print(f"format check passed: {len(d['runs'])} runs, {len(d.get('ad_hoc', []))} ad hoc runs, "
          f"{len(d['ladder'])} ladder rows")
    print(f"wrote {a.out}: {Path(a.out).stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
