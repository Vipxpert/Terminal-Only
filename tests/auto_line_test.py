# /llm_harness/tests/auto_line_test.py
"""AUTO-line test for llm_harness: off by default the footer shows nothing new; with --auto on, a pure read ends with AUTO: CONTINUE, a change, @ASK_USER (with its line) and a script that did nothing end with AUTO: PAUSE, and the tenth read-only script in a row pauses."""
import os, re, subprocess, sys, tempfile

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
    text = "\n".join(["@SCRIPT [C: auto %d]" % COUNT[0], "@WORKSPACE " + ws, "@SESSION alpha | alpha work"] + list(lines)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def auto(out):
    m = re.findall(r"=== AUTO: [^\n]*", out)
    return m[-1] if m else ""


def main():
    ws = tempfile.mkdtemp(prefix="harness-auto-")
    out = run(ws, "@LIST_DIR /")
    check("switched off, the footer shows no AUTO line and no @ASK_USER", "=== AUTO:" not in out and "@ASK_USER" not in out, out[-600:])
    sw = subprocess.run([sys.executable, HARNESS, "--workspace", ws, "--auto", "on"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60).stdout.decode("utf-8", "replace")
    out = run(ws, "@LIST_DIR /")
    check("switched on, a pure read ends with AUTO: CONTINUE", "IS ON" in sw and auto(out) == "=== AUTO: CONTINUE ===", (sw, out[-400:]))
    out = run(ws, "@SCOPE a | a.txt", "@NEW_FILE /a.txt", "x", "@END_NEW_FILE")
    check("a change pauses", auto(out).startswith("=== AUTO: PAUSE (the script changed"), out[-500:])
    out = run(ws, "@LIST_DIR /", "@ASK_USER done with the sweep")
    check("@ASK_USER pauses and shows its line", "PAUSE (the AI asks for you: done with the sweep)" in auto(out), out[-500:])
    out = run(ws)
    check("a script that did nothing pauses", "PAUSE (the script did nothing)" in auto(out), out[-500:])
    outs = [auto(run(ws, "@LIST_DIR /")) for _ in range(10)]
    check("nine reads continue and the tenth pauses", all(o == "=== AUTO: CONTINUE ===" for o in outs[:9]) and "10 read-only scripts in a row" in outs[9], outs)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
