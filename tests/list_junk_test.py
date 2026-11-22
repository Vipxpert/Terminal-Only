# /llm_harness/tests/list_junk_test.py
"""Listing test for llm_harness: @LIST_DIR and @LIST_RECURSIVE count, instead of listing, what .gitignore excludes and binary or media files, '| all' lists them, and a project without git hides binary files too."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []
COUNT = [0]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def git(ws, *args):
    subprocess.run(["git"] + list(args), cwd=ws, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def write(ws, rel, text="x\n"):
    path = os.path.join(ws, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="\n") as f:
        f.write(text)


def run(ws, *lines):
    COUNT[0] += 1
    text = "\n".join(["@SCRIPT [C: list %d]" % COUNT[0], "@WORKSPACE " + ws] + list(lines)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "").split("=== L1 CONTRACT")[0]


def main():
    ws = tempfile.mkdtemp(prefix="harness-listjunk-")
    git(ws, "init", "-q")
    git(ws, "checkout", "-q", "-b", "main")
    git(ws, "config", "user.email", "t@example.com")
    git(ws, "config", "user.name", "T")
    write(ws, ".gitignore", "logs/\n*.tmp\n")
    for rel in ("a.py", "sub/c.py", "img.png", "data.parquet", "logs/x.log", "b.tmp"):
        write(ws, rel)
    git(ws, "add", "-A")
    git(ws, "commit", "-q", "-m", "init")
    rec = run(ws, "@LIST_RECURSIVE /")
    check("a recursive listing shows the code and counts binary and media files instead", "a.py" in rec and "sub/c.py" in rec and "img.png" not in rec and "data.parquet" not in rec and "b.tmp" not in rec and "2 hidden" in rec, rec)
    top = run(ws, "@LIST_DIR /")
    check("a folder listing counts what .gitignore excludes and binary files", "a.py" in top and "sub/" in top and "b.tmp" not in top and "logs/" not in top and "img.png" not in top and "4 hidden" in top, top)
    full = run(ws, "@LIST_DIR / | all")
    check("| all lists everything", "b.tmp" in full and "img.png" in full and "logs/" in full and "hidden," not in full, full)
    plain = tempfile.mkdtemp(prefix="harness-listjunk-plain-")
    write(plain, "a.py")
    write(plain, "img.png")
    nongit = run(plain, "@LIST_RECURSIVE /")
    check("without git, binary and media files are counted too", "a.py" in nongit and "img.png" not in nongit and "1 hidden" in nongit, nongit)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
