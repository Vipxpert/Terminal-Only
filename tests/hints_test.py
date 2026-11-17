# /llm_harness/tests/hints_test.py
"""Hint test for llm_harness: a refusal's next step points at its stated reason, a space-separated @SCOPE gets the comma hint, and the tree reminder skips names the trees already describe."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-hints-")
RESULTS = []
STEP = [0]


def run(session, *lines):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0]] + (["@SESSION " + session] if session else []) + ["@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def hunk(path, old, new):
    return ["@FILE " + path, "@HUNK TOP | e", "--- [OLD CODE] ---"] + old + ["+++ [NEW CODE] +++"] + new + ["=== [END HUNK] ==="]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-700:].replace("\n", "\n    "))


def main():
    os.makedirs(os.path.join(WS, "docs", "trees"))
    os.makedirs(os.path.join(WS, "pkg"))
    proj = os.path.basename(WS)
    with open(os.path.join(WS, "docs", "trees", "tree_master.txt"), "w") as f:
        f.write("# /%s/docs/trees/tree_master.txt\n/%s (Root)\n\\-- m.py (Module with helper_one and the main loop)\n" % (proj, proj))
    with open(os.path.join(WS, "m.py"), "w") as f:
        f.write("# /%s/m.py\ndef main():\n    return 1\n" % proj)
    with open(os.path.join(WS, "a.txt"), "w") as f:
        f.write("some line here\n")
    out = run("alpha | try", *hunk("/a.txt", ["some line here"], ["other line here"]))
    check("a refusal's next step points at its stated reason", "outside this session's write scope" in out and "each refusal above names its reason" in out and "use a path inside the workspace, written from its root" not in out, out)
    out = run("alpha | try", "@SCOPE two files | a.txt m.py")
    check("a space-separated @SCOPE gets the comma hint and changes nothing", "separate scope paths with commas" in out and "write scope: none" in out, out)
    out = run("alpha | try", "@SCOPE folder | pkg depth 1")
    check("an entry with a depth is still accepted", "[SCOPE] alpha scope set" in out, out)
    out = run(None, *hunk("/m.py", ["def main():"], ["def helper_one():", "    return 0", "", "def main():"]))
    check("a new name the tree already describes gives no tree reminder", "TREE SYNC REMINDER" not in out, out)
    out = run(None, *hunk("/m.py", ["def main():"], ["def brand_new():", "    return 2", "", "def main():"]))
    check("a new name the tree does not mention still gives the reminder", "TREE SYNC REMINDER" in out and "+brand_new" in out, out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
