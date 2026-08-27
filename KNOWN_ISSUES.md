# Known issues

Defects that are recorded but not fixed. Anything found and left alone belongs
here, with what it is, where it lives, and what a reader would wrongly conclude
because of it. Nothing in this file is a plan; it is a list of things that are
currently wrong.

---

## The MidCap150 chart declares itself invalid, and is not

Found 2026-08-27. Open.

`results_mid/metrics/chart_mid_FINAL.png` renders with this as its first line:

> NOT A VALID RESULT -- PANEL DENSITY BLOCKER: only 148 of 148 names are scored,
> median 130 priced per day. idio_vol_60/beta_60 use rolling(60) on the UNION date
> index, so midcap non-trading days void 60 windows each; 32.9% of rows survive.
> Unpriced names forward-fill flat, so breadth reads 0.202 vs 0.550 on the 58 and
> deployment collapses to ~20%.

That text is built at `results/make_mid_chart.py:185-189`. The figures `32.9%`,
`0.202`, `0.550` and `~20%` are hardcoded string literals. They describe the panel
as it was before the `beta_60` / `idio_vol_60` density fix of 2026-08-13, which is
recorded in `nautilus/NAUTILUS_STATUS.md` and in `experiments/EXPERIMENTS.md`.

It contradicts its own chart. Two lines further down, at
`make_mid_chart.py:191`, the same subtitle prints `v2 holds {inv}% invested on
average`, and `inv` is read from the params file at run time. On the current
artefact that renders as 54%. So the image says deployment collapsed to about 20%
and then says it is 54%, in adjacent sentences.

What makes it worse: the surrounding text is live. `only 148 of 148 names are
scored` and `median 130 priced per day` are computed from the actual run. A reader
has no way to tell which half of the sentence is measured and which half is a
three-week-old literal, so the stale numbers borrow credibility from the live ones.

**Consequence.** Anyone who opens that PNG concludes the MidCap150 results are
void. The project treats them as valid — mid is one of the two live universes, it
reconciles against the Nautilus port on 93 of 93 rebalances, and its numbers are in
the README. The chart is the only thing in the repository still saying otherwise,
and it says it in 14-point type at the top of the image.

**Not fixed deliberately.** The stale text is evidence of when the density fix
landed and what it changed, and editing it away would remove that. Fixing it
properly means deciding whether the blocker note should be recomputed from the
current panel, rewritten as a dated historical note, or deleted — that is a
judgement about what the chart is for, not a typo correction.

**Consequence for the README.** `chart_mid_FINAL.png` is not embedded in
`README.md` while this stands. The published figure is
`docs/chart_COMBINED_n100_mid.png`, which covers mid and n100 together and carries
no stale text. If the mid chart is ever wanted on its own, this has to be resolved
first.
