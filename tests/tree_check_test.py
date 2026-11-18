# /llm_harness/tests/tree_check_test.py
"""Tree-check test for llm_harness: extensionless files (Dockerfile, Makefile, dotfiles) are checked as files, and a # Stage node must match a real anchor comment, not just the same words somewhere in the file."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-treecheck-")
RESULTS = []
STEP = [0]


def run(*lines):
    STEP[0] += 1
    head = ["@SCRIPT [P: step %d]" % STEP[0], "@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def put(rel, text):
    path = os.path.join(WS, rel)
    os.makedirs(os.path.dirname(path) or WS, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-900:].replace("\n", "\n    "))


def main():
    proj = os.path.basename(WS)
    put("Dockerfile", "FROM python:3.12\n")
    put(".gitignore", "*.pyc\n")
    put("app.py", "# /%s/app.py\ndef main():\n    # Stage: Load (read the input)\n    x = 'Stage: Save is only text in a string'\n    return x\n" % proj)
    put("docs/trees/tree_master.txt", "\n".join([
        "# /%s/docs/trees/tree_master.txt" % proj,
        "/%s (Root)" % proj,
        "|-- Dockerfile (Container image)",
        "|-- Makefile (Build entry, deleted from disk)",
        "|-- .gitignore (Ignored files)",
        "\\-- app.py (Entry)",
        "    \\-- () main (Runs the job)",
        "        |-- # Stage: Load (read the input)",
        "        \\-- # Stage: Save (anchor deleted, words left in a string)", ""]))
    out = run("@PROBE /docs/trees/tree_master.txt | Check")
    check("extensionless files and dotfiles are checked as files", "4 file(s)" in out and "Dockerfile" not in out.split("stale]")[-1].split("file not found")[0] and "file not found: /Makefile" in out, out)
    check("an existing anchor comment passes", "anchor not found in /app.py: Stage: Load" not in out, out)
    check("an anchor whose words only remain in a string is reported", "anchor not found in /app.py: Stage: Save" in out, out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
