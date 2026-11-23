# /llm_harness/tests/unclaim_test.py
"""Unclaim test for llm_harness: @UNCLAIM without a brief is refused; with one, the chat's own session becomes UNCLAIMED in that same run without being claimed back, the handshake lists it, and the next chat that names it claims it with its brief, its files and its own to-do note."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []
COUNT = [0]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-1200:].replace("\n", "\n    "))


def run(ws, session, *lines):
    COUNT[0] += 1
    text = "\n".join(["@SCRIPT [C: unclaim %d]" % COUNT[0], "@WORKSPACE " + ws, "@SESSION %s | %s work" % (session, session)] + list(lines)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "").split("=== L1 CONTRACT")[0]


def main():
    ws = tempfile.mkdtemp(prefix="harness-unclaim-")
    with open(os.path.join(ws, "a.txt"), "w", newline="\n") as f:
        f.write("x\n")
    run(ws, "alpha", "@SCOPE alpha aim | a.txt", "@NOTE_ADD own | Todo: ALPHA-TODO")
    out = run(ws, "alpha", "@UNCLAIM")
    check("@UNCLAIM without a brief is refused", "[UNCLAIM REFUSED]" in out, out)
    out = run(ws, "alpha", "@UNCLAIM BRIEF-NEXT finish a.txt")
    check("@UNCLAIM hands the session on and does not claim it back in the same run", "[UNCLAIMED] session alpha" in out and "=== CLAIMED" not in out, out)
    hs = subprocess.run([sys.executable, HARNESS, "--workspace", ws], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120).stdout.decode("utf-8", "replace")
    check("the handshake lists it for the next chat", "=== UNCLAIMED SESSIONS" in hs and "BRIEF-NEXT" in hs, hs[:1500])
    out = run(ws, "alpha", "@LIST_DIR /")
    check("the next chat that names it claims it and gets the brief, the files and the own to-do", "=== CLAIMED: this chat now holds session alpha" in out and "BRIEF-NEXT" in out and "ALPHA-TODO" in out and "a.txt" in out, out)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
