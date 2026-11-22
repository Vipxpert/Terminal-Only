# /llm_harness/tests/setup_version_test.py
"""Setup-version test for llm_harness: setup.sh prints the available and the installed harness version before it replaces anything, and the version now installed at the end, for a first install and for an upgrade. It runs in a temporary HOME with fake curl and xclip first on PATH, so it neither downloads CBM nor installs packages."""
import os, shutil, stat, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SETUP = os.path.join(os.path.dirname(HERE), "setup.sh")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def main():
    sh = shutil.which("sh")
    if not sh or not os.path.isfile(SETUP):
        print("SKIP setup.sh needs a POSIX sh")
        sys.exit(0)
    root = tempfile.mkdtemp(prefix="harness-setupver-")
    src, home, fake = (os.path.join(root, n) for n in ("src", "home", "fakebin"))
    for d in (src, home, fake):
        os.makedirs(d)
    for name in ("curl", "wget", "xclip"):
        path = os.path.join(fake, name)
        with open(path, "w", newline="\n") as f:
            f.write("#!/bin/sh\nexit 1\n")
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    shutil.copy(SETUP, os.path.join(src, "setup.sh"))
    with open(os.path.join(src, "workflow_commands.txt"), "w") as f:
        f.write("rules\n")

    def run(version):
        with open(os.path.join(src, "harness.py"), "w") as f:
            f.write('"""stub"""\nVERSION = "%s"\n' % version)
        env = dict(os.environ, HOME=home, NO_PAUSE="1", PATH=fake + os.pathsep + os.environ.get("PATH", ""))
        p = subprocess.run([sh, os.path.join(src, "setup.sh")], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=120)
        return p.stdout.decode("utf-8", "replace")

    first = run("9.9")
    check("a first install prints none -> 9.9, and now 9.9", "Harness version: none -> 9.9" in first and "Installed version now: 9.9" in first, first)
    second = run("9.10")
    check("an upgrade prints 9.9 -> 9.10, and now 9.10", "Harness version: 9.9 -> 9.10" in second and "Installed version now: 9.10" in second, second)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
