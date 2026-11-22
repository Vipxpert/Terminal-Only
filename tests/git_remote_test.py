# /llm_harness/tests/git_remote_test.py
"""Remote test for llm_harness: @GIT_REMOTE lists, adds or changes a remote and says what changed, refuses addresses that are not https or ssh, that carry a password or token, or that look like an option, refuses a bad name, and never removes a remote."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []
COUNT = [0]
URL1, URL2 = "https://example.com/team/project.git", "git@example.com:team/other.git"


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-700:].replace("\n", "\n    "))


def git(ws, *args):
    p = subprocess.run(["git"] + list(args), cwd=ws, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.stdout.decode("utf-8", "replace").strip()


def run(ws, *lines):
    COUNT[0] += 1
    text = "\n".join(["@SCRIPT [C: remote %d]" % COUNT[0], "@WORKSPACE " + ws] + list(lines)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "").split("=== L1 CONTRACT")[0]


def main():
    ws = tempfile.mkdtemp(prefix="harness-remote-")
    git(ws, "init", "-q")
    out = run(ws, "@GIT_REMOTE")
    check("with no remote the listing says so", "no remote yet" in out, out)
    out = run(ws, "@GIT_REMOTE origin " + URL1)
    check("a remote is added and the run says so", "added origin" in out and git(ws, "remote", "get-url", "origin") == URL1, out)
    out = run(ws, "@GIT_REMOTE origin " + URL1)
    check("the same address again changes nothing and says so", "already points" in out and git(ws, "remote", "get-url", "origin") == URL1, out)
    out = run(ws, "@GIT_REMOTE set-url origin " + URL2)
    check("a different address changes the remote and names the old one", "changed origin" in out and URL1 in out and git(ws, "remote", "get-url", "origin") == URL2, out)
    out = run(ws, "@GIT_REMOTE")
    check("the listing shows the address", URL2 in out, out)
    bad = ["file:///tmp/elsewhere.git", "ext::sh", "/tmp/a/local/path", "https://user:secret@example.com/a/b.git", "-oops"]
    outs = [run(ws, "@GIT_REMOTE origin " + b) for b in bad]
    check("addresses that are not https or ssh, that carry a password, or that look like an option are refused", all("[GIT REMOTE REFUSED]" in o for o in outs) and git(ws, "remote", "get-url", "origin") == URL2, [o[-300:] for o in outs if "[GIT REMOTE REFUSED]" not in o])
    out = run(ws, "@GIT_REMOTE -x " + URL1)
    check("a name that starts with a dash is refused", "[GIT REMOTE REFUSED]" in out and git(ws, "remote") == "origin", out)
    out = run(ws, "@GIT_REMOTE origin " + URL2 + " extra")
    check("extra words are refused and the remote stays", "[GIT REMOTE REFUSED]" in out and git(ws, "remote", "get-url", "origin") == URL2, out)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
