# /llm_harness/tests/run_all.py
"""Runs every suite in this folder (the *_test.py files) one after another and prints one summary line per suite and a total.

Usage: python tests/run_all.py [path to harness.py]
Without an argument each suite tests the installed copy (~/.llm_harness/harness.py); with one, every suite tests that file, which is what the GitHub Actions workflow does. Exit code 0 only when every suite passed.
"""
import glob, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
KINDS = ("PASS", "FAIL", "SKIP")


def main():
    harness = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else None
    if harness and not os.path.isfile(harness):
        print("no such file: " + harness)
        return 2
    suites = sorted(glob.glob(os.path.join(HERE, "*_test.py")))
    total = dict.fromkeys(KINDS, 0)
    failed = []
    started = time.time()
    for path in suites:
        name = os.path.basename(path)[:-len("_test.py")]
        begun = time.time()
        try:
            p = subprocess.run([sys.executable, path] + ([harness] if harness else []), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
            out, code = p.stdout.decode("utf-8", "replace").replace("\r", ""), p.returncode
        except subprocess.TimeoutExpired:
            out, code = "timed out after 600 s\n", 1
        counts = dict((k, len(re.findall(r"(?m)^%s " % k, out))) for k in KINDS)
        for k in KINDS:
            total[k] += counts[k]
        bad = code != 0 or counts["FAIL"] > 0 or (counts["PASS"] == 0 and counts["SKIP"] == 0)
        print("%s %-16s PASS %-3d FAIL %-3d SKIP %-3d (%.1fs)" % ("FAIL" if bad else "ok  ", name, counts["PASS"], counts["FAIL"], counts["SKIP"], time.time() - begun))
        sys.stdout.flush()
        if bad:
            failed.append(name)
            print("    " + out.rstrip().replace("\n", "\n    "))
    print("")
    print("%d suite(s), %d check(s) passed, %d failed, %d skipped, %.0fs" % (len(suites), total["PASS"], total["FAIL"], total["SKIP"], time.time() - started))
    if failed:
        print("FAILED: " + ", ".join(failed))
        return 1
    print("ALL SUITES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
