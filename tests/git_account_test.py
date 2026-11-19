# /llm_harness/tests/git_account_test.py
"""Git-account test for llm_harness: @GIT_ACCOUNT lists the accounts signed in for the remote's host (GitHub through Git Credential Manager, with a stand-in here), pins one for this project in the clone's git config so git passes that username to the credential helper instead of showing a chooser, refuses an account that is not signed in, clears the pin, and does nothing for SSH remotes; at a terminal a pressed number pins the account. The account-name reading from the Windows credential list is checked everywhere."""
import importlib.util, os, shutil, subprocess, sys, tempfile, time

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
BASE = tempfile.mkdtemp(prefix="harness-account-")
RESULTS = []
STEP = [0]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-800:].replace("\n", "\n    "))


def git(cwd, *args, **kw):
    r = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t"] + list(args), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, input=kw.get("input"), env=kw.get("env"))
    return r.stdout.decode("utf-8", "replace").strip()


def main():
    spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS)
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    sample = "\nCurrent credentials:\n\n    Target: LegacyGeneric:target=git:https://github.com\n    Type: Generic\n    User: alice\n    Local machine persistence\n\n    Target: LegacyGeneric:target=git:https://alice@github.com\n    Type: Generic\n    User: alice\n\n    Target: LegacyGeneric:target=git:https://bob@github.com\n    Type: Generic\n    User: bob\n\n    Target: LegacyGeneric:target=git:https://carol@gitlab.com\n    Type: Generic\n    User: carol\n"
    check("account names are read from the git entries of the Windows credential list, one host at a time", hh.parse_cmdkey_accounts(sample, "github.com") == ["alice", "bob"] and hh.parse_cmdkey_accounts(sample, "gitlab.com") == ["carol"] and hh.parse_cmdkey_accounts("", "github.com") == [], hh.parse_cmdkey_accounts(sample, "github.com"))
    if os.name == "nt":
        print("SKIP the stand-ins for Git Credential Manager and the credential helper are shell scripts; the rest is checked on Linux and macOS")
        sys.exit(0 if all(RESULTS) else 1)
    fake = os.path.join(BASE, "bin")
    os.makedirs(fake)
    with open(os.path.join(fake, "git-credential-manager"), "w") as f:
        f.write('#!/bin/sh\nSTATE="%s"\n[ -f "$STATE" ] || printf "alice\\nbob\\n" > "$STATE"\nif [ "$1" = "github" ] && [ "$2" = "list" ]; then cat "$STATE"; exit 0; fi\nif [ "$1" = "github" ] && [ "$2" = "login" ]; then echo carol >> "$STATE"; exit 0; fi\nexit 1\n' % os.path.join(BASE, "accounts.txt"))
    os.chmod(os.path.join(fake, "git-credential-manager"), 0o755)
    helper, log = os.path.join(fake, "helper.sh"), os.path.join(BASE, "helper.log")
    with open(helper, "w") as f:
        f.write('#!/bin/sh\ncat >> "%s"\necho "password=secret"\n' % log)
    os.chmod(helper, 0o755)
    proj, ssh, bare = (os.path.join(BASE, n) for n in ("proj", "ssh", "bare"))
    for d in (proj, ssh, bare):
        os.makedirs(d)
        git(d, "init", "-q")
    git(proj, "remote", "add", "origin", "https://github.com/alice-org/proj.git")
    git(ssh, "remote", "add", "origin", "git@github.com:alice-org/proj.git")
    git(proj, "checkout", "-q", "-b", "main")
    git(proj, "commit", "--allow-empty", "-q", "-m", "chore: start")
    git(proj, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(proj, "config", "branch.main.remote", "origin")
    git(proj, "config", "branch.main.merge", "refs/heads/main")
    git(proj, "commit", "--allow-empty", "-q", "-m", "feat: one commit ahead")
    wrapper = """#!/bin/sh
if [ "$1" = "fetch" ] && [ -n "$LLM_FAIL_FETCH" ]; then
  if [ "$LLM_FAIL_FETCH" = "auth" ]; then echo "fatal: could not read Username for 'https://github.com': terminal prompts disabled" >&2; else echo "fatal: unable to access 'https://github.com/': Could not resolve host: github.com" >&2; fi
  exit 128
fi
exec "REAL_GIT" "$@"
""".replace("REAL_GIT", shutil.which("git"))
    with open(os.path.join(fake, "git"), "w") as f:
        f.write(wrapper)
    os.chmod(os.path.join(fake, "git"), 0o755)
    env = dict(os.environ, PATH=fake + os.pathsep + os.environ.get("PATH", ""), LLM_HARNESS_FETCH="off", LLM_HARNESS_NO_COPY="1", GIT_TERMINAL_PROMPT="0", https_proxy="http://127.0.0.1:9", HTTPS_PROXY="http://127.0.0.1:9")

    def run(ws, *lines, extra=None):
        STEP[0] += 1
        head = ["@SCRIPT [C: step %d]" % STEP[0], "@WORKSPACE " + ws]
        return subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120, env=dict(env, **(extra or {}))).stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")

    key = "credential.https://github.com.username"
    out = run(proj, "@GIT_ACCOUNT")
    check("the accounts are listed, with what is pinned and how to pin", "1. alice" in out and "2. bob" in out and "accounts from Git Credential Manager" in out and "none pinned yet" in out and "pin one with @GIT_ACCOUNT" in out, out)
    out = run(proj, "@GIT_ACCOUNT BOB")
    check("an account is pinned by name (any letter case), under its real spelling", "[PINNED] github.com -> bob" in out and git(proj, "config", "--local", "--get", key) == "bob", out)
    git(proj, "config", "--local", "credential.helper", helper)
    git(proj, "credential", "fill", input=b"protocol=https\nhost=github.com\n\n", env=env)
    got = open(log).read() if os.path.exists(log) else ""
    check("git now hands that username to the credential helper, which is what stops the chooser", "username=bob" in got, got)
    out = run(proj, "@GIT_ACCOUNT carol")
    check("an account that is not signed in is refused and the pin stays", "[GIT ACCOUNT REFUSED]" in out and "alice, bob" in out and git(proj, "config", "--local", "--get", key) == "bob", out)
    out = run(proj, "@GIT_ACCOUNT")
    check("the listing shows the pinned account", "2. bob   <- pinned for this project" in out, out)
    out = run(proj, "@GIT_ACCOUNT clear")
    check("clear removes the pin", "cleared" in out and git(proj, "config", "--local", "--get", key) == "", out)
    out = run(ssh, "@GIT_ACCOUNT")
    check("an SSH remote has nothing to pin", "not an https remote" in out, out)
    out = run(bare, "@GIT_ACCOUNT")
    check("a repository without a remote says so", "no remote" in out, out)
    import pty, select

    def pressed(answer, lines=("@GIT_ACCOUNT",), marker=b"to pin one for this project"):
        STEP[0] += 1
        path = os.path.join(BASE, "script%d.txt" % STEP[0])
        with open(path, "w") as f:
            f.write("@SCRIPT [C: pty %d]\n@WORKSPACE %s\n%s\n" % (STEP[0], proj, "\n".join(lines)))
        pid, master = pty.fork()
        if pid == 0:
            os.dup2(os.open(path, os.O_RDONLY), 0)
            os.execve(sys.executable, [sys.executable, HARNESS], env)
        answers = answer if isinstance(answer, list) else [answer]; buf, sent, deadline = b"", 0, time.time() + 40
        while time.time() < deadline:
            ready, _, _ = select.select([master], [], [], 1)
            if not ready:
                continue
            try:
                chunk = os.read(master, 65536)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            if sent < len(answers) and buf.count(marker) > sent:
                os.write(master, answers[sent])
                sent += 1
        os.waitpid(pid, 0)
        return buf.decode("utf-8", "replace")

    out = pressed(b"2")
    check("at a terminal, pressing a number pins that account", "[PINNED] github.com -> bob" in out and git(proj, "config", "--local", "--get", key) == "bob", out)
    git(proj, "config", "--local", "--unset", key)
    out = pressed(b"x")
    check("pressing X leaves the project as it was", "[PINNED]" not in out and git(proj, "config", "--local", "--get", key) == "", out)
    key_pin = "credential.https://github.com.username"
    git(proj, "config", "--local", "--unset", key_pin)
    out = run(proj, extra={"LLM_HARNESS_FETCH": "0", "LLM_FAIL_FETCH": "auth"})
    check("when the automatic fetch cannot sign in and nothing is pinned, the footer says why and what to do", "=== GIT ACCOUNT: the automatic fetch could not sign in to github.com" in out and "@GIT_ACCOUNT" in out, out)
    git(proj, "config", "--local", key_pin, "bob")
    out = run(proj, extra={"LLM_HARNESS_FETCH": "0", "LLM_FAIL_FETCH": "auth"})
    check("with an account pinned there is no such line", "=== GIT ACCOUNT" not in out, out)
    git(proj, "config", "--local", "--unset", key_pin)
    out = run(proj, extra={"LLM_HARNESS_FETCH": "0", "LLM_FAIL_FETCH": "net"})
    check("a fetch that fails for another reason (no network) says nothing about accounts", "=== GIT ACCOUNT" not in out, out)
    out = run(proj, "@GIT_PUSH")
    check("without a terminal a push does not ask, and pins nothing", "Several accounts are signed in" not in out and git(proj, "config", "--local", "--get", key_pin) == "", out)
    out = pressed(b"2", ("@GIT_PUSH",), b"Several accounts are signed in")
    check("a push the user asked for asks once which account to use, and pins it", "[PINNED] github.com -> bob" in out and git(proj, "config", "--local", "--get", key_pin) == "bob", out)
    out = pressed(b"", ("@GIT_PUSH",), b"Several accounts are signed in")
    check("once pinned the same push never asks again", "Several accounts are signed in" not in out, out)
    git(proj, "config", "--local", "--unset", key_pin)
    out = pressed(b"x", ("@GIT_PUSH",), b"Several accounts are signed in")
    check("X decides later and pins nothing", "[PINNED]" not in out and git(proj, "config", "--local", "--get", key_pin) == "", out)
    git(proj, "config", "--local", key_pin, "bob")
    out = run(proj, "@GIT_PUSH")
    check("a push says which account it signs in with, so a sign-in window can be answered correctly", "[ACCOUNT] signing in to github.com as bob (pinned for this project)" in out and "authorize bob in the browser" in out, out)
    git(proj, "config", "--local", "--unset", key_pin)
    out = run(proj, "@GIT_PUSH")
    check("with nothing pinned the push does not name an account", "[ACCOUNT]" not in out, out)
    out = pressed([b"a", b"3"], ("@GIT_ACCOUNT",))
    check("A signs another account in first, the list then offers it, and its number pins it", "3. carol" in out and "[PINNED] github.com -> carol" in out and git(proj, "config", "--local", "--get", key_pin) == "carol", out)
    out = run(proj, "@GIT_ACCOUNT")
    check("without a terminal the listing says how to add an account", "git credential-manager github login" in out, out)
    print("test workspace: " + BASE)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
