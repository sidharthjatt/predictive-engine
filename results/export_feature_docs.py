"""
export_feature_docs.py -- exports the feature documentation for review.
Descriptions are extracted from the actual features_v2.py source, not guessed.
Outputs (results/metrics/):
  feature_dictionary.csv -> naam, family, asli code line, comment
  panel_sample.csv       -> the first 500 rows of the panel (the model's input)
  panel_summary.csv      -> per-column statistics
"""
import sys, re, warnings
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from engine_core import build_panel, HORIZON
from features_v2 import FEATS_V2

SRC = Path(__file__).resolve().parent / "features_v2.py"
lines = SRC.read_text().splitlines()

def family_at(idx):
    for j in range(idx, -1, -1):
        m = re.search(r"#\s*-+\s*[A-Z]\.\s*(.+?)\s*-+\s*$", lines[j])
        if m:
            return m.group(1).strip()
    return ""

rows = []
for feat in FEATS_V2:
    formula, comment, fam = "", "", ""
    for i, ln in enumerate(lines):
        if 'df["' + feat + '"]' in ln and "=" in ln:
            code = ln.strip()
            if "#" in code:
                code, comment = code.split("#", 1)
                comment = comment.strip()
            k = i
            while code.count("(") > code.count(")") and k + 1 < len(lines):
                k += 1
                code += " " + lines[k].strip()
            if not comment and i > 0 and lines[i-1].strip().startswith("#"):
                comment = lines[i-1].strip().lstrip("#").strip()
            formula = re.sub(r"\s+", " ", code.strip())
            fam = family_at(i)
            break
    if not formula:
        # not built as df["name"] = ... (e.g. cross-sectional regression block)
        for i, ln in enumerate(lines):
            if feat in ln and not ln.strip().startswith("#") and "FEATS_V2" not in ln:
                formula = re.sub(r"\s+", " ", ln.strip())
                fam = family_at(i) or "CROSS-SECTIONAL (market model)"
                for j in range(i - 1, max(i - 4, -1), -1):
                    if lines[j].strip().startswith("#"):
                        comment = lines[j].strip().lstrip("#").strip()
                        break
                break
    rows.append({"feature": feat, "family": fam,
                 "code_in_features_v2": formula, "note": comment})

fd = pd.DataFrame(rows)
out = config.METRICS_DIR
fd.to_csv(out / "feature_dictionary.csv", index=False)
print("feature_dictionary.csv  (%d features)" % len(fd))
print(fd[["feature", "family"]].to_string(index=False))

p = build_panel(HORIZON)
p.head(500).to_csv(out / "panel_sample.csv", index=False)
print("\npanel_sample.csv  (500 of %s rows, %d cols)" % (format(len(p), ","), len(p.columns)))

def num(c, fn):
    return round(fn(p[c]), 4) if np.issubdtype(p[c].dtype, np.number) else ""

summ = pd.DataFrame({
    "column": p.columns,
    "dtype":  [str(p[c].dtype) for c in p.columns],
    "NaN_%":  [round(p[c].isna().mean() * 100, 2) for c in p.columns],
    "mean":   [num(c, lambda s: s.mean()) for c in p.columns],
    "std":    [num(c, lambda s: s.std())  for c in p.columns],
    "min":    [num(c, lambda s: s.min())  for c in p.columns],
    "max":    [num(c, lambda s: s.max())  for c in p.columns],
})
summ.to_csv(out / "panel_summary.csv", index=False)
print("panel_summary.csv")
print(summ.to_string(index=False))
print("\nAll saved -> %s" % out)
print("NOTE: features are cross-sectionally z-scored (mean~0, std~1, clipped +/-3).")
