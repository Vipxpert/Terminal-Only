# /llm_harness/tests/gh_account_test.py
"""gh-account test for llm_harness: the gh CLI is a source of accounts for @GIT_ACCOUNT. The JSON parser keeps only healthy accounts of the asked host and survives garbage (any OS); with a fake gh on POSIX, the accounts are listed, a pin also switches gh, the harness says to run gh auth setup-git when git does not use gh as its credential helper, and says nothing once it does."""
import importlib.util, json, os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
BASE = tempfile.mkdtemp(prefix="harness-gh-")
RESULTS = []
STEP = [0]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-800:].replace("\n", "\n    "))


def git(cwd, *args):
    r = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t"] + list(args), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return r.stdout.decode("utf-8", "replace").strip()


def main():
    spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS)
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    sample = {"hosts": {"github.com": [
        {"state": "success", "active": False, "host": "github.com", "login": "alice"},
        {"state": "success", "active": True, "host": "github.com", "login": "bob"},
        {"state": "error", "active": False, "host": "github.com", "login": "carol"}],
        "other.example": [{"state": "success", "active": True, "host": "other.example", "login": "dave"}]}}
    check("the parser keeps healthy accounts of the asked host and finds the active one", hh.parse_gh_accounts(json.dumps(sample), "github.com") == (["alice", "bob"], "bob"), hh.parse_gh_accounts(json.dumps(sample), "github.com"))
    check("garbage, an empty object and an unknown host give no accounts", hh.parse_gh_accounts("not json", "github.com") == ([], None) and hh.parse_gh_accounts("{}", "github.com") == ([], None) and hh.parse_gh_accounts(json.dumps(sample), "nowhere") == ([], None))
    if os.name == "nt":
        print("SKIP the fake gh is a shell script; the rest is checked on Linux and macOS")
        sys.exit(0 if all(RESULTS) else 1)
    fake = os.path.join(BASE, "bin")
    os.makedirs(fake)
    log, status = os.path.join(BASE, "gh.log"), os.path.join(BASE, "status.json")
    with open(status, "w") as f:
        json.dump(sample, f)
    with open(os.path.join(fake, "gh"), "w") as f:
        f.write('#!/bin/sh\nif [ "$1" = "auth" ] && [ "$2" = "status" ]; then cat "%s"; exit 0; fi\nif [ "$1" = "auth" ] && [ "$2" = "switch" ]; then echo "$@" >> "%s"; exit 0; fi\nexit 1\n' % (status, log))
    os.chmod(os.path.join(fake, "gh"), 0o755)
    proj = os.path.join(BASE, "proj")
    os.makedirs(proj)
    git(proj, "init", "-q")
    git(proj, "remote", "add", "origin", "https://github.com/alice-org/proj.git")
    env = dict(os.environ, PATH=fake + os.pathsep + os.environ.get("PATH", ""), LLM_HARNESS_FETCH="off", LLM_HARNESS_NO_COPY="1", GIT_TERMINAL_PROMPT="0", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")

    def run(*lines):
        STEP[0] += 1
        text = "\n".join(["@SCRIPT [C: gh %d]" % STEP[0], "@WORKSPACE " + proj] + list(lines) + [""])
        return subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120, env=env).stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")

    out = run("@GIT_ACCOUNT")
    check("the gh accounts are listed with their source, and an errored login is left out", "1. alice" in out and "2. bob" in out and "GitHub CLI (gh)" in out and "carol" not in out, out)
    out = run("@GIT_ACCOUNT bob")
    sw = open(log).read() if os.path.exists(log) else ""
    check("pinning a gh account also switches gh to it", "[PINNED] github.com -> bob" in out and "auth switch --hostname github.com --user bob" in sw, (out, sw))
    check("without gh as the credential helper the harness names gh auth setup-git and does not run it", "gh auth setup-git --hostname github.com" in out and "setup-git" not in sw, (out, sw))
    git(proj, "config", "--local", "credential.helper", "!/usr/bin/gh auth git-credential")
    out = run("@GIT_ACCOUNT alice")
    check("once git uses gh as its helper there is no setup hint", "[PINNED] github.com -> alice" in out and "setup-git" not in out, out)
    print("test workspace: " + BASE)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
