"""
capital_axis.py -- the STARTING CAPITAL axis, and the one definition of it.

DEFAULT is the starting capital of every published run, Rs 10,00,000. It used to
be written out as START_CAPITAL = 1_000_000 in six files (test_exposure,
engine_core, engine_v2_final, make_daily_log, nautilus/nt_run,
nautilus/nt_attribution); each of those names is now this value, and every code
path a run takes reads selected() instead, so --capital reaches the engine, the
buy & hold, the cost report, the daily log and the Nautilus port alike.

The seventh axis, appended after dd in naming.AXES. The suffix is "" at the
default, so no existing name moves; otherwise "_cap5000000" (whole rupees) after
every other suffix and "@cap5000000" in directory segments.
"""
DEFAULT = 1_000_000
MINIMUM = 100_000          # Rs 1 lakh

_SELECTED = None


def set_selection(rupees):
    """Record this run's capital. None restores the default. Called once by run.py."""
    global _SELECTED
    if rupees is None:
        _SELECTED = None
        return
    if int(rupees) != rupees or int(rupees) < MINIMUM:
        raise ValueError(f"starting capital must be a whole number of rupees, at least "
                         f"{MINIMUM:,}; got {rupees!r}")
    _SELECTED = int(rupees)


def selected():
    """The run's starting capital in rupees, an int. DEFAULT when nothing set one."""
    return DEFAULT if _SELECTED is None else _SELECTED


def is_default():
    return selected() == DEFAULT


def suffix():
    """"" at the default, else "_cap<rupees>" -- the artefact name tail."""
    return "" if is_default() else f"_cap{selected()}"


def segment():
    """"" at the default, else "@cap<rupees>" -- the directory segment tail."""
    return "" if is_default() else f"@cap{selected()}"


def refusal(profile, impact_given):
    """Why run.py refuses this capital, or None.

    A capital other than DEFAULT is refused under the research profile, which has
    no participation cap and no market impact and so gives the same return at any
    size, and under the tradeable profile unless --impact is given, 0 included.
    The values listed are results/impact_sweep.py's K_VALUES."""
    if is_default():
        return None
    if profile == "research":
        return (f"--capital {selected():,} needs --profile tradeable: the research profile "
                f"ignores capital size (it has no participation cap and no market impact, so "
                f"every capital gives the same return). Use --profile tradeable with "
                f"--impact K.")
    if not impact_given:
        return (f"--capital {selected():,} needs an explicit --impact K under the tradeable "
                f"profile: no impact coefficient is assumed. Give --impact 0 for no market "
                f"impact, or one of the values results/impact_sweep.py measures: "
                f"{', '.join(f'{k:g}' for k in sweep_k_values())}.")
    return None


def sweep_k_values():
    """results/impact_sweep.py's K_VALUES, read from its source without importing it
    (it imports the engine)."""
    import ast
    from pathlib import Path
    src = (Path(__file__).resolve().parent / "results" / "impact_sweep.py").read_text()
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "K_VALUES"
                                                 for t in node.targets):
            return tuple(ast.literal_eval(node.value))
    raise RuntimeError("results/impact_sweep.py defines no K_VALUES")


def label():
    """The chart-title fragment, "" at the default."""
    return "" if is_default() else f"capital Rs {selected():,}"
