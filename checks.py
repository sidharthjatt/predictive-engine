"""
checks.py -- every check of this repository, and the command that runs them all.

    ./venv/bin/python checks.py                 every fast gate and delegate (was check_all.py)
    ./venv/bin/python checks.py --slow          also the validate_* gates that refit the model
    ./venv/bin/python checks.py TOOL [ARGS]     one check, as its own file used to run

The tools, in file order (each section header names the file it came from):
  check_all            the runner: gates 0-9 and every delegate, each in its own process
  check_data           raw data against the recorded sha256 manifests
  code_checks          static code checks (platform identity, stop call sites, cost
                       reconciliation, transitional asserts)
  engine_tests         synthetic engine tests, one case per process
  gate_compare         compare two artefacts' approved fields
  naming_declare_check every artefact write declares the axes its name carries
  tax_acceptance_check the tax axis composes names as the other axes do
  test_survivorship    point-in-time membership
  engine_core          the validation backtest (backtest, avg_hold) used by
                       validate_sizing; metrics() is in backtest_runs.py
  validate_engine, validate_sizing, validate_topn, validate_breadth_live
                       the slow gates (--slow)
  check_a_close_values, check_b_exec_timing, leakage_check1_causality,
  leakage_check2_trading_purge
                       look-ahead and execution-timing checks on run artefacts
  nt_attribution, nt_verify, verify_v34_arms, verify_next_open_execution
                       the Nautilus port against the engine
  lookahead_proof      no decision on or before a cut date reads data after it
  test_dashboard       the dashboard page in headless Chrome (run by hand)
  costs_selftest       costs.py's worked charge examples

Importing this file imports no Nautilus module: the tools that need the port
import it in their setup function.
"""
from __future__ import annotations
import sys
from pathlib import Path

import python_floor  # before any third-party import
python_floor.require("checks.py")

ROOT = Path(__file__).resolve().parent
import argparse
import ast
import contextlib
import importlib
import re
import subprocess
import time
import warnings
from market_data import read_table
from settings import list_dir
from settings import CERTIFIED as _CERTIFIED
import hashlib
import json
import tempfile
import numpy as np
import pandas as pd
import market_data
import os
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import settings
from costs import calc_tc
from costs import SLIPPAGE
from costs import fill_price
from settings import capital_axis
import model
from settings import REGISTRY
from model import seed_cache_key
from backtest_runs import metrics
from market_data import precompute
from model import score_monthly
from model import HORIZON
from portfolio import backtest_exposure
from portfolio import TOP_N
from portfolio import BUFFER
from portfolio import START_CAPITAL
import costs
from model import score_floor
from settings import certified
import portfolio
from backtest_runs import arm_row
from backtest_runs import held_and_skips
from backtest_runs import _git_state
from market_data import EXTREME_RET_HI
from market_data import EXTREME_RET_LO
from datetime import datetime
from settings import gated
import portfolio as _arm_reg
from market_data import FEATS_V2
from market_data import add_stock_features
from market_data import add_market_relative_features
from model import PURGE_EMBARGO
from market_data import rolling_std
import io
from settings import argv_universes
from settings import check_tags
from portfolio import ALL_ARMS as _ARMS
from portfolio import ARMS as ARM_REGISTRY
import pickle
import base64
import shutil
import socket
import struct
import urllib.request


# ======================================================================================
# check_all. From check_all.py (moved 2026-11-27).
# ======================================================================================
# check_all -- one command, against one class of defect.
#
#     ./venv/bin/python checks.py                  # before every commit, and in CI
#     ./venv/bin/python checks.py --since <epoch>  # after a run: did the steps write?
#
# THE CLASS, STATED ONCE
#     AN OPERATION REPORTS SUCCESS HAVING DONE PART OR NONE OF THE WORK.
#
#     Not a family of unrelated bugs. One shape, four instances in this repository
#     inside two weeks, each caught by a different accident:
#
#       1. NINE things a new universe must be wired into, two of them invisible to
#          every static check -- PAIR_CHART_REGISTRY_SIZE, read at a pipeline
#          step's run time, and seed_noise_measure.LABELS, read at the import of a
#          module the pipeline never imports. A survey conducted entirely through
#          the static gates reported the cost as seven.
#       2. seed_noise_measure and seed_noise_report UNIMPORTABLE FOR TWO WEEKS,
#          from the day nifty50 was registered, beside four green checkers. Found by
#          accident, in the control arm of an unrelated experiment.
#       3. A REGEX OVER PIPELINE_ORDER MATCHING 12 OF 15 ROWS, twice, because the
#          script column contains digits. Both times the half-renamed pipeline
#          imported cleanly. Caught by an assertion the author happened to write.
#       4. reports.py RUN DIRECTLY, WRITING NOTHING, EXITING 0 -- its
#          __main__ guard exists only inside a docstring. Caught by diffing the
#          output against copies saved beforehand.
#
#     Every one of them would have passed `git commit`. Three of the four would
#     have passed CI. The common property is not that the checks were missing; it
#     is that SUCCESS AND PARTIAL SUCCESS WERE INDISTINGUISHABLE at the only
#     moment anybody looked.
#
# WHAT THIS DOES ABOUT IT
#     Five gates, in one exit code. Gates 1-4 are new; gate 5 folds in the four
#     checkers that already existed so there is ONE command rather than five, and
#     so that "I ran the checks" means the same thing every time it is said.
#
#     GATE 0  RAW DATA     runs first: checks.py check_data, static and --pit, read-only.
#                          Any missing, different or extra price file stops the
#                          run before any other gate, naming the files. The other
#                          gates rebuild the constituent farms from data/raw/, so
#                          a stray file would otherwise be linked in first. Added
#                          2026-10-16 after data/raw/ was restored from an older
#                          copy and PRIVISCL, removed 2026-10-10, came back. A
#                          precondition, not one of the nine counted gates.
#     GATE 1  IMPORTS      every module in the repository, by name, loudly.
#     GATE 2  TABLE        PIPELINE_ORDER's row count against a DECLARED constant,
#                          and every script column resolved to a file on disk.
#     GATE 3  ENTRY POINTS every script the pipeline invokes has a real __main__
#                          block that CALLS something -- by AST, not by grep.
#     GATE 4  OUTPUTS      with --since: every step's declared span contains a file
#                          whose mtime moved. "Ran, wrote nothing, exited 0" fails.
#                          Only steps of universes that a run finishing after
#                          --since selected (its runs/*/RUN.txt); the rest are
#                          "not selected by this run" and skipped.
#     GATE 6  TAX          with --since: under tax=on the numbers must MOVE, by
#                          what the ledger says. The string-only acceptance check
#                          cannot tell a renaming axis from a charging one, and for
#                          the axis's first day that is what it was.
#     GATE 5  DELEGATES    every gate-like script in the tree that can return a
#                          verdict, run and reported ONE LINE EACH. It was four
#                          scripts until 2026-09-22; the other sixteen were never
#                          called by anything. Scripts that check one universe per
#                          invocation are listed once per live tag, because a
#                          single call checks one and says nothing about the other.
#                          The refit ones need --slow; without it they are named
#                          skips. Three cannot assert at all and are listed with
#                          the reason. See DELEGATES.
#     GATE 8  DATA SOURCE  every v34_params*.json and v34_stop_params*.json
#                          names the price data it was built from -- resolved raw_data_dir, symlink target and a
#                          sha256 over the whole input -- and that source is still
#                          the one the registry uses. FAILS CLOSED: a missing field
#                          is a failure. This is the only gate that opens a price
#                          file. It exists because midcap150's tradeable artefacts
#                          were built on a source the tree no longer has, and the
#                          other seven were green for three days.
#     GATE 7  LTCG         the artefacts' claim about the long-term branch must
#                          match the lots. Fails when a universe's longest hold
#                          is held more than twelve calendar months while
#                          HOLDING_PERIOD still says
#                          the branch does not fire. This is the gate whose absence
#                          let 443- and 588-day lots appear unannounced.
#     GATE 9  LIVE-LIKE    the four delegates that prove the backtest trades like
#                          a live book: fills at the next open, priced to the paisa
#                          (check_b_exec_timing, verify_next_open_execution), no
#                          feature look-ahead (leakage_check1_causality) and a
#                          positive purge gap (leakage_check2_trading_purge). Split
#                          out of GATE 5 on 2026-09-24 so they count in the final
#                          tally: GATE 5 never asserts (three of its delegates
#                          cannot, see DELEGATES), which hid these four with it.
#                          Asserts when all four ran and passed; a missing input
#                          is a named skip. Covers every registered universe
#                          (registry.gated()) since 2026-09-25.
#
# WHICH GATE NEVER ASSERTS, AND WHY
#     GATE 5, even with --since and --slow. One of its delegates can never
#     assert inside this runner: checks.py gate_compare needs an artefact pair. Any skipped delegate
#     makes GATE 5 a skip, so it is always one. Its delegates still run and a
#     failing one still fails the run.
#
# WHAT GATE 4 IS, AND WHAT IT IS NOT -- READ THIS BEFORE TRUSTING IT
#     It was specified as "assert each step declares its outputs, then assert those
#     files exist and their mtime moved". The first half is NOT implemented as a
#     new table of outputs per step, deliberately, and the deviation is written
#     here rather than left to be discovered.
#
#     A second list of what each step writes would be a list that can disagree with
#     the code -- the exact failure this repository has recorded under
#     REQUIRED_INPUTS, PIPELINE_ORDER, REPORT_ORDER and FILES, four tables that
#     each went stale once. check_pipeline_order's scanner cannot supply the list
#     either: `_scan` on an entry point alone returns ZERO writes for all ten
#     steps, because a step is scanned concatenated with its helpers and its tag is
#     bound from the invocation. Reproducing that here would be a second copy of
#     the hardest code in the repository.
#
#     So gate 4 uses the declaration the table ALREADY CARRIES: field 3 (the
#     universe a row runs for) and field 4 (row_span, the universes whose metrics
#     directories the step touches). After a run, every step must have left at
#     least one file with a moved mtime inside that span. It is coarser than a
#     per-file manifest -- a step that writes three of its four artefacts passes --
#     and it is exact on the case that has actually happened four times: a step
#     that wrote NOTHING and said it was fine.
#
#     A whole-run step (field 3 None, no span) declares nothing about where it
#     writes, so gate 4 cannot check it and SAYS SO, per step, rather than
#     counting it as passed.

# Modules that are not this project's code, or that no import can reach without
# side effects worth avoiding. venv is obvious; the rest are directories this
# repository does not own or that hold copies rather than source.
CHECK_ALL_SKIP_DIRS = {"venv", ".git", "__pycache__", "node_modules", "runs",
             "pre_repoint_baseline"}
CHECK_ALL_SKIP_PREFIX = ("forensic_snapshot_",)
# THE DELEGATE TABLE. It was a tuple of four bare filenames run with no
# arguments, which is why sixteen gate-like scripts sat dormant: a script that
# needs an argument could not be expressed here at all.
#
# Each row is (script, args, slow, blocked).
#
#   args     the argument list, so a script that checks one universe per run can
#            appear TWICE with different tags. checks.py validate_sizing and
#            checks.py nt_verify both silently check a single universe otherwise.
#   slow     it refits the model. Run only under --slow; otherwise recorded as a
#            named skip, never as a pass.
#   blocked  it cannot return a meaningful verdict as it stands, with the reason.
#            Always a skip. Listed rather than omitted, because a gate nobody
#            lists is a gate nobody remembers, which is how these went dormant.
#
# WHY --run APPEARS ON THE SLOW ROWS. checks.py validate_sizing and
# checks.py validate_breadth_live return early WITHOUT it, and the early return exits 0
# having asserted nothing -- `return` with no value, then `sys.exit(main())`.
# Wiring them without --run would have produced a green over zero tests, which
# is the defect class this file exists to catch.

# GATE 9's members. They run inside the delegate loop like every other delegate
# and are reported in the same table; they are tallied as their own gate.
LIVE_LIKE = (
    "check_b_exec_timing",
    "verify_next_open_execution",
    "leakage_check1_causality",
    "leakage_check2_trading_purge",
)

# nt_verify cells that do not verify and so are not in DELEGATES, each with the
# reason. The 12 core-arm cells listed here on 2026-09-27 have verified since
# 2026-09-29 under nt_verify's quote-mid valuation rule (pass I; KNOWN_ISSUES.md).
#
# midcap100 v3, 2026-10-10 data. The port and the open-valued baseline first hold
# different names on 2024-10-23: the port buys 87 POWERINDIA, the baseline 1,175
# TATAINVEST. At the previous rebalance, 2024-09-24, both held the same names, the
# port one to three shares lower on four of them, from close-against-open
# valuation and the 0.05 tick grid; with slightly less cash, a different entrant
# was funded at the cash-short skip. Names then differ on 7 of 92 rebalances, and
# the port-minus-engine equity gap grows from +1.6% before the fork to +6.08% at
# the end. Neither the port nor the rule was changed.
#
# microcap250 v3 was listed here while its results were withheld for PRIVISCL's
# bad price data. Rerun without PRIVISCL on 2026-10-10 it verifies (quote-mid
# valuation, 92 of 92 rebalances, no symbol-set difference) and is gated again.
#
# v5 and v6 are rejected and outside --arm all, so none of their 16 cells is
# gated; every v5/v6 figure was measured on the previous data delivery.
NT_VERIFY_UNGATED = (
    ("midcap100", "v3", "holds different names from the open-valued baseline on 7 of 92 rebalances from 2024-10-23"),
    # THE MARKET-CAP BUCKETS: mcapover10000 verifies on all four arms (92 of 92).
    # These eight stay ungated until nt_attribution and the port apply the
    # engine's row rule, and are then gated together (owner's decision,
    # 2026-10-17). Measured 2026-10-17, after the rule went into the engine:
    # mcap5001to10000 v2 and v4 verify, the other six are INCONCLUSIVE.
    ("mcap1500to5000", "v1", "INCONCLUSIVE, measured 2026-10-17: ARM A holds the engine's own symbol set on 73 of 92 rebalances; the engine trades a name only on sessions with a row and defers a due sale to the next row (market_data.py, the row rule); nt_attribution and the port do not, so nt_verify cannot judge the port here"),
    ("mcap1500to5000", "v2", "INCONCLUSIVE, measured 2026-10-17: ARM A holds the engine's own symbol set on 80 of 92 rebalances; the engine trades a name only on sessions with a row and defers a due sale to the next row (market_data.py, the row rule); nt_attribution and the port do not, so nt_verify cannot judge the port here"),
    ("mcap1500to5000", "v3", "INCONCLUSIVE, measured 2026-10-17: ARM A holds the engine's own symbol set on 70 of 92 rebalances; the engine trades a name only on sessions with a row and defers a due sale to the next row (market_data.py, the row rule); nt_attribution and the port do not, so nt_verify cannot judge the port here"),
    ("mcap1500to5000", "v4", "INCONCLUSIVE, measured 2026-10-17: ARM A holds the engine's own symbol set on 79 of 92 rebalances; the engine trades a name only on sessions with a row and defers a due sale to the next row (market_data.py, the row rule); nt_attribution and the port do not, so nt_verify cannot judge the port here"),
    ("mcap5001to10000", "v1", "INCONCLUSIVE, measured 2026-10-17: ARM A holds the engine's own symbol set on 89 of 92 rebalances; the engine trades a name only on sessions with a row and defers a due sale to the next row (market_data.py, the row rule); nt_attribution and the port do not, so nt_verify cannot judge the port here"),
    ("mcap5001to10000", "v2", "VERIFIED 92 of 92, measured 2026-10-17, not gated: it verifies only because no owed sale or refused buy reaches this arm's selection; nt_attribution and the port do not apply the engine's row rule (market_data.py), and all eight bucket cells are gated together once they do"),
    ("mcap5001to10000", "v3", "INCONCLUSIVE, measured 2026-10-17: ARM A holds the engine's own symbol set on 84 of 92 rebalances; the engine trades a name only on sessions with a row and defers a due sale to the next row (market_data.py, the row rule); nt_attribution and the port do not, so nt_verify cannot judge the port here"),
    ("mcap5001to10000", "v4", "VERIFIED 92 of 92, measured 2026-10-17, not gated: it verifies only because no owed sale or refused buy reaches this arm's selection; nt_attribution and the port do not apply the engine's row rule (market_data.py), and all eight bucket cells are gated together once they do"),
)

DELEGATES = (
    # registry_coverage_check.py and check_pipeline_order.py (both rows) were
    # retired on 2026-11-26; they last exist at commit dbe387e.
    ("naming_declare_check",               [], False, None),
    # The gate backtest_runs.py applies before a run: declared defects and declarations
    # that do not hold fail it. Judged by its exit code, so check_all fails
    # whenever backtest_runs.py would refuse to start.
    ("naming_declare_check",               ["--gate-declared-only"], False, None),
    # THE FOUR CHECKS BELOW AND FURTHER DOWN ARE CASES OF checks.py code_checks SINCE
    # 2026-10-19, one row per old file, each run as its own subprocess.
    ("code_checks", ["platform_identity"], False, None),
    # No call site may pass an arm's mode and sizing and drop its drawdown stop:
    # v5 and v6 share v1's and v3's mode and sizing. Static; a second.
    ("code_checks", ["stop_callsite"], False, None),
    # THE TEN TESTS BELOW ARE CASES OF checks.py engine_tests SINCE 2026-10-18, one row per
    # old file, each run as its own subprocess. Never run two cases in one process:
    # cache_key changes the state of modules it imports.
    # The drawdown stop's edge cases on a synthetic panel, engine and reference
    # copy: exit on a rebalance day, capped and unopened exit sales, the tax
    # assessment day, the last two days, a re-entry with no fill, low breadth.
    ("engine_tests", ["drawdown_stop", "--quiet"], False, None),
    # The drawdown-limit axis on a synthetic panel: the partial sells and top-ups
    # it adds, the band, the floor, the cap, a missing open, a gap through the
    # limit, tax on, and the refusal on a stop arm. Every case is reconciled to
    # the paisa by cost_report. A few seconds.
    ("engine_tests", ["dd_overlay", "--quiet"], False, None),
    # The tax rules of 2026-10-14 on hand-worked cases, to the paisa: the
    # calendar-month holding period, short loss against long gain, carry-forward
    # with its 8-year limit and oldest-first order, the 4% cess, and the engine's
    # Ledger carrying a loss forward. A second.
    ("engine_tests", ["tax_rules", "--quiet"], False, None),
    # The starting-capital axis on a synthetic panel: validation, names, the default
    # path unchanged, the engine and the buy & hold at a selected capital, and one
    # definition of the default. A second.
    ("engine_tests", ["capital_axis", "--quiet"], False, None),
    # The market-impact and participation-cap axes on a synthetic panel: validation,
    # names, the research refusal, the default path unchanged, and impact split from
    # flat slippage in the cost report. A second.
    ("engine_tests", ["impact_pcap_axis", "--quiet"], False, None),
    # The fixed-capital axis: purchases never lift invested value above the book
    # (nifty200 pit tradeable, v1 to v4, tax off and on), fixed and compounded runs
    # identical while equity has not passed the base (nifty500 v4 pit tradeable, and
    # a synthetic falling panel), and every test run reconciled from its own fills.
    # About 40 seconds; reads the cached pit panels.
    ("engine_tests", ["fixed_capital", "--quiet"], False, None),
    # The COSTS block's tax figures against what cash paid: the printed tax total
    # equals COST_TAX_YEARS total_tax and the ledger's cum_tax, and short + long +
    # cess add up to it, in the summary, the per-year table and the buy & hold.
    # A synthetic tax-on run. A second.
    ("engine_tests", ["tax_total", "--quiet"], False, None),
    # The row rule (reports.py): rows dated after day i change no trade
    # up to day i; an owed sale fills at the next row's open; a capped owed sale is
    # cancelled when kept again; an ended file is held at its last close; no buy on
    # a session with no row. A synthetic universe on calendar sessions; about 10
    # seconds. The engine before 2026-10-16 fails five of its six cases.
    ("engine_tests", ["tradability_causality", "--quiet"], False, None),
    # market_data.py on synthetic membership files: static mode is a
    # no-op, the validation gate rejects each failure mode, and the point-in-time
    # lookup holds at its boundaries. 55 checks, about a second. Writes only into
    # a tempfile.mkdtemp folder, which it does not delete. Wired 2026-10-18.
    ("test_survivorship",          [], False, None),

    # Cheap, and each already carries an exit status.
    ("leakage_check1_causality",   [], False, None),
    ("leakage_check2_trading_purge", [], False, None),
    ("validate_topn",              [], False, None),
    ("check_a_close_values",       [], False, None),
    # A fit cache from other code or other data must be refused.
    # Writes only into a temporary directory. A few seconds.
    ("engine_tests", ["cache_key"], False, None),
    # engine_tests noise_harness was retired on 2026-11-26 with the noise scripts.
    # A buy cash cannot fully pay for: trim gives the largest q that fits, the
    # rounding of charges included; q = 0 and q below half the wanted quantity
    # are refused; refuse trims nothing.
    # Synthetic, no data. A few seconds.
    ("engine_tests", ["buy_shortfall", "--quiet"], False, None),
    # A buy's quantity comes from the decision close: moving one fill session's
    # open leaves every wanted quantity that session unchanged.
    # Synthetic, no data. A few seconds.
    ("engine_tests", ["fill_open_sizing", "--quiet"], False, None),
    ("engine_tests", ["fill_price", "--quiet"], False, None),
    ("check_b_exec_timing",        [], False, None),
    ("verify_next_open_execution", [], False, None),
    ("tax_acceptance_check",               [], False, None),
    # Charges, slippage and tax reconciled to the paisa (reports.py) on
    # every universe and arm, both profiles, tax off and on, and the buy & hold:
    # 144 combinations, nothing written. About 4 minutes.
    ("code_checks", ["cost_reconcile"], False, None),
    ("code_checks", ["transitional_asserts"], False, None),

    # THE PORT AGAINST THE REFERENCE FOR EVERY ARM, on the certified universes.
    # Wired 2026-09-26 after a re-run on the current data and numerics passed 92
    # of 92 on all four arms of both; its previous output predated the
    # 2026-09-18 data repoint. About 70 s.
    ("verify_v34_arms",                    [], False, None),

    # ONE UNIVERSE PER INVOCATION, once per registry.CERTIFIED tag. checks.py nt_verify
    # defaults to the first REGISTERED universe, which is not a statement about
    # what ships; naming each tag is.
    # EVERY (UNIVERSE, ARM) CELL, SINCE 2026-09-29. nt_verify takes --arm. On the
    # cleaned prices all 32 cells verify (diagnostics/nt_verify_all_arms_20260929.txt):
    # 20 by the one-share signature, 12 by the quote-mid valuation rule added to
    # nt_verify that day (pass I). On 2026-09-27 20 of 32 did; on 2026-09-26, before
    # the cleaning, 16. The cells are named so that a cell cannot leave the gate
    # without an edit that shows in a diff. On the 2026-10-10 data 35 of the 36
    # cells are gated; midcap100 v3 is in NT_VERIFY_UNGATED above, with the reason.
    *[("nt_verify", [f"--universe={t}"] + ([] if a == "v2" else [f"--arm={a}"]),
       False, None)
      for t, a in (("nifty100", "v1"), ("nifty100", "v2"), ("nifty100", "v3"), ("nifty100", "v4"),
                   ("midcap150", "v1"), ("midcap150", "v2"), ("midcap150", "v3"), ("midcap150", "v4"),
                   ("nifty50", "v1"), ("nifty50", "v2"), ("nifty50", "v3"), ("nifty50", "v4"),
                   ("midcap50", "v1"), ("midcap50", "v2"), ("midcap50", "v3"), ("midcap50", "v4"),
                   ("midcap100", "v1"), ("midcap100", "v2"), ("midcap100", "v3"), ("midcap100", "v4"),
                   ("nifty200", "v1"), ("nifty200", "v2"), ("nifty200", "v3"), ("nifty200", "v4"),
                   ("smallcap250", "v1"), ("smallcap250", "v2"), ("smallcap250", "v3"), ("smallcap250", "v4"),
                   ("nifty500", "v1"), ("nifty500", "v2"), ("nifty500", "v3"), ("nifty500", "v4"),
                   ("microcap250", "v1"), ("microcap250", "v2"), ("microcap250", "v3"),
                   ("microcap250", "v4"),
                   # THE MARKET-CAP BUCKETS, ADDED 2026-10-16: static, research, tax off.
                   ("mcap1500to5000", "v1"), ("mcap1500to5000", "v2"),
                   ("mcap1500to5000", "v3"), ("mcap1500to5000", "v4"),
                   ("mcap5001to10000", "v1"), ("mcap5001to10000", "v2"),
                   ("mcap5001to10000", "v3"), ("mcap5001to10000", "v4"),
                   ("mcapover10000", "v1"), ("mcapover10000", "v2"),
                   ("mcapover10000", "v3"), ("mcapover10000", "v4"))
      if (t, a) not in {(u, x) for u, x, _ in NT_VERIFY_UNGATED}],

    # SLOW. checks.py validate_engine iterates the certified universes inside one run,
    # so it is wired ONCE and must not be given a tag. The other two do not, so
    # they are wired once per tag.
    ("validate_engine",            [], True, None),
    *[("validate_sizing", [f"--universe={t}", "--run"], True, None)
      for t in _CERTIFIED],
    *[("validate_breadth_live", [f"--universe={t}", "--run"], True, None)
      for t in _CERTIFIED],

    # NO DECISION ON OR BEFORE A CUT DATE READS DATA AFTER IT, on every normal run
    # since 2026-11-27: nifty50 static, all four arms, one cut, the configuration
    # recorded in diagnostics/result_runs_verification_20261124.txt (about 19 min).
    ("lookahead_proof", ["--universe", "nifty50", "--mode", "static",
                         "--arms", "v1,v2,v3,v4", "--cut", "2022-12-30"], False, None),
    # costs.py's worked charge examples, which nothing ran before 2026-11-27.
    ("costs_selftest", [], False, None),

    # BLOCKED, each with the reason rather than an invented pass condition.
    ("gate_compare", [], False,
     "cannot run standalone: needs two positional artefact paths plus "
     "--universe, --arm and --since, and this runner has no artefact pair to "
     "hand it"),
)


# RETIRED, AND NOT IN THE TABLE ABOVE. None since 2026-10-22, when
# results/leakage_check2_purge.py was deleted with the calendar purge rule it
# audited.
RETIRED_DELEGATES = {}

# THE VERDICT LINE NAMES EVERY DELEGATE THAT DID NOT ASSERT, AND THIS IS WHERE THE
# WORDS COME FROM. Added 2026-09-22.
#
# WHY A SECOND, SHORTER REASON RATHER THAN THE ONE ALREADY WRITTEN. The reasons in
# DELEGATES and RETIRED_DELEGATES are two and three lines each, correctly: they
# have to justify the skip to somebody deciding whether to accept it. A verdict
# line carrying eight of those is a verdict line nobody finishes, which is how
# "GATE 5  8 of 22 delegates did not assert" came to be the whole of it -- true,
# and naming nobody.
#
# THIS IS THE SAME DEFECT THE Result DOCSTRING DESCRIBES, ONE LEVEL DOWN. That one
# was a verdict line concealing which GATES did not assert. This was a verdict
# line concealing which DELEGATES did not, inside a gate that reported the count
# honestly and the names only in a table forty lines away.
#
# DECLARED, NOT DERIVED. Truncating the long reason at its first clause would put
# an arbitrary prefix in the verdict; a blocked or retired delegate with no entry
# here is a FAILURE below, not a blank, so the next one cannot slip in unnamed.
SKIP_SHORT = {
    "gate_compare": "needs an artefact pair this runner does not have",
}
SLOW_SHORT = "refits the model; needs --slow"

# WHAT A DELEGATE READS THAT A RUN PRODUCES. Added 2026-09-23.
#
# A FRESH TREE IS NOT A FAILED CHECK. On a clean-room copy these five exited 1
# for one reason: an input that only a pipeline run writes was absent -- a panel
# under cache/, or a universe's daily audit files or Nautilus reports. That made
# the runner red on every fresh checkout for a reason that says nothing about the
# code. A delegate whose declared inputs are missing is now a named SKIP that
# says which file and which command produces it; a delegate whose inputs exist
# and that then fails is still a failure.
#
# DECLARED, NOT INFERRED FROM THE ERROR TEXT. Classifying a traceback as "missing
# input" would also classify a genuinely missing file the code should have
# written. Each entry lists what the script reads, from the registry.
def _needs(label):
    import settings
    from settings import REGISTRY as _R
    from settings import certified as _certified, gated as _gated
    two = _certified()
    every = _gated()
    if label == "leakage_check2_trading_purge":
        return [u.raw_cache for u in every]
    if label == "leakage_check1_causality":
        return [u.data_dir for u in every]
    if label == "validate_topn":
        return [u.score_cache for u in two] + [u.metrics_dir / "v34_comparison.csv" for u in two]
    if label == "check_b_exec_timing":
        from portfolio import ARMS as _A
        return [u.score_cache for u in every] + [
            ROOT / "nautilus" / "reports" / u.tag / a / "fills.csv"
            for u in every for a in _A]
    if label == "code_checks cost_reconcile":
        return [u.score_cache for u in _R.values()]
    if label == "verify_v34_arms":
        return [u.score_cache for u in two]
    if label.startswith("nt_verify --universe="):
        opts = dict(a.split("=", 1) for a in label.split()[1:])
        u = _R[opts["--universe"]]
        if str(ROOT / "results") not in sys.path:
            sys.path.insert(0, str(ROOT / "results"))
        import backtest_runs as _as
        tag = _as.artefact_tag(u, opts.get("--arm", "v2"))
        return [u.score_cache] + [u.metrics_dir / f"{s}_{tag}.csv" for s in
                                  ("daily_summary", "daily_holdings",
                                   "daily_trades", "daily_decisions")]
    return []

# naming_declare_check reports a KNOWN, PRE-EXISTING count of undeclared write
# calls and exits 1 for it. That number was 111 before this checker existed and
# is not this checker's business to fix; what IS its business is that the number
# does not GROW unnoticed. The check below ignores the script's exit code and
# fails only when the count rises above this baseline. A fall is not reported
# and does not lower the baseline on its own; known-defect markers do not count.
#
# 71 SINCE 2026-10-22, the count after the look-ahead fixes, which deleted four
# files (81 from 2026-10-18, the count on 4a4b427). THE BASELINE MAY ONLY GO
# DOWN: lower it by hand when writes are declared, and never raise it to make
# room for a new undeclared write. See KNOWN_ISSUES.md.
NAMING_UNDECLARED_BASELINE = 71

# MODULES KNOWN NOT TO IMPORT, EACH WITH ITS REASON. An unlisted failure is a
# gate-1 failure; so is a LISTED module that starts importing, because an
# exception nobody removes is how a list like this rots. The whole point of this
# checker is that a green run means something, and a checker that is permanently
# red means nothing at all -- but the cure for that is a declaration with a
# reason, not a lowered bar.
#
# EMPTY SINCE 2026-09-29. The two entries it held, diagnostics/membership/analyse.py
# (needed pdfplumber) and results/audit_leakage.py (imported the missing engine_v2),
# were deleted as dead code. results/save_ewma_comparison.py left the list on
# 2026-09-23. A module that fails to import is now a gate-1 failure unless it is
# added here with its reason.
KNOWN_UNIMPORTABLE = {}


# THE SEVEN, BY NUMBER, so the verdict can subtract rather than be told a total.
# A gate added below without a line here would not be counted, which is the same
# defect this file exists to catch, so the count is asserted against it in main().
ALL_GATES = (1, 2, 3, 4, 5, 6, 7, 8, 9)


class Result:
    """Failures, notes, and -- ADDED 2026-09-20 -- WHICH GATES DID NOT RUN.

    THE DEFECT THIS FIXES IS NOT A WRONG NUMBER. Every skip below was already
    printed, honestly, in the body: "GATE 4  SKIPPED -- needs --since ... Not
    counted as passed." The summary line then said "RESULT: PASS -- all seven
    gates" over the top of it. Both lines were produced by the same run and only
    one of them is read, because a verdict line is what a verdict line is for.

    A CHECK THAT REPORTS HONESTLY IN ITS BODY AND MISREPORTS IN ITS SUMMARY is
    its own shape, and it is not the "written, declared to be the fix, never
    wired" class this repository already tracks: the body here was wired, ran,
    and was correct. Nothing was unwired and no literal was stale. The summary
    simply did not read what the body had written -- so the cure is to make the
    verdict a FUNCTION of the recorded skips rather than a constant string.

    A SKIP STAYS LEGITIMATE AND STAYS EXIT 0. Gate 4 and gate 6 cannot assert
    anything without a run to check against; refusing to run them is correct,
    and turning a skip into an error would make the checker permanently red,
    which is the failure mode declared at KNOWN_UNIMPORTABLE above. What is not
    legitimate is a skip that the verdict line conceals.
    """

    def __init__(self):
        self.failures = []
        self.notes = []
        self.skipped = {}
        # ONE ROW PER DELEGATE, so gate 5's summary cannot hide a member of it.
        # The gate-level skip above says how many did not assert; this says
        # which, and why, by name.
        self.delegates = []
        # THE SAME NAMES AGAIN, SHORT, FOR THE VERDICT BLOCK. The table above is
        # printed before the notes and is the full account; this is what travels
        # with the headline, because a headline read on its own must not be able
        # to omit them.
        self.not_asserted = []
        # Per gate, the steps (gate 4) or universe/arm pairs (gates 6, 7) that
        # no run after --since selected: skipped, never passed.
        self.not_selected = {}

    def fail(self, gate, what, detail=""):
        self.failures.append((gate, what, detail))

    def note(self, text):
        self.notes.append(text)

    def skip(self, gate_no, text, why):
        """Record that gate `gate_no` did not assert, and say so in the body too.

        `why` is the short reason the verdict line carries; `text` is the full
        body line, unchanged from what this file printed before.
        """
        self.skipped[gate_no] = why
        self.notes.append(text)

    def delegate(self, label, status, detail="", short=None):
        """Record one delegate's outcome: PASS, FAIL, SKIP or RETIRED.

        `short` is the reason the VERDICT block carries. It is required for any
        status other than PASS and FAIL: a delegate that did not assert and
        cannot say why in one clause is not something to print blank.
        """
        self.delegates.append((label, status, detail))
        if status in ("SKIP", "RETIRED"):
            self.not_asserted.append((label, status, short or "NO REASON GIVEN"))

    def asserted(self):
        return [g for g in ALL_GATES if g not in self.skipped]


# ---------------------------------------------------------------------------
# GATE 1 -- every module imports
# ---------------------------------------------------------------------------
def gate_imports(res):
    """Import every module in the repository and name the ones that refuse.

    THIS IS THE GATE THAT WOULD HAVE CAUGHT seed_noise ON DAY ONE. Those two
    modules raised SystemExit at import from the moment nifty50 was registered, and
    nothing imported them: not run_all, not any checker, not any test. They are
    run by hand, so the failure waited two weeks for a person.
    """
    mods = []
    for p in list_dir(ROOT, "*.py", recursive=True):
        if any(x in CHECK_ALL_SKIP_DIRS for x in p.parts): continue
        if any(x.startswith(CHECK_ALL_SKIP_PREFIX) for x in p.parts): continue
        if p.resolve() == Path(__file__).resolve(): continue
        rel = p.relative_to(ROOT)
        mods.append((rel, p.stem if len(rel.parts) == 1
                     else ".".join(rel.with_suffix("").parts)))
    for path in (ROOT / "results", ROOT / "nautilus"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    bad = 0
    known = set()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for rel, name in mods:
            try:
                if len(rel.parts) > 1 and (ROOT / f"{rel.parts[0]}.py").exists():
                    # dashboard/ beside dashboard.py: the top-level module owns the
                    # name, so the folder is not a package; load the file itself.
                    from importlib import util as _ilu
                    spec = _ilu.spec_from_file_location(name.replace(".", "_"), ROOT / rel)
                    spec.loader.exec_module(_ilu.module_from_spec(spec))
                else:
                    importlib.import_module(name)
            except BaseException as e:               # SystemExit included, on purpose
                first = str(e).splitlines()[0] if str(e) else ""
                if str(rel) in KNOWN_UNIMPORTABLE:
                    known.add(str(rel))
                    continue
                res.fail("GATE 1 imports", str(rel),
                         f"{type(e).__name__}: {first[:120]}")
                bad += 1
            else:
                if str(rel) in KNOWN_UNIMPORTABLE:
                    res.fail("GATE 1 imports", str(rel),
                             "is on KNOWN_UNIMPORTABLE and now imports fine. "
                             "Remove the entry; a stale exception is how the "
                             "list stops meaning anything.")
                    bad += 1
    res.note(f"GATE 1  {len(mods) - bad - len(known)} of {len(mods)} modules "
             f"import, {len(known)} known-unimportable and declared")
    return len(mods)


# ---------------------------------------------------------------------------
# GATE 2 -- the table is the size it says it is, and every script exists
# ---------------------------------------------------------------------------
def gate_table(res):
    """Row count against backtest_runs.PIPELINE_ROW_COUNT, and every script resolved.

    THE ROW IS READ BY INDEX, NEVER MATCHED. row[1] is the script; nothing here
    constructs a pattern over the row's text, because a pattern over this table
    is precisely what matched 12 of 15 rows twice. A checker that re-enacted the
    defect while checking for it would be worse than no checker.
    """
    # THE IMPORT IS GUARDED, because run_all REFUSES AT IMPORT when the table is
    # half-edited -- _step_label cannot name a producer, and it raises SystemExit
    # before this gate can look at a single row. That refusal is correct and it is
    # the thing that caught the 12-of-15 rename twice. What was wrong is that it
    # killed the checker mid-run, so the operator saw one raw message and no
    # report. Caught here and reported as a gate-2 failure, with the rest of the
    # gates still running.
    try:
        import backtest_runs as run_all
    except BaseException as e:
        res.fail("GATE 2 table", "backtest_runs is unimportable",
                 f"{type(e).__name__}: {str(e).splitlines()[0][:160]}")
        res.skip(2, "GATE 2  NOT CHECKED -- backtest_runs does not import",
                 "backtest_runs does not import")
        return []
    rows = run_all.PIPELINE_ORDER
    declared = getattr(run_all, "PIPELINE_ROW_COUNT", None)
    if declared is None:
        res.fail("GATE 2 table", "backtest_runs.PIPELINE_ROW_COUNT",
                 "not declared; a bulk edit over PIPELINE_ORDER cannot be checked")
    elif len(rows) != declared:
        res.fail("GATE 2 table", "row count",
                 f"PIPELINE_ORDER has {len(rows)} rows, PIPELINE_ROW_COUNT says "
                 f"{declared}. One of them is wrong; if a row was added, update "
                 f"the constant by hand.")
    # AND EVERY ROW'S UNIVERSE IS A REGISTERED ONE. This is the half-rename
    # check, and it is the one that speaks to instance 3 in the header. The row
    # COUNT does not catch that defect -- a bulk edit that rewrites 12 of 15 tag
    # values leaves 15 rows -- and run_all already refuses at import when
    # _step_label cannot name a producer. What this adds is WHERE: the failure
    # arrives naming the rows that were missed, at the table, instead of naming
    # the first consumer that could not find a producer.
    from settings import REGISTRY
    missing = stale = 0
    for row in rows:
        label, script = row[0], row[1]
        tag = row[2] if len(row) > 2 else None
        p, _fn = run_all.step_source(script)
        if not Path(p).exists():
            res.fail("GATE 2 table", f"{label} {script}",
                     f"resolves to {p}, which does not exist")
            missing += 1
        if tag is not None and tag not in REGISTRY:
            res.fail("GATE 2 table", f"{label} {script}",
                     f"names universe {tag!r}, which the registry does not "
                     f"define. Known: {', '.join(sorted(REGISTRY))}. A bulk edit "
                     f"over this table covered part of it.")
            stale += 1
    res.note(f"GATE 2  {len(rows)} rows (declared {declared}), "
             f"{len(rows) - missing} steps resolve to a file, "
             f"{len(rows) - stale} rows name a registered universe")
    return rows


# ---------------------------------------------------------------------------
# GATE 3 -- a script the pipeline invokes must do something when invoked
# ---------------------------------------------------------------------------
def _has_live_main(path):
    """True when a module-level `if __name__ == "__main__":` block CALLS something.

    BY AST, NOT BY GREP, and the difference is the whole gate.
    reports.py contains the string "__main__" -- inside a docstring
    explaining that its body was moved out of the guard. A text search passes it.
    Running it does nothing and exits 0.

    This repository has already recorded a scanner matching a comment ABOUT code
    rather than code, twice, in check_pipeline_order's own header. This is the
    third, and it is why the check parses.
    """
    try:
        tree = ast.parse(Path(path).read_text())
    except SyntaxError as e:
        return None, f"does not parse: {e}"
    for node in tree.body:
        if (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
                and getattr(node.test.left, "id", "") == "__name__"):
            if any(isinstance(n, ast.Call) for n in ast.walk(node)):
                return True, ""
            return False, "has a __main__ block that calls nothing"
    return False, ("has no module-level __main__ block; run directly it does "
                   "nothing and exits 0")


def _has_step_function(path, fn):
    """True when `path` defines a module-level function `fn`. A step is a function
    since 2026-11-27 (backtest_runs.STEP_HOME); the two Nautilus steps are still
    their file's main(). By ast, as _has_live_main was."""
    try:
        tree = ast.parse(Path(path).read_text())
    except SyntaxError as e:
        return None, f"does not parse: {e}"
    if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn
           for n in tree.body):
        return True, ""
    return False, f"{Path(path).name} has no module-level function {fn}()"


def gate_entry_points(res, rows):
    if not rows:
        res.skip(3, "GATE 3  NOT CHECKED -- no pipeline table",
                 "no pipeline table")
        return
    import backtest_runs as run_all
    seen, bad = [], 0
    for row in rows:
        script = row[1]
        if script in seen: continue
        seen.append(script)
        p, fn = run_all.step_source(script)
        if not Path(p).exists(): continue          # already reported by gate 2
        ok, why = _has_step_function(p, fn)
        if not ok:
            res.fail("GATE 3 entry points", script, why)
            bad += 1
    res.note(f"GATE 3  {len(seen) - bad} of {len(seen)} pipeline steps name a "
             f"module-level function in their file")


# ---------------------------------------------------------------------------
# GATE 4 -- a step that ran must have written something where it said it would
# ---------------------------------------------------------------------------
def gate_outputs(res, rows, since, sel):
    """After a run: every step's declared span must hold a file whose mtime moved.

    See the module docstring for what this is and is not. The span comes from the
    row itself -- field 3 for a per-universe step, row_span() for a step that
    declares one -- so there is no second table to go stale.

    WHICH STEPS RAN IS READ FROM THE RUN FOLDERS, NOT ASSUMED. Until 2026-09-30
    this checked every universe unless --universe narrowed it, so after
    `run.py --universe nifty100,midcap150` a bare --since failed 36 steps of the
    six universes that run never selected, each "ran, exited 0, and left no
    file". Now the selection comes from RUN.txt of every run folder that
    finished at or after --since (run.read_run_record). A step of a universe no
    such run selected is "not selected by this run" and counted as skipped, not
    passed. If no run folder finished after --since, gate 4 skips rather than
    assume a full run. --universe no longer narrows this gate.
    """
    import datetime
    if not rows:
        res.skip(4, "GATE 4  NOT CHECKED -- no pipeline table",
                 "no pipeline table")
        return
    import backtest_runs as run_all
    from settings import REGISTRY
    if since is None:
        res.skip(4, "GATE 4  SKIPPED -- needs --since <epoch>, i.e. a run to "
                 "check against. Not counted as passed.", "need --since")
        return
    when = datetime.datetime.fromtimestamp(since).strftime("%Y-%m-%d %H:%M:%S")
    runs = _runs_since(since)
    if not runs:
        res.skip(4, f"GATE 4  SKIPPED -- no run folder under runs/ finished at or "
                 f"after --since {since:.0f} ({when}), so which steps ran is "
                 f"unknown. Not counted as passed.", "no run folder for --since")
        return
    want = set()
    for r in runs:
        res.note(f"GATE 4  run {r['folder'].name}: universes "
                 f"{', '.join(r['universes'])}; arms {', '.join(r['arms'])}; "
                 f"cadence {r['cadence']}; profile {r['profile']}; tax {r['tax']}; "
                 f"{r['pipeline_steps']} pipeline steps")
        if r["started"] < since - 1:
            res.note(f"    it started before --since, so a step it finished "
                     f"before --since cannot show a moved file")
        if r["pipeline_steps"]:
            want |= set(r["universes"])
    if not want:
        res.skip(4, "GATE 4  SKIPPED -- the run(s) after --since ran no pipeline "
                 "step (--steps arms). Not counted as passed.",
                 "no pipeline step selected")
        return
    checked = unverifiable = n_skip = 0
    not_selected = {}
    for row in rows:
        label, script = row[0], row[1]
        tag = row[2] if len(row) > 2 else None
        span = run_all.row_span(row) if len(row) > 3 else ()
        declared = (tag,) if tag else tuple(span)
        tags = tuple(t for t in declared if t in want)
        if declared and not tags:
            n_skip += 1
            for t in declared:
                not_selected.setdefault(t, []).append(label)
            continue
        if not tags:
            unverifiable += 1
            res.note(f"    {label} {script}: declares no universe and no span -- "
                     f"gate 4 cannot check where it writes")
            continue
        moved = []
        for t in tags:
            u = REGISTRY.get(t)
            if u is None: continue
            d = Path(u.metrics_dir)
            if not d.exists(): continue
            moved += [f for f in list_dir(d, recursive=True)
                      if f.is_file() and f.stat().st_mtime >= since]
        checked += 1
        if not moved:
            res.fail("GATE 4 outputs", f"{label} {script}",
                     f"ran, exited 0, and left no file with a moved mtime under "
                     f"{', '.join(str(REGISTRY[t].metrics_dir.name) for t in tags if t in REGISTRY)}")
    for t in sorted(not_selected):
        res.note(f"    not selected by this run: {t} -- "
                 f"{', '.join(not_selected[t])}")
    res.not_selected[4] = n_skip
    res.note(f"GATE 4  {checked} steps checked against --since, "
             f"{n_skip} not selected by this run (skipped, not passed), "
             f"{unverifiable} not checkable (no declared span)")


# ---------------------------------------------------------------------------
# GATE 5 -- the four that already existed, run together
# ---------------------------------------------------------------------------
def gate_delegates(res, slow):
    """Run every wired delegate and record a status for each, by name.

    WHAT CHANGED, 2026-09-22. This ran four scripts with no arguments. The other
    sixteen gate-like scripts in the tree were never called by anything, and
    three of them cannot be called without an argument, so no amount of adding
    filenames to a tuple would have reached them.

    A SKIP IS NOT A PASS AND IS NOT A FAILURE. A blocked or slow-and-not-asked-for
    delegate is recorded here, counted, and named in the verdict line through
    res.skip below. The one thing it must never do is leave no trace, which is
    what "run four of twenty" looked like from the outside: a green run.
    """
    ran = skipped = 0
    live = {}                     # GATE 9: name -> PASS / FAIL / SKIP
    for name, args, is_slow, blocked in DELEGATES:
        label = " ".join([name] + args)
        gate = "GATE 9 live-like" if name in LIVE_LIKE else "GATE 5 delegates"
        n_before = len(res.delegates)
        if blocked is not None:
            short = SKIP_SHORT.get(name)
            if short is None:
                res.fail("GATE 5 delegates", label,
                         "is blocked and has no SKIP_SHORT entry, so the verdict "
                         "line would name it without a reason")
            res.delegate(label, "SKIP", blocked, short)
            skipped += 1
            continue
        if is_slow and not slow:
            res.delegate(label, "SKIP", SLOW_SHORT, SLOW_SHORT)
            skipped += 1
            continue
        if name not in TOOLS:
            res.fail("GATE 5 delegates", label, "not a checks.py tool")
            res.delegate(label, "FAIL", "not found")
            continue
        missing = [x for x in _needs(label) if not Path(x).exists()]
        if missing:
            first = Path(missing[0])
            try:
                first = first.relative_to(ROOT)
            except ValueError:
                pass
            why = (f"needs {len(missing)} run artefact(s) not on disk, first "
                   f"{first}; produce with ./venv/bin/python run.py --universe "
                   f"{','.join(_CERTIFIED)}")
            if name in LIVE_LIKE:
                live[name] = "SKIP"
                res.delegate(label, "SKIP", why, None)
                res.not_asserted.pop()
            else:
                res.delegate(label, "SKIP", why, f"needs run artefacts: {first}")
                skipped += 1
            continue
        r = subprocess.run([sys.executable, str(ROOT / "checks.py"), name] + args,
                           capture_output=True, text=True)
        ran += 1
        if name == "naming_declare_check" and "--gate-declared-only" not in args:
            # ITS FAILURE IS A KNOWN NUMBER, AND THE CHECK IS THAT IT DOES NOT GROW.
            import re
            m = re.search(r"GATE 1 \(blocking\): (\d+) write call", r.stdout)
            n = int(m.group(1)) if m else None
            if n is None:
                res.fail("GATE 5 delegates", label,
                         "could not read its undeclared-write count")
                res.delegate(label, "FAIL", "undeclared-write count unreadable")
            elif n > NAMING_UNDECLARED_BASELINE:
                res.fail("GATE 5 delegates", label,
                         f"undeclared write calls rose to {n} from a baseline of "
                         f"{NAMING_UNDECLARED_BASELINE}")
                res.delegate(label, "FAIL",
                             f"undeclared writes {n} > baseline "
                             f"{NAMING_UNDECLARED_BASELINE}")
            else:
                res.delegate(label, "PASS",
                             f"{n} undeclared writes "
                             f"(baseline {NAMING_UNDECLARED_BASELINE})")
            continue
        if r.returncode == 3 and label == "code_checks platform_identity":
            # A NAMED SKIP, NOT A PASS: outside a git checkout with no tracked-file
            # manifest the tracked .py files cannot be listed. The reason is the
            # delegate's last line.
            why = [l for l in r.stdout.splitlines() if l.strip()][-1:] or ["no reason given"]
            res.delegate(label, "SKIP", why[0], "cannot list tracked files")
            skipped += 1
            continue
        if r.returncode != 0:
            tail = [l for l in (r.stdout + r.stderr).splitlines() if l.strip()][-3:]
            res.fail(gate, label, f"exit {r.returncode}: " + " | ".join(tail))
            res.delegate(label, "FAIL", f"exit {r.returncode}")
            if name in LIVE_LIKE:
                live[name] = "FAIL"
        else:
            res.delegate(label, "PASS", "exit 0")
            if name in LIVE_LIKE:
                live[name] = "PASS"

    for name, why in sorted(RETIRED_DELEGATES.items()):
        short = SKIP_SHORT.get(name)
        if short is None:
            res.fail("GATE 5 delegates", name,
                     "is retired and has no SKIP_SHORT entry, so the verdict "
                     "line would name it without a reason")
        res.delegate(name, "RETIRED", why, short)

    n5 = len(DELEGATES) - len(LIVE_LIKE)
    res.note(f"GATE 5  {ran - sum(1 for v in live.values() if v != 'SKIP')} of "
             f"{n5} delegates ran, {skipped} skipped, "
             f"{len(RETIRED_DELEGATES)} retired")
    if skipped or RETIRED_DELEGATES:
        # THE TWO COUNTS MUST AGREE. The verdict block below names skipped AND
        # retired delegates, so the one-line reason says both rather than the
        # smaller number -- a reason that reads "8" above a list of 9 is the same
        # concealment one digit smaller.
        res.skip(5, f"GATE 5  {skipped} skipped + {len(RETIRED_DELEGATES)} "
                    f"retired of {n5 + len(RETIRED_DELEGATES)} delegates did not "
                    f"assert. Not counted as passed.",
                 f"{skipped} skipped + {len(RETIRED_DELEGATES)} retired, "
                 f"named below")

    # GATE 9 -- asserted only when every live-like delegate ran and passed.
    missing9 = [n for n in LIVE_LIKE if n not in live]
    if missing9:
        res.fail("GATE 9 live-like", ", ".join(missing9),
                 "is in LIVE_LIKE but not wired in DELEGATES")
    skip9 = [n for n, v in live.items() if v == "SKIP"]
    if skip9:
        res.skip(9, f"GATE 9  SKIPPED -- {len(skip9)} of {len(LIVE_LIKE)} live-like "
                    f"delegates lack run artefacts: {', '.join(skip9)}. Not counted "
                    f"as passed.",
                 f"live-like delegates lack run artefacts ({', '.join(skip9)})")
    elif not missing9 and all(v == "PASS" for v in live.values()):
        from settings import gated as _gated
        res.note(f"GATE 9  {len(LIVE_LIKE)} of {len(LIVE_LIKE)} live-like delegates "
                 f"passed on all {len(_gated())} universes: next-open fills to the "
                 f"paisa, no feature look-ahead on sampled dates, purge gap > 0")


# ---------------------------------------------------------------------------
# GATE 6 -- the tax axis CHARGES tax, it does not merely rename files
# ---------------------------------------------------------------------------

def _runs_since(since, _cache={}):
    """run.runs_finished_since(since), read once per check_all invocation."""
    if since not in _cache:
        import run as _run
        _cache[since] = _run.runs_finished_since(since)
    return _cache[since]


@contextlib.contextmanager
def _run_axes(rec=None, tax_on=True):
    """Select a run's cadence, profile and arms, and tax on or off, for the
    duration of the block, so the writers' own composers name what that run
    wrote. rec=None selects the defaults (cadence 20, research, all four arms)."""
    from settings import cadence as _cd
    import settings
    from settings import tax as _tx
    import portfolio as _ar
    from settings import survivorship_axis as _sva
    from settings import dd_axis as _dda
    from settings import capital_axis as _capa
    from settings import impact_axis as _impa
    from settings import pcap_axis as _pca
    from settings import fixed_axis as _fxa
    from settings import start_axis as _sta
    saved = (_cd._SELECTED, settings.profile_axis.selected(), _tx.selected(), _ar._SELECTED,
             _sva.selected(), _dda.selected(), _capa._SELECTED, _impa._SELECTED,
             _pca._SELECTED, _fxa._SELECTED, _sta._SELECTED, settings.shortfall_axis.selected())
    try:
        _cd.set_selection(rec["cadence"] if rec else None)
        settings.profile_axis.set_selection(rec["profile"] if rec else None)
        _ar.set_selection(rec["arms"] if rec else None)
        _tx.set_selection(tax_on)
        _sva.set_selection((rec or {}).get("survivorship"))
        _dda.set_selection((rec or {}).get("dd"))
        _capa.set_selection((rec or {}).get("capital"))
        _impa.set_selection((rec or {}).get("impact"))
        _pca.set_selection((rec or {}).get("pcap"))
        _fxa.set_selection(bool((rec or {}).get("fixed")))
        _sta.set_selection((rec or {}).get("start"))
        settings.shortfall_axis.set_selection((rec or {}).get("buy_shortfall"))
        yield
    finally:
        _cd.set_selection(saved[0]); settings.profile_axis.set_selection(saved[1])
        _tx.set_selection(saved[2]); _ar._SELECTED = saved[3]
        _sva.set_selection(saved[4])
        _dda.set_selection(saved[5])
        _capa.set_selection(saved[6])
        _impa.set_selection(saved[7])
        _pca.set_selection(saved[8])
        _fxa.set_selection(saved[9])
        _sta.set_selection(saved[10])
        settings.shortfall_axis.set_selection(saved[11])


def _tax_ledger(u, M, arm="v2", stems=("FY_EQUITY", "FY_TAX_STATEMENT"), rec=None):
    """Paths of `stems` for u's `arm` under tax=on, named by the writers' own
    composers: at the axes run record `rec` selected, or at the default cadence
    and profile when rec is None. Every arm since 2026-09-26."""
    sys.path.insert(0, str(ROOT / "results"))
    import backtest_runs as audit_step
    import reports as tax_report
    from portfolio import ALL_ARMS
    with _run_axes(rec):
        tag = audit_step.artefact_tag(u, ALL_ARMS[getattr(arm, "name", arm)])
        return tuple(M / tax_report.artefact_name(s, tag) for s in stems)


def _v34_equity_pair(M, rec, arm=None):
    """(taxed, untaxed) v34_equity paths at rec's axes, composed as
    v34_common.write_v34 composes them: arm subset, cadence, profile, tax. A stop
    arm's curve is in the companion v34_stop_equity file, named the same way from
    the stop part of the selection."""
    from settings import cadence as _cd
    import settings
    from settings import tax as _tx
    import portfolio as _ar
    stop = getattr(arm, "name", arm) in _ar.STOP_ARMS
    out = []
    for on in (True, False):
        with _run_axes(rec, tax_on=on):
            head = (f"v34_stop_equity{_ar.stop_selection_suffix()}" if stop
                    else f"v34_equity{_ar.selection_suffix()}")
            from settings import survivorship_axis as _sva
            from settings import dd_axis as _dda
            from settings import capital_axis as _capa
            from settings import impact_axis as _impa
            from settings import pcap_axis as _pca
            from settings import fixed_axis as _fxa
            from settings import start_axis as _sta
            import settings
            out.append(M / f"{head}{_cd.suffix()}{settings.profile_axis.suffix()}{_tx.suffix()}"
                           f"{_sva.suffix()}{_dda.suffix()}{_capa.suffix() + _impa.suffix() + _pca.suffix() + _fxa.suffix() + _sta.suffix() + settings.shortfall_axis.suffix()}.csv")
    return tuple(out)


def _tax_targets(res, gate, since):
    """The (run, universe, arm) triples that runs finishing after --since wrote
    tax artefacts for, or None after recording why the gate skips.

    A pair no tax=on run selected is "not selected by this run": listed per
    universe and counted in res.not_selected[gate], never passed. The same
    reading of RUN.txt as gate 4; see gate_outputs.
    """
    import datetime
    from settings import REGISTRY
    from portfolio import ALL_ARMS as ARMS
    runs = _runs_since(since)
    if not runs:
        when = datetime.datetime.fromtimestamp(since).strftime("%Y-%m-%d %H:%M:%S")
        res.skip(gate, f"GATE {gate}  SKIPPED -- no run folder under runs/ finished "
                 f"at or after --since {since:.0f} ({when}), so which tax "
                 f"artefacts a run wrote is unknown. Not counted as passed.",
                 "no run folder for --since")
        return None
    targets, seen = [], set()
    for r in runs:
        if r["tax"] != "on":
            res.note(f"GATE {gate}  run {r['folder'].name}: tax off, so it wrote "
                     f"no tax artefacts")
            continue
        res.note(f"GATE {gate}  run {r['folder'].name}: universes "
                 f"{', '.join(r['universes'])}; arms {', '.join(r['arms'])}; "
                 f"cadence {r['cadence']}; profile {r['profile']}; tax on")
        for t in r["universes"]:
            for a in r["arms"]:
                key = (t, a, r["cadence"], r["profile"])
                if t in REGISTRY and a in ARMS and key not in seen:
                    seen.add(key)
                    targets.append((r, t, ARMS[a]))
    chosen = {(t, a.name) for _r, t, a in targets}
    skipped = {}
    for t in sorted(REGISTRY):
        rest = [a for a in ARMS if (t, a) not in chosen]
        if rest:
            skipped[t] = rest
    for t, rest in skipped.items():
        res.note(f"    not selected by this run: {t} -- {', '.join(rest)}")
    res.not_selected[gate] = sum(len(v) for v in skipped.values())
    if not targets:
        res.skip(gate, f"GATE {gate}  SKIPPED -- no run after --since had tax on, "
                 f"so none wrote tax artefacts. Not counted as passed.",
                 "no tax=on run after --since")
        return None
    return targets


def _written_by_run(res, gate, what, files, rec, since):
    """Fail and return False unless every file exists and moved after --since."""
    missing = [p.name for p in files if not p.exists()]
    if missing:
        res.fail(f"GATE {gate}", what,
                 f"{rec['folder'].name} selected it with tax on, but there is no "
                 f"{', '.join(missing)}")
        return False
    old = [p.name for p in files if p.stat().st_mtime < since]
    if old:
        res.fail(f"GATE {gate}", what,
                 f"{rec['folder'].name} selected it with tax on, but "
                 f"{', '.join(old)} was not rewritten after --since")
        return False
    return True


def gate_tax(res, since, sel):
    """CONDITION 3: under tax=on the numbers must move, by what the ledger says.

    WHAT THE STRING-ONLY CHECK COULD NOT DISTINGUISH, AND FOR HOW LONG.
    checks.py tax_acceptance_check asks two questions, and says plainly that it "checks
    NAMES, not CONTENTS":

        CONDITION 1  at the default, does every composer emit the same string?
        CONDITION 2  off the default, does every composer MOVE?

    Both are satisfied by an axis that renames artefacts and charges nothing.
    From the day the axis landed (7846f67, 2026-09-17) until 21c6624 that is
    exactly what it was: backtest_exposure's tax_enabled defaulted to False at
    every call site on the published path, so `--tax on` produced 36 of 40
    suffixed artefacts BYTE-IDENTICAL to their untaxed twins and the other four
    differed only in a header label. Both conditions passed throughout.

    IT IS THE TRAP THAT CHECK'S OWN DOCSTRING OPENS WITH, ONE LEVEL UP. It warns
    that "AN OMITTED AXIS AND A DEFAULT AXIS PRODUCE THE SAME STRING" and builds
    condition 2 to catch that. What it cannot catch is a RENAMING axis and a
    CHARGING axis producing the same strings -- which they do, because the suffix
    is composed from the selection and not from anything the engine did with it.

    SO THIS GATE ASSERTS CONTENTS, AND IT LIVES HERE RATHER THAN THERE BECAUSE IT
    NEEDS A REAL RUN. tax_acceptance_check runs standalone with no caches and no
    engine, and correctly declines to pretend otherwise. --since already means a
    run happened.

    TWO PARTS, AND THE SECOND IS AN INEQUALITY ON PURPOSE:

      (i)  v34_equity<SFX>'s v2 column at the final session EQUALS FY_EQUITY's
           last close_equity, to a paisa. Two independent paths -- the engine
           under tax=on, and tax_report's own re-run -- must land on the same
           rupee.
      (ii) v34_equity<SFX> differs from the untaxed v34_equity by AT LEAST
           cum_tax.

    (ii) IS NOT AN EQUALITY, AND AN EQUALITY THERE WOULD FAIL ON A CORRECT
    IMPLEMENTATION. The equity gap EXCEEDS the cash taken, by the compounding the
    removed capital no longer earns: measured on midcap50, gap Rs 761,619.36
    against cum_tax Rs 492,955.59, a difference of Rs 268,663.77 -- 35.3% of the
    gap. backtest_runs.py states the mechanism: "the capital it removes stops
    compounding for the rest of the run". THAT IS THE AXIS WORKING. The identity
    that IS an equality is the one reconcile() already checks -- the per-year
    statement summing to the engine's cum_tax -- and it is checked there, at that
    tolerance, rather than restated here.

    IT ASSERTS ON THE ASSESSED TAX, NOT THE STATEMENT TOTAL, AND THAT WAS WRONG
    HERE FOR ONE DAY. This gate first summed every FY_TAX_STATEMENT row, which
    includes the final year's UNASSESSED liability -- section 3(9) charges
    FY2026-27 on the first trading day at or after 2027-03-31, outside the
    window, so no cash was taken for it and it cannot be inside an equity
    difference measured at the last session. Asserting against the total passed
    only by being STRICTER than the identity, which is luck rather than design.

    ONE UNIVERSE COULD NOT SHOW IT. midcap50's unassessed row is 0.00, and so is
    nifty50's, so on either of them the total and the assessed figure are the
    same number and the label looked right. It took a universe with a non-zero
    tail -- midcap150 at Rs 33,671.08, nifty100 at Rs 11,521.13 -- to separate
    them, and it surfaced only when the gate was run on four universes rather
    than the one it was written against. A gate exercised on a single case is a
    gate whose labels have not been read.

    ALL THREE FIGURES ARE PRINTED, separately labelled, because the difference
    between them is what section 3(9) does and a reader should not have to
    recompute it: assessed (deducted), statement total, and unassessed. Foregone
    compounding is derived from the ASSESSED figure -- deriving it from the total
    understates it by the unassessed amount.

    SKIPPED, NOT PASSED, when no tax artefacts are on disk: a tax=off run writes
    none, and this gate says so rather than counting silence as agreement.
    """
    import csv
    if since is None:
        res.skip(6, "GATE 6  SKIPPED -- needs --since, i.e. a run to check "
                 "against. Not counted as passed.", "need --since")
        return
    try:
        sys.path.insert(0, str(ROOT))
        from settings import REGISTRY
    except Exception as e:
        res.fail("GATE 6 tax", "registry", f"{type(e).__name__}: {e}")
        return
    # WHAT THE RUN SELECTED, SINCE 2026-09-30. This checked every universe and
    # arm with tax artefacts on disk, at the default cadence and profile, under
    # the four-arm names. After `run.py --universe nifty50 --arm v2 --tax on` it
    # therefore checked files older runs had left and missed the one this run
    # wrote, v34_equity_v2_tax.csv. It now checks the (universe, arm) pairs that
    # runs finishing after --since selected with tax on, at their cadence and
    # profile, and fails if one of them did not write its files.
    #
    # EVERY ARM, SINCE 2026-09-26. This checked v2's column and v2's ledger only;
    # tax_report now writes a ledger per arm, and each is held to the same two
    # identities against that arm's own column of the taxed v34_equity.
    targets = _tax_targets(res, 6, since)
    if targets is None:
        return
    for rec, t, arm in targets:
        u = REGISTRY[t]
        col_name = arm.equity_column
        tn = f"{t}/{arm.name}"
        M = Path(u.metrics_dir)
        taxed, plain = _v34_equity_pair(M, rec, arm)
        # THE LEDGER IS NAMED EXACTLY, FOR THE CADENCE THIS GATE CHECKS. taxed is
        # the default-cadence, research, four-arm curve, so its ledger is v2's at
        # the same axes, named by the writer's own rule (backtest_runs.artefact_tag +
        # reports.artefact_name). This was `sorted(glob("FY_EQUITY_*_tax.csv"))[0]`
        # until 2026-09-23, and FY_EQUITY_<tag>_r10_tax.csv sorts before
        # FY_EQUITY_<tag>_tax.csv: one cadence-10 tax run made the gate compare
        # the cadence-10 ledger with the cadence-20 curve and fail by Rs 329,753.
        fy, stmt = _tax_ledger(u, M, arm, rec=rec)
        if not _written_by_run(res, 6, tn, (taxed, fy, stmt), rec, since):
            continue

        def col(path, name):
            with open(path, newline="") as fh:
                rows = list(csv.DictReader(fh))
            return [r for r in rows], rows[-1]

        trows, tlast = col(taxed, None)
        if col_name not in tlast:
            res.fail("GATE 6 tax", f"{tn} {taxed.name}",
                     f"no {col_name} column to check")
            continue
        t_final = float(tlast[col_name])

        with open(fy, newline="") as fh:
            fyr = list(csv.DictReader(fh))
        fy_final = float(fyr[-1]["close_equity"])

        # (i) EXACT, to a paisa.
        if abs(t_final - fy_final) > 0.01:
            res.fail("GATE 6 tax", f"{tn} taxed equity vs FY_EQUITY",
                     f"{taxed.stem} {arm.name} final Rs {t_final:,.2f} against "
                     f"FY_EQUITY close_equity Rs {fy_final:,.2f} -- two paths "
                     f"through the same engine disagree by Rs "
                     f"{abs(t_final-fy_final):,.2f}")
            continue

        if not plain.exists():
            res.note(f"GATE 6  {tn}: no untaxed {plain.name} to compare against, "
                     f"so only the FY_EQUITY identity was checked")
            continue
        with open(plain, newline="") as fh:
            prows = list(csv.DictReader(fh))
        p_final = float(prows[-1][col_name])

        with open(stmt, newline="") as fh:
            srows = list(csv.DictReader(fh))
        # ASSESSED ONLY, WHICH IS THE CASH THAT ACTUALLY LEFT THE BOOK. A row
        # with assessed=False is a liability section 3(9) charges after the
        # window closes; no cash was taken for it, so it cannot be inside an
        # equity difference measured at the final session. This is the figure
        # audit["tax"]["cum_tax"] holds and the only one the identity is true of.
        def _f(r, k):
            v = (r.get(k) or "").strip()
            return v.lower() in ("true", "1", "yes")
        assessed = sum(float(r["total_tax"]) for r in srows if _f(r, "assessed"))
        unassessed = sum(float(r["total_tax"]) for r in srows
                         if not _f(r, "assessed"))
        total = assessed + unassessed

        gap = p_final - t_final
        # (ii) AT LEAST, never equal -- see the docstring.
        if gap < assessed - 0.01:
            res.fail("GATE 6 tax", f"{tn} taxed equity vs ledger",
                     f"the taxed curve is only Rs {gap:,.2f} below the untaxed "
                     f"one, which is LESS than the Rs {assessed:,.2f} the ledger "
                     f"says was deducted. Tax was named but not charged.")
            continue
        res.note(f"GATE 6  {tn}: taxed equity == FY_EQUITY to a paisa; gap Rs "
                 f"{gap:,.2f} >= assessed Rs {assessed:,.2f} "
                 f"(compounding Rs {gap-assessed:,.2f}; statement total Rs "
                 f"{total:,.2f}, unassessed Rs {unassessed:,.2f})")


# ---------------------------------------------------------------------------
# GATE 7 -- the LTCG ceiling, watched rather than assumed
# ---------------------------------------------------------------------------

def gate_ltcg(res, sel, since=None):
    """HOLDING_PERIOD's claim about the long-term branch must match its lots.

    THIS GATE EXISTS BECAUSE ITS ABSENCE WAS MEASURED. costs.max_holding_days
    was written with the docstring "EXISTS SO A GATE CAN WATCH THE 326-DAY
    CEILING ... the failure mode is silent: the long-term rate simply starts
    applying and every tax figure moves." It then sat with ZERO CALL SITES for
    its whole life. The ceiling was crossed on 2026-09-18 -- nifty50 588 days,
    nifty100 443 days, four lots over the threshold -- and the failure mode was
    silent exactly as predicted, because the thing that was supposed to make
    noise had never been connected to anything.

    So the assertion here is deliberately the one the prose promised:

        any lot held more than twelve calendar months  =>  the artefact must SAY SO

    and it is asserted against `reports.holding_period`, the producer, not
    against a file. A file can be stale; the producer is what the next run will
    write. Checking the producer means the gate goes green the moment the code
    is right, and red the moment a hardcoded claim is reintroduced -- which is
    the specific regression that happened.

    WHAT IT DOES NOT DO. It does not assert that no lot crosses 365. Crossing is
    legitimate: the tax code routes long lots correctly and always did, and
    midcap150 and midcap50 are short-term only as a property of their windows.
    The defect was never the crossing. It was an artefact asserting one thing
    while its own adjacent column said another.

    NO --since. It reads lots that are already on disk and calls a pure
    function, so there is nothing to date. A universe with no tax artefacts is
    skipped and counted, not silently passed.
    """
    try:
        sys.path.insert(0, str(ROOT))
        sys.path.insert(0, str(ROOT / "results"))
        from settings import REGISTRY
        import pandas as pd
        import costs
        import reports as TR
    except Exception as e:
        res.fail("GATE 7 ltcg", "import", f"{type(e).__name__}: {e}")
        return

    # WITH --since, ONLY WHAT THE RUN WROTE, SINCE 2026-09-30. Without it this
    # reads every universe's lots on disk at the default axes, which is right
    # for a check of the tree. After a run it read lots older runs had left and
    # never the ones a non-default run wrote. With --since the (universe, arm)
    # pairs come from the runs that finished after it, as in gate 6.
    #
    # EVERY ARM, EACH FILE NAMED EXACTLY, SINCE 2026-09-26. This took the first
    # HOLDING_PERIOD_LOTS_*_tax.csv in sort order, which was v2's research file
    # only by the accident of "_tax" sorting before "_tradeable_tax" and "_v1_tax".
    # Each arm's lots are now named by the writer's rule (_tax_ledger) and checked.
    from portfolio import ALL_ARMS as _ARMS
    if since is None:
        tags = sorted(REGISTRY) if sel in (None, "all") else [t.strip() for t in sel.split(",")]
        items = [(None, t, a) for t in tags for a in _ARMS.values()]
    else:
        items = _tax_targets(res, 7, since)
        if items is None:
            return
    checked, stale = 0, []
    for rec, t0, arm in items:
        u = REGISTRY.get(t0)
        if u is None:
            continue
        t = f"{t0}/{arm.name}"
        lp, onf = _tax_ledger(u, Path(u.metrics_dir), arm,
                              ("HOLDING_PERIOD_LOTS", "HOLDING_PERIOD"), rec=rec)
        if rec is not None:
            if not _written_by_run(res, 7, t, (lp,), rec, since):
                continue
        elif not lp.exists():
            continue
        try:
            lots = read_table(lp)
        except Exception as e:
            res.fail("GATE 7 ltcg", f"{t} {lp.name}", f"{type(e).__name__}: {e}")
            continue
        if lots.empty:
            continue
        checked += 1

        mx = costs.max_holding_days(lots)          # THE CALL SITE. Do not remove it.
        # the count must come from the same predicate that routes the lot: held
        # more than twelve calendar months (costs.long_term_mask, 2026-10-14)
        routed = int(costs.long_term_mask(lots).sum())
        fires = routed > 0
        row = TR.holding_period(lots).iloc[0]
        note = str(row["note"]).lower()
        says_fires = "fires" in note
        says_not = "does not fire" in note

        if int(row["lots_long_term"]) != routed:
            res.fail("GATE 7 ltcg", f"{t} lots_long_term",
                     f"artefact counts {int(row['lots_long_term'])} long lots, the "
                     f"routing predicate (more than {costs.LTCG_HOLD_MONTHS} calendar "
                     f"months) finds {routed}. The count and the bucket disagree, "
                     f"which means LTCG may be charged at STCG rates or the reverse.")

        if fires and (says_not or not says_fires):
            res.fail("GATE 7 ltcg", f"{t} HOLDING_PERIOD note",
                     f"longest hold is {mx} days and {routed} lot(s) were held more "
                     f"than {costs.LTCG_HOLD_MONTHS} calendar months and took the long "
                     f"branch -- but the note still claims the branch does not "
                     f"fire:\n      {row['note']}\n"
                     f"      headroom_days={int(row['headroom_days'])} in the same "
                     f"row already contradicts it. Make the whole sentence "
                     f"computed; do not hardcode the claim beside a measured "
                     f"margin. See tax_report.holding_period.")
        elif not fires and says_fires:
            res.fail("GATE 7 ltcg", f"{t} HOLDING_PERIOD note",
                     f"no lot was held more than {costs.LTCG_HOLD_MONTHS} calendar months "
                     f"(longest {mx} days), but the note claims the branch fires:"
                     f"\n      {row['note']}")
        else:
            res.note(f"GATE 7  {t}: max hold {mx}d, "
                     f"{'FIRES' if fires else 'no fire'}, {routed} long lot(s), "
                     f"note agrees")

        # the file that is already on disk was written by an earlier run and may
        # predate a fix. Reported, never failed: no code change can turn it
        # green, only a re-run, and a gate that cannot be satisfied is ignored.
        # The summary file is named exactly too (onf above), so the old glob's
        # LOTS-sorts-first trap no longer applies.
        if onf.exists():
            try:
                disk = read_table(onf).iloc[0]
                dn = str(disk["note"]).lower()
                if (int(disk["lots_long_term"]) > 0) and \
                        "does not fire" in dn:
                    stale.append(f"{t}/{onf.name}")
            except Exception:
                pass

    if checked == 0 and since is None:
        res.skip(7, "GATE 7  SKIPPED -- no HOLDING_PERIOD_LOTS artefacts on "
                 "disk (a tax=off run writes none). Not counted as passed.",
                 "no HOLDING_PERIOD_LOTS artefacts on disk")
    if stale:
        res.note(f"GATE 7  NOTE, not a failure: {len(stale)} artefact(s) on disk "
                 f"still carry a pre-fix note string and will be corrected by the "
                 f"next taxed run -- {', '.join(stale)}")


# ---------------------------------------------------------------------------
# GATE 8 -- a published artefact must name the price data it was built from
# ---------------------------------------------------------------------------

# THE ARTEFACTS THAT PREDATE THE data_source FIELD. Listed 2026-09-20 with 18
# names; down to 16 on 2026-09-20 when midcap150 v3 and nifty100 v2 were re-run.
# The gate failed on both the moment they gained the field and named the lines to
# delete, which is the list working as intended rather than an incident.
#
# The field was added by 7dd37d6 on 2026-09-20. These 18 params files, across all
# eight universes, were written before it existed, so they carry no data_source and
# the gate failed all 18 on every run. That is 18 red lines that no commit can
# clear except re-running the artefact, and a gate that is permanently red is a
# gate nobody reads. The artefacts are not defective; the reporting was.
#
# NOTHING IS BACKFILLED AND NOTHING IS FORGIVEN. An exemption says only "this file
# predates the field", never "this file's provenance is known". It is still true
# that these 18 cannot say what price data produced them, and that is still a
# reason not to quote them. The remedy is unchanged: re-run the artefact.
#
# THE LIST ONLY SHRINKS. Re-running any of these writes a data_source, and the gate
# then FAILS on it for still being listed, naming the line to delete. A new
# artefact without the field is not on the list, so it fails the ordinary way. The
# count is asserted against the length of this tuple, so a name cannot be added
# here without the number moving in the same diff.
GATE8_EXEMPT = (
    # EMPTY SINCE 2026-09-24. The sixteen artefacts listed here predated the
    # data_source field; the 2026-09-24 republish rewrote all of them with it,
    # and the gate below fails any listed file that has gained the field.
)
GATE8_EXEMPT_N = 0           # asserted below; move it when the tuple moves


def gate_data_source(res, sel):
    """Every v34_params*.json must record a data source that is still current.

    WHAT THIS CATCHES, MEASURED RATHER THAN IMAGINED. midcap150's two tradeable
    artefacts were written 2026-09-17 01:20 from data/raw/MidCap150/clean. The
    universe was repointed at Final_Without_Survivorship_Data on 2026-09-18.
    Afterwards 33 of the 1,019 fills in daily_trades_midcap150_tradeable.csv named
    a (symbol, date) pair with no price row in the tree at all, and 34 more
    recorded a fill price the tree does not imply. All seven gates stayed green
    for three days, because not one of them opens a price file.

    WHY THE OTHER SEVEN COULD NOT HAVE CAUGHT IT. Gates 1, 2 and 3 are static:
    modules, a table, and ASTs. Gate 4 stats mtimes, so a run against the wrong
    source moves them exactly like a correct one. Gate 5 delegates to four naming
    and wiring checkers. Gates 6 and 7 compare artefacts against other artefacts
    from the same run, which is self-consistent by construction. The missing
    comparison is artefact against INPUT, and this is it.

    THE MECHANISM IS BORROWED, NOT INVENTED. model.write_cache_source and
    model._verified have recorded and enforced a cache's source since
    2026-09-19; the rule was correct and lived one layer too low, because
    _cache_owner() matches only score_cache and raw_cache. A
    daily_trades and a v34_params -- the files people read and quote -- were
    covered by nothing. This raises the same rule to the published artefact.

    IT FAILS CLOSED. A params file with no data_source is a FAILURE, not a skip:
    an artefact that cannot say what it was built from is exactly the state the
    tradeable cells were in, and treating silence as acceptable would re-admit it
    by default. Nothing is backfilled -- a source written in now for an artefact
    produced before the field existed would be a guess presented as provenance,
    which is worse than the gap. The remedy is to re-run the artefact.

    The gate SKIPS only when no params file exists at all, which is a tree with
    nothing to check rather than a check that declined.

    THE 18 EXEMPTIONS ARE A CLOSED LIST, NOT A PATTERN. GATE8_EXEMPT above names
    every artefact that predates the field. A file without data_source that is not
    on the list fails. A file on the list that has GAINED the field fails too, and
    says to delete the line -- so re-running an artefact shrinks the list and the
    gate insists on it. The list's length is pinned to GATE8_EXEMPT_N. A listed
    path that is ABSENT is not checked and not failed: a clean checkout never
    contains these files.
    """
    import json
    try:
        import model
        import settings
        from settings import REGISTRY
    except Exception as e:
        res.fail("GATE 8 data source", "registry",
                 f"{type(e).__name__}: {e}")
        return
    tags = sorted(REGISTRY) if sel in (None, "all") else [t.strip() for t in sel.split(",")]

    def name(f):
        """Repo-relative where possible, absolute otherwise. A metrics_dir outside
        ROOT is legal -- runs/ hard-links artefacts, and a test can point one at a
        scratch directory -- and relative_to() raises on exactly that, which would
        turn a reportable failure into a traceback from inside the gate."""
        try:
            return str(Path(f).relative_to(ROOT))
        except ValueError:
            return str(f)

    live = {}                      # tag -> fingerprint, computed at most once
    checked = 0
    exempt_used = set()            # listed paths that were seen, and had no field
    for t in tags:
        u = REGISTRY.get(t)
        if u is None:
            continue
        M = Path(u.metrics_dir)
        if not M.exists():
            continue
        # The stop arms' companion params files carry the same field.
        for f in sorted(list_dir(M, "v34_params*.json")
                        + list_dir(M, "v34_stop_params*.json")):
            checked += 1
            nm = name(f)
            try:
                doc = json.loads(f.read_text())
            except Exception as e:
                res.fail("GATE 8 data source", nm,
                         f"unreadable: {type(e).__name__}: {e}")
                continue
            rec = doc.get("data_source")
            if not isinstance(rec, dict):
                if nm in GATE8_EXEMPT:
                    # Predates the field. Listed, dated and counted, not forgiven:
                    # it still cannot say what produced it. Re-run it to clear it.
                    exempt_used.add(nm)
                    continue
                res.fail("GATE 8 data source", nm,
                         "no data_source field, so which price data produced this "
                         "artefact cannot be established. NOT BACKFILLED: a source "
                         "written in now would be a guess. Re-run the artefact.")
                continue
            if nm in GATE8_EXEMPT:
                res.fail("GATE 8 data source", nm,
                         "this artefact is on GATE8_EXEMPT but now HAS a "
                         "data_source, so it has been re-run since the list was "
                         "written. Delete its line from GATE8_EXEMPT in "
                         "check_all and reduce GATE8_EXEMPT_N by one. The list "
                         "is meant to shrink; leaving a cleared artefact on it "
                         "hides the next one that genuinely lacks the field.")
                continue
            # A PIT ARTEFACT was built from the universe's point-in-time variant, so
            # it is checked against that variant's data: the with-survivorship
            # folder and the pit farm. "_pit" is followed only by the axes after it:
            # drawdown limit, capital, impact, participation cap, fixed capital, start
            # ("v34_params_v3_tax_pit_dd20_cap5000000_impact0p003_pcap0p1_fixed_s20091214");
            # testing endswith("_pit") checked those against the static data.
            pit = re.search(r"_pit(_dd[0-9p]+(m[0-9p]+)?(f[0-9p]+)?)?(_cap[0-9]+)?"
                            r"(_impact[0-9p]+)?(_pcap[0-9p]+)?(_fixed)?(_s[0-9]{8})?$",
                            f.stem) is not None
            if (t, pit) not in live:
                from settings import pit_variant
                uu = pit_variant(u) if pit else u
                live[(t, pit)] = model.data_fingerprint(uu.prepare_data_dir(),
                                                         uu.raw_data_dir)
            cur = live[(t, pit)]
            for key in ("raw_data_dir", "link_target_dir", "digest"):
                a, b = rec.get(key), cur.get(key)
                if key != "digest" and a and b and not str(a).startswith("MIXED"):
                    a, b = model.root_relative(a), model.root_relative(b)
                if a != b:
                    res.fail("GATE 8 data source", name(f),
                             f"{key} MISMATCH -- this artefact describes data the "
                             f"universe no longer uses.\n"
                             f"          artefact  {rec.get(key)}\n"
                             f"          tree now  {cur.get(key)}\n"
                             f"      Every number in it is a number about the first "
                             f"and is filed under a universe that names the second.")
                    break
    if not checked:
        res.skip(8, "GATE 8  SKIPPED -- no v34_params*.json on disk, so there is "
                 "no published artefact to check. Not counted as passed.",
                 "no params artefacts on disk")
        return

    # AN EXEMPTION MEANS "NOT CHECKED", AND AN ABSENT EXEMPT FILE IS NOT A FAILURE.
    # Until 2026-09-23 a full scan failed if any listed path was missing. The
    # sixteen listed files predate the data_source field and cannot be
    # regenerated -- a re-run writes the field, and that fails the list below --
    # so a clean checkout could never contain them and GATE 8 could never pass on
    # one. Measured in the 2026-09-23 clean-room audit. The list still cannot
    # grow unnoticed: its length is pinned to GATE8_EXEMPT_N, and a listed file
    # that is present AND has gained the field still fails by name above.
    if len(GATE8_EXEMPT) != GATE8_EXEMPT_N:
        res.fail("GATE 8 exemptions", "check_all",
                 f"GATE8_EXEMPT holds {len(GATE8_EXEMPT)} names but "
                 f"GATE8_EXEMPT_N says {GATE8_EXEMPT_N}. The count exists so a "
                 f"name cannot be added without the number moving in the same "
                 f"diff. Set them equal deliberately.")
    absent = [x for x in GATE8_EXEMPT if not (ROOT / x).exists()]

    res.note(f"GATE 8  {checked} published artefact(s) checked against the "
             f"registry's current raw_data_dir and a sha256 over the whole input; "
             f"{len(exempt_used)} of {GATE8_EXEMPT_N} listed exemptions are on disk "
             f"without the field and were not checked, {len(absent)} are absent")


def _print_not_asserted(res):
    """Name every delegate that did not assert, immediately under the verdict.

    GATE 5's reason was "8 of 22 delegates did not assert" -- a count, and a
    count is what the Result docstring above calls a verdict line concealing
    what the body recorded. The full table still prints further up with the long
    reasons; this is the short form, and it travels with the headline so the
    headline cannot be quoted without it.
    """
    if not res.not_asserted:
        return
    w = max(len(l) for l, _s, _r in res.not_asserted)
    print(f"        GATE 5 DID NOT ASSERT ({len(res.not_asserted)}), BY NAME:")
    for label, status, short in sorted(res.not_asserted):
        print(f"          {label:<{w}}  {short}")


# CELLS NO GATE COVERS, NAMED UNDER EVERY VERDICT. A pit cell (run.py
# --survivorship pit) is outside nt_verify: the Nautilus port has no membership
# rule and no index exit, so it would be checked against a different strategy.
# KNOWN_ISSUES.md, "Pit cells are not covered by nt_verify".
NOT_COVERED = (
    ("nt_verify", "every pit cell (--survivorship pit), all universes and arms",
     "the Nautilus port has no membership rule or index exit"),
    ("nt_verify", "every --dd cell with tax on, the tradeable profile or pit",
     "the port has no tax ledger and no participation cap; nt_verify --dd checks "
     "static, research, tax-off cells only, and only when run by hand"),
)


def _print_not_covered():
    for gate, cells, why in NOT_COVERED:
        print(f"        NOT COVERED by {gate}: {cells} -- {why}")


def _print_not_selected(res):
    unit = {4: "steps"}
    for g, n in sorted(res.not_selected.items()):
        if n:
            print(f"        GATE {g} SKIPPED {n} {unit.get(g, 'universe/arm pairs')} "
                  f"not selected by this run; they are not counted as passed.")


def gate_raw_data():
    """GATE 0: the price data must match both tracked manifests before anything runs.

    Runs checks.py check_data and checks.py check_data --pit (both read-only). Returns the
    problem lines, MISSING, DIFFERENT or EXTRA with the file, plus each failing
    command's verdict line; an empty list means both passed.
    """
    problems = []
    for args in ([], ["--pit"]):
        r = subprocess.run([sys.executable, str(ROOT / "checks.py"), "check_data"] + args,
                           cwd=ROOT, capture_output=True, text=True)
        if r.returncode == 0:
            ok = [ln for ln in r.stdout.splitlines() if ln.startswith("PASS")]
            print(f"  GATE 0  check_data.py {' '.join(args)}".rstrip()
                  + f": {ok[0] if ok else 'exit 0'}")
            continue
        lines = r.stdout.splitlines()
        named = [ln.strip() for ln in lines
                 if ln.strip().split(" ", 1)[0] in ("MISSING", "DIFFERENT", "EXTRA")]
        verdict = [ln.strip() for ln in lines if ln.startswith("FAIL")]
        problems.append((" ".join(["check_data"] + args),
                         named + (verdict or [f"exit {r.returncode}: {r.stderr.strip()[-300:]}"])))
    return problems


def check_all(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since", type=float, default=None,
                    help="epoch seconds; gate 4 checks that steps wrote after it")
    # WHICH UNIVERSES TO CHECK in gate 8, and in gate 7 without --since. Gates
    # 4, 6 and 7 with --since take the selection from the run folders that
    # finished after it, because a bare --since after a subset run checked, and
    # failed, what that run never selected.
    ap.add_argument("--universe", default="all",
                    help="comma-separated tags for gate 8 and for gate 7 without "
                         "--since, or 'all'; with --since, gates 4, 6 and 7 read "
                         "the run's own selection from runs/")
    # THE REFIT DELEGATES ARE OFF BY DEFAULT. Without this flag they are
    # recorded as named skips, not as passes: validate_sizing is 1,134 LightGBM
    # fits per universe, which its own cost block measures at ~22.7 min.
    #
    # WHAT IT COSTS DEPENDS ON /tmp. The refit caches of validate_engine,
    # validate_sizing and validate_breadth_live carry seed_cache_key in their
    # names (code, raw panel content, universe, seeds; validate_breadth_live
    # since 2026-09-27), so a warm run reuses only fits made on the current code
    # and panel. They do not survive a reboot. A cold --slow run measured about
    # 2 h 40 min on 2026-09-27.
    ap.add_argument("--slow", action="store_true",
                    help="also run the delegates that refit the model "
                         "(validate_engine, validate_sizing, validate_breadth_live)")
    args = ap.parse_args(argv)

    res = Result()
    print("=" * 78)
    print(" checks.py -- an operation must not report success having done "
          "part of the work")
    print("=" * 78)
    # GATE 0 RUNS BEFORE EVERYTHING ELSE, because gates 5 and 8 rebuild the
    # constituent farms from data/raw/: a stray price file is linked in before
    # any later gate could object.
    raw = gate_raw_data()
    if raw:
        print("!" * 78)
        print("STOPPED AT GATE 0: data/raw/ does not match the tracked manifests. "
              "No other gate ran.")
        print("!" * 78)
        for cmd, lines in raw:
            print(f"\n  [{cmd}]")
            for ln in lines:
                print(f"      {ln}")
        print()
        return 1
    gate_imports(res)
    rows = gate_table(res)
    gate_entry_points(res, rows)
    gate_outputs(res, rows, args.since, args.universe)
    gate_delegates(res, args.slow)
    gate_tax(res, args.since, args.universe)
    gate_ltcg(res, args.universe, args.since)
    gate_data_source(res, args.universe)

    print()
    if res.delegates:
        print("  GATE 5 AND GATE 9 DELEGATES, ONE LINE EACH (GATE 9: "
              + ", ".join(LIVE_LIKE) + ")")
        w = max(len(d[0]) for d in res.delegates)
        for label, status, detail in res.delegates:
            print(f"    {status:<8}{label:<{w}}  {detail}")
        print()
    for n in res.notes:
        print("  " + n)
    print()
    if res.failures:
        print("!" * 78)
        print(f"FAILURES: {len(res.failures)}")
        print("!" * 78)
        for gate, what, detail in res.failures:
            print(f"\n  [{gate}]  {what}")
            if detail:
                print(f"      {detail}")
        print()
        _print_not_covered()
        return 1
    # THE VERDICT IS COMPUTED FROM THE SKIPS, NEVER TYPED. A constant string is
    # exactly what went wrong: it survived every skip the body recorded.
    n = len(ALL_GATES)
    assert n == 9, f"ALL_GATES holds {n} gates; the wording below says nine"
    ok = res.asserted()
    if res.skipped:
        # GROUPED BY REASON, because the common case is gates 4 and 6 skipping
        # for the identical reason and "GATE 4 -- need --since; GATE 6 -- need
        # --since" is a verdict line nobody finishes reading.
        by_reason = {}
        for g in sorted(res.skipped):
            by_reason.setdefault(res.skipped[g], []).append(g)
        parts = [f"{', '.join('GATE %d' % g for g in gs)} -- {why}"
                 for why, gs in by_reason.items()]
        print(f"RESULT: PASS ({len(ok)} of {n} asserted, "
              f"{len(res.skipped)} skipped: {'; '.join(parts)})")
        print(f"        ASSERTED: {', '.join('GATE %d' % g for g in ok)}")
        _print_not_selected(res)
        _print_not_covered()
        _print_not_asserted(res)
        print("        A SKIPPED GATE IS NOT A PASSED GATE. Exit code is 0 "
              "because a skip is legitimate,")
        print("        not because the work was done. --since <epoch> after a run "
              "asserts GATE 4 and GATE 6;")
        print("        GATE 5 never asserts in this runner (three delegates cannot; "
              "see the docstring).")
    else:
        print(f"RESULT: PASS -- all {n} gates asserted, none skipped")
        _print_not_selected(res)
        _print_not_covered()
        _print_not_asserted(res)
    return 0


def _cli_check_all():
    """`python checks.py check_all [ARGS]`: what running check_all.py did."""
    raise SystemExit(check_all())


# ======================================================================================
# check_data. From check_data.py (moved 2026-11-27).
# ======================================================================================
# check_data -- does your copy of the price data match the one the results were built on?
#
#     python3 checks.py check_data                                  # all eight universes
#     ./venv/bin/python checks.py check_data --universe=midcap50    # one universe's folder
#     python3 checks.py check_data --write                          # owner only: rewrite both manifests
#     python3 checks.py check_data --pit                            # the point-in-time inputs
#
# Run it after copying the price data into data/raw/ and before running anything
# else. It needs only the Python standard library, so it works before the venv is
# built. Exit 0 means every file the manifest lists is present with the same
# SHA-256, and no extra CSV sits in a folder the pipeline reads. Anything else
# exits 1 and names each file that is missing, different or extra.
#
# --universe=<tag> checks only that universe's folder, for a copy holding one
# universe. The folder comes from settings.py (the row's raw_data_dir), so
# this form needs the venv; the plain form needs only the standard library. An
# unknown tag exits 2 with the list of valid universes.
#
# WHY EXTRA FILES FAIL. A universe is defined by the CSVs in its supplier folder
# (settings.py builds each symbol list from the folder), so one extra
# constituent file changes that universe and every figure computed on it.
#
# WHAT IS COVERED. Only data/raw/Final_Without_Survivorship_Data/, the one folder
# the pipeline reads (every universe's raw_data_dir in settings.py is
# under it). Other folders under data/raw/ are not read by any pipeline step and
# are not in the manifest. The manifest has the sha256sum format, one
# "<sha256>  <path relative to the repository root>" line per file, sorted by path,
# so `shasum -a 256 -c data/RAW_DATA_SHA256.txt` checks it too (without the
# extra-file test).
#
# THE SECOND MANIFEST, 2026-10-10. data/RAW_DATA_SHA256_PIT.txt covers what only a
# --survivorship pit run reads: data/raw/Final_With_Survivorship_Data/ and the
# membership files in data/raw/Survivorship_Bias/. --pit checks it, and run.py
# checks the selected universes' part of it before a pit run starts (check_pit).
# The plain form still checks only the static manifest.

CHECK_DATA_MANIFEST = ROOT / "data" / "RAW_DATA_SHA256.txt"
COVERED = ROOT / "data" / "raw" / "Final_Without_Survivorship_Data"
PIT_MANIFEST = ROOT / "data" / "RAW_DATA_SHA256_PIT.txt"
PIT_COVERED = (ROOT / "data" / "raw" / "Final_With_Survivorship_Data",
               ROOT / "data" / "raw" / "Survivorship_Bias")
def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def on_disk():
    """Every file under COVERED, as repository-relative POSIX paths, sorted."""
    if not COVERED.is_dir():
        return []
    return sorted(p.relative_to(ROOT).as_posix() for p in list_dir(COVERED, recursive=True)
                  if p.is_file())


def read_manifest(manifest=CHECK_DATA_MANIFEST):
    out = {}
    for n, line in enumerate(manifest.read_text().splitlines(), 1):
        if not line.strip():
            continue
        digest, sep, rel = line.partition("  ")
        if not sep or len(digest) != 64:
            raise SystemExit(f"{manifest.name}:{n}: not '<sha256>  <path>': {line!r}")
        out[rel] = digest
    return out


def pit_on_disk():
    """Every file under PIT_COVERED, as repository-relative POSIX paths, sorted."""
    return sorted(p.relative_to(ROOT).as_posix() for d in PIT_COVERED if d.is_dir()
                  for p in list_dir(d, recursive=True) if p.is_file())


def write():
    files = on_disk()
    if not files:
        raise SystemExit(f"nothing to hash: {COVERED.relative_to(ROOT)} is missing or empty")
    lines = [f"{sha256(ROOT / f)}  {f}" for f in files]
    # naming: axis-free -- one fixed manifest of the static price files.
    CHECK_DATA_MANIFEST.write_text("\n".join(lines) + "\n")
    print(f"wrote {CHECK_DATA_MANIFEST.relative_to(ROOT)}: {len(lines)} files")
    pit = pit_on_disk()
    if pit:
        # naming: axis-free -- one fixed manifest of the pit input files.
        PIT_MANIFEST.write_text("\n".join(f"{sha256(ROOT / f)}  {f}" for f in pit) + "\n")
        print(f"wrote {PIT_MANIFEST.relative_to(ROOT)}: {len(pit)} files")
    return 0


def check_pit(tags=None):
    """The pit inputs against PIT_MANIFEST: every file, or only the with-survivorship
    folders and membership files of `tags`. 0 on a match, 1 otherwise."""
    if not PIT_MANIFEST.exists():
        print(f"FAIL -- {PIT_MANIFEST.relative_to(ROOT)} is missing from this checkout.")
        return 1
    want, have = read_manifest(PIT_MANIFEST), pit_on_disk()
    if tags is not None:
        sys.path.insert(0, str(ROOT))
        from settings import REGISTRY
        keep = []
        for t in tags:
            u = REGISTRY[t]
            keep.append(Path(u.survivorship_data_dir).resolve().relative_to(ROOT).as_posix() + "/")
            keep.append(Path(u.membership_file).resolve().relative_to(ROOT).as_posix())
        sel = lambda f: any(f == k or (k.endswith("/") and f.startswith(k)) for k in keep)
        want = {f: d for f, d in want.items() if sel(f)}
        have = [f for f in have if sel(f)]
    missing = sorted(f for f in want if f not in set(have))
    extra = sorted(f for f in have if f not in want)
    changed = [f for f in sorted(set(have) & set(want)) if sha256(ROOT / f) != want[f]]
    for label, items in (("MISSING", missing), ("DIFFERENT", changed), ("EXTRA", extra)):
        for f in items:
            print(f"  {label:<9} {f}")
    if missing or changed or extra:
        print(f"FAIL -- pit inputs: {len(missing)} missing, {len(changed)} different, "
              f"{len(extra)} extra, of {len(want)} files in "
              f"{PIT_MANIFEST.relative_to(ROOT)}.")
        return 1
    print(f"PASS -- all {len(want)} pit input files match "
          f"{PIT_MANIFEST.relative_to(ROOT)} and no extra file is present.")
    return 0


def _universe_folder(argv):
    """The one folder --universe=<tag> names, as a repository-relative prefix, or None."""
    vals = [a.split("=", 1)[1] for a in argv if a.startswith("--universe=")]
    if not vals:
        return None
    sys.path.insert(0, str(ROOT))
    from settings import REGISTRY, check_tags
    tag = check_tags(vals[-1:])[0]
    return Path(REGISTRY[tag].raw_data_dir).resolve().relative_to(ROOT).as_posix() + "/"


def not_covered():
    """(folder, bytes) for every folder under data/raw/ this check does not cover."""
    raw = ROOT / "data" / "raw"
    out = []
    for d in (p for p in list_dir(raw) if p.is_dir() and p != COVERED
              and p not in PIT_COVERED):
        out.append((d.name, sum(f.stat().st_size for f in list_dir(d, recursive=True) if f.is_file())))
    return out


def check_data_check(argv=()):
    if not CHECK_DATA_MANIFEST.exists():
        print(f"FAIL -- {CHECK_DATA_MANIFEST.relative_to(ROOT)} is missing from this checkout.")
        return 1
    want = read_manifest()
    have = on_disk()
    prefix = _universe_folder(argv)
    if prefix is not None:
        want = {f: d for f, d in want.items() if f.startswith(prefix)}
        have = [f for f in have if f.startswith(prefix)]
        print(f"  checking one folder: {prefix}")
    if not have:
        print(f"FAIL -- {prefix or (COVERED.relative_to(ROOT).as_posix() + '/')} is "
              "missing or empty. Copy the price data there first; see README, "
              "'The price data'.")
        return 1
    have_set = set(have)
    missing = sorted(f for f in want if f not in have_set)
    extra = sorted(f for f in have if f not in want)
    changed = []
    for i, f in enumerate(sorted(have_set & set(want)), 1):
        if sha256(ROOT / f) != want[f]:
            changed.append(f)
        if i % 250 == 0:
            print(f"  ... {i} files hashed", flush=True)
    for label, items in (("MISSING", missing), ("DIFFERENT", changed), ("EXTRA", extra)):
        for f in items:
            print(f"  {label:<9} {f}")
    if missing or changed or extra:
        print(f"FAIL -- {len(missing)} missing, {len(changed)} different, {len(extra)} "
              f"extra, of {len(want)} files in the manifest. Do not run the pipeline "
              "on this copy: its figures would not be the published ones.")
        return 1
    print(f"PASS -- all {len(want)} files match {CHECK_DATA_MANIFEST.relative_to(ROOT)} "
          "and no extra file is present.")
    extra_dirs = not_covered()
    if extra_dirs:
        print("  not checked, read by no pipeline step: "
              + ", ".join(f"data/raw/{n}/ ({b / 1e6:,.0f} MB)" for n, b in extra_dirs))
    print(f"  the pit inputs are checked by --pit against "
          f"{PIT_MANIFEST.relative_to(ROOT)}")
    return 0


def _cli_check_data():
    """`python checks.py check_data [ARGS]`: what running check_data.py did."""
    _a = sys.argv[1:]
    raise SystemExit(write() if "--write" in _a else check_pit() if "--pit" in _a
                     else check_data_check(_a))


# ======================================================================================
# code_checks. From code_checks.py (moved 2026-11-27).
# ======================================================================================
# code_checks -- four static and reconciliation checks, one subcommand each.
#
#     ./venv/bin/python checks.py code_checks <case> [the old file's arguments]
#
#     case                  was
#     stop_callsite         stop_callsite_check.py
#     transitional_asserts  transitional_asserts_check.py
#     platform_identity     platform_identity_check.py
#     cost_reconcile        cost_reconcile_check.py [--universe=<tag>[,<tag>...]]
#
# Merged on 2026-10-19. The old files last exist at commit b2742a1. Each old file's
# body is the function _<case> below, unchanged apart from one level of indentation
# (the inside of multi-line strings is left as it was), so a case runs only its own
# imports and constants. The case name is removed from sys.argv before the case
# runs, so each sees the arguments its old file saw.
#
# ONE EXCEPTION, SHARED CODE. stop_callsite_check imported tracked_py and SKIP from
# platform_identity_check. Both, with what they need (subprocess, Path, ROOT,
# MANIFEST), are at module level here, as they were in platform_identity_check;
# stop_callsite's body no longer has that import or the sys.path line that served
# it. Neither name is rebound anywhere.
#
# ONE CASE PER PROCESS. check_all runs every case as its own subprocess.

# ---------------------------------------------------------------------------
# shared by platform_identity and stop_callsite (was platform_identity_check.py)
# ---------------------------------------------------------------------------

CODE_CHECKS_MANIFEST = ROOT / "TRACKED_FILES_SHA256.txt"
SKIP = 3        # check_all reads this exit code as a named skip; the reason is the last line


def tracked_py():
    """-> (tracked .py paths, where the list came from), or (None, reason).

    `git ls-files` in a checkout. Outside one, the tracked-file checksum manifest
    (TRACKED_FILES_SHA256.txt, "<sha256>  <path>" per line), whose listed .py files
    must still have their recorded checksums. Neither: no list, and the reason."""
    try:
        r = subprocess.run(["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout.split(), "git ls-files"
    except FileNotFoundError:
        pass
    if not CODE_CHECKS_MANIFEST.exists():
        return None, (f"not a git checkout and no {CODE_CHECKS_MANIFEST.name}, so the tracked .py files "
                      f"cannot be listed")
    import hashlib
    files, changed = [], []
    for line in CODE_CHECKS_MANIFEST.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        digest, rel = line.split(None, 1)
        if rel.endswith(".py"):
            files.append(rel)
            f = ROOT / rel
            if not f.exists() or hashlib.sha256(f.read_bytes()).hexdigest() != digest:
                changed.append(rel)
    if changed:
        return None, (f"{len(changed)} .py file(s) differ from {CODE_CHECKS_MANIFEST.name}, first "
                      f"{changed[0]}; the manifest does not describe this tree")
    return files, CODE_CHECKS_MANIFEST.name


def _stop_callsite():
    """
stop_callsite_check.py -- no call site may pass an arm's mode and sizing and drop
its drawdown stop.

v5 is (none, invvol) plus the stop and v6 is (none, provol) plus the stop: the same
mode and sizing as v1 and v3. A call site that hands the engine `mode=a.mode,
sizing=a.sizing` runs v5 as v1 with nothing saying so. The stop travels in
Arm.kwargs, so the safe spelling is `**arm.kwargs`; a call that spells mode or
sizing out must also say what it does about the stop, `drawdown_stop=...`, even
when that is None.

THE RULE. The functions that take a stop are found from the source: every function
defined in a tracked file with a `drawdown_stop` parameter. A call to one of those
names fails when
  - it passes `mode=` or `sizing=` and neither `drawdown_stop=` nor `**<x>.kwargs`.
    Any other `**` mapping (the cap's, for instance) does not excuse it; or
  - it unpacks `**name`, and `name` is assigned, anywhere in the file, a dict
    display or dict(...) call that carries mode or sizing and no drawdown_stop.
Metadata dicts that are never unpacked into such a call are not looked at.

Exit 0 when clean, 1 with every offending file:line, 3 (a named skip in check_all)
when the tracked files cannot be listed.
"""
    import ast
    import sys
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent


    def stop_functions(trees):
        """Names of every function defined with a drawdown_stop parameter."""
        names = set()
        for tree in trees.values():
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    a = node.args
                    if any(x.arg == "drawdown_stop" for x in a.args + a.kwonlyargs + a.posonlyargs):
                        names.add(node.name)
        return names


    def _called_name(call):
        f = call.func
        if isinstance(f, ast.Attribute):
            return f.attr
        if isinstance(f, ast.Name):
            return f.id
        return None


    def _is_arm_kwargs(expr):
        return isinstance(expr, ast.Attribute) and expr.attr == "kwargs"


    def _dict_keys(node):
        """The constant keys of a dict display or a dict(...) call, else None."""
        if isinstance(node, ast.Dict):
            return {k.value for k in node.keys if isinstance(k, ast.Constant)}
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict":
            return {k.arg for k in node.keywords if k.arg is not None}
        return None


    def offences(tree, rel, targets):
        assigned = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                keys = _dict_keys(node.value)
                if keys is None:
                    continue
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        assigned.setdefault(t.id, []).append((node.lineno, keys))
        out = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and _called_name(node) in targets):
                continue
            name = _called_name(node)
            kw = {k.arg for k in node.keywords if k.arg is not None}
            stars = [k.value for k in node.keywords if k.arg is None]
            if ({"mode", "sizing"} & kw and "drawdown_stop" not in kw
                    and not any(_is_arm_kwargs(x) for x in stars)):
                out.append(f"{rel}:{node.lineno}  {name}(...) passes "
                           f"{', '.join(sorted({'mode', 'sizing'} & kw))} without drawdown_stop")
            for x in stars:
                if isinstance(x, ast.Name):
                    for line, keys in assigned.get(x.id, []):
                        if {"mode", "sizing"} & keys and "drawdown_stop" not in keys:
                            out.append(f"{rel}:{node.lineno}  {name}(**{x.id}) unpacks the dict "
                                       f"at line {line}, which has mode or sizing and no "
                                       f"drawdown_stop")
        return sorted(set(out), key=lambda t: int(t.split(":")[1].split()[0]))


    def main():
        files, source = tracked_py()
        if files is None:
            print(f"stop_callsite_check: SKIP -- {source}")
            return SKIP
        trees = {}
        for rel in files:
            p = ROOT / rel
            if p.exists():
                trees[rel] = ast.parse(p.read_text(), filename=str(p))
        targets = stop_functions(trees)
        if "backtest_exposure" not in targets:
            print("stop_callsite_check: backtest_exposure has no drawdown_stop parameter; "
                  "the check has nothing to anchor on")
            return 1
        bad = []
        for rel, tree in trees.items():
            bad += offences(tree, rel, targets)
        if bad:
            print(f"stop_callsite_check: {len(bad)} site(s) pass mode or sizing without the stop:")
            for b in bad:
                print(f"    {b}")
            return 1
        print(f"stop_callsite_check: {len(files)} files ({source}); every call to "
              f"{', '.join(sorted(targets))} that names mode or sizing also names "
              f"drawdown_stop or passes **kwargs")
        return 0

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main())


def _transitional_asserts():
    """transitional_asserts_check.py -- the tree says the collapse is unfinished.

IT STAYS, AND IT IS GREEN BECAUSE THE WORK LANDED, NOT BECAUSE IT STOPPED
CHECKING: reintroduce one literal REGISTRY["midcap150"] in a step that takes a
universe and it fails again, as "MARKER REMOVED, HARDCODING KEPT". Deleting
it would remove the only thing in the tree that would notice.

WHAT THIS EXISTS FOR. Step 2 of the collapse (commit 5c636cf) gave the eight
per-universe steps `main(u)` while leaving their literal `REGISTRY["midcap150"]` /
`REGISTRY["nifty100"]` subscripts in place, because check_pipeline_order resolves
`daily_*_{tag}.csv` to a directory by READING those literals and a loop variable
there matches nothing. The steps therefore ASSERT `u.tag` rather than using `u`.

That is a deliberate half-state, and a deliberate half-state that is recorded only
in a commit message or a conversation is indistinguishable, six days later, from a
finished one. This check makes the repository itself carry the fact. It FAILS --
non-zero exit -- for as long as any transitional assert survives.

IT CANNOT BE SILENCED BY DELETING THE MARKER. Three conditions are checked, and
the second is the one that matters:

  1. MARKER PRESENT              -> unfinished. Reported, and fatal.
  2. LITERAL WITHOUT MARKER      -> the marker was removed while the literal it
                                    describes is still there. FATAL, and reported
                                    as tampering rather than as progress.
  3. MARKER WITHOUT LITERAL      -> the collapse removed the literals but left the
                                    marker. FATAL: the marker is now a lie, and a
                                    stale warning is how a checker gets ignored.

So it goes green on exactly one state: no markers AND no literal REGISTRY[...]
subscripts in any step that takes a universe. That is the state steps 3-7 produce.

Run it directly, or read its exit code.
"""
    import ast
    import sys
    from pathlib import Path
    from settings import list_dir

    ROOT = Path(__file__).resolve().parent
    MARKER = "TRANSITIONAL-ASSERT"

    # WHAT "STILL HARDCODED" ACTUALLY MEANS, and it is wider than one syntax.
    # The first version of this looked for REGISTRY["midcap150"] as a regex, and got two
    # things wrong at once. It matched its OWN marker comment -- which names the
    # subscript it warns about -- so a genuinely collapsed file still reported one. And
    # it MISSED the engines and the charts, which do not spell it that way: the engines
    # alias the import (`from universes.registry import REGISTRY as _REG`, then
    # _REG["midcap150"]) and the charts reach their universe through `import config_<tag>`.
    # A check that passes four of eight files for a spelling reason is worse than none.
    #
    # The condition is not a syntax. It is: THIS STEP STILL KNOWS ITS UNIVERSE BY NAME.
    # So it is tested as that -- any string constant in main() that IS a registry tag,
    # plus any module-level import of that universe's config. ast is used rather than
    # text so comments are invisible, which is what let the first version report a
    # literal that was only being described.
    #
    # REGISTRY[u.tag], REGISTRY[tag] and u.metrics_dir are all invisible here: their
    # slices are not string constants and they name no universe. That is the collapsed
    # form, and reaching it is exactly what turns this check green.
    def _hardcoded(fn, tree, tags):
        """The registry tags this step still names for itself, in code."""
        out = {n.value for n in ast.walk(fn)
               if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value in tags}
        for node in ast.walk(tree):                     # module level: import config_<tag>
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for nm in names:
                for t in tags:
                    if nm.split(".")[0] == f"config_{t}":
                        out.add(t)
        return sorted(out)


    def _takes_universe(src, path, fname="main"):
        """True when this file's module-level function `fname` declares one argument.

    The same ast read run.py._declared_arity does, and for the same reason: a step
    is not imported to find out how it is invoked.
    """
        for node in ast.parse(src, filename=str(path)).body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fname:
                a = node.args
                return len(a.posonlyargs) + len(a.args) + len(a.kwonlyargs) == 1
        return False


    def scan():
        """Every step that takes a universe, with its marker and hardcoding state."""
        sys.path.insert(0, str(ROOT))
        from settings import REGISTRY
        tags = set(REGISTRY)
        rows = []
        # THE PIPELINE STEPS ARE FUNCTIONS since 2026-11-27, in backtest_runs.py and
        # reports.py (backtest_runs.STEP_HOME); the two Nautilus steps are still their
        # file's main(). Every step function that takes a universe is scanned.
        import backtest_runs
        steps = dict.fromkeys(row[1] for row in backtest_runs.PIPELINE_ORDER)
        for p, fname in (backtest_runs.step_source(s) for s in steps):
            src = p.read_text()
            if not _takes_universe(src, p, fname):
                continue
            # THE __main__ GUARD'S OWN SUBSCRIPT IS NOT A DEFECT. It supplies the
            # argument for a direct `run.py --universe midcap150 --steps pipeline`, which
            # is how these are run by hand, and it survives the collapse as
            # REGISTRY[sys.argv[1]] or equivalent. Only main() itself is scanned.
            tree = ast.parse(src, filename=str(p))
            fn = next(n for n in tree.body
                      if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                      and n.name == fname)
            # The marker is a COMMENT, so ast cannot see it; it is read from the
            # source lines main() spans.
            lines = src.splitlines()[fn.lineno - 1:fn.end_lineno]
            rows.append((Path(f"{p}::{fname}"), any(MARKER in l for l in lines),
                         _hardcoded(fn, tree, tags)))
        return rows


    def main():
        rows = scan()
        marked = [r for r in rows if r[1]]
        untagged = [r for r in rows if not r[1] and r[2]]
        stale = [r for r in rows if r[1] and not r[2]]

        print("=" * 78)
        print(" TRANSITIONAL ASSERT CHECK -- is the collapse finished?")
        print("=" * 78)
        print(f"  steps taking a universe : {len(rows)}")
        print(f"  carrying the marker     : {len(marked)}")
        print()

        if marked:
            print(f"  UNFINISHED ({len(marked)}) -- these still name their own universe:")
            for p, _, lits in sorted(marked):
                print(f"    {p.relative_to(ROOT)!s:<34} names {', '.join(lits) or '?'}")
            print()
        if untagged:
            print(f"  MARKER REMOVED, HARDCODING KEPT ({len(untagged)}) -- this is not progress:")
            for p, _, lits in sorted(untagged):
                print(f"    {p.relative_to(ROOT)!s:<34} names {', '.join(lits)}")
            print()
        if stale:
            print(f"  STALE MARKER ({len(stale)}) -- nothing is hardcoded; remove the marker:")
            for p, _, _ in sorted(stale):
                print(f"    {p.relative_to(ROOT)!s}")
            print()

        if marked or untagged or stale:
            print("RESULT: FAIL -- the collapse (steps 3-7 of the new order) is unfinished.")
    
            return 1

        print("RESULT: PASS -- no transitional asserts remain; the collapse is complete.")
        print("  THIS CHECK IS NOT RETIRED BY THAT. It is green because the collapse")
        print("  landed, not because it stopped checking: reintroduce one literal and")
        print("  it reports MARKER REMOVED, HARDCODING KEPT and exits non-zero again.")
        return 0

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main())


def _platform_identity():
    """
platform_identity_check.py -- two operations that give different bits on
different platforms are allowed only through their shared replacements.

RULE 1: every CSV read goes through market_data.read_table.

pandas' default read_csv float parser returns different last bits for the same
bytes on macOS and on Linux, and on either platform does not return the values
the file was written from (measured 2026-09-24; see market_data.read_table). One
such read anywhere on the pipeline path is enough to make two machines
disagree. This check parses every tracked .py file and fails on:

    <anything>.read_csv(...)         a direct pandas call
    from pandas import read_csv      the same call under another name

The one allowed site is market_data.read_table itself.

RULE 2: no pandas rolling or grouped variance. `.rolling(...).std()`,
`.rolling(...).var()`, `.groupby(...).std()/.var()` and `.transform("std")` or
`.transform("var")` gave different bits on macOS, Linux arm64 or Linux amd64
(measured 2026-09-24; see market_data.py). Use market_data.rolling_std,
market_data.rolling_var or market_data.group_mean_std.

Exit 0 when clean, 1 with every offending file:line otherwise, 3 (a named skip in
check_all) when the tracked files cannot be listed: outside a git checkout with no
TRACKED_FILES_SHA256.txt, or with one that no longer matches the tree.
"""
    import ast
    import sys

    ALLOWED = {("market_data.py", "read_table")}


    def offences(path, rel):
        tree = ast.parse(path.read_text(), filename=str(path))
        out = []

        def visit(node, fn=None):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn = node.name
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "read_csv" and (rel, fn) not in ALLOWED):
                out.append(f"{rel}:{node.lineno}  .read_csv( call")
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("std", "var")
                    and isinstance(node.func.value, ast.Call)
                    and isinstance(node.func.value.func, ast.Attribute)
                    and node.func.value.func.attr in ("rolling", "groupby", "expanding")):
                out.append(f"{rel}:{node.lineno}  .{node.func.value.func.attr}(...).{node.func.attr}() -- use numerics")
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "transform" and node.args
                    and isinstance(node.args[0], ast.Constant) and node.args[0].value in ("std", "var")):
                out.append(f"{rel}:{node.lineno}  .transform({node.args[0].value!r}) -- use numerics.group_mean_std")
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("pandas"):
                if any(a.name == "read_csv" for a in node.names):
                    out.append(f"{rel}:{node.lineno}  imports read_csv from pandas")
            for child in ast.iter_child_nodes(node):
                visit(child, fn)

        visit(tree)
        return out


    def main():
        files, source = tracked_py()
        if files is None:
            print(f"platform_identity_check: SKIP -- {source}")
            return SKIP
        bad = []
        for rel in files:
            bad += offences(ROOT / rel, rel)
        if bad:
            print(f"platform_identity_check: {len(bad)} call(s) bypass the shared implementations:")
            for b in bad:
                print(f"    {b}")
            return 1
        print(f"platform_identity_check: {len(files)} files ({source}), every CSV read goes through "
              f"config.read_table and no pandas rolling or grouped variance is used")
        return 0

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main())


def _cost_reconcile():
    """cost_reconcile_check.py -- the cost reconciliation on every cell, profile and tax setting.

    ./venv/bin/python cost_reconcile_check.py [--universe=<tag>[,<tag>...]]

A check_all delegate. For each registered universe, each arm, the research and
tradeable profiles, and tax off and on, at the default cadence: run the backtest
with the cost trail and apply reports.reconcile_costs -- cash every day,
slippage and charges every fill, tax every financial year, and the totals; and
the investable buy & hold, held and sold on the last day, per universe. Writes
nothing. Exits 1 at the end if any combination failed, naming each with the check,
the first day and the gap; 0 if all reconcile.
"""
    import os
    for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        os.environ[_v] = "1"
    import sys
    import time
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent
    for _p in (ROOT, ROOT / "results"):
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))

    import model
    import settings                                                    # noqa: E402
    import reports as cost_report                                               # noqa: E402
    import market_data                                               # noqa: E402
    import costs
    import settings                                                  # noqa: E402
    import portfolio as arm_reg                                  # noqa: E402
    from market_data import read_table                                    # noqa: E402
    from market_data import precompute                               # noqa: E402
    from portfolio import backtest_exposure, START_CAPITAL       # noqa: E402
    from settings import REGISTRY, argv_universes, check_tags  # noqa: E402

    KEYS = ("holdings", "summary", "trades", "ranking", "decisions", "skipped")


    def cell(u, arm, panel, profile, tax_on):
        px, op, sc, bd, pc, mom20 = panel
        settings.profile_axis.set_selection(profile)
        try:
            audit = {k: [] for k in KEYS}
            audit["costs"] = {"fills": [], "days": []}
            _eq, tc, _n, _ = backtest_exposure(px, op, sc, bd, pc, mom20, audit=audit,
                                               tax_enabled=tax_on,
                                               **arm.kwargs, **costs.cap_kwargs(u))
        finally:
            settings.profile_axis.set_selection(None)
        tx = audit.get("tax")
        cost_report.reconcile_costs(audit["costs"], audit["trades"], list(bd), float(START_CAPITAL), tc,
                              float(tx["cum_tax"]) if tx else 0.0, tax_on,
                              tx["lots"] if tx else None)
        return len(audit["trades"])


    def main(argv):
        picked = check_tags(argv_universes(argv), REGISTRY) or list(REGISTRY)
        failed, n, t0 = [], 0, time.time()
        for tag in picked:
            u = REGISTRY[tag]
            market_data.set_tradeability(u)
            p = read_table(model.require_cache(u.score_cache, what=tag), parse_dates=["date"])
            px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
            op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
            sc = p.pivot_table(index="date", columns="symbol", values="score")
            panel = (px, op, sc, u.trading_days(px.index), precompute(px), px / px.shift(20) - 1)
            for tax_on in (False, True):
                what = f"{tag} buy & hold tax {'on' if tax_on else 'off'}"
                try:
                    cost_report.bh_costs(px, op, panel[3], float(START_CAPITAL), tax_on)
                    print(f"  PASS  {what}", flush=True)
                except cost_report.CostReconciliationError as e:
                    failed.append(f"{what}: {e}")
                    print(f"  FAIL  {what:<36} {e}", flush=True)
                n += 1
            for arm in arm_reg.ARMS.values():
                for profile in settings.profile_axis.PROFILES:
                    for tax_on in (False, True):
                        what = f"{tag} {arm.name} {profile} tax {'on' if tax_on else 'off'}"
                        try:
                            fills = cell(u, arm, panel, profile, tax_on)
                            print(f"  PASS  {what:<36} {fills:>5} fills", flush=True)
                        except cost_report.CostReconciliationError as e:
                            failed.append(f"{what}: {e}")
                            print(f"  FAIL  {what:<36} {e}", flush=True)
                        n += 1
        print(f"\n{n - len(failed)} of {n} combinations reconcile "
              f"({(time.time() - t0) / 60:.1f} min)")
        for f in failed:
            print(f"  FAILED {f}")
        return 1 if failed else 0

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main(sys.argv[1:]))


CODE_CHECKS_CASES = {"stop_callsite": _stop_callsite, "transitional_asserts": _transitional_asserts,
         "platform_identity": _platform_identity, "cost_reconcile": _cost_reconcile}


def _cli_code_checks():
    """`python checks.py code_checks [ARGS]`: what running code_checks.py did."""
    if len(sys.argv) < 2 or sys.argv[1] not in CODE_CHECKS_CASES:
        print(__doc__)
        sys.exit(2)
    _case = CODE_CHECKS_CASES[sys.argv[1]]
    sys.argv = [sys.argv[0]] + sys.argv[2:]
    _case()


# ======================================================================================
# engine_tests. From engine_tests.py (moved 2026-11-27).
# ======================================================================================
# engine_tests -- the eleven synthetic and cache tests, one subcommand each.
#
#     ./venv/bin/python checks.py engine_tests <case> [the old file's arguments]
#
#     case                   was
#     capital_axis           capital_axis_test.py [--quiet]
#     dd_overlay             dd_overlay_test.py [--quiet]
#     drawdown_stop          drawdown_stop_test.py [--quiet]
#     fixed_capital          fixed_capital_test.py [--quiet]
#     impact_pcap_axis       impact_pcap_axis_test.py [--quiet]
#     tax_rules              tax_rules_test.py [--quiet]
#     tax_total              tax_total_test.py [--quiet] [--module PATH]
#     tradability_causality  tradability_causality_test.py [--quiet] [--real]
#     cache_key              cache_key_test.py
#     buy_shortfall          (new, 2026-10-27)
#     fill_open_sizing       (new, 2026-10-28)
#     fill_price             (new, 2026-10-28)
#
# Merged on 2026-10-18. The old files last exist at commit 24614bb. Each old file's
# body is the function _<case> below, unchanged apart from one level of indentation
# (the inside of multi-line strings is left as it was): its imports, sys.path setup,
# warnings filter and constants run only when that case is chosen, as they did when
# the file was run on its own. The file's `if __name__ == "__main__":` block is the
# last statement of its function. Each function's docstring is the old file's.
#
# ONE CASE PER PROCESS. check_all runs every case as its own subprocess, as it ran
# the old files. Do not call two cases in one interpreter: cache_key changes the
# state of modules it imports, and the other cases read sys.argv for their own flags.
#
# noise_harness was retired on 2026-11-26 with results/noise_parallel.py,
# results/price_noise_measure.py and results/after_tax_noise.py, and cache_key lost
# the cases that tested those three. They last exist at commit dbe387e.

def _capital_axis():
    """
capital_axis_test.py -- the starting-capital axis on a synthetic panel.

    ./venv/bin/python capital_axis_test.py          # every case, with its figures
    ./venv/bin/python capital_axis_test.py --quiet  # PASS/FAIL lines only

    1. validation: whole rupees, at least Rs 1,00,000
    2. names: "" at the default, "_cap<rupees>" and "@cap<rupees>" otherwise
    3. the default path: unset, and start_capital=1,000,000 passed, give the same curve
    4. the engine starts at the selected capital and reconciles to the paisa
       (reports.reconcile_costs replays cash, charges and slippage fill by fill)
    5. the investable buy & hold (bh_held) is bought with the selected capital
    6. the one definition: every START_CAPITAL name is capital_axis.DEFAULT

No data, nothing written. Exit 0 when every case passes, 1 otherwise.
"""
    import sys
    import warnings
    from pathlib import Path

    warnings.filterwarnings("ignore")
    ROOT = Path(__file__).resolve().parent
    for _p in (ROOT, ROOT / "results", ROOT / "nautilus"):
        sys.path.insert(0, str(_p))

    import numpy as np
    import pandas as pd

    from settings import capital_axis
    import reports as cost_report
    from market_data import precompute
    from portfolio import backtest_exposure

    QUIET = "--quiet" in sys.argv
    RESULTS = []
    SYMS = [f"S{k:02d}" for k in range(12)]
    WARM = pd.bdate_range("2020-08-03", "2020-12-31")
    DATES = pd.bdate_range("2021-01-01", "2021-12-31")


    def case(name, ok, detail=""):
        RESULTS.append(bool(ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail and not QUIET else ""))


    def panel():
        idx = WARM.append(DATES)
        f = np.cumprod(np.r_[1.0, np.full(len(idx) - 1, 1.0007)])
        px = pd.DataFrame({s: 100.0 * f * (1 + 0.01 * k) * (1 + 0.002 * np.sin(np.arange(len(idx)) / (k + 3)))
                           for k, s in enumerate(SYMS)}, index=idx)
        sc = pd.DataFrame({s: float(len(SYMS) - k) for k, s in enumerate(SYMS)}, index=idx)
        return px, px.copy(), sc


    def run(px, op, sc, **kw):
        audit = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
        audit["costs"] = {"fills": [], "days": []}
        eq, tc, n, _ = backtest_exposure(px, op, sc, DATES, precompute(px), px / px.shift(20) - 1,
                                         mode="none", sizing="invvol", audit=audit, rebal=20,
                                         participation_cap=None, drawdown_stop=None, **kw)
        return eq, tc, audit


    def main():
        # 1 ----------------------------------------------------------------------
        bad = []
        for v in (99_999, 2.5, 0, -1):
            try:
                capital_axis.set_selection(v)
                bad.append(v)
            except ValueError:
                pass
        capital_axis.set_selection(100_000)
        ok_min = capital_axis.selected() == 100_000
        capital_axis.set_selection(None)
        case("1 validation: below Rs 1 lakh or not whole rupees is refused", not bad and ok_min,
             f"accepted wrongly: {bad}")

        # 2 ----------------------------------------------------------------------
        names_default = (capital_axis.suffix(), capital_axis.segment(), capital_axis.label())
        capital_axis.set_selection(5_000_000)
        names_on = (capital_axis.suffix(), capital_axis.segment())
        capital_axis.set_selection(None)
        case("2 names", names_default == ("", "", "") and names_on == ("_cap5000000", "@cap5000000"),
             f"default {names_default}, at 5,000,000 {names_on}")

        # 3 ----------------------------------------------------------------------
        px, op, sc = panel()
        e0, _, _ = run(px, op, sc)
        e1, _, _ = run(px, op, sc, start_capital=1_000_000)
        case("3 default path: unset equals start_capital=1,000,000", bool((e0 == e1).all()))

        # 4 ----------------------------------------------------------------------
        capital_axis.set_selection(5_000_000)
        try:
            e5, tc5, a5 = run(px, op, sc)
            cost_report.reconcile_costs(a5["costs"], a5["trades"], list(DATES), 5_000_000.0, tc5, 0.0, False)
            ok = abs(a5["costs"]["days"][0]["cash_open"] - 5_000_000) < 0.005
            case("4 engine starts at the selected capital and reconciles", ok,
                 f"first cash {a5['costs']['days'][0]['cash_open']:,.2f}, final {e5.iloc[-1]:,.2f} "
                 f"(Rs 10 lakh run final {e0.iloc[-1]:,.2f})")
        finally:
            capital_axis.set_selection(None)

        # 5 ----------------------------------------------------------------------
        import backtest_runs as bh_held
        bd = DATES
        r1 = bh_held.held_lots(px, op, bd)
        capital_axis.set_selection(3_000_000)
        try:
            r3 = bh_held.held_lots(px, op, bd)
        finally:
            capital_axis.set_selection(None)
        q1 = sum(q for q, _ in r1["shares"].values())
        q3 = sum(q for q, _ in r3["shares"].values())
        case("5 buy & hold is bought with the selected capital", 2.9 * q1 < q3 < 3.1 * q1,
             f"shares at Rs 10 lakh {q1:,}, at Rs 30 lakh {q3:,}")

        # 6 ----------------------------------------------------------------------
        # The same six constants, named: engine_core's and nt_attribution's now sit in
        # this file under their tool's prefix.
        import portfolio
        import market_data
        import backtest_runs as engine_v2_final
        import reports as make_daily_log
        import nautilus_port as nt_run
        vals = {"portfolio": portfolio.START_CAPITAL,
                "engine_core": ENGINE_CORE_START_CAPITAL,
                "engine_v2_final": engine_v2_final.START_CAPITAL,
                "make_daily_log": make_daily_log.START_CAPITAL,
                "nt_attribution": NT_ATTRIBUTION_START_CAPITAL,
                "nt_run": nt_run.START_CAPITAL}
        case("6 every START_CAPITAL is capital_axis.DEFAULT",
             all(v == capital_axis.DEFAULT for v in vals.values()), str(vals))

        print(f"\n  {sum(RESULTS)} of {len(RESULTS)} passed")
        return 0 if all(RESULTS) else 1

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main())


def _dd_overlay():
    """
dd_overlay_test.py -- the drawdown-limit axis on a synthetic panel.

    ./venv/bin/python dd_overlay_test.py          # every case, with its figures
    ./venv/bin/python dd_overlay_test.py --quiet  # PASS/FAIL lines only

The axis adds the engine's only partial sells and its only top-ups of held names
(portfolio.py). Each case builds a price path that reaches one
behaviour, runs portfolio.backtest_exposure with an explicit
dd_overlay and an audit dict, and asserts on the fills. Every case also passes the
cost trail through reports.reconcile_costs, which replays cash, charges,
slippage and the tax ledger fill by fill and raises on a paisa of difference.

    1. no drawdown                 no dd fill, equity identical to the axis off
    2. a dip inside the band       no dd fill
    3. a crash                     next-open trims, every name by the same ratio
    4. the recovery                top-ups, every name by the same ratio, back to
                                   within 1 point of the arm's 98%
    5. participation cap on a trim the remainder stays held, k is what filled
    6. no open price on the trim day   that name is skipped, the rest are trimmed
    7. the floor                   invested fraction within the band of F
    8. an overnight gap            the limit is breached and the summary says so
    9. tax on                      trims realise gains, the ledger reconciles, the
                                   marginal tax is positive
   10. refusal with a stop arm

The rebalance cadence is longer than the panel, so the only trades after the first
morning are the overlay's. No real data, nothing written. Exit 0 when every case
passes, 1 otherwise.
"""
    import sys
    import warnings
    from pathlib import Path

    warnings.filterwarnings("ignore")
    ROOT = Path(__file__).resolve().parent
    for _p in (ROOT, ROOT / "results"):
        sys.path.insert(0, str(_p))

    import numpy as np
    import pandas as pd

    from settings import dd_axis
    from portfolio import DrawdownStop
    from market_data import precompute
    from portfolio import backtest_exposure, START_CAPITAL
    import reports as cost_report

    QUIET = "--quiet" in sys.argv
    SYMS = [f"S{k:02d}" for k in range(12)]
    WARM = pd.bdate_range("2020-08-03", "2020-12-31")
    DATES = pd.bdate_range("2021-01-01", "2021-12-31")
    REBAL = 10_000
    DD20 = dd_axis.make(20)                      # L 20%, m 5, floor 25%


    def panel(path):
        """`path(t)` is the day-t multiplier on the common price, t indexing DATES."""
        idx = WARM.append(DATES)
        n0 = len(WARM)
        f = np.ones(len(idx))
        for t in range(n0, len(idx)):
            f[t] = f[t - 1] * path(t - n0)
        px = pd.DataFrame({s: 100.0 * f * (1 + 0.01 * k) for k, s in enumerate(SYMS)}, index=idx)
        sc = pd.DataFrame({s: float(len(SYMS) - k) for k, s in enumerate(SYMS)}, index=idx)
        return px, px.copy(), sc


    def run(px, op, sc, dd=DD20, cap=None, vol20=None, tax=False, stop=None):
        audit = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions",
                                 "skipped")}
        audit["costs"] = {"fills": [], "days": []}
        eq, tc, n, _ = backtest_exposure(px, op, sc, DATES, precompute(px), px / px.shift(20) - 1,
                                         mode="none", sizing="invvol", audit=audit, rebal=REBAL,
                                         participation_cap=cap, vol20=vol20, tax_enabled=tax,
                                         dd_overlay=dd, drawdown_stop=stop)
        engine_tax = float(audit["tax"]["cum_tax"]) if tax else 0.0
        lots = audit["tax"]["lots"] if tax else None
        cost_report.reconcile_costs(audit["costs"], audit["trades"], list(DATES), float(START_CAPITAL),
                              tc, engine_tax, tax, lots)
        fills = pd.DataFrame(audit["costs"]["fills"])
        return eq, audit, fills


    def dd_fills(fills, kind=None):
        if not len(fills):
            return fills
        f = fills[fills["kind"].str.startswith("dd")]
        return f[f["kind"] == kind] if kind else f


    def holdings_on(audit, d):
        h = pd.DataFrame(audit["holdings"])
        h = h[h["date"] == d]
        return dict(zip(h["symbol"], h["qty"]))


    def proportional(audit, fills, kind):
        """Every dd fill of `kind` on each day resizes its name by the ordered ratio:
    qty == floor(held at the previous close x |1 - r|), r from the order event."""
        orders = [e for e in audit["dd_events"] if e["event"].endswith("order")]
        days = sorted(set(dd_fills(fills, kind)["date"]))
        bad = []
        for d in days:
            i = DATES.get_loc(d)
            prev = DATES[i - 1]
            ev = [e for e in orders if e["date"] == prev][-1]
            r = ev["target_invested_pct"] / ev["invested_pct"]
            held = holdings_on(audit, prev)
            for _, f in dd_fills(fills, kind)[dd_fills(fills, kind)["date"] == d].iterrows():
                want = int(np.floor(held[f["symbol"]] * abs(1 - r)))
                if int(f["qty"]) != want:
                    bad.append((d, f["symbol"], int(f["qty"]), want))
        return days, bad


    RESULTS = []


    def case(name, ok, detail=""):
        RESULTS.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail and not QUIET else ""))


    def crash_path(day=40, crash=0.82, rec_from=None, rec=1.01):
        def p(t):
            if t == day:
                return crash
            if rec_from is not None and t >= rec_from:
                return rec
            return 1.001 if t < day else 0.999
        return p


    def main():
        # 1. no drawdown: rising prices, the overlay must be inert
        px, op, sc = panel(lambda t: 1.001)
        eq_on, a1, f1 = run(px, op, sc)
        eq_off, _, _ = run(px, op, sc, dd=None)
        case("1 no drawdown: no dd fill and equity identical to the axis off",
             len(dd_fills(f1)) == 0 and bool((eq_on == eq_off).all()),
             f"dd fills {len(dd_fills(f1))}, max |diff| {float((eq_on - eq_off).abs().max()):.6f}")

        # 2. a 1% dip: E = 5 x (0.99 - 0.80) / 0.99 = 0.96, so k* = 0.96 / 0.98 and the
        #    invested fraction would move about 2 points, inside the 5-point band. Near
        #    a peak E moves about 4 points per 1% of drawdown at m = 1 / L, so a 2% dip
        #    is already outside it.
        px, op, sc = panel(lambda t: 0.995 if t in (30, 31) else 1.0005)
        _, a2, f2 = run(px, op, sc)
        case("2 a 1% dip stays inside the 5-point band", len(dd_fills(f2)) == 0,
             f"worst dd {a2['dd']['worst_dd_pct']:.2f}%, dd fills {len(dd_fills(f2))}")

        # 3. a crash of 18% on day 40: trims at the next open, proportional
        px, op, sc = panel(crash_path())
        _, a3, f3 = run(px, op, sc)
        days, bad = proportional(a3, f3, "dd trim")
        first = DATES[41]
        case("3 crash: trims fill at the next open, every name by the ordered ratio",
             len(days) > 0 and days[0] == first and not bad,
             f"trim days {[str(d.date()) for d in days[:3]]}, mismatches {bad[:3]}")
        s3 = pd.DataFrame(a3["summary"]).set_index("date")
        ev = [e for e in a3["dd_events"] if e["event"] == "trim order"][0]
        W, M = ev["equity"], ev["peak"]
        E = max(0.25, min(1.0, 5 * (W - 0.8 * M) / W))
        case("3 the target exposure is max(F, min(1, m (W - (1 - L) M) / W))",
             abs(ev["limit_exposure_pct"] / 100 - E) < 1e-12,
             f"E {ev['limit_exposure_pct'] / 100:.4f}, recomputed {E:.4f}, invested after "
             f"{s3.loc[first, 'invested_pct']:.2f}%")

        # 4. recovery by three jumps (+25%, +25%, +10%): the limit rises faster than
        #    the drift of the trimmed book, so top-ups fill. A smooth recovery mostly
        #    re-risks by drift alone: the invested fraction rises with prices about as
        #    fast as E does, and the gap stays inside the band.
        px, op, sc = panel(lambda t: {40: 0.82, 60: 1.25, 70: 1.25, 80: 1.10}.get(
            t, 1.001 if t < 40 else 1.0))
        _, a4, f4 = run(px, op, sc)
        days4, bad4 = proportional(a4, f4, "dd top-up")
        s4 = pd.DataFrame(a4["summary"]).set_index("date")
        case("4 recovery: top-ups by the ordered ratio, back to the arm's own level",
             len(days4) >= 2 and not bad4 and a4["dd"]["invested_final_pct"] >= 97
             and s4["invested_pct"].iloc[-1] > 95,
             f"top-up days {len(days4)}, mismatches {bad4[:3]}, "
             f"invested at the end "
             f"{s4['invested_pct'].iloc[-1]:.2f}%")

        # 5. participation cap on the trim: 50 shares a day per name, from day 30 so
        #    the first morning's buys are not cut
        px, op, sc = panel(crash_path())
        vol20 = {s: {d: 500.0 for d in DATES[30:]} for s in SYMS}
        _, a5, f5 = run(px, op, sc, cap=0.10, vol20=vol20)
        t5 = dd_fills(f5, "dd trim")
        capped = [r for r in a5["skipped"] if r["reason"] == "participation cap"
                  and r["detail"].startswith("dd trim")]
        first_day = t5[t5["date"] == t5["date"].min()]
        case("5 cap on a trim: each sale is 50 sh, the rest stays held and is re-ordered",
             len(capped) > 0 and (first_day["qty"] == 50).all() and len(set(t5["date"])) > 1,
             f"capped legs {len(capped)}, first-day sizes {sorted(set(first_day['qty']))}, "
             f"trim days {len(set(t5['date']))}")

        # 6. no open on the trim day for S00
        px, op, sc = panel(crash_path())
        op.loc[DATES[41], "S00"] = np.nan
        _, a6, f6 = run(px, op, sc)
        t6 = dd_fills(f6, "dd trim")
        d6 = t6[t6["date"] == DATES[41]]
        skipped = [r for r in a6["skipped"] if r["reason"].startswith("dd trim: no open")]
        case("6 no open price: that name is skipped, the others are trimmed",
             "S00" not in set(d6["symbol"]) and len(d6) > 0 and len(skipped) == 1,
             f"trimmed {len(d6)} names on {DATES[41].date()}, skipped {[r['symbol'] for r in skipped]}")

        # 7. the floor: a 30% crash puts W below the limit; E is held at 25%
        px, op, sc = panel(crash_path(crash=0.70))
        _, a7, f7 = run(px, op, sc)
        s7 = pd.DataFrame(a7["summary"]).set_index("date")
        after = s7.loc[DATES[42]:, "invested_pct"]
        # The floor bounds E. The book itself may drift below it by up to the band
        # before a top-up is ordered.
        case("7 floor: days at the floor counted, invested within the band of F",
             a7["dd"]["days_at_floor"] > 0 and after.min() > 25 - 5 - 0.5,
             f"days at floor {a7['dd']['days_at_floor']}, min invested after the trim "
             f"{after.min():.2f}%")

        # 8. an overnight gap: 15% down, the trim, then a 35% gap the next session
        def gap(t):
            return {40: 0.85, 45: 0.65}.get(t, 1.001 if t < 40 else 1.0)
        px, op, sc = panel(gap)
        _, a8, _ = run(px, op, sc)
        d8 = a8["dd"]
        case("8 gap: the limit is breached and the summary reports it",
             d8["breached"] and d8["breach_points"] > 0 and d8["sessions_below_limit"] > 0,
             f"worst {d8['worst_dd_pct']:.2f}% on {pd.Timestamp(d8['worst_date']).date()}, "
             f"breached by {d8['breach_points']:.2f} points, sessions below {d8['sessions_below_limit']}")

        # 9. tax on: rise 40%, then crash; trims realise gains
        def taxed(t):
            return 1.003 if t < 120 else (0.80 if t == 120 else 1.0)
        px, op, sc = panel(taxed)
        _, a9, f9 = run(px, op, sc, tax=True)
        case("9 tax on: dd trims in the ledger, cost replay reconciles, marginal tax > 0",
             len(dd_fills(f9, "dd trim")) > 0 and a9["dd"]["marginal_tax"] > 0,
             f"dd trims {len(dd_fills(f9, 'dd trim'))}, marginal tax Rs {a9['dd']['marginal_tax']:,.2f}, "
             f"total tax Rs {float(a9['tax']['cum_tax']):,.2f}")

        # 10. refusal with a stop arm
        try:
            run(px, op, sc, stop=DrawdownStop(threshold=0.15, cooldown_cycles=1,
                                              reentry_breadth=0.5))
            ok = False
        except ValueError as e:
            ok = "stop arm" in str(e)
        case("10 the axis is refused on a stop arm", ok)

        n = len(RESULTS)
        print(f"\n  {sum(RESULTS)} of {n} passed")
        return 0 if all(RESULTS) else 1

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main())


def _drawdown_stop():
    """
drawdown_stop_test.py -- the drawdown stop's edge cases on a synthetic panel.

    ./venv/bin/python drawdown_stop_test.py          # every case, with its log rows
    ./venv/bin/python drawdown_stop_test.py --quiet  # PASS/FAIL lines only

experiments/DRAWDOWN_STOP_PREREG.txt and section 3 of the approved design list how
the stop behaves at its edges. A run on real prices reaches only some of them, so
each one is built here on purpose: twelve symbols, one common price path, scores
fixed by name, and a crash placed on the day the case needs. Each case runs
portfolio.backtest_exposure with an audit dict and asserts on its
stop events, skipped orders and fills. The cases without a cap or tax also run
checks.nt_attribution_run, the reference copy nt_verify compares the port with,
and require the same exit and re-entry dates.

    1. exit signal on a rebalance day       the order placed at that close is superseded
    2. exit sale cut by the participation cap   the remainder is held and offered again
    3. no open price on the exit day          the name stays held and is offered again
    4. exit on the tax assessment day         the sale is taxed with its own year
    5. exit on the penultimate and last day   sells at the last open / sells nothing
    6. re-entry where no buy fills            back to waiting, peak not reset
    7. breadth below 0.50                     the arm stays in cash until it recovers

No real data, no cache, nothing written. A second or two. Exit 0 when every case
passes, 1 otherwise.
"""
    import os
    import sys
    import warnings
    from pathlib import Path

    warnings.filterwarnings("ignore")
    ROOT = Path(__file__).resolve().parent
    for _p in (ROOT, ROOT / "results", ROOT / "nautilus"):
        sys.path.insert(0, str(_p))

    import numpy as np
    import pandas as pd

    from portfolio import DrawdownStop
    from market_data import precompute
    from portfolio import backtest_exposure

    QUIET = "--quiet" in sys.argv
    # 0.15, NOT THE REGISTERED 0.20, which is sealed. The synthetic crashes are 25%, so
    # every case triggers as it would at 0.20.
    STOP = DrawdownStop(threshold=0.15, cooldown_cycles=1, reentry_breadth=0.50)
    REBAL = 5
    SYMS = [f"S{k:02d}" for k in range(12)]
    WARM = pd.bdate_range("2020-08-03", "2020-12-31")
    DATES = pd.bdate_range("2021-01-01", "2021-06-30")


    def panel(crash_at, recover_at=None, crash=0.75):
        """Prices: flat to `crash_at` (an index into DATES), then x `crash` on that day,
    drifting down 0.5% a day until `recover_at`, then rising 1% a day."""
        idx = WARM.append(DATES)
        n0 = len(WARM)
        f = np.ones(len(idx))
        for t in range(n0 + crash_at, len(idx)):
            f[t] = f[t - 1] * (crash if t == n0 + crash_at else 0.995)
            if recover_at is not None and t >= n0 + recover_at:
                f[t] = f[t - 1] * 1.01
        px = pd.DataFrame({s: 100.0 * f * (1 + 0.01 * k) for k, s in enumerate(SYMS)}, index=idx)
        op = px.copy()
        sc = pd.DataFrame({s: float(len(SYMS) - k) for k, s in enumerate(SYMS)}, index=idx)
        return px, op, sc


    def run(px, op, sc, cap=None, vol20=None, tax=False, dates=DATES):
        audit = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions",
                                 "skipped")}
        audit["costs"] = {"fills": [], "days": []}
        eq, *_ = backtest_exposure(px, op, sc, dates, precompute(px), px / px.shift(20) - 1,
                                   mode="none", sizing="invvol", drawdown_stop=STOP,
                                   audit=audit, rebal=REBAL, participation_cap=cap,
                                   vol20=vol20, tax_enabled=tax)
        ev = pd.DataFrame(audit["stop_events"])
        return eq, audit, ev


    def reference_events(px, op, sc, dates=DATES):
        out = []
        nt_attribution_run(px, op, sc, dates, precompute(px), px / px.shift(20) - 1,
                           mode="none",
                           sizing="invvol", rebal=REBAL, drawdown_stop=STOP,
                           stop_events_out=out)
        return out


    KEY = ("trigger", "exit fills", "flat", "re-entry order", "re-entry filled",
           "re-entry not filled", "peak reset", "trigger on the last session")


    def key_dates(rows):
        return sorted((str(pd.Timestamp(r["date"]).date()), r["event"]) for r in rows
                      if r["event"] in KEY)


    def show(title, ev, extra=None):
        if QUIET:
            return
        print(f"\n  {title}")
        cols = ["date", "event", "state", "peak", "equity", "drawdown_pct", "breadth", "detail"]
        for _, r in ev[cols].iterrows():
            print(f"    {str(pd.Timestamp(r['date']).date())}  {r['event']:<27} {r['state']:<12}"
                  f" dd {r['drawdown_pct'] if pd.notna(r['drawdown_pct']) else '':>9}"
                  f"  breadth {r['breadth'] if pd.notna(r['breadth']) else '':>6}  {r['detail']}")
        for line in extra or []:
            print(f"    {line}")


    RESULTS = []


    def check(name, ok, why=""):
        RESULTS.append((name, ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" -- {why}" if why and not ok else ""))


    def skipped_on(audit, day, reason=None):
        return [r for r in audit["skipped"] if r["date"] == day
                and (reason is None or r["reason"] == reason)]


    def window(ev, first, last):
        d = pd.to_datetime(ev["date"])
        return ev[(d >= first) & (d <= last)]


    def case_1():
        k = 30                                   # DATES index 30 is a rebalance day (30 % 5 == 0)
        px, op, sc = panel(k)
        _, audit, ev = run(px, op, sc)
        day = DATES[k]
        sup = [d for d in audit["decisions"] if d["decided_on"] == day]
        show("1. exit signal on a rebalance day", window(ev, day, DATES[k + 1]),
             [f"decision row of {day.date()}: superseded = {sup[0].get('superseded') if sup else None}"])
        names = list(window(ev, day, day)["event"])
        check("1. exit on a rebalance day supersedes that close's order",
              names == ["order superseded", "trigger"] and sup and sup[0].get("superseded") == "drawdown exit",
              f"events {names}")
        check("1. reference copy has the same exit and re-entry dates",
              key_dates(ev.to_dict("records")) == key_dates(reference_events(px, op, sc)))


    def case_2():
        k = 31
        px, op, sc = panel(k)
        fill_day = DATES[k + 1]
        big = {s: {d: 1e9 for d in px.index} for s in SYMS}
        big["S00"][fill_day] = 10.0              # the cap allows 10 shares of S00 that morning
        _, audit, ev = run(px, op, sc, cap=1.0, vol20=big)
        caps = skipped_on(audit, fill_day, "participation cap")
        sells = [t for t in audit["trades"] if t["date"] in (fill_day, DATES[k + 2])
                 and t["symbol"] == "S00"]
        show("2. exit sale cut by the participation cap", window(ev, DATES[k], DATES[k + 2]),
             [f"skipped {fill_day.date()}: {c['side']} {c['symbol']} {c['reason']} [{c['detail']}]"
              for c in caps]
             + [f"trade {t['date'].date()}: SELL {t['symbol']} {t['qty']:,} sh at {t['price']:,.2f}"
                for t in sells])
        names = list(ev["event"])
        i = names.index("exit partly filled")
        check("2. a capped exit sale leaves the remainder held and offers it again",
              len(caps) == 1 and names[i + 1] == "exit retried" and "flat" in names[i + 1:i + 4]
              and [t["qty"] for t in sells][0] == 10 and len(sells) == 2,
              f"events {names[i:i + 4]}, sells {[t['qty'] for t in sells]}")


    def case_3():
        k = 31
        px, op, sc = panel(k)
        fill_day = DATES[k + 1]
        op.loc[fill_day, "S03"] = np.nan
        _, audit, ev = run(px, op, sc)
        miss = skipped_on(audit, fill_day, "no open price (NaN/<=0)")
        later = [t for t in audit["trades"] if t["symbol"] == "S03" and t["date"] == DATES[k + 2]]
        show("3. no open price on the exit day", window(ev, DATES[k], DATES[k + 2]),
             [f"skipped {fill_day.date()}: {c['side']} {c['symbol']} {c['reason']}" for c in miss]
             + [f"trade {t['date'].date()}: SELL {t['symbol']} {t['qty']:,} sh" for t in later])
        names = list(window(ev, fill_day, DATES[k + 2])["event"])
        check("3. a name with no open stays held and is sold at the next open",
              len(miss) == 1 and len(later) == 1
              and names == ["exit fills", "exit partly filled", "exit retried", "exit fills", "flat"],
              f"events {names}")
        check("3. reference copy has the same exit and re-entry dates",
              key_dates(ev.to_dict("records")) == key_dates(reference_events(px, op, sc)))


    def case_4():
        assess = pd.Timestamp("2021-03-31")      # FY2020-21's assessment day
        k = list(DATES).index(assess) - 1        # trigger the close before, sell on it
        px, op, sc = panel(k, crash=0.75)
        # A GAIN TO TAX: every price is 60% higher from day 10 on, so the exit after the
        # 25% crash still sells above cost and realises a short-term gain.
        n0 = len(WARM)
        px.iloc[n0 + 10:] *= 1.60
        op = px.copy()
        _, audit, ev = run(px, op, sc, tax=True)
        tax_rows = [r for r in audit["skipped"] if r["side"] == "TAX" and r["date"] == assess]
        sells = [t for t in audit["trades"] if t["date"] == assess and t["action"] == "SELL"]
        lots = audit["tax"]["lots"]
        sold = lots[pd.to_datetime(lots["sell_date"]) == assess] if "sell_date" in lots else lots.iloc[0:0]
        show("4. exit on the tax assessment day", window(ev, DATES[k], assess),
             [f"{len(sells)} exit sale(s) on {assess.date()}"]
             + [f"skipped {r['date'].date()}: TAX {r['reason']} [{r['detail']}]" for r in tax_rows])
        check("4. an exit on 31 March is taxed after the day's fills, with its own year",
              len(sells) > 0 and len(tax_rows) == 1 and "after this day's fills" in tax_rows[0]["detail"],
              f"{len(sells)} sales, tax rows {[r['detail'] for r in tax_rows]}")


    def case_5():
        n = len(DATES)
        px, op, sc = panel(n - 2)                # trigger at the penultimate close
        _, audit, ev = run(px, op, sc)
        last = DATES[-1]
        sells = [t for t in audit["trades"] if t["date"] == last and t["action"] == "SELL"]
        show("5a. exit triggered on the penultimate day", window(ev, DATES[-2], last),
             [f"{len(sells)} sale(s) at the last open, {last.date()}"])
        names = list(window(ev, DATES[-2], last)["event"])
        check("5a. a trigger at the penultimate close sells at the last open",
              names == ["trigger", "exit fills", "flat"] and len(sells) > 0, f"events {names}")
        px, op, sc = panel(n - 1)                # trigger at the last close
        _, audit, ev = run(px, op, sc)
        sells = [t for t in audit["trades"] if t["date"] == last and t["action"] == "SELL"]
        show("5b. exit triggered on the last day", window(ev, last, last),
             [f"{len(sells)} sale(s) on {last.date()}"])
        names = list(window(ev, last, last)["event"])
        check("5b. a trigger at the last close sells nothing",
              names == ["trigger on the last session"] and not sells, f"events {names}")
        check("5. reference copy has the same exit and re-entry dates",
              key_dates(ev.to_dict("records")) == key_dates(reference_events(px, op, sc)))


    def case_6_7():
        k = 31
        px, op, sc = panel(k, recover_at=k + 25)
        _, audit, ev = run(px, op, sc)
        order = ev[ev["event"] == "re-entry order"]
        waiting = ev[ev["event"] == "waiting"]
        show("7. breadth below 0.50 keeps the arm in cash",
             ev[ev["event"].isin(["flat", "cooldown", "waiting", "re-entry order"])].head(12))
        check("7. breadth below 0.50 holds the arm in cash until breadth recovers",
              len(waiting) >= 2 and (waiting["breadth"] < 0.5).all() and len(order)
              and pd.to_datetime(order["date"]).iloc[0] > pd.to_datetime(waiting["date"]).max()
              and float(order["breadth"].iloc[0]) >= 0.5,
              f"{len(waiting)} waits, first order {list(order['date'][:1])}")
        check("7. reference copy has the same exit and re-entry dates",
              key_dates(ev.to_dict("records")) == key_dates(reference_events(px, op, sc)))
        first = pd.Timestamp(order["date"].iloc[0])
        fill = DATES[list(DATES).index(first) + 1]
        op2 = op.copy()
        op2.loc[fill, :] = np.nan                # no symbol has an open on the re-entry morning
        _, audit2, ev2 = run(px, op2, sc)
        miss = skipped_on(audit2, fill, "no open price (NaN/<=0)")
        show("6. re-entry where no buy fills", window(ev2, first, DATES[list(DATES).index(first) + 6]),
             [f"skipped {fill.date()}: {len(miss)} BUY order(s), reason no open price"])
        after = window(ev2, fill, DATES[-1])
        names = list(after["event"])
        reset_before = (ev2["event"] == "peak reset") & (pd.to_datetime(ev2["date"]) <= fill)
        check("6. a re-entry with no fill goes back to waiting without a peak reset",
              names[0] == "re-entry not filled" and after.iloc[0]["state"] == "OUT"
              and not reset_before.any() and "re-entry filled" in names,
              f"events {names[:4]}")
        check("6. reference copy has the same exit and re-entry dates",
              key_dates(ev2.to_dict("records")) == key_dates(reference_events(px, op2, sc)))


    def main():
        for c in (case_1, case_2, case_3, case_4, case_5, case_6_7):
            c()
        bad = [n for n, ok in RESULTS if not ok]
        print(f"\nRESULT: {'PASS' if not bad else 'FAIL'} -- {len(RESULTS) - len(bad)} of "
              f"{len(RESULTS)} checks" + (f"; failed: {', '.join(bad)}" if bad else ""))
        return 1 if bad else 0

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main())


def _fixed_capital():
    """
fixed_capital_test.py -- the fixed-capital axis (settings.fixed_axis).

    ./venv/bin/python fixed_capital_test.py          # every case, with its figures
    ./venv/bin/python fixed_capital_test.py --quiet  # PASS/FAIL lines only

    1. names and refusals: "" and "_fixed" / "@fixed"; the engine and run.py refuse
       the axis with --dd and with the stop arms v5 and v6
    2. the default path: fixed_capital unset and fixed_capital=False give the same run
    a. purchases never lift invested value above the book: on every execution day,
       after all fills, valued at that open, held value <= max(book, held value
       before that day's buys), where book = min(base, portfolio value at that
       open after the morning's sells and tax). This is the rule the engine
       follows since 557de05. The open value is cash before the buys (cash after
       the buys plus each rebalance buy's fill value and charges, from
       audit["costs"]) plus held value before the buys. On days with a reserve
       the test also checks that reserve = open value - base. nifty200, pit,
       tradeable, v1 to v4, tax off and on
   b1. nifty500 v4, pit, tradeable, tax off and on: the fixed and compounded runs
       are identical, every fill, cash and equity value, up to the session before
       the first execution day whose open equity is above the base. That day is
       found from the run.
   b2. a synthetic falling panel on which equity never passes the base: the two
       runs are identical over the whole window, v1 and v4, tax off and on
    c. every run above reconciles from its own fills: end equity = base + realised
       P&L + final unrealised P&L - charges - tax, within Rs 1. Realised P&L is on
       average cost; prices and charges come from the run's full-precision cost
       trail (audit["costs"]). The yearly table is checked as well, as a format
       check only: base + the sum of the yearly rupee P&L = end equity, in Decimal.

The real-data cases read the cached pit score panels (cache/), as the engines do;
nothing under data/ is read or written by this file, and nothing is written at all.
Exit 0 when every case passes, 1 otherwise.
"""
    import contextlib
    import io
    import sys
    import warnings
    from pathlib import Path

    warnings.filterwarnings("ignore")
    ROOT = Path(__file__).resolve().parent
    for _p in (ROOT, ROOT / "results", ROOT / "nautilus", ROOT / "tools"):
        sys.path.insert(0, str(_p))

    import numpy as np
    import pandas as pd

    from settings import fixed_axis
    import backtest_runs as fc
    from market_data import precompute
    from portfolio import backtest_exposure

    QUIET = "--quiet" in sys.argv
    RESULTS = []
    BASE = 1_000_000.0
    TOL_RS = 1.0          # case c
    TOL_BOOK = 0.01       # case a: rupees of float rounding in a sum over held names


    def case(name, ok, detail=""):
        RESULTS.append(bool(ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail and not QUIET else ""),
              flush=True)


    def blank():
        a = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
        a["costs"] = {"fills": [], "days": []}
        return a


    # ---------------------------------------------------------------------------
    # case c: reconcile a run from its own fills
    # ---------------------------------------------------------------------------
    def reconcile(audit, eq, px, base):
        """(gap in rupees, realised, unrealised, charges, tax) for one run."""
        held, cost = {}, {}
        realised = charges = 0.0
        for f in audit["costs"]["fills"]:
            s, q, p = f["symbol"], f["qty"], f["fill_price"]
            charges += f["charges"]
            if f["side"] == "BUY":
                cost[s] = cost.get(s, 0.0) + q * p
                held[s] = held.get(s, 0) + q
            else:
                avg = cost[s] / held[s]
                realised += q * (p - avg)
                cost[s] -= q * avg
                held[s] -= q
                if held[s] == 0:
                    del held[s], cost[s]
        last = px.loc[eq.index[-1]]
        unrealised = sum(q * float(last[s]) - cost[s] for s, q in held.items()
                         if not np.isnan(last.get(s, np.nan)))
        tax = float(audit["tax"]["cum_tax"]) if "tax" in audit else 0.0
        gap = base + realised + unrealised - charges - tax - float(eq.iloc[-1])
        return gap, realised, unrealised, charges, tax


    RECONCILED = []


    def check_c(label, audit, eq, px, base=BASE):
        gap, r, u, c, t = reconcile(audit, eq, px, base)
        fmt_ok = fc.yearly_sum_check(eq, base)
        RECONCILED.append((label, abs(gap) <= TOL_RS and fmt_ok, gap, r, u, c, t, fmt_ok))


    # ---------------------------------------------------------------------------
    # real-data cells
    # ---------------------------------------------------------------------------
    def select_pit(tag):
        """The selections a `run.py --survivorship pit --profile tradeable --tax on`
        run makes, and the universe's membership loaded as run._pit_setup loads it."""
        import costs
        from settings import survivorship_axis, tax
        import settings
        import market_data
        import market_data
        from settings import REGISTRY, use_pit
        survivorship_axis.set_selection("pit")
        settings.profile_axis.set_selection("tradeable")
        tax.set_selection(True)
        use_pit([tag])
        u = REGISTRY[tag]
        m = market_data.load(u.membership_file, index_name=u.tag, price_dir=u.raw_data_dir,
                    allow_invalid=True)
        market_data.PIT_MEMBERSHIPS[tag] = m
        market_data.MEMBERSHIP = market_data.membership_for(u)
        market_data.set_tradeability(u)
        return u

    class Cell:
        """One pit, tradeable universe, loaded as run.py --survivorship pit
    --profile tradeable loads it (select_pit below; it was
    tools/pit_noise_band.select_pit until 2026-11-26)."""

        def __init__(self, tag):
            import model
            import settings
            import costs
            from market_data import read_table
            with contextlib.redirect_stdout(io.StringIO()):
                self.u = u = select_pit(tag)
                p = read_table(model.require_cache(u.score_cache, what=f"{tag} pit"),
                               parse_dates=["date"])
            self.px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
            self.op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
            self.sc = p.pivot_table(index="date", columns="symbol", values="score")
            self.bd = u.trading_days(self.px.index)
            self.pc = precompute(self.px)
            self.mom20 = self.px / self.px.shift(20) - 1
            with contextlib.redirect_stdout(io.StringIO()):
                self.capkw = costs.cap_kwargs(u)

        def run(self, arm, tax, fixed):
            import portfolio as ar
            a = ar.ARMS[arm]
            audit = blank()
            with contextlib.redirect_stdout(io.StringIO()):
                eq, tc, n, _ = backtest_exposure(
                    self.px, self.op, self.sc, self.bd, self.pc, self.mom20, rebal=20, tax_enabled=tax, audit=audit,
                    mode=a.mode, sizing=a.sizing, drawdown_stop=None, dd_overlay=None,
                    fixed_capital=fixed, start_capital=int(BASE), **self.capkw)
            return eq, audit


    def open_value(r, au):
        """Portfolio value at the fill open, after the morning's sells and tax and
        before the buys: cash before the buys plus held value before the buys."""
        bought = sum(f["qty"] * f["fill_price"] + f["charges"] for f in au["costs"]["fills"]
                     if f["date"] == r["date"] and f["side"] == "BUY"
                     and f["kind"] == "rebalance")
        return r["cash_after"] + bought + r["held_before_buys"]


    def open_book(r, au):
        """The fixed-capital book at the fill open: min(base, open value)."""
        return min(BASE, open_value(r, au))


    def case_a():
        C = Cell("nifty200")
        worst, n_days, n_res, n_short = [], 0, 0, 0
        for arm in ("v1", "v2", "v3", "v4"):
            for tax in (False, True):
                eq, au = C.run(arm, tax, True)
                rows = au["fixed"]
                books = [open_book(r, au) for r in rows]
                over = [r for r, b in zip(rows, books)
                        if r["held_after"] > max(b, r["held_before_buys"]) + TOL_BOOK]
                neg = [r for r in rows if r["cash_after"] < 0]
                bad_res = [r for r in rows if r["reserve"] > 0
                           and abs(r["reserve"] - (open_value(r, au) - BASE)) > TOL_BOOK]
                n_days += len(rows)
                n_res += sum(1 for r in rows if r["reserve"] > 0)
                n_short += sum(1 for s in au["skipped"] if "fixed-capital reserve" in s["detail"])
                margin = max(r["held_after"] - max(b, r["held_before_buys"])
                             for r, b in zip(rows, books))
                worst.append((arm, tax, len(over), margin))
                case(f"a nifty200 pit tradeable {arm} tax {'on' if tax else 'off'}: purchases "
                     f"never lift invested value above the book",
                     not over and not neg and not bad_res and len(rows) > 0,
                     f"{len(rows)} execution days, {len(over)} over, {len(neg)} with negative "
                     f"cash, {len(bad_res)} with a reserve that is not open value - base; "
                     f"largest held_after - max(book, held before) Rs {margin:,.2f}; "
                     f"reserve > 0 on {sum(1 for r in rows if r['reserve'] > 0)} days")
                check_c(f"nifty200 {arm} tax {'on' if tax else 'off'} fixed", au, eq, C.px)
        case("a the reserve bites: some day holds profit back and some buy is refused for it",
             n_res > 0 and n_short > 0,
             f"{n_res} execution days with a reserve, {n_short} buys skipped because of it, "
             f"over {n_days} execution days in 8 runs")


    def _first_above(rows, base):
        for r in rows:
            if r["port_val"] > base:
                return pd.Timestamp(r["date"])
        return None


    def _same_prefix(e0, a0, e1, a1, cut):
        """Every fill, every day's cash and every equity value before `cut`."""
        pre = e0.index < cut
        eq_ok = bool((e0[pre].to_numpy() == e1[pre].to_numpy()).all())
        f0 = [f for f in a0["costs"]["fills"] if pd.Timestamp(f["date"]) < cut]
        f1 = [f for f in a1["costs"]["fills"] if pd.Timestamp(f["date"]) < cut]
        d0 = [d for d in a0["costs"]["days"] if pd.Timestamp(d["date"]) < cut]
        d1 = [d for d in a1["costs"]["days"] if pd.Timestamp(d["date"]) < cut]
        return eq_ok and f0 == f1 and d0 == d1, int(pre.sum()), len(f0)


    def case_b1():
        C = Cell("nifty500")
        for tax in (False, True):
            e0, a0 = C.run("v4", tax, False)
            e1, a1 = C.run("v4", tax, True)
            cut = _first_above(a1["fixed"], BASE)
            if cut is None:
                case(f"b1 nifty500 v4 tax {'on' if tax else 'off'}", False,
                     "open equity never passed the base; the case has no cut")
                continue
            same, n_days, n_fills = _same_prefix(e0, a0, e1, a1, cut)
            after = int((e0[e0.index >= cut] != e1[e1.index >= cut]).sum())
            n_exec = sum(1 for r in a1["fixed"] if pd.Timestamp(r["date"]) < cut)
            case(f"b1 nifty500 pit tradeable v4 tax {'on' if tax else 'off'}: identical up to "
                 f"the session before {cut.date()}", same and n_days > 0,
                 f"{n_days} sessions, {n_exec} execution days, {n_fills} fills identical; "
                 f"{after} of {int((e0.index >= cut).sum())} later sessions differ")
            check_c(f"nifty500 v4 tax {'on' if tax else 'off'} compounded", a0, e0, C.px)
            check_c(f"nifty500 v4 tax {'on' if tax else 'off'} fixed", a1, e1, C.px)


    # ---------------------------------------------------------------------------
    # synthetic panels
    # ---------------------------------------------------------------------------
    SYMS = [f"S{k:02d}" for k in range(40)]
    WARM = pd.bdate_range("2020-08-03", "2020-12-31")
    DATES = pd.bdate_range("2021-01-01", "2021-12-31")


    def falling_panel():
        idx = WARM.append(DATES)
        rng = np.random.default_rng(7)
        out = {}
        for k, s in enumerate(SYMS):
            r = -0.0012 - 0.00002 * k + 0.004 * rng.standard_normal(len(idx))
            out[s] = 100.0 * (1 + 0.02 * k) * np.cumprod(1 + r)
        px = pd.DataFrame(out, index=idx)
        op = px.shift(1).fillna(px) * (1 + 0.001 * np.sin(np.arange(len(idx)))[:, None])
        # Scores redrawn every session, so each rebalance turns the book over.
        sc = pd.DataFrame(rng.standard_normal(px.shape), index=idx, columns=SYMS)
        return px, op, sc


    def synth_run(px, op, sc, mode, sizing, tax, fixed):
        audit = blank()
        kw = {} if fixed is None else {"fixed_capital": fixed}
        eq, tc, n, _ = backtest_exposure(px, op, sc, DATES, precompute(px), px / px.shift(20) - 1,
                                         mode=mode, sizing=sizing, audit=audit, rebal=20,
                                         participation_cap=None, drawdown_stop=None,
                                         dd_overlay=None, tax_enabled=tax,
                                         start_capital=int(BASE), **kw)
        return eq, audit


    def case_b2():
        px, op, sc = falling_panel()
        for mode, sizing, arm in (("none", "invvol", "v1"), ("breadth", "provol", "v4")):
            for tax in (False, True):
                e0, a0 = synth_run(px, op, sc, mode, sizing, tax, False)
                e1, a1 = synth_run(px, op, sc, mode, sizing, tax, True)
                never = (all(r["port_val"] <= BASE for r in a1["fixed"])
                         and bool((e1 <= BASE).all()))
                same, n_days, n_fills = _same_prefix(e0, a0, e1, a1, DATES[-1] + pd.Timedelta(days=1))
                case(f"b2 synthetic falling panel {arm} tax {'on' if tax else 'off'}: equity never "
                     f"passes the base and the two runs are identical", never and same and n_fills > 0,
                     f"{n_days} sessions, {n_fills} fills; end equity Rs {e1.iloc[-1]:,.2f}; "
                     f"highest open equity Rs {max(r['port_val'] for r in a1['fixed']):,.2f}")
                check_c(f"synthetic {arm} tax {'on' if tax else 'off'} compounded", a0, e0, px)
                check_c(f"synthetic {arm} tax {'on' if tax else 'off'} fixed", a1, e1, px)


    def case_names_refusals():
        d = (fixed_axis.suffix(), fixed_axis.segment(), fixed_axis.label())
        fixed_axis.set_selection(True)
        on = (fixed_axis.suffix(), fixed_axis.segment())
        fixed_axis.set_selection(None)
        case("1 names", d == ("", "", "") and on == ("_fixed", "@fixed"), f"off {d}, on {on}")

        px, op, sc = falling_panel()
        import portfolio as ar
        from settings import dd_axis
        refused = []
        for name, stop, dd in (("drawdown_stop", ar.DrawdownStop(threshold=0.5), None),
                               ("dd_overlay", None, dd_axis.make(20))):
            try:
                backtest_exposure(px, op, sc, DATES, precompute(px), px / px.shift(20) - 1,
                                  mode="none", rebal=20, participation_cap=None,
                                  fixed_capital=True, drawdown_stop=stop, dd_overlay=dd)
            except ValueError:
                refused.append(name)
        import run
        cli = []
        for argv in (["--fixed-capital", "--dd", "20", "--list"],
                     ["--fixed-capital", "--arm", "v5", "--list"]):
            err = io.StringIO()
            try:
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                    run.main(argv)
            except SystemExit as e:
                if e.code == 2 and "--fixed-capital cannot run with" in err.getvalue():
                    cli.append(argv[1])
        # run.main records the selections it parsed before refusing; restore them.
        fixed_axis.set_selection(None)
        dd_axis.set_selection(None)
        case("1 refusals: the engine and run.py refuse the axis with --dd and the stop arms",
             refused == ["drawdown_stop", "dd_overlay"] and cli == ["--dd", "--arm"],
             f"engine refused {refused}; run.py refused {cli}")


    def case_default():
        px, op, sc = falling_panel()
        e0, a0 = synth_run(px, op, sc, "none", "invvol", False, None)
        e1, a1 = synth_run(px, op, sc, "none", "invvol", False, False)
        case("2 default path: fixed_capital unset equals fixed_capital=False",
             bool((e0.to_numpy() == e1.to_numpy()).all()) and a0["costs"] == a1["costs"]
             and "fixed" not in a0)


    def main():
        case_names_refusals()
        case_default()
        case_b2()
        case_a()
        case_b1()
        for label, ok, gap, r, u, c, t, fmt_ok in RECONCILED:
            case(f"c {label}: end equity = base + realised + unrealised - charges - tax", ok,
                 f"gap Rs {gap:+.4f}; realised {r:,.2f}, unrealised {u:,.2f}, charges "
                 f"{c:,.2f}, tax {t:,.2f}; yearly table sums to end equity: {fmt_ok}")
        print(f"\n  {sum(RESULTS)} of {len(RESULTS)} passed")
        return 0 if all(RESULTS) else 1

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main())


def _impact_pcap_axis():
    """
impact_pcap_axis_test.py -- the market-impact and participation-cap axes on a
synthetic panel.

    ./venv/bin/python impact_pcap_axis_test.py          # every case, with its figures
    ./venv/bin/python impact_pcap_axis_test.py --quiet  # PASS/FAIL lines only

    1. validation: k below 0 and a cap at or below 0 are refused; k 0 is the default
    2. names: "" at the defaults, "_impact0p003" / "@impact0p003" and
       "_pcap0p1" / "@pcap0p1" otherwise; --cap at the profile's own value is ""
    3. the research profile refuses a non-zero k and any cap, in check_profile and
       in costs.cap_kwargs
    4. costs.participation_cap: the profile's value, or --cap's under tradeable
    5. the default path: impact_k unset and impact_k=None give the same curve, and
       the cost trail carries no impact keys
    6. with impact on, every fill is costs.impact on top of the flat rate, the
       run reconciles to the paisa, and impact is reported apart from slippage:
       flat slippage is exactly reference x SLIPPAGE x qty, and gross profit
       includes impact
    7. the summary block prints an impact row and summary_figures reads it back

No data, nothing written. Exit 0 when every case passes, 1 otherwise.
"""
    import sys
    import warnings
    from pathlib import Path

    warnings.filterwarnings("ignore")
    ROOT = Path(__file__).resolve().parent
    for _p in (ROOT, ROOT / "results"):
        sys.path.insert(0, str(_p))

    import numpy as np
    import pandas as pd

    import reports as cost_report
    from settings import impact_axis
    from settings import pcap_axis
    import costs
    import settings
    from market_data import precompute
    from portfolio import backtest_exposure

    QUIET = "--quiet" in sys.argv
    RESULTS = []
    SYMS = [f"S{k:02d}" for k in range(12)]
    WARM = pd.bdate_range("2020-08-03", "2020-12-31")
    DATES = pd.bdate_range("2021-01-01", "2021-12-31")
    K = 0.003


    def case(name, ok, detail=""):
        RESULTS.append(bool(ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail and not QUIET else ""))


    def panel():
        idx = WARM.append(DATES)
        f = np.cumprod(np.r_[1.0, np.full(len(idx) - 1, 1.0007)])
        px = pd.DataFrame({s: 100.0 * f * (1 + 0.01 * k) * (1 + 0.002 * np.sin(np.arange(len(idx)) / (k + 3)))
                           for k, s in enumerate(SYMS)}, index=idx)
        sc = pd.DataFrame({s: float(len(SYMS) - k) for k, s in enumerate(SYMS)}, index=idx)
        # a median volume on every date of the window, different per symbol
        vol20 = {s: {d: 20_000.0 + 1_000.0 * k for d in DATES} for k, s in enumerate(SYMS)}
        return px, px.copy(), sc, vol20


    def run(px, op, sc, **kw):
        audit = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
        audit["costs"] = {"fills": [], "days": []}
        eq, tc, n, _ = backtest_exposure(px, op, sc, DATES, precompute(px), px / px.shift(20) - 1,
                                         mode="none", sizing="invvol", audit=audit, rebal=20,
                                         drawdown_stop=None, **kw)
        return eq, tc, audit


    def reset():
        impact_axis.set_selection(None)
        pcap_axis.set_selection(None)
        settings.profile_axis.set_selection(None)


    def main():
        # 1 ----------------------------------------------------------------------
        bad = []
        for v in (-0.001, float("nan")):
            try:
                impact_axis.set_selection(v)
                bad.append(("impact", v))
            except ValueError:
                pass
        for v in (0, -0.5):
            try:
                pcap_axis.set_selection(v)
                bad.append(("cap", v))
            except ValueError:
                pass
        impact_axis.set_selection(0)
        zero_is_default = impact_axis.is_default() and impact_axis.impact_k() is None
        reset()
        case("1 validation: k < 0 and cap <= 0 refused; k 0 is the default",
             not bad and zero_is_default, f"accepted wrongly: {bad}")

        # 2 ----------------------------------------------------------------------
        settings.profile_axis.set_selection("tradeable")
        names_default = (impact_axis.suffix(), impact_axis.segment(), pcap_axis.suffix(),
                         pcap_axis.segment())
        impact_axis.set_selection(K)
        pcap_axis.set_selection(0.1)
        names_on = (impact_axis.suffix(), impact_axis.segment(), pcap_axis.suffix(),
                    pcap_axis.segment())
        pcap_axis.set_selection(1.0)
        own_cap = pcap_axis.suffix()
        reset()
        case("2 names", names_default == ("", "", "", "")
             and names_on == ("_impact0p003", "@impact0p003", "_pcap0p1", "@pcap0p1") and own_cap == "",
             f"default {names_default}, on {names_on}, --cap 1.0 under tradeable {own_cap!r}")

        # 3 ----------------------------------------------------------------------
        refused = []
        impact_axis.set_selection(K)
        for what, fn in (("impact check_profile", impact_axis.check_profile),
                         ("cap_kwargs", lambda: costs.cap_kwargs(None))):
            try:
                fn()
            except ValueError:
                refused.append(what)
        reset()
        pcap_axis.set_selection(0.1)
        try:
            pcap_axis.check_profile()
        except ValueError:
            refused.append("cap check_profile")
        reset()
        case("3 research refuses --impact and --cap", len(refused) == 3, f"refused: {refused}")

        # 4 ----------------------------------------------------------------------
        settings.profile_axis.set_selection("tradeable")
        own = costs.participation_cap()
        pcap_axis.set_selection(0.1)
        over = costs.participation_cap()
        reset()
        case("4 participation_cap: profile's 1.0, --cap's 0.1", own == 1.0 and over == 0.1,
             f"own {own}, with --cap 0.1 {over}")

        # 5 ----------------------------------------------------------------------
        px, op, sc, vol20 = panel()
        e0, _, a0 = run(px, op, sc, participation_cap=1.0, vol20=vol20)
        e1, _, _ = run(px, op, sc, participation_cap=1.0, vol20=vol20, impact_k=None)
        keys = set().union(*(r.keys() for r in a0["costs"]["fills"]))
        case("5 default path unchanged, no impact keys in the cost trail",
             bool((e0 == e1).all()) and "impact_median" not in keys
             and "impact_rs" not in cost_report.fills_frame(a0["costs"]).columns)

        # 6 ----------------------------------------------------------------------
        eK, tcK, aK = run(px, op, sc, participation_cap=1.0, vol20=vol20, impact_k=K)
        fills, lots, years, days = cost_report.reconcile_costs(aK["costs"], aK["trades"], list(DATES),
                                                         1_000_000.0, tcK, 0.0, False)
        want = [costs.impact(int(r.qty), vol20[r.symbol][r.date], K) for r in fills.itertuples()]
        rate_ok = np.allclose(fills["impact_rate"], want, rtol=0, atol=1e-15)
        # The fill is rounded to the paisa, so the flat part carries up to half a
        # paisa a share of rounding.
        flat = fills["reference_price"] * costs.SLIPPAGE * fills["qty"]
        flat_ok = bool((np.abs(fills["slippage_rs"] - flat) <= 0.005 * fills["qty"] + 1e-6).all())
        S = cost_report.strategy_totals(1_000_000.0, float(eK.iloc[-1]), fills, years)
        gross_ok = abs(S["gross"] - (S["final"] - 1_000_000.0 + S["charges"] + S["slippage"]
                                     + S["impact"] + S["tax"])) < 0.005
        case("6 impact on: fills reconcile, impact split from flat slippage",
             rate_ok and flat_ok and gross_ok and S["impact"] > 0 and eK.iloc[-1] < e0.iloc[-1],
             f"impact Rs {S['impact']:,.2f}, flat slippage Rs {S['slippage']:,.2f}, "
             f"final Rs {eK.iloc[-1]:,.2f} against Rs {e0.iloc[-1]:,.2f} without")

        # 7 ----------------------------------------------------------------------
        lines = cost_report.summary_block("synthetic v1", "tradeable", False, 20, 1_000_000.0, eK,
                                          fills, years, days, None)
        got = cost_report.summary_figures("\n".join(lines))
        case("7 summary prints impact and reads it back",
             got.get("strategy/impact") == f"{S['impact']:,.2f}",
             f"printed {got.get('strategy/impact')}")

        print(f"\n  {sum(RESULTS)} of {len(RESULTS)} passed")
        return 0 if all(RESULTS) else 1

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main())


def _tax_rules():
    """
tax_rules_test.py -- the tax rules of 2026-10-14, each on a hand-worked case.

    ./venv/bin/python tax_rules_test.py          # every case, with its arithmetic
    ./venv/bin/python tax_rules_test.py --quiet  # PASS/FAIL lines only

costs.py charges capital-gains tax on listed equity as the Income-tax
Act does for s.111A/112A, with these rules added on 2026-10-14:

    holding period   long-term only when held more than twelve calendar months
    within a year    a net short-term loss is set off against long-term gains
    carry-forward    a net short-term loss for up to 8 years against later short-
                     and long-term gains; a net long-term loss for up to 8 years
                     against later long-term gains only; oldest first; before the
                     LTCG exemption
    cess             4% on the tax

Each case below states its arithmetic and is checked to the paisa (0.005). The
last case runs the same years through costs.Ledger, the class the engine uses,
so the in-loop path is checked as well as the function. No data, nothing written.
Exit 0 when every case passes, 1 otherwise.
"""
    import sys
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent
    sys.path.insert(0, str(ROOT / "results"))

    import pandas as pd

    import costs

    QUIET = "--quiet" in sys.argv
    PAISA = 0.005
    RESULTS = []


    def B(**kw):
        b = dict.fromkeys(costs.BUCKETS, 0.0)
        b.update({k: float(v) for k, v in kw.items()})
        return b


    def case(name, got, want, how):
        ok = abs(got - want) < PAISA
        RESULTS.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  {name}: {got:,.2f} (hand-worked {want:,.2f})"
              + ("" if QUIET else f"\n          {how}"))


    def years(by_fy):
        return costs.assess_years(by_fy)


    def main():
        # 1. cess on a plain short-term gain
        t = costs.tax_for_fy(2025, B(short_new=10_000))
        case("1 cess", t["total_tax"], 2_080.00,
             "10,000 x 20% = 2,000; cess 4% = 80; 2,080")

        # 2. within a year: a net short-term loss against a long-term gain, before the exemption
        t = costs.tax_for_fy(2021, B(short_old=-30_000, long_old=150_000))
        case("2 short loss against this year's long gain", t["total_tax"], 2_080.00,
             "150,000 - 30,000 = 120,000; less exemption 1,00,000 = 20,000 x 10% = 2,000; +4% = 2,080")

        # 3. carry-forward of a short loss against a later short gain
        y = years({2020: B(short_old=-10_000), 2021: B(short_old=30_000)})
        case("3 short loss carried to a later short gain", y[2021]["total_tax"], 3_120.00,
             "FY2021: 30,000 - 10,000 brought forward = 20,000 x 15% = 3,000; +4% = 3,120")

        # 4. carry-forward of a short loss against a later long gain, before the exemption
        y = years({2020: B(short_old=-50_000), 2021: B(long_old=200_000)})
        case("4 short loss carried to a later long gain", y[2021]["total_tax"], 5_200.00,
             "200,000 - 50,000 = 150,000; less 1,00,000 = 50,000 x 10% = 5,000; +4% = 5,200")

        # 5. a long loss is not set off against short gains
        y = years({2020: B(long_old=-40_000), 2021: B(short_old=40_000, long_old=120_000)})
        case("5 long loss carried: long gains only", y[2021]["total_tax"], 6_240.00,
             "short 40,000 x 15% = 6,000 (the long loss cannot touch it); long 120,000 - "
             "40,000 = 80,000 < 1,00,000, nil; 6,000 + 4% = 6,240")

        # 6. eight years and no more
        y = years({2015: B(short_old=-10_000), 2023: B(short_old=10_000)})
        case("6a a loss usable in its 8th year", y[2023]["total_tax"], 0.00,
             "FY2015 loss, FY2023 gain (8 years on): 10,000 - 10,000 = 0")
        y = years({2015: B(short_old=-10_000), 2024: B(short_new=10_000)})
        case("6b a loss expired in its 9th year", y[2024]["total_tax"], 2_080.00,
             "FY2015 loss expired by FY2024: 10,000 x 20% = 2,000; +4% = 2,080")

        # 7. oldest loss first
        y = years({2020: B(short_old=-5_000), 2021: B(short_old=-5_000),
                   2029: B(short_new=10_000)})
        case("7 oldest loss first, and expiry by year of origin", y[2029]["total_tax"], 1_040.00,
             "FY2020's 5,000 expired by FY2029; FY2021's 5,000 is usable: 10,000 - 5,000 = "
             "5,000 x 20% = 1,000; +4% = 1,040")

        # 8. a partly used loss carries its remainder
        y = years({2020: B(short_old=-30_000), 2021: B(short_old=10_000),
                   2022: B(short_old=50_000)})
        case("8a remainder after partial use, FY2021", y[2021]["total_tax"], 0.00,
             "10,000 - 10,000 of the 30,000 = 0; 20,000 left")
        case("8b remainder after partial use, FY2022", y[2022]["total_tax"], 4_680.00,
             "50,000 - 20,000 = 30,000 x 15% = 4,500; +4% = 4,680")

        # 9. holding period by calendar months
        for buy, sell, want in (("2023-01-31", "2024-01-31", 0.0), ("2023-01-31", "2024-02-01", 1.0),
                                ("2023-03-01", "2024-02-29", 0.0), ("2023-03-01", "2024-03-02", 1.0)):
            got = 1.0 if costs.is_long_term(pd.Timestamp(buy), pd.Timestamp(sell)) else 0.0
            case(f"9 bought {buy}, sold {sell}: long", got, want,
                 "long-term only when sold after the buy date plus 12 calendar months")

        # 10. the engine's Ledger, in its own order, against the function
        dates = pd.bdate_range("2020-04-01", "2023-06-30")
        led = costs.Ledger(dates)
        led.buy("A", 100, 100.0, pd.Timestamp("2020-05-04"))
        led.sell("A", 100, 70.0, pd.Timestamp("2020-06-01"))      # FY2020 short -3,000
        led.buy("B", 100, 100.0, pd.Timestamp("2021-05-03"))
        led.sell("B", 100, 150.0, pd.Timestamp("2021-06-01"))     # FY2021 short +5,000
        paid = 0.0
        for d in dates:
            paid += led.due_on(d) + led.due_on(d, after_fills=True)
        case("10 the Ledger carries the loss forward", paid, 312.00,
             "FY2020: -3,000, nil, carried; FY2021 (sold before 2024-07-23, 15%): "
             "5,000 - 3,000 = 2,000 x 15% = 300; +4% = 312")
        return 0 if all(RESULTS) else 1

    # was this file's `if __name__ == "__main__":` block
    rc = main()
    print(f"\n  {sum(RESULTS)} of {len(RESULTS)} passed")
    sys.exit(rc)


def _tax_total():
    """
tax_total_test.py -- the COSTS block's tax figures against what cash paid.

    ./venv/bin/python tax_total_test.py                    # every case, with its figures
    ./venv/bin/python tax_total_test.py --quiet            # PASS/FAIL lines only
    ./venv/bin/python tax_total_test.py --module FILE.py   # test another copy of cost_report

A synthetic tax-on run with gains, reconciled by reports.py, then its
summary block read back as printed:

    1. the printed tax total equals COST_TAX_YEARS total_tax summed and the ledger's
       final cum_tax, within Rs 0.01
    2. short-term + long-term + cess, as printed, equal the printed tax total
    3. the printed gross profit is final equity - starting capital + charges +
       slippage + the tax total
    4. the per-year table's short tax, long tax and cess add up to the tax total
    5. the buy & hold sold on the last day: short + long + cess = its tax total
    6. reports.check_tax_total refuses a block whose tax total leaves the cess out

The block is parsed here with its own regular expressions, not with cost_report's
summary_figures, so the test reads what a person reads. --module points it at any
copy of reports.py: the copy at commit 6ab7c55, from before the fix, fails 1 to 5.
No data, nothing written. Exit 0 when every case passes, 1 otherwise.
"""
    import importlib.util
    import re
    import sys
    import warnings
    from pathlib import Path

    warnings.filterwarnings("ignore")
    ROOT = Path(__file__).resolve().parent
    for _p in (ROOT, ROOT / "results"):
        sys.path.insert(0, str(_p))

    import numpy as np
    import pandas as pd

    from market_data import precompute
    from portfolio import backtest_exposure

    QUIET = "--quiet" in sys.argv
    RESULTS = []
    BASE = 1_000_000.0
    SYMS = [f"S{k:02d}" for k in range(30)]
    WARM = pd.bdate_range("2020-08-03", "2020-12-31")
    DATES = pd.bdate_range("2021-01-01", "2022-06-30")


    def load_cost_report():
        if "--module" in sys.argv:
            path = Path(sys.argv[sys.argv.index("--module") + 1]).resolve()
            spec = importlib.util.spec_from_file_location("cost_report_under_test", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod, str(path)
        import reports as cost_report
        return cost_report, "reports.py"


    def case(name, ok, detail=""):
        RESULTS.append(bool(ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail and not QUIET else ""))


    def panel():
        idx = WARM.append(DATES)
        rng = np.random.default_rng(11)
        r = 0.0012 + 0.006 * rng.standard_normal((len(idx), len(SYMS)))
        px = pd.DataFrame(100.0 * np.cumprod(1 + r, axis=0), index=idx, columns=SYMS)
        op = px.shift(1).fillna(px)
        # Scores redrawn every session, so each rebalance sells and realises gains.
        sc = pd.DataFrame(rng.standard_normal(px.shape), index=idx, columns=SYMS)
        return px, op, sc


    def rs(text, label):
        """The rupee figure of the first block row named `label`, as printed."""
        m = re.search(rf"^  {re.escape(label)}\s+([-\d,]+\.\d\d)", text, re.M)
        return float(m.group(1).replace(",", "")) if m else None


    def main():
        cr, where = load_cost_report()
        print(f"  cost_report under test: {where}")
        px, op, sc = panel()
        audit = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
        audit["costs"] = {"fills": [], "days": []}
        eq, tc, n, _ = backtest_exposure(px, op, sc, DATES, precompute(px), px / px.shift(20) - 1,
                                         mode="none", sizing="invvol", audit=audit, rebal=20,
                                         participation_cap=None, drawdown_stop=None, dd_overlay=None,
                                         fixed_capital=False, tax_enabled=True,
                                         start_capital=int(BASE))
        cum_tax = float(audit["tax"]["cum_tax"])
        _reconcile = getattr(cr, "reconcile_costs", None) or cr.reconcile   # --module may hand in an older file
        fills, lots, years, days = _reconcile(audit["costs"], audit["trades"], list(DATES), BASE,
                                                tc, cum_tax, True, audit["tax"]["lots"])
        bh = cr.bh_costs(px, op, DATES, BASE, True)
        lines = cr.summary_block("synthetic v1", "research", True, 20, BASE, eq, fills, years, days, bh)
        text = "\n".join(lines)
        total_tax = float(years["total_tax"].sum())
        cess_due = float(years["cess"].sum())

        tax = rs(text, "tax, total")
        case("1 printed tax total = COST_TAX_YEARS total_tax summed = ledger cum_tax, within Rs 0.01",
             tax is not None and abs(tax - total_tax) <= 0.01 and abs(tax - cum_tax) <= 0.01,
             f"printed {tax:,.2f}; total_tax {total_tax:,.2f}; cum_tax {cum_tax:,.2f}; "
             f"cess due {cess_due:,.2f}")

        st, lt, ce = rs(text, "  short-term"), rs(text, "  long-term"), rs(text, "  cess")
        parts = (st or 0.0) + (lt or 0.0) + (ce or 0.0)
        case("2 short-term + long-term + cess = tax total, as printed",
             ce is not None and tax is not None and abs(parts - tax) <= 0.02,
             f"{st} + {lt} + {ce} = {parts:,.2f} against {tax}")

        m = re.search(r"gross profit Rs ([-\d,.]+) =", text)
        gross = float(m.group(1).replace(",", ""))
        want = float(eq.iloc[-1]) - BASE + rs(text, "charges, total") + rs(text, "slippage") + total_tax
        case("3 gross profit = final - start + charges + slippage + tax total",
             abs(gross - want) <= 0.03, f"printed {gross:,.2f}; from the parts {want:,.2f}")

        i = text.index("per financial year")
        head = text[i:].splitlines()[1]
        rows = [r for r in text[i:].splitlines()[2:] if re.match(r"^  FY\d{4}-\d\d", r)]
        per_year = 0.0
        for r in rows:
            v = [x.replace(",", "") for x in r.split()[1:]]
            # gross, charges, slippage, short tax, long tax, then cess when the header has it
            per_year += float(v[3]) + float(v[4]) + (float(v[5]) if "cess" in head else 0.0)
        case("4 per-year short tax + long tax + cess = tax total",
             "cess" in head and tax is not None and abs(per_year - tax) <= 0.01 * max(len(rows), 1),
             f"{len(rows)} years sum to {per_year:,.2f} against {tax}; header: {head.strip()}")

        j = text.index("investable buy & hold")
        bt = text[j:]

        def bh_row(label):
            m_ = re.search(rf"^  {re.escape(label)}\s+[-\d,]+\.\d\d\s+([-\d,]+\.\d\d)", bt, re.M)
            return float(m_.group(1).replace(",", "")) if m_ else None
        b_tax, b_st, b_lt, b_ce = (bh_row(x) for x in ("tax, total", "  short-term",
                                                         "  long-term", "  cess"))
        case("5 buy & hold sold on the last day: short + long + cess = its tax total",
             None not in (b_tax, b_ce) and abs((b_st or 0) + (b_lt or 0) + b_ce - b_tax) <= 0.02,
             f"{b_st} + {b_lt} + {b_ce} against {b_tax}")

        import reports as current
        short = [x.replace(f"{tax:>16,.2f}", f"{tax - cess_due:>16,.2f}") if x.startswith("  tax, total")
                 else x for x in lines] if tax is not None else lines
        try:
            current.check_tax_total(short, years, cum_tax)
            refused = False
        except current.CostReconciliationError:
            refused = True
        case("6 check_tax_total refuses a tax total without the cess", refused)

        print(f"\n  {sum(RESULTS)} of {len(RESULTS)} passed")
        return 0 if all(RESULTS) else 1

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main())


def _tradability_causality():
    """
tradability_causality_test.py -- no trade on day i may depend on a row dated after day i.

    ./venv/bin/python tradability_causality_test.py          # every case, with its figures
    ./venv/bin/python tradability_causality_test.py --quiet  # PASS/FAIL lines only
    ./venv/bin/python tradability_causality_test.py --real   # also the KAMAHOLD replay

A synthetic universe of 20 names on real NSE calendar sessions, written as price
files to a temporary folder and loaded through market_data.set_tradeability, the
way every engine run loads it. Each case runs portfolio.backtest_exposure.

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

    import market_data
    from market_data import read_table  # the one CSV/parquet reader: market_data.read_table
    import costs
    from market_data import precompute
    from portfolio import backtest_exposure

    QUIET = "--quiet" in sys.argv
    RESULTS = []
    SYMS = [f"S{k:02d}" for k in range(20)]
    CAL = sorted(d for d in market_data._load_calendar()
                 if pd.Timestamp("2020-06-01") <= d <= pd.Timestamp("2021-12-31"))
    DATES = [d for d in CAL if d >= pd.Timestamp("2021-01-01")]


    def D(i):
        return DATES[i]


    def case(name, ok, detail=""):
        RESULTS.append(bool(ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail and not QUIET else ""))


    class _Fixture:
        """A universe for market_data.set_tradeability: a tag and a folder of price files."""
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
                market_data.set_tradeability(_Fixture("causality", tmp))
            else:
                market_data.set_tradeability(None, enabled=False)
            audit = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions",
                                     "skipped")}
            eq, *_ = backtest_exposure(px, op, sc, DATES, precompute(px), px / px.shift(20) - 1,
                                       mode="none", sizing="invvol", audit=audit, rebal=20,
                                       participation_cap=1.0, vol20=VOL20,
                                       drawdown_stop=None, dd_overlay=None,
                                       fixed_capital=False)
            return audit, eq, op
        finally:
            market_data.set_tradeability(None, enabled=False)
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
        want = round(costs.sell_price(float(op.loc[D(43), "S01"]), 0, None, None), 2)
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
        import backtest_runs as audit_step
        from portfolio import ARMS
        from settings import REGISTRY
        u = REGISTRY["mcap5001to10000"]
        px, op, sc, bd = audit_step.prices(u)
        cut_day = pd.Timestamp("2019-03-15")

        def one(farm, px_, op_, sc_):
            market_data.set_tradeability(_Fixture(u.tag, farm))
            try:
                audit = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions",
                                         "skipped")}
                backtest_exposure(px_, op_, sc_, bd, precompute(px_), px_ / px_.shift(20) - 1,
                                  audit=audit, **ARMS["v1"].kwargs,
                                  tax_enabled=False, rebal=20, participation_cap=None,
                                  drawdown_stop=None, dd_overlay=None, fixed_capital=False)
                return audit
            finally:
                market_data.set_tradeability(None, enabled=False)

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

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main())


def _cache_key():
    """cache_key_test.py -- a cache or record from other code or other data must be refused.

    ./venv/bin/python cache_key_test.py

Each case writes a record the way its harness does, once with the current key and
once with a changed or missing one, into a temporary directory, and asserts that
the harness reuses the first and refuses the second. Nothing under the repository
is written. Exit 1 names every case that failed.

    seed_cache_key      the /tmp fit caches (validate_engine, validate_sizing,
                        validate_breadth_live, purge_fix_measure) change name when
                        the panel's content changes by one byte
"""
    import io
    import json
    import sys
    import tempfile
    from contextlib import redirect_stdout
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent
    for _p in (ROOT, ROOT / "results"):
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))

    import pandas as pd                                            # noqa: E402

    import model
    import settings                                                  # noqa: E402
    from settings import REGISTRY                        # noqa: E402

    TAG = "nifty50"
    FAILS = []


    def check(name, cond):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        if not cond:
            FAILS.append(name)


    def quiet(fn, *a):
        with redirect_stdout(io.StringIO()):
            return fn(*a)


    def fit_cache_cases(tmp):
        from model import seed_cache_key
        a, b = tmp / "panel_a.csv", tmp / "panel_b.csv"
        a.write_text("date,symbol,close\n2020-01-01,X,1.00\n")
        b.write_text("date,symbol,close\n2020-01-01,X,1.01\n")
        check("validate_breadth_live: the T1 cache name changes with the panel content",
              _t1_cache(TAG, 0, [5, 55, 555], a) != _t1_cache(TAG, 0, [5, 55, 555], b))
        code = [ROOT / "checks.py", ROOT / "market_data.py", ROOT / "model.py",
                ROOT / "settings.py"]
        check("seed_cache_key: one byte of panel content changes the key",
              seed_cache_key(code, a, (TAG,)) != seed_cache_key(code, b, (TAG,)))


    def main():
        print("cache_key_test -- stale caches and records must be refused")
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            fit_cache_cases(tmp)
        if FAILS:
            print(f"RESULT: FAIL -- {len(FAILS)} case(s): " + "; ".join(FAILS))
            return 1
        print("RESULT: PASS -- every stale record and cache was refused, every current one reused")
        return 0

    # was this file's `if __name__ == "__main__":` block
    sys.exit(main())


def _buy_shortfall():
    """
buy_shortfall -- a buy cash cannot fully pay for: trimmed or refused (portfolio.py).

    ./venv/bin/python checks.py engine_tests buy_shortfall [--quiet]

    1. names: "" at the default trim, "_refuse" / "@refuse" otherwise; an unknown
       value is refused
    2. largest_fit() returns the largest q that fits, checked against every q
       from 0 to the wanted quantity, at prices from Rs 0.95 to Rs 48,000 and cash
       on both sides of each boundary; trim() returns that q when it is at least
       MIN_FILL_PCT of the wanted quantity and 0 otherwise
    3. a case the rounding of charges decides: 5 shares at Rs 100.00 cost Rs 500 and
       Rs 0.50 of STT, which rounds up to Rs 1. Cash of that cost less Rs 0.01 buys 4,
       though the unrounded charges would let 5 fit
    4. not one share fits: q is 0, reason "cash short", and the engine refuses
       the buy as cash short
    5. the engine on a synthetic panel, v1 to v4, tax off and on, trim against
       refuse:
       a. refuse trims nothing: no trade row has wanted_qty, every cash-short skip
          has one of the two reasons it always had, and buy_shortfall=None with the
          selection at refuse gives the same run as buy_shortfall="refuse"
       b. the two runs are identical, every fill, every day's cash and every
          equity value, up to the first trimmed buy; an arm that is never short of
          cash under refuse trims nothing and is identical over the whole window
       c. each trimmed buy, replayed from the run's own cost trail, is the largest
          q whose cost and charges fit the cash in hand at that point of the
          morning: q fits and q + 1 does not
       d. every trimmed buy fills at least MIN_FILL_PCT of its wanted quantity,
          and every buy refused below the minimum is logged `cash short: below
          minimum fill` with a fill share under it
    6. the minimum fill at its boundary, Rs 100 a share: wanted 10 with cash
       for exactly 5 (50%) fills 5 and with cash for 6 fills 6, while cash
       one paisa short of 5 refuses (4 is 40%); wanted 9, where 50% is 4.5,
       fills 5 (55.6%) and refuses 4 (44.4%); wanted 1,000 fills 500 and
       refuses 499
    7. a floating-point floor that lands one share short: at Rs 0.05 with Rs 0.25
       of cash and no charges, 0.25 // 0.05 is 4.0 but five shares fit, and
       largest_fit() returns 5

No data, nothing written. Exit 0 when every case passes, 1 otherwise.
"""
    import sys
    import warnings
    from pathlib import Path

    warnings.filterwarnings("ignore")
    ROOT = Path(__file__).resolve().parent
    for _p in (ROOT, ROOT / "results"):
        sys.path.insert(0, str(_p))

    import numpy as np
    import pandas as pd

    import portfolio as bsf
    import settings
    from market_data import precompute
    from portfolio import backtest_exposure
    from costs import calc_tc

    QUIET = "--quiet" in sys.argv
    RESULTS = []

    def case(name, ok, detail=""):
        RESULTS.append(bool(ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail and not QUIET else ""),
              flush=True)

    def cost(pr, q):
        return q * pr + calc_tc(pr, q, "BUY")

    def charges(p_, n):
        return calc_tc(p_, n, "BUY")

    # 1. names
    d = (settings.shortfall_axis.selected(), settings.shortfall_axis.suffix(), settings.shortfall_axis.segment(), settings.shortfall_axis.label())
    settings.shortfall_axis.set_selection("refuse")
    on = (settings.shortfall_axis.suffix(), settings.shortfall_axis.segment())
    settings.shortfall_axis.set_selection(None)
    try:
        settings.shortfall_axis.set_selection("shrink")
        bad = False
    except ValueError:
        bad = True
    settings.shortfall_axis.set_selection(None)
    case("1 names and validation", d == ("trim", "", "", "") and on == ("_refuse", "@refuse") and bad,
         f"default {d}, refuse {on}, unknown value refused {bad}")

    # 2. the largest q, against every q
    worst, n_checked = [], 0
    for pr in (0.95, 13.37, 100.0, 251.35, 1999.99, 48000.0):
        for q_w in (1, 7, 40, 333):
            for full in range(0, q_w + 1, max(1, q_w // 20)):
                for eps in (-0.01, 0.0, 0.01):
                    cash = (cost(pr, full) if full else pr) + eps
                    want = max([0] + [k for k in range(1, q_w + 1) if cost(pr, k) <= cash])
                    got = bsf.largest_fit(q_w, cash, lambda n: pr, charges)[0]
                    t = bsf.trim(q_w, cash, lambda n: pr, charges)[0]
                    n_checked += 1
                    if got != want or t != (want if want * 2 >= q_w else 0):
                        worst.append((pr, q_w, round(cash, 2), want, got, t))
    case("2 largest_fit returns the largest q that fits, trim applies the minimum", not worst,
         f"{n_checked} (price, wanted, cash) cases" + (f"; wrong: {worst[:3]}" if worst else ""))

    # 3. rounding of the charges decides q
    pr = 100.0
    c5 = cost(pr, 5)
    unrounded_5 = 500 + 500 * 0.001 + (c5 - 500 - 1.0)   # STT exact, the rest as charged
    cash = c5 - 0.01
    got = bsf.trim(5, cash, lambda n: pr, charges)
    case("3 the rounding of charges decides q", got[0] == 4 and unrounded_5 <= cash and c5 > cash,
         f"cost of 5 Rs {c5:,.2f} (STT Rs {calc_tc(pr, 5, 'BUY') - (c5 - 500 - 1.0):.2f} as "
         f"charged), cash Rs {cash:,.2f}, unrounded cost of 5 Rs {unrounded_5:,.3f}; trim gave {got[0]}")

    # 4. not one share
    got = bsf.trim(10, 99.0, lambda n: 100.0, charges)
    neg = bsf.trim(10, -5_000.0, lambda n: 100.0, charges)
    case("4 not one share fits: q is 0", got[0] == 0 and neg[0] == 0
         and got[3] == "cash short" and neg[3] == "cash short",
         f"cash Rs 99 at Rs 100 -> {got[0]} ({got[3]}); cash -Rs 5,000 -> {neg[0]} ({neg[3]})")

    # 5. the engine
    syms = [f"S{k:02d}" for k in range(40)]
    idx = pd.bdate_range("2020-08-03", "2021-12-31")
    dates = pd.bdate_range("2021-01-01", "2021-12-31")
    rng = np.random.default_rng(11)
    px = pd.DataFrame({s: 100.0 * (1 + 0.05 * k) * np.cumprod(1 + 0.0004 + 0.012 * rng.standard_normal(len(idx)))
                       for k, s in enumerate(syms)}, index=idx)
    op = px.shift(1).fillna(px) * (1 + 0.001 * np.sin(np.arange(len(idx)))[:, None])
    sc = pd.DataFrame(rng.standard_normal(px.shape), index=idx, columns=syms)

    def blank():
        a = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
        a["costs"] = {"fills": [], "days": []}
        return a

    def run(mode, sizing, tax, rule):
        a = blank()
        eq, _, _, _ = backtest_exposure(px, op, sc, dates, precompute(px), px / px.shift(20) - 1,
                                        mode=mode, sizing=sizing, audit=a, rebal=20,
                                        participation_cap=None, drawdown_stop=None,
                                        dd_overlay=None, fixed_capital=False, tax_enabled=tax,
                                        start_capital=1_000_000, buy_shortfall=rule)
        return eq, a

    def first_trim(a):
        t = [r for r in a["trades"] if "wanted_qty" in r]
        return (pd.Timestamp(t[0]["date"]), t[0]) if t else (None, None)

    def replay_ok(a):
        """(trimmed buys checked, failures): each trimmed buy against the cash in hand."""
        trims = {(pd.Timestamp(r["date"]), r["symbol"]) for r in a["trades"] if "wanted_qty" in r}
        days = {pd.Timestamp(x["date"]): x for x in a["costs"]["days"]}
        cash, cur, n, bad = None, None, 0, []
        for f in a["costs"]["fills"]:
            dt = pd.Timestamp(f["date"])
            if dt != cur:
                cur = dt
                x = days[dt]
                cash = x["cash_open"] + x["interest"] - x["tax_before_fills"]
            q, pr, tc = f["qty"], f["fill_price"], f["charges"]
            if f["side"] == "BUY":
                if (dt, f["symbol"]) in trims:
                    n += 1
                    if not (cost(pr, q) <= cash < cost(pr, q + 1)):
                        bad.append((str(dt.date()), f["symbol"], q))
                cash -= q * pr + tc
            else:
                cash += q * pr - tc
        return n, bad

    reasons_old = {"cash short (before TC)", "cash short (incl TC)"}
    for mode, sizing, arm in (("none", "invvol", "v1"), ("breadth", "invvol", "v2"),
                              ("none", "provol", "v3"), ("breadth", "provol", "v4")):
        for tax in (False, True):
            lab = f"{arm} tax {'on' if tax else 'off'}"
            e0, a0 = run(mode, sizing, tax, "refuse")
            settings.shortfall_axis.set_selection("refuse")
            e0s, a0s = run(mode, sizing, tax, None)
            settings.shortfall_axis.set_selection(None)
            rs = {r["reason"] for r in a0["skipped"] if r["reason"].startswith("cash short")}
            case(f"5a {lab}: refuse trims nothing and keeps its reasons",
                 not any("wanted_qty" in r for r in a0["trades"]) and rs <= reasons_old
                 and a0["buy_shortfall"]["trimmed"] == 0
                 and bool((e0 == e0s).all()) and a0["trades"] == a0s["trades"],
                 f"{a0['buy_shortfall']['refused']} refused, reasons {sorted(rs)}")
            e1, a1 = run(mode, sizing, tax, "trim")
            cut, row = first_trim(a1)
            if cut is None:
                n_ref = a0["buy_shortfall"]["refused"]
                case(f"5b {lab}: never short of cash, so trim and refuse are the same run",
                     n_ref == 0 and bool((e0 == e1).all()) and a0["costs"] == a1["costs"],
                     f"{n_ref} refused under refuse, 0 trimmed, {len(a1['costs']['fills'])} fills")
                continue
            pre = e0.index < cut
            f0 = [f for f in a0["costs"]["fills"] if pd.Timestamp(f["date"]) < cut]
            f1 = [f for f in a1["costs"]["fills"] if pd.Timestamp(f["date"]) < cut]
            same = bool((e0[pre].to_numpy() == e1[pre].to_numpy()).all()) and f0 == f1
            case(f"5b {lab}: identical up to the first trimmed buy, {cut.date()}",
                 same and pre.sum() > 0,
                 f"{int(pre.sum())} sessions, {len(f0)} fills; first trim {row['symbol']} "
                 f"wanted {row['wanted_qty']:,}, filled {row['qty']:,}, short Rs "
                 f"{row['cash_shortfall']:,.2f}; {a1['buy_shortfall']['trimmed']} trimmed, "
                 f"{a1['buy_shortfall']['refused']} refused")
            n, bad = replay_ok(a1)
            case(f"5c {lab}: each trimmed buy is the largest q the cash in hand pays for",
                 n > 0 and not bad, f"{n} trimmed buys replayed" + (f"; wrong {bad[:3]}" if bad else ""))
            tr = [r for r in a1["trades"] if "wanted_qty" in r]
            low = [r for r in tr if r["qty"] * 100 < bsf.MIN_FILL_PCT * r["wanted_qty"]]
            bm = [r for r in a1["skipped"] if r["reason"] == bsf.BELOW_MINIMUM]
            bm_bad = [r for r in bm
                      if not float(r["detail"].split("(")[1].split("%")[0]) < bsf.MIN_FILL_PCT]
            case(f"5d {lab}: trimmed buys fill at least {bsf.MIN_FILL_PCT}%, the rest are refused",
                 not low and not bm_bad,
                 f"{len(tr)} trimmed, smallest fill "
                 f"{min((r['qty'] / r['wanted_qty'] * 100 for r in tr), default=float('nan')):.1f}%; "
                 f"{len(bm)} refused below the minimum")

    # 6. the minimum fill at its boundary
    pr = 100.0
    got = {}
    for q_w, fit, eps in ((10, 5, 0.0), (10, 6, 0.0), (10, 5, -0.01),
                          (9, 5, 0.0), (9, 4, 0.0), (1000, 500, 0.0), (1000, 499, 0.0)):
        r = bsf.trim(q_w, cost(pr, fit) + eps, lambda n: pr, charges)
        got[(q_w, fit, eps)] = (r[0], r[3])
    want = {(10, 5, 0.0): (5, None), (10, 6, 0.0): (6, None),
            (10, 5, -0.01): (0, bsf.BELOW_MINIMUM), (9, 5, 0.0): (5, None),
            (9, 4, 0.0): (0, bsf.BELOW_MINIMUM), (1000, 500, 0.0): (500, None),
            (1000, 499, 0.0): (0, bsf.BELOW_MINIMUM)}
    case(f"6 minimum fill {bsf.MIN_FILL_PCT}%: at, just above and just below", got == want,
         "; ".join(f"wanted {k[0]}, cash for {k[1]}{' less Rs 0.01' if k[2] else ''} -> "
                   f"{v[0]}{' (' + v[1] + ')' if v[1] else ''}" for k, v in got.items()))

    # 7. a floor that lands one share short
    floor_q = 0.25 // 0.05
    got7 = bsf.largest_fit(10, 0.25, lambda n: 0.05, lambda p_, n: 0.0)[0]
    case("7 0.25 // 0.05 floors to 4.0, five shares fit, largest_fit returns 5",
         floor_q == 4.0 and 5 * 0.05 <= 0.25 and got7 == 5,
         f"0.25 // 0.05 = {floor_q}, 5 x 0.05 = {5 * 0.05}, largest_fit -> {got7}")

    n_fail = RESULTS.count(False)
    print(f"RESULT: {'PASS' if not n_fail else 'FAIL'} -- {len(RESULTS) - n_fail} of {len(RESULTS)} cases")
    sys.exit(1 if n_fail else 0)


def _fill_open_sizing():
    """
fill_open_sizing -- a buy's quantity does not read the fill session's open.

    ./venv/bin/python checks.py engine_tests fill_open_sizing [--quiet]

Since 2026-10-28 the engine sizes every buy at the decision session's close. On a
synthetic panel, for v1 to v4, tax off and on, the open of one fill session is
moved by +7% and by -7% for every name, and nothing else changes:
    1. every run is identical, every equity value, before that session
    2. every buy decided for that session has the same wanted quantity in all
       three runs (the filled quantity, or wanted_qty for a trimmed buy, or the
       wanted quantity of a buy refused below the minimum fill)
    3. the buys' fill prices on that session moved with the open, so the open
       did reach the run

No data, nothing written. Exit 0 when every case passes, 1 otherwise.
"""
    import re
    import sys
    import warnings
    from pathlib import Path

    warnings.filterwarnings("ignore")
    ROOT = Path(__file__).resolve().parent
    for _p in (ROOT, ROOT / "results"):
        sys.path.insert(0, str(_p))

    import numpy as np
    import pandas as pd

    import portfolio as bsf
    import settings
    from market_data import precompute
    from portfolio import backtest_exposure

    QUIET = "--quiet" in sys.argv
    RESULTS = []

    def case(name, ok, detail=""):
        RESULTS.append(bool(ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail and not QUIET else ""),
              flush=True)

    syms = [f"S{k:02d}" for k in range(40)]
    idx = pd.bdate_range("2020-08-03", "2021-12-31")
    dates = pd.bdate_range("2021-01-01", "2021-12-31")
    rng = np.random.default_rng(11)
    px = pd.DataFrame({s: 100.0 * (1 + 0.05 * k) * np.cumprod(1 + 0.0004 + 0.012 * rng.standard_normal(len(idx)))
                       for k, s in enumerate(syms)}, index=idx)
    op = px.shift(1).fillna(px) * (1 + 0.001 * np.sin(np.arange(len(idx)))[:, None])
    sc = pd.DataFrame(rng.standard_normal(px.shape), index=idx, columns=syms)
    pc, mom = precompute(px), px / px.shift(20) - 1

    def run(op_, mode, sizing, tax):
        a = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
        a["costs"] = {"fills": [], "days": []}
        eq, _, _, _ = backtest_exposure(px, op_, sc, dates, pc, mom, mode=mode, sizing=sizing,
                                        audit=a, rebal=20, participation_cap=None,
                                        drawdown_stop=None, dd_overlay=None, fixed_capital=False,
                                        tax_enabled=tax, start_capital=1_000_000)
        return eq, a

    def wanted(a, day):
        """{symbol: wanted quantity} of every buy decided for `day`."""
        out = {}
        for r in a["trades"]:
            if r["action"] == "BUY" and pd.Timestamp(r["date"]) == day:
                out[r["symbol"]] = int(r.get("wanted_qty", r["qty"]))
        for r in a["skipped"]:
            if (r["side"] == "BUY" and pd.Timestamp(r["date"]) == day
                    and r["reason"] == bsf.BELOW_MINIMUM):
                out[r["symbol"]] = int(re.match(r"wanted ([\d,]+) sh", r["detail"])
                                       .group(1).replace(",", ""))
        return out

    def prices(a, day):
        return {r["symbol"]: r["price"] for r in a["trades"]
                if r["action"] == "BUY" and pd.Timestamp(r["date"]) == day}

    for arm, mode, sizing in (("v1", "none", "invvol"), ("v2", "breadth", "invvol"),
                              ("v3", "none", "provol"), ("v4", "breadth", "provol")):
        for tax in (False, True):
            eq0, a0 = run(op, mode, sizing, tax)
            # The second session with buys: by then the book holds names, so the
            # sells and the decision-close valuation of a held book are exercised.
            buy_days = sorted({pd.Timestamp(r["date"]) for r in a0["trades"] if r["action"] == "BUY"})
            day = buy_days[1]
            runs = {}
            for move in (1.07, 0.93):
                op_m = op.copy()
                op_m.loc[day] = op_m.loc[day] * move
                runs[move] = run(op_m, mode, sizing, tax)
            tag = f"{arm} tax {'on' if tax else 'off'}"
            pre = eq0.index < day
            same_pre = all(bool((e[pre].to_numpy() == eq0[pre].to_numpy()).all())
                           for e, _ in runs.values())
            case(f"1 {tag}: identical before {day.date()}", same_pre and pre.sum() > 0,
                 f"{int(pre.sum())} sessions")
            w0 = wanted(a0, day)
            ws = {m: wanted(a, day) for m, (_, a) in runs.items()}
            case(f"2 {tag}: wanted quantities on {day.date()} unchanged with the open +7% and -7%",
                 len(w0) > 0 and all(w == w0 for w in ws.values()),
                 f"{len(w0)} buys; " + ", ".join(f"{k} {v}" for k, v in sorted(w0.items())[:4]))
            p0 = prices(a0, day)
            moved = all(all(abs(prices(a, day)[k] / p0[k] - m) < 0.001
                            for k in p0 if k in prices(a, day))
                        for m, (_, a) in runs.items())
            case(f"3 {tag}: fill prices on {day.date()} moved with the open", len(p0) > 0 and moved,
                 f"{len(p0)} fills")

    n_fail = RESULTS.count(False)
    print(f"RESULT: {'PASS' if not n_fail else 'FAIL'} -- {len(RESULTS) - n_fail} of {len(RESULTS)} cases")
    sys.exit(1 if n_fail else 0)


def _fill_price():
    """
fill_price -- every fill price is the open moved by the slippage, to the paisa.

    ./venv/bin/python checks.py engine_tests fill_price [--quiet]

Since 2026-10-28 costs.fill_price prices every fill, as
~/Downloads/predictive-backtest's engine.fill_price does: round(open x (1 +/-
rate), 2) in float64, rounded by NumPy.
    1. a buy and a sale of a price already in paise round to the paisa
    2. half a paisa rounds as NumPy rounds: 3450 x 0.9985 = 3444.825 gives 3444.82
    3. buy_price and sell_price are fill_price at SLIPPAGE, with and without impact
    4. on a synthetic panel every fill of v1 to v4, tax off and on, is in whole
       paise and equals fill_price of its reference price

No data, nothing written. Exit 0 when every case passes, 1 otherwise.
"""
    import sys
    import warnings
    from pathlib import Path

    warnings.filterwarnings("ignore")
    ROOT = Path(__file__).resolve().parent
    for _p in (ROOT, ROOT / "results"):
        sys.path.insert(0, str(_p))

    import numpy as np
    import pandas as pd

    import costs
    from market_data import precompute
    from portfolio import backtest_exposure

    QUIET = "--quiet" in sys.argv
    RESULTS = []

    def case(name, ok, detail=""):
        RESULTS.append(bool(ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail and not QUIET else ""))

    b, s_ = costs.fill_price(123.45, 0.0015, True), costs.fill_price(123.45, 0.0015, False)
    case("1 Rs 123.45 buys at 123.64 and sells at 123.26", b == 123.64 and s_ == 123.26,
         f"buy {b}, sell {s_}")
    h = costs.fill_price(3450, 0.0015, False)
    case("2 3450 x 0.9985 = 3444.825 sells at 3444.82", h == 3444.82, f"got {h}")
    imp = costs.impact(1000, 50_000, 0.002)
    ok3 = (costs.buy_price(987.65, 0, None, None) == costs.fill_price(987.65, costs.SLIPPAGE, True)
           and costs.sell_price(987.65, 0, None, None) == costs.fill_price(987.65, costs.SLIPPAGE, False)
           and costs.buy_price(987.65, 1000, 50_000, 0.002)
           == costs.fill_price(987.65, costs.SLIPPAGE + imp, True))
    case("3 buy_price and sell_price are fill_price at SLIPPAGE", ok3)

    rng = np.random.default_rng(11)
    idx = pd.bdate_range("2020-01-01", periods=420)
    syms = [f"S{k:02d}" for k in range(24)]
    px = pd.DataFrame({s: 37.0 * (1 + 0.31 * k) * np.cumprod(1 + 0.0004 + 0.013 * rng.standard_normal(len(idx)))
                       for k, s in enumerate(syms)}, index=idx)
    op = px.shift(1).bfill() * (1 + 0.002 * rng.standard_normal(px.shape))
    sc = pd.DataFrame(rng.standard_normal(px.shape), index=idx, columns=syms)
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    dates = list(idx[80:])
    import portfolio as AR
    for name in ("v1", "v2", "v3", "v4"):
        arm = AR.ARMS[name]
        for tax in (False, True):
            audit = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions",
                                     "skipped")}
            audit["costs"] = {"fills": [], "days": []}
            backtest_exposure(px, op, sc, dates, pc, mom20, sizing=arm.sizing, mode=arm.mode,
                              audit=audit, rebal=20, participation_cap=None,
                              drawdown_stop=None, tax_enabled=tax)
            f = audit["costs"]["fills"]
            off = [r for r in f if abs(r["fill_price"] * 100 - round(r["fill_price"] * 100)) > 1e-6]
            bad = [r for r in f if r["fill_price"] != costs.fill_price(
                r["reference_price"], costs.SLIPPAGE, r["side"] == "BUY")]
            case(f"4 {name} tax {'on' if tax else 'off'}: fills in whole paise, each fill_price "
                 f"of its reference", len(f) > 0 and not off and not bad,
                 f"{len(f)} fills, {len(off)} off the paisa, {len(bad)} not fill_price")

    n_fail = RESULTS.count(False)
    print(f"RESULT: {'PASS' if not n_fail else 'FAIL'} -- {len(RESULTS) - n_fail} of {len(RESULTS)} cases")
    sys.exit(1 if n_fail else 0)


ENGINE_TESTS_CASES = {name[1:]: fn for name, fn in list(globals().items())
         if name.startswith("_") and callable(fn) and name[1:] in (
             "capital_axis", "dd_overlay", "drawdown_stop", "fixed_capital",
             "impact_pcap_axis", "tax_rules", "tax_total", "tradability_causality",
             "cache_key", "buy_shortfall", "fill_open_sizing",
             "fill_price")}


def _cli_engine_tests():
    """`python checks.py engine_tests [ARGS]`: what running engine_tests.py did."""
    if len(sys.argv) < 2 or sys.argv[1] not in ENGINE_TESTS_CASES:
        print(__doc__)
        sys.exit(2)
    ENGINE_TESTS_CASES[sys.argv[1]]()


# ======================================================================================
# gate_compare. From gate_compare.py (moved 2026-11-27).
# ======================================================================================
# gate_compare -- compare a cell's output against a preserved baseline.
#
# WHY THIS IS A TRACKED TOOL AND NOT A SCRIPT REWRITTEN EACH SESSION. Every
# regression verdict this project quoted in the week to 2026-09-15 came from an
# ad-hoc comparison written fresh in the session that needed it, and every one of
# them had the same defect: it walked the BASELINE DIRECTORY and sha'd whatever
# stood at each name in the live tree, without ever asking whether the run had
# written that file. A baseline directory is a snapshot of a whole metrics folder,
# so it holds artefacts from other arms, other profiles and earlier runs. Those
# files are not touched by the cell under test, so they match themselves, every
# time, no matter what the change did.
#
# MEASURED 2026-09-15: of the 36 deterministic artefacts in the midcap150 v3 baseline,
# `--universe midcap150 --arm v3` writes 17. The other 19 are v2's and the tradeable
# profile's. Every midcap150 verdict of the form "35 of 36 byte-identical" was therefore
# reporting 19 files that could not have moved, and a real regression in any of
# them would have been invisible for the same reason.
#
# nifty100 v2 was not affected -- all 17 of its deterministic baseline artefacts are
# written by its cell -- which is why the defect survived: half the evidence was
# sound.
#
# SO THE DENOMINATOR IS WHAT THE CELL WROTE, and the rest is listed but never
# counted. A file the tool cannot explain is UNCLASSIFIED and fails the run: the
# one outcome that must never be silent is "not written, and nobody knows why",
# because that is indistinguishable from a step that stopped writing.
#
#   python3 checks.py gate_compare <baseline-cell-dir> <live-metrics-dir>                           --universe midcap150 --arm v3 [--profile research] [--since EPOCH]

ULP = 2.3e-16          # one unit in the last place, relative


# ---------------------------------------------------------------------------
# THE ONE ACCEPTED NON-IDENTICAL FIELD SET, AND IT LIVES HERE, NOT IN A REVIEW
# ---------------------------------------------------------------------------
# STEP 7 PRODUCED THE FIRST PRE/POST PAIR THAT WAS NOT BYTE-IDENTICAL. Six
# v34_params*.json files moved, one per cell, and all six moved only inside
# `git_state`, which records the commit the run was produced at and whether the
# tree was clean. HEAD necessarily differs between a pre-merge and a post-merge
# run, so that block MUST move; a merge that left it unmoved would mean it was
# recording nothing.
#
# THAT VERDICT WAS REACHED BY SURVEYING WHAT DIFFERED, WHICH IS THE EXACT SHAPE
# THE POLICY BELOW EXISTS TO REJECT. The conclusion was right and the process was
# not: an exception argued at review time is available to argue again, for a field
# that is not provenance, by a reader who wants a green gate. So the exception is
# DATA HERE, checked by the comparator on every run, and a params file that moves
# in any other field is DIFFERS exactly as before.
#
# SCOPED TO `git_state`, NOT MATCHED BY BARE KEY NAME. "note" in particular is a
# generic word; excluding it wherever it appears would silently swallow a moved
# note somewhere else in the document. The block is named on the left of each pair.
#
# NOTHING IS ADDED TO THIS TUPLE WITHOUT THE OWNER OF THE REPOSITORY SAYING SO.
# It is four fields because four fields are provenance. A fifth entry is a request
# to stop checking something, and it has to look like one.
PROVENANCE_FIELDS = (
    ("git_state", "commit"),
    ("git_state", "working_tree_dirty"),
    ("git_state", "modified_or_untracked_files"),
    ("git_state", "note"),
)

# APPROVED BY THE OWNER ON 2026-10-18, FOR EXACTLY THESE FILES AND FIELDS. A rerun on
# another day writes another run_date, and validate_topn and shuffle_test stamp the
# commit and tree state into their own `git` block. Each entry is scoped to the file
# names it names; a block of None is a top-level field. Nothing else is masked.
#   (file-name prefixes, block, field)
APPROVED_FIELDS = (
    (("v34_params", "v2FINAL_params"), None, "run_date"),
    (("topn_params.json", "shuffle_params.json"), "git", "commit"),
    (("topn_params.json", "shuffle_params.json"), "git", "working_tree_dirty"),
    (("topn_params.json", "shuffle_params.json"), "git", "modified_or_untracked_files"),
    (("topn_params.json", "shuffle_params.json"), "git", "note"),
)


# APPROVED BY THE OWNER ON 2026-10-19 FOR runs/<universe>/<arm>/params.json ONLY: the
# per-cell params file a run writes under the repository's runs/ folder. A rerun on
# another day writes another run_date and the commit and tree state it ran at. The
# copies inside each run folder, runs/<folder>/runs/..., are not covered.
RUN_PARAMS_FIELDS = (
    (None, "run_date"),
    ("git_state", "commit"),
    ("git_state", "working_tree_dirty"),
    ("git_state", "modified_or_untracked_files"),
    ("git_state", "note"),
)
RUNS_DIR = Path(__file__).resolve().parent / "runs"


def is_run_params(path):
    """True only for <repository>/runs/<universe>/<arm>/params.json."""
    q = Path(path).resolve()
    return q.name == "params.json" and q.parent.parent.parent == RUNS_DIR


_ABSENT = object()


def masked_fields(name, path=None):
    """[(block or None, field)] masked for a JSON file of this name (and path)."""
    out = list(PROVENANCE_FIELDS) + [(b, f) for pre, b, f in APPROVED_FIELDS
                                     if name.endswith(".json") and name.startswith(pre)]
    if path is not None and is_run_params(path):
        out += [x for x in RUN_PARAMS_FIELDS if x not in out]
    return out


def _get(doc, block, field):
    if block is None:
        return doc.get(field, _ABSENT)
    blk = doc.get(block)
    return blk.get(field, _ABSENT) if isinstance(blk, dict) else _ABSENT


def _strip_provenance(doc, name="", path=None):
    """`doc` without the masked fields for its file. Returns (doc, [fields removed])."""
    if not isinstance(doc, dict):
        return doc, []
    out = dict(doc)
    removed = []
    for block, field in masked_fields(name, path):
        if block is None:
            if field in out:
                out.pop(field)
                removed.append(field)
            continue
        blk = out.get(block)
        if isinstance(blk, dict) and field in blk:
            blk = dict(blk)
            blk.pop(field)
            out[block] = blk
            removed.append(f"{block}.{field}")
    return out, removed


# ---------------------------------------------------------------------------
# CHECKSUM IS THE GATE. GREP IS A HINT.
# ---------------------------------------------------------------------------
# POLICY, 2026-09-15. A keyword survey of divergences has twice declared itself
# complete and been wrong.
#
#   step 5  the engine pair was surveyed for render and artefact divergence, and
#           the survey held -- but only because the pre/post checksum was run.
#   step 6  the chart pair's survey named two divergent render parameters, dpi and
#           the ax[1] legend font size. It missed a THIRD: the drawdown legend's
#           label format, which differs in three ways at once (the split token,
#           the word "max", and .1f versus .0f). The pattern matched the
#           ax[1].plot call and never reached the argument on its CONTINUATION
#           LINE. nifty100's chart moved by 3,971 pixels -- 0.103% of the image, all
#           of it inside one legend box -- and nothing in the survey said so.
#
# SO: A MERGE IS NOT GATED UNTIL BOTH UNIVERSES' ARTEFACTS ARE BYTE-IDENTICAL
# PRE/POST ON THE SAME PANEL. Run the cell at HEAD, checksum, apply the merge, run
# it again, checksum. No survey of differences substitutes for that, and from
# step 7 on a survey must not be offered as evidence that a merge is clean.
#
# AND A COMPARISON MUST EXERCISE WHAT IT CLAIMS TO. The first pixel diff of that
# nifty100 chart reported ZERO differences, because the last run executed at that
# moment was the PRE-merge one -- so it compared the pre-merge file against its
# own copy and proved nothing. Same class as the prose stripper that passed a
# two-line test and did nothing on the real tree: a check that passes because it
# never exercised the thing it claims to check. State which run produced the file
# you are checksumming, or the checksum is decoration.

# ---------------------------------------------------------------------------
# THE STANDING GATE FOR STEPS 4-8 OF THE COLLAPSE
# ---------------------------------------------------------------------------
# FOUR CELLS, AND THE TWO KINDS ARE NOT INTERCHANGEABLE. Measured 2026-09-15 by
# running each and recording what it wrote, rather than reasoning about it.
#
# portfolio.selection_suffix() is EMPTY for a full selection, because only a
# four-arm run may write the canonical v34 artefacts. So:
#
#   --arm all  writes  v34_comparison.csv      chart_v34.png      DAILY_LOG_midcap150.txt
#   --arm v3   writes  v34_comparison_v3.csv   chart_v34_v3.png   DAILY_LOG_midcap150_v3.txt
#
# These are DIFFERENT ARTEFACTS FROM DIFFERENT NAMING BRANCHES. An all-arm cell
# does not subsume a single-arm one, and a gate built only on all-arm cells leaves
# the suffixed branch -- exactly what the merged chart and engine must get right --
# entirely unexercised. That is the trap this table exists to close.
#
# Every cell runs on cached panels; the scoring path is skipped in all four.
STANDING_GATE = (
    # (universe, arm,  profile,    runtime, artefacts, what it alone exercises)
    ("midcap150",  "all", "research",  "67 s", 43, "canonical unsuffixed v34 artefacts"),
    ("nifty100", "all", "research",  "52 s", 43, "canonical, plus chart_nifty100_v1_v2_v3_v4.png"),
    ("midcap150",  "v3",  "research",  "24 s", 20, "the SUFFIXED naming branch on midcap150"),
    ("nifty100", "v2",  "research",  "20 s", 20, "the suffixed branch on nifty100; the accepted cell"),
    # THE TWO TRADEABLE CELLS. Added 2026-09-15 to cover the participation cap, and
    # they exercise the cap's CODE PATH -- vol20 is built, passed and consulted on
    # every buy -- but on today's data it never shrinks an order.
    #
    # THEY WERE ADDED AS "the cap BINDING, largest effect (Rs 3.85M)" AND THAT IS
    # NO LONGER WHAT THEY ARE. Measured 2026-09-20 at commit 7dd37d6: zero rows
    # with reason "participation cap" in either arm's daily_skipped artefact
    # (n=850 fills on v1, n=1006 on v2), highest participation 0.709 and 0.345
    # against a cap of 1.00, and all eight of {trades, skipped, holdings, summary}
    # x {v1, v2} byte-identical to their unsuffixed research twins. The Rs 3.85M
    # belonged to an earlier snapshot; the tree has moved since and nothing
    # re-checked the sentence.
    #
    # SO THE STATEMENT "midcap150 is the only universe whose cap binds" IS WITHDRAWN.
    # nifty100 was already recorded inert; as of this commit midcap150 is inert too,
    # and no cell in this gate replays a run in which the cap changed a single fill. What
    # these cells prove is that the tradeable naming branch and the cap's plumbing
    # reconcile -- not that a cap-shrunk order has ever been replayed.
    #
    # SCOPED 2026-09-23. "no cell in this gate" is exactly two cells -- midcap150 v1
    # and midcap150 v2, the two listed at the bottom of this table -- and it is
    # still true of them: both were re-run under --profile tradeable on 2026-09-22
    # with zero `participation cap` rows. It is NOT a statement about the cap. The
    # full universe x arm grid was run the same day and 7 of its 32 cells diverge
    # from their research twins, on nifty500 v1/v3, nifty100 v1, midcap100 v1/v3
    # and smallcap250 v1/v3. None of those is a cell in this gate, which is why
    # this gate still cannot replay a cap-shrunk order and why that is a gap in the
    # gate rather than a property of the cap.
    #
    # This is a dated measurement of these runs, not a property of the cap. Capital,
    # universe and data all move it. Re-count the "participation cap" rows in the
    # run's own daily_skipped artefact rather than trusting this comment.
    #
    # THE BYTE-IDENTITY ABOVE IS A PROPERTY OF cap=1.00, NOT OF THE CAP. Re-measured
    # 2026-09-22, and the sell side is now capped too, which it was not when the
    # sentences above were written: at cap=1.00 the cap still binds on NO fill on
    # either universe on either side (nifty100 940 fills, midcap150 1006), so the
    # identity holds. AT cap=0.10 IT DOES NOT, BY DESIGN:
    #
    #     nifty100    2 BUY + 1 SELL binds of 941 fills   CAGR 19.01 -> 18.88
    #     midcap150   7 BUY + 3 SELL binds of 1009 fills  CAGR 27.80 -> 27.61
    #
    # So a future run of these cells at a lower cap SHOULD differ from its research
    # twin, and a diff there is the cap working rather than a regression. These two
    # cells still run at the profile default; if that default moves, the expectation
    # above moves with it and this comment must be re-measured, not edited.
    ("midcap150",  "v1",  "tradeable", "25 s", 20, "tradeable branch; cap inert 2026-09-20  [PARTIAL]"),
    ("midcap150",  "v2",  "tradeable", "25 s", 20, "the arm 12b reads; cap inert  [PARTIAL]"),
)

# THE TWO TRADEABLE CELLS ARE PARTIAL, AND THAT IS NOT A DETAIL. They exercise the
# engine and the audit -- STEP 10b, 10c, 10d, 12b, 15, 15b all run, the artefacts
# are written, and all four midcap150 arms reconcile to under a paisa.
#
# THEY USED TO DIE AT STEP 16, AND NO LONGER DO. run_all._present() demanded a
# profile-suffixed v_midcap150_expanding_cache_tradeable.csv; the score panel carries no
# profile dimension, so the guard was asking for a file that should not exist.
# Fixed 2026-09-16 by scoping the guard to the axes each input's name declares.
# `--universe midcap150 --arm v2 --profile tradeable` now runs all nine steps, exit 0.
#
# THE CELLS ARE STILL [PARTIAL], AND FOR A STRONGER REASON THAN BEFORE. They no
# longer stop early -- but NOTHING HERE COMPARES WHAT STEP 16 AND STEP 17 PRODUCE
# under this profile against anything. Before 2026-09-16 those steps had never run
# under it at all; now they run and are unmeasured, which is the easier of the two
# states to mistake for coverage. A green tradeable cell means "the cap is applied
# and replayed correctly", NOT "the tradeable pipeline is verified".
#
# UNTIL A CELL EXISTS THAT ANCHORS THEM, EVERY TRADEABLE ARTEFACT SAYS SO OF
# ITSELF: costs.gate_status() is bannered by run.py at both ends of the run and
# written into v34_params{SFX}.json. Research artefacts are untouched by it, which
# the standing gate proves.
#
# THAT SAME NOTICE USED TO CARRY profiles.CAP_INERT_NOTICE. SUPERSEDED 2026-09-22.
# This comment read: "so a reader who meets a tradeable artefact is told in the
# artefact that its cap did not bind on 2026-09-20 and that it is not, on that
# date, a capped result ... on these runs applying it changed nothing." That was
# true of the two universes it was written from and false of six cells run on
# 2026-09-22, over which the banner printed CAP DID NOT BIND while the cap bound.
# The stored claim is deleted and costs.cap_report() now counts the
# `participation cap` rows out of the run's own daily_skipped instead. A green
# tradeable cell still means "the cap is applied and replayed correctly" and
# whether applying it changed anything is a per-run measurement, not a property.
#
# Parked until after the collapse by explicit decision: it is the third instance of
# one missing naming authority, and fixing it at the call site would add a fourth
# place that decides which artefacts carry a profile dimension. See KNOWN_ISSUES,
# "No component owns which axes an artefact carries".

# WHAT THE STANDING GATE DOES NOT COVER, stated so coverage is never assumed. Each
# of these is a real axis of this pipeline that no cell above touches:
#
#   --profile tradeable   RECONCILES since 2026-09-15 (audit_step now pairs the cap
#                         with vol20), and midcap150 v1/v2 tradeable are gate cells above.
#                         The cells remain [PARTIAL] for the reason given above
#                         them: nothing here compares what STEP 16 and STEP 17
#                         produce under this profile against anything.
#
#                         THE CLAIM THAT FOLLOWED WAS DISCHARGED ON 2026-09-16 BY
#                         COMMIT 211f151, and is kept because it is the reason the
#                         fourth field in REQUIRED_INPUTS exists:
#
#                           "It still cannot COMPLETE: run_all._present() demands a
#                            profile-suffixed v_midcap150_expanding_cache_tradeable.csv,
#                            and the score panel has no profile dimension, so
#                            STEP 16 blocks. A naming-authority defect, not a cap
#                            one. See KNOWN_ISSUES.md, 'The tradeable profile
#                            cannot complete'."
#
#                         run_all._present() (backtest_runs.py) now composes a
#                         suffix only for the axes an input's own name carries,
#                         taken from the compulsory fourth field of its
#                         REQUIRED_INPUTS entry. The score panel is declared
#                         AXIS_FREE (backtest_runs.py, entries at :608, :617, :634),
#                         so the guard asks for v_midcap150_expanding_cache.csv by
#                         its one true name and STEP 16 does not block. The block
#                         at lines 161-165 above records the same discharge.
#   --rebal 40            the _r40 cadence suffix. Exercised by no cell here.
#   9 of 15 arm subsets   portfolio.suffix() names any subset (_v1_v3 and so
#                         on); four singles and one full selection are covered,
#                         the other ten combinations are not. docs/HANDOFF.md
#                         records the same gap.
#   the scoring path      every cell runs on cached panels, so
#                         model.run() returns early. Covering it costs
#                         a 34-minute forced rebuild.


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# A PASS THAT WENT DIRTY HALFWAY IS CAUGHT BY THE ARTEFACT, NOT BY THE HARNESS
# ---------------------------------------------------------------------------
# THE REFUSAL AT THE TOP OF main() CHECKS THE TREE ONCE, BEFORE COMPARING, AND
# THAT IS NOT ENOUGH. On 2026-09-16 a post pass started clean, and the tree was
# edited while its first cell ran; the second cell recorded
# working_tree_dirty=true. The gate still reported PASS, and the only sign was in
# the PROVENANCE detail -- "git_state.commit" on one cell and all four fields on
# the other. A gate that can be invalidated halfway and is caught only by reading
# its own verdict carefully is not a gate.
#
# THE ARTEFACT CARRIES THE ANSWER, WHICH IS BETTER THAN ANY HARNESS CHECK. Each
# run stamps `git_state.working_tree_dirty` into its params JSON. Reading it here
# catches a dirty pass PER CELL, whatever ran the cells, including a harness that
# checks nothing at all -- and it catches the half that went dirty rather than the
# pass as a whole.
#
# THE FIELD IS EXCLUDED FROM THE DIFF AND CHECKED FOR ITS VALUE. Those are
# different questions: whether it MOVED between passes is provenance and is
# forgiven; whether it is TRUE is the pass admitting it cannot be reproduced.
def dirty_stamp(p):
    """(commit, n_files) when this artefact records a dirty tree, else None."""
    if p.suffix != ".json":
        return None
    try:
        g = json.loads(p.read_text()).get("git_state")
    except Exception:
        return None
    if isinstance(g, dict) and g.get("working_tree_dirty") is True:
        return (str(g.get("commit", "?"))[:12], g.get("modified_or_untracked_files", "?"))
    return None


def why_not_written(stem, universe, arm, profile, known_universes):
    """The reason this cell never writes that artefact, or None if unexplained."""
    if "tradeable" in stem and profile != "tradeable":
        return f"wrong profile (file is tradeable; cell ran {profile})"
    arms_in_name = set(re.findall(r'(?<![A-Za-z0-9])(v[1-4])(?![0-9])', stem))
    # v2FINAL / v34 are FILE FAMILIES, not arm tags -- strip them before deciding.
    for fam in ("v2FINAL", "v34"):
        if fam.lower() in stem.lower():
            arms_in_name -= {fam[:2].lower()}
    if arms_in_name and arm not in arms_in_name:
        return f"wrong arm (file is for {'/'.join(sorted(arms_in_name))}; cell ran {arm})"
    if not arms_in_name and stem.startswith("daily_"):
        return "wrong arm (unsuffixed daily log belongs to the default arm v2)"
    for u in known_universes:
        if u != universe and re.search(rf'(?<![A-Za-z0-9]){re.escape(u)}(?![A-Za-z0-9])', stem):
            return f"wrong universe (file is {u}; cell ran {universe})"
    return None


def gate_compare_compare(bp, lp):
    """(verdict, detail) for one artefact pair."""
    if sha(bp) == sha(lp):
        return "EXACT", ""
    if bp.suffix == ".png":
        return "DIFFERS", "image bytes (PNGs drift; not a regression verdict on their own)"
    if bp.suffix == ".json":
        a, b = json.loads(bp.read_text()), json.loads(lp.read_text())
        # PROVENANCE IS STRIPPED AND THE VERDICT IS NAMED, NOT FOLDED INTO EXACT.
        # Calling it EXACT would hide that the file moved at all, which is the
        # other half of the same defect: an accepted difference has to stay
        # visible in the report or the next reader cannot tell it was accepted.
        sa, ra = _strip_provenance(a, bp.name, lp)
        sb, rb = _strip_provenance(b, bp.name, lp)
        if (ra or rb) and sa == sb:
            # NAME THE FIELDS THAT MOVED, NOT THE FIELDS THAT ARE EXCLUDED. The
            # first version printed all four whenever all four were present, so a
            # pair whose only real difference was `commit` was reported as though
            # the tree state and the note had moved too. An accepted exception that
            # overstates itself is the same defect as one that hides: the reader
            # cannot tell what was actually forgiven.
            moved = [f if blk is None else f"{blk}.{f}" for blk, f in masked_fields(bp.name, lp)
                     if _get(a, blk, f) != _get(b, blk, f)]
            return "PROVENANCE", (", ".join(moved) + " only") if moved else "identical"
        return "DIFFERS", f"keys {sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))}"
    if bp.suffix != ".csv":
        return "DIFFERS", "content"
    import pandas as pd
    da, db = read_table(bp), read_table(lp)
    if list(da.columns) != list(db.columns) or len(da) != len(db):
        return "DIFFERS", f"shape {da.shape} -> {db.shape}"
    worst, col = 0.0, None
    for c in da.columns:
        if pd.api.types.is_numeric_dtype(da[c]) and pd.api.types.is_numeric_dtype(db[c]):
            r = ((da[c] - db[c]).abs() / da[c].abs().clip(lower=1e-12)).max()
            if pd.notna(r) and r > worst:
                worst, col = float(r), c
        elif not da[c].astype(str).equals(db[c].astype(str)):
            return "DIFFERS", f"text column '{c}'"
    if worst == 0.0:
        return "EXACT", ""
    return ("ULP" if worst <= ULP else "DIFFERS"), f"max rel {worst:.3e} in '{col}'"


def print_cells():
    print("STANDING GATE -- steps 4-8 of the collapse\n")
    for u, arm, pf, rt, n, why in STANDING_GATE:
        print(f"  --universe {u:<4} --arm {arm:<3} --profile {pf:<8}"
              f"  {rt:>5}  {n:>3} artefacts   {why}")
    print("\n  Both kinds are required: a full selection writes the CANONICAL v34")
    print("  artefacts and a single arm writes the SUFFIXED ones. Neither subsumes")
    print("  the other. See the module docstring for what is outside this gate:")
    print("  the tradeable profile, the _r40 cadence, 10 of 15 arm subsets, and")
    print("  the scoring path.")


def gate_compare(argv=None):
    if (argv if argv is not None else sys.argv[1:])[:1] == ["--cells"]:
        print_cells(); return 0
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline"); ap.add_argument("live")
    ap.add_argument("--universe", required=True); ap.add_argument("--arm", required=True)
    ap.add_argument("--profile", default="research")
    ap.add_argument("--since", type=float, required=True,
                    help="epoch seconds; a live file newer than this was written by the cell")
    a = ap.parse_args(argv)

    # ------------------------------------------------------------------
    # BOTH PASSES RUN CLEAN, AND THIS IS WHERE THAT STOPS BEING A HABIT
    # ------------------------------------------------------------------
    # Step 7's post-merge pass ran with 23 modified files in the tree. The
    # comparison was still sound -- the only field that moved was provenance --
    # but it was sound by luck: `git_state.working_tree_dirty` was TRUE, so the
    # artefact itself recorded that the commit did not describe the run, and the
    # gate compared a reproducible pass against an unreproducible one.
    #
    # A DIRTY TREE MEANS THE POST PASS CANNOT BE RE-RUN TO THE SAME BYTES by
    # anyone, including the person who ran it, because what produced it is not in
    # git. That is not a comparison; it is a measurement of something that no
    # longer exists. So this refuses rather than warning: a warning at the top of
    # a long report is read once.
    #
    # THERE IS NO --allow-dirty. Adding one is a request to compare against
    # something unreproducible, and it should have to be argued for, in this file,
    # by name.
    import subprocess
    try:
        dirty = subprocess.run(["git", "status", "--porcelain"],
                               cwd=str(Path(__file__).resolve().parent),
                               capture_output=True, text=True, check=True).stdout.strip()
    except Exception as e:                      # not a checkout, or no git
        dirty = ""
        print(f"  NOTE  could not read git state ({type(e).__name__}); "
              f"the clean-tree requirement was NOT checked.")
    if dirty:
        n = len(dirty.splitlines())
        print("REFUSING -- the working tree has "
              f"{n} modified or untracked file(s).")
        print("  Both passes of a pre/post gate must run from a clean tree, or the")
        print("  post pass records working_tree_dirty=true and cannot be reproduced")
        print("  by anyone from git. Commit the change, then run the post pass.")
        for line in dirty.splitlines()[:12]:
            print(f"    {line}")
        if n > 12:
            print(f"    ... and {n - 12} more")
        return 2

    B, L = Path(a.baseline), Path(a.live)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from settings import REGISTRY
        known = set(REGISTRY)
    except Exception:
        known = {a.universe}

    written, notwritten, unclassified = [], [], []
    for bp in list_dir(B):
        if bp.is_dir():
            continue
        lp = L / bp.name
        if lp.exists() and lp.stat().st_mtime >= a.since:
            written.append((bp, lp)); continue
        why = why_not_written(bp.stem, a.universe, a.arm, a.profile, known)
        (notwritten if why else unclassified).append((bp, why or "UNEXPLAINED"))

    print("=" * 88)
    print(f" GATE  {a.universe} {a.arm} profile={a.profile}   baseline {B}")
    print("=" * 88)
    print(f"  WRITTEN BY THIS CELL (compared) : {len(written)}")
    print(f"  NOT WRITTEN (listed, not counted): {len(notwritten)}")
    print(f"  UNCLASSIFIED                     : {len(unclassified)}")
    print()

    tally = {}
    stamped_dirty = []
    print("  --- COMPARED " + "-" * 73)
    for bp, lp in written:
        for side, q in (("baseline", bp), ("live", lp)):
            d0 = dirty_stamp(q)
            if d0:
                stamped_dirty.append((side, q.name, d0))
        v, d = gate_compare_compare(bp, lp)
        tally[v] = tally.get(v, 0) + 1
        if v != "EXACT":
            print(f"    {v:<8} {bp.name:<42} {d}")
    print(f"    {tally.get('EXACT', 0)} of {len(written)} byte-exact"
          + (f", {tally.get('ULP', 0)} within one ULP" if tally.get("ULP") else "")
          + (f", {tally.get('PROVENANCE', 0)} provenance-only" if tally.get("PROVENANCE") else "")
          + (f", {tally.get('DIFFERS', 0)} differ" if tally.get("DIFFERS") else ""))
    print()
    print("  --- NOT WRITTEN BY THIS CELL (never counted) " + "-" * 42)
    for bp, why in notwritten:
        print(f"    {bp.name:<42} {why}")
    if unclassified:
        print()
        print("  --- UNCLASSIFIED -- FATAL " + "-" * 61)
        for bp, _ in unclassified:
            print(f"    {bp.name:<42} the cell did not write it and no rule explains why")
        print("\nRESULT: FAIL -- an artefact went unwritten for a reason this tool cannot")
        print("  name. That is indistinguishable from a step that stopped writing.")
        return 2

    if stamped_dirty:
        print()
        print("  --- PASS RECORDED A DIRTY TREE -- FATAL " + "-" * 47)
        for side, name, (commit, n) in stamped_dirty:
            print(f"    {side:<8} {name:<38} commit {commit}, {n} modified or "
                  f"untracked file(s)")
        print("\n  That artefact was produced from a tree that is not in git, so")
        print("  nobody -- including whoever ran it -- can reproduce it. The tree was")
        print("  clean when the pass STARTED or the refusal above would have fired;")
        print("  it went dirty while the pass was running. Commit, then run again.")
        print("\nRESULT: FAIL -- the comparison is against something unreproducible.")
        return 2

    bad = tally.get("DIFFERS", 0)
    prov = tally.get("PROVENANCE", 0)
    print(f"\nRESULT: {'FAIL' if bad else 'PASS'} -- {len(written)} artefacts measured, "
          f"{tally.get('EXACT', 0)} byte-exact, "
          + (f"{prov} provenance-only, " if prov else "")
          + f"{bad} differing.")
    return 1 if bad else 0


def _cli_gate_compare():
    """`python checks.py gate_compare [ARGS]`: what running gate_compare.py did."""
    sys.exit(gate_compare())


# ======================================================================================
# naming_declare_check. From naming_declare_check.py (moved 2026-11-27).
# ======================================================================================
# naming_declare_check -- DECLARE OR FAIL, AND HONOUR OR FAIL.
# ===============================================================
#
# TWO GATES, AND THE SECOND IS THE ONE THAT MATTERS
#     GATE 1, DECLARE. Every site that writes an artefact must carry an inline
#     `# naming:` directive saying which axes its filename varies over. A site with
#     no directive is a FAILURE, not a default: the bug class being closed is a
#     silently omitted axis, and a permissive default reproduces it exactly.
#
#     GATE 2, HONOUR. A declaration is a CLAIM, not a proof. A site may declare
#     `arm,cadence,profile` and then write a bare literal that varies over nothing --
#     which is the same defect as a commit message asserting completion without
#     verifying it. So for every site declaring a non-empty axis set, this check
#     proves the claim: it emits the site's name under a NON-DEFAULT selection and
#     requires the tail settings.py computes to actually appear. A declaration that
#     does not survive that is a FAILURE, and until this gate existed a declared site
#     was worth no more than an undeclared one.
#
# WHY THE DIRECTIVE LIVES AT THE WRITER
#     A central table of 58 entries would be the fifth hardcoded list in this
#     repository, and it would drift the moment someone adds a writer without
#     knowing the table exists. The directive sits on the write call instead, so
#     discovery picks it up where it is true and the next person adding a writer
#     sees one on the line above.
#
# DIRECTIVE SYNTAX -- immediately above the write call, or on the enclosing `def`.
#     A directive above a call covers THAT CALL ONLY; the walk stops at the first
#     line that is not a comment, so it can never silently adopt the statement
#     after it. When a block of sibling writes shares one classification, the
#     directive belongs on the `def`, where it covers all of them and a reader
#     sees it before the block rather than inside it.
#     # naming: arm,cadence,profile     this name varies over exactly these axes
#     # naming: <axes> via <composer>   ... and <composer> is what builds it,
#     #                                 checked against its MEASURED coverage in
#     #                                 settings.CARRIES, not against its name
#     # naming: axis-free -- <reason>   invariant to every axis; reason required
#     # naming: delegated -- <where>    path arrives from a caller that declares it
#     # naming: DEFECT <axis> -- <why>  known to omit an axis it should carry
#
# WHY NON-DEFAULT IS THE ONLY HONEST TEST SELECTION
#     At an all-default selection every axis contributes "", so a profile-blind
#     writer and a correct one emit identical paths. The gate would pass on both.
#     HONOUR_SELECTION below is deliberately non-default on all FOUR axes. It
#     gained `tax` on 2026-09-17 with the tax axis itself, and that addition is the
#     whole of condition 2 of the tax acceptance test: at tax=off a tax-blind
#     writer and a tax-aware one emit identical paths, so the byte-exactness half
#     of that test is passed by a no-op. Only a non-default probe can tell them
#     apart, and only a declaration can be checked against it.

NAMING_DECLARE_CHECK_SKIP_DIRS = {"venv", ".git", "__pycache__", "node_modules"}
NAMING_DECLARE_CHECK_SKIP_PREFIX = ("forensic_snapshot_",)
SELF = {"settings.py"}
# This checker lives in checks.py since 2026-11-27. Its own section quotes the
# directive syntax, so that section is skipped; the rest of checks.py is scanned.
SELF_SECTION = ("checks.py", "# naming_declare_check. From naming_declare_check.py")
WRITERS = {"to_csv", "savefig", "to_parquet", "dump", "to_json", "write_text"}

DIRECTIVE = re.compile(r"#\s*naming:\s*(.+?)\s*$")

# Non-default on every axis, so no axis can hide behind an empty suffix.
HONOUR_SELECTION = {"arms": ["v1", "v3"], "cadence": 40, "profile": "tradeable",
                    "tax": True, "survivorship": "pit", "dd": 20, "capital": 5_000_000,
                    "impact": 0.003, "pcap": 0.1, "fixed": True, "buy_shortfall": "refuse"}

# THE MEMBERSHIP LIST IS GONE. Gate 2 used to ask "does this expression mention a
# blessed helper name?", which is a question about spelling. It now asks "does the
# composer this expression uses actually carry every axis the site declared?",
# which is a question about behaviour. settings.CARRIES holds the measured answer
# per composer; see the audit recorded above it. An expression whose composer is
# unknown carries nothing and fails -- a new helper must be measured before it can
# certify anything.


class Decl:
    __slots__ = ("kind", "axes", "reason", "line", "composer")

    def __init__(self, kind, axes=(), reason="", line=0):
        self.kind, self.axes, self.reason, self.line = kind, tuple(axes), reason, line
        self.composer = ""


def parse_directive(text, line):
    m = DIRECTIVE.search(text)
    if not m:
        return None
    body = m.group(1).strip()
    low = body.lower()
    if low.startswith("axis-free"):
        return Decl("axis-free", (), body.partition("--")[2].strip(), line)
    if low.startswith("delegated"):
        return Decl("delegated", (), body.partition("--")[2].strip(), line)
    if low.startswith("defect"):
        rest = body[6:].strip()
        axis = rest.partition("--")[0].strip().strip(",")
        return Decl("DEFECT", [a.strip() for a in axis.split(",") if a.strip()],
                    rest.partition("--")[2].strip(), line)
    # AXES FIRST, THEN AN OPTIONAL COMPOSER, THEN AN OPTIONAL REASON.
    #   # naming: arm,cadence,profile via artefact_tag -- why
    # Splitting on "--" before the comma split is what stops a reason clause being
    # parsed as three more axis names, which it was: audit_step declared
    # "profile -- every daily_* artefact here is named through" as an axis.
    head = body.split("--")[0].strip()
    reason = body.partition("--")[2].strip()
    composer = ""
    if " via " in head:
        head, _, composer = head.partition(" via ")
        composer = composer.strip()
    d = Decl("axes", [a.strip() for a in head.split(",") if a.strip()], reason, line)
    d.composer = composer
    return d


def _iter_py():
    for p in list_dir(ROOT, "*.py", recursive=True):
        rel = p.relative_to(ROOT)
        if set(rel.parts) & NAMING_DECLARE_CHECK_SKIP_DIRS or rel.name in SELF:
            continue
        if any(str(rel).startswith(x) for x in NAMING_DECLARE_CHECK_SKIP_PREFIX):
            continue
        yield rel, p


def _walk_up(lines, ln):
    """The directive in the contiguous comment block immediately above a call.

    WALKING THE WHOLE BLOCK, not a fixed lookback. A directive that needs two
    lines of explanation sits further from its call than a one-liner does, and a
    fixed window silently dropped exactly those -- the longest-explained sites,
    which are the ones most worth reading. The walk stops at the first line that
    is neither a comment nor blank, so it can never cross into another statement.
    """
    i = ln - 2                      # 0-indexed line directly above the call
    while i >= 0:
        raw = lines[i].strip()
        if raw.startswith("#"):
            d = parse_directive(lines[i], i + 1)
            if d:
                # THE REASON CONTINUES across the comment lines beneath the
                # directive. Truncating at the first newline kept the shortest
                # half of every explanation -- "has no" -- and dropped the part
                # that says what goes wrong.
                tail_txt = []
                j = i + 1
                while j < len(lines) and lines[j].strip().startswith("#"):
                    if parse_directive(lines[j], j + 1):
                        break
                    tail_txt.append(lines[j].strip().lstrip("#").strip())
                    j += 1
                if tail_txt:
                    d.reason = " ".join([d.reason] + tail_txt).strip()
                return d
            i -= 1
            continue
        if raw == "":
            i -= 1
            continue
        return None
    return None


def discover():
    """Every artefact-writing call, with the declaration in force at that call."""
    sites = {}
    for rel, p in _iter_py():
        src = p.read_text(encoding="utf-8", errors="replace")
        lines = src.splitlines()
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        own = range(0)
        if str(rel) == SELF_SECTION[0] and SELF_SECTION[1] in src:
            # this checker's own section: from its header to the next section header
            a_ = next(i for i, l in enumerate(lines) if l.startswith(SELF_SECTION[1]))
            b_ = next((i for i in range(a_ + 1, len(lines))
                       if lines[i].startswith("# ") and ". From " in lines[i]
                       and "(moved 2026-11-27)" in lines[i]), len(lines))
            own = range(a_ + 1, b_ + 1)
        fn_at, fn_decl = {}, {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # SAME WALK AS A CALL-LEVEL DIRECTIVE. A fixed two-line lookback
                # here dropped any def whose directive ran to more than one line,
                # which is every def whose reason was worth writing down.
                d = _walk_up(lines, node.lineno)
                for ln in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                    fn_at.setdefault(ln, node.name)
                    if d:
                        fn_decl.setdefault(ln, d)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            nm = f.attr if isinstance(f, ast.Attribute) else (
                f.id if isinstance(f, ast.Name) else None)
            if nm not in WRITERS:
                continue
            ln = node.lineno
            if ln in own:
                continue
            decl = _walk_up(lines, ln) or fn_decl.get(ln)
            try:
                expr = ast.unparse(node.args[1] if nm == "dump" and len(node.args) > 1
                                   else node.args[0]) if node.args else ""
            except Exception:
                expr = ""
            key = f"{rel}::{fn_at.get(ln, '<module>')}"
            sites.setdefault(key, []).append((ln, nm, expr, decl))
    return sites


def honour_probe():
    """Prove settings.tail() moves under HONOUR_SELECTION before trusting it."""
    import portfolio as ar
    import settings
    ar.set_selection(HONOUR_SELECTION["arms"])
    settings.cadence.set_selection(HONOUR_SELECTION["cadence"])
    settings.profile_axis.set_selection(HONOUR_SELECTION["profile"])
    settings.tax.set_selection(HONOUR_SELECTION["tax"])
    settings.survivorship_axis.set_selection(HONOUR_SELECTION["survivorship"])
    settings.dd_axis.set_selection(settings.dd_axis.make(HONOUR_SELECTION["dd"]))
    settings.capital_axis.set_selection(HONOUR_SELECTION["capital"])
    settings.impact_axis.set_selection(HONOUR_SELECTION["impact"])
    settings.pcap_axis.set_selection(HONOUR_SELECTION["pcap"])
    settings.fixed_axis.set_selection(HONOUR_SELECTION["fixed"])
    settings.shortfall_axis.set_selection(HONOUR_SELECTION["buy_shortfall"])
    return settings, settings.tail()


def added_lines(base):
    """{path: {line numbers ADDED relative to `base`}}, from git diff -U0.

    THE RATCHET EXISTS BECAUSE A BACKLOG DOES NOT BLOCK THE NEXT ENTRANT. The
    same defect recurred here within three days of being fixed, because the fix
    closed the instances it found and nothing stopped a new writer arriving
    undeclared. Gate 1 over the whole repository cannot be made blocking today --
    129 calls are undeclared. Gate 1 over the lines this change ADDED can be, and
    that is the half that keeps the count from growing.
    """
    import subprocess
    try:
        out = subprocess.run(
            ["git", "diff", "-U0", base, "--", "*.py"],
            cwd=ROOT, capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    added, cur = {}, None
    for line in out.stdout.splitlines():
        if line.startswith("+++ b/"):
            cur = line[6:].strip()
        elif line.startswith("@@") and cur:
            # @@ -a,b +c,d @@
            try:
                seg = line.split("+")[1].split("@@")[0].strip()
                start, _, cnt = seg.partition(",")
                start, cnt = int(start), int(cnt or 1)
            except (ValueError, IndexError):
                continue
            added.setdefault(cur, set()).update(range(start, start + cnt))
    return added


def naming_declare_check():
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-known-defects", action="store_true")
    ap.add_argument("--list-undeclared", action="store_true")
    ap.add_argument("--gate-declared-only", action="store_true",
                    help="block on Gate 2, on DEFECT, and on undeclared calls "
                         "inside a site that is already declared; report "
                         "undeclared calls in wholly-undeclared sites without "
                         "blocking. A site enters the gated set the moment "
                         "someone declares it and cannot leave.")
    ap.add_argument("--ratchet", metavar="BASE", default=None,
                    help="also block on any write call ADDED relative to BASE "
                         "(e.g. HEAD, origin/main) that carries no directive")
    args = ap.parse_args()

    settings, tail = honour_probe()
    if not tail:
        print("ABORT: settings.tail() is empty under the non-default honour "
              "selection. The authority itself is broken; every honour result "
              "below would be vacuous.")
        return 2

    sites = discover()
    undeclared, axis_free, delegated, defects, honoured, dishonoured = (
        [], [], [], [], [], [])

    for key in sorted(sites):
        calls = sites[key]
        undecl = [c for c in calls if c[3] is None]
        if undecl:
            undeclared.append((key, [c[0] for c in undecl]))
        for ln, nm, expr, d in calls:
            if d is None:
                continue
            if d.kind == "axis-free":
                axis_free.append((key, ln, d))
            elif d.kind == "delegated":
                delegated.append((key, ln, d))
            elif d.kind == "DEFECT":
                defects.append((key, ln, d))
            else:
                # GATE 2. Declared axes must be a subset of what the composer in
                # this expression provably carries.
                # A COMPOSER NAMED IN THE DIRECTIVE WINS over sniffing the write
                # expression. audit_step binds `tag = artefact_tag(...)` several
                # lines above its writes, so the expression at the write site says
                # only `{tag}` -- textual sniffing cannot see the composer that
                # actually built the name, and guessing from `{tag}` would credit
                # any variable that happened to be called tag.
                carried = (settings.carried_axes(d.composer) if d.composer
                           else settings.carried_axes(expr))
                missing = set(d.axes) - carried
                if missing:
                    dishonoured.append((key, ln, d, expr, sorted(missing), sorted(carried)))
                else:
                    honoured.append((key, ln, d, expr))

    n_sites = len(sites)
    n_calls = sum(len(v) for v in sites.values())
    print("=" * 78)
    print(" NAMING AUTHORITY -- DECLARE OR FAIL, HONOUR OR FAIL")
    print("=" * 78)
    print(f"  honour selection : arms={HONOUR_SELECTION['arms']} "
          f"cadence={HONOUR_SELECTION['cadence']} "
          f"profile={HONOUR_SELECTION['profile']} "
          f"tax={HONOUR_SELECTION['tax']} "
          f"survivorship={HONOUR_SELECTION['survivorship']} "
          f"dd={HONOUR_SELECTION['dd']} capital={HONOUR_SELECTION['capital']} "
          f"impact={HONOUR_SELECTION['impact']} pcap={HONOUR_SELECTION['pcap']} "
          f"fixed={HONOUR_SELECTION['fixed']}  "
          f"-> tail {tail!r}")
    print(f"  sites / write calls          : {n_sites} / {n_calls}")
    print(f"  GATE 1  undeclared calls     : {sum(len(v) for _, v in undeclared)}"
          f"  across {len(undeclared)} site(s)")
    print(f"  GATE 2  declared + honoured  : {len(honoured)}")
    print(f"  GATE 2  declared, NOT honoured: {len(dishonoured)}")
    print(f"          axis-free declared   : {len(axis_free)}")
    print(f"          delegated            : {len(delegated)}")
    print(f"          DEFECT               : {len(defects)}")
    print()

    if dishonoured:
        print("-" * 78)
        print(" GATE 2 FAILURES -- declares an axis set it does not honour")
        print("-" * 78)
        for key, ln, d, expr, missing, carried in dishonoured:
            print(f"  {key}:{ln}")
            print(f"      declares : {','.join(d.axes)}")
            print(f"      writes   : {expr[:78]}")
            print(f"      carries  : {','.join(carried) or '(nothing -- composer unknown)'}")
            print(f"      MISSING  : {','.join(missing)}"
                  f"   -- under {tail!r} those axes vanish from the name")
        print()

    if defects:
        print("-" * 78)
        print(" KNOWN DEFECTS -- declared, and still wrong")
        print("-" * 78)
        for key, ln, d in defects:
            print(f"  {key}:{ln}")
            print(f"      missing axis : {', '.join(d.axes)}")
            print(f"      consequence  : {d.reason}")
        print()

    if undeclared and args.list_undeclared:
        print("-" * 78)
        print(" GATE 1 FAILURES -- artefact written with no `# naming:` directive")
        print("-" * 78)
        for key, lns in undeclared:
            print(f"  {key}  (lines {', '.join(map(str, lns))})")
        print()

    # THE GATED SET. A site is in it as soon as ANY of its calls is declared.
    # Undeclared calls inside such a site block; undeclared calls in a site nobody
    # has touched yet report only. That enforces at zero from the first day
    # instead of waiting for a backlog to clear with nothing holding the line.
    declared_sites = {k for k in sites
                      if any(c[3] is not None for c in sites[k])}
    blocking_undeclared = [(k, v) for k, v in undeclared if k in declared_sites]

    ratchet_hits = []
    if args.ratchet:
        add = added_lines(args.ratchet)
        if add is None:
            print(f"RATCHET: could not diff against {args.ratchet!r}; "
                  f"treating as a failure rather than a pass.")
            ratchet_hits = [("<git diff failed>", 0)]
        else:
            for key in sorted(sites):
                path = key.split("::")[0]
                for ln, nm, expr, d in sites[key]:
                    if d is None and ln in add.get(path, ()):
                        ratchet_hits.append((key, ln))

    if ratchet_hits:
        print("-" * 78)
        print(f" RATCHET FAILURES -- write call added since {args.ratchet},"
              f" no `# naming:` directive")
        print("-" * 78)
        for key, ln in ratchet_hits:
            print(f"  {key}:{ln}")
        print()

    gate1_blocking = blocking_undeclared if args.gate_declared_only else undeclared
    failed = bool(gate1_blocking) or bool(dishonoured) or bool(ratchet_hits) or (
        bool(defects) and not args.allow_known_defects)
    print("RESULT:", "FAIL" if failed else "PASS")
    if args.gate_declared_only:
        n_report = sum(len(v) for k, v in undeclared if k not in declared_sites)
        print(f"  gated set: {len(declared_sites)} site(s) declared and enforced.")
        if n_report:
            print(f"  GATE 1 (reporting only): {n_report} undeclared call(s) in "
                  f"{len([1 for k, _ in undeclared if k not in declared_sites])} "
                  f"site(s) nobody has declared yet. Not blocking.")
    if gate1_blocking:
        print(f"  GATE 1 (blocking): "
              f"{sum(len(v) for _, v in gate1_blocking)} write call(s) carry no "
              f"directive. --list-undeclared to see them.")
    if ratchet_hits:
        print(f"  RATCHET: {len(ratchet_hits)} newly added write call(s) undeclared.")
    if dishonoured:
        print(f"  GATE 2: {len(dishonoured)} declaration(s) are unproven claims.")
    if defects and not args.allow_known_defects:
        print(f"  {len(defects)} site(s) declared DEFECT and not yet fixed.")
    return 1 if failed else 0


def _cli_naming_declare_check():
    """`python checks.py naming_declare_check [ARGS]`: what running naming_declare_check.py did."""
    sys.exit(naming_declare_check())


# ======================================================================================
# tax_acceptance_check. From tax_acceptance_check.py (moved 2026-11-27).
# ======================================================================================
# tax_acceptance_check -- the tax axis is inert at its default. BOTH HALVES.
#
#     run standalone; no caches, no engine, no network
#
# WHY THIS IS TWO CONDITIONS AND NOT ONE
#     The stated acceptance test for the tax axis is "with tax off, every existing
#     artefact reproduces byte-exact". That test is necessary and it is NOT
#     sufficient, for a reason settings.py already writes down about a different
#     axis:
#
#         AN OMITTED AXIS AND A DEFAULT AXIS PRODUCE THE SAME STRING.
#
#     At tax=off every composer contributes "", so a writer that carries the tax
#     axis and a writer that has never heard of it emit identical paths. A
#     completely empty implementation -- no settings.tax, no composer edits, nothing --
#     passes the byte-exactness test perfectly. It is passed by doing nothing,
#     which is precisely how site 12 survived: a research-profile run and a
#     profile-blind writer were byte-identical, and they differed only when
#     somebody finally ran `tradeable`.
#
#     So this check asks two questions:
#
#       CONDITION 1  at the default, does every composer emit the SAME STRING it
#                    emitted before the tax axis existed?   (nothing moved)
#       CONDITION 2  off the default, does every composer MOVE, and does every
#                    declared write site still honour its declaration?
#                                                           (something is there)
#
#     Condition 1 alone is satisfied by a no-op. Condition 2 alone is satisfied by
#     an implementation that renames published files. Neither is the acceptance
#     test; both together are.
#
#     CONDITION 3 pins the 365-day long-term boundary. CONDITION 4 (2026-09-25)
#     pins the end-of-window rules against hand-worked numbers: the last partial
#     financial year settled on the final session; the investable buy & hold
#     selling nothing in the headline and paying the strategy's own sell charge
#     and tax when sold on the last day; the strategy keeping its holdings in the
#     headline and ending flat with end_sale=True.
#
# CONDITION 1 IS MEASURED AGAINST git HEAD, NOT AGAINST A TYPED-IN EXPECTATION
#     A hardcoded list of expected default names would be a restatement of what
#     this file's author believed the names were -- the same class of defect as a
#     report that restates its output instead of deriving it. Instead the
#     composers are called in a clean checkout of HEAD and again in the working
#     tree, at an all-default selection, and the two strings are compared. A name
#     that moves is reported with both spellings.
#
# WHAT THIS DOES NOT COVER, STATED RATHER THAN IMPLIED
#     It checks NAMES, not CONTENTS. Byte-exactness of a file's bytes is a
#     property of the engine, and the gate that actually tests it is
#     heldout_prereg_run.py's reproduction check against the shipped
#     v2FINAL_equity.csv. This check cannot run that -- it needs score caches --
#     and it says so rather than implying coverage it does not have.
#
#     The retired-universe manifest (171 hashes, deleted from the tree on
#     2026-09-24; git show 50562ed:RETIRED_UNIVERSES-manifest.txt) is not verified
#     here: its paths are relative to forensic_snapshot_20260911T0100/, which is
#     not present in this tree.

# The probe body. Run verbatim in HEAD and in the working tree, so the two
# answers cannot diverge through the probe rather than through the composers.
PROBE = r'''
import sys, pathlib, itertools, tempfile, json
R = pathlib.Path(sys.argv[1])
for p in (R, R/"results", R/"nautilus"): sys.path.insert(0, str(p))
try:
    import portfolio as arm_reg
except ImportError:          # a checkout from before portfolio.py (2026-11-27)
    import arms.registry as arm_reg
try:
    import settings
    cadence, profiles, naming = settings.cadence, settings.profile_axis, settings
    tax, survivorship_axis = settings.tax, settings.survivorship_axis
    AXIS_NS = {"settings": settings, "_dda": settings.dd_axis, "_capa": settings.capital_axis,
               "_impa": settings.impact_axis, "_pca": settings.pcap_axis,
               "_fxa": settings.fixed_axis, "_sta": settings.start_axis,
               "_bsf": settings.shortfall_axis}
except ImportError:          # a checkout from before settings.py (2026-11-27)
    import cadence, profiles, naming, tax, survivorship_axis
    import dd_axis, capital_axis, impact_axis, pcap_axis, fixed_axis, start_axis, buy_shortfall
    AXIS_NS = {"_dda": dd_axis, "_capa": capital_axis, "_impa": impact_axis, "_pca": pcap_axis,
               "_fxa": fixed_axis, "_sta": start_axis, "_bsf": buy_shortfall}

D = pathlib.Path(tempfile.mkdtemp())
for c in itertools.product(["","_r40"],["","_tradeable"],["","_tax"]):
    (D / f"v2FINAL_equity{''.join(c)}.csv").write_text("x")
for c in itertools.product(["","_v1"],["","_r40"],["","_tradeable"],["","_tax"]):
    (D / f"chart_midcap150_FINAL{''.join(c)}.png").write_text("x")

out = {}
out["naming.tail"] = naming.tail()
out["naming.name"] = naming.name("stem", ".csv")
out["selection_suffix"] = arm_reg.selection_suffix()

# SFX is an INLINE expression inside a function body, not a callable, so it is
# read out of the source and evaluated. Indentation is stripped line by line --
# a naive slice carries the function body's indent into eval() and fails with a
# syntax error that LOOKS like a moved name.
if (R/"backtest_runs.py").exists():
    src = (R/"backtest_runs.py").read_text().splitlines()
    i0 = next(n for n, l in enumerate(src) if "From results/v34_common.py" in l)
else:                        # a checkout from before backtest_runs.py (2026-11-27)
    src = (R/"results"/"v34_common.py").read_text().splitlines()
    i0 = 0
i = next(n for n, l in enumerate(src) if n >= i0 and l.strip().startswith("SFX = "))
buf, depth = [], 0
for l in src[i:]:
    buf.append(l.strip())
    depth += l.count("(") - l.count(")")
    if depth <= 0 and buf[-1]:
        break
expr = " ".join(buf)[len("SFX = "):].strip()
ns = {"arm_reg": arm_reg, "cadence": cadence, "profiles": profiles, "_tax": tax,
      "_sva": survivorship_axis, **AXIS_NS}
try: out["SFX"] = eval(expr, ns)
except Exception as e: out["SFX"] = f"EVALFAIL {type(e).__name__}: {e}"

try:
    import backtest_runs as audit_step, backtest_runs as engine_v2_final
    import reports as make_chart, reports as mcu
    _ci_comb = mcu._ci_combined
except ImportError:          # a checkout from before backtest_runs.py (2026-11-27)
    import audit_step, engine_v2_final, make_chart
    import make_combined_universes as mcu
    _ci_comb = mcu._ci
class _U: tag = "midcap150"
out["artefact_tag"] = audit_step.artefact_tag(_U(), "v1")
out["_c"]   = str(engine_v2_final._c(D / "v2FINAL_equity.csv"))
out["_ci_chart"] = str(make_chart._ci(D / "v2FINAL_equity.csv"))
out["_ci_comb"]  = str(_ci_comb(D / "v2FINAL_equity.csv"))
out["chart_path"] = pathlib.Path(str(make_chart.chart_path(D, "chart_midcap150_FINAL", ["v2","v1"]))).name
out["combined_chart_path"] = pathlib.Path(
    str(mcu.combined_chart_path(D, ["midcap150","nifty100"]))).name
out["_c"] = pathlib.Path(out["_c"]).name
out["_ci_chart"] = pathlib.Path(out["_ci_chart"]).name
out["_ci_comb"]  = pathlib.Path(out["_ci_comb"]).name
print(json.dumps(out))
'''


def _run_probe(tree):
    """The probe's dict, evaluated inside `tree` at an all-default selection."""
    f = Path(tempfile.mkdtemp()) / "probe.py"
    # naming: axis-free -- this is the PROBE SOURCE, written to a throwaway temp
    # directory so it can be executed inside another checkout. It is not an
    # artefact, nothing reads it, and it is deleted with the temp dir. Declared
    # rather than left bare because this file was itself the 112th undeclared
    # write call when it landed -- the ratchet exists to stop exactly that, and a
    # checker that adds a violation while enforcing the rule is the worst kind.
    f.write_text(PROBE)
    r = subprocess.run([sys.executable, str(f), str(tree)],
                       capture_output=True, text=True, cwd=str(tree))
    if r.returncode != 0:
        raise RuntimeError(f"probe failed in {tree}:\n{r.stderr[-2000:]}")
    import json
    return json.loads(r.stdout.strip().splitlines()[-1])


def condition_1():
    """Nothing moved at the default. Measured against a clean checkout of HEAD."""
    print("\n  CONDITION 1 -- at tax=off, no composed name moved")
    with tempfile.TemporaryDirectory() as td:
        head = Path(td) / "head"
        r = subprocess.run(["git", "worktree", "add", "--detach", str(head), "HEAD"],
                           cwd=str(ROOT), capture_output=True, text=True)
        if r.returncode != 0:
            print("    UNAVAILABLE: could not create a HEAD worktree")
            print(f"    {r.stderr.strip()}")
            return None
        try:
            before = _run_probe(head)
            after = _run_probe(ROOT)
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(head)],
                           cwd=str(ROOT), capture_output=True)
    keys = sorted(set(before) | set(after))
    moved = [(k, before.get(k), after.get(k)) for k in keys
             if before.get(k) != after.get(k)]
    for k in keys:
        mark = "MOVED" if before.get(k) != after.get(k) else "same "
        print(f"    {mark}  {k:<22} {after.get(k)!r}")
    if moved:
        print(f"\n    FAIL: {len(moved)} composed name(s) moved at the default:")
        for k, b, a in moved:
            print(f"      {k}: HEAD {b!r}  ->  working tree {a!r}")
        return False
    print(f"    PASS: {len(keys)} composers, every default name character-identical to HEAD")
    return True


def condition_2():
    """Something is actually there. The axis moves, and declarations honour it."""
    print("\n  CONDITION 2 -- off the default, the axis is real and declared")
    sys.path.insert(0, str(ROOT))
    from settings import tax, cadence
    import settings
    import portfolio as arm_reg

    for m in (cadence, settings.profile_axis, arm_reg, tax):
        m.set_selection(None)
    base = settings.tail()
    tax.set_selection(True)
    on = settings.tail()
    tax.set_selection(None)
    ok_axis = (base == "" and on == "_tax" and "tax" in settings.AXES)
    print(f"    tail at default {base!r} -> at tax=on {on!r}   "
          f"{'PASS' if ok_axis else 'FAIL'}")

    # tax must follow the first three, and any later axis must be appended after
    # it, or every existing non-default artefact is renamed. survivorship was
    # appended after tax on 2026-10-10.
    ok_last = settings.AXES[:4] == ("arm", "cadence", "profile", "tax")
    print(f"    tax is fourth, later axes appended after it      "
          f"{'PASS' if ok_last else 'FAIL -- appending is what keeps _r40/_tradeable in place'}")

    # No entry may credit an axis by live reference to AXES.
    # CODE ONLY. The prose above CARRIES quotes the construct it replaced, so a
    # bare substring search over the whole file matches the explanation and
    # reports the defect it is explaining. Comments and docstrings are stripped.
    import io, tokenize
    src = (ROOT / "settings.py").read_text()
    code = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type not in (tokenize.COMMENT, tokenize.STRING):
            code.append(tok.string)
    ok_lit = "frozenset(AXES)" not in "".join(code).replace(" ", "")
    print(f"    CARRIES holds no frozenset(AXES) live reference   "
          f"{'PASS' if ok_lit else 'FAIL -- a new axis would be auto-credited unmeasured'}")

    # Every composer a site may name must be measured for tax.
    unmeasured = [k for k, v in settings.CARRIES.items() if "tax" not in v
                  and k != "selection_suffix"]
    ok_meas = not unmeasured
    print(f"    every composer measured for tax                  "
          f"{'PASS' if ok_meas else 'FAIL ' + str(unmeasured)}")

    # THE FROZEN ENGINE MUST STAY OFF THIS AXIS, AND THIS IS HOW IT IS ENFORCED.
    #
    # The phase-1 design said run.py should refuse --tax on for the two retired
    # universes, taken from settings.cadence's docstring, which records exactly such a
    # refusal for the cadence axis. THAT IS NOT IMPLEMENTABLE: both were deleted on
    # 2026-09-11, settings.py then held only midcap150 and nifty100, and
    # run.py:396 records that the cadence skip-list was itself dropped because "every
    # universe honours every cadence now". There is no selection left to refuse.
    #
    # What the design was actually protecting is still real -- results/
    # the engine_core section is the frozen engine behind the hash-pinned artefacts and
    # must not grow a tax path. So the refusal is replaced by an assertion on the
    # file itself, which is stronger: it cannot be satisfied by a selection that
    # nobody makes, and it fires on the edit rather than on the run.
    _src = (ROOT / "checks.py").read_text()
    _a = _src.index("\n# engine_core. From results/engine_core.py") + 1   # the section header
    eng = _src[_a:_src.index("\n# ======", _src.index("\n", _a) + 100)]
    eng_clean = not any(t in eng for t in ("import tax", "tax_util", "tax_enabled",
                                           "Ledger", "CGT_REGIME"))
    print(f"    engine_core.py carries no tax path                "
          f"{'PASS' if eng_clean else 'FAIL -- the frozen engine must stay off this axis'}")

    # The declaration gate must exercise tax, and no declared site may break.
    r = subprocess.run([sys.executable, str(ROOT / "checks.py"), "naming_declare_check"],
                       capture_output=True, text=True, cwd=str(ROOT))
    txt = r.stdout
    ok_probe = "tax=True" in txt and "_tradeable_tax" in txt
    nothon = [l for l in txt.splitlines() if "NOT honoured" in l]
    ok_hon = bool(nothon) and nothon[0].strip().endswith("0")
    print(f"    naming_declare_check honour probe carries tax    "
          f"{'PASS' if ok_probe else 'FAIL'}")
    print(f"    declared sites still honour their axes           "
          f"{'PASS' if ok_hon else 'FAIL'}   ({nothon[0].strip() if nothon else 'not reported'})")
    return all([ok_axis, ok_last, ok_lit, ok_meas, eng_clean, ok_probe, ok_hon])


def condition_3():
    """The LTCG holding-period boundary, asserted rather than assumed.

    WHY THIS FIXTURE EXISTS. The rationale below was rewritten 2026-09-19,
    because the one it replaced had been overtaken by the data.

    IT USED TO SAY THE PANEL COULD NOT REACH THE BOUNDARY. It said no run of
    this pipeline ever exercises `is_long = held >= LTCG_HOLD_DAYS` in its True
    state, citing the longest real lot at 326 days with 39 days of headroom, and
    it justified the synthetic lots on that ground -- they were needed BECAUSE
    the real data could not get there. **The panel reached it.** The 2026-09-18
    four-universe runs contain four lots over 365 days:

        nifty100   SOLARINDS   443 days      nifty50   TRENT       588 days
        nifty50    TATACONSUM  445 days      nifty50   TRENT       383 days

    all four routed to `long_old` and taxed at LTCG_RATE["old"]. The True state
    is exercised in production now, on two of four universes.

    THE FIXTURES STAY, AND THE REASON IS A BETTER ONE THAN THE OLD REASON.
    Synthetic lots at 364/365/366 test the boundary DETERMINISTICALLY: exactly
    one day either side, every run, independent of which universes are wired,
    which arm is selected, what the cadence is, or whether any real lot happens
    to land near 365 this month. Real lots at 383 and 588 days exercise the long
    branch but say nothing about where the branch begins -- they would pass
    identically under `>`, under `>= 364` and under `>= 380`. A boundary test
    has to sit ON the boundary, and nothing in the panel is placed there on
    purpose.

    So the old justification is gone and the fixtures are not: they were never
    really a substitute for unreachable data, they were a boundary test, and a
    boundary test does not become unnecessary when the region beyond it becomes
    occupied.

    364 -> short, 365 -> long, 366 -> long.  The comparison is `>=`, so 365 is
    the FIRST long-term day, not the last short-term one. An edit to `>` would
    move every 365-day lot from 12.5% to 20% and no existing artefact would
    change, because no artefact has a lot at EXACTLY 365 days in it -- the four
    real long lots are at 383 and beyond and would survive the edit untouched.
    This condition is still the only thing that would notice.
    """
    import pandas as pd
    sys.path.insert(0, str(ROOT / "results"))
    import costs

    # SUPERSEDED 2026-10-14: the boundary is no longer `held_days >= 365` but
    # MORE THAN TWELVE CALENDAR MONTHS (costs.is_long_term), by the owner's
    # decision to follow the Act rather than section 3.2 of the document. The
    # rationale above is kept as the record; the fixtures below are the new
    # boundary, each one day either side of buy date + 12 months, and a leap-year
    # lot the old day count got wrong.
    cases = (
        ("2023-01-31", "2024-01-31", False),   # exactly 12 months: not MORE than
        ("2023-01-31", "2024-02-01", True),    # one day past
        ("2023-03-01", "2024-02-29", False),   # 365 days, under 12 months (long by the old rule)
        ("2023-03-01", "2024-03-01", False),   # 366 days, exactly 12 months
        ("2023-03-01", "2024-03-02", True),
    )
    dates = [pd.Timestamp("2023-01-01"), pd.Timestamp("2027-04-01")]

    print("\n  CONDITION 3 -- the long-term boundary: more than 12 calendar months")
    ok_all = True
    for b_, s_, want_long in cases:
        buy, sell = pd.Timestamp(b_), pd.Timestamp(s_)
        led = costs.Ledger(dates)
        led.buy("FIXTURE", 10, 100.0, buy)
        led.sell("FIXTURE", 10, 110.0, sell)
        row = led.rows[-1]
        want_arm = "long" if want_long else "short"
        got_arm = ("long_" if row["is_long"] else "short_") + costs.regime_of(sell)
        ok = bool(row["is_long"]) == want_long and got_arm.startswith(want_arm)
        ok_all = ok_all and ok
        print(f"    bought {b_} sold {s_} ({(sell - buy).days}d)  is_long="
              f"{str(bool(row['is_long'])):<5} bucket={got_arm:<11} expect {want_arm:<5} "
              f"{'PASS' if ok else 'FAIL'}")
        assert ok, (f"LTCG boundary wrong: bought {b_}, sold {s_} -> is_long="
                    f"{bool(row['is_long'])}, expected {want_long} (more than "
                    f"{costs.LTCG_HOLD_MONTHS} calendar months).")
    assert costs.LTCG_HOLD_MONTHS == 12
    print(f"    LTCG_HOLD_MONTHS == 12                           PASS")
    return ok_all


def condition_4():
    """The end-of-window rules of 2026-09-25, each against a hand-worked number.

      4a  the last, partial financial year is SETTLED on the final session, after
          its fills, on realised gains, with the document's netting and the full
          annual exemption; an earlier year is still assessed under section 3(9)
      4b  the investable buy & hold: the headline sells nothing, so it pays no
          tax and no sell charge; "sold on the last day" pays the strategy's own
          sell charge (calc_tc) and long-term tax on the realised gain
      4c  the strategy: the headline keeps its holdings at the end; end_sale=True
          ends with none, and its tax is exactly tax_for_fy over what it realised

    Synthetic data only: no caches, no panel, no network.
    """
    import numpy as np
    import pandas as pd
    for p in (ROOT, ROOT / "results"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import costs
    import backtest_runs as bh_held
    import portfolio as TE
    from market_data import precompute

    print("\n  CONDITION 4 -- end-of-window settlement and the last-day sale")

    # ---- 4a. Partial-year settlement, worked by hand ------------------------
    dates = pd.bdate_range("2026-03-02", "2026-05-29")
    led = costs.Ledger(dates)
    fills = {   # date -> [(side, sym, qty, price)]
        pd.Timestamp("2026-03-10"): [("SELL", "D", 10, 150.0)],
        pd.Timestamp("2026-04-06"): [("BUY", "A", 100, 100.0), ("BUY", "C", 50, 200.0)],
        pd.Timestamp("2026-05-04"): [("SELL", "A", 100, 110.0), ("SELL", "B", 1000, 400.0)],
        pd.Timestamp("2026-05-05"): [("SELL", "C", 50, 190.0)],
    }
    led.buy("D", 10, 100.0, pd.Timestamp("2025-04-10"))      # FY2025-26, short
    led.buy("B", 1000, 100.0, pd.Timestamp("2025-01-15"))    # held 474 days, long
    paid = {}
    for d in dates:
        due = led.due_on(d)
        for side, sym, q, pr in fills.get(d, []):
            (led.buy if side == "BUY" else led.sell)(sym, q, pr, d)
        due += led.due_on(d, after_fills=True)
        if due:
            paid[d] = due
    # FY2025-26: short_new +500 -> 500 x 20% = 100, plus 4% cess = 104, assessed
    #   2026-03-31 (a Tuesday, inside FY2025-26, so after that day's fills).
    # FY2026-27: short_new +1,000 - 500 = 500 -> 100; long_new 300,000 less the
    #   Rs 1,25,000 exemption = 175,000 x 12.5% = 21,875; 21,975 plus 4% cess =
    #   22,854, settled on the last session 2026-05-29. (Before the cess was
    #   charged, 2026-10-14, these were 100 and 21,975.)
    want = {pd.Timestamp("2026-03-31"): 104.0, pd.Timestamp("2026-05-29"): 22_854.0}
    ok_a = (set(paid) == set(want)
            and all(abs(paid[d] - want[d]) < 1e-6 for d in want)
            and led.settled_at_end == {2026})
    stmt, _ = costs.liability_schedule(pd.DataFrame(led.rows), dates)
    r26 = stmt[stmt["fy"] == 2026].iloc[0]
    ok_a = ok_a and bool(r26["assessed"]) and r26["assessed_basis"] == "backtest end" \
        and abs(float(r26["total_tax"]) - 22_854.0) < 1e-6
    print(f"    4a partial year: paid {dict((str(k.date()), round(v, 2)) for k, v in paid.items())}"
          f"  expect {{'2026-03-31': 104.0, '2026-05-29': 22854.0}}  "
          f"{'PASS' if ok_a else 'FAIL'}")
    assert ok_a, f"end-of-window settlement: paid {paid}, expected {want}"

    # ---- 4b. Buy & hold, headline and last-day sale, worked by hand ---------
    bd = pd.bdate_range("2025-05-01", "2026-05-29")
    px = pd.DataFrame({"X": 100.0, "Y": 200.0}, index=bd)
    op = px.copy()
    px.iloc[-1] = [140.0, 170.0]
    op.iloc[-1] = [150.0, 180.0]
    r = bh_held.held_lots(px, op, bd)
    cash = TE.START_CAPITAL
    qty, bpx = {}, {}
    # Fill prices to the paisa (costs.fill_price): 100 x 1.0015 = 100.15 and
    # 200 x 1.0015 = 200.30 to buy; 150 x 0.9985 = 149.775, a double just above the
    # half, sells at 149.78, and 180 x 0.9985 at 179.73.
    buy_px = {"X": 100.15, "Y": 200.30}
    sell_px = {"X": 149.78, "Y": 179.73}
    # The construction's own rule: equal rupees per name, a name skipped when
    # the cash left cannot pay for it and its charge. Here X's buy charge leaves
    # too little for Y, so only X is held -- the hand calculation follows suit.
    for sym in ("X", "Y"):
        pr = buy_px[sym]
        q = int((TE.START_CAPITAL / 2) // pr)
        cost = q * pr + TE.calc_tc(pr, q, "BUY")
        if cash < cost:
            continue
        cash -= cost
        qty[sym], bpx[sym] = q, pr
    close_n = {"X": 140.0, "Y": 170.0}
    head = cash + sum(qty[k] * close_n[k] for k in qty)
    proceeds = sell_tc = gain = 0.0
    for sym in qty:
        pr = sell_px[sym]
        proceeds += qty[sym] * pr
        sell_tc += TE.calc_tc(pr, qty[sym], "SELL")
        gain += qty[sym] * (round(pr, 2) - round(bpx[sym], 2))
    tax = max(gain - 125_000.0, 0.0) * 0.125 * 1.04   # held 393 days: long, new rate, 4% cess
    last = cash + proceeds - sell_tc - tax
    ok_b = (abs(r["eq_headline"].iloc[-1] - head) < 1e-6
            and abs(r["eq_last_day"].iloc[-1] - last) < 1e-6
            and abs(r["detail"]["sell_tc"] - sell_tc) < 1e-9 and sell_tc > 0
            and abs(r["detail"]["tax"] - tax) < 1e-6 and tax > 0
            and bh_held.calc_tc is TE.calc_tc)
    print(f"    4b buy & hold: headline {r['eq_headline'].iloc[-1]:,.2f} (expect {head:,.2f}, "
          f"no tax, no sell charge); last day {r['eq_last_day'].iloc[-1]:,.2f} (expect "
          f"{last:,.2f}: sell charges {sell_tc:,.2f}, tax {tax:,.2f})  "
          f"{'PASS' if ok_b else 'FAIL'}")
    assert ok_b, "buy & hold headline or last-day figure does not match the hand-worked case"

    # ---- 4c. The strategy engine, headline against last-day sale ------------
    bd = pd.bdate_range("2026-01-01", "2026-05-29")
    # Ten names, so a TOP_N=8 selection is possible; constant scores, so the
    # engine buys once and never sells until the end; every price rises, so the
    # last-day sale realises a short-term gain inside FY2026-27.
    syms = [f"S{k}" for k in range(10)]
    steps = np.arange(len(bd))
    px = pd.DataFrame({sym: 100.0 * (1 + (k + 1) * 0.0005) ** steps
                       for k, sym in enumerate(syms)}, index=bd)
    op = px.shift(1).fillna(px.iloc[0])
    sc = pd.DataFrame({sym: float(10 - k) for k, sym in enumerate(syms)}, index=bd)
    pc = precompute(px, vol_win=5)
    pc["vol"] = pc["vol"].fillna(0.2).replace(0, 0.2)
    mom20 = px / px.shift(20) - 1
    out = {}
    for end_sale in (False, True):
        a = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
        eq, tc, n, _ = TE.backtest_exposure(px, op, sc, bd, pc, mom20, drawdown_stop=None, mode="none",
                                            audit=a, tax_enabled=True, end_sale=end_sale,
                                            participation_cap=None)
        led = a["tax"]["ledger"]
        want_tax = sum(t["total_tax"] for t in costs.assess_years(led.realized).values())
        out[end_sale] = dict(held=a["summary"][-1]["n_stocks"], tax=a["tax"]["cum_tax"],
                             want=want_tax, cash=a["summary"][-1]["cash"], final=eq.iloc[-1])
    h, l = out[False], out[True]
    ok_c = (h["held"] > 0 and l["held"] == 0
            and abs(h["tax"] - h["want"]) < 1e-6 and abs(l["tax"] - l["want"]) < 1e-6
            and l["tax"] > h["tax"] and abs(l["final"] - l["cash"]) < 0.01)
    print(f"    4c strategy: headline holds {h['held']} at the end, tax {h['tax']:,.2f}; "
          f"last day holds {l['held']}, tax {l['tax']:,.2f} = tax_for_fy over realised "
          f"{l['want']:,.2f}  {'PASS' if ok_c else 'FAIL'}")
    assert ok_c, f"engine end-of-window behaviour wrong: {out}"
    return ok_a and ok_b and ok_c


def tax_acceptance_check():
    print("=" * 78)
    print(" TAX AXIS ACCEPTANCE -- inert at default, real off it")
    print("=" * 78)
    c1 = condition_1()
    c2 = condition_2()
    c3 = condition_3()
    c4 = condition_4()

    print("\n  NOT COVERED BY THIS CHECK, AND NOT IMPLIED:")
    print("    - file CONTENTS. This checks names. The contents gate is")
    print("      heldout_prereg_run.py's reproduction check against the shipped")
    print("      v2FINAL_equity.csv, which needs score caches and is not run here.")
    print("    - the retired-universe manifest's 171 hashes: not checked (the "
          "manifest was deleted from the tree on 2026-09-24).")

    ok = (c1 is not False) and c2 and c3 and c4
    print("\n" + "=" * 78)
    print(f" RESULT: {'PASS' if ok else 'FAIL'}"
          + ("   (condition 1 UNAVAILABLE -- see above)" if c1 is None else ""))
    print("=" * 78)
    return 0 if ok else 1


def _cli_tax_acceptance_check():
    """`python checks.py tax_acceptance_check [ARGS]`: what running tax_acceptance_check.py did."""
    raise SystemExit(tax_acceptance_check())


# ======================================================================================
# test_survivorship. From results/test_survivorship.py (moved 2026-11-27).
# ======================================================================================
# test_survivorship -- test suite for market_data.py
#
# Run it:
#     python3 checks.py test_survivorship
#
# Exit code 0 means every test passed. Non-zero means something is broken and the
# module should not be trusted until it is fixed.
#
# No pytest required -- it runs on a bare Python with pandas and numpy, so anyone
# can check the module on their own machine without installing anything.
#
# WHAT IS TESTED, AND WHY EACH TEST EXISTS
#
#     Every test below corresponds to a way this module could silently produce a
#     wrong backtest. The validation tests in particular are modelled on the real
#     broken file this project received: 76 clean-looking rows that contained no
#     RELIANCE. A test suite that only checked the happy path would have passed that
#     file too.
#
#     The most important property under test is the one that is easiest to lose in a
#     refactor: static mode must be a byte-identical no-op. If someone edits this
#     module and static mode starts filtering rows, every existing result in the
#     project silently changes. test_static_mode_is_noop guards that.

def test_survivorship_check(name, cond, detail=""):
    if cond:
        _PASS.append(name)
    else:
        _FAIL.append((name, detail))


def section(title):
    print(f"\n--- {title} " + "-" * max(0, 62 - len(title)))


def test_survivorship_run(name, fn):
    try:
        fn()
        print(f"  ok    {name}")
    except AssertionError as e:
        _FAIL.append((name, str(e)))
        print(f"  FAIL  {name}\n          {e}")
    except Exception as e:
        _FAIL.append((name, f"{type(e).__name__}: {e}"))
        print(f"  ERROR {name}\n          {type(e).__name__}: {e}")


def write_csv(name, rows) -> str:
    p = TMP / name
    pd.DataFrame(rows).to_csv(p, index=False)
    return str(p)


def valid_file() -> str:
    """A small but structurally correct membership history.

    Anchors present throughout, inclusions/exclusions consistent with the symbols
    column, three reconstitution dates with one change each."""
    base = ANCHORS + ["LT", "AXISBANK", "WIPRO"]
    r1 = list(base)
    r2 = [x for x in r1 if x != "WIPRO"] + ["MARUTI"]
    r3 = [x for x in r2 if x != "AXISBANK"] + ["TITAN"]
    return write_csv("valid.csv", [
        {"effective_date": "2019-03-29", "symbols": ",".join(r1),
         "inclusions": "", "exclusions": ""},
        {"effective_date": "2019-09-27", "symbols": ",".join(r2),
         "inclusions": "MARUTI", "exclusions": "WIPRO"},
        {"effective_date": "2020-03-27", "symbols": ",".join(r3),
         "inclusions": "TITAN", "exclusions": "AXISBANK"},
    ])


def price_dir(symbols, name="prices") -> str:
    d = TMP / name
    d.mkdir(exist_ok=True)
    for s in symbols:
        (d / f"{s}.csv").write_text("date,close\n2019-01-01,100\n")
    return str(d)


# ---------------------------------------------------------------------------
# 1. validation -- the gate
# ---------------------------------------------------------------------------

def test_valid_file_passes():
    r = market_data.validate(valid_file(), index_name="nifty100")
    assert r.ok, f"a structurally correct file failed: {r.errors}"
    assert not r.errors, f"unexpected errors: {r.errors}"


def test_missing_anchor_is_error():
    """The exact failure of the real broken file: an index history with no Reliance."""
    base = [a for a in ANCHORS if a != "RELIANCE"] + ["LT", "WIPRO"]
    p = write_csv("no_reliance.csv", [
        {"effective_date": "2019-03-29", "symbols": ",".join(base),
         "inclusions": "", "exclusions": ""}])
    r = market_data.validate(p, index_name="nifty100")
    assert not r.ok, "a file with no RELIANCE was accepted"
    assert any("RELIANCE" in e for e in r.errors), \
        f"the error does not name RELIANCE: {r.errors}"


def test_bond_ticker_is_error():
    """722HPCL29 is a debenture and appeared in the real broken file."""
    p = write_csv("bond.csv", [
        {"effective_date": "2019-03-29",
         "symbols": ",".join(ANCHORS + ["722HPCL29"]),
         "inclusions": "", "exclusions": ""}])
    r = market_data.validate(p, index_name="nifty100")
    assert not r.ok, "a file containing a bond was accepted"
    assert any("722HPCL29" in e for e in r.errors), \
        f"the error does not name the bond: {r.errors}"


def test_inconsistent_transitions_is_error():
    """symbols column disagrees with inclusions/exclusions."""
    r1 = ANCHORS + ["LT", "WIPRO"]
    r2 = [x for x in r1 if x != "WIPRO"] + ["MARUTI"]
    p = write_csv("inconsistent.csv", [
        {"effective_date": "2019-03-29", "symbols": ",".join(r1),
         "inclusions": "", "exclusions": ""},
        # claims nothing changed, but WIPRO left and MARUTI arrived
        {"effective_date": "2019-09-27", "symbols": ",".join(r2),
         "inclusions": "", "exclusions": ""}])
    r = market_data.validate(p, index_name="nifty100")
    assert not r.ok, "an internally inconsistent file was accepted"
    assert any("disagree" in e for e in r.errors), \
        f"the error does not mention the disagreement: {r.errors}"


def test_duplicate_dates_is_error():
    row = {"effective_date": "2019-03-29", "symbols": ",".join(ANCHORS),
           "inclusions": "", "exclusions": ""}
    p = write_csv("dupes.csv", [row, dict(row)])
    r = market_data.validate(p, index_name="nifty100")
    assert not r.ok, "duplicate effective_date rows were accepted"


def test_unparseable_date_raises():
    p = write_csv("baddate.csv", [
        {"effective_date": "not-a-date", "symbols": ",".join(ANCHORS),
         "inclusions": "", "exclusions": ""}])
    try:
        market_data.validate(p, index_name="nifty100")
    except market_data.MembershipError:
        return
    raise AssertionError("an unparseable date did not raise")


def test_missing_required_column_raises():
    p = write_csv("nocol.csv", [{"date": "2019-03-29", "names": "RELIANCE"}])
    try:
        market_data.validate(p, index_name="nifty100")
    except market_data.MembershipError as e:
        assert "effective_date" in str(e), f"error should name the missing column: {e}"
        return
    raise AssertionError("a file missing required columns did not raise")


def test_load_raises_on_invalid():
    base = [a for a in ANCHORS if a != "RELIANCE"]
    p = write_csv("load_invalid.csv", [
        {"effective_date": "2019-03-29", "symbols": ",".join(base),
         "inclusions": "", "exclusions": ""}])
    try:
        market_data.load(p, index_name="nifty100")
    except market_data.MembershipError:
        return
    raise AssertionError("load() accepted a file that failed validation")


def test_allow_invalid_bypasses():
    """The escape hatch must work, for inspecting a broken file."""
    base = [a for a in ANCHORS if a != "RELIANCE"]
    p = write_csv("bypass.csv", [
        {"effective_date": "2019-03-29", "symbols": ",".join(base),
         "inclusions": "", "exclusions": ""}])
    m = market_data.load(p, index_name="nifty100", allow_invalid=True)
    assert not m.validation.ok, "validation result should still record the failure"


def test_index_with_no_anchors_skips_that_check():
    """midcap150 has no guaranteed-present name; the check must not fire."""
    p = write_csv("midcap.csv", [
        {"effective_date": "2019-03-29", "symbols": "SUZLON,LLOYDSME,AIIL",
         "inclusions": "", "exclusions": ""}])
    r = market_data.validate(p, index_name="midcap150")
    assert r.ok, f"midcap file rejected despite no anchors defined: {r.errors}"


def test_price_coverage_is_warning_not_error():
    p = valid_file()
    pd_dir = price_dir(["RELIANCE", "INFY"])       # deliberately incomplete
    r = market_data.validate(p, index_name="nifty100", price_dir=pd_dir)
    assert r.ok, "incomplete price coverage must not fail the file"
    assert any("no price file" in w for w in r.warnings), \
        f"coverage gap not reported as a warning: {r.warnings}"
    assert any("RESIDUAL SURVIVORSHIP" in w for w in r.warnings), \
        "the residual-bias disclosure is missing"


# ---------------------------------------------------------------------------
# 2. members_on -- the lookup
# ---------------------------------------------------------------------------

def test_members_on_before_first_date_is_empty():
    m = market_data.load(valid_file())
    assert m.members_on("2018-01-01") == set(), \
        "membership before the history starts must be empty, not the first list"


def test_members_on_exact_boundary_is_inclusive():
    """On the effective date itself, the NEW list applies."""
    m = market_data.load(valid_file())
    on = m.members_on("2019-09-27")
    assert "MARUTI" in on, "the inclusion is not active on its own effective date"
    assert "WIPRO" not in on, "the exclusion is still present on its effective date"


def test_members_on_day_before_boundary():
    m = market_data.load(valid_file())
    on = m.members_on("2019-09-26")
    assert "WIPRO" in on, "a name was removed a day early"
    assert "MARUTI" not in on, "a name was added a day early"


def test_members_on_after_last_date_carries_forward():
    m = market_data.load(valid_file())
    assert m.members_on("2030-01-01") == m.members_on("2020-03-27"), \
        "the last known membership must carry forward"


def test_is_member_is_case_insensitive():
    m = market_data.load(valid_file())
    assert m.is_member("reliance", "2019-06-01"), "lowercase symbol not matched"
    assert m.is_member("RELIANCE", "2019-06-01")


def test_whitespace_in_symbols_is_stripped():
    p = write_csv("spaces.csv", [
        {"effective_date": "2019-03-29",
         "symbols": " RELIANCE , INFY ,TCS,HDFCBANK,ICICIBANK,ITC,SBIN ",
         "inclusions": "", "exclusions": ""}])
    m = market_data.load(p)
    assert "RELIANCE" in m.members_on("2019-06-01"), "whitespace broke the parse"
    assert " RELIANCE " not in m.members_on("2019-06-01")


# ---------------------------------------------------------------------------
# 3. forced_exits -- the exit policy
# ---------------------------------------------------------------------------

def test_forced_exit_sells_excluded_name():
    m = market_data.load(valid_file())
    market_data.set_exit_policy("forced")
    out = m.forced_exits({"RELIANCE", "WIPRO", "INFY"}, "2019-10-01")
    assert out == {"WIPRO"}, f"expected WIPRO forced out, got {out}"


def test_forced_exit_keeps_current_members():
    m = market_data.load(valid_file())
    market_data.set_exit_policy("forced")
    out = m.forced_exits({"RELIANCE", "INFY", "TCS"}, "2019-10-01")
    assert out == set(), f"current members were forced out: {out}"


def test_buffer_policy_returns_empty():
    m = market_data.load(valid_file())
    market_data.set_exit_policy("buffer")
    out = m.forced_exits({"RELIANCE", "WIPRO"}, "2019-10-01")
    assert out == set(), f"buffer policy must not force exits, got {out}"
    market_data.set_exit_policy("forced")


def test_forced_exit_before_history_is_empty():
    """With no membership defined, nothing can be forced out."""
    m = market_data.load(valid_file())
    market_data.set_exit_policy("forced")
    out = m.forced_exits({"RELIANCE", "WIPRO"}, "2018-01-01")
    assert out == set(), "names were force-sold on a date with no membership"


# ---------------------------------------------------------------------------
# 4. the switch -- static must be a no-op
# ---------------------------------------------------------------------------

def _panel():
    return pd.DataFrame({
        "date": pd.to_datetime(["2019-10-01"] * 3 + ["2019-06-01"] * 3),
        "symbol": ["RELIANCE", "WIPRO", "MARUTI"] * 2,
        "close": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
    })


def test_static_mode_is_noop():
    """The property that protects every existing result in the project."""
    m = market_data.load(valid_file())
    market_data.set_mode("static")
    p = _panel()
    out = market_data.apply_to_panel(p, m)
    assert out.equals(p), "static mode altered the panel"
    assert len(out) == len(p), f"static mode dropped rows: {len(p)} -> {len(out)}"


def test_static_mode_noop_even_with_no_membership():
    market_data.set_mode("static")
    p = _panel()
    assert market_data.apply_to_panel(p, None).equals(p), \
        "static mode with no membership altered the panel"


def test_pit_mode_filters_correctly():
    m = market_data.load(valid_file())
    market_data.set_mode("pit")
    out = market_data.apply_to_panel(_panel(), m)
    got = set(zip(out["date"].dt.strftime("%Y-%m-%d"), out["symbol"]))
    expect = {("2019-10-01", "RELIANCE"), ("2019-10-01", "MARUTI"),
              ("2019-06-01", "RELIANCE"), ("2019-06-01", "WIPRO")}
    assert got == expect, f"pit filter wrong.\n  got    {sorted(got)}\n  expect {sorted(expect)}"
    market_data.set_mode("static")


def test_pit_mode_with_none_membership_is_noop():
    """Guards against a crash if the switch is on but no file was loaded."""
    market_data.set_mode("pit")
    p = _panel()
    assert market_data.apply_to_panel(p, None).equals(p), \
        "pit mode with membership=None should pass through, not crash"
    market_data.set_mode("static")


def test_empty_panel_survives():
    m = market_data.load(valid_file())
    market_data.set_mode("pit")
    empty = pd.DataFrame({"date": pd.Series([], dtype="datetime64[ns]"),
                          "symbol": pd.Series([], dtype=str)})
    assert len(market_data.apply_to_panel(empty, m)) == 0, "empty panel broke the filter"
    market_data.set_mode("static")


def test_apply_to_panel_does_not_mutate_input():
    m = market_data.load(valid_file())
    market_data.set_mode("pit")
    p = _panel()
    before = p.copy()
    market_data.apply_to_panel(p, m)
    assert p.equals(before), "apply_to_panel mutated its input"
    market_data.set_mode("static")


# ---------------------------------------------------------------------------
# 5. eligible_mask
# ---------------------------------------------------------------------------

def test_eligible_mask_shape_and_values():
    m = market_data.load(valid_file())
    dates = pd.to_datetime(["2019-06-01", "2019-10-01"])
    syms = ["RELIANCE", "WIPRO", "MARUTI"]
    mask = m.eligible_mask(dates, syms)
    assert mask.shape == (2, 3), f"wrong shape {mask.shape}"
    assert bool(mask.loc["2019-06-01", "WIPRO"]), "WIPRO should be eligible in June"
    assert not bool(mask.loc["2019-10-01", "WIPRO"]), "WIPRO eligible after exclusion"
    assert bool(mask.loc["2019-10-01", "MARUTI"]), "MARUTI not eligible after inclusion"
    assert not bool(mask.loc["2019-06-01", "MARUTI"]), "MARUTI eligible before inclusion"


def test_eligible_mask_before_history_all_false():
    m = market_data.load(valid_file())
    mask = m.eligible_mask(pd.to_datetime(["2018-01-01"]), ["RELIANCE"])
    assert not mask.values.any(), "names eligible before the history starts"


def test_eligible_mask_unknown_symbol_is_false():
    m = market_data.load(valid_file())
    mask = m.eligible_mask(pd.to_datetime(["2019-10-01"]), ["NOTALISTEDNAME"])
    assert not mask.values.any(), "an unknown symbol was marked eligible"


# ---------------------------------------------------------------------------
# 6. switches and reporting
# ---------------------------------------------------------------------------

def test_set_mode_rejects_bad_value():
    try:
        market_data.set_mode("sometimes")
    except ValueError:
        assert market_data.SURVIVORSHIP_MODE in ("static", "pit"), "mode was corrupted"
        return
    raise AssertionError("set_mode accepted an invalid value")


def test_set_exit_policy_rejects_bad_value():
    try:
        market_data.set_exit_policy("maybe")
    except ValueError:
        return
    raise AssertionError("set_exit_policy accepted an invalid value")


def test_describe_state_names_the_bias_in_static():
    market_data.set_mode("static")
    s = market_data.describe_state()
    assert "static" in s and "survivorship bias" in s, \
        f"static mode must disclose the bias on its face: {s!r}"


def test_describe_state_names_policy_in_pit():
    market_data.set_mode("pit")
    market_data.set_exit_policy("forced")
    s = market_data.describe_state()
    assert "pit" in s and "forced" in s, f"pit state under-described: {s!r}"
    market_data.set_mode("static")


def test_coverage_table():
    m = market_data.load(valid_file())
    d = price_dir(["RELIANCE", "INFY", "TCS"], name="cov")
    t = m.coverage_table(d)
    assert len(t) == 3, f"expected one row per effective date, got {len(t)}"
    assert set(t.columns) == {"effective_date", "members", "with_price", "coverage_pct"}
    assert (t["with_price"] == 3).all(), "coverage count wrong"


# ---------------------------------------------------------------------------
# 7. date format handling
# ---------------------------------------------------------------------------

def test_iso_and_dayfirst_both_parse():
    """The project's CSVs mix 27-01-2003 and 3/2/2003 in one column."""
    p = write_csv("dayfirst.csv", [
        {"effective_date": "29-03-2019", "symbols": ",".join(ANCHORS),
         "inclusions": "", "exclusions": ""},
        {"effective_date": "27-09-2019", "symbols": ",".join(ANCHORS + ["LT"]),
         "inclusions": "LT", "exclusions": ""}])
    m = market_data.load(p)
    assert m.dates[0] == pd.Timestamp("2019-03-29"), \
        f"day-first date misparsed: {m.dates[0]}"
    assert m.dates[1] == pd.Timestamp("2019-09-27")


def test_searchsorted_works_across_pandas_versions():
    """Regression: np.searchsorted against a LIST of Timestamps raises
    "'<' not supported between instances of 'Timestamp' and 'int'" on some
    pandas/numpy combinations and silently works on others. This suite passed on
    pandas 3.0.2 and failed five tests on an older build. Membership now compares
    against a datetime64 array, so the behaviour is environment-independent.

    Exercises every array-valued lookup path with a variety of date containers."""
    m = market_data.load(valid_file())
    containers = [
        pd.DatetimeIndex(["2019-06-01", "2019-10-01"]),
        pd.Series(pd.to_datetime(["2019-06-01", "2019-10-01"])),
        ["2019-06-01", "2019-10-01"],
        pd.to_datetime(["2019-06-01", "2019-10-01"]).values,
    ]
    for c in containers:
        pos = m._pos(c)
        assert list(pos) == [0, 1], f"wrong positions for {type(c).__name__}: {pos}"
        mask = m.eligible_mask(pd.DatetimeIndex(pd.to_datetime(c)), ["RELIANCE"])
        assert mask.values.all(), f"mask failed for {type(c).__name__}"
    market_data.set_mode("pit")
    out = market_data.apply_to_panel(_panel(), m)
    assert len(out) == 4, f"apply_to_panel wrong after fix: {len(out)}"
    market_data.set_mode("static")


def test_dates_are_sorted_regardless_of_file_order():
    p = write_csv("unsorted.csv", [
        {"effective_date": "2020-03-27", "symbols": ",".join(ANCHORS + ["TITAN"]),
         "inclusions": "TITAN", "exclusions": ""},
        {"effective_date": "2019-03-29", "symbols": ",".join(ANCHORS),
         "inclusions": "", "exclusions": ""}])
    m = market_data.load(p, allow_invalid=True)
    assert m.dates == sorted(m.dates), "dates not sorted after load"
    assert "TITAN" not in m.members_on("2019-06-01"), \
        "out-of-order rows produced a wrong lookup"


# ---------------------------------------------------------------------------
# 8. golden test -- the real broken file
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# gate: one synthetic fixture per error class
#
# THESE REPLACED A TEST THAT READ A FILE OFF DISK.
#     The old `golden: the real broken file still fails` searched for
#     data/raw/N100_Survivorship/index_membership_nifty100.csv and asserted that
#     three specific errors fired on whatever it found. That silently assumed the
#     file at that path would always be the ORIGINAL broken one. When a second,
#     differently-broken file was placed there -- all seven anchors present,
#     RELIANCE on 50 of 50 dates -- the missing-anchor assertion failed and the
#     suite reported 38/39. The module was fine; the test was coupled to a file
#     that changed underneath it.
#
#     A test that reads whatever happens to be at a path is not a regression test:
#     it cannot fail for a reason you control, and it cannot tell you which error
#     class regressed. Each fixture below is built in-process and exercises exactly
#     ONE failure mode, so a failure names the defect.
# ---------------------------------------------------------------------------

def test_gate_missing_anchor():
    """A Nifty 100 history with no RELIANCE anywhere."""
    syms = [a for a in ANCHORS if a != "RELIANCE"] + ["LT", "WIPRO"]
    p = write_csv("gate_anchor.csv", [
        {"effective_date": "2019-03-29", "symbols": ",".join(syms),
         "inclusions": "", "exclusions": ""}])
    r = market_data.validate(p, index_name="nifty100")
    assert not r.ok, "a Nifty 100 history without RELIANCE was accepted"
    assert any("RELIANCE" in e and "anchor" in e for e in r.errors), \
        f"missing-anchor error did not fire: {r.errors}"


def test_gate_non_equity_ticker():
    """A debenture identifier among the constituents."""
    p = write_csv("gate_bond.csv", [
        {"effective_date": "2019-03-29",
         "symbols": ",".join(ANCHORS + ["722HPCL29"]),
         "inclusions": "", "exclusions": ""}])
    r = market_data.validate(p, index_name="nifty100")
    assert not r.ok, "a file containing a debenture was accepted"
    assert any("722HPCL29" in e for e in r.errors), \
        f"non-equity error did not fire: {r.errors}"


def test_gate_inconsistent_transitions():
    """symbols contradicts inclusions/exclusions: list[t] != list[t-1]+inc-exc."""
    r1 = ANCHORS + ["LT", "WIPRO"]
    r2 = ANCHORS + ["LT", "WIPRO", "MARUTI", "TITAN"]   # TITAN is not declared
    p = write_csv("gate_transition.csv", [
        {"effective_date": "2019-03-29", "symbols": ",".join(r1),
         "inclusions": "", "exclusions": ""},
        {"effective_date": "2019-09-27", "symbols": ",".join(r2),
         "inclusions": "MARUTI", "exclusions": ""}])
    r = market_data.validate(p, index_name="nifty100")
    assert not r.ok, "a self-contradicting file was accepted"
    assert any("disagree" in e for e in r.errors), \
        f"transition-consistency error did not fire: {r.errors}"


def test_gate_cumulative_list():
    """Each row a superset of the last, growing from ~100 to ~800 names.

    This is the defect in the second real file: the generating script adds
    inclusions without ever removing exclusions, so the 'membership' becomes a
    running total of everyone who was ever in the index."""
    cur = ANCHORS + [f"EQ{i:03d}" for i in range(93)]
    rows, start = [], len(cur)
    for i in range(20):
        add = [f"ADD{i:02d}{j:02d}" for j in range(35)]
        cur = cur + add
        rows.append({"effective_date": f"{2006+i}-03-31", "symbols": ",".join(cur),
                     "inclusions": ",".join(add), "exclusions": ""})
    assert start == 100 and len(cur) > 750, \
        f"fixture does not span ~100 -> ~800 names: {start} -> {len(cur)}"
    r = market_data.validate(write_csv("gate_cumulative.csv", rows), index_name="nifty100")
    assert not r.ok, "a cumulative file was accepted"
    assert any("CUMULATIVE" in e for e in r.errors), \
        f"cumulative error did not fire: {r.errors}"


def test_gate_exclusion_not_removed():
    """A name in `exclusions` is still present in the same row's `symbols`."""
    r1 = ANCHORS + ["LT", "WIPRO"]
    p = write_csv("gate_exclusion.csv", [
        {"effective_date": "2019-03-29", "symbols": ",".join(r1),
         "inclusions": "", "exclusions": ""},
        {"effective_date": "2019-09-27", "symbols": ",".join(r1),
         "inclusions": "", "exclusions": "WIPRO"}])
    r = market_data.validate(p, index_name="nifty100")
    assert not r.ok, "an unremoved exclusion was accepted"
    assert any("STILL in the" in e for e in r.errors), \
        f"exclusion-not-removed error did not fire: {r.errors}"


# --- the two false positives that the cumulative check used to produce --------

def test_cumulative_does_not_fire_on_stable_history():
    """A membership that barely changes is not a running total.

    Consecutive rows are IDENTICAL here, and a set is a superset of itself. The
    first version of the check counted that as evidence of accumulation and
    reported a file growing 'from 100 to 100 names' as cumulative."""
    cur = ANCHORS + [f"EQ{i:03d}" for i in range(93)]
    rows = []
    for i in range(12):
        inc = exc = ""
        if i and i % 4 == 0:
            exc = cur[-1]; cur = cur[:-1] + [f"NEW{i}"]; inc = f"NEW{i}"
        rows.append({"effective_date": f"{2010+i}-03-31", "symbols": ",".join(cur),
                     "inclusions": inc, "exclusions": exc})
    r = market_data.validate(write_csv("stable.csv", rows), index_name="nifty100")
    assert not any("CUMULATIVE" in e for e in r.errors), \
        f"cumulative error fired on a stable legitimate history: {r.errors}"


def test_cumulative_does_not_fire_on_genuine_index_expansion():
    """A real Nifty 50 -> Nifty 100 style widening must not read as accumulation.

    Every transition is a non-strict superset, which is why the first version of
    the check fired at 11 of 11. The distinguishing facts are that the growth
    happens in ONE step rather than being sustained across reconstitutions."""
    nifty50 = ANCHORS + [f"EQ{i:03d}" for i in range(43)]
    nifty100 = nifty50 + [f"EX{i:03d}" for i in range(50)]
    rows = [{"effective_date": f"{2010+i}-03-31",
             "symbols": ",".join(nifty50 if i < 6 else nifty100),
             "inclusions": ",".join(f"EX{j:03d}" for j in range(50)) if i == 6 else "",
             "exclusions": ""} for i in range(12)]
    r = market_data.validate(write_csv("expansion.csv", rows), index_name="nifty100")
    assert not any("CUMULATIVE" in e for e in r.errors), \
        f"cumulative error fired on a genuine index expansion: {r.errors}"


def test_exclusion_check_allows_same_date_removal_and_readd():
    """A name in BOTH inclusions and exclusions on one date is not a defect."""
    r1 = ANCHORS + ["LT", "WIPRO"]
    p = write_csv("readd.csv", [
        {"effective_date": "2019-03-29", "symbols": ",".join(r1),
         "inclusions": "", "exclusions": ""},
        {"effective_date": "2019-09-27", "symbols": ",".join(r1),
         "inclusions": "WIPRO", "exclusions": "WIPRO"}])
    r = market_data.validate(p, index_name="nifty100")
    assert not any("STILL in the" in e for e in r.errors), \
        f"same-date removal and re-add was reported as a defect: {r.errors}"
    assert any("re-added" in w for w in r.warnings), \
        f"a single same-date re-add should still be disclosed as a warning: {r.warnings}"


def test_routine_inclusion_exclusion_collision_is_an_error():
    """One same-date remove-and-re-add is plausible; dozens are a merge bug.

    This is what the second real file does: 45 of its 114 exclusion entries name a
    symbol the same row also lists as an inclusion. Guarding the unremoved-exclusion
    check against that case is correct, but it must not make the symptom invisible."""
    r1 = ANCHORS + ["LT", "WIPRO", "MARUTI", "TITAN"]
    rows = [{"effective_date": "2019-03-29", "symbols": ",".join(r1),
             "inclusions": "", "exclusions": ""}]
    for i, s in enumerate(("WIPRO", "MARUTI", "TITAN", "LT")):
        rows.append({"effective_date": f"{2020+i}-03-29", "symbols": ",".join(r1),
                     "inclusions": s, "exclusions": s})
    r = market_data.validate(write_csv("collision.csv", rows), index_name="nifty100")
    assert not r.ok, "routine inclusion/exclusion collisions were accepted"
    assert any("also lists as an inclusion" in e for e in r.errors), \
        f"collision error did not fire: {r.errors}"


# --- the non-equity rule, against real tickers -------------------------------

def test_digit_leading_equities_are_not_rejected():
    """Real NSE equities that begin with digits must pass.

    The first version of _looks_non_equity rejected anything starting with a
    digit, which is wrong: these are all ordinary listed equities."""
    for sym in ("3MINDIA", "8KMILES", "5PAISA", "63MOONS", "20MICRONS",
                "21STCENMGM", "3IINFOLTD", "360ONE", "3PLAND"):
        assert not market_data._looks_non_equity(sym), f"{sym} is a real NSE equity"


def test_debt_identifiers_are_rejected():
    """Coupon-prefixed debt, and issuer-plus-four-digit-year debt."""
    for sym in ("722HPCL29", "828GS2027", "1025GOI30", "685NHAI29",
                "795HDFC28", "760IRFC30", "GS2027"):
        assert market_data._looks_non_equity(sym), f"{sym} is a debt identifier"


def test_ordinary_equities_are_not_rejected():
    """Including the punctuation and digit forms that appear in real files."""
    for sym in ("RELIANCE", "TCS", "INFY", "HDFCBANK", "TV18BRDCST", "M&M",
                "L&TFH", "IDFCFIRSTB", "BAJAJ-AUTO", "MOTHERSON"):
        assert not market_data._looks_non_equity(sym), f"{sym} is a real NSE equity"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def test_pit_keeps_first_list_before_first_row():
    """Before the first effective date only the first list's symbols stay, for
    training: a symbol that joins on a later list is not chosen by that list."""
    m = market_data.load(valid_file())
    market_data.set_mode("pit")
    p = pd.DataFrame({"date": pd.to_datetime(["2019-01-02", "2019-01-02"]),
                      "symbol": ["RELIANCE", "MARUTI"], "close": [1.0, 2.0]})
    out = market_data.apply_to_panel(p, m)
    market_data.set_mode("static")
    assert list(out["symbol"]) == ["RELIANCE"], \
        f"before the first row, kept {list(out['symbol'])}, expected the first list's RELIANCE only"


def test_load_applies_renames():
    """An old ticker in the file comes back as the symbol the price files use."""
    base = ANCHORS + ["L&TFH"]
    path = write_csv("renamed.csv", [
        {"effective_date": "2019-03-29", "symbols": ",".join(base),
         "inclusions": "", "exclusions": ""}])
    m = market_data.load(path, allow_invalid=True)
    assert "LTF" in m.members_on("2019-06-01") and "L&TFH" not in m.members_on("2019-06-01"), \
        f"rename not applied: {sorted(m.members_on('2019-06-01'))}"


def test_buyhold_columns_static_is_identity():
    m = market_data.load(valid_file())
    market_data.set_mode("static")
    cols = ["RELIANCE", "WIPRO", "MARUTI"]
    assert market_data.buyhold_columns(cols, "2019-06-01", m) is cols, "static basket changed"


def test_buyhold_columns_pit_filters():
    m = market_data.load(valid_file())
    market_data.set_mode("pit")
    got = market_data.buyhold_columns(["RELIANCE", "WIPRO", "MARUTI"], "2019-10-01", m)
    market_data.set_mode("static")
    assert got == ["RELIANCE", "MARUTI"], f"pit basket wrong: {got}"


def test_residual_counts_unpriced_members():
    m = market_data.load(valid_file())
    d = price_dir([a for a in ANCHORS] + ["LT", "AXISBANK", "MARUTI"], name="resid")
    r = market_data.residual_survivorship(m, d, current=ANCHORS + ["LT", "MARUTI", "TITAN"])
    assert r["no_price_file_dropped"] == ["WIPRO"], r
    assert r["no_price_file_current"] == ["TITAN"], r


def test_survivorship():
    print("=" * 74)
    print(" SURVIVORSHIP MODULE -- TEST SUITE")
    print("=" * 74)
    last = None
    for name, fn in TESTS:
        head = name.split(":")[0]
        if head != last:
            section(head)
            last = head
        test_survivorship_run(name, fn)

    print("\n" + "=" * 74)
    total = len(TESTS)
    failed = len(_FAIL)
    print(f"  {total - failed} passed, {failed} failed, of {total}")
    if _FAIL:
        print("\n  FAILURES:")
        for n, d in _FAIL:
            print(f"    {n}\n      {d}")
        print("\n  The module must not be used until these pass.")
    else:
        print("\n  All tests passed. Static mode is a verified no-op, the validation")
        print("  gate rejects each failure mode and passes legitimate files, and the")
        print("  point-in-time lookup is correct at its boundaries.")
    print("=" * 74)
    return 1 if _FAIL else 0


def _test_survivorship_setup():
    """What importing results/test_survivorship.py did: read the command line and set up
    the module state its functions read. Called by its subcommand."""
    global _PASS, _FAIL, TMP, ANCHORS, TESTS
    # ---------------------------------------------------------------------------
    # tiny test harness
    # ---------------------------------------------------------------------------

    _PASS, _FAIL = [], []


    # ---------------------------------------------------------------------------
    # fixtures
    # ---------------------------------------------------------------------------

    TMP = Path(tempfile.mkdtemp(prefix="surv_test_"))

    ANCHORS = ["RELIANCE", "INFY", "TCS", "HDFCBANK", "ICICIBANK", "ITC", "SBIN"]


    TESTS = [
        ("validation: valid file passes", test_valid_file_passes),
        ("validation: missing anchor is an error", test_missing_anchor_is_error),
        ("validation: bond ticker is an error", test_bond_ticker_is_error),
        ("validation: inconsistent transitions are an error", test_inconsistent_transitions_is_error),
        ("validation: duplicate dates are an error", test_duplicate_dates_is_error),
        ("validation: unparseable date raises", test_unparseable_date_raises),
        ("validation: missing column raises", test_missing_required_column_raises),
        ("validation: load() raises on invalid", test_load_raises_on_invalid),
        ("validation: allow_invalid bypasses", test_allow_invalid_bypasses),
        ("validation: index with no anchors skips check", test_index_with_no_anchors_skips_that_check),
        ("validation: price coverage is a warning", test_price_coverage_is_warning_not_error),

        ("members_on: before history is empty", test_members_on_before_first_date_is_empty),
        ("members_on: effective date is inclusive", test_members_on_exact_boundary_is_inclusive),
        ("members_on: day before boundary", test_members_on_day_before_boundary),
        ("members_on: after last date carries forward", test_members_on_after_last_date_carries_forward),
        ("members_on: case insensitive", test_is_member_is_case_insensitive),
        ("members_on: whitespace stripped", test_whitespace_in_symbols_is_stripped),

        ("exits: forced sells excluded name", test_forced_exit_sells_excluded_name),
        ("exits: forced keeps current members", test_forced_exit_keeps_current_members),
        ("exits: buffer policy returns empty", test_buffer_policy_returns_empty),
        ("exits: before history is empty", test_forced_exit_before_history_is_empty),

        ("switch: STATIC IS A NO-OP", test_static_mode_is_noop),
        ("switch: static no-op with no membership", test_static_mode_noop_even_with_no_membership),
        ("switch: pit filters correctly", test_pit_mode_filters_correctly),
        ("switch: pit with membership=None passes through", test_pit_mode_with_none_membership_is_noop),
        ("switch: empty panel survives", test_empty_panel_survives),
        ("switch: does not mutate input", test_apply_to_panel_does_not_mutate_input),
        ("switch: pit keeps the first list before the first row",
         test_pit_keeps_first_list_before_first_row),

        ("pit: load applies the validated renames", test_load_applies_renames),
        ("pit: static buy & hold basket is unchanged", test_buyhold_columns_static_is_identity),
        ("pit: buy & hold holds the first members", test_buyhold_columns_pit_filters),
        ("pit: residual counts unpriced members", test_residual_counts_unpriced_members),

        ("mask: shape and values", test_eligible_mask_shape_and_values),
        ("mask: before history all false", test_eligible_mask_before_history_all_false),
        ("mask: unknown symbol is false", test_eligible_mask_unknown_symbol_is_false),

        ("config: set_mode rejects bad value", test_set_mode_rejects_bad_value),
        ("config: set_exit_policy rejects bad value", test_set_exit_policy_rejects_bad_value),
        ("config: static state discloses bias", test_describe_state_names_the_bias_in_static),
        ("config: pit state names the policy", test_describe_state_names_policy_in_pit),
        ("config: coverage table", test_coverage_table),

        ("dates: iso and day-first both parse", test_iso_and_dayfirst_both_parse),
        ("dates: sorted regardless of file order", test_dates_are_sorted_regardless_of_file_order),
        ("dates: searchsorted works across pandas versions", test_searchsorted_works_across_pandas_versions),

        # One synthetic fixture per error class. No test in this suite reads a file it
        # did not create -- see the note above test_gate_missing_anchor.
        ("gate: missing anchor", test_gate_missing_anchor),
        ("gate: non-equity ticker", test_gate_non_equity_ticker),
        ("gate: inconsistent transitions", test_gate_inconsistent_transitions),
        ("gate: cumulative list", test_gate_cumulative_list),
        ("gate: exclusion not removed", test_gate_exclusion_not_removed),

        ("falsepos: cumulative quiet on stable history",
         test_cumulative_does_not_fire_on_stable_history),
        ("falsepos: cumulative quiet on genuine expansion",
         test_cumulative_does_not_fire_on_genuine_index_expansion),
        ("falsepos: same-date removal and re-add allowed",
         test_exclusion_check_allows_same_date_removal_and_readd),
        ("gate: routine inc/exc collision is an error",
         test_routine_inclusion_exclusion_collision_is_an_error),

        ("tickers: digit-leading equities pass", test_digit_leading_equities_are_not_rejected),
        ("tickers: debt identifiers rejected", test_debt_identifiers_are_rejected),
        ("tickers: ordinary equities pass", test_ordinary_equities_are_not_rejected),
    ]


def _cli_test_survivorship():
    """`python checks.py test_survivorship [ARGS]`: what running results/test_survivorship.py did."""
    _test_survivorship_setup()
    sys.exit(test_survivorship())


# ======================================================================================
# engine_core. From results/engine_core.py (moved 2026-11-27).
# ======================================================================================
# engine_core -- the validation engine: comparison + validation + frozen config.
#
# NOTE ON WHICH ENGINE THIS IS:
#   This engine sizes new buys from leftover cash. It is the right tool for seed
#   and sub-period validation, but its absolute CAGR is NOT the reported figure.
#   The official system is backtest_runs.py (portfolio-value sizing, breadth
#   scaling). Do not quote numbers from this file as headline results.
#
# WHAT WAS LEARNED ALONG THE WAY:
#  1. The original model had no signal (IC 0.011, t=0.75): 10 of its 16 features were
#     momentum. Fixed with 17 features across 5 families, cross-sectionally z-scored.
#     IC rose to 0.036, t=2.10.
#  2. LABEL LEAK worth 5.4% of CAGR. Labels from the last 20 days of a training window
#     resolved inside the test window. Fixed by purging 32 days at every retrain.
#  3. DEV SELECTION IS NOISE. Five seed sets produced three different winners, and the
#     gap (0.05) was smaller than the noise (0.08). Dev selection was abandoned and the
#     config fixed a priori.
#  4. N=8 was wrong at this stage -- worst on every seed set. Moved to N=12.
#     (The final system later moved to top-8 after the concentration test.)
#  5. The slope regime rule failed: 14 fires, 4 correct. In COVID it avoided the crash
#     but missed the recovery.
#  6. The ABSOLUTE GATE addressed a real flaw but the fix did not work: Sharpe fell from
#     1.03 to 0.76. The model's edge comes partly from mean reversion, which is exactly
#     what the gate blocks.
#  7. A BUG invalidated the first v6 run: the `slots` cap was dropped, giving 15.5 average
#     positions instead of 12. The gate appeared to win (Sharpe 1.21) purely because of it.
#     Lesson: always reconcile the baseline against the previous engine. If the control
#     fails, everything downstream fails.
#  8. WHAT ACTUALLY WORKED: inverse-vol sizing, weight = 1/vol.
#     Sharpe 1.03 -> 1.09, MaxDD -37.8 -> -33.7, ahead of buy & hold on every metric.
#
# VALIDATION (4 tests): baseline control, seed robustness, sub-period split, parameter
# sensitivity.

warnings.filterwarnings("ignore")

# TOP_N and BUFFER are defined LIVE in settings.py as of 2026-08-29; this line
# keeps its own literals, exactly as the year window does. NOTE that
# checks.py validate_sizing imports TOP_N from HERE while running on the live
# universes -- the two definitions agree at 8 and nothing enforces it.
# See KNOWN_ISSUES.md and experiments/TOPN_SPEC.txt Part A.
ENGINE_CORE_REBAL, ENGINE_CORE_TOP_N, ENGINE_CORE_BUFFER, ENGINE_CORE_VOL_WIN = 20, 8, 16, 60

# Status label for a checklist row that is RECORDED, not computed. It exists so
# that no row can quietly go back to asserting a verdict this run did not reach.
NOT_CHECKED = "NOT CHECKED BY THIS RUN"
# SLIPPAGE comes from costs.py, which is the only definition. It was
# written out in seven files until 2026-09-22; these engines are
# cross-checked against each other, so a value changed in one and not the
# rest surfaces as a reconciliation failure elsewhere, not as a wrong
# number here. Value unchanged at 0.0015.
# THE DEFAULT, defined once in settings.capital_axis. A run's capital is
# capital_axis.selected(); this name stays for callers that want the default.
ENGINE_CORE_START_CAPITAL = capital_axis.DEFAULT
ENGINE_CORE_M = settings.METRICS_DIR


def backtest(px, op, sc, dates, pc, top_n=ENGINE_CORE_TOP_N, buffer_rank=ENGINE_CORE_BUFFER,
             rebal=ENGINE_CORE_REBAL, sizing="equal"):
    shares, cash = {}, ENGINE_CORE_START_CAPITAL
    cum_tc, n_trades = 0.0, 0
    eq, tl, pending, npos = [], [], None, []

    for i, dt in enumerate(dates):
        prices, opens = px.loc[dt], op.loc[dt]
        if pending is not None:
            top, keep, weights = pending
            for s in list(shares.keys()):
                if s not in keep:
                    p = opens.get(s, np.nan)
                    if np.isnan(p) or p <= 0:
                        continue
                    p = fill_price(p, SLIPPAGE, False)
                    q = int(shares[s]); tc = calc_tc(p, q, "SELL")
                    cash += q * p - tc; cum_tc += tc; n_trades += 1
                    tl.append({"Date": dt.date(), "Symbol": s, "Action": "SELL",
                               "Price": round(p, 2), "Shares": q, "TC_Rs": round(tc, 2)})
                    del shares[s]
            slots = top_n - len(shares)          # <-- the cap that v6 lost
            cands = [s for s in top if s not in shares][:slots]
            if slots > 0 and cands:
                w = {s: weights.get(s, 1.0) for s in cands}
                wsum = sum(w.values()); avail = cash * 0.98
                for s in cands:
                    p = opens.get(s, np.nan)
                    if np.isnan(p) or p <= 0:
                        continue
                    p = fill_price(p, SLIPPAGE, True)
                    q = int((avail * (w[s] / wsum)) // p)
                    if q < 1:
                        continue
                    tc = calc_tc(p, q, "BUY")
                    if cash < q * p + tc:
                        continue
                    cash -= q * p + tc; cum_tc += tc; n_trades += 1
                    shares[s] = shares.get(s, 0) + q
                    tl.append({"Date": dt.date(), "Symbol": s, "Action": "BUY",
                               "Price": round(p, 2), "Shares": q, "TC_Rs": round(tc, 2)})
            pending = None

        if i % rebal == 0 and i < len(dates) - 1:
            s_ = sc.loc[dt].dropna()
            s_ = s_[[k for k in s_.index if not np.isnan(prices.get(k, np.nan))]]
            # TOUCH POINT 2 -- only names in the index on this date may be ranked.
            if market_data.is_pit() and market_data.MEMBERSHIP is not None:
                _members = market_data.MEMBERSHIP.members_on(dt)
                s_ = s_[[k for k in s_.index if k in _members]]
            if len(s_) >= top_n:
                rk = s_.sort_values(ascending=False)
                top = list(rk.index[:top_n])
                keep = set(rk.index[:buffer_rank])
                # TOUCH POINT 3 -- a name that has left the index is sold on the next
                # trading day whatever its rank. The sell set is `held - keep`, so
                # dropping the forced exits out of `keep` is the union the note asks
                # for. Empty unless mode is pit AND exit policy is forced.
                if market_data.is_pit() and market_data.MEMBERSHIP is not None:
                    keep -= market_data.MEMBERSHIP.forced_exits(set(shares.keys()), dt)
                if sizing == "invvol":
                    v = pc["vol"].loc[dt]
                    w = {}
                    for s in top:
                        vs = v.get(s, np.nan)
                        w[s] = (1.0 / vs) if (not np.isnan(vs) and vs > 0.01) else 0.0
                    if sum(w.values()) == 0:
                        w = {s: 1.0 for s in top}
                else:
                    w = {s: 1.0 for s in top}
                pending = (top, keep, w)

        pv = sum(q * prices[s] for s, q in shares.items()
                 if not np.isnan(prices.get(s, np.nan))) + cash
        eq.append(pv); npos.append(len(shares))
    return pd.Series(eq, index=dates), cum_tc, n_trades, pd.DataFrame(tl), np.mean(npos)


def avg_hold(tl):
    if tl.empty:
        return np.nan
    op_, hd = {}, []
    for _, r in tl.sort_values("Date").iterrows():
        if r.Action == "BUY":
            op_[r.Symbol] = pd.Timestamp(r.Date)
        elif r.Symbol in op_:
            hd.append((pd.Timestamp(r.Date) - op_.pop(r.Symbol)).days)
    return round(np.mean(hd), 1) if hd else np.nan


# ======================================================================================
# validate_engine. From results/validate_engine.py (moved 2026-11-27).
# ======================================================================================
# validate_engine -- the four-test validation suite, run against the SHIPPING engine.
# =====================================================================================
#     ./venv/bin/python checks.py validate_engine                     # the certified universes
#     ./venv/bin/python checks.py validate_engine --universe=nifty50  # any registered universe
#     ./venv/bin/python checks.py validate_engine --fast           # skip T2 (no scoring)
#
# WHY THIS FILE EXISTS
#     The four-test suite (T1 baseline, T2 seed robustness, T3 sub-period, T4 vol-window)
#     lived inside engine_core.main() (deleted 2026-09-24 with the retired universe it
#     served) and tested checks.backtest. That is NOT the engine that produces the
#     published numbers -- those come from portfolio.backtest_exposure. The two
#     disagreed by 1.80 CAGR points on a retired universe (26.42 vs 24.62), for three
#     independent reasons measured on 2026-09-04:
#       - sizing base   : cash * 0.98        vs  port_val * exposure * 0.98
#       - weight base   : renormalised over new buys  vs  share of the whole book
#       - slot cap      : buy at most TOP_N - len(held)  vs  no cap
#     So "inverse-vol was validated" and "v2 is what ships" were claims about different
#     code. This file closes that gap: same four tests, pointed at the engine that ships.
#
#     The engine_core section IS NOT MODIFIED. Its suite stays exactly where it is, as the
#     historical record of what was validated before. This is an addition, not a
#     replacement, and the two can be compared row for row.
#
# WHAT T1 MEANS HERE, AND WHY IT IS NOT THE OLD T1
#     engine_core's T1 asserted `abs(mean_positions - TOP_N) < 0.2`, and its comment
#     says positions == TOP_N proves "the slot-cap and buffer logic are intact". That
#     test is defined in terms of a mechanism the shipping engine deliberately does not
#     have. engine_core caps new buys at TOP_N - len(shares), which on a retired
#     universe refused 149 of the model's own top-8 picks across 93 rebalances, holding rank-9..16
#     incumbents in preference to rank-1..8 entrants.
#
#     The shipping engine has no such cap, so its book floats between TOP_N and BUFFER:
#     it sells a name only once it leaves the top BUFFER, and buys every top-TOP_N name
#     it does not already hold. A book of exactly TOP_N would in fact be evidence the
#     buffer had stopped working.
#
#     T1 IS THEREFORE A RANGE CHECK ON THE SAME UNDERLYING QUESTION -- is selection
#     still doing what it is specified to do -- expressed in terms this engine can
#     satisfy: the mean book sits within [TOP_N, BUFFER], and the trade count is in the
#     same 400-1400 band the old T1 used. This is a redefinition and is labelled as one
#     everywhere it is reported. It is NOT the old T1 and its PASS is not the old PASS.
#
# WHAT IS COMPARED, IN EVERY TEST
#     Inverse-vol sizing against EQUAL-rupee sizing, both at mode="none" (100%
#     invested). That is the same contrast engine_core drew -- its backtest has no
#     exposure mode at all -- so the verdicts stay comparable. Breadth scaling is a
#     separate question with its own validation (checks.py validate_breadth_live); mixing it
#     in here would change what the four tests mean.
#
# WHICH UNIVERSES
#     Every registered universe is a row in settings.py and can be named with
#     --universe. The default is registry.CERTIFIED (nifty100 and midcap150), the
#     universes whose verdicts are published in diagnostics/, run in registry order.
#
# NOTHING PUBLISHED IS OVERWRITTEN
#     Outputs use the v2val_ prefix. engine_core's FINAL_val_*.csv are left untouched,
#     so the old and new verdicts sit side by side rather than one replacing the other.

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True

# The same three alternate seed sets engine_core's T2 uses, so T2 is a like-for-like
# comparison rather than a differently-seeded one.
VALIDATE_ENGINE_SEED_SETS = [[5, 55, 555], [13, 26, 39], [101, 202, 303]]
VALIDATE_ENGINE_VOL_WINDOWS = [40, 60, 90, 120]
VALIDATE_ENGINE_HALVES = [("2019-2022", 2019, 2022), ("2023-2026", 2023, 2026)]
TRADE_BAND = (400, 1400)          # the band engine_core's T1 used; carried over as-is

# One entry per registered universe, built from settings.py. Nothing
# here names a universe. The T2 seed caches are keyed by tag under /tmp.
def _seed_cache(tag):
    return lambda si, k: Path(f"/tmp/V2VAL_{tag}_seed{si}_{k}.csv")


VALIDATE_ENGINE_UNIVERSES = {
    u.tag: {
        "label": f"{u.name} (live)",
        "metrics": u.metrics_dir,
        "perm": u.score_cache,
        "raw_perm": u.raw_cache,
        "seed_cache": _seed_cache(u.tag),
        "purge_mode": u.purge_mode,
        "y_end": 2026,
        "live": True,
    }
    for u in REGISTRY.values()
}


def pivot(p):
    """Panel -> the objects backtest_exposure wants."""
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    return px, op, sc


def validate_engine_arm(px, op, sc, dates, pc, mom20, sizing, audit=None):
    """One always-invested arm. mode="none" matches checks.backtest, which has
    no exposure concept, so the sizing contrast is the only thing being measured."""
    # RESEARCH-ONLY, DECLARED. This caller passes no vol20, so it could not
    # apply a participation cap even if one were selected; research_only()
    # makes that a statement rather than an accident, and STOPS the run if
    # --profile ever reaches here. See costs.research_only.
    return backtest_exposure(px, op, sc, dates, pc, mom20, drawdown_stop=None, mode="none", sizing=sizing, audit=audit, participation_cap=costs.research_only(__name__))


def mean_book(audit):
    """Mean number of names held per day, from the audit's daily summary."""
    s = pd.DataFrame(audit["summary"])
    return float(s["n_stocks"].mean()) if len(s) else float("nan")


def validate_engine_sharpe_exact(eq):
    """Annualised Sharpe at full precision.

    EVERY VERDICT IN THIS FILE IS DECIDED ON THIS, NOT ON metrics()["Sharpe"].
    metrics() rounds to 2dp for display. Comparing rounded values makes a verdict
    depend on which side of a decimal a number falls: on a retired universe, T4's vol_win=60 arm
    scores 1.242330 against an equal-rupee reference of 1.240205 -- it BEATS the
    reference by +0.002125, but both round to 1.24 and a rounded ">" therefore
    reports FAIL. engine_core's suite compares rounded values too; it never bit there
    only because its margins happened to be wider. The rounded figures are still
    written to the CSVs for readability, alongside the exact ones.

    A MARGIN IS REPORTED WITH EVERY VERDICT. A pass of +0.002 Sharpe is arithmetically
    a pass and is not evidence of anything: EXPERIMENTS.md entry 29 measured this
    project's seed-noise floor at sd 0.97-2.14 CAGR points. No Sharpe noise threshold
    has been measured here, so none is invented -- the margin is printed and the
    reader judges it.
    """
    r = eq.pct_change().dropna()
    return float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0


def validate_engine_run_universe(tag, cfg, W, fast=False):
    W("=" * 104)
    W(f" VALIDATION SUITE vs THE SHIPPING ENGINE -- {cfg['label']}")
    W("=" * 104)
    W(f"  engine      test_exposure.backtest_exposure "
      f"(buys sized at the decision close)")
    W(f"  contrast    inverse-vol vs equal-rupee, mode=\"none\" (100% invested)")
    W(f"  TOP_N={TOP_N}  BUFFER={BUFFER}  purge_mode=\"{cfg['purge_mode']}\"")

    src = model.require_cache(cfg["perm"], what=f"{tag} score panel")
    p = read_table(src, parse_dates=["date"])
    px, op, sc = pivot(p)
    # THE WINDOW IS config's, NOT A YEAR SLICE. Until 2026-09-22 this was
    # `year >= 2019 & year <= y_end`, which runs to the end of the price data
    # (2026-06-08) while settings.BT_END_DATE is 2026-05-29. This file validates
    # the SHIPPING engine, so it measured six trading days that do not ship.
    # Same defect checks.py validate_sizing's T3 records and the engine_core section still
    # has. y_end is kept as a per-universe upper bound and still applies.
    bd = px.index[(px.index >= settings.BT_START_DATE)
                  & (px.index <= settings.BT_END_DATE)
                  & (px.index.year <= cfg["y_end"])]
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    W(f"  panel       {len(bd)} trading days, {px.shape[1]} symbols, "
      f"{bd[0].date()} -> {bd[-1].date()}")

    passed, tables = {}, {}

    # ---------------------------------------------------------------- T1
    W("\n  T1. BASELINE STRUCTURE -- is selection doing what it is specified to do?")
    W("      REDEFINED for this engine. engine_core's T1 asserted mean positions was")
    W(f"      within 0.2 of TOP_N, which tested for its slot cap. The shipping engine")
    W(f"      has no cap, so its book floats in [TOP_N, BUFFER] = [{TOP_N}, {BUFFER}] by")
    W("      design. A book pinned at TOP_N would mean the buffer had stopped working.")
    # NO AUDIT ON THE EQUAL ARM. backtest_exposure(sizing="equal", audit=<dict>)
    # raises UnboundLocalError: `v` (the vol series) is bound only in the non-equal
    # branch at portfolio.py, but the audit's ranking block reads v.get(...)
    # at :231 unconditionally. That defect is PRE-EXISTING -- it is in git HEAD and is
    # not introduced by the valuation fix -- and it is reported rather than patched
    # here, because repairing the shipping engine is not this file's job. Only the
    # inverse-vol arm's book size is needed for T1, so the equal arm runs unaudited
    # and the bug is simply not triggered.
    a_iv = {k: [] for k in ("holdings", "summary", "trades", "ranking",
                            "decisions", "skipped")}
    eq_e, tc_e, n_e, _ = validate_engine_arm(px, op, sc, bd, pc, mom20, "equal")
    eq_i, tc_i, n_i, _ = validate_engine_arm(px, op, sc, bd, pc, mom20, "invvol", audit=a_iv)
    m_e, m_i = metrics(eq_e, "equal-rupee", tc_e, n_e), metrics(eq_i, "inverse-vol", tc_i, n_i)
    sh_ref = validate_engine_sharpe_exact(eq_e)          # the T4 reference, at full precision
    book_i = mean_book(a_iv)
    in_range = TOP_N <= book_i <= BUFFER
    in_band = TRADE_BAND[0] <= n_i <= TRADE_BAND[1]
    ok1 = in_range and in_band
    W(f"      structural target : mean book in [{TOP_N}, {BUFFER}]  and  "
      f"{TRADE_BAND[0]}-{TRADE_BAND[1]} trades")
    W(f"      got               : mean book {book_i:.2f} ({'in range' if in_range else 'OUT OF RANGE'}), "
      f"{n_i} trades ({'in band' if in_band else 'OUT OF BAND'})")
    W(f"      reference         : equal-rupee CAGR {m_e['CAGR%']}%, Sharpe {m_e['Sharpe']} | "
      f"inverse-vol CAGR {m_i['CAGR%']}%, Sharpe {m_i['Sharpe']}")
    W(f"      CAGR is not checked -- it moves +/-0.5% per refit. Structure is.")
    W(f"      -> {'PASS' if ok1 else 'FAIL -- selection or buffer logic is not behaving as specified'}")
    passed["T1 baseline structure (REDEFINED)"] = ok1

    # ---------------------------------------------------------------- T2
    if fast:
        W("\n  T2. SEED ROBUSTNESS -- SKIPPED (--fast). Not a PASS and not a FAIL.")
        passed["T2 seed robustness"] = None
    else:
        W("\n  T2. SEED ROBUSTNESS -- does inverse-vol still win on OTHER score seeds?")
        raw_src = model.require_cache(cfg["raw_perm"],
                                       what=f"{tag} raw panel")
        raw = read_table(raw_src, parse_dates=["date"])
        t2_rows = []
        for si, seeds in enumerate(VALIDATE_ENGINE_SEED_SETS):
            # KEYED ON CODE, PANEL CONTENT, TAG, SEEDS AND PURGE MODE. Until
            # 2026-09-22 this was the tag and the seed INDEX, so it could not
            # miss on a code or panel change and read stale fits back as current.
            # purge_mode is in the key because it is per-universe here and two
            # universes differing only by it must not share a cache entry.
            key = seed_cache_key(
                code_files=[ROOT / "checks.py",
                            ROOT / "backtest_runs.py",
                            ROOT / "market_data.py", ROOT / "model.py",
                    ROOT / "settings.py"],
                panel_path=raw_src,
                parts=(tag, sorted(seeds), cfg["purge_mode"]))
            cache = cfg["seed_cache"](si, key)
            if cache.exists():
                ps = read_table(cache, parse_dates=["date"])
                W(f"      seed set {si+1}/3 from cache {cache.name}")
            else:
                W(f"      seed set {si+1}/3 -- scoring (refits the model, slow) ...")
                ps = score_monthly(raw, seeds, purge_mode=cfg["purge_mode"])
                ps[["date", "symbol", "open", "close", "score"]].to_csv(cache, index=False)
            pxs, ops, scs = pivot(ps)
            bds = pxs.index[(pxs.index >= settings.BT_START_DATE)
                            & (pxs.index <= settings.BT_END_DATE)
                            & (pxs.index.year <= cfg["y_end"])]
            pcs = precompute(pxs)
            m20s = pxs / pxs.shift(20) - 1
            e_e, _, _, _ = validate_engine_arm(pxs, ops, scs, bds, pcs, m20s, "equal")
            e_i, _, _, _ = validate_engine_arm(pxs, ops, scs, bds, pcs, m20s, "invvol")
            me, mi = metrics(e_e, "eq"), metrics(e_i, "iv")
            d_exact = validate_engine_sharpe_exact(e_i) - validate_engine_sharpe_exact(e_e)
            t2_rows.append({"seedset": si, "seeds": str(seeds),
                            "eq_Sharpe": me["Sharpe"], "iv_Sharpe": mi["Sharpe"],
                            "delta": round(mi["Sharpe"] - me["Sharpe"], 2),
                            "delta_exact": round(d_exact, 6),
                            "eq_MaxDD": me["MaxDD%"], "iv_MaxDD": mi["MaxDD%"],
                            "eq_CAGR": me["CAGR%"], "iv_CAGR": mi["CAGR%"]})
            W(f"        equal {me['Sharpe']:.2f} -> invvol {mi['Sharpe']:.2f} "
              f"(delta {d_exact:+.4f} exact) | "
              f"MaxDD {me['MaxDD%']:.1f}% -> {mi['MaxDD%']:.1f}%")
        t2 = pd.DataFrame(t2_rows)
        tables["seeds"] = t2
        ok2 = bool((t2["delta_exact"] > 0).all())
        W(f"      -> improved on {(t2['delta_exact']>0).sum()}/{len(t2)} seed sets "
          f"(smallest margin {t2['delta_exact'].min():+.4f} Sharpe). "
          f"{'PASS' if ok2 else 'FAIL -- seed-dependent'}")
        passed["T2 seed robustness"] = ok2

    # ---------------------------------------------------------------- T3
    W("\n  T3. SUB-PERIOD SPLIT -- does it work in BOTH halves independently?")
    t3_rows = []
    for hname, y0, y1 in VALIDATE_ENGINE_HALVES:
        # INTERSECTED WITH THE BACKTEST WINDOW, so the two halves cover exactly
        # the period the full run covers and no more.
        hd = px.index[(px.index.year >= y0) & (px.index.year <= y1)
                      & (px.index >= settings.BT_START_DATE)
                      & (px.index <= settings.BT_END_DATE)]
        if len(hd) < 30:
            continue
        e_e, _, _, _ = validate_engine_arm(px, op, sc, hd, pc, mom20, "equal")
        e_i, _, _, _ = validate_engine_arm(px, op, sc, hd, pc, mom20, "invvol")
        bhh = START_CAPITAL * (1 + px.pct_change().loc[hd].mean(axis=1).fillna(0)).cumprod()
        me, mi, mb = metrics(e_e, "eq"), metrics(e_i, "iv"), metrics(bhh, "bh")
        d_exact = validate_engine_sharpe_exact(e_i) - validate_engine_sharpe_exact(e_e)
        t3_rows.append({"period": hname, "eq_Sharpe": me["Sharpe"], "iv_Sharpe": mi["Sharpe"],
                        "bh_Sharpe": mb["Sharpe"],
                        "delta": round(mi["Sharpe"] - me["Sharpe"], 2),
                        "delta_exact": round(d_exact, 6),
                        "iv_CAGR": mi["CAGR%"], "bh_CAGR": mb["CAGR%"],
                        "iv_MaxDD": mi["MaxDD%"], "bh_MaxDD": mb["MaxDD%"],
                        "days": len(hd)})
        W(f"      {hname}: equal {me['Sharpe']:.2f} -> invvol {mi['Sharpe']:.2f} "
          f"(delta {d_exact:+.4f} exact) | buy&hold {mb['Sharpe']:.2f}")
    t3 = pd.DataFrame(t3_rows)
    tables["periods"] = t3
    ok3 = bool((t3["delta_exact"] > 0).all()) if len(t3) else False
    W(f"      -> {'PASS' if ok3 else 'FAIL -- only works in one sub-period'}"
      f"   (smallest margin {t3['delta_exact'].min():+.4f} Sharpe)")
    passed["T3 sub-period"] = ok3

    # ---------------------------------------------------------------- T4
    W("\n  T4. PARAMETER SENSITIVITY -- does the vol window matter?")
    t4_rows = []
    for vw in VALIDATE_ENGINE_VOL_WINDOWS:
        pcv = precompute(px, vol_win=vw)
        e_i, tcv, nv, _ = validate_engine_arm(px, op, sc, bd, pcv, mom20, "invvol")
        mi = metrics(e_i, f"vol_win={vw}", tcv, nv)
        mi["Sharpe_exact"] = round(validate_engine_sharpe_exact(e_i), 6)
        mi["margin_vs_equal"] = round(validate_engine_sharpe_exact(e_i) - sh_ref, 6)
        t4_rows.append(mi)
        W(f"      vol_win={vw:>3}: CAGR {mi['CAGR%']:>6.2f}%  Sharpe {mi['Sharpe']:>5.2f}  "
          f"MaxDD {mi['MaxDD%']:>7.2f}%   margin vs equal-rupee "
          f"{mi['margin_vs_equal']:+.4f}")
    t4 = pd.DataFrame(t4_rows)
    tables["volwin"] = t4
    ok4 = bool((t4["margin_vs_equal"] > 0).all())
    W(f"      reference: equal-rupee Sharpe {sh_ref:.6f} (exact)")
    W(f"      -> all four beat equal-rupee? "
      f"{'PASS' if ok4 else 'FAIL -- depends on the exact window'}"
      f"   (smallest margin {t4['margin_vs_equal'].min():+.4f} Sharpe)")
    passed["T4 param sensitivity"] = ok4

    # ---------------------------------------------------------------- verdict
    W("\n  " + "-" * 100)
    counted = {k: v for k, v in passed.items() if v is not None}
    n_pass = sum(1 for v in counted.values() if v)
    for k, v in passed.items():
        W(f"    {k:<42s} {'PASS' if v else ('SKIPPED' if v is None else 'FAIL')}")
    W(f"    {'':<42s} {n_pass} of {len(counted)} tests passed")
    W("  " + "-" * 100)

    tables["summary"] = pd.DataFrame(
        [{"test": k, "verdict": ("SKIPPED" if v is None else ("PASS" if v else "FAIL"))}
         for k, v in passed.items()])
    return passed, tables, {"mean_book": round(book_i, 2), "trades": int(n_i),
                            "eq_Sharpe": m_e["Sharpe"], "iv_Sharpe": m_i["Sharpe"],
                            "eq_CAGR": m_e["CAGR%"], "iv_CAGR": m_i["CAGR%"]}


def validate_engine():
    fast = "--fast" in sys.argv
    # THE DEFAULT IS registry.CERTIFIED, in registry order (midcap150, nifty100),
    # which is the order this report has always been written in. An unknown tag,
    # including a retired short tag, exits 2 with the list of valid universes.
    from settings import CERTIFIED, argv_universes, check_tags
    unis = check_tags(argv_universes(sys.argv), VALIDATE_ENGINE_UNIVERSES) \
        or [t for t in VALIDATE_ENGINE_UNIVERSES if t in CERTIFIED]
    diag = ROOT / "diagnostics"
    diag.mkdir(exist_ok=True)

    all_out, results, heads = [], {}, {}
    for tag in unis:
        cfg = VALIDATE_ENGINE_UNIVERSES[tag]
        out = []
        W = out.append
        passed, tables, head = validate_engine_run_universe(tag, cfg, W, fast=fast)
        results[tag], heads[tag] = passed, head
        md = Path(cfg["metrics"])
        for name, df in tables.items():
            df.to_csv(md / f"v2val_{name}.csv", index=False)
        W(f"\n  saved -> {md.name}/v2val_summary.csv, v2val_periods.csv, "
          f"v2val_volwin.csv" + (", v2val_seeds.csv" if "seeds" in tables else ""))
        (diag / f"validate_engine_{tag}.txt").write_text("\n".join(out) + "\n")
        print("\n".join(out))
        all_out += out + [""]

    # ------------------------------------------------------------ combined
    L = []
    L.append("=" * 104)
    L.append(" COMBINED VERDICT -- the shipping engine against the four tests")
    L.append("=" * 104)
    L.append("  Every verdict below is on test_exposure.backtest_exposure. engine_core's")
    L.append("  own FINAL_val_*.csv are untouched and still describe engine_core.backtest.")
    L.append("")
    names = sorted({k for r in results.values() for k in r})
    L.append(f"  {'test':<42s}" + "".join(f"{u:>12s}" for u in unis))
    for n in names:
        row = f"  {n:<42s}"
        for u in unis:
            v = results[u].get(n)
            row += f"{('SKIPPED' if v is None else ('PASS' if v else 'FAIL')):>12s}"
        L.append(row)
    L.append("")
    L.append(f"  {'mean book / trades':<42s}" +
             "".join(f"{str(heads[u]['mean_book'])+' / '+str(heads[u]['trades']):>12s}"
                     for u in unis))
    L.append(f"  {'Sharpe equal -> invvol':<42s}" +
             "".join(f"{str(heads[u]['eq_Sharpe'])+'->'+str(heads[u]['iv_Sharpe']):>12s}"
                     for u in unis))
    L.append("")
    live = [u for u in unis if VALIDATE_ENGINE_UNIVERSES[u]["live"]]
    if live:
        L.append("  THE LIVE UNIVERSES ARE THE ONES THAT DESCRIBE WHAT SHIPS:")
        for u in live:
            c = {k: v for k, v in results[u].items() if v is not None}
            L.append(f"    {u:<6s} {sum(1 for v in c.values() if v)} of {len(c)} passed")
    # THE VERDICT LINE AND THE EXIT STATUS, ADDED 2026-09-21. Nothing above this
    # point changed: the same tests run on the same panels and every number in
    # the report is the one this file already produced. What was missing was a
    # way for a runner to see the result -- this exited 0 while printing
    # "midcap150 1 of 4 passed", so checks.py could not have caught it even if
    # it had called this script.
    #
    # THE PASS CONDITION IS THE ONE THIS FILE ALREADY STATES: every test that ran
    # must pass, on every LIVE universe. A skipped test is not counted as passed;
    # it is counted as skipped, and a run with nothing to assert fails rather than
    # passing vacuously.
    failed = {u: sorted(k for k, v in results[u].items() if v is False)
              for u in live}
    n_bad = sum(len(v) for v in failed.values())
    asserted = sum(1 for u in live for v in results[u].values() if v is not None)
    L.append("")
    if not live or asserted == 0:
        L.append("  RESULT: FAIL -- no live universe asserted anything.")
        rc = 1
    elif n_bad:
        for u, ks in failed.items():
            if ks:
                L.append(f"  FAILED on {u}: {', '.join(ks)}")
        L.append(f"  RESULT: FAIL -- {n_bad} test-universe pair(s) failed "
                 f"of {asserted} asserted.")
        rc = 1
    else:
        L.append(f"  RESULT: PASS -- all {asserted} asserted test-universe "
                 f"pair(s) passed.")
        rc = 0
    L.append("=" * 104)
    (diag / "validate_engine_verdict.txt").write_text("\n".join(L) + "\n")
    print("\n" + "\n".join(L))
    return rc


def _cli_validate_engine():
    """`python checks.py validate_engine [ARGS]`: what running results/validate_engine.py did."""
    sys.exit(validate_engine())


# ======================================================================================
# validate_sizing. From validate_sizing.py (moved 2026-11-27).
# ======================================================================================
# validate_sizing -- run the engine_core section's inverse-vol validation suite on a
# live universe rather than the retired one it was written for.
#
# WHY THIS EXISTS
#     The four-test suite that lived in engine_core.main() ([2] VALIDATION; main()
#     was deleted 2026-09-24) is the only evidence that inverse-vol sizing is real
#     rather than cherry-picked. It only ever ran on a retired universe. Inverse-vol is the default sizing in
#     production on both live universes and has never been validated on either:
#     engine_v2_final_n100.py says so in its own params file --
#     "not measured on this universe".
#
#     This script runs the same four tests on nifty100 or midcap150. It changes none
#     of them.
#
# THE FOUR TESTS ARE RE-IMPLEMENTED HERE, not called, because every path in
# engine_core.main() was a hardcoded literal for a retired universe --
# /tmp/v5_expanding.csv, /tmp/raw_panel_20.csv, M = settings.METRICS_DIR -- with no
# universe parameter. The CRITERIA are copied verbatim; only the paths move.
#
# IMPORTING engine_core IS SAFE, AND THAT WAS VERIFIED RATHER THAN ASSUMED
#     An AST walk over every module-level statement found no I/O: lines 49-50 edit
#     sys.path, 88 and 95 construct Path objects without reading them, 68 is a try
#     that only selects a cost function, and a __main__ guard kept main() -- which
#     held every retired-universe path -- from running on import (both deleted
#     2026-09-24). Confirmed empirically with /tmp cleared. Note that importing
#     binds checks.ENGINE_CORE_M to results/metrics, the shared non-universe directory;
#     nothing here writes through it.
#
# THE T2 CACHE IS CONTENT-ADDRESSED, AND WAS NOT UNTIL 2026-09-22
#     engine_core.main() cached seed scores at /tmp/FINAL_seed{i}.csv, with no
#     universe in the name. A nifty100 run reusing that path would silently load the
#     retired universe's scores and report a pass or a fail on the wrong data, with no error anywhere.
#     The caches here carry a different prefix, so that collision is impossible.
#
#     THE PREFIX WAS NOT ENOUGH. Until 2026-09-22 the name was
#     /tmp/VALSIZE_{universe}_seed{i}.csv -- universe and seed-set index and
#     nothing else -- so the key could not miss on a code change or a panel
#     change. The same universe fit by a different engine against a different
#     panel landed on the same path and was read back as if current. A --slow run
#     on 2026-09-22 finished both universes in 0.0 and 0.1 min against caches
#     written the day before, which is how it was found.
#
#     The name is now /tmp/VALSIZE_{universe}_seed{i}_{key}.csv, where key is a
#     sha256 over checks.py (this gate and the engine_core section), backtest_runs.py,
#     market_data.py, model.py, settings.py, the raw panel's CONTENT
#     and the seed list. See _t2_cache_key. A stale cache no longer collides with
#     a live one; it is simply a file nothing asks for.
#
# T1'S TRADE RANGE IS UNCHANGED AND DELIBERATELY NOT RECALIBRATED
#     400-1400 was calibrated on the retired universe, which produced 706. Re-fitting it per
#     universe would be changing the test. It stays, and the measured count is
#     printed beside it so a universe falling outside becomes visible rather than
#     failing a structural check for a reason nobody looks at.
#
# THE SEED LOOP IS SEQUENTIAL, MATCHING the engine_core section
#     T2 runs three seed sets one after another, three processes of ten cores, as
#     engine_core does. Running the sets concurrently would be roughly three times
#     faster and is deliberately not done: if a result differs from the original suite's, that
#     must be the universe and not the harness.
#
# WHAT CANNOT BE CHECKED HERE
#     There is no artefact to gate the baseline against. checks.backtest is a
#     separate implementation from the production portfolio.backtest_exposure --
#     on the retired universe they disagreed by design, 26.42% against 24.62% for
#     the same sizing.
#     So this script cannot prove it reproduces anything published. The strongest
#     available check is T1's own structural test, and its numbers are printed.
#
# Reads the panels. Writes only the /tmp seed caches -- nothing in the repository.
#
#     python3 checks.py validate_sizing --universe=nifty100      # cost estimate, then stop
#     python3 checks.py validate_sizing --universe=nifty100 --run # run the suite

sys.dont_write_bytecode = True
warnings.filterwarnings("ignore")
# Date window from settings.py, NOT the engine_core section's year ints -- see settings.py.
# ALL FOUR PANEL PATHS come from settings.py -- the single definition.
# The label is u.name, the "Nifty 100"/"MidCap150" spelling this file has always
# written into its committed artefacts.
VALIDATE_SIZING_UNIVERSES = {
    u.tag: {"score_perm": u.score_cache,
            "raw_perm": u.raw_cache,
            "label": u.name}
    for u in certified()
}

# Verbatim from the engine_core section. Not tuned, not reordered.
VALIDATE_SIZING_SEED_SETS = [[5, 55, 555], [13, 26, 39], [101, 202, 303]]
VALIDATE_SIZING_HALVES = [("2019-2022", 2019, 2022), ("2023-2026", 2023, 2026)]
VALIDATE_SIZING_VOL_WINDOWS = [40, 60, 90, 120]
TRADE_LO, TRADE_HI = 400, 1400      # as in the engine_core section, unchanged


# THE T2 CACHE KEY LIVES IN model.py, shared with validate_engine's T2,
# which had the identical defect. See that file for what goes into the key and
# why there is no override flag. What this file contributes is its own source --
# it chooses SEED_SETS and the columns written to the cache -- plus the universe
# tag and the seed values of the set being fit.
def _t2_cache_key(u, seeds, raw_path):
    return seed_cache_key(
        code_files=[ROOT / "checks.py",
                    ROOT / "backtest_runs.py",
                    ROOT / "market_data.py", ROOT / "model.py",
                    ROOT / "settings.py"],
        panel_path=raw_path,
        parts=(u, sorted(seeds)))


def validate_sizing_sharpe_exact(eq):
    """Annualised Sharpe at full precision.

    T2, T3 AND T4 ARE DECIDED ON THIS, NOT ON metrics()["Sharpe"]. metrics()
    rounds to 2dp for display, and until 2026-09-22 every verdict in this file
    compared those rounded values -- T2 and T3 on `round(iv - eq, 2)`, T4 on
    `t4["Sharpe"] > eq_sh` with both sides already rounded. A difference smaller
    than half a hundredth therefore read as 0.00 and failed a strict `> 0`
    whatever its true sign.

    checks.py validate_engine's sharpe_exact has recorded this trap since it was
    written, including the sentence "engine_core's suite compares rounded values
    too; it never bit there only because its margins happened to be wider". It
    bit. Measured 2026-09-22 on nifty100, three results that are genuinely
    positive and were being counted as failures:

        T3 2023-2026   exact +0.002156   printed +0.00   1.38 vs 1.38
        T4 vol_win= 60 exact +0.000122   1.27 vs 1.27
        T4 vol_win=120 exact +0.007148   1.27 vs 1.27

    THE THRESHOLD IS UNCHANGED AND STILL STRICT `> 0`. This is a precision
    correction, not a wider bar, and it moves no verdict: all four T3/T4 verdicts
    still FAIL. What it stops is T4 claiming three of four vol windows fail on
    nifty100 when one does. The rounded figures stay in the printed tables for
    readability, next to the exact margins.

    NO NOISE BAND IS APPLIED. A margin of +0.0001 is arithmetically a pass and is
    not evidence of anything; the margin is printed beside every verdict and the
    reader judges it. EXPERIMENTS.md entry 29 measured this project's seed floor
    in CAGR points, not Sharpe, so there is no measured Sharpe floor to use and
    none is invented.
    """
    r = eq.pct_change().dropna()
    return float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0


def validate_sizing_universe_from_argv():
    from settings import argv_universes, check_tags
    picked = check_tags(argv_universes(sys.argv), VALIDATE_SIZING_UNIVERSES)
    if picked:
        return picked[-1]
    print(f"usage: validate_sizing.py --universe=<{'|'.join(VALIDATE_SIZING_UNIVERSES)}> [--run]")
    print("  no default -- the universe must be named explicitly.")
    sys.exit(2)


def validate_sizing():
    u = validate_sizing_universe_from_argv()
    U = VALIDATE_SIZING_UNIVERSES[u]
    t_start = time.perf_counter()

    print("=" * 110)
    print(f" SIZING VALIDATION -- is inverse-vol real, or cherry-picked?   "
          f"[{U['label']} / {u}]")
    print("=" * 110)
    print("  The four tests below are the engine_core section's, unchanged. Only the panel")
    print("  paths differ. The engine_core section is not modified by this gate.")

    score_path = model.require_cache(U["score_perm"],
                                      what=f"{U['label']} score panel")
    p = read_table(score_path, parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    bd = px.index[(px.index >= settings.BT_START_DATE) & (px.index <= settings.BT_END_DATE)]
    pc = precompute(px)
    print(f"\n  score panel : {score_path}")
    print(f"                {px.shape[1]} symbols, {len(px)} dates, "
          f"{len(bd)} in the backtest window")

    # ---------------------------------------------------------------- [1] arms
    print("\n" + "=" * 110)
    print("[1] THE TWO SIZING ARMS")
    print("=" * 110)
    eq_eq, tc1, n1, tl1, ap1 = backtest(px, op, sc, bd, pc, sizing="equal")
    eq_iv, tc2, n2, tl2, ap2 = backtest(px, op, sc, bd, pc, sizing="invvol")
    bh = ENGINE_CORE_START_CAPITAL * (1 + px.pct_change().loc[bd].mean(axis=1).fillna(0)).cumprod()
    comp = pd.DataFrame([metrics(eq_eq, "Equal-rupee (validation engine)", tc1, n1),
                         metrics(eq_iv, "Inverse-vol (validation engine)", tc2, n2),
                         metrics(bh, f"Equal-weight buy & hold ({u})")])
    print(comp.to_string(index=False))

    if "--run" not in sys.argv:
        _floor = score_floor()
        n_months = len(sorted(read_table(U["raw_perm"], usecols=["date"],
                                          parse_dates=["date"])
                              .query("date >= @_floor")["date"]
                              .dt.to_period("M").unique()))
        print("\n" + "=" * 110)
        print(" COST")
        print("=" * 110)
        print(f"   T1, T3, T4 are backtests only          : seconds")
        print(f"   T2 REFITS the model: {n_months} months x 3 seeds x "
              f"{len(VALIDATE_SIZING_SEED_SETS)} sets = {n_months*3*len(VALIDATE_SIZING_SEED_SETS):,} LightGBM fits")
        print(f"   measured on nifty100 at 3.57 s/month   : ~22.7 min")
        print(f"   seed sets run SEQUENTIALLY (3 procs of 10 cores), matching")
        print(f"   engine_core.py -- comparability over speed")
        print("\n   Stopping here. Re-run with --run to execute the suite.")
        return

    print("\n" + "=" * 110)
    print("[2] VALIDATION -- is inverse-vol real, or cherry-picked?")
    print("=" * 110)
    passed = {}

    # ------------------------------------------------------------------- T1
    print("\n  T1. BASELINE CONTROL -- does equal-rupee reproduce the engine?")
    m1 = comp.iloc[0]
    ok1 = (abs(ap1 - float(ENGINE_CORE_TOP_N)) < 0.2 and TRADE_LO <= m1["Trades"] <= TRADE_HI)
    print(f"      structural target: ~{float(ENGINE_CORE_TOP_N):.1f} positions, "
          f"trades within {TRADE_LO}-{TRADE_HI}")
    print(f"      got             : CAGR {m1['CAGR%']}%, Sharpe {m1['Sharpe']}, "
          f"{int(m1['Trades'])} trades, {ap1:.1f} positions")
    inside = TRADE_LO <= m1["Trades"] <= TRADE_HI
    print(f"      trade count {int(m1['Trades'])} is "
          f"{'INSIDE' if inside else 'OUTSIDE'} the {TRADE_LO}-{TRADE_HI} range "
          f"(range unchanged from the retired universe, which produced 706)")
    print(f"      (CAGR varies +/-0.5% per retrain -- not checked; structure is)")
    print(f"      -> {'PASS' if ok1 else 'FAIL -- slot-cap or buffer logic broken'}")
    passed["T1 baseline control"] = ok1

    # ------------------------------------------------------------------- T2
    print("\n  T2. SEED ROBUSTNESS -- does inv-vol win on OTHER score seeds?")
    raw_path = model.require_cache(U["raw_perm"],
                                    what=f"{U['label']} raw feature panel")
    raw = read_table(raw_path, parse_dates=["date"])
    t2_rows = []
    for si, seeds in enumerate(VALIDATE_SIZING_SEED_SETS):
        key = _t2_cache_key(u, seeds, raw_path)
        cache = Path(f"/tmp/VALSIZE_{u}_seed{si}_{key}.csv")
        if cache.exists():
            ps = read_table(cache, parse_dates=["date"])
            print(f"      seed set {si+1}/3 from cache {cache.name} "
                  f"(key {key}: engine_core + validate_sizing + config + raw "
                  f"panel content + seeds)", flush=True)
        else:
            print(f"      scoring seed set {si+1}/3 (refits the model) ...", flush=True)
            ps = score_monthly(raw, seeds)
            ps[["date", "symbol", "open", "close", "score"]].to_csv(cache, index=False)
        pxs = ps.pivot_table(index="date", columns="symbol", values="close").ffill()
        ops = ps.pivot_table(index="date", columns="symbol", values="open").ffill()
        scs = ps.pivot_table(index="date", columns="symbol", values="score")
        bds = pxs.index[(pxs.index >= settings.BT_START_DATE) & (pxs.index <= settings.BT_END_DATE)]
        pcs = precompute(pxs)
        e_e, _, _, _, _ = backtest(pxs, ops, scs, bds, pcs, sizing="equal")
        e_i, _, _, _, _ = backtest(pxs, ops, scs, bds, pcs, sizing="invvol")
        me, mi = metrics(e_e, "eq"), metrics(e_i, "iv")
        t2_rows.append({"seedset": si, "eq_Sharpe": me["Sharpe"], "iv_Sharpe": mi["Sharpe"],
                        "delta": round(mi["Sharpe"] - me["Sharpe"], 2),
                        "delta_exact": round(validate_sizing_sharpe_exact(e_i) - validate_sizing_sharpe_exact(e_e), 6),
                        "eq_MaxDD": me["MaxDD%"], "iv_MaxDD": mi["MaxDD%"]})
        print(f"      seed set {si+1}: equal {me['Sharpe']:.2f} -> invvol {mi['Sharpe']:.2f} "
              f"(delta {mi['Sharpe']-me['Sharpe']:+.2f}) | MaxDD {me['MaxDD%']:.1f}% -> "
              f"{mi['MaxDD%']:.1f}%", flush=True)
    t2 = pd.DataFrame(t2_rows)
    ok2 = bool((t2["delta_exact"] > 0).all())
    print(f"      -> improved on {(t2['delta_exact']>0).sum()}/3 seed sets "
          f"(smallest margin {t2['delta_exact'].min():+.6f} Sharpe). "
          f"{'PASS' if ok2 else 'FAIL -- seed-dependent'}")
    passed["T2 seed robustness"] = ok2

    # ------------------------------------------------------------------- T3
    print("\n  T3. SUB-PERIOD SPLIT -- works in BOTH halves independently?")
    t3_rows = []
    for hname, y0, y1 in VALIDATE_SIZING_HALVES:
        # INTERSECTED WITH THE BACKTEST WINDOW, not sliced from the full panel.
        # Slicing px.index by year alone let the late half run to the end of the
        # price data (2026-06-08) while the full period stopped at settings.BT_END_DATE,
        # so the two ended on different days in the same report. engine_core.main()
        # had that bug; it affected only a retired universe, is recorded in
        # KNOWN_ISSUES.md, and went with main() on 2026-09-24.
        hd = px.index[(px.index.year >= y0) & (px.index.year <= y1)
                      & (px.index >= settings.BT_START_DATE) & (px.index <= settings.BT_END_DATE)]
        e_e, _, _, _, _ = backtest(px, op, sc, hd, pc, sizing="equal")
        e_i, _, _, _, _ = backtest(px, op, sc, hd, pc, sizing="invvol")
        bhh = ENGINE_CORE_START_CAPITAL * (1 + px.pct_change().loc[hd].mean(axis=1).fillna(0)).cumprod()
        me, mi, mb = metrics(e_e, "eq"), metrics(e_i, "iv"), metrics(bhh, "bh")
        t3_rows.append({"period": hname, "eq_Sharpe": me["Sharpe"], "iv_Sharpe": mi["Sharpe"],
                        "bh_Sharpe": mb["Sharpe"], "delta": round(mi["Sharpe"]-me["Sharpe"], 2),
                        "delta_exact": round(validate_sizing_sharpe_exact(e_i) - validate_sizing_sharpe_exact(e_e), 6)})
        print(f"      {hname}: equal {me['Sharpe']:.2f} -> invvol {mi['Sharpe']:.2f} "
              f"(delta {validate_sizing_sharpe_exact(e_i)-validate_sizing_sharpe_exact(e_e):+.6f} exact) "
              f"| buy&hold {mb['Sharpe']:.2f}")
    t3 = pd.DataFrame(t3_rows)
    ok3 = bool((t3["delta_exact"] > 0).all())
    print(f"      -> {'PASS' if ok3 else 'FAIL -- only works in one sub-period'}"
          f"   (smallest margin {t3['delta_exact'].min():+.6f} Sharpe)")
    passed["T3 sub-period"] = ok3

    # ------------------------------------------------------------------- T4
    print("\n  T4. PARAMETER SENSITIVITY -- does the vol window matter?")
    t4_rows = []
    for vw in VALIDATE_SIZING_VOL_WINDOWS:
        pcv = precompute(px, vol_win=vw)
        e_i, tcv, nv, _, _ = backtest(px, op, sc, bd, pcv, sizing="invvol")
        mi = metrics(e_i, f"vol_win={vw}", tcv, nv)
        mi["Sharpe_exact"] = round(validate_sizing_sharpe_exact(e_i), 6)
        t4_rows.append(mi)
        print(f"      vol_win={vw:>3}: CAGR {mi['CAGR%']:>6.2f}%  Sharpe {mi['Sharpe']:>5.2f}  "
              f"MaxDD {mi['MaxDD%']:>7.2f}%  margin vs equal-rupee "
              f"{validate_sizing_sharpe_exact(e_i)-validate_sizing_sharpe_exact(eq_eq):+.6f}")
    t4 = pd.DataFrame(t4_rows)
    # THE REFERENCE IS THE EXACT SHARPE OF THE SAME equal-rupee CURVE T1 REPORTS,
    # not comp's rounded column. Comparing a rounded arm against a rounded
    # reference is what made vol_win=60 and 120 read as failures on nifty100 at
    # +0.000122 and +0.007148.
    eq_sh_exact = validate_sizing_sharpe_exact(eq_eq)
    ok4 = bool((t4["Sharpe_exact"] > eq_sh_exact).all())
    print(f"      -> all four beat equal-rupee ({eq_sh_exact:.6f} exact)? "
          f"{'PASS' if ok4 else 'FAIL -- depends on exact window'}"
          f"   (smallest margin {(t4['Sharpe_exact']-eq_sh_exact).min():+.6f} Sharpe)")
    passed["T4 param sensitivity"] = ok4

    # ------------------------------------------------- SUB-PERIOD TABLE (added)
    # ADDED TABLE, NOT A CHANGE TO THE SUITE. The four tests above and their
    # pass/fail criteria are untouched; nothing below feeds back into `passed`.
    #
    # It uses the same HALVES constant and the same window intersection as T3, so
    # the late half ends on settings.BT_END_DATE rather than on the last day of the price
    # panel. Every arm the script already runs appears, plus equal-weight buy &
    # hold of the same universe as a constant reference line carrying the same
    # columns.
    print("\n" + "=" * 110)
    print("[3] SUB-PERIODS -- reported, not graded")
    print("=" * 110)
    sp_rows = []
    for hname, y0, y1 in VALIDATE_SIZING_HALVES:
        hd = px.index[(px.index.year >= y0) & (px.index.year <= y1)
                      & (px.index >= settings.BT_START_DATE) & (px.index <= settings.BT_END_DATE)]
        e_e, _, _, _, _ = backtest(px, op, sc, hd, pc, sizing="equal")
        e_i, _, _, _, _ = backtest(px, op, sc, hd, pc, sizing="invvol")
        bhh = ENGINE_CORE_START_CAPITAL * (1 + px.pct_change().loc[hd].mean(axis=1).fillna(0)).cumprod()
        for lab, e in (("Equal-rupee (validation engine)", e_e),
                       ("Inverse-vol (validation engine)", e_i),
                       (f"Equal-weight buy & hold ({u})", bhh)):
            m = metrics(e, lab)
            r = e.pct_change().dropna()
            sp_rows.append({"Period": hname, "Config": lab,
                            "CAGR%": m["CAGR%"],
                            "AnnVol%": round(float(r.std() * np.sqrt(252) * 100), 2),
                            "Sharpe": m["Sharpe"], "MaxDD%": m["MaxDD%"],
                            "FirstDate": str(hd[0].date()),
                            "LastDate": str(hd[-1].date()), "Days": len(hd)})
    sp = pd.DataFrame(sp_rows)
    print(sp.to_string(index=False))

    # -------------------------------------------------------------- summary
    print("\n" + "-" * 110)
    print("  VALIDATION SUMMARY")
    print("-" * 110)
    for k, v in passed.items():
        print(f"    {'PASS' if v else 'FAIL'}  {k}")
    n_ok = sum(passed.values())
    print(f"\n    {n_ok} of {len(passed)} passed.")
    if n_ok < len(passed):
        print("    SOME FAILED -- read the failures before trusting the result.")
    print(f"\n  runtime: {(time.perf_counter()-t_start)/60:.1f} min")
    # THE VERDICT LINE AND THE EXIT STATUS, ADDED 2026-09-21. No test, threshold
    # or printed number above this point changed. The pass condition is the one
    # the summary already applies -- every one of the four tests must pass -- and
    # it is restated here only so a runner can read it from the exit code. This
    # printed "SOME FAILED" and exited 0, so nothing calling it could tell.
    rc = 0 if n_ok == len(passed) else 1
    print(f"\n  RESULT: {'PASS' if rc == 0 else 'FAIL'} -- "
          f"{n_ok} of {len(passed)} tests passed on {U['label']}.")
    print("=" * 110)
    return rc


def _cli_validate_sizing():
    """`python checks.py validate_sizing [ARGS]`: what running validate_sizing.py did."""
    sys.exit(validate_sizing())


# ======================================================================================
# validate_topn. From results/validate_topn.py (moved 2026-11-27).
# ======================================================================================
# validate_topn -- does the incumbent TOP_N=8 still hold on the live universes?
#
# SPEC: experiments/TOPN_SPEC.txt Part B, written before this file existed.
# This is a VALIDATION, not a search. Two arms, no sweep, nothing promoted.
#
# THE CONTRAST
#     TOP_N=8 (incumbent) against TOP_N=12 (the value it beat in EXPERIMENTS.md
#     entry 10, the single acceptance in twenty-five trials). BUFFER is PINNED at
#     16 in BOTH arms so only the size of the buy set moves.
#
#     The pin handicaps the challenger on turnover: 8/16 leaves an eight-rank
#     hysteresis band, 12/16 leaves four. That is a stated limit of the test, not a
#     defect, and turnover is reported for both arms so its size is visible.
#
# THE VERDICT RULE, FIXED IN THE SPEC BEFORE ANY NUMBER EXISTED
#     A: Sharpe(8) >= Sharpe(12) on nifty100,  full period
#     B: Sharpe(8) >= Sharpe(12) on midcap150, full period
#     C: Sharpe(8) >= Sharpe(12) in BOTH halves of BOTH universes
#     All three must hold. Ties hold for the incumbent, deliberately: the burden is
#     on the challenger, which is the direction entry 10 imposed on 8 when 8 was
#     the challenger. MaxDD, CAGR, volatility and turnover are REPORTED, NOT GATED.
#
# THE OUTCOME HAS TWO HALVES AND THEY ARE REPORTED TOGETHER, ALWAYS
#     A reader who takes only the first sentence must not be able to do so
#     honestly, so this file never prints one without the other:
#
#       1. TOP_N=8 is NOT CONTRADICTED on its pre-registered rule.
#       2. In the SAME measurement TOP_N=12 had the shallower MaxDD in BOTH
#          universes, on a dimension the rule does not gate.
#
#     The second half is NOT a claim that 12 is better: its Sharpe is lower in
#     every period and its turnover is far higher. And no drawdown criterion was
#     pre-registered, so nothing here is a result about drawdown -- it is an
#     ungated observation, recorded because the rule cannot see it.
#
#     NO DRAWDOWN CRITERION IS ADDED. Adding one now would be fitting the rule to
#     the data, which is exactly what documenting the Sharpe-only asymmetry rather
#     than fixing it was meant to avoid.
#
# THE OUTCOME WORD IS "NOT CONTRADICTED" OR "CONTRADICTED". NEVER "RE-EARNED".
#     Entry 10 accepted 8 against 12 on the two retired universes. The record does not
#     state what BUFFER the 12-arm ran at -- searched across EXPERIMENTS.md, the
#     pre-registrations, rejected_experiments_REPORT.txt, git history and every
#     surviving script, all negative. So this cannot be shown to be entry 10's
#     contrast, and a pass cannot re-earn that acceptance. See the spec.
#
# WHICH ENGINE, AND WHY IT MATTERS
#     portfolio.backtest_exposure -- the SHIPPING engine, the same side of the
#     split as checks.py validate_breadth_live. Per KNOWN_ISSUES.md the two engines sit
#     1.80 CAGR points apart on a retired universe, so a TOP_N result measured on
#     checks.backtest would not cover production.
#
# CACHES
#     This suite WRITES NO CACHE. TOP_N changes selection, not scoring, so both arms
#     read the one production score panel. It is not trusted by path: the universe
#     and the panel shape are asserted FROM THE FILE, and both arms are proven to
#     have read an identical panel before any number is reported.
#
# SUB-PERIODS ARE RE-RUN, NOT SLICED
#     Each half is a fresh backtest over the half's dates, intersected with the
#     backtest window -- the checks.py validate_sizing form, matching how the breadth
#     suite's T2 measures its halves "independently". backtest_runs.sub_rows() slices
#     the full curve instead, which carries the boundary portfolio into the second
#     half. The two answer different questions and this file states which it asks.
#
# English only. No verdict string is hardcoded; every criterion outcome is computed
# from the run that prints it.

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True

VALIDATE_TOPN_VOL_WIN = 60
BUFFER_PINNED = 16
INCUMBENT, CHALLENGER = 8, 12
VALIDATE_TOPN_HALVES = [("2019-2022", 2019, 2022), ("2023-2026", 2023, 2026)]

# PATHS AND SYMBOLS COME FROM settings.py -- the single definition.
# The LABEL stays local: this file's spelling is printed into
# diagnostics/topn_verdict.txt, which is committed and cited by EXPERIMENTS.md,
# and the sibling scripts spell the same two universes two other ways. Labels are
# presentation; paths are facts.
#
# Order is load-bearing: run_universe() is called per universe in this order and
# the combined verdict accumulates in that sequence.
VALIDATE_TOPN_LABELS = {u.tag: u.display_name for u in certified()}
VALIDATE_TOPN_UNIVERSES = {
    u.tag: {"perm": u.score_cache,
            "metrics_dir": u.metrics_dir, "symbols": u.symbols,
            "label": VALIDATE_TOPN_LABELS[u.tag]}
    for u in certified()
}


def validate_topn_load_panel(cfg, uni):
    """Read the production score panel and PROVE which universe it is.

    The path is not taken as evidence. A wrong-universe panel loaded silently is
    the failure BREADTH_LIVE_SPEC.txt calls the most dangerous part of that port,
    and it produces a verdict for the wrong universe with no error at all.
    """
    # SAME GUARDS AS THE RUN THAT PRODUCED THE ARTEFACT THIS COMPARES
    # AGAINST. A script that recomputes and then checks itself against a
    # published row must run under the production guards, or it measures a
    # different engine. rebal_cadence_sweep.py failed exactly this way:
    # midcap150 v3 AnnVol% recomputed 24.89 against 24.88 published.
    import market_data
    from settings import REGISTRY as _REG
    market_data.set_tradeability(_REG[uni])
    src = model.require_cache(cfg["perm"], what=f"{uni} score panel")
    p = read_table(src, parse_dates=["date"])
    got, want = set(p["symbol"].unique()), cfg["symbols"]()
    if got != want:
        raise SystemExit(
            f"{uni}: score panel symbol set does not match the universe.\n"
            f"  source        : {src}\n"
            f"  panel symbols : {len(got)}\n"
            f"  universe      : {len(want)}\n"
            f"  only in panel : {sorted(got - want)[:10]}\n"
            f"  only in config: {sorted(want - got)[:10]}\n"
            f"  Refusing to report a verdict for a universe this panel may not be.")
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    return src, px, op, sc


def panel_fingerprint(px, op, sc):
    """A value that changes if either arm were handed a different panel."""
    import hashlib
    h = hashlib.sha256()
    for frame in (px, op, sc):
        h.update(np.ascontiguousarray(
            np.nan_to_num(frame.to_numpy(dtype=np.float64), nan=-1.0)).tobytes())
        h.update(",".join(map(str, frame.columns)).encode())
    return h.hexdigest()


def run_arm(top_n, px, op, sc, dates, pc, mom20, label):
    """One arm over one date range. BUFFER is pinned for every call."""
    portfolio.TOP_N = top_n
    portfolio.BUFFER = BUFFER_PINNED
    audit = {k: [] for k in
             ("holdings", "summary", "trades", "ranking", "decisions", "skipped")}
    # RESEARCH-ONLY, DECLARED. This caller passes no vol20, so it could not
    # apply a participation cap even if one were selected; research_only()
    # makes that a statement rather than an accident, and STOPS the run if
    # --profile ever reaches here. See costs.research_only.
    eq, tc, ntr, expo = backtest_exposure(px, op, sc, dates, pc, mom20, drawdown_stop=None, mode="breadth", audit=audit, participation_cap=costs.research_only(__name__))
    # backtest_exposure returns the MEAN exposure already, as a scalar.
    dep = float(expo) * 100
    row = arm_row(eq, label, tc, ntr, dep)
    mh, nsk = held_and_skips(audit)
    row["MeanNamesHeld"] = round(mh, 2) if mh == mh else ""
    row["CashShortSkips"] = nsk
    row["TOP_N"] = top_n
    row["BUFFER"] = BUFFER_PINNED
    n_rb = len(pd.DataFrame(audit["decisions"])) if audit["decisions"] else 0
    row["Rebalances"] = n_rb
    row["TradesPerRebal"] = round(ntr / n_rb, 2) if n_rb else float("nan")
    years = (dates[-1] - dates[0]).days / 365.25
    row["TradesPerYear"] = round(ntr / years, 1) if years > 0 else float("nan")
    return row, eq


def shipped_v2(metrics_dir):
    """The published v2 figures, READ FROM THE ARTEFACT, never typed in."""
    f = Path(metrics_dir) / "v34_comparison.csv"
    if not f.exists():
        return None
    d = read_table(f)
    r = d[d["Config"].astype(str).str.startswith("v2")]
    if not len(r):
        return None
    r = r.iloc[0]
    return {"CAGR%": float(r["CAGR%"]), "Sharpe": float(r["Sharpe"]),
            "MaxDD%": float(r["MaxDD%"])}


def validate_topn_run_universe(uni, cfg, out):
    W = out.append
    src, px, op, sc = validate_topn_load_panel(cfg, uni)
    fp = panel_fingerprint(px, op, sc)

    bd = px.index[(px.index >= settings.BT_START_DATE)
                  & (px.index <= settings.BT_END_DATE)]
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1

    W("=" * 100)
    W(f" TOP_N VALIDATION -- {cfg['label']} ({uni})")
    W("=" * 100)
    W("")
    W(f"  score panel   {src}")
    W(f"  symbol set    {px.shape[1]} names, asserted equal to the configured universe")
    W(f"  window        {bd[0].date()} .. {bd[-1].date()}   {len(bd)} trading days")
    W(f"  engine        test_exposure.backtest_exposure (SHIPPING)")
    W(f"  arms          TOP_N={INCUMBENT} vs TOP_N={CHALLENGER}, "
      f"BUFFER pinned at {BUFFER_PINNED} in both")
    W(f"  panel sha256  {fp}")
    W("")

    full, curves = {}, {}
    for tn in (INCUMBENT, CHALLENGER):
        row, eq = run_arm(tn, px, op, sc, bd, pc, mom20,
                          f"TOP_N={tn} BUFFER={BUFFER_PINNED}")
        full[tn], curves[tn] = row, eq

    # Both arms must have read one panel. Recomputed after the runs, because an
    # arm that mutated the panel in place would otherwise go undetected.
    fp_after = panel_fingerprint(px, op, sc)
    same_panel = (fp == fp_after)
    W(f"  IDENTICAL PANEL FOR BOTH ARMS: "
      f"{'yes' if same_panel else 'NO -- the panel changed between arms'}")
    if not same_panel:
        raise SystemExit(f"{uni}: the panel changed during the run; no verdict reported.")

    # --- identity gate: the incumbent arm must reproduce shipped v2 ------------
    ship = shipped_v2(cfg["metrics_dir"])
    gate_rows, gate_ok = [], True
    if ship is None:
        gate_ok = False
        W("\n  IDENTITY GATE: v34_comparison.csv not found -- cannot check the")
        W("  incumbent against the shipped v2. No verdict is reported.")
    else:
        W("")
        W("  IDENTITY GATE -- the TOP_N=8 arm must reproduce the shipped v2")
        W(f"  {'metric':<10}{'this run':>12}{'v34_comparison':>16}{'':>8}")
        for k in ("CAGR%", "Sharpe", "MaxDD%"):
            a, b = float(full[INCUMBENT][k]), ship[k]
            ok = abs(a - b) < 0.005
            gate_ok = gate_ok and ok
            gate_rows.append({"metric": k, "this_run": a, "shipped": b, "match": ok})
            W(f"  {k:<10}{a:>12.2f}{b:>16.2f}{('ok' if ok else 'MISMATCH'):>8}")

    # --- sub-periods, re-run independently ------------------------------------
    subs = []
    for hname, y0, y1 in VALIDATE_TOPN_HALVES:
        hd = px.index[(px.index.year >= y0) & (px.index.year <= y1)
                      & (px.index >= settings.BT_START_DATE)
                      & (px.index <= settings.BT_END_DATE)]
        for tn in (INCUMBENT, CHALLENGER):
            row, _ = run_arm(tn, px, op, sc, hd, pc, mom20,
                             f"TOP_N={tn} BUFFER={BUFFER_PINNED}")
            row["Period"] = hname
            row["FirstDate"] = str(hd[0].date())
            row["LastDate"] = str(hd[-1].date())
            row["Days"] = len(hd)
            subs.append(row)

    # --- criteria -------------------------------------------------------------
    d_full = float(full[INCUMBENT]["Sharpe"]) - float(full[CHALLENGER]["Sharpe"])
    crit_full = d_full >= 0
    crit_halves = []
    for hname, _, _ in VALIDATE_TOPN_HALVES:
        a = [r for r in subs if r["Period"] == hname and r["TOP_N"] == INCUMBENT][0]
        b = [r for r in subs if r["Period"] == hname and r["TOP_N"] == CHALLENGER][0]
        d = float(a["Sharpe"]) - float(b["Sharpe"])
        crit_halves.append({"period": hname, "delta": round(d, 4), "holds": d >= 0})

    cols = ["TOP_N", "BUFFER", "CAGR%", "AnnVol%", "Sharpe", "MaxDD%", "Calmar",
            "Deployed%", "Trades", "TradesPerYear", "TradesPerRebal",
            "MeanNamesHeld", "CashShortSkips", "TC_Rs", "FinalEquity"]

    W("")
    W("-" * 100)
    W(" FULL PERIOD -- gated on Sharpe only. Everything else is reported, not gated.")
    W("-" * 100)
    W(f" {'TOP_N':>6}{'CAGR%':>8}{'AnnVol%':>9}{'Sharpe':>8}{'MaxDD%':>9}"
      f"{'Trades':>8}{'/year':>8}{'/rebal':>8}{'MeanHeld':>10}{'CashShort':>10}")
    for tn in (INCUMBENT, CHALLENGER):
        r = full[tn]
        W(f" {tn:>6}{r['CAGR%']:>8.2f}{r['AnnVol%']:>9.2f}{r['Sharpe']:>8.2f}"
          f"{r['MaxDD%']:>9.2f}{r['Trades']:>8}{r['TradesPerYear']:>8.1f}"
          f"{r['TradesPerRebal']:>8.2f}{str(r['MeanNamesHeld']):>10}"
          f"{r['CashShortSkips']:>10}")
    W("")
    W(f"  dSharpe (8 minus 12)          {d_full:+.4f}")
    W(f"  dCAGR   (8 minus 12)          "
      f"{float(full[INCUMBENT]['CAGR%'])-float(full[CHALLENGER]['CAGR%']):+.2f} pt")
    W(f"  dMaxDD  (8 minus 12)          "
      f"{float(full[INCUMBENT]['MaxDD%'])-float(full[CHALLENGER]['MaxDD%']):+.2f} pt")
    W("")
    W("  TURNOVER, AND THE SIZE OF THE PIN'S HANDICAP")
    W("    BUFFER is 16 in both arms, so the hysteresis band is "
      f"{BUFFER_PINNED-INCUMBENT} ranks wide at TOP_N={INCUMBENT} and "
      f"{BUFFER_PINNED-CHALLENGER} at TOP_N={CHALLENGER}.")
    ti, tc_ = full[INCUMBENT]["Trades"], full[CHALLENGER]["Trades"]
    W(f"    trades {ti} vs {tc_}   "
      f"({(tc_-ti)/ti*100:+.1f}% for the challenger)")
    W("    The challenger is handicapped by the pin. This test cannot separate")
    W("    '8 is a better concentration' from '16 suits 8 better than it suits 12'.")

    W("")
    W("-" * 100)
    W(" SUB-PERIODS -- each half re-run independently, intersected with the window")
    W("-" * 100)
    W(f" {'period':<12}{'TOP_N':>6}{'days':>6}{'CAGR%':>8}{'AnnVol%':>9}{'Sharpe':>8}"
      f"{'MaxDD%':>9}{'Trades':>8}{'MeanHeld':>10}{'CashShort':>10}")
    for r in subs:
        W(f" {r['Period']:<12}{r['TOP_N']:>6}{r['Days']:>6}{r['CAGR%']:>8.2f}"
          f"{r['AnnVol%']:>9.2f}{r['Sharpe']:>8.2f}{r['MaxDD%']:>9.2f}"
          f"{r['Trades']:>8}{str(r['MeanNamesHeld']):>10}{r['CashShortSkips']:>10}")
    W("")
    for c in crit_halves:
        W(f"  {c['period']}  dSharpe (8 minus 12)  {c['delta']:+.4f}")

    # --- the funding-defect prediction, on the record ------------------------
    W("")
    W("  THE FUNDING-DEFECT PREDICTION, TESTED")
    W("    TOPN_SPEC.txt records, before the run, an expectation that TOP_N=12")
    W("    would show HIGHER cash-short skips than TOP_N=8, because twelve targets")
    W("    funded from cash alone is more pressure on the same defect.")
    si = int(full[INCUMBENT]["CashShortSkips"])
    sc_ = int(full[CHALLENGER]["CashShortSkips"])
    W(f"    measured, full period:  TOP_N=8 {si}   TOP_N=12 {sc_}")
    W(f"    the prediction is {'BORNE OUT' if sc_ > si else 'NOT BORNE OUT'} on {uni}.")

    return {"uni": uni, "full": full, "subs": subs, "gate_ok": gate_ok,
            "gate_rows": gate_rows, "crit_full": crit_full, "d_full": d_full,
            "crit_halves": crit_halves, "cols": cols, "panel": str(src),
            "fingerprint": fp, "days": len(bd),
            "window": (str(bd[0].date()), str(bd[-1].date()))}


def write_artefacts(res, cfg):
    md = Path(cfg["metrics_dir"])
    pd.DataFrame([res["full"][INCUMBENT], res["full"][CHALLENGER]])[
        res["cols"]].to_csv(md / "topn_full.csv", index=False)
    pd.DataFrame(res["subs"])[["Period", "FirstDate", "LastDate", "Days"]
                              + res["cols"]].to_csv(md / "topn_subperiods.csv",
                                                    index=False)
    params = {
        "spec": "experiments/TOPN_SPEC.txt Part B",
        "universe": res["uni"],
        "window_start": res["window"][0], "window_end": res["window"][1],
        "trading_days": res["days"],
        "engine": "test_exposure.backtest_exposure (shipping)",
        "mode": "breadth", "sizing": "invvol",
        "incumbent_top_n": INCUMBENT, "challenger_top_n": CHALLENGER,
        "buffer_pinned": BUFFER_PINNED,
        "vol_win": VALIDATE_TOPN_VOL_WIN,
        "score_panel": res["panel"], "panel_sha256": res["fingerprint"],
        "identity_gate_passed": bool(res["gate_ok"]),
        "git": _git_state(),
    }
    (md / "topn_params.json").write_text(json.dumps(params, indent=2) + "\n")


def validate_topn():
    results, out_all = {}, []
    for uni, cfg in VALIDATE_TOPN_UNIVERSES.items():
        out = []
        res = validate_topn_run_universe(uni, cfg, out)
        write_artefacts(res, cfg)
        results[uni] = res
        (ROOT / "diagnostics" / f"topn_{uni}.txt").write_text("\n".join(out) + "\n")
        out_all += out + [""]

    # ---- combined verdict, computed ----------------------------------------
    W = out_all.append
    W("=" * 100)
    W(" VERDICT -- rule fixed in experiments/TOPN_SPEC.txt before any number existed")
    W("=" * 100)
    W("")
    gates_ok = all(r["gate_ok"] for r in results.values())
    if not gates_ok:
        W("  IDENTITY GATE FAILED. The TOP_N=8 arm did not reproduce the shipped v2")
        W("  in at least one universe, so the harness is wrong and NO verdict is")
        W("  reported for either arm. This is a correctness gate, not a performance")
        W("  gate: failure voids the run rather than producing a result.")
        W("")
        W("  RESULT: FAIL -- identity gate did not hold on "
          + ", ".join(sorted(u for u, r in results.items() if not r["gate_ok"])) + ".")
        (ROOT / "diagnostics" / "topn_verdict.txt").write_text("\n".join(out_all) + "\n")
        print("\n".join(out_all))
        return 1

    per_uni = {}
    for uni, r in results.items():
        halves_ok = all(c["holds"] for c in r["crit_halves"])
        per_uni[uni] = r["crit_full"] and halves_ok
        W(f"  {uni}")
        W(f"    full period      dSharpe {r['d_full']:+.4f}   "
          f"{'holds' if r['crit_full'] else 'does not hold'}")
        for c in r["crit_halves"]:
            W(f"    {c['period']}        dSharpe {c['delta']:+.4f}   "
              f"{'holds' if c['holds'] else 'does not hold'}")
    W("")
    all_hold = all(per_uni.values())
    any_hold = any(per_uni.values())
    outcome = "NOT CONTRADICTED" if all_hold else "CONTRADICTED"
    W(f"  TOP_N={INCUMBENT} IS {outcome}"
      + ("" if all_hold else " -- at least one criterion does not hold"))
    W("")
    # THE SECOND HALF OF THE OUTCOME, PRINTED WITH THE FIRST AND NOT BELOW IT.
    # Computed from the run, never asserted: if the challenger's drawdown were
    # not shallower, these lines would say so.
    dd = {u: (float(r["full"][INCUMBENT]["MaxDD%"]),
              float(r["full"][CHALLENGER]["MaxDD%"])) for u, r in results.items()}
    shallower = [u for u, (i, c) in dd.items() if c > i]
    if len(shallower) == len(dd):
        W(f"  AND IN THE SAME MEASUREMENT, TOP_N={CHALLENGER} HAD THE SHALLOWER MaxDD")
        W(f"  IN BOTH UNIVERSES, ON A DIMENSION THE RULE DOES NOT GATE.")
    elif shallower:
        W(f"  AND IN THE SAME MEASUREMENT, TOP_N={CHALLENGER} HAD THE SHALLOWER MaxDD")
        W(f"  ON {', '.join(shallower)}, ON A DIMENSION THE RULE DOES NOT GATE.")
    else:
        W(f"  TOP_N={INCUMBENT} ALSO HELD THE SHALLOWER MaxDD IN EVERY UNIVERSE,")
        W(f"  ON A DIMENSION THE RULE DOES NOT GATE.")
    for u, (i, c) in dd.items():
        W(f"    {u:<6} MaxDD  TOP_N={INCUMBENT} {i:.2f}   TOP_N={CHALLENGER} {c:.2f}")
    W("")
    sh_lo = all(float(results[u]["full"][CHALLENGER]["Sharpe"])
                < float(results[u]["full"][INCUMBENT]["Sharpe"]) for u in results)
    W(f"  THIS IS NOT A CLAIM THAT TOP_N={CHALLENGER} IS BETTER.")
    W(f"    Its Sharpe is lower in {'every period' if sh_lo else 'the periods gated above'},")
    tt = ", ".join(f"{u} {(float(results[u]['full'][CHALLENGER]['Trades'])/float(results[u]['full'][INCUMBENT]['Trades'])-1)*100:+.1f}%"
                   for u in results)
    W(f"    and its turnover is higher -- {tt}.")
    W("    NO DRAWDOWN CRITERION WAS PRE-REGISTERED, so nothing here is a result")
    W("    about drawdown. It is an ungated observation, recorded because the rule")
    W("    cannot see it.")
    W("")
    W("    NO DRAWDOWN CRITERION IS ADDED NOW. That would be fitting the rule to")
    W("    the data, which is what documenting the Sharpe-only asymmetry rather")
    W("    than fixing it was meant to avoid. It stays ungated and recorded.")
    W("")
    if all_hold:
        W("  WHAT THIS MEANS, AND ITS CEILING")
        W(f"    TOP_N={INCUMBENT} is not beaten by TOP_N={CHALLENGER} on either live")
        W("    universe, full period or either half, under entry 10's own criterion,")
        W("    measured on the shipping engine.")
        W("    IT DOES NOT RE-EARN entry 10's acceptance. The record does not state")
        W("    what BUFFER the original 12-arm ran at, so this cannot be shown to be")
        W("    entry 10's contrast. NOT CONTRADICTED is the ceiling in every outcome.")
        W(f"    IT DOES NOT MEAN {INCUMBENT} is optimal. Two arms cannot say that.")
    elif any_hold:
        held = [u for u, v in per_uni.items() if v]
        fell = [u for u, v in per_uni.items() if not v]
        W("  THE UNIVERSES DISAGREE, AND THE DISAGREEMENT IS THE FINDING.")
        W(f"    holds on {', '.join(held)}; does not hold on {', '.join(fell)}.")
        W("    It is NOT resolved toward either universe, NOT averaged, NOT called a")
        W("    hold with a caveat, and NOT re-run with a changed criterion. Neither")
        W("    universe is primary. Same handling as the v34 measurement.")
    else:
        W("  THE INCUMBENT IS CONTRADICTED ON BOTH LIVE UNIVERSES.")
        W("    The single acceptance in twenty-five trials does not reproduce on the")
        W(f"    universes that ship. This does NOT promote TOP_N={CHALLENGER}:")
        W("    promotion is a separate decision needing its own pre-registration.")
        W("    The immediate output is a KNOWN_ISSUES.md entry, not a config change.")
    W("")
    W("  NOT GATED, REPORTED ONLY: MaxDD, CAGR, volatility, turnover, mean names")
    W("  held and cash-short skips. Entry 10 gated on Sharpe alone and this")
    W("  inherits that. A challenger matching Sharpe while halving drawdown would")
    W("  not be detected by this rule.")
    W("")
    W("  THIS COUNTS AS A TRIAL and is entered in experiments/EXPERIMENTS.md.")
    W("  Calling it a validation constrains what may be DONE with the result --")
    W("  no promotion, no second value, no re-run at a changed criterion -- and")
    W("  that is the whole of the difference.")
    W("=" * 100)
    # THE VERDICT LINE AND THE EXIT STATUS, ADDED 2026-09-21. No criterion, gate
    # or number above changed.
    #
    # ONLY THE IDENTITY GATE IS GATED, AND DELIBERATELY SO. `per_uni` above holds
    # whether TOP_N=12 beat TOP_N=8 on the pre-registered Sharpe criterion. That
    # is a TRIAL OUTCOME -- this file says so itself, "THIS COUNTS AS A TRIAL" --
    # and a trial that does not come out is a result, not a broken repository.
    # Exiting non-zero on it would convert a research finding into a runner
    # failure and would create pressure to re-run it at a changed criterion,
    # which is the one thing the spec forbids.
    #
    # The identity gate is different in kind: it asserts the harness reproduces
    # the shipped v2 row, and this file already states that its failure "voids
    # the run rather than producing a result". That is a correctness condition
    # and it is the one carried into the exit status.
    W("")
    W("  RESULT: PASS -- identity gate held on all "
      f"{len(results)} universe(s): {', '.join(sorted(results))}. "
      "The TOP_N trial outcome above is reported, not gated.")

    (ROOT / "diagnostics" / "topn_verdict.txt").write_text("\n".join(out_all) + "\n")
    print("\n".join(out_all))
    return 0


def _cli_validate_topn():
    """`python checks.py validate_topn [ARGS]`: what running results/validate_topn.py did."""
    sys.exit(validate_topn())


# ======================================================================================
# validate_breadth_live. From results/validate_breadth_live.py (moved 2026-11-27).
# ======================================================================================
# validate_breadth_live -- breadth validation on the LIVE universes.
#
# Governed by experiments/BREADTH_LIVE_SPEC.txt, written before this file existed.
# Read that first; this module implements it and does not restate its reasoning.
#
# WHY THIS IS A NEW FILE AND results/validate_breadth.py IS NOT TOUCHED
#     validate_breadth.py is the provenance of the 58-stock result. Rewriting it to
#     take a universe argument would destroy that record. It stays frozen. T1 and T2
#     below are copied from it verbatim -- same seed sets, same criteria, same
#     thresholds -- so that this is the SAME test applied to a different universe
#     rather than a new test that happens to resemble it.
#
# THE THREE TESTS
#     T1  seed robustness   GATED   dSharpe > 0 and dMaxDD > 3 on all three seed sets
#     T2  sub-period        GATED   dSharpe > 0 in both halves
#     T3  constant-exposure control  NOT GATED, REPORTED ONLY
#
#     T1 AND T2 ARE ASYMMETRIC AND THAT IS INHERITED, NOT CHOSEN. T1 gates on Sharpe
#     AND drawdown; T2 gates on Sharpe ALONE. A rule that improved Sharpe in both
#     halves while WORSENING drawdown in one of them would pass T2. The original
#     suite (validate_breadth.py, written for a retired universe) was written that
#     way and harmonising it here would be changing the test.
#
#     THE dMaxDD > 3 BAR IS UNDERIVED. Nothing in validate_breadth.py derives it and
#     nothing here does either -- it is a magic constant of the same class as T1's
#     400-1400 trade range in checks.py validate_sizing. It is copied unchanged to both
#     universes and is NOT recalibrated per universe.
#
# T3 IS REPORTED, NEVER JUDGED
#     T3 compares breadth against a FIXED exposure equal to breadth's own realised
#     mean, so the deployment level is neutralised and only the timing differs. It
#     therefore does NOT test whether breadth's chosen level is a good level, and
#     the constant is not an independent benchmark -- it is read out of the arm it
#     is compared against.
#
#     T3 was added after v2's numbers were known, so gating on it would be choosing
#     a criterion with the data in view. It prints differences and nothing else: no
#     verdict word, no threshold, and never T1's 3-point bar, which belongs to a
#     different comparison.
#
# CACHES ARE NAMESPACED AND THERE IS NO FALLBACK
#     validate_breadth.py:56-60 falls back to engine_core's /tmp/FINAL_seed{i}.csv.
#     On the retired universe it was written for that is sound -- same raw panel,
#     same seeds. Carried here unchanged it would silently score that universe's
#     panel and print a verdict for the wrong universe with no error at all. The caches here are
#     /tmp/VALBREADTH_{universe}_seed{i}_{key}.csv and NOTHING ELSE IS READ. No
#     cache written by another script is used, including /tmp/VALSIZE_* -- see the
#     spec. The key is seed_cache_key over checks.py (this gate and the engine_core section), backtest_runs.py,
#     market_data.py, model.py, settings.py, the
#     raw panel's content, the universe and the seeds (since 2026-09-27; until then
#     the name carried the universe and the seed-set index only, so a cache written
#     against an earlier panel was read back as current).
#
# Reads the panels. Writes the /tmp seed caches, three CSVs into the universe's
# metrics folder, and one report into diagnostics/.
#
#     python3 checks.py validate_breadth_live --universe=nifty100      # cost only
#     python3 checks.py validate_breadth_live --universe=nifty100 --run  # full run

sys.dont_write_bytecode = True
warnings.filterwarnings("ignore")
# Date window from settings.py, NOT the engine_core section's year ints -- see settings.py.
# ALL FOUR PANEL PATHS AND THE METRICS DIRECTORY come from
# settings.py -- the single definition. The label is u.name, the
# "Nifty 100"/"MidCap150" spelling this file has always written into
# breadth_live_params.json and printed.


def _t1_cache(u, si, seeds, raw_path):
    """The T1 seed cache for one seed set, keyed on code, panel content and seeds."""
    key = seed_cache_key(
        code_files=[ROOT / "checks.py",
                    ROOT / "backtest_runs.py",
                    ROOT / "market_data.py", ROOT / "model.py",
                    ROOT / "settings.py"],
        panel_path=raw_path,
        parts=(u, sorted(seeds)))
    return Path(f"/tmp/VALBREADTH_{u}_seed{si}_{key}.csv")


VALIDATE_BREADTH_LIVE_UNIVERSES = {
    u.tag: {"score_perm": u.score_cache,
            "raw_perm": u.raw_cache,
            "metrics": u.metrics_dir, "label": u.name}
    for u in certified()
}

# Verbatim from results/validate_breadth.py. Not reordered, not extended.
VALIDATE_BREADTH_LIVE_SEED_SETS = [[5, 55, 555], [13, 26, 39], [101, 202, 303]]
VALIDATE_BREADTH_LIVE_HALVES = [("2019-2022", 2019, 2022), ("2023-2026", 2023, 2026)]
DD_BAR = 3.0            # UNDERIVED. See the module docstring and the spec.


# ---------------------------------------------------------------- panel helpers
def panel_parts(p):
    """Pivot a scored panel into the objects backtest_exposure wants."""
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    pc = precompute(px)
    mom20 = px / px.shift(20) - 1
    return px, op, sc, pc, mom20


def window_dates(px, y0=None, y1=None):
    """The backtest window, optionally narrowed to a year range."""
    m = (px.index >= settings.BT_START_DATE) & (px.index <= settings.BT_END_DATE)
    if y0 is not None:
        m &= (px.index.year >= y0) & (px.index.year <= y1)
    return px.index[m]


def run_mode(parts, dd, mode, const_expo=None):
    """One backtest. Returns (metrics dict, realised mean exposure)."""
    px, op, sc, pc, mom20 = parts
    # RESEARCH-ONLY, DECLARED. This caller passes no vol20, so it could not
    # apply a participation cap even if one were selected; research_only()
    # makes that a statement rather than an accident, and STOPS the run if
    # --profile ever reaches here. See costs.research_only.
    eq, tc, ntr, expo = backtest_exposure(px, op, sc, dd, pc, mom20, drawdown_stop=None, mode=mode, const_expo=const_expo, participation_cap=costs.research_only(__name__))
    return metrics(eq, mode, tc, ntr), float(expo)


def validate_breadth_live_compare(parts, dd, mode_a, mode_b, const_expo=None):
    """mode_b minus mode_a on Sharpe and MaxDD, plus both realised exposures."""
    ma, ea = run_mode(parts, dd, mode_a, const_expo if mode_a == "const" else None)
    mb, eb = run_mode(parts, dd, mode_b, const_expo if mode_b == "const" else None)
    return {"Sharpe_a": ma["Sharpe"], "Sharpe_b": mb["Sharpe"],
            "dSharpe": round(mb["Sharpe"] - ma["Sharpe"], 4),
            "MaxDD_a": ma["MaxDD%"], "MaxDD_b": mb["MaxDD%"],
            "dMaxDD": round(mb["MaxDD%"] - ma["MaxDD%"], 4),
            "CAGR_a": ma["CAGR%"], "CAGR_b": mb["CAGR%"],
            "dCAGR": round(mb["CAGR%"] - ma["CAGR%"], 4),
            "expo_a": round(ea * 100, 2), "expo_b": round(eb * 100, 2)}


def validate_breadth_live_git_state():
    """The tree this ran on, dirt included. Mirrors backtest_runs._git_state."""
    def _run(args):
        try:
            r = subprocess.run(["git"] + args, capture_output=True, text=True,
                               timeout=10, cwd=str(ROOT))
            return r.stdout if r.returncode == 0 else None
        except Exception:
            return None
    head, status = _run(["rev-parse", "HEAD"]), _run(["status", "--porcelain"])
    if head is None or status is None:
        return {"commit": None,
                "note": "git unavailable; the tree this ran on is not recorded"}
    modified = [l for l in status.splitlines() if l.strip()]
    return {"commit": head.strip(),
            "working_tree_dirty": len(modified) > 0,
            "modified_or_untracked_files": len(modified),
            "note": ("the commit alone does NOT describe this run: the working "
                     "tree had uncommitted changes when it was produced"
                     if modified else
                     "working tree clean; the commit describes this run exactly")}


def validate_breadth_live_universe_from_argv():
    from settings import argv_universes, check_tags
    picked = check_tags(argv_universes(sys.argv), VALIDATE_BREADTH_LIVE_UNIVERSES)
    if picked:
        return picked[-1]
    print(f"usage: validate_breadth_live.py --universe=<{'|'.join(VALIDATE_BREADTH_LIVE_UNIVERSES)}> [--run]")
    print("  no default -- the universe must be named explicitly.")
    sys.exit(2)


# ------------------------------------------------------------------------ main
def validate_breadth_live():
    u = validate_breadth_live_universe_from_argv()
    U = VALIDATE_BREADTH_LIVE_UNIVERSES[u]
    L = []

    def W(s=""):
        L.append(s)
        print(s, flush=True)

    W("=" * 104)
    W(f" BREADTH VALIDATION ON A LIVE UNIVERSE -- {U['label']} ({u})")
    W("=" * 104)
    W(f"  spec    experiments/BREADTH_LIVE_SPEC.txt")
    W(f"  window  {settings.BT_START_DATE.date()} to {settings.BT_END_DATE.date()} inclusive")
    W("  T1 and T2 are copied verbatim from results/validate_breadth.py, which")
    W("  stays frozen. T3 is new and is REPORTED, NOT GATED.")

    score_path = model.require_cache(U["score_perm"],
                                      what=f"{U['label']} score panel")
    prod = read_table(score_path, parse_dates=["date"])
    parts = panel_parts(prod)
    bd = window_dates(parts[0])
    W(f"\n  score panel  {score_path}")
    W(f"               {parts[0].shape[1]} symbols, {len(bd)} days in the window")

    raw_path = model.require_cache(U["raw_perm"],
                                    what=f"{U['label']} raw feature panel")

    if "--run" not in sys.argv:
        _floor = score_floor()
        n_months = len(read_table(raw_path, usecols=["date"], parse_dates=["date"])
                       .query("date >= @_floor")["date"].dt.to_period("M")
                       .unique())
        cached = sum(_t1_cache(u, i, s, raw_path).exists()
                     for i, s in enumerate(VALIDATE_BREADTH_LIVE_SEED_SETS))
        W("\n" + "=" * 104)
        W(" COST -- nothing has been run")
        W("=" * 104)
        W(f"   T1 refits the model: {n_months} months x {len(VALIDATE_BREADTH_LIVE_SEED_SETS[0])} seeds "
          f"x {len(VALIDATE_BREADTH_LIVE_SEED_SETS)} sets = "
          f"{n_months*len(VALIDATE_BREADTH_LIVE_SEED_SETS[0])*len(VALIDATE_BREADTH_LIVE_SEED_SETS):,} LightGBM fits")
        W(f"   seed caches already present: {cached} of {len(VALIDATE_BREADTH_LIVE_SEED_SETS)}")
        W("   T2 and T3 are backtests on the production panel: seconds")
        W("\n   re-run with --run to execute")
        return

    t_start = time.perf_counter()

    # -------------------------------------------------------------------- T1
    W("\n" + "=" * 104)
    W(" T1. SEED ROBUSTNESS -- does breadth beat 100% invested on 3 independent"
      " seed sets?")
    W("=" * 104)
    W("  GATED on BOTH: dSharpe > 0 and dMaxDD > 3 points, on ALL three sets.")
    raw = read_table(raw_path, parse_dates=["date"])
    t1_rows = []
    for si, seeds in enumerate(VALIDATE_BREADTH_LIVE_SEED_SETS):
        cache = _t1_cache(u, si, seeds, raw_path)
        if cache.exists():
            ps = read_table(cache, parse_dates=["date"])
            W(f"    seed set {si+1}/{len(VALIDATE_BREADTH_LIVE_SEED_SETS)} {seeds} from cache {cache.name}")
        else:
            W(f"    seed set {si+1}/{len(VALIDATE_BREADTH_LIVE_SEED_SETS)} {seeds} scoring "
              f"(refits the model) ...")
            ps = score_monthly(raw, seeds)
            ps[["date", "symbol", "open", "close", "score"]].to_csv(cache, index=False)
        sp = panel_parts(ps)
        r = validate_breadth_live_compare(sp, window_dates(sp[0]), "none", "breadth")
        r = {"seedset": si, "seeds": str(seeds), **r}
        t1_rows.append(r)
        W(f"      Sharpe {r['Sharpe_a']:.2f} -> {r['Sharpe_b']:.2f} "
          f"({r['dSharpe']:+.2f})    "
          f"MaxDD {r['MaxDD_a']:.2f}% -> {r['MaxDD_b']:.2f}% "
          f"({r['dMaxDD']:+.2f} pt)    deployed {r['expo_b']:.1f}%")
    t1 = pd.DataFrame(t1_rows)
    ok_sharpe = bool((t1["dSharpe"] > 0).all())
    ok_dd = bool((t1["dMaxDD"] > DD_BAR).all())
    W(f"\n    Sharpe improved on {(t1['dSharpe'] > 0).sum()}/{len(t1)} seed sets"
      f"  -> {'PASS' if ok_sharpe else 'FAIL'}")
    W(f"    MaxDD improved by more than {DD_BAR:.0f} points on "
      f"{(t1['dMaxDD'] > DD_BAR).sum()}/{len(t1)} seed sets"
      f"  -> {'PASS' if ok_dd else 'FAIL'}")

    # -------------------------------------------------------------------- T2
    W("\n" + "=" * 104)
    W(" T2. SUB-PERIOD STABILITY -- does breadth hold in both halves?")
    W("=" * 104)
    W("  GATED on dSharpe > 0 in both halves. THERE IS NO DRAWDOWN CRITERION HERE.")
    W("  That asymmetry with T1 is inherited from validate_breadth.py, not chosen: a")
    W("  rule improving Sharpe in both halves while worsening drawdown in one")
    W("  would pass T2. MaxDD is printed below but does NOT gate.")
    t2_rows = []
    for lab, y0, y1 in VALIDATE_BREADTH_LIVE_HALVES:
        dd = window_dates(parts[0], y0, y1)
        r = {"period": lab, "first": str(dd[0].date()), "last": str(dd[-1].date()),
             "days": len(dd), **validate_breadth_live_compare(parts, dd, "none", "breadth")}
        t2_rows.append(r)
        W(f"    {lab}  ({r['first']} to {r['last']}, {r['days']} days)")
        W(f"      Sharpe {r['Sharpe_a']:.2f} -> {r['Sharpe_b']:.2f} "
          f"({r['dSharpe']:+.2f})    "
          f"MaxDD {r['MaxDD_a']:.2f}% -> {r['MaxDD_b']:.2f}% "
          f"({r['dMaxDD']:+.2f} pt, not gated)    deployed {r['expo_b']:.1f}%")
    t2 = pd.DataFrame(t2_rows)
    ok2 = bool((t2["dSharpe"] > 0).all())
    W(f"\n    Sharpe improved in {(t2['dSharpe'] > 0).sum()}/{len(t2)} halves"
      f"  -> {'PASS' if ok2 else 'FAIL'}")

    # -------------------------------------------------------------------- T3
    W("\n" + "=" * 104)
    W(" T3. CONSTANT-EXPOSURE CONTROL -- REPORTED, NOT GATED, NO VERDICT")
    W("=" * 104)
    W("  Breadth against a FIXED exposure set to breadth's OWN realised mean over")
    W("  the same window, so the average cash level is identical in both arms and")
    W("  only the timing differs.")
    W("  The constant is read from the breadth run itself; it is never a literal.")
    W("  It is therefore NOT an independent benchmark, and this does NOT test")
    W("  whether the level breadth picks is a good level -- that is unmeasured.")
    W("  No criterion is applied to any number below.")
    t3_rows = []
    for lab, dd in [("full", bd)] + [(l, window_dates(parts[0], a, b))
                                     for l, a, b in VALIDATE_BREADTH_LIVE_HALVES]:
        _, expo_b = run_mode(parts, dd, "breadth")
        r = {"period": lab, "const_level_pct": round(expo_b * 100, 2),
             "first": str(dd[0].date()), "last": str(dd[-1].date()),
             **validate_breadth_live_compare(parts, dd, "const", "breadth", const_expo=expo_b)}
        t3_rows.append(r)
        W(f"    {lab:<10} constant held at {r['const_level_pct']:.2f}% "
          f"(breadth's own realised mean over this window)")
        W(f"      Sharpe  const {r['Sharpe_a']:.2f}  breadth {r['Sharpe_b']:.2f}"
          f"   difference {r['dSharpe']:+.2f}")
        W(f"      MaxDD   const {r['MaxDD_a']:.2f}%  breadth {r['MaxDD_b']:.2f}%"
          f"   difference {r['dMaxDD']:+.2f} points")
        W(f"      CAGR    const {r['CAGR_a']:.2f}%  breadth {r['CAGR_b']:.2f}%"
          f"   difference {r['dCAGR']:+.2f} points")
    t3 = pd.DataFrame(t3_rows)

    # --------------------------------------------------------------- verdict
    passed = {"T1 seed robustness (Sharpe)": ok_sharpe,
              f"T1 seed robustness (MaxDD > {DD_BAR:.0f} pt)": ok_dd,
              "T2 sub-period stability (Sharpe)": ok2}
    n_ok = sum(passed.values())
    W("\n" + "=" * 104)
    W(f" VERDICT -- {U['label']} ({u})")
    W("=" * 104)
    for k, v in passed.items():
        W(f"    {'PASS' if v else 'FAIL'}   {k}")
    W(f"\n    {n_ok} of {len(passed)} gated criteria hold.")
    W(f"    {'PASS' if n_ok == len(passed) else 'FAIL'} on this universe.")
    W("    T3 did not enter this verdict.")
    if n_ok != len(passed):
        W("\n    A FAIL means the mechanism setting deployment for every published")
        W("    v2 and v4 number on this universe is not robust here. Per the spec,")
        W("    a disagreement between universes is reported as a disagreement and")
        W("    is not resolved toward whichever universe looks better.")

    M = U["metrics"]
    t1.to_csv(M / "breadth_live_t1.csv", index=False)
    t2.to_csv(M / "breadth_live_t2.csv", index=False)
    t3.to_csv(M / "breadth_live_t3.csv", index=False)
    params = {"universe": u, "label": U["label"],
              "window": [str(settings.BT_START_DATE.date()), str(settings.BT_END_DATE.date())],
              "seed_sets": VALIDATE_BREADTH_LIVE_SEED_SETS, "dd_bar_points": DD_BAR,
              "dd_bar_note": "underived; copied from validate_breadth.py, not recalibrated",
              "criteria": {k: bool(v) for k, v in passed.items()},
              "verdict": "PASS" if n_ok == len(passed) else "FAIL",
              "t3_gated": False,
              "runtime_sec": round(time.perf_counter() - t_start, 1),
              "git": validate_breadth_live_git_state()}
    (M / "breadth_live_params.json").write_text(json.dumps(params, indent=2))
    out = ROOT / "diagnostics" / f"breadth_live_{u}.txt"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(L) + "\n")
    print(f"\n  saved -> {M/'breadth_live_t1.csv'}")
    print(f"           {M/'breadth_live_t2.csv'}")
    print(f"           {M/'breadth_live_t3.csv'}")
    print(f"           {M/'breadth_live_params.json'}")
    print(f"           {out}")
    print(f"  runtime {params['runtime_sec']/60:.1f} min")
    # THE EXIT STATUS, ADDED 2026-09-21. This file already computed the verdict
    # and already wrote it into breadth_live_params.json as "verdict"; what it
    # did not do was return it, so it exited 0 whether the universe passed or
    # failed. Nothing measured changed here and the verdict is not recomputed --
    # the same n_ok and passed that produced the printed block produce this.
    #
    # T3 IS NOT GATED AND STILL IS NOT. It is the constant-exposure control and
    # this file already excludes it from the verdict; that exclusion is carried
    # through unchanged, and params["t3_gated"] stays False.
    rc = 0 if n_ok == len(passed) else 1
    print(f"\n  RESULT: {params['verdict']} -- {n_ok} of {len(passed)} gated "
          f"criteria hold on {U['label']} ({u}). T3 not gated.")
    return rc


def _cli_validate_breadth_live():
    """`python checks.py validate_breadth_live [ARGS]`: what running results/validate_breadth_live.py did."""
    sys.exit(validate_breadth_live())


# ======================================================================================
# check_a_close_values. From results/check_a_close_values.py (moved 2026-11-27).
# ======================================================================================
# check_a_close_values -- CHECK A of experiments/DATA_EXEC_SPEC.txt.
#
# Which column carries the bad value on a close/adj_close disagreement day?
#
# It is not symmetric: build_panel selects `close` and ignores `adj_close`, so a
# bad value in close is IN THE FEATURES AND IN THE RETURNS, while one in adj_close
# is inert.
#
# PRIMARY TEST, DECISIVE, NO EXTERNAL TRUTH REQUIRED
#     A closing price must lie inside its own session's range: low <= x <= high.
#     A value outside its own row's bounds is provably bad from the row itself.
#
# CORROBORATING TEST, NOT DECISIVE
#     A single bad price spikes on day d and reverts on d+1. Reversal ratio
#     -r(d+1)/r(d) near +1 with a large |r(d)| is that signature. A genuine crash
#     and rebound looks the same, so this never condemns a value on its own.
#
# Nothing is corrected.

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True

# The DATA DIRECTORY and METRICS DIRECTORY come from settings.py --
# the single definition. The LABEL stays local: it is printed into
# diagnostics/checkA_close_bad_values.txt. Labels are presentation; paths are
# facts. Order is load-bearing -- the report is written universe by universe.
CHECK_A_CLOSE_VALUES_LABELS = {u.tag: u.display_name for u in certified()}
CHECK_A_CLOSE_VALUES_UNIVERSES = {u.tag: (u.data_dir, u.metrics_dir, CHECK_A_CLOSE_VALUES_LABELS[u.tag])
             for u in certified()}
TOL = 1e-9


def check_a_close_values_run(uni, ddir, mdir, label, W):
    rows = []
    for f in list_dir(ddir, "*.csv"):
        x = market_data.read_price_csv(f)
        need = ["date", "open", "high", "low", "close", "adj_close"]
        if any(c not in x.columns for c in need):
            continue
        x = x[need].dropna().sort_values("date").reset_index(drop=True)
        x["symbol"] = f.stem
        x["r_close"] = x["close"].pct_change()
        x["r_adj"] = x["adj_close"].pct_change()
        x["r_close_next"] = x["r_close"].shift(-1)
        x["r_adj_next"] = x["r_adj"].shift(-1)
        rows.append(x)
    P = pd.concat(rows, ignore_index=True)

    rel = (P["close"] - P["adj_close"]).abs() / P["close"].abs().clip(lower=1e-9)
    P["disagree"] = rel > 1e-9
    D = P[P["disagree"]].copy()
    inwin = (D["date"] >= settings.BT_START_DATE) & (D["date"] <= settings.BT_END_DATE)

    # PRIMARY: does each column sit inside its OWN row's high/low?
    for col in ("close", "adj_close"):
        lo = D[col] < D["low"] - TOL
        hi = D[col] > D["high"] + TOL
        D[f"{col}_out"] = lo | hi
        D[f"{col}_viol_pct"] = np.where(
            lo, (D["low"] - D[col]) / D[col].abs().clip(lower=1e-9) * 100,
            np.where(hi, (D[col] - D["high"]) / D[col].abs().clip(lower=1e-9) * 100, 0.0))
    D["reversal_close"] = -D["r_close_next"] / D["r_close"].replace(0, np.nan)
    D["reversal_adj"] = -D["r_adj_next"] / D["r_adj"].replace(0, np.nan)

    W("=" * 100)
    W(f" CHECK A -- WHICH COLUMN CARRIES THE BAD VALUE -- {label} ({uni})")
    W("=" * 100)
    W("")
    W(f"  rows in file set        {len(P):,}")
    W(f"  close/adj_close disagree {len(D):,}   of which inside the backtest "
      f"window {int(inwin.sum()):,}")
    W("")
    W("  PRIMARY TEST -- does the value sit inside its OWN session's high/low?")
    nc = int(D["close_out"].sum())
    na = int(D["adj_close_out"].sum())
    W(f"    close      outside its own [low, high] : {nc:,} of {len(D):,}")
    W(f"    adj_close  outside its own [low, high] : {na:,} of {len(D):,}")
    W(f"    neither out of bounds                  : "
      f"{int((~D['close_out'] & ~D['adj_close_out']).sum()):,}")
    W(f"    both out of bounds                     : "
      f"{int((D['close_out'] & D['adj_close_out']).sum()):,}")
    W("")

    bad_close = D[D["close_out"]]
    if len(bad_close):
        W(f"  *** {len(bad_close):,} BAD VALUES IN close -- THE COLUMN THE ENGINE")
        W("  *** USES FOR FEATURES, RETURNS AND EXECUTION PRICES.")
        bw = bad_close[(bad_close["date"] >= settings.BT_START_DATE)
                       & (bad_close["date"] <= settings.BT_END_DATE)]
        W(f"      inside the backtest window: {len(bw):,}")
        W(f"      symbols affected: {bad_close['symbol'].nunique()}")
        W("")
        W(f"      {'symbol':<14}{'date':<12}{'close':>10}{'low':>10}{'high':>10}"
          f"{'viol%':>8}{'ret':>9}{'guard':>9}{'window':>8}")
        for _, r in bad_close.nlargest(min(40, len(bad_close)), "close_viol_pct").iterrows():
            masked = (r["r_close"] > EXTREME_RET_HI) or (r["r_close"] < EXTREME_RET_LO)
            W(f"      {r['symbol']:<14}{str(r['date'].date()):<12}{r['close']:>10.2f}"
              f"{r['low']:>10.2f}{r['high']:>10.2f}{r['close_viol_pct']:>8.2f}"
              f"{r['r_close']*100:>8.1f}%{('masked' if masked else 'PASSES'):>9}"
              f"{('in' if settings.BT_START_DATE <= r['date'] <= settings.BT_END_DATE else 'out'):>8}")
    else:
        W("  NO close VALUE ON ANY DISAGREEMENT ROW FALLS OUTSIDE ITS OWN SESSION'S")
        W("  RANGE. By this test the traded column is internally consistent on every")
        W("  row where the two columns disagree.")
    W("")

    if na:
        W(f"  adj_close out of bounds on {na:,} rows. Worst 10 by magnitude:")
        W(f"      {'symbol':<14}{'date':<12}{'adj_close':>11}{'low':>10}{'high':>10}{'viol%':>8}")
        for _, r in D[D["adj_close_out"]].nlargest(min(10, na), "adj_close_viol_pct").iterrows():
            W(f"      {r['symbol']:<14}{str(r['date'].date()):<12}{r['adj_close']:>11.2f}"
              f"{r['low']:>10.2f}{r['high']:>10.2f}{r['adj_close_viol_pct']:>8.2f}")
        W("")

    W("  CORROBORATING TEST -- spike and revert on the disagreement day")
    W("    A ratio near +1 with a large |r(d)| is the signature of a bad value.")
    W("    It is NOT decisive: a genuine crash and rebound looks identical.")
    for col, rc, rr in (("close", "r_close", "reversal_close"),
                        ("adj_close", "r_adj", "reversal_adj")):
        s = D[(D[rc].abs() > 0.05) & D[rr].notna()]
        if len(s):
            near1 = int(((s[rr] > 0.7) & (s[rr] < 1.3)).sum())
            W(f"    {col:<10} rows with |r(d)| > 5%: {len(s):>5}   "
              f"of which reversal ratio in [0.7, 1.3]: {near1:>5} "
              f"({near1/len(s)*100:.0f}%)")
        else:
            W(f"    {col:<10} no rows with |r(d)| > 5%")
    W("")
    D.to_csv(Path(mdir) / "checkA_disagreements.csv", index=False)
    W(f"  every disagreement row written to {Path(mdir).name}/checkA_disagreements.csv")
    W("")
    # nc and na are the PRIMARY TEST counts computed above; returning them adds no
    # measurement, it only stops them being discarded.
    return {"close_out": nc, "adj_close_out": na, "rows": len(D)}


def check_a_close_values():
    out = []
    res = {}
    for uni, (ddir, mdir, label) in CHECK_A_CLOSE_VALUES_UNIVERSES.items():
        # THE FARM IS BUILT ON DEMAND under cache/<tag>/ since 2026-09-23;
        # u.data_dir is only its path and is empty on a fresh tree.
        ddir = REGISTRY[uni].prepare_data_dir()
        res[uni] = check_a_close_values_run(uni, ddir, mdir, label, out.append)
        out.append("")
    # THE VERDICT LINE AND THE EXIT STATUS, ADDED 2026-09-21. No count, bound,
    # extreme-return constant or printed row changed.
    #
    # WHAT IS GATED IS THIS FILE'S OWN PRIMARY TEST, and only the traded column.
    # The report already states the condition categorically -- "NO close VALUE ON
    # ANY DISAGREEMENT ROW FALLS OUTSIDE ITS OWN SESSION'S RANGE ... the traded
    # column is internally consistent" -- so a close outside its own [low, high]
    # is a failure by the file's own words, not by a threshold chosen here.
    #
    # adj_close IS REPORTED AND NOT GATED. It is out of bounds on 170 nifty100 and
    # 41 midcap150 rows, measured 2026-09-21, and that is the exact population
    # market_data.canonical_price already falls back to the raw close on. Gating
    # it would fail the run for a condition the engine is documented to handle,
    # and this file states no tolerance for it.
    bad = {u: r for u, r in res.items() if r["close_out"]}
    tot_close = sum(r["close_out"] for r in res.values())
    tot_adj = sum(r["adj_close_out"] for r in res.values())
    out.append(f"  ungated, reported only: adj_close outside its own [low, high] "
               f"on {tot_adj:,} row(s); canonical_price falls back to close there.")
    if bad:
        out.append(f"  RESULT: FAIL -- the traded column is outside its own "
                   f"session range on {tot_close:,} row(s), on: "
                   + ", ".join(sorted(bad)) + ".")
        rc = 1
    else:
        out.append(f"  RESULT: PASS -- no close value on any disagreement row "
                   f"falls outside its own session range, across "
                   f"{len(res)} universe(s).")
        rc = 0
    (ROOT / "diagnostics" / "checkA_close_bad_values.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))
    return rc


def _cli_check_a_close_values():
    """`python checks.py check_a_close_values [ARGS]`: what running results/check_a_close_values.py did."""
    sys.exit(check_a_close_values())


# ======================================================================================
# check_b_exec_timing. From results/check_b_exec_timing.py (moved 2026-11-27).
# ======================================================================================
# check_b_exec_timing -- CHECK B of experiments/DATA_EXEC_SPEC.txt.
#
# Did every Nautilus fill execute at the NEXT session's open, as the design claims?
#
# The claim -- signal at the close of day t, fill at the open of day t+1 -- is
# stated in HANDOFF_SUMMARY and was asserted as a hardcoded PASS in engine_core's
# leakage checklist until 2026-08-29. NOTHING HAS EVER VERIFIED IT AGAINST THE FILL
# RECORD. This does.
#
# THE FILL PRICE IS THE INSTRUMENT. Each fill is tested against FOUR candidates,
# not one, so that "matches the open" can be distinguished from "matches everything
# because the tolerance is loose":
#     (a) that day's OPEN            -- the design
#     (b) that day's CLOSE           -- same-day close execution
#     (c) the PREVIOUS session's CLOSE -- signal-day close execution
#     (d) the PREVIOUS session's OPEN
#
# Slippage is applied against the trade and the port rounds the fill price to the
# paisa, so each candidate is reconstructed with costs.fill_price, the port's own
# rule, from the port's own rows (nautilus_port.quote_frame), and must equal the fill
# exactly. Every fill price must also be in whole paise. It certifies the
# PIPELINE's fills, nautilus/reports/, which since 2026-09-24 no other program
# writes.
#
# Nothing is corrected.

# SLIPPAGE comes from costs.py, which is the only definition. It was
# written out in seven files until 2026-09-22; these engines are
# cross-checked against each other, so a value changed in one and not the
# rest surfaces as a reconciliation failure elsewhere, not as a wrong
# number here. Value unchanged at 0.0015.
# EXACT EQUALITY, SINCE 2026-10-28. The port and the reconstruction both round to
# the paisa with costs.fill_price, so a fill at the open matches to the bit.
# From 2026-09-24 the port quoted on NSE's dated tick and the tolerance was half
# that tick; the tick was removed because its price band came from the adjusted
# close, which carries later splits and bonuses.
# ---------------------------------------------------------------------------
# WHICH FILL RECORD THIS READS, AND WHY IT HAS TO SAY SO
# ---------------------------------------------------------------------------
# THIS READ A PATH NOTHING HAD WRITTEN FOR ELEVEN DAYS. It asked for
# `nautilus/reports/<universe>/fills.csv`, and the port stopped writing that at
# 8568b78 (2026-09-05 02:33), which added an arm segment. The previous diagnostic
# was committed at 13:34 THE SAME DAY, from a leftover file that nothing was
# writing any more -- the warm-tree failure, in its purest form: it passed because
# the old file had not been cleaned up. Once it was, this died with
# FileNotFoundError, loudly, and nobody noticed because nobody ran it.
#
# WORSE THAN THE PATH: THE OLD FILE HAD NO ARM. One shared fills.csv per universe
# held whichever arm ran LAST, unlabelled, so the finding could not be attributed
# to anything. That is what this block fixes -- not just where to read, but the
# record of WHAT was read.
#
# THE SEGMENT COMES FROM THE WRITER'S OWN DEFINITION. nautilus_port.reports_segment() is
# what builds the directory the port writes into, carrying arm, cadence and
# profile; re-spelling that rule here would be a second definition that can
# disagree with the first, which is how the path went stale the first time.
# Importing nt_run costs about 1.4 s and pulls nautilus_trader; that is the price
# of having one rule instead of two, and this is a hand-run probe.
#
# EVERY ARM, SINCE 2026-09-26. Until then this read v2 only, on the ground that
# v2 is the shipping arm, and v1, v3 and v4 sat at sibling paths unread. Every
# arm's fills come from the same port through the same order path, and every arm
# has published figures, so each is checked the same way. Each section names its
# arm, because "whichever ran last" is exactly what made the old numbers unusable.
# The decision file is the arm's own audit artefact, named by
# backtest_runs.artefact_tag, the writer's rule (v2 unsuffixed, others _v1/_v3/_v4).


def _decisions(u, arm):
    import backtest_runs as audit_step
    return u.metrics_dir / f"daily_decisions_{audit_step.artefact_tag(u, arm)}.csv"


def check_b_exec_timing_run(uni, arm, fills_p, sc_p, dec_p, label, W):
    F = read_table(fills_p)
    F["date"] = pd.to_datetime(F["ts_event"], utc=True).dt.tz_localize(None).dt.normalize()
    F["symbol"] = F["instrument_id"].str.split(".").str[0]
    F["px"] = F["last_px"].astype(float)

    # THE PORT'S OWN INPUTS: its panel (forward filled, as nautilus_port.load_panel
    # builds it) and its quoted rows (nautilus_port.quote_frame), over the dates the
    # pipeline's run quoted, warm-up included.
    import nautilus_port as nt_data
    import nautilus_port as nt_run
    pxf, opf = nt_data.load_panel(model.require_cache(sc_p, what=f"{uni} panel"))
    q_start = pd.Timestamp(settings.BT_START_DATE) - pd.Timedelta(days=nt_run.WARMUP_DAYS)
    q_end = pd.Timestamp(nt_run.UNIVERSES[uni]["end"])
    Q = {s: nt_data.quote_frame(s, pxf, opf, q_start, q_end).set_index("date")
         for s in F["symbol"].unique()}
    cal = list(opf.index)
    prev = {d: cal[i - 1] for i, d in enumerate(cal) if i > 0}
    op = opf  # the calendar check below reads op.index

    W("=" * 100)
    W(f" CHECK B -- EXECUTION TIMING FROM THE FILL RECORD -- {label} ({uni}), arm {arm.name}")
    W("=" * 100)
    W("")
    W(f"  fills file      {fills_p.relative_to(ROOT)}")
    # THE ARM IS NAMED, AND THAT IS THE POINT OF THE REPOINT. The superseded
    # version of this file read a shared fills.csv holding whichever arm ran last,
    # so its 978 fills belonged to nothing in particular.
    W(f"  arm             {arm.name} -- {arm.label}   "
      f"(segment '{_reports_segment(arm.mode, arm.sizing)}',")
    W(f"                  from nt_run.reports_segment, the writer's own rule)")
    W(f"  fills recorded  {len(F):,}")
    # FILL PRICES IN WHOLE PAISE -- GATED. The port rounds every fill to the paisa.
    _off = int((np.abs(F["px"] * 100 - np.round(F["px"] * 100)) > 1e-6).sum())
    W(f"  off the paisa   {_off:,} of {len(F):,} fill prices")
    W(f"  price panel     {Path(sc_p).name}")
    W(f"  reconstruction  price * (1 +/- {SLIPPAGE}) rounded to the paisa")
    W("                  (costs.fill_price, the port's own rule)")
    W("  tolerance       none: exact equality")
    W("")

    recs = []
    for _, r in F.iterrows():
        d, s, side, px = r["date"], r["symbol"], r["order_side"], r["px"]
        sgn = 1.0 if side == "BUY" else -1.0
        pd_ = prev.get(d)
        qs = Q.get(s)
        def cand(col, dd):
            if qs is None or dd is None or dd not in qs.index:
                return np.nan
            v = qs.at[dd, col]
            return np.nan if pd.isna(v) else fill_price(v, SLIPPAGE, sgn > 0)
        c = {"a_open_today": cand("open", d), "b_close_today": cand("close", d),
             "c_close_prev": cand("close", pd_), "d_open_prev": cand("open", pd_)}
        m = {k: (abs(px - v) < 1e-9) if v == v else False for k, v in c.items()}
        recs.append({"date": d, "symbol": s, "side": side, "px": px,
                     "on_calendar": d in op.index, **c,
                     **{f"m_{k}": v for k, v in m.items()},
                     "n_match": sum(m.values())})
    R = pd.DataFrame(recs)

    W("  MATCHES, PER CANDIDATE (a fill may match more than one)")
    for k, lab in (("a_open_today", "(a) that day's OPEN      -- the design"),
                   ("b_close_today", "(b) that day's CLOSE     -- same-day close"),
                   ("c_close_prev", "(c) previous CLOSE       -- signal-day close"),
                   ("d_open_prev", "(d) previous OPEN")):
        W(f"    {lab:<45} {int(R[f'm_{k}'].sum()):>5} of {len(R):,}")
    W("")
    W(f"  fills matching (a): {int(R['m_a_open_today'].sum()):,} of {len(R):,}")
    W(f"  fills matching NOTHING: {int((R['n_match'] == 0).sum()):,}")
    W(f"  fills matching (a) UNIQUELY: {int((R['m_a_open_today'] & (R['n_match'] == 1)).sum()):,}")
    amb = R[R["m_a_open_today"] & (R["n_match"] > 1)]
    W(f"  fills matching (a) AND another candidate (ambiguous, the same price to")
    W(f"    the paisa -- a limit of the instrument, not an exception): {len(amb):,}")
    W("")

    bad = R[~R["m_a_open_today"]]
    W(f"  EXCEPTIONS -- fills NOT matching the fill day's open: {len(bad):,}")
    if len(bad):
        W(f"    {'date':<12}{'symbol':<14}{'side':<6}{'fill px':>10}"
          f"{'(a) open':>10}{'(b) close':>11}{'(c) prevC':>11}{'(d) prevO':>11}")
        for _, r in bad.iterrows():
            W(f"    {str(r['date'].date()):<12}{r['symbol']:<14}{r['side']:<6}"
              f"{r['px']:>10.2f}{r['a_open_today']:>10.2f}{r['b_close_today']:>11.2f}"
              f"{r['c_close_prev']:>11.2f}{r['d_open_prev']:>11.2f}")
    W("")

    only_bc = R[(~R["m_a_open_today"]) & (R["m_b_close_today"] | R["m_c_close_prev"])]
    W(f"  FILLS EXECUTING AT A CLOSE RATHER THAN AN OPEN: {len(only_bc):,}")
    W("")
    W(f"  every fill date on the panel's trading calendar: "
      f"{int(R['on_calendar'].sum()):,} of {len(R):,}")

    if Path(dec_p).exists():
        DEC = read_table(dec_p)
        # column name verified from the file, not assumed
        cands = [c for c in DEC.columns if "date" in c.lower() or "decid" in c.lower()]
        if not cands:
            raise SystemExit(f"{dec_p}: no date-like column. present: {list(DEC.columns)}")
        dcol = cands[0]
        dec_days = set(pd.to_datetime(DEC[dcol]).dt.normalize())
        nxt = {prev[d] : d for d in prev}
        ok = sum(1 for d in R["date"] if prev.get(d) in dec_days)
        W(f"  fills whose PREVIOUS session is a recorded decision date: "
          f"{ok:,} of {len(R):,}")
    else:
        W(f"  decision file {Path(dec_p).name} absent -- the 'right open' check")
        W("  could not be run, only the 'an open' check above.")
    W("")
    return {"n": len(R), "at_a_close": len(only_bc), "off_paisa": _off,
            "off_calendar": len(R) - int(R["on_calendar"].sum()),
            "not_matching_open": len(bad)}


def check_b_exec_timing():
    out = [HISTORY, ""]
    res = {}
    for uni, arm, f, s, d, lab in CELLS:
        res[f"{uni}/{arm.name}"] = (check_b_exec_timing_run(uni, arm, f, s, d, lab, out.append), f)
        out.append("")
    # THE VERDICT LINE AND THE EXIT STATUS, ADDED 2026-09-21. No measurement,
    # candidate rule or printed number above changed.
    #
    # THE VERDICT NAMES ITS INPUT, AND THE RUN LOG NAMES ITS mtime, because this file reads
    # nautilus/reports/<universe>/<seg>/fills.csv, which is GITIGNORED and holds
    # whatever last wrote it. A run of nt_verify or verify_v34_arms at a
    # non-production tick regenerates it, so a verdict that did not say which file
    # it read, and when that file was written, would be reporting on someone
    # else's run under this file's name. Measured 2026-09-21: this session's own
    # gate runs had rewritten both fills.csv at tick 0.01 fixed rather than the
    # production 0.05/nse grid.
    #
    # THE mtime IS PRINTED, NOT WRITTEN TO THE TRACKED DIAGNOSTIC (2026-09-25).
    # In the file it made every pipeline run change a committed record whose
    # verdict had not changed, so check_all left the tree dirty after any run.
    # The file keeps the repository-relative path and the fill count; the write
    # time goes to stdout, which is the run's log.
    #
    # WHAT IS GATED: no fill may execute at a CLOSE rather than an open, every
    # fill must fall on the panel's trading calendar, and every fill price must be
    # in whole paise.
    #
    # WHAT IS NOT GATED: `not_matching_open`. Three of 1,006 fills differ from the
    # day's open by 0.01 and this file states no tolerance for that, adjudicates
    # none, and separately classes near-ties as "a limit of the instrument, not an
    # exception". Picking a tolerance here would be inventing a pass condition
    # rather than reading one, so the count is reported and left ungated.
    bad_u = {u: r for u, (r, _) in res.items()
             if r["at_a_close"] or r["off_calendar"] or r["off_paisa"]}
    out.append("  INPUT READ (gitignored; holds whatever last wrote it):")
    for u, (r, f) in sorted(res.items()):
        fp = Path(f)
        mt = (datetime.fromtimestamp(fp.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
              if fp.exists() else "ABSENT")
        try:
            rel = fp.resolve().relative_to(ROOT)
        except ValueError:
            rel = fp
        out.append(f"    {u:<16} {rel}  ({r['n']:,} fills)")
        print(f"  input {rel} written {mt}")
    tot_close = sum(r["at_a_close"] for r, _ in res.values())
    tot_offcal = sum(r["off_calendar"] for r, _ in res.values())
    tot_offp = sum(r["off_paisa"] for r, _ in res.values())
    tot_nmo = sum(r["not_matching_open"] for r, _ in res.values())
    out.append(f"  ungated, reported only: {tot_nmo} fill(s) not matching the "
               f"day's open exactly.")
    if bad_u:
        out.append(f"  RESULT: FAIL -- {tot_close} fill(s) executed at a close, "
                   f"{tot_offcal} fell off the trading calendar and {tot_offp} are "
                   f"off the paisa, on: "
                   + ", ".join(sorted(bad_u)) + ".")
        rc = 1
    else:
        out.append(f"  RESULT: PASS -- gated: 0 fills match a close without matching "
                   f"the open, 0 fills fall off the trading calendar, and 0 fill "
                   f"prices are off the paisa, on "
                   f"{len(res)} universe/arm cell(s) ({len(CHECK_B_EXEC_TIMING_LABELS)} universes x "
                   f"{len(_arm_reg.ARMS)} arms). Not gated: "
                   f"that every fill matches the day's open (reported above).")
        rc = 0
    (ROOT / "diagnostics" / "checkB_execution_timing.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))
    return rc


def _check_b_exec_timing_setup():
    """What importing results/check_b_exec_timing.py did: read the command line and set up
    the module state its functions read. Called by its subcommand."""
    global _reports_segment, CHECK_B_EXEC_TIMING_LABELS, CELLS, HISTORY
    warnings.filterwarnings("ignore")
    sys.dont_write_bytecode = True
    from nautilus_port import reports_segment as _reports_segment


    # The LABEL stays local: it is printed into
    # diagnostics/checkB_execution_timing.txt. Labels are presentation; paths are
    # facts. Order is load-bearing -- the report is written universe by universe,
    # arm by arm within each universe.
    CHECK_B_EXEC_TIMING_LABELS = {u.tag: u.display_name for u in gated()}
    CELLS = [
        (u.tag, arm,
         ROOT / "nautilus" / "reports" / u.tag / _reports_segment(arm.mode, arm.sizing) / "fills.csv",
         u.score_cache, _decisions(u, arm), CHECK_B_EXEC_TIMING_LABELS[u.tag])
        for u in gated() for arm in _arm_reg.ARMS.values()
    ]


    # ---------------------------------------------------------------------------
    # THE RECORD OF WHAT THE PORT DID UNDER THE OLD LAYOUT, CARRIED INTO EVERY RERUN
    # ---------------------------------------------------------------------------
    # A HEADER ADDED TO THE FILE BY HAND WOULD BE ERASED BY THE NEXT RUN. The previous
    # diagnostic was marked stale in place on 2026-09-16, and that marking only
    # survives if the probe itself emits it. So it does. The old finding is not
    # withdrawn: it measured the port's execution semantics, which is not a fact about
    # where its reports live.
    HISTORY = """\
    --------------------------------------------------------------------------------
     SUPERSEDED MEASUREMENT, KEPT AS THE RECORD OF WHAT THE PORT DID BEFORE 2026-09-05
    --------------------------------------------------------------------------------
      The version of this diagnostic committed at 40b938e read
          nautilus/reports/<universe>/fills.csv
      and found, on nifty100, 977 of 978 fills reconstructing as that day's OPEN to
      within 0.005, with one exception (CHOLAFIN, 2020-05-22) and zero fills
      executing at a close.

      THAT FILE'S ARM IS UNKNOWN. Under the old layout one shared fills.csv per
      universe held whichever arm ran LAST, unlabelled, so the 978 fills cannot be
      attributed to a strategy. Read it as a property of the port, not of an arm.

      The port stopped writing that path at 8568b78, 2026-09-05 02:33. The
      superseded diagnostic was committed eleven hours later, from a file nothing
      was writing any more.
    --------------------------------------------------------------------------------
    """


def _cli_check_b_exec_timing():
    """`python checks.py check_b_exec_timing [ARGS]`: what running results/check_b_exec_timing.py did."""
    _check_b_exec_timing_setup()
    sys.exit(check_b_exec_timing())


# ======================================================================================
# leakage_check1_causality. From results/leakage_check1_causality.py (moved 2026-11-27).
# ======================================================================================
# leakage_check1_causality -- CHECK 1 of experiments/LEAKAGE_SPEC.txt.
#
# For every feature in FEATS_V2: compute its value at day t on the real panel;
# corrupt every row STRICTLY AFTER t; recompute; compare at day t, BIT-EXACT.
#
# Any feature whose day-t value moves when only future rows changed is reading
# forward. Two independent corruptions are applied because one could leave a value
# unchanged by coincidence:
#     (a) REPLACE  future rows get a synthetic random walk
#     (b) SHUFFLE  future rows are permuted in time, per symbol
#
# BOTH feature stages are recomputed, because add_market_relative_features derives
# a market return at PANEL level -- a per-symbol-only test could not see a leak
# entering through the market series.
#
# Reports THE LIST, per feature, not a summary verdict. Nothing is fixed here.

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True

N_DATES = 24
PRICE_COLS = ["open", "high", "low", "close"]

# The DATA DIRECTORY comes from settings.py -- the single definition.
# The LABEL stays local: this file's "NIFTY 100"/"MIDCAP150" spelling is printed
# into diagnostics/leakage_check1_causality.txt, and the sibling scripts use two
# other spellings for the same two universes. Labels are presentation; paths are
# facts. Order is load-bearing -- the report is written universe by universe.
LEAKAGE_CHECK1_CAUSALITY_LABELS = {u.tag: u.display_name for u in gated()}
LEAKAGE_CHECK1_CAUSALITY_UNIVERSES = {u.tag: (u.data_dir, LEAKAGE_CHECK1_CAUSALITY_LABELS[u.tag])
             for u in gated()}


def load_raw(d):
    frames = []
    for f in list_dir(d, "*.csv"):
        x = market_data.read_price_csv(f)[["date", "open", "high", "low", "close",
                                      "volume"]].dropna().sort_values("date")
        x["symbol"] = f.stem
        x["raw_close"] = x["close"]   # amihud_20's rupee volume uses the unadjusted close
        frames.append(x)
    return pd.concat(frames, ignore_index=True)


def pipeline(raw):
    """Exactly the two feature stages build_panel runs, in the same order."""
    out = [add_stock_features(g.sort_values("date").copy())
           for _, g in raw.groupby("symbol")]
    return add_market_relative_features(pd.concat(out, ignore_index=True))


def corrupt(raw, t, mode, seed):
    """Corrupt every row strictly after date t. Rows up to and including t are
    left byte-identical, so any change at t is the feature reaching forward."""
    rng = np.random.default_rng(seed)
    c = raw.copy()
    fut = c["date"] > t
    if mode == "replace":
        n = int(fut.sum())
        # A synthetic positive random walk: prices stay valid so that a NaN
        # cannot masquerade as agreement.
        base = rng.uniform(50, 5000, size=n)
        c.loc[fut, "close"] = base
        c.loc[fut, "raw_close"] = base
        c.loc[fut, "open"] = base * rng.uniform(0.97, 1.03, size=n)
        c.loc[fut, "high"] = base * rng.uniform(1.00, 1.08, size=n)
        c.loc[fut, "low"] = base * rng.uniform(0.92, 1.00, size=n)
        c.loc[fut, "volume"] = rng.uniform(1e3, 1e8, size=n)
    elif mode == "shuffle":
        # Permute the future block in time, within each symbol.
        for sym, g in c[fut].groupby("symbol"):
            idx = g.index.to_numpy()
            perm = rng.permutation(idx)
            for col in PRICE_COLS + ["raw_close", "volume"]:
                c.loc[idx, col] = c.loc[perm, col].to_numpy()
    else:
        raise ValueError(mode)
    return c


def compare_at(ref, test, t):
    """Bit-exact comparison of every feature at date t, across all symbols."""
    a = ref[ref["date"] == t].sort_values("symbol")
    b = test[test["date"] == t].sort_values("symbol")
    if list(a["symbol"]) != list(b["symbol"]):
        raise SystemExit("symbol sets diverged at t -- the corruption changed rows it must not")
    res = {}
    for f in FEATS_V2:
        x = a[f].to_numpy(dtype=np.float64)
        y = b[f].to_numpy(dtype=np.float64)
        same = np.array_equal(x, y, equal_nan=True)
        if same:
            res[f] = (True, 0, 0.0)
        else:
            d = ~((x == y) | (np.isnan(x) & np.isnan(y)))
            with np.errstate(invalid="ignore"):
                mx = float(np.nanmax(np.abs(x[d] - y[d]))) if d.any() else 0.0
            res[f] = (False, int(d.sum()), mx)
    return res


def leakage_check1_causality_run(uni, d, label, W):
    raw = load_raw(d)
    ref = pipeline(raw)
    # Sample dates spread across the BACKTEST window, not the whole price panel.
    dates = sorted(x for x in ref["date"].unique()
                   if settings.BT_START_DATE <= x <= settings.BT_END_DATE)
    picks = [dates[i] for i in np.linspace(0, len(dates) - 1, N_DATES).astype(int)]
    nsym = ref["symbol"].nunique()

    W("=" * 100)
    W(f" CHECK 1 -- FEATURE CAUSALITY -- {label} ({uni})")
    W("=" * 100)
    W("")
    W(f"  symbols {nsym}   panel rows {len(ref):,}")
    W(f"  dates sampled {len(picks)} spread across "
      f"{picks[0].date()} .. {picks[-1].date()}")
    W(f"  cells compared per feature: {len(picks)} dates x {nsym} symbols x "
      f"2 corruptions = {len(picks)*nsym*2:,}")
    W("  corruption (a) replace: future rows overwritten with a synthetic random walk")
    W("  corruption (b) shuffle: future rows permuted in time within each symbol")
    W("  comparison: BIT-EXACT (np.array_equal with equal_nan)")
    W("")

    fail = {f: {"replace": [], "shuffle": []} for f in FEATS_V2}
    for i, t in enumerate(picks):
        for mode in ("replace", "shuffle"):
            res = compare_at(ref, pipeline(corrupt(raw, t, mode, seed=1000 + i)), t)
            for f, (ok, ncell, mx) in res.items():
                if not ok:
                    fail[f][mode].append((str(pd.Timestamp(t).date()), ncell, mx))

    W("-" * 100)
    W(f" {'feature':<24}{'(a) replace':>14}{'(b) shuffle':>14}   verdict")
    W("-" * 100)
    leaking = []
    for f in FEATS_V2:
        na, nb = len(fail[f]["replace"]), len(fail[f]["shuffle"])
        ok = (na == 0 and nb == 0)
        if not ok:
            leaking.append(f)
        W(f" {f:<24}{('bit-exact' if na==0 else f'{na} dates MOVED'):>14}"
          f"{('bit-exact' if nb==0 else f'{nb} dates MOVED'):>14}"
          f"   {'causal' if ok else 'READS FORWARD'}")
    W("-" * 100)
    W("")
    if leaking:
        W(f"  {len(leaking)} OF {len(FEATS_V2)} FEATURES MOVED WHEN ONLY FUTURE ROWS CHANGED:")
        for f in leaking:
            for mode in ("replace", "shuffle"):
                for dt, ncell, mx in fail[f][mode][:6]:
                    W(f"    {f:<22} {mode:<8} {dt}  cells {ncell:>4}  max|diff| {mx:.6g}")
    else:
        W(f"  ALL {len(FEATS_V2)} FEATURES BIT-EXACT UNDER BOTH CORRUPTIONS AT EVERY")
        W("  SAMPLED DATE. No feature's day-t value moved when only future rows changed.")
    W("")
    W("  WHAT THIS DOES NOT SAY: dates are sampled, so a leak confined to dates")
    W("  outside this sample would survive. It tests the feature stage only --")
    W("  the training mask and the label are CHECK 2.")
    W("")
    return leaking


def leakage_check1_causality():
    out = []
    bad = {}
    for uni, (d, label) in LEAKAGE_CHECK1_CAUSALITY_UNIVERSES.items():
        # THE FARM IS BUILT ON DEMAND under cache/<tag>/ since 2026-09-23;
        # u.data_dir is only its path and is empty on a fresh tree.
        d = REGISTRY[uni].prepare_data_dir()
        bad[uni] = leakage_check1_causality_run(uni, d, label, out.append)
        out.append("")
    # THE VERDICT LINE AND THE EXIT STATUS, ADDED 2026-09-21. `bad` was already
    # collected here and then dropped on the floor; nothing about the corruption
    # test, the sampled dates or the comparison changed. The pass condition is
    # the one the report already states -- no feature's day-t value may move when
    # only future rows change, on either universe.
    #
    # WHAT A PASS STILL DOES NOT SAY, and the report says this too: dates are
    # SAMPLED, so a leak confined to dates outside the sample survives this. A
    # green here is evidence, not proof.
    leaking = {u: v for u, v in bad.items() if v}
    if leaking:
        for u, v in leaking.items():
            out.append(f"  LEAKING on {u}: {', '.join(sorted(v))}")
        out.append(f"  RESULT: FAIL -- {sum(len(v) for v in leaking.values())} "
                   f"feature-universe pair(s) moved under a future-only corruption.")
        rc = 1
    else:
        out.append(f"  RESULT: PASS -- no FEATS_V2 value at t moved when every row "
                   f"after t was corrupted, on {N_DATES} sampled dates per universe, "
                   f"on {len(bad)} universe(s): {', '.join(sorted(bad))}. Dates "
                   f"outside the sample and the labels are not tested.")
        rc = 0
    (ROOT / "diagnostics" / "leakage_check1_causality.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))
    return rc


def _cli_leakage_check1_causality():
    """`python checks.py leakage_check1_causality [ARGS]`: what running results/leakage_check1_causality.py did."""
    sys.exit(leakage_check1_causality())


# ======================================================================================
# leakage_check2_trading_purge. From results/leakage_check2_trading_purge.py (moved 2026-11-27).
# ======================================================================================
# leakage_check2_trading_purge -- CHECK 2 of experiments/LEAKAGE_SPEC.txt: no
# training label ends after the purge limit of the month it trains.
# ==============================================================================
#
# WHAT IS CHECKED
#
#     For every month score_monthly would train, the training rows are taken from
#     model.training_set -- the function score_monthly calls, not a copy of
#     it -- on the universe's cached raw panel. For each row the date its label
#     ends (`label_end`, the symbol's own row HORIZON rows ahead) is placed on the
#     panel's calendar, and
#
#         gap = position(first scored session) - position(latest label_end)
#
#     in trading sessions. THE GATE IS gap >= PURGE_EMBARGO IN EVERY TRAINED MONTH
#     ON EVERY GATED UNIVERSE. training_set promises that by construction; this
#     checks the promise on the real panels.
#
#     A second assertion: every training target is a rank within the training
#     rows of its own date, so it lies in (0, 1]. A target ranked over labels that
#     had not ended would still lie there, which is why the label-end test above is
#     the gate and this one only catches a malformed target.
#
# WHY IT WAS REWRITTEN ON 2026-10-22
#
#     The previous version recovered the latest training DATE and added HORIZON
#     sessions on the panel's calendar. That measures where a label ends for a
#     symbol with no missing sessions only. A symbol's label is HORIZON of its own
#     rows ahead, so across a gap it ends later; the old check passed on 252 of 252
#     month-universe pairs while smallcap250 pit had labels ending up to 25
#     sessions past the limit. The label end date is now in the panel and is read
#     directly.
#
#     The calendar-rule sibling, leakage_check2_purge.py, was deleted the same day
#     with the calendar rule itself.
#
# MONTHS THE ENGINE SKIPS ARE NOT INVENTED INTO THE COUNT. A month with no
# qualifying cut, fewer than 5,000 training rows, or nothing scorable never trains;
# those months are counted and reported as skipped.
#
# USAGE
#
#     python checks.py leakage_check2_trading_purge
#
#     Writes diagnostics/leakage_check2_trading_purge.txt. Exits non-zero if any
#     trained month on any gated universe has a label ending inside its purge window.

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True

LEAKAGE_CHECK2_TRADING_PURGE_LABELS = {u.tag: u.display_name for u in gated()}
LEAKAGE_CHECK2_TRADING_PURGE_UNIVERSES = {u.tag: (u.raw_cache, LEAKAGE_CHECK2_TRADING_PURGE_LABELS[u.tag]) for u in gated()}


def leakage_check2_trading_purge_run(uni, perm, label, W):
    src = model.require_cache(perm, what=f"{uni} raw panel")
    raw = read_table(src, parse_dates=["date", "label_end"])

    W("=" * 100)
    W(f" CHECK 2 (TRADING RULE) -- TRAINING LABELS AGAINST THE PURGE LIMIT -- {label} ({uni})")
    W("=" * 100)
    W("")
    W(f"  panel {src.name}   rows {len(raw):,}   symbols {raw['symbol'].nunique()}")
    W(f"  HORIZON = {HORIZON} rows of the symbol's own history   "
      f"PURGE_EMBARGO = {PURGE_EMBARGO} sessions")

    # The panel exactly as score_monthly orders it.
    p = raw.sort_values(["date", "symbol"]).reset_index(drop=True)
    cal = np.array(sorted(p["date"].unique()))
    pos = {d: i for i, d in enumerate(cal)}
    ym_col = p["date"].dt.to_period("M")
    months = sorted(ym_col[p["date"] >= model.score_floor()].unique())

    rows, skipped, bad_target = [], 0, 0
    for ym in months:
        first = p.loc[ym_col == ym, "date"].min()
        i = pos[np.datetime64(first)]
        ts = model.training_set(p, cal, i)
        te = (ym_col == ym) & p["scorable"]
        if ts is None or len(ts[1]) < 5000 or not te.any():
            skipped += 1
            continue
        tri, y = ts
        bad_target += int(((y <= 0) | (y > 1)).sum())
        latest_end = p.loc[tri, "label_end"].max()
        j = pos[np.datetime64(latest_end)]
        rows.append({"month": str(ym), "first_scored": str(first.date()),
                     "train_rows": len(y), "latest_label_end": str(latest_end.date()),
                     "gap_trading_days": i - j,
                     "gap_calendar_days": (first - latest_end).days})
    W(f"  scoring months considered: {len(months)}   trained: {len(rows)}   "
      f"skipped by the engine's rule: {skipped}")
    W("")

    D = pd.DataFrame(rows)
    if D.empty:
        W("  NO MONTH TRAINED. Nothing to assert.")
        return {"trained": 0, "below": 0, "bad_target": 0}

    g = D["gap_trading_days"]
    below = D[g < PURGE_EMBARGO]
    W("  WHERE THE LATEST TRAINING LABEL ENDS -- gap to the first scored session, in "
      "TRADING sessions")
    W(f"    min {g.min()}   p5 {np.percentile(g, 5):.0f}   median {g.median():.0f}"
      f"   p95 {np.percentile(g, 95):.0f}   max {g.max()}")
    W(f"    months with gap < {PURGE_EMBARGO} (a label ends inside the purge window): "
      f"{len(below)} of {len(D)}")
    W(f"    training targets outside (0, 1]: {bad_target}")
    W("")
    if len(below):
        W("    THE PURGE DOES NOT HOLD IN THESE MONTHS:")
        for _, r in below.iterrows():
            W(f"      {r['month']}  first scored {r['first_scored']}  latest label end "
              f"{r['latest_label_end']}  gap {r['gap_trading_days']} sessions")
        W("")
    W("  THE TIGHTEST MONTHS (smallest gaps):")
    W(f"  {'month':<10}{'first scored':<14}{'latest label':<14}{'gap td':>7}{'gap cal':>9}")
    for _, r in D.nsmallest(8, "gap_trading_days").iterrows():
        W(f"  {r['month']:<10}{r['first_scored']:<14}{r['latest_label_end']:<14}"
          f"{r['gap_trading_days']:>7}{r['gap_calendar_days']:>9}")
    W("")
    md = REGISTRY[uni].metrics_dir
    # naming: axis-free -- the per-month gap table for one universe under the
    # live purge rule. It describes the TRAINING MASK, not a strategy result, so
    # it varies over no arm, cadence, profile or tax selection; the universe is
    # carried by the directory it is written into.
    D.to_csv(md / "leakage_purge_gaps_trading.csv", index=False)
    W(f"  every month written to {md.name}/leakage_purge_gaps_trading.csv")
    W("")
    return {"trained": len(D), "below": len(below), "bad_target": bad_target}


def leakage_check2_trading_purge():
    out = []
    res = {}
    for uni, (perm, label) in LEAKAGE_CHECK2_TRADING_PURGE_UNIVERSES.items():
        res[uni] = leakage_check2_trading_purge_run(uni, perm, label, out.append)
        out.append("")

    tot_tr = sum(r["trained"] for r in res.values())
    bad = {u: r for u, r in res.items() if r["below"] or r["bad_target"]}
    out.append("  RULE TESTED: engine_core.training_set, the rule score_monthly runs: "
               "row date <= cal[i - HORIZON - PURGE_EMBARGO]")
    out.append("  and label_end <= cal[i - PURGE_EMBARGO], targets ranked within the "
               "qualifying rows of each date.")
    if bad:
        out.append("  RESULT: FAIL -- a training label ends inside the purge window, or "
                   "a target is malformed, on: "
                   + ", ".join(f"{u} ({r['below']} month(s), {r['bad_target']} target(s))"
                               for u, r in sorted(bad.items())) + ".")
        rc = 1
    else:
        per = ", ".join(f"{u} {r['trained']}" for u, r in sorted(res.items()))
        out.append(f"  RESULT: PASS -- the latest training label ends at least "
                   f"{PURGE_EMBARGO} sessions before the first scored session in every "
                   f"trained month, {tot_tr} month-universe pair(s) across "
                   f"{len(res)} universe(s) ({per}).")
        rc = 0
    # naming: axis-free -- one report on the training mask under the live purge
    # rule, covering every gated universe, which are named inside the file.
    (ROOT / "diagnostics" / "leakage_check2_trading_purge.txt").write_text(
        "\n".join(out) + "\n")
    print("\n".join(out))
    return rc


def _cli_leakage_check2_trading_purge():
    """`python checks.py leakage_check2_trading_purge [ARGS]`: what running results/leakage_check2_trading_purge.py did."""
    sys.exit(leakage_check2_trading_purge())


# ======================================================================================
# nt_attribution. From nautilus/nt_attribution.py (moved 2026-11-27).
# ======================================================================================
# nt_attribution -- explain the gap between the reference engine and Nautilus.
#
# THE QUESTION
#     The reference engine ends at Rs 31,01,677 and the Nautilus port at Rs 31,90,675
#     -- a gap of about 2.9%, or 0.43 points of CAGR. Is that gap the KNOWN structural
#     difference, or is it a bug?
#
# SIZING
#     Since 2026-10-28 the engine, this copy and the port all size a buy at the close
#     of the decision session t, from the book at that close and the close price
#     with slippage:
#         q = (book_value(t close) * exposure * 0.98 * weight) // (close(t) * (1 + s))
#     The open of t+1 sets only the fill price, the cash test and the trim. Until
#     then the engine and this copy sized at the open of t+1 and the port matched
#     them; the ARM B that sized at the close is gone with that difference.
#
# THE TEST
#     Run this copy on the port's data and scores. Both fill at the open with
#     slippage, rounded to the paisa by costs.fill_price, so the two final
#     equities should agree; the gap printed is what remains.
#
# This file does not modify the production engine. It re-implements the loop locally
# so that results/ is untouched.

# Inlined from market_data.precompute so this script does not need lightgbm.
NT_ATTRIBUTION_VOL_WIN = 60
def nt_attribution_precompute(px, vol_win=NT_ATTRIBUTION_VOL_WIN):
    return {"vol": rolling_std(px.pct_change(), vol_win) * np.sqrt(252)}

NT_ATTRIBUTION_REBAL = 20
# SELECTION -- imported from settings.py, the single definition.
NT_ATTRIBUTION_TOP_N, NT_ATTRIBUTION_BUFFER = settings.TOP_N, settings.BUFFER
# SLIPPAGE comes from costs.py, which is the only definition. It was
# written out in seven files until 2026-09-22; these engines are
# cross-checked against each other, so a value changed in one and not the
# rest surfaces as a reconciliation failure elsewhere, not as a wrong
# number here. Value unchanged at 0.0015.
# THE DEFAULT, defined once in settings.capital_axis. A run's capital is
# capital_axis.selected(); this name stays for callers that want the default.
NT_ATTRIBUTION_START_CAPITAL = capital_axis.DEFAULT
SAFETY = 0.98


def nt_attribution_load_panel(cache_path):
    """The price/score panel every arm runs on. Shared with checks.py nt_verify so both
    scripts are provably reading the same input. cache_path selects the universe
    and is required: until 2026-09-24 it defaulted to the retired 58's panel,
    which no longer exists."""
    p = read_table(cache_path, parse_dates=["date"])
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    sc = p.pivot_table(index="date", columns="symbol", values="score")
    # Window from settings.py so the reference re-implementation cuts on exactly
    # the same dates as the engine. A year cut here against a date cut there
    # would make nt_verify fail on rebalance COUNT for a reason unrelated to
    # sizing or execution.
    bd = px.index[(px.index >= settings.BT_START_DATE)
                  & (px.index <= settings.BT_END_DATE)]
    return px, op, sc, bd, nt_attribution_precompute(px), px / px.shift(20) - 1


# ---------------------------------------------------------------------------
# SIZING AND EXPOSURE MODE -- must mirror nt_strategy and test_exposure exactly
# ---------------------------------------------------------------------------
# This module is the REFERENCE side that nt_verify compares the port against. If
# it stayed on inverse-vol while the port ran pro-vol, every pro-vol arm would
# fail verification for a reason that has nothing to do with the port. Same guard
# (vol > 0.01), same zero on failure, same normalisation, same fallback.
# PASSED PER CALL, NOT SET AS A MODULE GLOBAL. run() already takes its other
# switches as keyword arguments; sizing and mode
# now join them. The globals they replace were process-wide, so a value
# left behind by one arm silently applied to the next, and asserting the global had
# been set never proved the run used it. See nautilus_port.py nt_strategy for the same change.
DEFAULT_SIZING = "invvol"
DEFAULT_MODE = "breadth"


def nt_attribution_run(px, op, sc, dates, pc, mom20, holdings_out=None,
        sizing: str = DEFAULT_SIZING, mode: str = DEFAULT_MODE, applied_out=None,
        rebal: int = None, drawdown_stop=None, stop_events_out=None, dd_overlay=None,
        buy_shortfall: str = None, fills_out=None):
    """`holdings_out`, when a dict is passed, is filled with
    {rebalance_date: {symbol: qty}} -- the holdings standing at each decision, which
    is the same quantity the port records in strat.holdings_log and the same one
    the reference engine's daily_holdings file reports. It is an out-parameter
    rather than an extra return value so existing three-value callers keep
    working.

    `drawdown_stop` runs the stop of v5/v6 through portfolio.py, the
    state machine the engine and the port also run; `stop_events_out`, a list,
    receives its events. Both None for the core arms, which then run the loop
    exactly as before.

    `dd_overlay`, a dd_axis.DDLimit, runs the drawdown-limit axis through
    portfolio.py, the class the engine and the port also run. None,
    the default, runs none of its code.

    `buy_shortfall`, "trim" or "refuse", is what a buy cash cannot fully pay for
    does, as in the engine (portfolio.py). None reads portfolio.selected().

    `fills_out`, a list, receives one row per fill in the port's strat.fills
    shape (date, action, symbol, qty, price). nt_verify compares it with the
    port's strat.fills."""
    import portfolio as _bsf
    import settings
    _shortfall = settings.shortfall_axis.selected() if buy_shortfall is None else buy_shortfall

    def _fill(dt, action, s, q, pr):
        if fills_out is not None:
            fills_out.append({"date": dt, "action": action, "symbol": s,
                              "qty": int(q), "price": float(pr)})

    def _afford(q, pr):
        """(q, charges) for a buy of q at fill price pr, cut to what cash pays for
        under trim; q is 0 when the buy is refused."""
        if cash >= q * pr:
            tc = calc_tc(pr, q, "BUY")
            if cash >= q * pr + tc:
                return q, tc
        if _shortfall != "trim":
            return 0, 0.0
        q, _, tc, _ = _bsf.trim(q, cash, lambda n: pr, lambda p_, n: calc_tc(p_, n, "BUY"))
        return q, tc

    # THE CADENCE, AS AN ARGUMENT. REBAL stays the module DEFAULT and is never
    # reassigned: module_state.py records that rebal_cadence_sweep.py:172 writes
    # portfolio.REBAL and never restores it, and that every later step then
    # backtests on the wrong cadence with nothing saying so. A parameter cannot
    # leak into the next call; a global can, and did.
    #
    # THIS SIDE AND nt_strategy MUST MOVE TOGETHER. verify_v34_arms compares the
    # port against this reference at each rebalance date, so a cadence that
    # reached only one of them would fail the gate for a reason that has nothing
    # to do with the port -- the same trap the old SIZING global set.
    _reb = NT_ATTRIBUTION_REBAL if rebal is None else int(rebal)
    if _reb < 1:
        raise ValueError(f"rebal must be >= 1, got {rebal!r}")
    if sizing not in ("invvol", "provol"):
        raise ValueError(f"sizing must be 'invvol' or 'provol', got {sizing!r}")
    if mode not in ("breadth", "none"):
        raise ValueError(f"mode must be 'breadth' or 'none', got {mode!r}")
    shares, cash = {}, float(capital_axis.selected())
    eq, pending, n_trades, cum_tc = [], None, 0, 0.0
    _stop = drawdown_stop
    if _stop is not None:
        from portfolio import StopState
        _st = StopState(_stop, _reb, len(dates))
        _EXIT = ({"_exposure": 0.0}, set())
    _dd = dd_overlay
    if _dd is not None:
        from portfolio import OverlayState
        _ds = OverlayState(_dd, capital_axis.selected())
        _expo_last = 1.0

    for i, dt in enumerate(dates):
        prices, opens = px.loc[dt], op.loc[dt]
        if _stop is not None:
            _st.begin_day()
            _held_before = dict(shares)

        if pending is not None:
            plan, keep = pending
            for s in list(shares.keys()):
                if s not in keep:
                    pr = opens.get(s, np.nan)
                    if np.isnan(pr) or pr <= 0:
                        continue
                    pr = fill_price(pr, SLIPPAGE, False)
                    q = int(shares[s]); tc = calc_tc(pr, q, "SELL")
                    cash += q * pr - tc; cum_tc += tc; n_trades += 1
                    _fill(dt, "SELL", s, q, pr)
                    del shares[s]

            if plan:
                # Sized from the decision close: the book's value and each name's
                # close there, with slippage. This open sets only the fill price.
                invest_val = dec_val * plan["_exposure"] * SAFETY
                if _dd is not None:
                    invest_val *= _ds.entry_factor(plan["_exposure"])
                for s, w in plan.items():
                    if s == "_exposure" or s in shares:
                        continue
                    cp = dec_px.get(s, np.nan)
                    pr = opens.get(s, np.nan)
                    if np.isnan(cp) or cp <= 0 or np.isnan(pr) or pr <= 0:
                        continue
                    q = int((invest_val * w) // (cp * (1 + SLIPPAGE)))
                    pr = fill_price(pr, SLIPPAGE, True)
                    if q < 1:
                        continue
                    q, tc = _afford(q, pr)
                    if q < 1:
                        continue
                    cash -= q * pr + tc; cum_tc += tc; n_trades += 1
                    _fill(dt, "BUY", s, q, pr)
                    shares[s] = shares.get(s, 0) + q
            pending = None
            if _stop is not None and (_st.exit_pending or _st.reentry_pending):
                _st.after_fills(i, shares, _held_before,
                                lambda k: pd.Timestamp(dates[k]).date())

        # THE DRAWDOWN-LIMIT ORDER, after the arm's fills: the engine's sequence
        # (portfolio.py), without the cap, tax or impact this copy
        # never models.
        if _dd is not None and _ds.order is not None:
            _ord = _ds.order
            _before = {s: int(shares[s]) for s in _ord if s in shares}
            for s in sorted(_before):
                dq = _ord[s]
                if dq >= 0:
                    continue
                pr = opens.get(s, np.nan)
                if np.isnan(pr) or pr <= 0:
                    continue
                pr = fill_price(pr, SLIPPAGE, False)
                q = min(-dq, int(shares[s]))
                tc = calc_tc(pr, q, "SELL")
                cash += q * pr - tc; cum_tc += tc; n_trades += 1
                _fill(dt, "SELL", s, q, pr)
                shares[s] -= q
                if shares[s] == 0:
                    del shares[s]
            _buys = [(s, _ord[s]) for s in sorted(_before) if _ord[s] > 0 and s in shares]
            _need = 0.0
            for s, dq in _buys:
                pr = opens.get(s, np.nan)
                if not (np.isnan(pr) or pr <= 0):
                    _need += dq * fill_price(pr, SLIPPAGE, True)
            _f = min(1.0, cash * SAFETY / _need) if _need > 0 else 1.0
            for s, dq in _buys:
                pr = opens.get(s, np.nan)
                if np.isnan(pr) or pr <= 0:
                    continue
                pr = fill_price(pr, SLIPPAGE, True)
                q = int(dq * _f)
                if q < 1:
                    continue
                tc = calc_tc(pr, q, "BUY")
                if cash < q * pr + tc:
                    continue
                cash -= q * pr + tc; cum_tc += tc; n_trades += 1
                _fill(dt, "BUY", s, q, pr)
                shares[s] += q
            _ds.cancel()

        _grid = i % _reb == 0 and i < len(dates) - 1
        _reentry = False
        if _grid and _stop is not None and _st.state != "IN":
            def _breadth():
                _m = mom20.loc[dt].dropna()
                return float((_m > 0).mean()) if len(_m) else 1.0
            _grid = _reentry = _st.grid_allows_order(i, _breadth)
        if _grid:
            m = mom20.loc[dt].dropna()
            expo = float((m > 0).mean()) if len(m) else 1.0
            expo = 1.0 if mode == "none" else max(0.0, min(1.0, expo))
            if _dd is not None:
                _expo_last = expo     # the engine's expo_log[-1]
            if applied_out is not None:
                applied_out["mode"] = mode
            s_ = sc.loc[dt].dropna()
            s_ = s_[[k for k in s_.index if not np.isnan(prices.get(k, np.nan))]]
            if len(s_) >= NT_ATTRIBUTION_TOP_N:
                rk = s_.sort_values(ascending=False)
                top, keep = list(rk.index[:NT_ATTRIBUTION_TOP_N]), set(rk.index[:NT_ATTRIBUTION_BUFFER])
                # Recorded at the same point in the sequence as the port's
                # holdings_log: the decision is going ahead, and these are the
                # positions standing when it is taken.
                if holdings_out is not None:
                    holdings_out[dt] = {s: int(q) for s, q in shares.items() if q}
                v = pc["vol"].loc[dt]
                w = {}
                for s in top:
                    vs = v.get(s, np.nan)
                    ok = (not np.isnan(vs)) and vs > 0.01
                    if not ok:
                        w[s] = 0.0
                    elif sizing == "provol":
                        w[s] = vs
                    else:
                        w[s] = 1.0 / vs
                tot = sum(w.values())
                w = ({s: w[s] / tot for s in top} if tot > 0
                     else {s: 1.0 / len(top) for s in top})
                if applied_out is not None:
                    applied_out["sizing"] = sizing

                w["_exposure"] = expo
                pending = (w, keep)
            if _reentry:
                _st.after_reentry_order(pending is not None)

        mtm = sum(q * prices[s] for s, q in shares.items()
                  if not np.isnan(prices.get(s, np.nan)))
        if _stop is not None:
            if _st.at_close(i, dt, cash + mtm, pending is not None, bool(shares),
                            i == len(dates) - 1) == "exit":
                pending = _EXIT
            if stop_events_out is not None:
                stop_events_out.extend(_st.rows(dt, cash + mtm))
        if _dd is not None:
            _ds.at_close(dt, cash + mtm, mtm, shares, i == len(dates) - 1, _expo_last)
        eq.append(cash + mtm)
        dec_val, dec_px = cash + mtm, prices

    return pd.Series(eq, index=dates), n_trades, cum_tc


def _cli_nt_attribution():
    """`python checks.py nt_attribution [ARGS]`: what running nautilus/nt_attribution.py did."""
    global yrs
    import nautilus_port as nt_run
    from settings import CERTIFIED, argv_universes, check_tags
    _picked = check_tags(argv_universes(sys.argv), nt_run.UNIVERSES)
    _tag = _picked[-1] if _picked else CERTIFIED[0]
    _strat = nt_run.run(str(settings.BT_START_DATE.date()), str(settings.BT_END_DATE.date()),
                        universe=_tag)
    NAUTILUS_EQUITY = _strat.daily_equity[-1]["equity"]

    px, op, sc, bd, pc, mom20 = nt_attribution_load_panel(nt_run.UNIVERSES[_tag]["cache"])

    print("=" * 74)
    print("ATTRIBUTION TEST -- is the Nautilus gap the known sizing difference?")
    print("=" * 74)

    a_eq, a_n, a_tc = nt_attribution_run(px, op, sc, bd, pc, mom20)

    yrs = (bd[-1] - bd[0]).days / 365.25
    def cagr(e): return ((e.iloc[-1] / capital_axis.selected()) ** (1 / yrs) - 1) * 100

    print(f"\n  reference copy, fills at the open : Rs {a_eq.iloc[-1]:>12,.0f}  "
          f"CAGR {cagr(a_eq):5.2f}%  trades {a_n}")
    print(f"  NAUTILUS                          : Rs {NAUTILUS_EQUITY:>12,.0f}")
    gap = (NAUTILUS_EQUITY - a_eq.iloc[-1]) / a_eq.iloc[-1] * 100
    print(f"\n  reference -> Nautilus             : {gap:+6.2f}%")


# ======================================================================================
# nt_verify. From nautilus/nt_verify.py (moved 2026-11-27).
# ======================================================================================
# nt_verify -- one command that reports the true state of the Nautilus port.
#
# Runs the port, compares it against the reference engine on three levels, and
# prints what matches, what does not, and by how much. Nothing here is hardcoded:
# every number is produced by the run it describes.
#
# Run: ./venv/bin/python checks.py nt_verify --universe=nifty100 [--arm=v3] [--rebal=3]
#                                              [--dd=20 [--dd-m=5] [--dd-floor=25]]
#                                              [--capital=5000000]
#
# --arm=NAME verifies that arm (default v2): the port runs with the arm's mode and
# sizing, the reference copy (nt_attribution) takes the same, and the reference
# files are the arm's own audit trail, named by backtest_runs.artefact_tag. Added
# 2026-09-26; before that every run verified v2.
#
# --rebal=N at a non-default cadence REPORTS the port-vs-vectorised gap at that
# cadence and exits 0. It does not gate: the share-level verdict below is the
# default-cadence certification and is unchanged. See KNOWN_ISSUES.md for the gap
# measured at cadences 20, 3 and 1 on 2026-09-23.
#
# Both sides size every buy at the decision session's close (since 2026-10-28), so
# neither values its book at the open. The quote-mid exemption that covered the
# port's open valuation (added 2026-09-29, pass I) went with it.
#
# --buy-shortfall=trim|refuse picks the buy rule (portfolio.py) for the port,
# the reference copy and the reference trail's name; the default is
# settings.BUY_SHORTFALL.
#
# THE VERDICT. Both sides price every fill with costs.fill_price, to the paisa.
# The port and the reference copy must hold the same names and quantities at every
# rebalance and fill the same orders (name, side, quantity) in every rebalance
# period: n of n, with no exemption. Any period that differs is unexplained and
# fails.
#
# Since 2026-10-28 there is one run of each side. Until then the port quoted on
# NSE's dated tick (0.05 for most of the window), and the verdict re-ran both sides
# on a uniform 0.01 grid to separate tick rounding from logic. The dated tick took
# its price band from the adjusted close, which carries later splits and bonuses,
# so it was removed, and the paisa run is now the only one.

# Selected by --universe on the command line. THE CHOICES ARE THE REGISTRY, not a
# written-down tuple: the tuple used to name two retired universes, and the
# default was one of their tags, so this module raised KeyError at import the day
# they were deleted. The reference CSVs, the price panel and the score parquet all move
# together, because a verification is only meaningful when both sides read the same
# universe.
# An unknown tag, including a retired short tag, exits with the list of valid
# universes rather than falling back to the default.

# --dd=L [--dd-m=m] [--dd-floor=F]: THE DRAWDOWN-LIMIT AXIS. The selection is set
# here, so the reference trail is found by the writer's own name (_ref_tag), and the
# overlay rides in _ARM_KW to the port and to both reference re-runs. This command
# runs at research profile and tax off only; a cell with the axis on under tax or
# the tradeable profile is outside port verification (the port has no tax ledger
# and no participation cap).
def _flag(name):
    return next((a.split("=", 1)[1] for a in sys.argv if a.startswith(f"--{name}=")), None)


def stop_dates(rows):
    """{(date, event)} for the stop's key events."""
    return {(pd.Timestamp(r["date"]).normalize(), r["event"]) for r in rows
            if r["event"] in STOP_KEY_EVENTS}


def _ref_tag():
    """The arm's audit-trail tag at the default cadence and profile, tax off.

    v2 is the unsuffixed TAG the reference files have always used; the other arms
    are suffixed by the writer's own rule."""
    sys.path.insert(0, str(ROOT / "results"))
    import backtest_runs as audit_step
    from settings import REGISTRY
    return audit_step.artefact_tag(REGISTRY[UNIVERSE], ARM)


def nt_verify_compare(a_all, b_all, dates):
    """Compare two {date: {symbol: qty}} maps over the same rebalance dates.

    Returns (mismatches, symbol-set mismatches, quantity-only mismatches, errors%).
    """
    mism = sym_mism = qty_only = 0
    worst = []
    for d in dates:
        a, b = a_all.get(d, {}), b_all.get(d, {})
        if a == b:
            continue
        mism += 1
        if set(a) != set(b):
            sym_mism += 1
        else:
            qty_only += 1
            for s in a:
                if a[s] != b[s]:
                    worst.append(abs(a[s] - b[s]) / max(b[s], 1) * 100)
    return mism, sym_mism, qty_only, worst


def report(label, stats, n):
    mism, sym_mism, qty_only, worst = stats
    print(f"\n  {label}")
    print(f"    identical holdings      : {n - mism} of {n}")
    print(f"    differing by symbol set : {sym_mism}")
    print(f"    differing by quantity   : {qty_only}")
    if worst:
        w = pd.Series(worst)
        print(f"    quantity error: median {w.median():.2f}%  max {w.max():.2f}%")


def port_holdings(strat):
    """{rebalance_date: {symbol: qty}} plus the rebalance dates themselves.

    THE REBALANCE DATES COME FROM `decisions`, NOT FROM `holdings_log`.
    holdings_log emits one row per HELD symbol, so a rebalance that starts from an
    empty portfolio -- 2019-01-01, the first one -- emits nothing at all. Counting
    its distinct dates therefore reported 92 against the reference's 93 and made a
    bookkeeping artefact look like a missing rebalance. There is no missing
    rebalance: the run itself reports 93.
    """
    dates = [pd.Timestamp(d["decided_on"]) for d in strat.decisions]
    # COLUMNS GIVEN, because a stop arm can take every decision from an empty book,
    # and then holdings_log has no rows at all.
    hp = pd.DataFrame(strat.holdings_log, columns=["date", "symbol", "qty"])
    hp["date"] = pd.to_datetime(hp["date"])
    port = {d: {} for d in dates}
    for _, r in hp.iterrows():
        port[r["date"]][r["symbol"]] = int(r["qty"])
    return dates, port


def nt_verify_arm(panel, dates, **kwargs):
    """Holdings from one arm of the reference re-implementation, on `dates`."""
    out = {}
    nt_attribution_run(*panel, holdings_out=out, **kwargs)
    return {d: out.get(d, {}) for d in dates}


def fills_by_period(rows, dates):
    """{rebalance date: {(symbol, side): (qty, price)}} from fill rows.

    A fill belongs to the last rebalance decided before its date, so a
    rebalance's period holds the orders it released the next morning. Partial
    fills of one order are summed; the price is their quantity-weighted mean."""
    ds = sorted(dates)
    out = {d: {} for d in ds}
    for r in rows:
        when = pd.Timestamp(r["date"]).normalize()
        prior = [d for d in ds if d < when]
        if not prior:
            raise ValueError(f"a fill on {when.date()} precedes the first rebalance")
        key = (r["symbol"], r["action"])
        q0, p0 = out[prior[-1]].get(key, (0, 0.0))
        q = q0 + int(r["qty"])
        out[prior[-1]][key] = (q, (q0 * p0 + int(r["qty"]) * float(r["price"])) / q)
    return out


def compare_fills(a, b):
    """[(rebalance date, rupees)] for every period whose fills differ, a against b.

    rupees is the value of the differing shares: |qty difference| per (symbol,
    side) at side a's price, or side b's where a has no such fill."""
    out = []
    for d in a:
        fa, fb = a[d], b.get(d, {})
        if {k: q for k, (q, _) in fa.items()} == {k: q for k, (q, _) in fb.items()}:
            continue
        rs = 0.0
        for k in set(fa) | set(fb):
            qa, pa = fa.get(k, (0, None))
            qb, pb = fb.get(k, (0, None))
            if qa != qb:
                rs += abs(qa - qb) * (pa if pa is not None else pb)
        out.append((d, rs))
    return out


def cadence_gap(rebal):
    """Port vs vectorised final equity at a non-default cadence. Reported, not gated.

    Both sides are v2 at `rebal`: the port run here, the vectorised reference from
    that cadence's daily_summary, named by the writer's own rule. The reference
    must already exist -- run `run.py --universe <u> --arm v2 --rebal <n>` first.
    """
    from settings import cadence as _cd
    sys.path.insert(0, str(ROOT / "results"))
    import backtest_runs as audit_step
    from portfolio import ARMS
    from settings import REGISTRY
    _cd.set_selection(rebal)
    ref_f = NT_VERIFY_M / f"daily_summary_{audit_step.artefact_tag(REGISTRY[UNIVERSE], ARMS['v2'])}.csv"
    if not ref_f.exists():
        print(f"  no vectorised reference at {ref_f.name}; run "
              f"./venv/bin/python run.py --universe {UNIVERSE} --arm v2 --rebal {rebal}")
        return 1
    with contextlib.redirect_stdout(io.StringIO()):
        strat = nt_run.run(str(settings.BT_START_DATE.date()), U["end"], quiet=True,
                           universe=UNIVERSE, rebal=rebal)
    port = pd.DataFrame(strat.daily_equity).set_index("date")["equity"]
    ref = read_table(ref_f, parse_dates=["date"]).set_index("date")["total"]
    p_fin, r_fin = float(port.iloc[-1]), float(ref.iloc[-1])
    print(f"  cadence {rebal}  {UNIVERSE} v2")
    print(f"    Nautilus final equity   Rs {p_fin:,.2f}   ({strat.rebalances} rebalances, "
          f"{strat.orders_submitted} orders)")
    print(f"    vectorised final equity Rs {r_fin:,.2f}   ({ref_f.name})")
    print(f"    gap                     Rs {p_fin - r_fin:+,.2f}  "
          f"({(p_fin / r_fin - 1) * 100:+.3f}%)   REPORTED, NOT GATED")
    return 0


def nt_verify():
    from settings import cadence as _cd
    if NT_VERIFY_REBAL is not None and NT_VERIFY_REBAL != _cd.DEFAULT:
        return cadence_gap(NT_VERIFY_REBAL)
    strat = nt_run.run(str(settings.BT_START_DATE.date()), U["end"], universe=UNIVERSE,
                       **_ARM_KW)
    TAG = _ref_tag()

    eq = pd.DataFrame(strat.daily_equity)
    eq["date"] = pd.to_datetime(eq["date"])
    eq = eq.set_index("date")["equity"]
    ref_eq = read_table(NT_VERIFY_M / f"daily_summary_{TAG}.csv", parse_dates=["date"]) \
               .set_index("date")["total"]

    # THE INTERSECTION USED TO HIDE A MISSING DAY, AND DID.
    #     `common` silently discards any date one side lacks, so when the port's
    #     series held 1,841 rows against the reference's 1,842 the comparison simply
    #     moved to the last date they shared and reported it as "final equity". The
    #     missing 2026-06-08 carried ten fills on a retired universe and twelve on
    #     midcap150. Nothing in the output said so: the numbers looked like a clean
    #     0.03% agreement.
    #
    #     A date index that does not match is a defect to report, not a set to
    #     narrow. The comparison below still runs -- it is diagnostic and refusing to
    #     print it would be less useful -- but the mismatch is stated first and the
    #     equity line is labelled with the date it actually describes.
    idx_ok = (len(eq.index) == len(ref_eq.index)
              and eq.index[0] == ref_eq.index[0]
              and eq.index[-1] == ref_eq.index[-1])
    common = eq.index.intersection(ref_eq.index)

    dates, port = port_holdings(strat)

    hr = read_table(NT_VERIFY_M / f"daily_holdings_{TAG}.csv", parse_dates=["date"])
    ref = {d: {} for d in dates}
    for _, r in hr[hr["date"].isin(dates)].iterrows():
        ref[r["date"]][r["symbol"]] = int(r["qty"])

    panel = nt_attribution_load_panel(U["cache"])
    # THE REFERENCE COPY: the engine's loop re-implemented in nt_attribution and run
    # on the port's panel and scores, with the same fill price rule. The port is
    # gated against it. Its own holdings must keep the engine's selection
    # (daily_holdings_{TAG}.csv), which is checked below rather than assumed: it is
    # what licenses the copy as the baseline.
    _r_hold, r_fills, r_ev = {}, [], []
    nt_attribution_run(*panel, holdings_out=_r_hold, fills_out=r_fills,
                       stop_events_out=r_ev, **_ARM_KW)
    arm_r = {d: _r_hold.get(d, {}) for d in dates}

    ref_stats = nt_verify_compare(port, ref, dates)
    r_stats = nt_verify_compare(port, arm_r, dates)
    a_check = nt_verify_compare(arm_r, ref, dates)
    o_diff = compare_fills(fills_by_period(strat.fills, dates), fills_by_period(r_fills, dates))
    h_diff = [d for d in dates if port.get(d, {}) != arm_r.get(d, {})]
    unexplained = sorted(set(h_diff) | {d for d, _ in o_diff})

    fp = pd.DataFrame(strat.fills)
    fr = read_table(NT_VERIFY_M / f"daily_trades_{TAG}.csv", parse_dates=["date"])

    n = len(dates)
    print("\n" + "=" * 72)
    print(f" NAUTILUS PORT -- VERIFICATION AGAINST THE REFERENCE ENGINE  [{UNIVERSE} universe, arm {ARM.name}]")
    print("=" * 72)
    print(f"  buy rule: {RULE} -- fills to the paisa on both sides; holdings and "
          f"orders identical on every rebalance")
    if not idx_ok:
        print("\n  *** DATE INDEX MISMATCH -- the two series do not cover the same days ***")
        print(f"      port      {len(eq.index):>5} rows   "
              f"{eq.index[0].date()} -> {eq.index[-1].date()}")
        print(f"      reference {len(ref_eq.index):>5} rows   "
              f"{ref_eq.index[0].date()} -> {ref_eq.index[-1].date()}")
        only_ref = ref_eq.index.difference(eq.index)
        only_prt = eq.index.difference(ref_eq.index)
        if len(only_ref):
            print(f"      missing from the PORT      ({len(only_ref)}): "
                  f"{', '.join(str(d.date()) for d in only_ref[:8])}"
                  f"{' ...' if len(only_ref) > 8 else ''}")
        if len(only_prt):
            print(f"      missing from the REFERENCE ({len(only_prt)}): "
                  f"{', '.join(str(d.date()) for d in only_prt[:8])}"
                  f"{' ...' if len(only_prt) > 8 else ''}")
        print("      Every figure below is computed on the shared dates only, so it")
        print("      does NOT describe the full window. Fix the mismatch first.")

    # Labelled with the date it actually describes. This used to say "final equity"
    # while reporting the last SHARED day, which on a mismatched index is not the
    # final day of either series.
    _d = common[-1]
    _lab = "final equity" if idx_ok else "equity on last shared day"
    print(f"\n  {_lab}  ({_d.date()})")
    print(f"                 reference Rs {ref_eq.loc[_d]:>12,.0f}")
    print(f"                 port      Rs {eq.loc[_d]:>12,.0f}"
          f"   ({(eq.loc[_d] / ref_eq.loc[_d] - 1) * 100:+.2f}%)")
    # daily_holdings_{TAG}.csv has a row per day, not per rebalance, so count the
    # rebalance dates from the decisions file instead.
    n_ref = len(read_table(NT_VERIFY_M / f"daily_decisions_{TAG}.csv"))
    print(f"\n  rebalances     reference {n_ref:>4}   port {n:>4}")
    # INFORMATIONAL ONLY -- the verdict below does not read these numbers.
    print(f"  fills [FYI]    reference {len(fr):>4}   port {len(fp):>4}"
          f"   (not a pass/fail gate)")

    report("vs REFERENCE (the engine's own audit trail, not gated)", ref_stats, n)
    report("vs the reference copy (gated)", r_stats, n)
    # THE CONTROL GATES SELECTION AND MEASURES SIZING. checks.nt_attribution_run and
    # portfolio.backtest_exposure are two of this repository's backtest
    # reimplementations. Selection is gated; their integer sizing is reported only.
    # See KNOWN_ISSUES.md, "There are FIVE reimplementations of the backtest".
    _a_mism, _a_sym, _a_qty, _a_worst = a_check
    print(f"\n  control: the reference copy vs the reference's own holdings")
    print(f"           SELECTION (gated)  -- {n - _a_sym} of {n} rebalances hold "
          f"the same symbol set")
    print(f"           SIZING (not gated) -- {_a_qty} of {n} differ in quantity "
          f"only" + (f", worst {max(_a_worst):.2f}% on a single position"
                     if _a_worst else ""))

    print(f"\n  port vs the reference copy, to the paisa")
    print(f"    holdings at each rebalance (name, quantity) -- "
          f"{n - len(h_diff)} of {n} identical")
    print(f"    orders filled per rebalance period (name, side, quantity) -- "
          f"{n - len(o_diff)} of {n} identical")
    for d, rs in o_diff[:20]:
        print(f"      differs: {d.date()}  Rs {rs:,.2f} of differing shares  UNEXPLAINED")
    if len(o_diff) > 20:
        print(f"      ... {len(o_diff) - 20} more")
    for d in [d for d in h_diff if d not in {x for x, _ in o_diff}][:20]:
        print(f"      holdings differ: {d.date()}  UNEXPLAINED")

    # THE EXIT STATUS. ONLY "VERIFIED" IS A PASS. INCONCLUSIVE is not a pass: it
    # says the reference copy is not a trustworthy baseline, so the run
    # established nothing and must not be read as agreement.
    rc = 1
    print("\n" + "=" * 72)
    if not idx_ok:
        print("  NOT VERIFIED. The port and the reference do not cover the same set of")
        print("  trading days, so no figure above describes the same window on both")
        print("  sides. This is reported rather than intersected away because a silent")
        print("  intersection is what let a missing final day -- carrying ten fills on")
        print("  a retired universe -- go unnoticed while the output read as a clean")
        print("  agreement.")
    elif a_check[1] != 0:
        print("  INCONCLUSIVE. The reference copy does not reproduce the reference")
        print("  engine's own SELECTION -- the two engines hold different symbols, so")
        print("  the copy is not a trustworthy baseline for the port. Fix that first.")
    elif unexplained:
        print(f"  NOT VERIFIED. {len(unexplained)} rebalance(s) differ between the port")
        print("  and the reference copy in holdings or in the orders filled. Both price")
        print("  every fill to the paisa with one function, so nothing explains a")
        print("  difference. Do not trade this.")
    else:
        print("  VERIFIED. The port and the reference copy hold the same names and")
        print("  quantities at every rebalance and fill the same orders in every")
        print("  rebalance period, with every fill priced to the paisa on both sides.")
        rc = 0
    # THE STOP ARM'S EXITS AND RE-ENTRIES, port against the engine's own record.
    if ARM.stop is not None:
        _sf = NT_VERIFY_M / f"daily_stop_events_{TAG}.csv"
        eng_ev = (read_table(_sf, parse_dates=["date"]).to_dict("records")
                  if _sf.exists() else [])
        p_set, e_set = stop_dates(strat.stop_events), stop_dates(eng_ev)
        a_set = stop_dates(r_ev)
        _common = eq.index.intersection(ref_eq.index)
        _gap = float(((eq.loc[_common] / ref_eq.loc[_common]) - 1).abs().max() * 100)
        print(f"\n  DRAWDOWN STOP -- {len(e_set)} key events in {_sf.name}")
        print(f"    port vs engine        : {len(p_set & e_set)} shared, "
              f"{len(p_set - e_set)} port only, {len(e_set - p_set)} engine only")
        print(f"    copy vs engine        : {len(a_set & e_set)} shared, "
              f"{len(a_set - e_set)} copy only, {len(e_set - a_set)} engine only")
        for d, e in sorted(p_set ^ e_set)[:20]:
            print(f"      differs: {d.date()} {e}  ({'port' if (d, e) in p_set else 'engine'} only)")
        print(f"    daily equity, port vs engine: largest gap {_gap:.4f}% over "
              f"{len(_common)} days (reported, not gated, as for every arm)")
        print(f"    exits {sum(1 for _, e in e_set if e == 'trigger')}, re-entries "
              f"{sum(1 for _, e in e_set if e == 're-entry filled')}")
        if not e_set or p_set != e_set:
            print("  NOT VERIFIED. The port's exit and re-entry dates are not the engine's.")
            rc = 1
    print(f"\n  RESULT: {'PASS' if rc == 0 else 'FAIL'} -- universe {UNIVERSE}, arm {ARM.name}, "
          f"buy rule {RULE}, holdings {n - len(h_diff)} of {n} identical, "
          f"orders {n - len(o_diff)} of {n} identical, "
          f"{len(unexplained)} unexplained.")
    print("=" * 72)
    return rc


def _nt_verify_setup():
    """What importing nautilus/nt_verify.py did: read the command line and set up
    the module state its functions read. Called by its subcommand."""
    global nt_data, nt_run, _picked, UNIVERSE, U, NT_VERIFY_M, TAG, NT_VERIFY_REBAL, _ARM_NAME, ARM, _ARM_KW, _dda, _DD, _capa, RULE, STOP_KEY_EVENTS
    import nautilus_port as nt_data
    import nautilus_port as nt_run
    _picked = check_tags(argv_universes(sys.argv), nt_run.UNIVERSES)
    UNIVERSE = _picked[-1] if _picked else next(iter(nt_run.UNIVERSES))
    U = nt_run.UNIVERSES[UNIVERSE]
    NT_VERIFY_M = U["metrics"]
    TAG = U["tag"]
    NT_VERIFY_REBAL = next((int(a.split("=", 1)[1]) for a in sys.argv if a.startswith("--rebal=")), None)
    _ARM_NAME = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--arm=")), "v2")
    if _ARM_NAME not in _ARMS:
        raise SystemExit(f"unknown arm {_ARM_NAME!r}; known: {', '.join(_ARMS)}")
    ARM = _ARMS[_ARM_NAME]
    # THE ARM'S OWN KWARGS: mode and sizing, and for v5/v6 the drawdown stop, which
    # the port and the reference copy then both run. Sealed for a stop arm unless the
    # test fixture is set (portfolio.FIXTURE_ENV).
    _ARM_KW = ARM.kwargs


    if _flag("dd") is not None:
        from settings import dd_axis as _dda
        _DD = _dda.make(float(_flag("dd")),
                        float(_flag("dd-m")) if _flag("dd-m") is not None else None,
                        float(_flag("dd-floor")) if _flag("dd-floor") is not None else None)
        if ARM.stop is not None:
            raise SystemExit("--dd cannot be used with a stop arm (v5/v6)")
        _dda.set_selection(_DD)
        _ARM_KW = dict(ARM.kwargs, dd_overlay=_DD)
        print(f"  drawdown-limit axis: {_dda.label()} -- research profile, tax off")
    elif _flag("dd-m") is not None or _flag("dd-floor") is not None:
        raise SystemExit("--dd-m and --dd-floor need --dd")

    # --capital=RUPEES: THE STARTING-CAPITAL AXIS. Selected here, so the port's starting
    # balance (nt_run), the reference copy's cash (nt_attribution) and the reference
    # trail's name (_ref_tag) all follow it. Research profile, tax off, as every cell here.
    if _flag("capital") is not None:
        from settings import capital_axis as _capa
        _capa.set_selection(int(_flag("capital")))
        print(f"  starting capital: Rs {_capa.selected():,}")

    # --buy-shortfall=trim|refuse: THE BUY RULE. Selected here, so the port
    # (nt_strategy), the reference copy (nt_attribution) and the reference trail's
    # name (_ref_tag, through backtest_runs.artefact_tag) all follow it.
    if _flag("buy-shortfall") is not None:
        settings.shortfall_axis.set_selection(_flag("buy-shortfall"))
    RULE = settings.shortfall_axis.selected()
    # THE STOP'S DATES, compared exactly: these events on these days, on both sides.
    STOP_KEY_EVENTS = ("trigger", "exit fills", "flat", "re-entry order", "re-entry filled",
                       "peak reset", "trigger on the last session")


def _cli_nt_verify():
    """`python checks.py nt_verify [ARGS]`: what running nautilus/nt_verify.py did."""
    _nt_verify_setup()
    sys.exit(nt_verify())


# ======================================================================================
# verify_v34_arms. From verify_v34_arms.py (moved 2026-11-27).
# ======================================================================================
# verify_v34_arms -- the V34 correctness gate: nt_verify for all four arms.
#
# experiments/V34_SPEC.txt requires VERIFIED at 92 of 92 rebalances for EVERY arm on
# BOTH universes. If any arm fails, no performance number may be reported for it.
#
# WHY A DRIVER RATHER THAN FOUR nt_verify INVOCATIONS
#     checks.py nt_verify reads its universe from sys.argv at import time and does its work
#     in main(). It has no per-arm entry point. This drives its pieces directly so
#     all four arms are verified in one process against one panel.
#
# THE STALE-CONFIG RISK, AND HOW IT IS PROVEN ABSENT
#     Sizing used to be a module-level global in two places -- nautilus_port.SIZING and
#     checks.SIZING -- and four arms in one process is exactly the setup where
#     a value left over from the previous arm silently verifies the wrong rule and
#     still prints 92 of 92. This file guarded that by asserting both globals held the
#     intended value before each arm.
#
#     That guard was weaker than it looked: it proved the global had been SET, never
#     that the run USED it. The exposure mode proved the point -- there was none, so
#     every arm ran at breadth exposure while the sizing asserts passed happily, and
#     v1/v3 were verified as configurations that were never actually run.
#
#     Both are now passed as arguments, and BOTH SIDES RECORD WHAT THEY ACTUALLY
#     APPLIED, on the branch actually taken. This asserts against that recording and
#     prints it. An arm whose configuration never reaches the decision point now fails
#     here instead of passing.
#
#     Both sides must move together. If only the port switched, a pro-vol arm would
#     be compared against an inverse-vol reference and would fail for a reason that
#     has nothing to do with the port.
#
# Nothing is hardcoded: the 92 comes from the run's own rebalance count. The four
# arms come from portfolio.py, so an arm added there is verified here with no
# edit to this file.
#
# Reads the panels and writes NOTHING TRACKED. It is not side-effect free, and the
# docstring used to say "writes nothing in the repository", which was wrong: each
# nautilus_port.run() call writes orders.csv / fills.csv / positions.csv. Those go to
# nautilus/reports/{universe}/{arm}/ -- gitignored, and per-arm since 2026-09-04,
# before which all four arms of a universe overwrote one directory and only the
# last survived.
#
#     python3 checks.py verify_v34_arms                       # both universes, four arms each
#     python3 checks.py verify_v34_arms --universe=midcap150  # one universe

# NO TOLERANCE. From 2026-09-27 to 2026-10-28 midcap150 v1 to v3 were allowed to
# pass when every divergence was exactly one share, from the port valuing its book
# at the mid of two tick-rounded quotes. Both sides now size buys from the decision
# close, that mechanism is gone, and every cell must be 92 of 92 again.


def verify_arm(universe, arm, mode, sizing):
    """Return (n_rebalances, n_identical, observed_port, observed_ref, detail).

    WHAT REPLACED THE GLOBAL ASSERT, AND WHY IT IS STRONGER. This used to set
    nautilus_port.SIZING and checks.SIZING and assert both had taken the
    value. That proved the global was SET; it never proved the run USED it -- and
    the exposure mode was being ignored entirely while those asserts passed.
    Both sides now take the configuration as an argument and record what they
    actually applied, on the branch actually taken. The assert reads that recording
    back, so an arm whose configuration never reached the decision point fails here
    instead of passing.
    """

    U = nt_run.UNIVERSES[universe]
    with contextlib.redirect_stdout(io.StringIO()):
        strat = nt_run.run(str(settings.BT_START_DATE.date()), U["end"],
                           quiet=True, universe=universe,
                           sizing=sizing, mode=mode, drawdown_stop=None)
        dates, port = port_holdings(strat)
        panel = nt_attribution_load_panel(U["cache"])
        ref_applied = {"sizing": None, "mode": None}
        ref = nt_verify_arm(panel, dates, sizing=sizing, mode=mode,
                            applied_out=ref_applied)
    stats = nt_verify_compare(port, ref, dates)

    mism, sym_mism, qty_only, worst = stats
    n = len(dates)
    detail = None
    if mism:
        for d in dates:
            if port.get(d, {}) != ref.get(d, {}):
                detail = (d, port.get(d, {}), ref.get(d, {}))
                break
    # READ BACK WHAT EACH SIDE ACTUALLY APPLIED, not what it was asked to apply.
    port_applied, ref_a = strat.applied, ref_applied
    for who, got in (("nt_strategy", port_applied), ("nt_attribution", ref_a)):
        assert got["sizing"] == sizing, \
            f"{who} applied sizing {got['sizing']!r}, expected {sizing!r}"
        assert got["mode"] == mode, \
            f"{who} applied mode {got['mode']!r}, expected {mode!r}"
    obs_port = f"{port_applied['mode']}/{port_applied['sizing']}"
    obs_ref = f"{ref_a['mode']}/{ref_a['sizing']}"
    return n, n - mism, obs_port, obs_ref, detail


def verify_v34_arms():
    from settings import argv_universes, check_tags
    unis = check_tags(argv_universes(sys.argv), VERIFY_V34_ARMS_UNIVERSES) or VERIFY_V34_ARMS_UNIVERSES
    print("=" * 100)
    print(" V34 CORRECTNESS GATE -- nt_verify, four arms, both universes")
    print("=" * 100)
    print(f"  window {settings.BT_START_DATE.date()} to {settings.BT_END_DATE.date()}"
          f"   (from config.py, shared by engine and port)")
    print("  the applied columns are what each side RECORDED at its decision point,")
    print("  not what it was asked to apply, so they cannot report a rule the code")
    print("  did not actually use.")

    failures = []
    for u in unis:
        print(f"\n  {u.upper()}")
        print(f"    {'arm':<5}{'intended':<16}{'port applied':<17}"
              f"{'reference applied':<20}{'result':<16}verdict")
        for arm, mode, sizing in ARMS:
            n, ok, ps, rs, detail = verify_arm(u, arm, mode, sizing)
            intended = f"{mode}/{sizing}"
            agree = (ps == intended == rs)
            verdict = "VERIFIED" if (ok == n and agree) else "NOT VERIFIED"
            if verdict != "VERIFIED":
                failures.append((u, arm, intended, n, ok, ps, rs, detail))
            print(f"    {arm:<5}{intended:<16}{ps:<17}{rs:<20}"
                  f"{f'{ok} of {n}':<16}{verdict}")

    print("\n" + "=" * 100)
    if failures:
        print(" GATE FAILED")
        print("=" * 100)
        for u, arm, intended, n, ok, ps, rs, detail in failures:
            print(f"\n  {u} {arm} (intended {intended}): {ok} of {n} identical")
            print(f"    port applied {ps!r}   reference applied {rs!r}")
            if detail:
                d, pd_, rd_ = detail
                syms = sorted(set(pd_) | set(rd_))
                print(f"    first diverging rebalance: {pd.Timestamp(d).date()}")
                print(f"      {'symbol':<14}{'port':>10}{'reference':>12}")
                for s in syms:
                    a, b = pd_.get(s, 0), rd_.get(s, 0)
                    mark = "" if a == b else "   <-- differs"
                    print(f"      {s:<14}{a:>10}{b:>12}{mark}")
        print("\n  Per the spec, NO performance number is reported for a failing arm.")
        sys.exit(1)
    print(" GATE PASSED -- every arm VERIFIED on every universe run")
    print("=" * 100)


def _verify_v34_arms_setup():
    """What importing verify_v34_arms.py did: read the command line and set up
    the module state its functions read. Called by its subcommand."""
    global nt_run, nt_strategy, ARMS, VERIFY_V34_ARMS_UNIVERSES
    _nt_verify_setup()
    sys.dont_write_bytecode = True
    warnings.filterwarnings("ignore")
    import nautilus_port as nt_run
    import nautilus_port as nt_strategy

    # BOTH REGISTRIES FEED THIS FILE, and it is the one place where that matters
    # most: this is the correctness gate, so a name here that disagreed with the name
    # the engine uses would verify the wrong thing and still print 92 of 92.
    #
    # ARMS carries each arm's MODE and SIZING, both taken from portfolio.py rather
    # than re-listed here, so the gate cannot drift from the definition the research
    # engine uses.
    # NOW CARRIES THE EXPOSURE MODE TOO. Until 2026-09-04 the port had no exposure
    # mode -- it always used breadth -- so v1/v3 (mode="none", 100% invested) could not
    # be expressed and this gate ran two configurations twice, printing 92 of 92 for
    # four arms it had only two of. mode is threaded through now, so the four arms are
    # four arms.
    ARMS = [(a.name, a.mode, a.sizing) for a in ARM_REGISTRY.values()]
    # ORDER IS LOAD-BEARING AND IS NOT registry.LIVE's ORDER. LIVE is the registry's
    # declaration order (midcap150 first), while this report -- like every other
    # script here -- runs nifty100 first. Using LIVE swapped the two blocks in the
    # output. registry.CERTIFIED states the order once.
    VERIFY_V34_ARMS_UNIVERSES = [u.tag for u in certified()]


def _cli_verify_v34_arms():
    """`python checks.py verify_v34_arms [ARGS]`: what running verify_v34_arms.py did."""
    _verify_v34_arms_setup()
    verify_v34_arms()


# ======================================================================================
# verify_next_open_execution. From nautilus/verify_next_open_execution.py (moved 2026-11-27).
# ======================================================================================
# verify_next_open_execution -- a synthetic probe of Nautilus's next-open execution.
#
# WHAT A PASS SAYS: on five invented bars, with a LatencyModel and an explicit open
# tick, one market order submitted at a close fills at the next day's open. It does
# not exercise the production port, which runs with LATENCY_NS = 0 and sends orders
# at the next open instead (nautilus_port.py nt_run), and it covers no universe. The
# production fills are checked by checks.py check_b_exec_timing.
#
# THE RULE (from the existing engine, and from the leakage checklist):
#     signal at the CLOSE of day t  ->  order fills at the OPEN of day t+1
#     Same-day close execution is a look-ahead and must never happen.
#
# WHAT WAS MEASURED (three configurations, day 4 has OPEN=150 and CLOSE=152):
#
#     1. Bars only, no latency          -> filled at 104.00  = the CLOSE of day 3
#                                          SAME-DAY EXECUTION. This is look-ahead.
#     2. Bars + latency, no open tick   -> filled at 152.00  = the CLOSE of day 4
#                                          Right day, wrong price.
#     3. Bars + latency + open tick     -> filled at 150.00  = the OPEN of day 4
#                                          CORRECT.
#
# WHY BOTH PIECES ARE REQUIRED:
#     - Without a latency model, a market order is immediately marketable and fills
#       against the book as it stands at submission, i.e. the current bar's close.
#     - Without an explicit open-price tick, the next price the exchange sees is the
#       following bar, which resolves to its close.
#     Supplying the open as its own data point makes the execution price explicit
#     rather than an artefact of how bars are decomposed internally.
#
# CONCLUSION: feed each trading day as TWO events --
#     09:15  TradeTick  at the day's OPEN   (this is what orders execute against)
#     15:30  Bar        with the day's OHLC (this is what signals are computed from)
# and attach a LatencyModel so orders cannot fill inside the bar that created them.
#
# Run: python3 checks.py verify_next_open_execution


def _verify_next_open_execution_setup():
    """What importing nautilus/verify_next_open_execution.py did: read the command line and set up
    the module state its functions read. Called by its subcommand."""
    global pd, BacktestEngine, BacktestEngineConfig, LoggingConfig, USD, AccountType, OmsType, OrderSide, AggressorSide, Venue, TradeId, Money, Price, Quantity, Bar, BarType, TradeTick, TestInstrumentProvider, Strategy, LatencyModel, VENUE, inst, BT, T, FILLS, TARGET_PX, eng, prices, d0, data, i, o, h, l, c, day, t_open, t_close
    import pandas as pd
    from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
    from nautilus_trader.config import LoggingConfig
    from nautilus_trader.model.currencies import USD
    from nautilus_trader.model.enums import AccountType, OmsType, OrderSide, AggressorSide
    from nautilus_trader.model.identifiers import Venue, TradeId
    from nautilus_trader.model.objects import Money, Price, Quantity
    from nautilus_trader.model.data import Bar, BarType, TradeTick
    from nautilus_trader.test_kit.providers import TestInstrumentProvider
    from nautilus_trader.trading.strategy import Strategy
    from nautilus_trader.backtest.models import LatencyModel

    VENUE = Venue("SIM"); inst = TestInstrumentProvider.equity(symbol="AAA", venue="SIM")
    BT = BarType.from_str(f"{inst.id}-1-DAY-LAST-EXTERNAL")

    class T(Strategy):
        def on_start(self):
            self.subscribe_bars(BT); self.n = 0
        def on_bar(self, bar):
            self.n += 1
            print(f"  [close] bar {self.n}: O={bar.open} C={bar.close}")
            if self.n == 3:
                print("  --> BUY submitted at CLOSE of bar 3 (price 104)")
                self.submit_order(self.order_factory.market(inst.id, OrderSide.BUY, Quantity.from_int(10)))
        def on_order_filled(self, e):
            print(f"  *** FILLED at {e.last_px}")
            FILLS.append(float(e.last_px))

    FILLS = []
    TARGET_PX = 150.00

    eng = BacktestEngine(config=BacktestEngineConfig(logging=LoggingConfig(bypass_logging=True)))
    eng.add_venue(VENUE, OmsType.NETTING, AccountType.CASH,
                  starting_balances=[Money(1_000_000, USD)], base_currency=USD,
                  latency_model=LatencyModel(base_latency_nanos=int(3600*1e9)))
    eng.add_instrument(inst)

    prices=[(100,101,99,100),(102,103,101,102),(104,105,103,104),(150,155,149,152),(160,161,159,160)]
    d0=pd.Timestamp("2020-01-01", tz="UTC"); data=[]
    for i,(o,h,l,c) in enumerate(prices):
        day = d0 + pd.Timedelta(days=i)
        t_open  = int((day + pd.Timedelta(hours=9,minutes=15)).value)   # opening print
        t_close = int((day + pd.Timedelta(hours=15,minutes=30)).value)  # daily bar stamped at close
        data.append(TradeTick(inst.id, Price.from_str(f"{o}.00"), Quantity.from_int(100),
                              AggressorSide.NO_AGGRESSOR, TradeId(f"O{i}"), t_open, t_open))
        data.append(Bar(BT, Price.from_str(f"{o}.00"), Price.from_str(f"{h}.00"),
                        Price.from_str(f"{l}.00"), Price.from_str(f"{c}.00"),
                        Quantity.from_int(1000), t_close, t_close))
    eng.add_data(sorted(data, key=lambda x: x.ts_init))
    eng.add_strategy(T(None))
    print(f"Target: fill at {TARGET_PX:.2f} = OPEN of day 4\n")
    eng.run()

    # THE VERDICT LINE AND THE EXIT STATUS, ADDED 2026-09-21. The engine, the venue,
    # the latency model, the five bars and the order are untouched; the only addition
    # is that the fill price the strategy already printed is now also collected and
    # compared against the target this file already declares one line above eng.run().
    #
    # THE TARGET IS NOT INVENTED HERE. It is this file's own stated purpose -- an
    # order signalled at the close of bar 3 must fill at the OPEN of day 4, 150.00,
    # not at 104.00 (same-bar fill, no latency model) and not at 152.00 (next close,
    # no opening tick). Those two wrong answers are named in the header as the
    # failures this configuration exists to rule out.
    #
    # THIS COVERS NO UNIVERSE AND NO ARM. It is a synthetic five-bar probe of
    # Nautilus execution semantics on invented prices, and a pass says the port's
    # execution assumption holds in the engine, not that any strategy is correct.
    print()
    if len(FILLS) != 1:
        print(f"  RESULT: FAIL -- expected exactly 1 fill, got {len(FILLS)}: {FILLS}")
        raise SystemExit(1)
    if abs(FILLS[0] - TARGET_PX) > 1e-9:
        print(f"  RESULT: FAIL -- filled at {FILLS[0]:.2f}, expected {TARGET_PX:.2f} "
              f"(the OPEN of day 4). A fill at 104.00 means the order filled inside "
              f"the bar that created it; 152.00 means it filled at the next CLOSE.")
        raise SystemExit(1)
    print(f"  RESULT: PASS -- synthetic 5-bar test with a latency model: one fill, at "
          f"{FILLS[0]:.2f}, the OPEN of day 4. Covers no universe and not the "
          f"production port's zero-latency configuration.")


def _cli_verify_next_open_execution():
    """`python checks.py verify_next_open_execution [ARGS]`: what running nautilus/verify_next_open_execution.py did."""
    _verify_next_open_execution_setup()


# ======================================================================================
# lookahead_proof. From tools/lookahead_proof.py (moved 2026-11-27).
# ======================================================================================
# lookahead_proof -- no decision on or before a cut date T depends on any input after T.
#
#     python checks.py lookahead_proof --universe nifty100 --mode static \
#         --arms v1,v2,v3,v4 --cut 2019-09-30,2022-12-30,2026-03-31
#     python checks.py lookahead_proof ... --control leak     # must FAIL
#     python checks.py lookahead_proof ... --control label    # must FAIL
#     python checks.py lookahead_proof ... --mode pit --control member   # must FAIL
#     python checks.py lookahead_proof ... --start 2007-09-24   # a non-default backtest start
#     python checks.py lookahead_proof recompare --work <an earlier work folder>
#
# WHAT IT RUNS. The decision path of a pipeline run, in-process, for one universe:
# build_panel, score_monthly with the production seeds, and backtest_exposure for
# each arm at the default cadence, profile and capital, tax off, from the backtest
# start --start (default 2019-01-01; the scoring floor follows it, settings.start_axis).
# It runs in these variants, each in its own process:
#
#     full    every input as delivered. Scores every month, as the pipeline does.
#     cut     every price row dated after T removed, and in pit mode every
#             membership row with an effective date after T.
#     noise   every open, high, low, close, adj_close and volume value dated after
#             T replaced by random positive numbers. Membership is unchanged.
#     names   pit only: cut, and also every symbol removed that is not a member on
#             any effective date on or before T and is not in the first list.
#
# The NSE index file is not an input to any decision (it is read only for the
# benchmark rows), so it is not loaded and has nothing to cut.
#
# WHAT IS COMPARED, bit for bit: every model score on every date on or before T,
# decision date or not; and for every decision date on or before T, per arm: the
# scores on that date; the ranked list, the 8 selected names, the 16
# kept and the target weights with the exposure (audit "orders", unrounded); the
# audit ranking and decision rows; and the drawdown-stop and drawdown-limit
# events dated on or before T, where the arm has them. The fills, holdings and
# daily valuations dated on or before T are compared too, as one check per arm.
#
# THREE THINGS THAT ARE NOT DATA AND ARE THE SAME IN EVERY VARIANT, stated:
#   1. The cut variant's backtest dates end at T plus the next calendar session
#      from data/nse_trading_calendar.csv, which carries no data. The engine makes
#      no order on the last date of its window, so without that session the cut
#      run would skip the decision on T for a reason that is not look-ahead.
#   2. The cut and noise variants score only the months whose first session is on
#      or before T (score_monthly's `through`). A month's model and scores do not
#      depend on later months.
#   3. The full variant's results are reused for every cut date of one invocation.
#
# NEGATIVE CONTROLS, --control, applied in every variant of the invocation:
#   leak    rev_1 is computed from the NEXT session's return, a 1-session leak.
#   label   the training rule before 2026-10-22: rows up to the cut with any
#           label, ranked once per date over every label. On data with no missing
#           sessions that rule leaks nothing, so this control also plants a gap:
#           for the first scorable symbol on the cut of T's month, its rows after
#           that cut up to T are removed, so its label there ends after T. The same
#           gap with --control gap and the current rule must PASS.
#   member  pit only: market_data.member_mask and portfolio.breadth_momentum
#           as before 2026-10-22, every row before the first effective date kept.
# The full variant of a control scores only through the last cut date.
#
# Writes only under --work (default: the system temp folder). Prints PASS or FAIL
# per decision date and the first difference of each failure. Exits 0 when every
# comparison passes, 1 otherwise.

PRICE_FIELDS = ("open", "high", "low", "close", "adj_close", "volume")
TABLES = ("holdings", "summary", "trades", "skipped")
CONTROLS = ("none", "leak", "label", "gap", "member")


# ---------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------
def universe(tag, mode):
    from settings import REGISTRY, pit_variant
    u = REGISTRY[tag]
    return pit_variant(u) if mode == "pit" else u


def source_dir(u, mode):
    return Path(u.survivorship_data_dir if mode == "pit" else u.raw_data_dir)


def stock_files(src, index_name):
    from settings import normalise_stem
    key = normalise_stem(index_name) if index_name else None
    return sorted(f for f in src.glob("*.csv")
                  if not f.name.startswith("._") and normalise_stem(f.stem) != key)


def _dates(lines, source):
    """The parsed date of each data line, as read_price_csv parses the column."""
    import pandas as pd
    import market_data
    import settings
    first = pd.Series([ln.split(",", 1)[0] for ln in lines])
    return market_data.smart_parse_dates(first, source=source)


def write_farm(u, mode, variant, T, dst, gap=None, drop=frozenset(), seed=0):
    """The variant's constituent folder. Kept lines are the source's own bytes."""
    import numpy as np
    dst.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    for f in stock_files(source_dir(u, mode), u.index_name):
        if f.stem in drop:
            continue
        g = gap if gap is not None and gap[0] == f.stem else None
        if variant == "full" and g is None:
            (dst / f.name).symlink_to(f)
            continue
        text = f.read_text().splitlines()
        head, rows = text[0], [ln for ln in text[1:] if ln.strip()]
        cols = head.split(",")
        d = _dates(rows, str(f))
        out = [head]
        for ln, dt in zip(rows, d):
            if g is not None and g[1] < dt <= g[2]:
                continue
            if variant in ("cut", "names") and dt > T:
                continue
            if variant == "noise" and dt > T:
                v = ln.split(",")
                if len(v) != len(cols):
                    raise SystemExit(f"{f.name}: a line has {len(v)} fields, the header "
                                     f"{len(cols)}; cannot rewrite it safely")
                base = float(rng.uniform(1.0, 5000.0))
                vals = {"open": base * rng.uniform(0.97, 1.03),
                        "high": base * rng.uniform(1.03, 1.08),
                        "low": base * rng.uniform(0.92, 0.97),
                        "close": base, "adj_close": base * rng.uniform(0.98, 1.0),
                        "volume": float(rng.integers(1, 10_000_000))}
                for k, x in vals.items():
                    if k in cols:
                        v[cols.index(k)] = repr(float(x))
                ln = ",".join(v)
            out.append(ln)
        # naming: axis-free -- a scratch copy of one constituent file under --work,
        # an input to one proof variant and never an artefact
        (dst / f.name).write_text("\n".join(out) + "\n")


def write_membership(u, T, dst):
    """The membership file with every row whose effective date is after T removed.
    Kept rows keep their delivered text, so they parse as the original does."""
    import pandas as pd
    import market_data
    import settings
    df = market_data.read_table(u.membership_file, dtype=str, keep_default_na=False)
    col = {c.lower().strip(): c for c in df.columns}["effective_date"]
    raw = df[col].astype(str)
    d = pd.to_datetime(raw, format="%Y-%m-%d", errors="coerce")
    d = d.fillna(pd.to_datetime(raw, dayfirst=True, errors="coerce"))
    # naming: axis-free -- a scratch copy of the membership file under --work
    df[(d <= T).to_numpy()].to_csv(dst, index=False)
    return dst


def late_names(u, T):
    """Pit symbols that are not a member on any effective date up to T and are not
    in the first list."""
    import market_data
    m = market_data.load(u.membership_file, index_name=u.index_name, allow_invalid=True)
    known = set(m.lists[0])
    for d, L in zip(m.dates, m.lists):
        if d <= T:
            known |= set(L)
    return {f.stem for f in stock_files(source_dir(u, "pit"), u.index_name)
            if f.stem.upper() not in known}


# ---------------------------------------------------------------------------
# controls
# ---------------------------------------------------------------------------
def apply_control(control):
    import numpy as np
    import pandas as pd
    import market_data
    import model
    import market_data
    if control == "leak":
        orig = market_data.add_stock_features

        def leaked(df):
            d = orig(df)
            c = d["close"]
            d["rev_1"] = -(c.shift(-1) / c - 1)
            return d
        market_data.add_stock_features = leaked
    elif control == "label":
        def old_training_set(p, cal, i_first, horizon=model.HORIZON, embargo=model.PURGE_EMBARGO):
            j = i_first - horizon - embargo
            if j < 0:
                return None
            if "_old_rank" not in p.columns:
                lab = p["scorable"] & p["fwd_ret"].notna()
                p["_old_rank"] = np.nan
                p.loc[lab, "_old_rank"] = p.loc[lab].groupby("date")["fwd_ret"].rank(pct=True)
            ok = (p["date"] <= pd.Timestamp(cal[j])) & p["_old_rank"].notna()
            return p.index[ok], p.loc[ok, "_old_rank"].to_numpy()
        model.training_set = old_training_set
    elif control == "member":
        import market_data
        import portfolio as te

        def old_mask(panel, membership, date_col="date", symbol_col="symbol"):
            if not market_data.is_pit() or membership is None or panel.empty:
                return np.ones(len(panel), dtype=bool)
            pos = membership._pos(panel[date_col])
            syms = panel[symbol_col].astype(str).str.upper().values
            return np.array([q < 0 or s in membership.lists[q] for q, s in zip(pos, syms)])

        def old_breadth(mom20, dt):
            m = mom20.loc[dt].dropna()
            M = market_data.MEMBERSHIP
            if market_data.is_pit() and M is not None:
                mem = M.members_on(dt)
                if mem:
                    m = m[[str(k).upper() in mem for k in m.index]]
            return m
        market_data.member_mask = old_mask
        te.breadth_momentum = old_breadth


def plant_gap(u, mode, T):
    """(symbol, after, through): the label control's gap for cut date T.

    The symbol is the first one, alphabetically, that is scorable and labelled on
    the cut of T's month, in the panel the run itself builds: in pit mode with
    the membership applied, so the symbol is a member there and its label would
    be used for training."""
    import io
    import contextlib
    import numpy as np
    import pandas as pd
    import market_data
    import model
    import market_data
    farm = Path(tempfile.mkdtemp(prefix="lookahead_gap_"))
    write_farm(u, mode, "full", T, farm)
    if mode == "pit":
        market_data.set_mode("pit")
        market_data.MEMBERSHIP = market_data.load(u.membership_file, index_name=u.index_name, allow_invalid=True)
    with contextlib.redirect_stdout(io.StringIO()):
        p = market_data.build_panel(model.HORIZON, data_dir=farm)
    market_data.set_mode("static")
    market_data.MEMBERSHIP = None
    cal = np.array(sorted(p["date"].unique()))
    first = p.loc[p["date"].dt.to_period("M") == pd.Timestamp(T).to_period("M"), "date"].min()
    i = int(np.searchsorted(cal, np.datetime64(first)))
    cut = pd.Timestamp(cal[i - model.HORIZON - model.PURGE_EMBARGO])
    sym = sorted(p.loc[(p["date"] == cut) & p["scorable"] & p["fwd_ret"].notna(), "symbol"])[0]
    return sym, cut, pd.Timestamp(T)


# ---------------------------------------------------------------------------
# one variant, in its own process
# ---------------------------------------------------------------------------
def run_variant(a):
    import io
    import contextlib
    import numpy as np
    import pandas as pd
    import market_data
    import model
    import market_data
    import market_data
    import costs
    import settings
    import portfolio as arm_reg
    from model import SEEDS
    from portfolio import backtest_exposure

    T = pd.Timestamp(a.T)
    from settings import start_axis
    start_axis.set_selection(a.start)
    u = universe(a.universe, a.mode)
    apply_control(a.control)
    work = Path(a.work)
    farm = work / "farm"
    gap = None
    if a.control in ("label", "gap"):
        gap = pickle.loads(Path(a.gap).read_bytes())
    drop = late_names(u, T) if a.variant == "names" else frozenset()
    write_farm(u, a.mode, a.variant, T, farm, gap=gap, drop=drop, seed=a.noise_seed)
    if a.mode == "pit":
        mfile = (u.membership_file if a.variant in ("full", "noise")
                 else write_membership(u, T, work / "membership.csv"))
        market_data.set_mode("pit")
        market_data.MEMBERSHIP = market_data.load(mfile, index_name=u.index_name, allow_invalid=True)
    cal = market_data._load_calendar()
    t0 = time.time()
    with contextlib.redirect_stdout(io.StringIO()):
        raw = market_data.build_panel(model.HORIZON, data_dir=farm)
    t_panel = time.time()
    through = None if (a.variant == "full" and a.through is None) else pd.Timestamp(a.through or T)
    with contextlib.redirect_stdout(io.StringIO()):
        p = model.score_monthly(raw[market_data.SCORE_INPUT_COLS], SEEDS, purge_mode=u.purge_mode,
                             through=through)
    t_score = time.time()
    market_data.TRADEABLE = market_data.sessions_with_row(farm, cal)
    market_data.TRADEABLE_TAG = u.tag
    px = p.pivot_table(index="date", columns="symbol", values="close").ffill()
    op = p.pivot_table(index="date", columns="symbol", values="open").ffill()
    # Reindexed to the price dates: a variant scored only through T has no score
    # row after it. For the full variant every price date has a score row already.
    sc = p.pivot_table(index="date", columns="symbol", values="score").reindex(px.index)
    bd = u.trading_days(px.index)
    if a.variant in ("cut", "names"):
        nxt = sorted(d for d in cal if d > T)[0]
        bd = bd.append(pd.DatetimeIndex([nxt]))
        px = px.reindex(px.index.union(bd)).ffill()
        op = op.reindex(op.index.union(bd)).ffill()
        sc = sc.reindex(sc.index.union(bd))
    pc = market_data.precompute(px)
    mom20 = px / px.shift(20) - 1
    out = {"scores": p.loc[p["score"].notna(), ["date", "symbol", "score"]].reset_index(drop=True),
           "arms": {}, "bd": bd,
           "seconds": {"panel": round(t_panel - t0, 1), "score": round(t_score - t_panel, 1)}}
    for name in a.arms.split(","):
        arm = arm_reg.ALL_ARMS[name]
        audit = {k: [] for k in ("holdings", "summary", "trades", "ranking", "decisions",
                                 "skipped")}
        with contextlib.redirect_stdout(io.StringIO()):
            eq, _tc, _n, _e = backtest_exposure(px, op, sc, bd, pc, mom20, audit=audit,
                                                tax_enabled=False, **arm.kwargs,
                                                **costs.cap_kwargs(u))
        audit.pop("tax", None)
        out["arms"][name] = {"audit": audit, "equity": eq}
    out["seconds"]["backtest"] = round(time.time() - t_score, 1)
    # naming: axis-free -- one variant's decisions, a scratch file under --work
    (work / "result.pkl").write_bytes(pickle.dumps(out))


# ---------------------------------------------------------------------------
# comparison
# ---------------------------------------------------------------------------
def same(x, y):
    """Exact equality: floats bit for bit (NaN equal to NaN), recursively."""
    import math
    import numpy as np
    if isinstance(x, float) or isinstance(y, float):
        if not (isinstance(x, (float, int, np.floating)) and isinstance(y, (float, int, np.floating))):
            return False
        if math.isnan(x) and math.isnan(y):
            return True
        return float(x) == float(y) and np.float64(x).tobytes() == np.float64(y).tobytes()
    if isinstance(x, dict) and isinstance(y, dict):
        return x.keys() == y.keys() and all(same(x[k], y[k]) for k in x)
    if isinstance(x, (list, tuple)) and isinstance(y, (list, tuple)):
        return len(x) == len(y) and all(same(a, b) for a, b in zip(x, y))
    return x == y


def first_diff(x, y, path=""):
    import math
    if isinstance(x, dict) and isinstance(y, dict):
        for k in sorted(set(x) | set(y), key=str):
            if k not in x or k not in y:
                return f"{path}.{k}: present in only one ({'full' if k in x else 'variant'})"
            d = first_diff(x[k], y[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(x, (list, tuple)) and isinstance(y, (list, tuple)):
        for i, (a, b) in enumerate(zip(x, y)):
            d = first_diff(a, b, f"{path}[{i}]")
            if d:
                return d
        return None if len(x) == len(y) else f"{path}: length {len(x)} vs {len(y)}"
    return None if same(x, y) else f"{path}: full {x!r} vs variant {y!r}"


def _on(rows, key, T):
    import pandas as pd
    return [r for r in rows if pd.Timestamp(r[key]) <= T]


def lookahead_proof_compare(full, var, T, label):
    """Lines of the report for one variant against full; returns (lines, failures)."""
    import numpy as np
    import pandas as pd
    L, fails = [], 0
    fs = full["scores"][full["scores"]["date"] <= T].set_index(["date", "symbol"])["score"]
    vs = var["scores"][var["scores"]["date"] <= T].set_index(["date", "symbol"])["score"]
    # EVERY SCORE ON OR BEFORE T, decision date or not. A leak that reaches only
    # the last sessions before T changes no decision when T is not a rebalance
    # date, and must still fail.
    why = None
    if list(fs.index) != list(vs.index):
        only = sorted(set(fs.index) ^ set(vs.index))[:3]
        why = (f"different (date, symbol) pairs scored, {len(set(fs.index) ^ set(vs.index))} "
               f"in all, e.g. {[(str(d.date()), s) for d, s in only]}")
    elif not np.array_equal(fs.to_numpy(), vs.to_numpy(), equal_nan=True):
        k = int(np.flatnonzero(fs.to_numpy() != vs.to_numpy())[0])
        d, sym = fs.index[k]
        why = f"score of {sym} on {d.date()}: full {fs.iloc[k]!r} vs variant {vs.iloc[k]!r}"
    fails += why is not None
    L.append(f"    {label:<6} all   every model score on every date to {T.date()} "
             f"({len(fs):,} scores)  " + ("PASS" if why is None else f"FAIL  first difference: {why}"))
    for name in full["arms"]:
        fa, va = full["arms"][name]["audit"], var["arms"][name]["audit"]
        f_orders = {pd.Timestamp(o["decided_on"]): o for o in _on(fa.get("orders", []), "decided_on", T)}
        v_orders = {pd.Timestamp(o["decided_on"]): o for o in _on(va.get("orders", []), "decided_on", T)}
        dates = sorted(set(f_orders) | set(v_orders)
                       | {pd.Timestamp(r["decided_on"]) for r in _on(fa["decisions"], "decided_on", T)})
        n_pass = 0
        for d in dates:
            why = None
            a = fs.xs(d, level="date") if d in fs.index.get_level_values(0) else pd.Series(dtype=float)
            b = vs.xs(d, level="date") if d in vs.index.get_level_values(0) else pd.Series(dtype=float)
            if list(a.index) != list(b.index):
                only = sorted(set(a.index) ^ set(b.index))[:5]
                why = f"scores: different scored names, e.g. {only}"
            elif not np.array_equal(a.to_numpy(), b.to_numpy(), equal_nan=True):
                k = int(np.flatnonzero(a.to_numpy() != b.to_numpy())[0])
                why = (f"score of {a.index[k]}: full {a.iloc[k]!r} vs variant {b.iloc[k]!r}")
            if why is None:
                why = first_diff(f_orders.get(d), v_orders.get(d), "order")
            for tab in ("ranking", "decisions"):
                if why is None:
                    why = first_diff([r for r in fa[tab] if pd.Timestamp(r["decided_on"]) == d],
                                     [r for r in va[tab] if pd.Timestamp(r["decided_on"]) == d], tab)
            if why is None:
                n_pass += 1
                L.append(f"    {label:<6} {name}  {d.date()}  PASS")
            else:
                fails += 1
                L.append(f"    {label:<6} {name}  {d.date()}  FAIL  first difference: {why}")
        for tab, key in (("stop_events", "date"), ("dd_events", "date")):
            if tab in fa or tab in va:
                why = first_diff(_on(fa.get(tab, []), key, T), _on(va.get(tab, []), key, T), tab)
                fails += why is not None
                L.append(f"    {label:<6} {name}  drawdown state ({tab}) to {T.date()}  "
                         + ("PASS" if why is None else f"FAIL  first difference: {why}"))
        why = None
        for tab in TABLES:
            key = "date"
            why = why or first_diff(_on(fa[tab], key, T), _on(va[tab], key, T), tab)
        fails += why is not None
        L.append(f"    {label:<6} {name}  fills, holdings and valuation to {T.date()}  "
                 + ("PASS" if why is None else f"FAIL  first difference: {why}"))
        L.append(f"    {label:<6} {name}  {n_pass} of {len(dates)} decision dates on or before "
                 f"{T.date()} identical")
    return L, fails


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------
def spawn(args, variant, T, work, through=None, gap=None):
    work.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(Path(__file__).resolve()), "lookahead_proof", "_variant",
           "--universe", args.universe, "--mode", args.mode, "--arms", args.arms,
           "--control", args.control, "--variant", variant, "--T", str(T.date()),
           "--work", str(work), "--noise-seed", str(args.noise_seed)]
    if args.start is not None:
        cmd += ["--start", args.start]
    if through is not None:
        cmd += ["--through", str(through.date())]
    if gap is not None:
        cmd += ["--gap", str(gap)]
    t0 = time.time()
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                       env=dict(os.environ, PYTHONHASHSEED="0"))
    if r.returncode != 0:
        raise SystemExit(f"variant {variant} at {T.date()} failed:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
    res = pickle.loads((work / "result.pkl").read_bytes())
    print(f"  ran {variant:<6} cut {T.date()}  panel {res['seconds']['panel']:.0f}s  "
          f"scores {res['seconds']['score']:.0f}s  backtests {res['seconds']['backtest']:.0f}s  "
          f"total {time.time() - t0:.0f}s", flush=True)
    return res


def recompare(base):
    """Compare the saved results of an earlier invocation again: `base` is its work
    folder (<universe>_<mode>_<control>_<time>). Nothing is recomputed."""
    import pandas as pd
    full = pickle.loads((base / "full" / "result.pkl").read_bytes())
    print(f"RECOMPARE  {base.name}  (saved results, nothing recomputed)")
    total = 0
    runs = sorted((d for d in base.iterdir() if d.is_dir() and d.name != "full"),
                  key=lambda d: (d.name.rsplit("_", 1)[1], d.name))
    for d in runs:
        v, T = d.name.rsplit("_", 1)
        T = pd.Timestamp(T)
        res = pickle.loads((d / "result.pkl").read_bytes())
        print(f"\n  CUT DATE {T.date()}  variant {v}")
        lines, fails = lookahead_proof_compare(full, res, T, v)
        print("\n".join(lines))
        total += fails
    print(f"\nRESULT: {'PASS' if total == 0 else f'FAIL ({total} comparison(s) differ)'}"
          f"  -- {base.name}")
    return 0 if total == 0 else 1


def lookahead_proof(argv=None):
    import pandas as pd
    ap = argparse.ArgumentParser(description="Prove no decision on or before T reads data after T.")
    ap.add_argument("cmd", nargs="?", default="prove", choices=("prove", "_variant", "recompare"))
    ap.add_argument("--universe")
    ap.add_argument("--mode", choices=("static", "pit"), default="static")
    ap.add_argument("--arms", default="v1,v2,v3,v4")
    ap.add_argument("--cut", help="comma-separated cut dates")
    ap.add_argument("--control", choices=CONTROLS, default="none")
    ap.add_argument("--work", default=str(Path(tempfile.gettempdir()) / "lookahead_proof"))
    ap.add_argument("--noise-seed", type=int, default=12345)
    ap.add_argument("--start", help="backtest start, YYYY-MM-DD (default 2019-01-01)")
    # _variant only
    ap.add_argument("--variant")
    ap.add_argument("--T")
    ap.add_argument("--through")
    ap.add_argument("--gap")
    a = ap.parse_args(argv)
    if a.cmd == "_variant":
        return run_variant(a)
    if a.cmd == "recompare":
        return recompare(Path(a.work))
    if not a.universe:
        ap.error("--universe is required")

    if a.control == "member" and a.mode != "pit":
        ap.error("--control member needs --mode pit")
    cuts = [pd.Timestamp(x) for x in a.cut.split(",")]
    from settings import start_axis
    start_axis.set_selection(a.start)
    variants = ["cut", "noise"] + (["names"] if a.mode == "pit" else [])
    base = Path(a.work) / f"{a.universe}_{a.mode}_{a.control}_{time.strftime('%Y%m%dT%H%M%S')}"
    print(f"LOOK-AHEAD PROOF  universe {a.universe}  mode {a.mode}  arms {a.arms}  "
          f"control {a.control}  cut dates {', '.join(str(c.date()) for c in cuts)}")
    print(f"  backtest start {start_axis.selected().date()}, scoring from "
          f"{start_axis.score_floor().date()}")
    print(f"  python {sys.version.split()[0]} at {sys.executable}; work folder {base}")
    total = 0
    if a.control in ("label", "gap"):
        if len(cuts) != 1:
            ap.error("--control label and gap take one cut date: the gap is planted for it")
    full_through = None if a.control == "none" else max(cuts)
    gapfile = None
    if a.control in ("label", "gap"):
        gap = plant_gap(universe(a.universe, a.mode), a.mode, cuts[0])
        base.mkdir(parents=True, exist_ok=True)
        gapfile = base / "gap.pkl"
        # naming: axis-free -- the planted gap for this invocation, under --work
        gapfile.write_bytes(pickle.dumps(gap))
        print(f"  planted gap: {gap[0]} has no rows after {gap[1].date()} up to {gap[2].date()}")
    full = spawn(a, "full", max(cuts), base / "full", through=full_through, gap=gapfile)
    for T in cuts:
        print(f"\n  CUT DATE {T.date()}")
        for v in variants:
            res = spawn(a, v, T, base / f"{v}_{T.date()}", gap=gapfile)
            lines, fails = lookahead_proof_compare(full, res, T, v)
            print("\n".join(lines))
            total += fails
    verdict = "PASS" if total == 0 else f"FAIL ({total} comparison(s) differ)"
    print(f"\nRESULT: {verdict}  -- universe {a.universe}, mode {a.mode}, control {a.control}")
    return 0 if total == 0 else 1


def _cli_lookahead_proof():
    """`python checks.py lookahead_proof [ARGS]`: what running tools/lookahead_proof.py did."""
    sys.exit(lookahead_proof())


# ======================================================================================
# test_dashboard. From dashboard/test_dashboard.py (moved 2026-11-27).
# ======================================================================================
# test_dashboard -- browser test for dashboard/dashboard.html.
#
# NEEDS GOOGLE CHROME (or Chromium). It starts Chrome headless and drives the page over
# the DevTools protocol, using only the Python standard library. Set CHROME to the
# browser executable if it is not in the default macOS location or on PATH.
#
#     python3 checks.py test_dashboard           system colour scheme
#     python3 checks.py test_dashboard --dark    forced dark mode
#
# Opens every view for several runs, clicks, hovers, presses keys, checks phone width,
# and reports console messages, exceptions and network requests. Exits 1 if any step
# fails or the page logs an error, 2 if no browser or no page is found.

def find_chrome():
    for c in (os.environ.get("CHROME"),
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chromium-browser")):
        if c and Path(c).exists():
            return c
    return None


CHROME = find_chrome()
PAGE_PATH = Path(__file__).resolve().parent / "dashboard" / "dashboard.html"
PAGE = PAGE_PATH.as_uri()
PORT = 9333
DARK = "--dark" in sys.argv


class WS:
    def __init__(self, url):
        host, rest = url[len("ws://"):].split("/", 1)
        h, p = host.split(":")
        self.s = socket.create_connection((h, int(p)))
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET /{rest} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
                        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                        f"Sec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.s.recv(4096)
        self.buf = buf.split(b"\r\n\r\n", 1)[1]
        self.id = 0
        self.events = []

    def _recv_exact(self, n):
        while len(self.buf) < n:
            chunk = self.s.recv(1 << 20)
            if not chunk:
                raise EOFError
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self):
        msg = b""
        while True:
            b1, b2 = self._recv_exact(2)
            n = b2 & 127
            if n == 126:
                n = struct.unpack(">H", self._recv_exact(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._recv_exact(8))[0]
            msg += self._recv_exact(n)
            if b1 & 0x80:
                return json.loads(msg)

    def send(self, method, **params):
        self.id += 1
        data = json.dumps({"id": self.id, "method": method, "params": params}).encode()
        hdr = bytes([0x81])
        n = len(data)
        if n < 126:
            hdr += bytes([0x80 | n])
        elif n < 65536:
            hdr += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            hdr += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        self.s.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
        want = self.id
        while True:
            m = self.recv()
            if m.get("id") == want:
                if "error" in m:
                    raise RuntimeError(m["error"])
                return m.get("result", {})
            self.events.append(m)


def js(ws, expr):
    r = ws.send("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
    if "exceptionDetails" in r:
        raise RuntimeError(r["exceptionDetails"].get("exception", {}).get("description", r["exceptionDetails"]))
    return r["result"].get("value")


def test_dashboard():
    if CHROME is None:
        print("test_dashboard: no Chrome or Chromium found; set CHROME to its executable.")
        sys.exit(2)
    if not PAGE_PATH.exists():
        print("test_dashboard: dashboard/dashboard.html not found; run `python dashboard.py build` first.")
        sys.exit(2)
    prof = tempfile.mkdtemp()
    args = [CHROME, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={prof}",
            f"--remote-debugging-port={PORT}", "--window-size=1280,900", "about:blank"]
    if DARK:
        args.insert(1, "--force-dark-mode")
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
                page = [t for t in tabs if t["type"] == "page"][0]
                break
            except Exception:
                time.sleep(0.1)
        ws = WS(page["webSocketDebuggerUrl"])
        ws.send("Runtime.enable"); ws.send("Log.enable"); ws.send("Page.enable")
        ws.send("Network.enable")
        ws.send("Page.navigate", url=PAGE)
        for _ in range(600):
            if js(ws, "document.readyState") == "complete" and js(ws, "typeof DATA !== 'undefined' && !!DATA"):
                break
            time.sleep(0.1)
        exec_script(ws)
    finally:
        proc.terminate()


def exec_script(ws):
    results = []

    def step(name, expr):
        try:
            v = js(ws, expr)
            results.append((name, "ok", v))
        except Exception as e:
            results.append((name, "ERROR", str(e)[:300]))

    runs = js(ws, """(() => {
      const pick = f => RUNS.find(f);
      const a = pick(r => r.axes.universe==='nifty200' && r.axes.arm==='v3' && r.axes.survivorship==='pit' && r.axes.profile==='tradeable' && r.axes.tax==='on' && r.axes.capital==='1000000' && r.axes.impact==='0' && r.axes.pcap==='1' && r.axes.fixed==='off');
      const b = pick(r => r.axes.universe==='midcap100' && r.axes.arm==='v3' && r.axes.profile==='research' && r.axes.tax==='off' && r.axes.survivorship==='static');
      const c = pick(r => r.axes.universe==='nifty200' && r.axes.arm==='v1' && r.axes.capital==='5000000' && r.axes.impact==='0.01' && r.axes.pcap==='0.1');
      const d = pick(r => r.axes.universe==='nifty50' && r.axes.arm==='v2' && r.axes.profile==='research' && r.axes.tax==='on');
      return [a,b,c,d].map(r => r && r.id);
    })()""")
    results.append(("chosen runs", "ok", runs))
    views = ["run", "grid", "compare", "ladder", "methods", "all", "notes"]
    for rid in runs:
        step(f"open {rid}", f"openRun(BYID.get({json.dumps(rid)})); state.cmp.includes({json.dumps(rid)}) || document.getElementById('addCmp').click(); document.querySelector('.tile .v').textContent")
        for v in views:
            step(f"  view {v}", f"""(() => {{ state.view={json.dumps(v)}; render();
                const svgs = MAIN.querySelectorAll('svg.chart').length;
                const rows = MAIN.querySelectorAll('tbody tr').length;
                return `svgs ${{svgs}}, table rows ${{rows}}, hash ${{location.hash.length}} chars`; }})()""")
        # Hover each chart in the run view and read the tooltip.
        step("  hover charts (run view)", """(() => { state.view='run'; render(); const out=[];
            MAIN.querySelectorAll('svg.chart').forEach(svg => { const r=svg.getBoundingClientRect();
              svg.scrollIntoView(); const r2=svg.getBoundingClientRect();
              const tgt = svg.querySelector('.hit') || svg;
              tgt.dispatchEvent(new MouseEvent('mousemove',{clientX:r2.left+r2.width*0.6, clientY:r2.top+r2.height*0.5, bubbles:true}));
              const t=document.getElementById('tip'); const tr=t.getBoundingClientRect();
              out.push(t.style.display + ' inside=' + (tr.left>=0 && tr.right<=document.documentElement.clientWidth && tr.top>=0 && tr.bottom<=innerHeight) + ' :: ' + t.innerText.replace(/\\n/g,' | ').slice(0,160));
              svg.dispatchEvent(new MouseEvent('mouseleave')); });
            return out; })()""")
        step("  keyboard on equity chart", """(() => { const svg=MAIN.querySelector('svg.chart'); svg.focus();
            ['End','ArrowLeft','ArrowLeft'].forEach(k => svg.dispatchEvent(new KeyboardEvent('keydown',{key:k,bubbles:true})));
            return document.activeElement===svg ? document.getElementById('tip').innerText.replace(/\\n/g,' | ') : 'not focused'; })()""")
        step("  checks table and rounding notes", """(() => { state.view='run'; render(); const t=[...MAIN.querySelectorAll('section.panel')].pop();
            return 'pass ' + t.querySelectorAll('td.pass').length + ', fail ' + t.querySelectorAll('td.fail').length + ', not run ' + t.querySelectorAll('td.muted').length
              + ' | ' + [...MAIN.querySelectorAll('.tile .s')].slice(0,2).map(x=>x.textContent).join(' / '); })()""")
        step("  linear scale", "(() => { MAIN.querySelector('[data-scale=linear]').click(); return state.scale + ' ' + MAIN.querySelectorAll('svg.chart').length; })()")
        step("  one-setting table opens a run", """(() => { const tr = [...MAIN.querySelectorAll('tr[data-open]')][0]; if (!tr) return 'no rows';
            const id = tr.dataset.open; tr.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true})); const ok = current() && current().id===id; history.back; return 'opened ' + id + ' ' + ok; })()""")
        step("  back to run", f"openRun(BYID.get({json.dumps(rid)})); current().id")
    # Return methods with and without a fixed-capital twin.
    step("methods: fixed-capital twin shown, no-data line gone", """(() => { const out=[];
        for (const fx of ['off','on']) {
          const r = RUNS.find(x => x.axes.universe==='nifty200' && x.axes.arm==='v3' && x.axes.survivorship==='pit' && x.axes.profile==='tradeable' && x.axes.tax==='on' && x.axes.capital==='1000000' && x.axes.impact==='0' && x.axes.pcap==='1' && x.axes.fixed===fx);
          if (!r) { out.push('fixed ' + fx + ': no run'); continue; }
          openRun(r); state.view='methods'; render();
          const h3 = [...MAIN.querySelectorAll('h3')].map(h=>h.textContent).join(' / ');
          const t = MAIN.querySelectorAll('table')[1];
          const rows = t ? [...t.querySelectorAll('tbody tr')].map(tr=>tr.innerText.replace(/\t/g,' ')) : [];
          const years = MAIN.querySelectorAll('table')[2] ? MAIN.querySelectorAll('table')[2].querySelectorAll('tbody tr').length : 0;
          out.push(`fixed ${fx}: ${h3} | ${rows.join(' ; ')} | year rows ${years} | no-data line ${MAIN.innerText.includes('is not in this data')} | sentences ${MAIN.querySelectorAll('ul')[1] ? MAIN.querySelectorAll('ul')[1].children.length : 0}`);
        }
        const nt = RUNS.find(x => !x.fixed_twin);
        openRun(nt); state.view='methods'; render();
        out.push('no twin (' + nt.id + '): no-data line ' + MAIN.innerText.includes('is not in this data') + ', fixed block ' + MAIN.querySelectorAll('h3').length);
        return out.join(' || '); })()""")
    step("bias label on a market-cap bucket run", """(() => { const r = RUNS.find(x => x.axes.universe==='mcapover10000' && x.axes.arm==='v1');
        if (!r) return 'no run';
        const out = [];
        for (const v of ['run', 'methods']) { openRun(r); state.view = v; render();
          const h = [...MAIN.querySelectorAll('section.panel h2')].map(x => x.textContent).find(t => t.startsWith('Bias'));
          out.push(v + ': ' + (h || 'no bias panel')); }
        state.view = 'notes'; render();
        out.push('notes: ' + ([...MAIN.querySelectorAll('h2')].map(x => x.textContent).find(t => t.startsWith('Universes with a bias')) || 'none'));
        const o = RUNS.find(x => x.axes.universe==='nifty200'); openRun(o); state.view='run'; render();
        out.push('nifty200 bias panel: ' + [...MAIN.querySelectorAll('section.panel h2')].some(x => x.textContent.startsWith('Bias')));
        return out.join(' || '); })()""")
    # Grid interactions.
    step("grid: rows capital, cols impact, metric minus_basket", """(() => { state.view='grid'; state.grow='capital'; state.gcol='impact'; state.gmetric='minus_basket'; render();
        const b = MAIN.querySelectorAll('td.cell button'); const empty = MAIN.querySelectorAll('td.cell:not(:has(button))').length;
        const t = b.length ? b[0].textContent : ''; if (b.length) b[0].click(); return `cells ${b.length}, empty ${empty}, first ${t}, opened ${state.view} ${current() && current().id}`; })()""")
    for met in ["cagr", "minus_index", "max_dd", "end_equity", "tax", "costs"]:
        step(f"grid metric {met}", f"(() => {{ state.view='grid'; state.grow='universe'; state.gcol='arm'; state.gmetric='{met}'; render(); return MAIN.querySelectorAll('td.cell button').length; }})()")
    # Compare.
    step("compare rupees", "(() => { state.view='compare'; state.cmode='rupees'; render(); return state.cmp.length + ' runs, legend: ' + MAIN.querySelector('.legend').innerText.replace(/\\n/g,' | '); })()")
    step("compare hover", """(() => { const svg=MAIN.querySelector('svg.chart'); const r=svg.getBoundingClientRect();
        svg.dispatchEvent(new MouseEvent('mousemove',{clientX:r.left+r.width*0.5, clientY:r.top+r.height*0.5})); return document.getElementById('tip').innerText.replace(/\\n/g,' | '); })()""")
    # Ladder.
    for cell in js(ws, "[...new Set(DATA.ladder.map(x => `${x.universe} ${x.arm}`))]"):
        for m in ["cagr_minus_basket", "cagr", "max_dd", "impact_cost"]:
            step(f"ladder {cell} {m}", f"""(() => {{ state.view='ladder'; state.lcell={json.dumps(cell)}; state.lmetric='{m}'; render();
                const svg=MAIN.querySelector('svg.chart'); const r=svg.getBoundingClientRect();
                svg.dispatchEvent(new MouseEvent('mousemove',{{clientX:r.left+r.width*0.3, clientY:r.top+r.height*0.5}}));
                return MAIN.querySelectorAll('svg path').length + ' lines; tip: ' + document.getElementById('tip').innerText.replace(/\\n/g,' | ').slice(0,200); }})()""")
    # All runs: sort and filter.
    step("all runs: sort by CAGR desc, filter", """(() => { state.view='all'; state.filter=''; render();
        MAIN.querySelector('[data-sort=cagr]').click(); MAIN.querySelector('[data-sort=cagr]').click();
        const top = MAIN.querySelector('tbody tr').innerText.replace(/\\t/g,' ');
        state.filter='nifty200 tradeable pit'; render(); const n = MAIN.querySelectorAll('tbody tr').length;
        MAIN.querySelector('tbody tr').click(); return `top by CAGR: ${top} | filtered rows ${n} | opened ${state.view}`; })()""")
    # Not-run combination.
    step("not-run combination", """(() => { state.view='run'; state.sel = Object.assign({}, RUNS[0].axes, {cadence:'20', universe:'nifty50', capital:'50000000', profile:'research'}); render();
        return MAIN.querySelector('h2:nth-of-type(1)') ? [...MAIN.querySelectorAll('section.panel h2')].map(h=>h.textContent).join(' / ') + ' :: ' + document.getElementById('cmdText').textContent : 'none'; })()""")
    step("dimmed chips present", "MAIN.querySelectorAll('.chip.dim').length + ' dimmed of ' + MAIN.querySelectorAll('.chip').length")
    # Hash round trip.
    step("hash reopen", """(() => { const h = location.hash; state.view='notes'; state.sel = {}; location.hash = ''; location.hash = h;
        return new Promise(res => setTimeout(() => res(state.view + ' ' + (current() ? current().id : 'no run')), 300)); })()""")
    # Bad file through the same validator.
    step("validator on a bad file", "validate({schema:'x', generated_at:1, repo:{}, data_end:'2026', command_template:'run', axes:[], runs:[{}], ladder:[], known_issues:[], export_checks:[]})")
    step("validator on the embedded file", "validate(DATA).length")
    step("narrow window: page wider than viewport?", "document.documentElement.scrollWidth + ' vs ' + document.documentElement.clientWidth")

    # Phone width: every view, page must not scroll sideways.
    ws.send("Emulation.setDeviceMetricsOverride", width=375, height=812, deviceScaleFactor=2, mobile=True)
    step("phone: views without sideways page scroll", """(() => { const out=[]; openRun(RUNS[0]);
        for (const v of ['run','grid','compare','ladder','methods','all','notes']) { state.view=v; render();
          out.push(v + ' ' + document.documentElement.scrollWidth + '/' + document.documentElement.clientWidth); }
        return out.join(', '); })()""")
    ws.send("Emulation.clearDeviceMetricsOverride")
    # Theme toggle and colours.
    step("theme cycle", """(() => { const b=document.getElementById('theme'); const out=[];
        for (let i=0;i<3;i++){ b.click(); out.push(b.textContent + ' bg=' + getComputedStyle(document.body).backgroundColor); } return out.join(' | '); })()""")
    # Fresh load from a hash.
    hash_url = js(ws, "(() => { openRun(BYID.get(" + json.dumps(runs[2]) + ")); state.view='methods'; render(); return location.href; })()")
    ws.send("Page.navigate", url="about:blank"); time.sleep(0.5)
    ws.send("Page.navigate", url=hash_url)
    for _ in range(600):
        try:
            if js(ws, "typeof DATA !== 'undefined' && !!DATA && document.readyState==='complete'"):
                break
        except Exception:
            pass
        time.sleep(0.1)
    step("fresh load from hash", "state.view + ' ' + (current() && current().id) + ' :: ' + MAIN.querySelector('tbody tr').innerText.replace(/\\t/g,' ')")

    # ---- steps for items 2 to 6 of the second fix round ----
    step("2 run view window + 4 two commands", """(() => { const r = RUNS.find(x => x.axes.universe==='microcap250' && x.axes.arm==='v1' && x.axes.survivorship==='static' && x.axes.profile==='research' && x.axes.tax==='off');
        openRun(r); const h2 = MAIN.querySelectorAll('section.panel h2')[0].textContent;
        const b = document.getElementById('cmdBatch').textContent, o = document.getElementById('cmdOne').textContent;
        return h2.slice(0,90) + ' || labels: ' + [...MAIN.querySelectorAll('.lab2')].map(x=>x.textContent).join(' / ') + ' || batch: ' + b + ' || only: ' + o + ' || copy buttons ' + MAIN.querySelectorAll('#copyBatch,#copyOne').length; })()""")
    step("4 copy button feedback", """(() => { const b=document.getElementById('copyOne'); b.click(); return new Promise(res => setTimeout(() => res(b.textContent), 50)); })()""")
    step("2 one-setting table marks different window", """(() => { const t = [...MAIN.querySelectorAll('section.panel')].find(s => s.querySelector('h2') && s.querySelector('h2').textContent.startsWith('The same run'));
        const marked = [...t.querySelectorAll('tr')].filter(tr => tr.querySelector('.diffwin')).map(tr => tr.cells[0].textContent + ' ' + tr.cells[1].textContent);
        return 'marked: ' + marked.join(', ') + ' || note: ' + t.querySelector('p.muted').textContent; })()""")
    step("2+5 grid: settings panel with spread axes, window marks", """(() => { state.view='grid'; state.grow='survivorship'; state.gcol='arm'; state.gmetric='cagr'; render();
        return 'spread notes: ' + [...MAIN.querySelectorAll('.spread')].map(x=>x.textContent).join(' / ') + ' || chips ' + MAIN.querySelectorAll('.chip').length
          + ' || marked cells ' + MAIN.querySelectorAll('td.cell .diffwin').length + ' of ' + MAIN.querySelectorAll('td.cell button').length
          + ' || note: ' + [...MAIN.querySelectorAll('p.muted')].map(p=>p.textContent).find(t=>t.includes('comparable')); })()""")
    step("5 grid chip changes the fixed settings", """(() => { const c = [...MAIN.querySelectorAll('.chip[data-axis=universe]')].find(b => b.dataset.v==='nifty200'); c.click();
        return state.view + ' universe=' + state.sel.universe + ' cells ' + MAIN.querySelectorAll('td.cell button').length; })()""")
    step("2 compare marks different window", """(() => { const a = RUNS.find(x => x.axes.universe==='microcap250' && x.axes.arm==='v1' && x.axes.survivorship==='pit' && x.axes.profile==='research' && x.axes.tax==='off');
        const b = RUNS.find(x => x.axes.universe==='microcap250' && x.axes.arm==='v1' && x.axes.survivorship==='static' && x.axes.profile==='research' && x.axes.tax==='off');
        state.cmp = [b.id, a.id]; openRun(b); state.view='compare'; render();
        return 'badges ' + MAIN.querySelectorAll('.diffwin').length + ' :: ' + [...MAIN.querySelectorAll('tbody tr')].map(tr => tr.cells[tr.cells.length-2].textContent).join(' | ') + ' || ' + [...MAIN.querySelectorAll('p.muted')][0].textContent; })()""")
    step("2 all runs start/end columns", """(() => { state.view='all'; state.filter='microcap250 pit'; render(); const hs=[...MAIN.querySelectorAll('th')].map(t=>t.textContent);
        const i = hs.findIndex(t=>t.startsWith('Start')); const starts = new Set([...MAIN.querySelectorAll('tbody tr')].map(tr=>tr.cells[i].textContent));
        state.filter=''; render(); const all = new Set([...MAIN.querySelectorAll('tbody tr')].map(tr=>tr.cells[i].textContent));
        return 'headers include Start/End: ' + hs.includes('Start') + '/' + hs.includes('End') + ' || microcap250 pit starts ' + [...starts] + ' || all starts ' + [...all]; })()""")
    step("3 ladder ramp, dashes, cap switch, edge label, note", """(() => { state.view='ladder'; state.lcell='nifty200 v3'; state.lmetric='cagr'; state.lcap='both'; render();
        const out=[]; const svg = () => MAIN.querySelector('svg.chart');
        const desc = () => { const ps=[...svg().querySelectorAll('path')]; const W=svg().viewBox.baseVal.width; const ts=[...svg().querySelectorAll('text')].filter(t=>t.getAttribute('y')>200);
          const last = ts[ts.length-1]; const bb = last.getBBox();
          return `${ps.length} lines (${ps.filter(p=>p.getAttribute('stroke-dasharray')).length} dashed), colours ${new Set(ps.map(p=>p.getAttribute('stroke'))).size}, last x label '${last.textContent}' ends at ${Math.round(bb.x+bb.width)} of ${W}`; };
        out.push('both: ' + desc());
        for (const c of ['1','0.1']) { MAIN.querySelector(`[data-lcap="${c}"]`).click(); out.push('cap ' + c + ': ' + desc()); }
        out.push('header: ' + MAIN.querySelectorAll('p.muted')[0].textContent.slice(0,60));
        out.push('note: ' + MAIN.querySelectorAll('p.muted')[1].textContent);
        return out.join(' || '); })()""")
    step("6 tooltip colours", """(() => { state.view='run'; openRun(RUNS[0]); const svg=MAIN.querySelector('svg.chart'); const r=svg.getBoundingClientRect();
        svg.dispatchEvent(new MouseEvent('mousemove',{clientX:r.left+r.width/2, clientY:r.top+r.height/2}));
        const t=getComputedStyle(document.getElementById('tip')); return 'theme ' + (isDark() ? 'dark' : 'light') + ': tip bg ' + t.backgroundColor + ', text ' + t.color + ', page bg ' + getComputedStyle(document.body).backgroundColor; })()""")
    step("6 notes: price data through, runs end", """(() => { state.view='notes'; render(); return [...MAIN.querySelectorAll('tr')].slice(1,3).map(tr=>tr.innerText.replace(/\\t/g,': ')).join(' || '); })()""")
    ws.send("Emulation.setDeviceMetricsOverride", width=375, height=812, deviceScaleFactor=2, mobile=True)
    step("6 phone: settings collapsed to a summary, opens on tap", """(() => { state.setOpen=false; state.view='run'; render(); const d=MAIN.querySelector('details.settings');
        const before = d.open + ' summary height ' + Math.round(d.querySelector('summary').getBoundingClientRect().height) + 'px: ' + d.querySelector('summary').textContent.slice(0,80);
        d.querySelector('summary').click();
        return new Promise(res => setTimeout(() => { const d2=MAIN.querySelector('details.settings'); res('closed=' + before + ' || after tap open=' + d2.open + ', chips visible ' + [...d2.querySelectorAll('.chip')].filter(c=>c.offsetParent).length + ', page ' + document.documentElement.scrollWidth + '/' + document.documentElement.clientWidth); }, 50)); })()""")
    step("6 phone: grid view summary", """(() => { state.setOpen=false; state.view='grid'; render(); const d=MAIN.querySelector('details.settings'); return 'open=' + d.open + ' :: ' + d.querySelector('summary').textContent.slice(0,120) + ' | page ' + document.documentElement.scrollWidth + '/' + document.documentElement.clientWidth; })()""")
    ws.send("Emulation.clearDeviceMetricsOverride")
    step("basket label on the run view", """(() => { state.view='run'; openRun(RUNS[0]); const t=[...MAIN.querySelectorAll('.tile')].find(x=>x.querySelector('.k').textContent==='Basket CAGR');
        return t.querySelector('.s').innerText.replace(/\\n/g,' | ') + ' || name in data: ' + RUNS[0].basket.name; })()""")
    # Network requests made by the page.
    reqs = [e["params"]["request"]["url"][:80] for e in ws.events if e.get("method") == "Network.requestWillBeSent"]
    cons = [(e["params"]["type"], " ".join(str(a.get("value", a.get("description", ""))) for a in e["params"]["args"])[:200])
            for e in ws.events if e.get("method") == "Runtime.consoleAPICalled"]
    excs = [e["params"]["exceptionDetails"].get("exception", {}).get("description", "")[:300]
            for e in ws.events if e.get("method") == "Runtime.exceptionThrown"]
    logs = [(e["params"]["entry"]["level"], e["params"]["entry"]["text"][:200]) for e in ws.events if e.get("method") == "Log.entryAdded"]
    for name, status, v in results:
        print(f"{status:5} {name}: {json.dumps(v)[:400] if not isinstance(v, str) else v[:400]}")
    print("network requests:", reqs)
    print("console calls:", cons)
    print("exceptions:", excs)
    print("log entries:", logs)
    failed = sum(1 for _, st, _ in results if st != "ok")
    errors = [c for c in cons if c[0] in ("error", "assert")] + excs + [l for l in logs if l[0] == "error"]
    print(f"RESULT: {len(results) - failed} of {len(results)} steps ok, "
          f"{len(errors)} console errors or exceptions")
    if failed or errors:
        sys.exit(1)


def _cli_test_dashboard():
    """`python checks.py test_dashboard [ARGS]`: what running dashboard/test_dashboard.py did."""
    test_dashboard()


# ======================================================================================
# costs_selftest. costs.py's worked charge examples (costs._selftest), which nothing
# ran before 2026-11-27. The function stays in costs.py: it tests that file's own
# private helpers.
# ======================================================================================
def _cli_costs_selftest():
    """`python checks.py costs_selftest`: run costs._selftest()."""
    import costs
    costs._selftest()


# ======================================================================================
# THE COMMAND LINE. `python checks.py TOOL [ARGS]` runs one tool as its own
# file used to run, with ARGS as its command line; with no TOOL it runs check_all.
# ======================================================================================
TOOLS = {
    "check_all": _cli_check_all,
    "check_data": _cli_check_data,
    "code_checks": _cli_code_checks,
    "engine_tests": _cli_engine_tests,
    "gate_compare": _cli_gate_compare,
    "naming_declare_check": _cli_naming_declare_check,
    "tax_acceptance_check": _cli_tax_acceptance_check,
    "test_survivorship": _cli_test_survivorship,
    "validate_engine": _cli_validate_engine,
    "validate_sizing": _cli_validate_sizing,
    "validate_topn": _cli_validate_topn,
    "validate_breadth_live": _cli_validate_breadth_live,
    "check_a_close_values": _cli_check_a_close_values,
    "check_b_exec_timing": _cli_check_b_exec_timing,
    "leakage_check1_causality": _cli_leakage_check1_causality,
    "leakage_check2_trading_purge": _cli_leakage_check2_trading_purge,
    "nt_attribution": _cli_nt_attribution,
    "nt_verify": _cli_nt_verify,
    "verify_v34_arms": _cli_verify_v34_arms,
    "verify_next_open_execution": _cli_verify_next_open_execution,
    "lookahead_proof": _cli_lookahead_proof,
    "test_dashboard": _cli_test_dashboard,
    "costs_selftest": _cli_costs_selftest,
}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in TOOLS:
        _tool = sys.argv.pop(1)
        sys.argv[0] = f"checks.py {_tool}"
        TOOLS[_tool]()
    else:
        _cli_check_all()
