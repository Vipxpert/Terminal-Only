# /llm_harness/tests/session_merge_test.py
"""Session merge test for llm_harness: --merge <from> <into> absorbs write scope, grants, uncommitted history ownership/undo, pinned notes, verdicts, and delegation/waiting queues, even after the source session was released."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-merge-")
RESULTS = []
STEP = [0]


def run(session, *lines):
    STEP[0] += 1
    payload = "\n".join(["@SCRIPT [C: step %d]" % STEP[0], "@SESSION " + session, "@WORKSPACE " + WS] + list(lines) + [""])
    p = subprocess.run([sys.executable, HARNESS], input=payload.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0]


def user(*args):
    p = subprocess.run([sys.executable, HARNESS, "--workspace", WS] + list(args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.stdout.decode("utf-8", "replace")


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-700:].replace("\n", "\n    "))


def hunk(path, old, new):
    return ["@FILE " + path, "@HUNK TOP | edit", "--- [OLD CODE] ---", old, "+++ [NEW CODE] +++", new, "=== [END HUNK] ==="]


def commit(msg, *paths):
    return ["@GIT_COMMIT " + msg] + ["/" + p for p in paths] + ["@END_GIT_COMMIT"]


def git(*args):
    subprocess.run(["git"] + list(args), cwd=WS, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def main():
    for d in ("src", "docs"):
        os.makedirs(os.path.join(WS, d), exist_ok=True)
    for f in ("src/dead.py", "src/live.py", "src/helper.py", "docs/spec.md"):
        with open(os.path.join(WS, f), "w") as fh:
            fh.write("x = 0\n")
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    git("add", "-A")
    git("commit", "-qm", "init")

    dead = "dead-chat | old stalled task"
    live = "live-chat | active continuation"
    helper = "helper-chat | assisting"

    run(live, "@SCOPE live work | src/live.py", "@VERDICT /src/live.py | clean | verified by live")
    run(helper, "@SCOPE helper work | src/helper.py")
    run(dead,
        "@SCOPE dead work | src/dead.py, docs/spec.md",
        *hunk("/src/dead.py", "x = 0", "x = 1"),
        "@NOTE_ADD pin dead-chat | Todo: finish dead-chat cleanup",
        "@VERDICT /src/dead.py | needs-fix | left by dead-chat",
        "@VERDICT /src/live.py | stale-opinion | older dead-chat view",
        "@SCOPE_REQUEST helper-chat | src/helper.py | need helper file")
    run(dead, "@DELEGATE helper-chat | docs/spec.md | review spec")
    user("--grant", "dead-chat", "docs/spec.md")

    out = run(live, "@RUN python \"" + HARNESS + "\" --workspace . --merge dead-chat live-chat")
    check("a script cannot run --merge", "[REFUSED]" in out and "--merge" in out, out)

    res = user("--merge", "dead-chat", "live-chat")
    check("--merge transfers scope, grants, history, notes, verdicts, and delegations",
          "SESSION MERGED BY THE USER: dead-chat -> live-chat" in res and "scope (" in res and "history (" in res and "notes (1)" in res and "verdicts (" in res,
          res)

    out = run(live, "@VERDICTS", *commit("feat: adopt dead-chat work", "src/dead.py"))
    check("merged session sees one-time notice, pinned note, transferred verdict, and can commit dead session's uncommitted work",
          "merged session dead-chat into your session" in out
          and "Todo: finish dead-chat cleanup" in out
          and "needs-fix" in out
          and "clean" in out
          and "[COMMITTED]" in out,
          out)

    out = run(helper, "@RETURN live-chat | spec reviewed")
    check("delegated helper can @RETURN straight to the merged target session", "[RETURNED] /docs/spec.md -> live-chat" in out, out)

    ghost = "ghost-chat | ended early"
    run(ghost, "@NOTE_ADD pin ghost-chat | Follow up after release", "@VERDICT /docs/spec.md | checked | ghost verdict")
    user("--release", "ghost-chat")
    res2 = user("--merge", "ghost-chat", "live-chat")
    out2 = run(live, "@VERDICTS")
    check("--merge also absorbs notes and verdicts from an already-released session",
          "SESSION MERGED BY THE USER: ghost-chat -> live-chat" in res2
          and "Follow up after release" in out2
          and "ghost verdict" in out2,
          res2 + "\n" + out2)

    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
