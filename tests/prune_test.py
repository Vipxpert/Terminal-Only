# /llm_harness/tests/prune_test.py
"""Prune test for llm_harness: after a rename or delete, the folders it emptied are removed up to the workspace root (a folder holding only __pycache__ counts as empty), folders that still hold files stay, and the optional psutil lookup names what holds a folder."""
import importlib.util, os, subprocess, sys, tempfile, time

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-prune-")
RESULTS = []
STEP = [0]


def run(*lines):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0], "@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def put(rel, text="x = 1\n"):
    path = os.path.join(WS, rel)
    os.makedirs(os.path.dirname(path) or WS, exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def exists(rel):
    return os.path.exists(os.path.join(WS, rel))


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-800:].replace("\n", "\n    "))


def main():
    put("a/b/c/only.py")
    out = run("@RENAME /a/b/c/only.py -> /x/only.py")
    check("moving the last file out of a nest removes every emptied folder above it", not exists("a") and exists("x/only.py") and "[FOLDERS REMOVED] /a, /a/b, /a/b/c (emptied)" in out, out)
    put("keep/sub/one.py")
    put("keep/two.py")
    out = run("@RENAME /keep/sub/one.py -> /keep2/one.py")
    check("a folder that still holds a file stays, only the emptied one goes", exists("keep/two.py") and not exists("keep/sub") and "/keep/sub" in out and "[FOLDERS REMOVED] /keep (" not in out, out)
    put("pk/m.py")
    put("pk/__pycache__/m.cpython-312.pyc", "bytecode\n")
    out = run("@DELETE_FILE /pk/m.py")
    check("a folder holding only __pycache__ counts as empty after a delete", not exists("pk"), out)
    put("d1/d2/f.txt")
    out = run("@DELETE_FILE /d1/d2/f.txt")
    check("deleting a nested file removes the emptied folders", not exists("d1"), out)
    put("fold/sub/m.py")
    out = run("@RENAME /fold/sub -> /fold2")
    check("moving a folder removes the parent it emptied", exists("fold2/m.py") and not exists("fold"), out)
    try:
        import psutil
    except ImportError:
        psutil = None
    if psutil is None:
        print("SKIP psutil is not installed: the lookup of what holds a folder open is not checked")
    else:
        spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS)
        hh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hh)
        held = os.path.join(WS, "held")
        os.makedirs(held)
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], cwd=held)
        try:
            time.sleep(0.5)
            names = hh.lock_holders(held)
        finally:
            child.kill()
        check("a process whose working folder is inside the folder is named", any("PID %d" % child.pid in n for n in names), "holders: %s" % names)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
