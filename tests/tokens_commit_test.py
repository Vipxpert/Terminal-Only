# /llm_harness/tests/tokens_commit_test.py
"""Token-commit test for llm_harness: tokens.json changes on nearly every paste, so on its own it is not committed after each script; it is committed together with another memory change and when a session ends."""
import json, os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-tokens-")
RESULTS = []
STEP = [0]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-700:].replace("\n", "\n    "))


def git(*args):
    r = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t"] + list(args), cwd=WS, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return r.stdout.decode("utf-8", "replace").strip()


def run(*lines):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0], "@SESSION tok | token commit test", "@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def run_full(*lines):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0], "@SESSION tok | token commit test", "@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def bump(n):
    os.makedirs(os.path.join(WS, ".llm_harness"), exist_ok=True)
    with open(os.path.join(WS, ".llm_harness", "tokens.json"), "w", newline="\n") as f:
        json.dump({"buckets": {"t@m": {"account": "t", "machine": "m", "tokens": n, "pastes": 1, "chars": n * 4, "last_tok": n, "last_chars": n * 4, "sessions": {}}}}, f, indent=1)


def main():
    git("init", "-q")
    subprocess.run([sys.executable, HARNESS, "--workspace", WS, "--compact", "off"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    git("checkout", "-q", "-b", "main")
    with open(os.path.join(WS, "a.txt"), "w") as f:
        f.write("first line\n")
    bump(1)
    git("add", ".")
    git("commit", "-q", "-m", "chore: start")
    head0 = git("rev-parse", "HEAD")
    bump(2)
    run("@GREP first | in a.txt")
    check("tokens.json alone is not committed after a script", git("rev-parse", "HEAD") == head0 and "tokens.json" in git("status", "--porcelain"), git("status", "--porcelain"))
    full = run_full("@GREP first | in a.txt")
    check("a modified tokens.json alone does not keep the standing rules expanded", "[L1-Git Gate] (brief" in full and "uncommitted changes in workspace" not in full, full[-900:])
    out = run("@NOTE_ADD A standing fact for the test")
    show = git("show", "--stat", "--format=%s", "HEAD")
    check("with another memory change it is committed along", "tokens.json" in show and "notes.md" in show, show + out)
    bump(3)
    out = run("@SESSION_END")
    show = git("show", "--stat", "--format=%s", "HEAD")
    check("ending a session commits it", git("status", "--porcelain", "--", ".llm_harness/tokens.json") == "" and "tokens.json" in show, show + out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
