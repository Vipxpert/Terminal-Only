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
    out = run("@DELETE_FILE /y1.sql", "@DELETE_FILE /y2.sql", "@DELETE_FILE /y3.sql", "@DELETE_FILE /y4.txt")
    return STEP[0], out


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-800:].replace("\n", "\n    "))


def main():
    data = dict((n, ("content of %s\n" % n).encode()) for n in ("y1.sql", "y2.sql", "y3.sql", "y4.txt"))
    for n, d in data.items():
        put(n, d)
    num, _ = delete_all()
    out = run("@UNDO %d | /y1.sql" % num, "@UNDO %d | /y2.sql" % num)
    check("two @UNDO lines in one script both run", get("y1.sql") == data["y1.sql"] and get("y2.sql") == data["y2.sql"] and not exists("y3.sql"), out)
    out = run("@UNDO %d | /y3.sql, /y4.txt" % num)
    check("comma-separated paths restore several files", exists("y3.sql") and exists("y4.txt"), out)
    for n in data:
        os.remove(os.path.join(WS, n))
    for n, d in data.items():
        put(n, d)
    num2, _ = delete_all()
    out = run("@UNDO %d | /y*.sql" % num2)
    check("a glob restores every match and nothing else", exists("y1.sql") and exists("y2.sql") and exists("y3.sql") and not exists("y4.txt"), out)
    for n in data:
        if exists(n):
            os.remove(os.path.join(WS, n))
    for n, d in data.items():
        put(n, d)
    num3, _ = delete_all()
    out = run("@UNDO %d | /y1.sql -> /docs/personal/mine.sql" % num3)
    check("'/old -> /new' copies the file as it was to another path and leaves the old path alone", get("docs/personal/mine.sql") == data["y1.sql"] and not exists("y1.sql") and "[RECOVERED]" in out, out)
    out = run("@UNDO %d | /y*.sql -> /docs/archive/" % num3)
    check("a destination folder takes each file's own name", get("docs/archive/y2.sql") == data["y2.sql"] and get("docs/archive/y3.sql") == data["y3.sql"] and get("docs/archive/y1.sql") == data["y1.sql"], out)
    out = run("@UNDO %d | /y2.sql -> /docs/archive/y2.sql" % num3)
    check("recovery never overwrites an existing file", "[RECOVER SKIPPED]" in out and "already exists" in out, out)
    out = run("@UNDO %d | /nothing_here.sql" % num3)
    check("a path that was not in the script says so", "no journaled scripts in range" in out and "/nothing_here.sql" in out, out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
