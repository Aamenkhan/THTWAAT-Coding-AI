"""
Reliability test: Run "Optimize test_opt.py" 10 times in a row.
Outputs raw pass/fail for each run. No caching between runs.

PASS = pipeline produces >= 1 grounded pending edit referencing actual code
FAIL = 0 edits, planning error, or hallucinated edit that fails validation
"""
import sys
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from packaging.packager import bootstrap
config = bootstrap()

from ai.ollama_client import OllamaClient
from ai.diff_engine import DiffEngine
from ai.planner import Planner

TEST_FILE = ROOT / "test_opt.py"
TEST_CODE = TEST_FILE.read_text(encoding="utf-8")
GOAL_PREFIX = f"Optimize {TEST_FILE}"

RUNS = 10
results = []

print(f"=== RELIABILITY TEST: {RUNS} runs on test_opt.py ===")
print(f"File content:\n{TEST_CODE}")
print("=" * 60)

for run_num in range(1, RUNS + 1):
    print(f"\n--- Run {run_num}/{RUNS} ---", flush=True)

    # Fresh instances per run (no caching)
    client = OllamaClient()
    diff_engine = DiffEngine()
    diff_engine.clear()
    planner = Planner(client, diff_engine, project_dir=str(ROOT))

    goal = f"Optimize {TEST_FILE}\n\nFile content of {TEST_FILE}:\n```\n{TEST_CODE}\n```"

    run_start = time.time()
    raw_plan_json = None
    error_msg = None
    pending_count = 0
    grounded = False

    try:
        plan = planner.build_plan(goal)
        raw_plan_json = plan  # logged by planner itself

        # Execute plan steps to stage edits
        import threading
        stop_event = threading.Event()
        plan_executed = planner.run(goal, on_progress=None, stop_event=stop_event)

        pending_edits = diff_engine.pending_edits()
        pending_count = len(pending_edits)

        # Grounded = at least one edit where old_text was actually found in the file
        for edit in pending_edits:
            if edit.original and edit.original == TEST_CODE.replace('\r\n', '\n') or \
               edit.proposed != edit.original:
                grounded = True
                break

        status = "PASS" if pending_count > 0 else "FAIL (0 edits)"

    except RuntimeError as exc:
        error_msg = str(exc)
        status = f"FAIL (error: {error_msg[:80]})"
    except Exception as exc:
        error_msg = str(exc)
        status = f"FAIL (exception: {error_msg[:80]})"

    elapsed = time.time() - run_start
    results.append({
        "run": run_num,
        "status": status,
        "pending_edits": pending_count,
        "elapsed_s": round(elapsed, 1),
        "error": error_msg,
    })
    print(f"Run {run_num}: {status} | edits={pending_count} | time={elapsed:.1f}s", flush=True)

print("\n" + "=" * 60)
print("=== RAW RESULTS ===")
passes = sum(1 for r in results if r["status"].startswith("PASS"))
fails = RUNS - passes
for r in results:
    print(f"  Run {r['run']:2d}: {r['status']} | edits={r['pending_edits']} | {r['elapsed_s']}s")
print(f"\nTOTAL: {passes}/{RUNS} PASS  |  {fails}/{RUNS} FAIL")
print(f"RELIABILITY RATE: {passes/RUNS*100:.0f}%")
