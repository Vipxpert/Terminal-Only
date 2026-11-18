# /llm_harness/tests/scope_glob_test.py
"""Scope-glob test for llm_harness: a glob collides only with files it really matches (not with every file, and not across folders or extensions), and a scope entry whose file name holds a space is accepted even after the file was deleted."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-scopeglob-")
RESULTS = []
STEP = [0]


def run(session, *lines):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0], "@SESSION %s | try globs" % session, "@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def put(rel, text="x\n"):
    path = os.path.join(WS, rel)
    os.makedirs(os.path.dirname(path) or WS, exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-800:].replace("\n", "\n    "))


def main():
    for rel in ("discord_bots/universal_bot/bot.py", "core/web_agent_poc.py", "docs/trees/tree_discord_bots.txt", "docs/notes.md", "why1.txt", "my notes.txt"):
        put(rel)
    run("alpha", "@SCOPE bot | discord_bots/universal_bot/bot.py, core/web_agent_poc.py, docs/trees/tree_discord_bots.txt")
    out = run("beta", "@SCOPE why files | /why*.txt")
    check("a root glob does not collide with unrelated files in other folders", "scope set" in out and "SCOPE REFUSED" not in out, out)
    out = run("gamma", "@SCOPE md | docs/*.md")
    check("a glob in one folder does not collide with a file of another extension below it", "scope set" in out and "SCOPE REFUSED" not in out, out)
    out = run("delta", "@SCOPE txt | docs/*.txt")
    check("* stays in one folder, so docs/*.txt does not reach docs/trees/", "scope set" in out and "SCOPE REFUSED" not in out, out)
    out = run("epsilon", "@SCOPE deep | docs/**/*.txt")
    check("a glob that really matches another chat's file is still refused", "SCOPE REFUSED" in out and "docs/trees/tree_discord_bots.txt" in out, out)
    out = run("zeta", "@SCOPE whole | discord_bots")
    check("a folder around another chat's file is still refused", "SCOPE REFUSED" in out, out)
    run("eta", "@SCOPE spaced | my notes.txt")
    run("eta", "@DELETE_FILE /my notes.txt")
    run("eta", "@SCOPE_END")
    out = run("eta", "@SCOPE spaced again | my notes.txt")
    check("a file name with a space is accepted after the file was deleted", "scope set" in out and "holds a space" not in out, out)
    out = run("theta", "@SCOPE two files | a.py b.py")
    check("two paths run together are still refused with the comma hint", "separate scope paths with commas" in out, out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
