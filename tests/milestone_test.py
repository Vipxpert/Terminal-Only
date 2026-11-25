# /llm_harness/tests/milestone_test.py
"""Milestone test for llm_harness: only a session that borrows work may record @MILESTONE, the owner's footer shows what was recorded (while the work is lent and after it returned), only the borrower is told about the command, the log keeps the last 20, and the handshake shows the harness states line."""
import contextlib, importlib.util, io, os, subprocess, sys, tempfile

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
    text = "\n".join(["@SCRIPT [C: milestone %d]" % COUNT[0], "@WORKSPACE " + ws, "@SESSION %s | %s work" % (session, session)] + list(lines)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def main():
    spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS)
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    ws = tempfile.mkdtemp(prefix="harness-milestone-")
    with open(os.path.join(ws, "a.txt"), "w", newline="\n") as f:
        f.write("x\n")
    run(ws, "owner", "@SCOPE owner aim | a.txt")
    run(ws, "relief", "@LIST_DIR /")
    run(ws, "third", "@LIST_DIR /")
    out = run(ws, "third", "@MILESTONE nothing is borrowed here")
    check("a session that borrows nothing is refused", "[MILESTONE REFUSED] this session borrows no work" in out, out)
    hh.enter_workspace(ws)
    hh.ask_console = lambda prompt: ""
    with contextlib.redirect_stdout(io.StringIO()):
        hh.borrow_directive({"borrow": "owner", "session": "relief"})
    out = run(ws, "relief", "@MILESTONE finished the API part")
    check("a borrower records a milestone on the owner", "[MILESTONE] recorded on owner's session" in out, out)
    own, third, rel = run(ws, "owner", "@LIST_DIR /"), run(ws, "third", "@LIST_DIR /"), run(ws, "relief", "@LIST_DIR /")
    check("the owner's footer shows the lent work and the milestone", "=== LENT" in own and "=== MILESTONES" in own and "finished the API part" in own, own[-1500:])
    check("only the borrower is told about @MILESTONE", "record it with @MILESTONE" in rel and "@MILESTONE" not in own and "@MILESTONE" not in third, (rel[-800:], own[-400:]))
    run(ws, "relief", "@RETURN owner | finished part one")
    own2, rel2 = run(ws, "owner", "@LIST_DIR /"), run(ws, "relief", "@LIST_DIR /")
    check("after the return the owner still sees the milestone and the borrower is no longer told", "finished the API part" in own2 and "=== LENT" not in own2 and "=== BORROWING" not in rel2 and "@MILESTONE" not in rel2, (own2[-800:], rel2[-400:]))
    with contextlib.redirect_stdout(io.StringIO()):
        hh.borrow_directive({"borrow": "owner", "session": "relief"})
        for i in range(25):
            hh.milestone_directive({"session": "relief", "milestone": "step %d" % i})
    log = hh.load_json(hh.sessions_path(), {})["owner"]["milestones"]
    check("the log keeps the last 20", len(log) == 20 and log[-1]["text"] == "step 24", [m["text"] for m in log])
    hs = subprocess.run([sys.executable, HARNESS, "--workspace", ws], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120).stdout.decode("utf-8", "replace")
    check("the handshake shows the states line, without naming the hidden AUTO line", "=== HARNESS STATES" in hs and "stewardship" in hs and "auto-copy" in hs and "AUTO status line" not in hs, hs[:1500])
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
