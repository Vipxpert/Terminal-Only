# /llm_harness/tests/git_reads_test.py
"""Read-only git through @RUN: listing tags or stashes is allowed; creating or deleting a tag, or stashing, is still refused (those go through the harness's own directives)."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-gitreads-")
RESULTS = []
STEP = [0]


def git(*args):
    r = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t"] + list(args), cwd=WS, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return r.stdout.decode("utf-8", "replace").strip()


def run(cmd):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0], "@WORKSPACE " + WS, "@RUN " + cmd]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-700:].replace("\n", "\n    "))


def main():
    git("init", "-q")
    with open(os.path.join(WS, "a.txt"), "w") as f:
        f.write("x\n")
    git("add", ".")
    git("commit", "-q", "-m", "chore: start")
    git("tag", "v1.0.0")
    out = run("git tag")
    check("git tag with nothing after it lists the tags", "v1.0.0" in out and "[REFUSED]" not in out, out)
    out = run("git tag --list")
    check("git tag --list is allowed", "v1.0.0" in out and "[REFUSED]" not in out, out)
    out = run("git tag -l v1*")
    check("git tag -l with a pattern is allowed", "v1.0.0" in out and "[REFUSED]" not in out, out)
    out = run("git tag --contains HEAD")
    check("git tag --contains is allowed", "v1.0.0" in out and "[REFUSED]" not in out, out)
    out = run("git stash list")
    check("git stash list is allowed", "[REFUSED]" not in out and "[exit 0" in out, out)
    out = run("git tag v2.0.0")
    check("creating a tag is still refused and nothing is created", "[REFUSED]" in out and "v2.0.0" not in git("tag"), out)
    out = run("git tag -d v1.0.0")
    check("deleting a tag is still refused and the tag stays", "[REFUSED]" in out and "v1.0.0" in git("tag"), out)
    out = run("git tag --list; git tag v3.0.0")
    check("a listing followed by a write in one command is refused", "[REFUSED]" in out and "v3.0.0" not in git("tag"), out)
    out = run("git stash")
    check("a plain git stash is still refused", "[REFUSED]" in out, out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
