# /llm_harness/tests/delete_test.py
"""Recycle-bin test for llm_harness: @DELETE_FILE takes files, folders and globs; every deleted file goes into the script's journal and comes back with @UNDO; claims apply file by file; undo leaves files another chat now holds."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-delete-")
RESULTS = []
STEP = [0]


def run(session, *lines):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0]] + (["@SESSION " + session] if session else []) + ["@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def put(rel, data):
    path = os.path.join(WS, rel)
    os.makedirs(os.path.dirname(path) or WS, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def exists(rel):
    return os.path.exists(os.path.join(WS, rel))


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-700:].replace("\n", "\n    "))


def main():
    put("api/v1/a.py", b"x = 1\n")
    put("api/v1/endpoints/__pycache__/a.cpython-312.pyc", bytes(range(256)))
    put("keep.txt", b"keep\n")
    out = run(None, "@DELETE_FILE /api/v1")
    check("a folder is deleted file by file, each line saying how to get it back", "recoverable: @UNDO 1 | /api/v1/a.py" in out and not exists("api/v1"), out)
    out = run(None, "@UNDO 1")
    with open(os.path.join(WS, "api/v1/endpoints/__pycache__/a.cpython-312.pyc"), "rb") as f:
        restored = f.read()
    check("@UNDO brings the whole folder back, binary files included", exists("api/v1/a.py") and restored == bytes(range(256)), out)
    put("logs/one.tmp", b"1\n")
    put("logs/two.tmp", b"2\n")
    put("logs/keep.log", b"3\n")
    out = run(None, "@DELETE_FILE /logs/*.tmp")
    check("a glob deletes only what it matches", not exists("logs/one.tmp") and not exists("logs/two.tmp") and exists("logs/keep.log"), out)
    out = run(None, "@DELETE_FILE /logs/*.nothing")
    check("a glob that matches nothing says so", "nothing to delete" in out, out)
    put("pkg/a.py", b"a = 1\n")
    put("pkg/b.py", b"b = 1\n")
    run("alpha | owns a", "@SCOPE a | pkg/a.py")
    out = run("beta | owns b", "@SCOPE b | pkg/b.py", "@DELETE_FILE /pkg")
    check("claims apply file by file: another chat's file stays", exists("pkg/a.py") and not exists("pkg/b.py") and "inside session alpha's scope" in out, out)
    put("y.txt", b"first\n")
    run("gamma | edits y", "@SCOPE y | y.txt", "@FILE /y.txt", "@HUNK TOP | e", "--- [OLD CODE] ---", "first", "+++ [NEW CODE] +++", "second", "=== [END HUNK] ===")
    num = STEP[0]
    run("gamma | edits y", "@SCOPE_END handover")
    run("delta | takes y", "@SCOPE y | y.txt")
    out = run("gamma | edits y", "@UNDO %d" % num)
    check("undo leaves a file that another chat now holds", "[UNDO SKIPPED] /y.txt is inside session delta's scope" in out and "second" in open(os.path.join(WS, "y.txt")).read(), out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
