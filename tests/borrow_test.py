# /llm_harness/tests/borrow_test.py
"""Borrow test for llm_harness: @BORROW lends a session's work to another chat only on the user's answer at the terminal (no terminal, no change), the owner is marked LENT and cannot change the lent files, the borrower stays the author of its changes, borrowing work that is already lent moves the loan (the owner stays the owner, the earlier holder keeps its own files and is told), @RETURN puts the files back in the owner's scope with the result, and @RECLAIM with n only asks while Enter takes the work back. The console is replaced by a fake, since a real prompt needs a terminal."""
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
    text = "\n".join(["@SCRIPT [C: borrow %d]" % COUNT[0], "@WORKSPACE " + ws, "@SESSION %s | %s work" % (session, session)] + list(lines)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "").split("=== L1 CONTRACT")[0]


def replace(ws, session, new):
    return run(ws, session, "@TEXT_REPLACE /a.txt | expect 1 | edit a", "--- [OLD TEXT] ---", "line one of alpha", "+++ [NEW TEXT] +++", new, "=== [END TEXT] ===")


def main():
    spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS)
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    ws = tempfile.mkdtemp(prefix="harness-borrow-")
    for n, t in (("a.txt", "line one of alpha"), ("b.txt", "line one of bravo"), ("c.txt", "line one of charlie")):
        with open(os.path.join(ws, n), "w", newline="\n") as f:
            f.write(t + "\n")
    run(ws, "owner", "@SCOPE owner aim | a.txt, b.txt")
    run(ws, "relief", "@SCOPE relief aim | c.txt")
    run(ws, "third", "@LIST_DIR /")
    hh.enter_workspace(ws)
    asked = []

    def act(P, value):
        def fake(prompt):
            asked.append(prompt)
            return value
        hh.ask_console = fake
        asked.clear()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            hh.borrow_directive(P)
        return buf.getvalue()

    def reg():
        return hh.load_json(hh.sessions_path(), {})

    def paths(n):
        return ((reg().get(n) or {}).get("scope") or {}).get("paths", [])

    def text():
        return open(os.path.join(ws, "a.txt")).read()

    out = act({"borrow": "owner", "session": "relief"}, None)
    check("with no terminal nothing is lent", "NOT DONE" in out and "a.txt" in paths("owner"), out)
    out = act({"borrow": "owner", "session": "relief"}, "")
    r = reg()
    check("Enter lends the owner's work: relief holds it beside its own file, and the owner is marked LENT", set(paths("relief")) >= {"a.txt", "b.txt", "c.txt"} and not paths("owner") and (r["owner"].get("lent") or {}).get("to") == "relief" and len(asked) == 1, (out, r))
    out = replace(ws, "owner", "owner was here")
    check("the owner sees LENT and cannot change the lent file", "=== LENT" in out and "owner was here" not in text(), out)
    out = replace(ws, "relief", "relief was here")
    check("the borrower changes it and stays the author in the history", "relief was here" in text() and hh.loan_scripts("relief", ["a.txt"]), out)
    out = act({"borrow": "owner", "session": "third"}, "")
    r = reg()
    check("a second borrower takes over the loan: the owner stays the owner, relief keeps only its own file", "a.txt" in paths("third") and paths("relief") == ["c.txt"] and r["owner"]["lent"]["to"] == "third" and "relief" in r["owner"]["lent"].get("holders", []), (out, r))
    out = run(ws, "relief", "@LIST_DIR /")
    check("the earlier holder is told the loan moved", "moved the loan" in out, out)
    out = run(ws, "third", "@RETURN owner | finished part one")
    r = reg()
    check("@RETURN puts the files straight back into the owner's scope", set(paths("owner")) >= {"a.txt", "b.txt"} and not r["owner"].get("lent") and not r["third"].get("borrowed"), (out, r))
    out = run(ws, "owner", "@LIST_DIR /")
    check("the owner hears the result", "finished part one" in out, out)
    act({"borrow": "owner", "session": "relief"}, "")
    out1 = act({"reclaim": True, "session": "owner"}, "n")
    still = (reg()["owner"].get("lent") or {}).get("to")
    out2 = act({"reclaim": True, "session": "owner"}, "")
    check("@RECLAIM: n only asks, Enter takes the work back at once", still == "relief" and set(paths("owner")) >= {"a.txt", "b.txt"} and not reg()["owner"].get("lent") and paths("relief") == ["c.txt"], (out1, out2, reg()))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
