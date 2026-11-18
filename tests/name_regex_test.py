# /llm_harness/tests/name_regex_test.py
"""Path-regex test for llm_harness: @FIND and the '| in' filter of @GREP accept re:<regex> on the workspace-relative path."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-nameregex-")
RESULTS = []
STEP = [0]


def run(*lines):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0], "@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def put(rel, text):
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
    put("src/api/user_test.py", "value = 1\n")
    put("src/api/user.py", "value = 2\n")
    put("test_x.py", "value = 3\n")
    put("docs/readme.md", "value = 4\n")
    out = run("@FIND re:_test[.]py$")
    check("@FIND filters by a regex on the path (a suffix)", "/src/api/user_test.py" in out and "/src/api/user.py" not in out and "(1 file(s))" in out, out)
    out = run("@FIND re:^test_")
    check("@FIND filters by a regex on the path (a prefix)", "/test_x.py" in out and "(1 file(s))" in out, out)
    out = run("@FIND re:^src/.*[.]py$")
    check("@FIND regex can span folders", "(2 file(s))" in out and "/src/api/user.py" in out, out)
    out = run("@GREP value | in re:^docs/")
    check("@GREP limits its search with a path regex", "/docs/readme.md:1" in out and "/src/api" not in out and "(1 match(es) in 1 file(s))" in out, out)
    out = run("@FIND re:(")
    check("an invalid path regex is reported, not a crash", "invalid path regex" in out, out)
    out = run("@FIND *.md")
    check("globs and fragments still work", "/docs/readme.md" in out and "(1 file(s))" in out, out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
