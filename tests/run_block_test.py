# /llm_harness/tests/run_block_test.py
"""Tests for Phase 3 Gemini friction fixes: @RUN gate on failed @FILE, @RUN_ALWAYS, multi-line @RUN_BLOCK ... @END_RUN_BLOCK, and Python Class.method + <top> scope resolution."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []
COUNT = [0]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def run(ws, *lines):
    COUNT[0] += 1
    text = "\n".join(["@SCRIPT [CR: p3 %d]" % COUNT[0], "@WORKSPACE " + ws, "@SESSION alpha | p3 test"] + list(lines)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "").split("=== L1 CONTRACT")[0]


def main():
    ws = tempfile.mkdtemp(prefix="harness-p3-")
    with open(os.path.join(ws, "app.py"), "w", encoding="utf-8") as f:
        f.write("class LockScreenApp:\n    async def _draw_sine(self):\n        return 1\n\nX = 1\n")

    out = run(ws, "@SCOPE p3 | app.py", "@FILE /app.py", "@HUNK LockScreenApp._draw_sine | edit method",
              "--- [OLD CODE] ---", "        return 1", "+++ [NEW CODE] +++", "        return 2", "=== [END HUNK] ===",
              "@HUNK <top> | edit top-level tail",
              "--- [OLD CODE] ---", "X = 1", "+++ [NEW CODE] +++", "X = 2", "=== [END HUNK] ===")
    check("Class.method and <top> scopes resolve cleanly without warnings", "[OK] /app.py | Scope: LockScreenApp._draw_sine" in out and "[OK] /app.py | Scope: <top>" in out and "outside the named scope" not in out and "not found" not in out, out)

    out_blk = run(ws, "@RUN_BLOCK", "python -c \"print('line1')\"", "python -c \"print('line2')\"", "@END_RUN_BLOCK")
    check("@RUN_BLOCK executes multi-line commands", "line1" in out_blk and "line2" in out_blk and "[exit 0" in out_blk, out_blk)

    out_gate = run(ws, "@FILE /app.py", "@HUNK <top> | bad hunk",
                   "--- [OLD CODE] ---", "NONEXISTENT_LINE", "+++ [NEW CODE] +++", "Y = 3", "=== [END HUNK] ===",
                   "@RUN python -c \"print('SHOULD_' + 'SKIP')\"",
                   "@RUN_ALWAYS python -c \"print('ALWAYS_RAN')\"")
    check("@RUN is skipped when earlier @FILE fails, while @RUN_ALWAYS still runs", "[SKIPPED] earlier @GIT_COMMIT or @FILE failed" in out_gate and "SHOULD_SKIP" not in out_gate and "ALWAYS_RAN" in out_gate, out_gate)

    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
