# /llm_harness/tests/setup_pull_tokens_test.py
"""Setup pull-tokens test for llm_harness: setup.cmd (Windows) and setup.sh (Linux/macOS) fast-forward cleanly when .llm_harness/tokens.json is locally modified and incoming commits also changed it, merging both machines' token counts."""
import json, os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = []


def TOK(n):
    return json.dumps({"buckets": {"acct@m": {"tokens": n, "pastes": 1, "chars": n * 4, "sessions": {}}}})


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def git(cwd, *args):
    p = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t"] + list(args), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.stdout.decode("utf-8", "replace").strip()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main():
    base = tempfile.mkdtemp(prefix="harness-setup-tok-")
    origin, seed, clone, home = (os.path.join(base, n) for n in ("origin.git", "seed", "clone", "home"))
    os.makedirs(seed)
    os.makedirs(home)
    git(base, "init", "-q", "--bare", origin)
    git(origin, "symbolic-ref", "HEAD", "refs/heads/main")
    git(seed, "init", "-q")
    git(seed, "checkout", "-q", "-b", "main")
    for name in ("harness.py", "workflow_commands.txt", "setup.cmd", "setup.sh"):
        shutil.copy(os.path.join(ROOT, name), os.path.join(seed, name))
    write(os.path.join(seed, ".llm_harness", "tokens.json"), TOK(10))
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "init")
    git(seed, "remote", "add", "origin", origin)
    git(seed, "push", "-q", "-u", "origin", "main")
    git(base, "clone", "-q", origin, clone)
    write(os.path.join(seed, ".llm_harness", "tokens.json"), TOK(40))
    write(os.path.join(seed, "marker.txt"), "pulled\n")
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "incoming token counts")
    git(seed, "push", "-q", "origin", "main")
    write(os.path.join(clone, ".llm_harness", "tokens.json"), TOK(25))
    env = dict(os.environ)
    if os.name == "nt":
        env["USERPROFILE"] = home
        p = subprocess.run(["cmd", "/c", os.path.join(clone, "setup.cmd")], cwd=clone, env=env, input=b"\r\n", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    else:
        env["HOME"] = home
        env["NO_PAUSE"] = "1"
        env.pop("LLM_SETUP_PULLED", None)
        p = subprocess.run(["/bin/sh", os.path.join(clone, "setup.sh")], cwd=clone, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    out = p.stdout.decode("utf-8", "replace")
    check("setup fast-forwards over dirty .llm_harness/tokens.json", p.returncode == 0 and os.path.isfile(os.path.join(clone, "marker.txt")) and "git pull did not complete" not in out, out)
    try:
        with open(os.path.join(clone, ".llm_harness", "tokens.json"), "r", encoding="utf-8") as f:
            merged = json.load(f)["buckets"]["acct@m"]["tokens"]
    except (OSError, ValueError, KeyError) as exc:
        merged = repr(exc)
    check("setup 3-way merges local and incoming tokens.json counts (25 + 40 - 10 = 55)", merged == 55, (merged, out))
    print("test workspace: " + base)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
