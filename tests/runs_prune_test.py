# /llm_harness/tests/runs_prune_test.py
"""Run-history test for llm_harness: saved run outputs keep only the newest RUNS_KEEP numbered runs, a flood of @SIDE runs never pushes numbered runs out, and the side runs are bounded too."""
import importlib.util, os, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-700:].replace("\n", "\n    "))


def main():
    spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS)
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    ws = tempfile.mkdtemp(prefix="harness-runs-")
    err = hh.enter_workspace(ws)
    hh.RUNS_KEEP = 5
    for n in range(1, 8):
        hh.save_run({"side": False, "num": n, "id": "C-%d" % n}, "script %d" % n, "out")
    numbered = sorted(f for f in os.listdir(hh.runs_dir()) if f[:6].isdigit())
    check("only the newest RUNS_KEEP numbered runs are kept", not err and len(numbered) == 5 and numbered[0].startswith("000003"), (err, numbered))
    for i in range(12):
        hh.save_run({"side": True, "id": "S-%d" % i}, "side script %d" % i, "out")
    hh.save_run({"side": False, "num": 8, "id": "C-8"}, "script 8", "out")
    names = sorted(os.listdir(hh.runs_dir()))
    numbered = [f for f in names if f[:6].isdigit()]
    check("a flood of side runs never pushes the numbered runs out", len(numbered) == 5 and numbered[-1].startswith("000008"), names)
    side = [f for f in names if not f[:6].isdigit()]
    check("side runs are bounded too", len(side) <= 5, side)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
