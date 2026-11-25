# /llm_harness/tests/history_test.py
"""History test for llm_harness: @HISTORY <session> [| files] [| n] lists a session's recent journaled scripts (id, title, age, status), filters by session, supports '| files' and '| n', and reflects @UNDO status."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []
COUNT = [0]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def run(ws, session, title, *lines):
    COUNT[0] += 1
    text = "\n".join(["@SCRIPT [C: %s]" % title, "@WORKSPACE " + ws, "@SESSION %s | %s work" % (session, session)] + list(lines)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "").split("=== L1 CONTRACT")[0]


def main():
    ws = tempfile.mkdtemp(prefix="harness-history-")
    run(ws, "alpha", "create a", "@SCOPE a | a.txt", "@NEW_FILE /a.txt", "hello", "@END_NEW_FILE")
    run(ws, "beta", "create b", "@SCOPE b | b.txt", "@NEW_FILE /b.txt", "world", "@END_NEW_FILE")
    run(ws, "alpha", "create a2", "@SCOPE a | a.txt, a2.txt", "@NEW_FILE /a2.txt", "two", "@END_NEW_FILE")

    out = run(ws, "alpha", "check history", "@HISTORY alpha")
    check("@HISTORY lists alpha's scripts and not beta's", "=== HISTORY: alpha ===" in out and "create a2" in out and "create a" in out and "create b" not in out and "| applied" in out, out)

    out_files = run(ws, "alpha", "check history files", "@HISTORY alpha | files")
    check("@HISTORY | files lists changed paths", "files: a.txt" in out_files and "files: a2.txt" in out_files, out_files)

    out_n = run(ws, "alpha", "check history limit", "@HISTORY alpha | 1")
    check("@HISTORY | 1 caps output to the newest script", "create a2" in out_n and "create a |" not in out_n, out_n)

    out_none = run(ws, "alpha", "check history missing", "@HISTORY nobody")
    check("@HISTORY on unknown session reports no journaled scripts", "no journaled scripts for session 'nobody'" in out_none, out_none)

    run(ws, "alpha", "undo a2", "@UNDO 3")
    out_undone = run(ws, "alpha", "check history undone", "@HISTORY alpha")
    check("@HISTORY marks an undone script as undone", "create a2" in out_undone and "| undone" in out_undone, out_undone)

    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
