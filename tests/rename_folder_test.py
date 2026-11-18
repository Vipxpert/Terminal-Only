# /llm_harness/tests/rename_folder_test.py
"""Folder-rename test for llm_harness: @RENAME on a folder moves it file by file through the journal (binary files included), @UNDO brings it back, text replacements and claims apply per file, and unsafe moves are refused whole."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-renamefolder-")
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


def get(rel):
    with open(os.path.join(WS, rel), "rb") as f:
        return f.read()


def exists(rel):
    return os.path.exists(os.path.join(WS, rel))


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-800:].replace("\n", "\n    "))


def main():
    proj = os.path.basename(WS)
    put("workers/discord/bot.py", ("# /%s/workers/discord/bot.py\nimport utils_x\n" % proj).encode())
    put("workers/discord/data/blob.bin", bytes(range(256)))
    put("workers/discord/sub/deep.txt", b"deep\n")
    out = run(None, "@RENAME /workers/discord -> /apps/discord",
              "@TEXT_REPLACE /apps/discord/bot.py | expect 1 | imports follow the move",
              "--- [OLD TEXT] ---", "import utils_x", "+++ [NEW TEXT] +++", "import utils_y", "=== [END TEXT] ===")
    check("a folder moves with all its files, binary included, and later edits find them", not exists("workers/discord") and get("apps/discord/data/blob.bin") == bytes(range(256)) and b"import utils_y" in get("apps/discord/bot.py") and exists("apps/discord/sub/deep.txt"), out)
    check("the emptied source folders are gone and the line-1 headers follow the move", not exists("workers") or not os.listdir(os.path.join(WS, "workers")), out)
    check("a moved file's line-1 header names its new path", get("apps/discord/bot.py").startswith(("# /%s/apps/discord/bot.py" % proj).encode()), out)
    num = STEP[0]
    out = run(None, "@UNDO %d" % num)
    check("@UNDO brings the whole folder back where it was", get("workers/discord/data/blob.bin") == bytes(range(256)) and b"import utils_x" in get("workers/discord/bot.py") and not exists("apps/discord/bot.py"), out)
    put("apps/discord/keep.txt", b"already here\n")
    out = run(None, "@RENAME /workers/discord -> /apps/discord")
    check("a destination that already exists is refused whole", "folder rename refused" in out and "already exists and is not empty" in out and exists("workers/discord/bot.py"), out)
    out = run(None, "@RENAME /workers/discord -> /workers/discord/inner")
    check("moving a folder into itself is refused", "into itself" in out and exists("workers/discord/bot.py"), out)
    out = run(None, "@RENAME /workers/discord -> /workers/Discord")
    check("a case-only rename is refused with the way around it", "only change the case" in out, out)
    put("raw/odd.dat", b"no newline at the end\r\n\n\n")
    put("raw/pic.png", bytes(range(255, -1, -1)))
    out = run(None, "@RENAME /raw/odd.dat -> /raw/odd2.dat", "@RENAME /raw/pic.png -> /raw/pic2.png")
    check("renaming single files keeps their exact bytes, binary or odd line endings", get("raw/odd2.dat") == b"no newline at the end\r\n\n\n" and get("raw/pic2.png") == bytes(range(255, -1, -1)), out)
    put("pkg/a.py", b"a = 1\n")
    put("pkg/b.py", b"b = 1\n")
    run("alpha | owns a", "@SCOPE a | pkg/a.py")
    out = run("beta | moves pkg", "@SCOPE b | pkg/b.py, pkg2/b.py", "@RENAME /pkg -> /pkg2")
    check("claims apply file by file: another chat's file stays, the rest moves", exists("pkg/a.py") and exists("pkg2/b.py") and "inside session alpha's scope" in out, out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
