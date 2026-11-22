# /llm_harness/tests/session_count_test.py
"""Session-count test for llm_harness: the footer shows a count and the names of the other sessions instead of a line each, @SESSIONS lists every session with its aim, and a lone session prints no OTHER SESSIONS line."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []
COUNT = [0]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def run(ws, session, *lines):
    COUNT[0] += 1
    text = "\n".join(["@SCRIPT [C: count %d]" % COUNT[0], "@WORKSPACE " + ws, "@SESSION %s | %s does its own work" % (session, session)] + list(lines)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "").split("=== L1 CONTRACT")[0]


def main():
    ws = tempfile.mkdtemp(prefix="harness-sesscount-")
    alone = run(ws, "alpha", "@LIST_DIR /")
    check("a lone session prints no OTHER SESSIONS line", "OTHER SESSIONS" not in alone, alone)
    for n in ("beta", "gamma", "delta"):
        run(ws, n, "@LIST_DIR /")
    out = run(ws, "alpha", "@LIST_DIR /")
    check("the footer counts the other sessions and names them, with no line each", "OTHER SESSIONS: 3" in out and "delta" in out and "gamma: aim:" not in out and "delta: aim:" not in out, out)
    full = run(ws, "alpha", "@SESSIONS")
    check("@SESSIONS lists every other session with its aim", all(("%s: aim: %s does its own work" % (n, n)) in full for n in ("beta", "gamma", "delta")), full)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
