# /llm_harness/tests/setup_test.py
"""Setup test for llm_harness (Linux and macOS): setup.sh pulls the latest changes first when its folder is a git clone, then installs; a pull that brings a newer setup.sh runs that one; a folder that is not a clone, or a pull that fails, still installs the files already there."""
import os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = tempfile.mkdtemp(prefix="harness-setup-")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-800:].replace("\n", "\n    "))


def git(cwd, *args):
    r = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t"] + list(args), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return r.stdout.decode("utf-8", "replace").strip()


def put(path, text):
    with open(path, "w") as f:
        f.write(text)


def get(path):
    with open(path) as f:
        return f.read()


def setup(folder, home):
    bin_dir = os.path.join(BASE, "nobin")
    os.makedirs(bin_dir, exist_ok=True)
    for tool in ("curl", "wget"):
        put(os.path.join(bin_dir, tool), "#!/bin/sh\nexit 22\n")
        os.chmod(os.path.join(bin_dir, tool), 0o755)
    env = dict(os.environ, HOME=home, NO_PAUSE="1", PATH=bin_dir + os.pathsep + os.environ.get("PATH", ""))
    env.pop("LLM_SETUP_PULLED", None)
    p = subprocess.run(["/bin/sh", os.path.join(folder, "setup.sh")], cwd=folder, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120, stdin=subprocess.DEVNULL)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def main():
    if os.name == "nt":
        print("SKIP setup.sh is tested on Linux and macOS; run setup.cmd by hand on Windows")
        sys.exit(0)
    real_setup = os.path.join(ROOT, "setup.sh")
    origin, seed, clone = (os.path.join(BASE, n) for n in ("origin.git", "seed", "clone"))
    git(BASE, "init", "-q", "--bare", origin)
    git(origin, "symbolic-ref", "HEAD", "refs/heads/main")
    os.makedirs(seed)
    git(seed, "init", "-q")
    git(seed, "checkout", "-q", "-b", "main")
    put(os.path.join(seed, "harness.py"), "# harness v1\n")
    put(os.path.join(seed, "workflow_commands.txt"), "rules v1\n")
    shutil.copy(real_setup, os.path.join(seed, "setup.sh"))
    git(seed, "add", ".")
    git(seed, "commit", "-q", "-m", "chore: v1")
    git(seed, "remote", "add", "origin", origin)
    git(seed, "push", "-q", "origin", "main")
    git(BASE, "clone", "-q", origin, clone)
    put(os.path.join(seed, "harness.py"), "# harness v2\n")
    git(seed, "commit", "-q", "-am", "chore: v2")
    git(seed, "push", "-q", "origin", "main")
    home = os.path.join(BASE, "home1")
    os.makedirs(home)
    code, out = setup(clone, home)
    check("in a clone, setup pulls the newer harness before installing it", code == 0 and "Pulling the latest harness" in out and get(os.path.join(home, ".llm_harness", "harness.py")) == "# harness v2\n" and get(os.path.join(clone, "harness.py")) == "# harness v2\n", out)
    text = get(os.path.join(seed, "setup.sh")).replace('TARGET_DIR="$HOME/.llm_harness"', 'echo "SETUP-V2 RAN"\nTARGET_DIR="$HOME/.llm_harness"', 1)
    put(os.path.join(seed, "setup.sh"), text)
    put(os.path.join(seed, "harness.py"), "# harness v3\n")
    git(seed, "commit", "-q", "-am", "chore: v3 with a newer setup")
    git(seed, "push", "-q", "origin", "main")
    home = os.path.join(BASE, "home2")
    os.makedirs(home)
    code, out = setup(clone, home)
    check("when the pull brings a newer setup.sh, that one finishes the install, once", code == 0 and out.count("SETUP-V2 RAN") == 1 and out.count("Pulling the latest harness") == 1 and get(os.path.join(home, ".llm_harness", "harness.py")) == "# harness v3\n", out)
    plain = os.path.join(BASE, "plain")
    os.makedirs(plain)
    for n in ("harness.py", "workflow_commands.txt", "setup.sh"):
        shutil.copy(os.path.join(clone, n), os.path.join(plain, n))
    home = os.path.join(BASE, "home3")
    os.makedirs(home)
    code, out = setup(plain, home)
    check("a folder that is not a clone installs what it holds, without pulling", code == 0 and "Pulling" not in out and get(os.path.join(home, ".llm_harness", "harness.py")) == "# harness v3\n", out)
    git(clone, "remote", "set-url", "origin", os.path.join(BASE, "gone.git"))
    put(os.path.join(seed, "harness.py"), "# harness v4\n")
    home = os.path.join(BASE, "home4")
    os.makedirs(home)
    code, out = setup(clone, home)
    check("a pull that fails warns and still installs the files already there", code == 0 and "WARNING: git pull did not complete" in out and get(os.path.join(home, ".llm_harness", "harness.py")) == "# harness v3\n", out)
    if os.uname().sysname != "Darwin":
        clip_bin, clip_log, home5 = os.path.join(BASE, "clipbin"), os.path.join(BASE, "clip.log"), os.path.join(BASE, "home5")
        os.makedirs(clip_bin, exist_ok=True)
        os.makedirs(home5)
        for tool in ("xclip", "xsel", "wl-copy", "pbcopy"):
            put(os.path.join(clip_bin, tool), "#!/bin/sh\nexit 127\n")
            os.chmod(os.path.join(clip_bin, tool), 0o755)
        put(os.path.join(clip_bin, "sudo"), '#!/bin/sh\nexec "$@"\n')
        put(os.path.join(clip_bin, "apt-get"), '#!/bin/sh\necho "$*" >> "%s"\nexit 0\n' % clip_log)
        os.chmod(os.path.join(clip_bin, "sudo"), 0o755)
        os.chmod(os.path.join(clip_bin, "apt-get"), 0o755)
        env5 = dict(os.environ, HOME=home5, NO_PAUSE="1", PATH=os.pathsep.join([clip_bin, os.path.join(BASE, "nobin"), "/usr/bin", "/bin"]), XDG_SESSION_TYPE="x11", WAYLAND_DISPLAY="")
        env5.pop("LLM_SETUP_PULLED", None)
        p5 = subprocess.run(["/bin/sh", os.path.join(plain, "setup.sh")], cwd=plain, env=env5, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60, stdin=subprocess.DEVNULL)
        logged = get(clip_log) if os.path.exists(clip_log) else ""
        check("setup.sh installs xclip when no clipboard tool is present", p5.returncode == 0 and "install -y -qq xclip" in logged, p5.stdout.decode("utf-8", "replace") + "\n" + logged)
    print("test workspace: " + BASE)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
