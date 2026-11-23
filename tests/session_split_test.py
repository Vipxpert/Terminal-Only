# /llm_harness/tests/session_split_test.py
"""Session-split test for llm_harness: @SPLIT sets up an UNCLAIMED session and hands it files the way @DELEGATE does, @NEW_SESSION sets one up with no files, both show as UNCLAIMED in the session list, the first chat that names one claims it and gets its brief and files, and a split whose files cannot move creates nothing."""
import importlib.util, os, subprocess, sys, tempfile

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
    text = "\n".join(["@SCRIPT [C: split %d]" % COUNT[0], "@WORKSPACE " + ws, "@SESSION %s | %s work" % (session, session)] + list(lines)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "").split("=== L1 CONTRACT")[0]


def main():
    ws = tempfile.mkdtemp(prefix="harness-split-")
    run(ws, "alpha", "@SCOPE alpha work | a.py, b.py", "@NEW_FILE /a.py", "x = 1", "@END_NEW_FILE", "@NEW_FILE /b.py", "y = 1", "@END_NEW_FILE")
    out = run(ws, "alpha", "@SPLIT beta | beta work | b.py | BRIEF-TEXT finish b.py")
    check("@SPLIT creates an unclaimed session and hands it the file", "[SESSION CREATED] beta (UNCLAIMED)" in out and "[DELEGATED] /b.py -> beta" in out, out)
    run(ws, "alpha", "@SPLIT gamma | gamma work |  | GAMMA-BRIEF")
    out = run(ws, "alpha", "@SESSIONS")
    check("both show as UNCLAIMED in the session list", out.count("UNCLAIMED, set up by alpha") >= 2 and "GAMMA-BRIEF" in out, out)
    out = run(ws, "beta", "@LIST_DIR /")
    check("the first chat that names it claims it and gets the brief, the files and the inherited task", "=== CLAIMED: this chat now holds session beta" in out and "BRIEF-TEXT" in out and "INHERITED" in out and "b.py" in out, out)
    out = run(ws, "alpha", "@SESSIONS")
    check("once claimed, beta is no longer unclaimed and gamma still is", "beta: UNCLAIMED" not in out and "gamma: UNCLAIMED" in out, out)
    out = run(ws, "alpha", "@SPLIT delta | delta work | c.py | x", "@SESSIONS")
    check("a split whose files cannot move creates nothing", "[SPLIT REFUSED]" in out and "delta:" not in out, out)
    hs = subprocess.run([sys.executable, HARNESS, "--workspace", ws], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120).stdout.decode("utf-8", "replace")
    check("the handshake lists the unclaimed session for a new chat", "=== UNCLAIMED SESSIONS" in hs and "gamma: gamma work" in hs and "GAMMA-BRIEF" in hs, hs[:1500])
    spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS)
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    hh.enter_workspace(ws)
    hh.merge_sessions("alpha", "beta")
    out = run(ws, "alpha", "@LIST_DIR /")
    check("a chat that comes back after its session was merged away is told where its work went", "=== MERGED: session alpha was taken over by beta" in out, out)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
