# /llm_harness/tests/probe_relative_test.py
"""Verify anchor-relative @PROBE slicing (+N, -N, A-B, N)."""
import os
import subprocess
import sys
import tempfile

HARNESS = os.path.abspath("harness.py")


def run_script(ws, body):
    script = "@SCRIPT [P: probe test]\n@SESSION test-rel | test relative probe\n@WORKSPACE %s\n%s\n" % (ws, body)
    p = subprocess.run([sys.executable, HARNESS], input=script, text=True, capture_output=True, encoding="utf-8")
    return p.stdout + p.stderr


def check(name, ok, out=""):
    if ok:
        print("PASS %s" % name)
    else:
        print("FAIL %s\n%s" % (name, out[-600:]))
        sys.exit(1)


def main():
    with tempfile.TemporaryDirectory() as ws:
        sample = os.path.join(ws, "sample.py")
        with open(sample, "w", encoding="utf-8") as f:
            f.write("# /ws/sample.py\ndef demo():\n" + "".join("    x_%d = %d\n" % (i, i) for i in range(1, 11)))
        out = run_script(
            ws,
            "\n".join([
                "@PROBE /sample.py | Scope | demo | +3",
                "@PROBE /sample.py | Scope | demo | -2",
                "@PROBE /sample.py | Scope | demo | 4-6",
                "@PROBE /sample.py | Scope | demo | 5",
            ]),
        )
        check("top-down +3 prints def demo and x_1..x_2", "Scope: demo (+3)" in out and "x_2 = 2" in out, out)
        check("bottom-up -2 prints x_9..x_10", "Scope: demo (-2)" in out and "x_9 = 9" in out and "x_10 = 10" in out, out)
        check("relative range 4-6 prints x_2..x_4", "Scope: demo (4-6)" in out and "x_2 = 2" in out and "x_4 = 4" in out, out)
        check("single relative line 5 prints x_3", "Scope: demo (5)" in out and "x_3 = 3" in out, out)


if __name__ == "__main__":
    main()
