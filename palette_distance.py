"""
palette_distance.py -- how far apart are the chart lines, to an eye that sees
                       colour normally and to one that does not.
=============================================================================

WHAT IT MEASURES
    CIEDE2000 between every pair of lines make_combined_universes._series()
    actually draws -- per universe, its selected arms plus its own buy&hold
    (chart_colours[2]) and its own cap-weighted index (chart_colours[3]) --
    under normal colour vision and under the Vienot 1999 dichromat simulations
    for deuteranopia and protanopia.

    Twelve lines on the canonical chart (v2 + v1 per universe), eighteen under
    --arm all. The just-noticeable difference is about 2.3.

WHY THIS IS A TOOL AND NOT A GATE, WHICH WAS A DECISION AND NOT AN OVERSIGHT
    A gate was considered on 2026-09-18, costed, and declined. Adding it to
    registry_coverage_check.py is computationally free -- 48 colours, 1,128
    pairs, no new dependency, and that checker already imports the registry
    directly. Two things stopped it.

    THE THRESHOLD IS REVERSE-ENGINEERED, NOT A STANDARD. dE 10 is what nifty50's
    replacement palette was searched against, and it was chosen because it was
    the highest round number achievable against midcap150's and nifty100's
    tuples WITHOUT MOVING THEM. A gate would write that number down and defend it as though it
    came from somewhere. It came from the palettes it would be judging.

    AND IT WOULD SHIP PRE-FAILED. Three pairs in the current palettes are below
    it -- midcap150/v2 vs midcap150/v1 at 4.24 and nifty100/v1 vs nifty100/v3 at 3.26
    under deuteranopia, midcap150/v4 vs nifty100/bh at 10.75 under protanopia --
    so the gate could only be green on the day it landed with an exception list
    naming all three. A gate whose first commit is its own exception list is a report with
    a non-zero exit code, and this repository already knows what an exception
    list becomes: somewhere to put the thing you did not want to fix.

    So this reports and EXITS 0, ALWAYS. It is run by hand when a universe is
    wired, which is the moment its palette is chosen and the only moment the
    answer can change. See PANEL_MIGRATION.md and KNOWN_ISSUES.md.

USAGE
    ./venv/bin/python palette_distance.py            # report to stdout
    ./venv/bin/python palette_distance.py --write    # also write the diagnostic

NO DEPENDENCY. sRGB->Lab (D65), the Vienot matrices and CIEDE2000 are written
out below. Adding a colour library for 90 lines of arithmetic would be a
dependency in requirements.txt for something nothing else needs.
"""
import itertools
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from universes.registry import REGISTRY   # noqa: E402

JND = 2.3          # just-noticeable difference, for reference in the report
REVIEW = 10.0      # the judgement of 2026-09-18; see the docstring


def _s2l(c): return c/12.92 if c <= 0.04045 else ((c+0.055)/1.055)**2.4
def _l2s(c):
    c = min(max(c, 0.0), 1.0)
    return 12.92*c if c <= 0.0031308 else 1.055*c**(1/2.4) - 0.055

def hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3: h = "".join(x*2 for x in h)
    return tuple(int(h[i:i+2], 16)/255 for i in (0, 2, 4))

def rgb_to_hex(rgb):
    return "#" + "".join(f"{round(min(max(c,0),1)*255):02x}" for c in rgb)

_M = ((0.4124564,0.3575761,0.1804375),(0.2126729,0.7151522,0.0721750),
      (0.0193339,0.1191920,0.9503041))
_MI = ((3.2404542,-1.5371385,-0.4985314),(-0.9692660,1.8760108,0.0415560),
       (0.0556434,-0.2040259,1.0572252))
_WP = (0.95047, 1.0, 1.08883)

def rgb_to_lab(rgb):
    r,g,b = (_s2l(c) for c in rgb)
    xyz = [sum(_M[i][j]*v for j,v in enumerate((r,g,b))) for i in range(3)]
    def f(t): return t**(1/3) if t > 216/24389 else (841/108)*t + 4/29
    fx,fy,fz = (f(xyz[i]/_WP[i]) for i in range(3))
    return (116*fy-16, 500*(fx-fy), 200*(fy-fz))

def lab_to_rgb(lab):
    L,a,b = lab
    fy = (L+16)/116; fx = fy + a/500; fz = fy - b/200
    def fi(t): return t**3 if t**3 > 216/24389 else (108/841)*(t - 4/29)
    xyz = [fi(fx)*_WP[0], fi(fy)*_WP[1], fi(fz)*_WP[2]]
    lin = [sum(_MI[i][j]*xyz[j] for j in range(3)) for i in range(3)]
    if any(c < -1e-4 or c > 1+1e-4 for c in lin):
        return None                      # out of sRGB gamut
    return tuple(_l2s(c) for c in lin)

def simulate(rgb, kind):
    if kind == "normal": return rgb
    r,g,b = (_s2l(c) for c in rgb)
    L = 17.8824*r + 43.5161*g + 4.11935*b
    M = 3.45565*r + 27.1554*g + 3.86714*b
    S = 0.0299566*r + 0.184309*g + 1.46709*b
    if kind == "protan":   L,M,S = 2.02344*M - 2.52581*S, M, S
    elif kind == "deutan": L,M,S = L, 0.494207*L + 1.24827*S, S
    r2 = 0.080944*L - 0.130504*M + 0.116721*S
    g2 = -0.0102485*L + 0.0540194*M - 0.113615*S
    b2 = -0.000365294*L - 0.00412163*M + 0.693513*S
    return tuple(_l2s(c) for c in (r2, g2, b2))

def ciede2000(lab1, lab2):
    L1,a1,b1 = lab1; L2,a2,b2 = lab2
    C1,C2 = math.hypot(a1,b1), math.hypot(a2,b2); Cb = (C1+C2)/2
    G = 0.5*(1 - math.sqrt(Cb**7/(Cb**7+25**7))) if Cb > 0 else 0.5
    a1p,a2p = (1+G)*a1, (1+G)*a2
    C1p,C2p = math.hypot(a1p,b1), math.hypot(a2p,b2)
    h1p = math.degrees(math.atan2(b1,a1p)) % 360 if (a1p or b1) else 0
    h2p = math.degrees(math.atan2(b2,a2p)) % 360 if (a2p or b2) else 0
    dLp = L2-L1; dCp = C2p-C1p
    if C1p*C2p == 0: dhp = 0
    elif abs(h2p-h1p) <= 180: dhp = h2p-h1p
    elif h2p-h1p > 180: dhp = h2p-h1p-360
    else: dhp = h2p-h1p+360
    dHp = 2*math.sqrt(C1p*C2p)*math.sin(math.radians(dhp)/2)
    Lbp = (L1+L2)/2; Cbp = (C1p+C2p)/2
    if C1p*C2p == 0: hbp = h1p+h2p
    elif abs(h1p-h2p) <= 180: hbp = (h1p+h2p)/2
    elif h1p+h2p < 360: hbp = (h1p+h2p+360)/2
    else: hbp = (h1p+h2p-360)/2
    T = (1 - 0.17*math.cos(math.radians(hbp-30)) + 0.24*math.cos(math.radians(2*hbp))
         + 0.32*math.cos(math.radians(3*hbp+6)) - 0.20*math.cos(math.radians(4*hbp-63)))
    dth = 30*math.exp(-(((hbp-275)/25)**2))
    Rc = 2*math.sqrt(Cbp**7/(Cbp**7+25**7)) if Cbp > 0 else 0
    Sl = 1 + (0.015*(Lbp-50)**2)/math.sqrt(20+(Lbp-50)**2)
    Sc = 1 + 0.045*Cbp; Sh = 1 + 0.015*Cbp*T
    Rt = -math.sin(math.radians(2*dth))*Rc
    return math.sqrt((dLp/Sl)**2 + (dCp/Sc)**2 + (dHp/Sh)**2
                     + Rt*(dCp/Sc)*(dHp/Sh))


VISIONS = ("normal", "deutan", "protan")
ARMSLOT = {"v2": 0, "v1": 1, "v3": 4, "v4": 5}


def labs_of(hexcolour):
    rgb = hex_to_rgb(hexcolour)
    return {v: rgb_to_lab(simulate(rgb, v)) for v in VISIONS}


def lines(arms, tags=None):
    """Exactly what make_combined_universes._series() draws, in its order."""
    out = []
    for t in (tags or list(REGISTRY)):
        u = REGISTRY[t]
        for a in arms:
            out.append((f"{t}/{a}", u.chart_colours[ARMSLOT[a]]))
        out.append((f"{t}/bh", u.chart_colours[2]))
        out.append((f"{t}/ix", u.chart_colours[3]))
    return out


def report(tags=None):
    out = []
    w = out.append
    for title, arms in (("CANONICAL COMBINED CHART (v2 + v1 per universe)", ("v2", "v1")),
                        ("--arm all (v2, v1, v3, v4 per universe)",
                         ("v2", "v1", "v3", "v4"))):
        L = lines(arms, tags)
        labs = {n: labs_of(c) for n, c in L}
        names = [n for n, _ in L]
        w("=" * 78)
        w(f" {title} -- {len(names)} lines")
        w("=" * 78)
        for n, c in L:
            w(f"    {n:14s} {c}")
        for vision in VISIONS:
            pairs = sorted((ciede2000(labs[a][vision], labs[b][vision]), a, b)
                           for a, b in itertools.combinations(names, 2))
            w("")
            w(f"  --- {vision}: closest 8 pairs")
            for d, a, b in pairs[:8]:
                mark = ("  <-- BELOW THE JND" if d < JND
                        else f"  <-- below {REVIEW:.0f}" if d < REVIEW else "")
                w(f"      dE={d:6.2f}   {a:14s} vs {b:14s}{mark}")
            below = [p for p in pairs if p[0] < REVIEW]
            w(f"      minimum {pairs[0][0]:.2f}; {len(below)} pair(s) below "
              f"{REVIEW:.0f}, {sum(1 for p in pairs if p[0] < JND)} below the JND")
        w("")
    return "\n".join(out)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    text = report()
    print(text)
    if "--write" in argv:
        # naming: axis-free -- a palette is a property of the registry rows, not
        # of any arm, cadence, profile or tax selection; the report is the same
        # file whatever the run selected.
        (ROOT / "diagnostics" / "palette_distance.txt").write_text(text + "\n")
        print("\nwritten -> diagnostics/palette_distance.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
