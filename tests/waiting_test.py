# /llm_harness/tests/waiting_test.py
"""Waiting-list test for llm_harness: work refused because another session holds it is remembered, shown every turn, announced once when free, and keeps a session from ending quietly."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-waiting-")
RESULTS = []
STEP = [0]


def run(session, *lines):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0], "@SESSION " + session, "@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def edit(path, old, new):
    return ["@FILE " + path, "@HUNK TOP | e", "--- [OLD CODE] ---", old, "+++ [NEW CODE] +++", new, "=== [END HUNK] ==="]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-700:].replace("\n", "\n    "))


def main():
    for rel, text in (("a.txt", "alpha holds this line\n"), ("b.txt", "another held line\n")):
        with open(os.path.join(WS, rel), "w") as f:
            f.write(text)
    run("alpha | owns a and b", "@SCOPE hold | a.txt, b.txt")
    out = run("beta | needs a", *edit("/a.txt", "alpha holds this line", "beta changed this line"))
    check("a refused change is listed under WAITING ON", "=== WAITING ON" in out and "/a.txt held by alpha" in out, out)
    out = run("alpha | owns a and b", "@GREP holds")
    check("the holder is told who is blocked on its scope", "session beta is blocked by your scope on a.txt" in out, out)
    out = run("beta | needs a", "@SESSION_END")
    check("a session cannot end while it waits on blocked work", "[SESSION END REFUSED]" in out, out)
    out = run("gamma | needs b", "@SCOPE_REQUEST alpha | b.txt | to finish the conversion")
    check("a scope request is listed under WAITING ON too", "/b.txt held by alpha" in out, out)
    out = run("alpha | owns a and b", "@SCOPE_END")
    check("the release names the chats that were waiting on it", "[WAKE] session beta was waiting on /a.txt" in out and "[WAKE] session gamma was waiting on /b.txt" in out, out)
    out = run("beta | needs a", "@GREP holds")
    check("once the holder lets go, the waiting session hears [UNBLOCKED]", "[UNBLOCKED] /a.txt is free now" in out and "=== WAITING ON" not in out, out)
    out = run("beta | needs a", "@GREP holds")
    check("[UNBLOCKED] is said only once", "[UNBLOCKED]" not in out, out)
    out = run("beta | needs a", "@SCOPE edit a | a.txt", *edit("/a.txt", "alpha holds this line", "beta changed this line"))
    check("the resumed change now goes through", "beta changed this line" in open(os.path.join(WS, "a.txt")).read(), out)
    run("delta | wants a too", "@GREP holds")
    run("beta | needs a", "@SCOPE edit a | a.txt")
    out = run("delta | wants a too", "@SCOPE mine | a.txt")
    check("an overlapping scope claim is listed under WAITING ON", "[SCOPE REFUSED]" in out and "/a.txt held by beta" in out, out)
    out = run("delta | wants a too", "@SESSION_END drop")
    check("'@SESSION_END drop' gives the blocked work up and ends the session", "[SESSION END REFUSED]" not in out and "THIS SESSION: delta" not in out, out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
