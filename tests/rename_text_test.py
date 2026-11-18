# /llm_harness/tests/rename_text_test.py
"""Rename test for llm_harness: a @TEXT_REPLACE or @HUNK on a file renamed earlier in the same script works on the first pass, and the rename rewrites the line-1 path header."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-renametext-")
RESULTS = []
STEP = [0]


def run(*lines):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0], "@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def read(rel):
    with open(os.path.join(WS, rel), encoding="utf-8") as f:
        return f.read()


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-800:].replace("\n", "\n    "))


def main():
    proj = os.path.basename(WS)
    os.makedirs(os.path.join(WS, "pkg"))
    with open(os.path.join(WS, "old.py"), "w") as f:
        f.write("# /%s/old.py\nanswer_value = 1\n" % proj)
    out = run("@RENAME /old.py -> /pkg/new.py",
              "@TEXT_REPLACE /pkg/new.py | expect 1 | after the rename",
              "--- [OLD TEXT] ---", "answer_value = 1", "+++ [NEW TEXT] +++", "answer_value = 2", "=== [END TEXT] ===")
    check("a text replacement on the renamed file works in the same script", "[OK" in out and "REFUSED" not in out and "answer_value = 2" in read("pkg/new.py") and not os.path.exists(os.path.join(WS, "old.py")), out)
    check("the rename rewrote the line-1 path header", read("pkg/new.py").startswith("# /%s/pkg/new.py" % proj), out)
    with open(os.path.join(WS, "two.py"), "w") as f:
        f.write("# /%s/two.py\nother_value = 1\n" % proj)
    out = run("@RENAME /two.py -> /pkg/three.py", "@FILE /pkg/three.py", "@HUNK TOP | header and value",
              "--- [OLD CODE] ---", "# /%s/pkg/three.py" % proj, "other_value = 1", "+++ [NEW CODE] +++", "# /%s/pkg/three.py" % proj, "other_value = 3", "=== [END HUNK] ===")
    check("a hunk that includes the new header matches after the rename", "[OK] /pkg/three.py" in out and "other_value = 3" in read("pkg/three.py"), out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
