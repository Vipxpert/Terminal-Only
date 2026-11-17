# /llm_harness/tests/tip_test.py
"""Line-edit tip test for llm_harness: a hunk that resends a long, mostly unchanged block gets a [TIP] that +++ [LINE EDITS] +++ would be shorter; line-edit hunks, short blocks and real rewrites get none."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-tip-")
RESULTS = []
STEP = [0]
BLOCK = ["value_%02d = %d" % (i, i) for i in range(12)]


def run(*lines):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0], "@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-700:].replace("\n", "\n    "))


def write(lines):
    with open(os.path.join(WS, "v.py"), "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    write(BLOCK)
    new = list(BLOCK)
    new[5] = "value_05 = 50"
    out = run("@FILE /v.py", "@HUNK TOP | one value", "--- [OLD CODE] ---", *BLOCK, "+++ [NEW CODE] +++", *new, "=== [END HUNK] ===")
    check("resending a long block to change one line gets the tip", "[OK] /v.py" in out and "[TIP] /v.py | one value: this hunk resent 11 unchanged lines to change 1" in out, out)
    write(BLOCK)
    out = run("@FILE /v.py", "@HUNK TOP | one value", "--- [OLD CODE] ---", *BLOCK, "+++ [LINE EDITS] +++", "6: value_05 = 50", "=== [END HUNK] ===")
    check("the same change with line edits gets no tip", "[OK] /v.py" in out and "[TIP]" not in out, out)
    write(BLOCK)
    out = run("@FILE /v.py", "@HUNK TOP | short", "--- [OLD CODE] ---", *BLOCK[:4], "+++ [NEW CODE] +++", *(BLOCK[:3] + ["value_03 = 30"]), "=== [END HUNK] ===")
    check("a short block gets no tip", "[OK] /v.py" in out and "[TIP]" not in out, out)
    write(BLOCK)
    out = run("@FILE /v.py", "@HUNK TOP | rewrite", "--- [OLD CODE] ---", *BLOCK, "+++ [NEW CODE] +++", *["other_%02d = %d" % (i, i) for i in range(12)], "=== [END HUNK] ===")
    check("a real rewrite gets no tip", "[OK] /v.py" in out and "[TIP]" not in out, out)
    write(BLOCK)
    out = run("@FILE /v.py", "@HUNK TOP | two values", "--- [OLD CODE] ---", *BLOCK, "+++ [LINE EDITS] +++", "3: value_02 = 20", "9: value_08 = 80", "=== [END HUNK] ===")
    check("line edits that change a couple of lines in a long block get no tip", "[OK] /v.py" in out and "[TIP]" not in out, out)
    write(BLOCK)
    out = run("@FILE /v.py", "@HUNK TOP | reindent", "--- [OLD CODE] ---", *BLOCK[:6], "+++ [LINE EDITS] +++", "2-", "3-", "4: value_03 = 300", "5: value_04 = 400", "6: value_05 = 500", "=== [END HUNK] ===")
    check("line edits that rewrite most of their block get the reverse tip", "[TIP] /v.py | reindent: these line edits change 5 of 6 lines; plain +++ [NEW CODE] +++ is clearer for rewrites" in out, out)
    with open(os.path.join(WS, "v.py")) as f:
        text = f.read()
    check("the tip never stops the edit", "[OK] /v.py" in out and "value_05 = 500" in text and "value_01 = 1" not in text, out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
