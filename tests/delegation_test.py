# /llm_harness/tests/delegation_test.py
"""Delegation test for llm_harness: @DELEGATE moves files and a task from one chat to another at once (no acceptance step), the receiving chat's footer says INHERITED, @RETURN releases the files and sends the result back, a chat cannot end while it still holds delegated work, and delegating one of the files breaks a deadlock."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-delegation-")
RESULTS = []
STEP = [0]


def run(session, *lines, **kw):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0], "@SESSION %s | try delegation" % session, "@WORKSPACE " + (kw.get("ws") or WS)]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    # Comment (constraint): the standing rules printed at the end of every run contain the words REFUSED and WAITING ON, so a check must look only at the part before them
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def edit(path, old="one", new="two"):
    return ["@FILE /" + path, "@HUNK TOP | edit", "--- [OLD CODE] ---", old, "+++ [NEW CODE] +++", new, "=== [END HUNK] ==="]


def read(path):
    with open(os.path.join(WS, path)) as f:
        return f.read()


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-900:].replace("\n", "\n    "))


def main():
    os.makedirs(os.path.join(WS, "src"))
    for n in ("routes.py", "api.py", "a.txt", "b.txt", "src/x.py", "c.txt", "d.txt"):
        with open(os.path.join(WS, n), "w") as f:
            f.write("one\n")
    run("alpha", "@SCOPE routes | routes.py")
    run("beta", "@SCOPE api | api.py")
    out = run("alpha", "@DELEGATE beta | /routes.py | finish the part of the routes that needs api.py")
    check("delegating moves the file at once", "[DELEGATED] /routes.py -> beta" in out and "=== DELEGATED" in out, out)
    out = run("alpha", *edit("routes.py"))
    check("the delegating chat can no longer change the file", "REFUSED" in out and "two" not in read("routes.py"), out)
    out = run("beta")
    check("the receiving chat is told, and its footer says INHERITED", "delegation from alpha" in out and "=== INHERITED" in out and "finish the part of the routes" in out, out)
    out = run("beta", *edit("routes.py"))
    check("the receiving chat can change the file with no acceptance step", "two" in read("routes.py") and "REFUSED" not in out, out)
    out = run("beta", "@RETURN alpha | routes now call api.py")
    check("returning releases the files", "[RETURNED] /routes.py -> alpha" in out and "=== INHERITED" not in out, out)
    out = run("beta", *edit("routes.py", "two", "three"))
    check("the returning chat no longer holds them", "REFUSED" in out and "three" not in read("routes.py"), out)
    out = run("alpha")
    check("the delegating chat hears the result and has nothing delegated", "delegation returned from beta" in out and "routes now call api.py" in out and "=== DELEGATED" not in out, out)
    out = run("alpha", "@SCOPE routes again | routes.py", *edit("routes.py", "two", "four"))
    check("and claims the files again to continue", "four" in read("routes.py"), out)
    run("gamma", "@SCOPE src | src")
    out = run("gamma", "@DELEGATE beta | /src/x.py | touch it")
    check("a path that is only part of a wider scope entry is refused with the way to narrow it", "[DELEGATE REFUSED]" in out and "narrow your scope" in out, out)
    out = run("gamma", "@DELEGATE beta | /api.py | touch it")
    check("a file the chat does not hold is refused", "[DELEGATE REFUSED]" in out and "do not hold" in out, out)
    out = run("gamma", "@DELEGATE nobody | /src | touch it")
    check("an unknown chat is refused", "[DELEGATE REFUSED]" in out and "no other session" in out, out)
    run("gamma", "@DELEGATE beta | src | do the src part")
    out = run("beta", "@SCOPE_END")
    check("a chat holding delegated work cannot release or end until it returns or drops it", "[RELEASE REFUSED]" in out and "delegated to it" in out, out)
    out = run("beta", "@SESSION_END drop")
    check("ending with 'drop' gives it back unfinished", "session ended" in out or "ended" in out, out)
    out = run("gamma")
    check("and the delegating chat is told", "delegation dropped from beta" in out and "=== DELEGATED" not in out, out)
    run("p", "@SCOPE a | a.txt")
    run("q", "@SCOPE b | b.txt")
    run("p", *edit("b.txt"))
    out = run("q", *edit("a.txt"))
    check("two chats stuck on each other get DEADLOCK", "=== DEADLOCK (" in out and "@DELEGATE" in out, out)
    out = run("p", "@DELEGATE q | a.txt | take a.txt, you need it")
    out = run("q")
    check("delegating one of the files ends the deadlock and clears the wait", "=== DEADLOCK (" not in out and "WAITING ON" not in out and "=== INHERITED" in out, out)
    g = os.path.join(WS, "g")
    os.makedirs(g)
    for n in ("routes.py", "api.py"):
        with open(os.path.join(g, n), "w") as f:
            f.write("one\n")
    run("alpha", "@GIT_INIT Tester <t@t.t>", ws=g)
    run("alpha", "@GIT_COMMIT chore: start", "/routes.py", "/api.py", "/.gitignore", "@END_GIT_COMMIT", ws=g)
    run("beta", "@SCOPE api | api.py", ws=g)
    run("alpha", "@SCOPE routes | routes.py", *edit("routes.py"), ws=g)
    out = run("alpha", "@DELEGATE beta | /routes.py | finish and commit the routes", ws=g)
    check("in a git project the delegating chat's uncommitted work goes with the files", "[DELEGATED]" in out, out)
    out = run("beta", "@GIT_COMMIT fix(routes): finish the routes", "/routes.py", "@END_GIT_COMMIT", ws=g)
    check("so the receiving chat can commit it", "[COMMITTED]" in out and "REFUSED" not in out, out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
