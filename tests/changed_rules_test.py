# /llm_harness/tests/changed_rules_test.py
"""Changed-rule test for llm_harness: a standing rule that changed since a chat last saw it is marked [CHANGED] once in that chat's footer; new chats and runs without a session see no marks."""
import os, re, shutil, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-rules-")
INSTALL = tempfile.mkdtemp(prefix="harness-rules-install-")
RESULTS = []
STEP = [0]


def run(session):
    STEP[0] += 1
    head = ["@SCRIPT [P: step %d]" % STEP[0]] + (["@SESSION " + session] if session else []) + ["@WORKSPACE " + WS, "@GREP nothing"]
    p = subprocess.run([sys.executable, os.path.join(INSTALL, "harness.py")], input="\n".join(head + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-900:].replace("\n", "\n    "))


def main():
    shutil.copy(HARNESS, os.path.join(INSTALL, "harness.py"))
    rules = os.path.join(INSTALL, "workflow_commands.txt")
    with open(rules, "w", encoding="utf-8") as f:
        f.write("- **L1 Rule — `[L1-Alpha]`:** `first wording of alpha`\n- **L1 Rule — `[L1-Beta]`:** `beta stays the same`\n")
    out = run("alpha | a")
    check("a chat's first footer has no marks", "[L1-Alpha] first wording of alpha" in out and "[CHANGED]" not in out, out)
    with open(rules, "w", encoding="utf-8") as f:
        f.write("- **L1 Rule — `[L1-Alpha]`:** `second wording of alpha`\n- **L1 Rule — `[L1-Beta]`:** `beta stays the same`\n")
    out = run("alpha | a")
    check("a rule that changed is marked [CHANGED], the unchanged one is not", "[CHANGED] [L1-Alpha] second wording of alpha" in out and "[CHANGED] [L1-Beta]" not in out, out)
    out = run("alpha | a")
    check("the mark appears only once", "[CHANGED]" not in out, out)
    out = run("beta | b")
    check("a new chat sees no marks", "[CHANGED]" not in out, out)
    out = run(None)
    check("a run without a session sees no marks", "[CHANGED]" not in out and "[L1-Alpha]" in out, out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
