# /llm_harness/tests/undo_multi_test.py
"""Multi-undo test for llm_harness: several @UNDO lines in one script all run, paths may be comma-separated or globs, and '/old -> /new' (or '-> /folder/') copies a file as it was before the script to another path."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-undomulti-")
RESULTS = []
STEP = [0]


def run(*lines):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0], "@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def put(rel, data):
    path = os.path.join(WS, rel)
    os.makedirs(os.path.dirname(path) or WS, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def get(rel):
    with open(os.path.join(WS, rel), "rb") as f:
        return f.read()


def exists(rel):
    return os.path.exists(os.path.join(WS, rel))


def delete_all():
    out = run("@DELETE_FILE /y1.csv", "@DELETE_FILE /y2.csv", "@DELETE_FILE /y3.csv", "@DELETE_FILE /y4.txt")
    return STEP[0], out


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-800:].replace("\n", "\n    "))


def main():
    data = dict((n, ("content of %s\n" % n).encode()) for n in ("y1.csv", "y2.csv", "y3.csv", "y4.txt"))
    for n, d in data.items():
        put(n, d)
    num, _ = delete_all()
    out = run("@UNDO %d | /y1.csv" % num, "@UNDO %d | /y2.csv" % num)
    check("two @UNDO lines in one script both run", get("y1.csv") == data["y1.csv"] and get("y2.csv") == data["y2.csv"] and not exists("y3.csv"), out)
    out = run("@UNDO %d | /y3.csv, /y4.txt" % num)
    check("comma-separated paths restore several files", exists("y3.csv") and exists("y4.txt"), out)
    for n in data:
        os.remove(os.path.join(WS, n))
    for n, d in data.items():
        put(n, d)
    num2, _ = delete_all()
    out = run("@UNDO %d | /y*.csv" % num2)
    check("a glob restores every match and nothing else", exists("y1.csv") and exists("y2.csv") and exists("y3.csv") and not exists("y4.txt"), out)
    for n in data:
        if exists(n):
            os.remove(os.path.join(WS, n))
    for n, d in data.items():
        put(n, d)
    num3, _ = delete_all()
    out = run("@UNDO %d | /y1.csv -> /docs/personal/mine.csv" % num3)
    check("'/old -> /new' copies the file as it was to another path and leaves the old path alone", get("docs/personal/mine.csv") == data["y1.csv"] and not exists("y1.csv") and "[RECOVERED]" in out, out)
    out = run("@UNDO %d | /y*.csv -> /docs/archive/" % num3)
    check("a destination folder takes each file's own name", get("docs/archive/y2.csv") == data["y2.csv"] and get("docs/archive/y3.csv") == data["y3.csv"] and get("docs/archive/y1.csv") == data["y1.csv"], out)
    out = run("@UNDO %d | /y2.csv -> /docs/archive/y2.csv" % num3)
    check("recovery never overwrites an existing file", "[RECOVER SKIPPED]" in out and "already exists" in out, out)
    out = run("@UNDO %d | /nothing_here.csv" % num3)
    check("a path that was not in the script says so", "no journaled scripts in range" in out and "/nothing_here.csv" in out, out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
