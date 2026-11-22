# /llm_harness/tests/takeover_test.py
"""Takeover test for llm_harness: @TAKEOVER lets a chat absorb another chat's work only on the user's own answer at the terminal (Enter agrees, n declines, no terminal changes nothing), refuses an unknown session, itself, a side script and a chat without a session before asking anything, and the moved work arrives: the write scope and an unread message. The console is replaced by a fake, since a real prompt needs a terminal."""
import contextlib, importlib.util, io, os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []
COUNT = [0]
MSG = "a note for alpha that was never read"


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def run(ws, *lines):
    COUNT[0] += 1
    text = "\n".join(["@SCRIPT [C: takeover %d]" % COUNT[0], "@WORKSPACE " + ws] + list(lines)) + "\n"
    subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)


def main():
    spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS)
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    ws = tempfile.mkdtemp(prefix="harness-takeover-")
    with open(os.path.join(ws, "a.txt"), "w", newline="\n") as f:
        f.write("x\n")
    run(ws, "@SESSION alpha | alpha work", "@SCOPE alpha aim | a.txt")
    run(ws, "@SESSION beta | beta work")
    run(ws, "@SESSION gamma | gamma work", "@MESSAGE alpha | " + MSG)
    err = hh.enter_workspace(ws)
    asked, said = [], io.StringIO()

    def answer(value):
        def fake(prompt):
            asked.append(prompt)
            return value
        return fake

    def ask(P):
        asked.clear()
        said.truncate(0)
        said.seek(0)
        with contextlib.redirect_stdout(said):
            hh.takeover_directive(P)

    def reg():
        return hh.load_json(hh.sessions_path(), {})

    beta = {"takeover": "alpha", "session": "beta"}
    hh.ask_console = answer(None)
    ask(beta)
    check("with no terminal nothing changes", not err and "alpha" in reg() and "NOT DONE" in said.getvalue(), (err, said.getvalue()))
    hh.ask_console = answer("n")
    ask(beta)
    check("answering n leaves the other chat's work where it is, after one question", "alpha" in reg() and len(asked) == 1, said.getvalue())
    hh.ask_console = answer("")
    refused = []
    for P in ({"takeover": "nobody", "session": "beta"}, {"takeover": "beta", "session": "beta"}, {"takeover": "alpha", "session": "beta", "side": True}, {"takeover": "alpha"}):
        ask(P)
        refused.append("REFUSED" in said.getvalue() and not asked)
    check("an unknown session, itself, a side script and a chat without a session are refused before any question", all(refused) and "alpha" in reg(), refused)
    ask(beta)
    r = reg()
    paths = ((r.get("beta") or {}).get("scope") or {}).get("paths", [])
    check("Enter moves the work: the other session is gone and beta holds its write scope", "alpha" not in r and any("a.txt" in p for p in paths), (list(r), r.get("beta")))
    events = hh.load_json(hh.events_path(), {}).get("events", [])
    check("and the unread message for the other session is sent again to beta", any(e.get("to") == "beta" and MSG in e.get("text", "") for e in events), events[-3:])
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
