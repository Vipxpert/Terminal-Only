# /llm_harness/tests/quiet_fetch_test.py
"""Quiet-fetch test for llm_harness (Linux and macOS): the automatic fetch behind the UPSTREAM line asks Git Credential Manager not to open a window (GCM_INTERACTIVE=never), while a fetch the user asked for with @GIT_PULL does not; checked with a stand-in git that records what each fetch was given."""
import os, shutil, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
BASE = tempfile.mkdtemp(prefix="harness-quietfetch-")
RESULTS = []
STEP = [0]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-700:].replace("\n", "\n    "))


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t"] + list(args), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def main():
    if os.name == "nt":
        print("SKIP the stand-in git is a shell script; the quiet fetch is checked on Linux and macOS")
        sys.exit(0)
    real = shutil.which("git")
    origin, proj, fake = (os.path.join(BASE, n) for n in ("origin.git", "proj", "bin"))
    record = os.path.join(BASE, "record.txt")
    os.makedirs(fake)
    with open(os.path.join(fake, "git"), "w") as f:
        f.write('#!/bin/sh\nif [ "$1" = "fetch" ]; then echo "[$GCM_INTERACTIVE] $*" >> "$LLM_RECORD"; fi\nexec "%s" "$@"\n' % real)
    os.chmod(os.path.join(fake, "git"), 0o755)
    git(BASE, "init", "-q", "--bare", origin)
    git(origin, "symbolic-ref", "HEAD", "refs/heads/main")
    os.makedirs(proj)
    git(proj, "init", "-q")
    git(proj, "checkout", "-q", "-b", "main")
    with open(os.path.join(proj, "a.txt"), "w") as f:
        f.write("x\n")
    git(proj, "add", ".")
    git(proj, "commit", "-q", "-m", "chore: start")
    git(proj, "remote", "add", "origin", origin)
    git(proj, "push", "-q", "-u", "origin", "main")
    env = dict(os.environ, PATH=fake + os.pathsep + os.environ.get("PATH", ""), LLM_RECORD=record, LLM_HARNESS_FETCH="0")
    env.pop("GCM_INTERACTIVE", None)

    def run(*lines):
        STEP[0] += 1
        head = ["@SCRIPT [C: step %d]" % STEP[0], "@WORKSPACE " + proj]
        return subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120, env=env).stdout.decode("utf-8", "replace")

    run()
    seen = open(record).read() if os.path.exists(record) else ""
    check("the automatic fetch runs with GCM_INTERACTIVE=never", "[never] fetch --quiet origin" in seen, seen)
    os.remove(record)
    run("@GIT_PULL")
    seen = open(record).read() if os.path.exists(record) else ""
    check("the fetch inside @GIT_PULL, which the user asked for, does not set it, so a sign-in can still be asked for", "[] fetch --quiet origin" in seen, seen)
    print("test workspace: " + BASE)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
