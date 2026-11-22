# /llm_harness/tests/text_remove_line_test.py
"""Line-removal test for llm_harness: a @TEXT_REPLACE whose replacement is empty removes the whole line when nothing is left on it (it used to leave a blank line behind), keeps the rest of a line when only part of it goes, removes every matching line when several are expected, and an ordinary replacement is unchanged."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []
COUNT = [0]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def put(ws, text):
    with open(os.path.join(ws, "notes.csv"), "w", newline="\n") as f:
        f.write(text)


def get(ws):
    with open(os.path.join(ws, "notes.csv"), "r", newline="") as f:
        return f.read()


def replace(ws, old, new, expect=1):
    COUNT[0] += 1
    lines = ["@SCRIPT [C: remove %d]" % COUNT[0], "@WORKSPACE " + ws, "@TEXT_REPLACE /notes.csv | expect %d | remove test" % expect, "--- [OLD TEXT] ---", old, "+++ [NEW TEXT] +++"] + ([new] if new else []) + ["=== [END TEXT] ==="]
    p = subprocess.run([sys.executable, HARNESS], input=("\n".join(lines) + "\n").encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "").split("=== L1 CONTRACT")[0]


def main():
    ws = tempfile.mkdtemp(prefix="harness-removeline-")
    put(ws, "alpha\nremove this whole line\nbeta\n")
    out = replace(ws, "remove this whole line", "")
    check("an empty replacement that empties a whole line removes it and leaves no blank line behind", get(ws) == "alpha\nbeta\n" and "removed" in out, (get(ws), out))
    put(ws, "keep this line and drop this part\nnext\n")
    replace(ws, " and drop this part", "")
    check("removing only part of a line keeps the rest of it", get(ws) == "keep this line\nnext\n", get(ws))
    put(ws, "one\ndup line here\ntwo\ndup line here\nthree\n")
    replace(ws, "dup line here", "", 2)
    check("every matching line goes when several are expected", get(ws) == "one\ntwo\nthree\n", get(ws))
    put(ws, "alpha\nchange this line\nbeta\n")
    replace(ws, "change this line", "changed that line")
    check("control: an ordinary replacement is unchanged", get(ws) == "alpha\nchanged that line\nbeta\n", get(ws))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
