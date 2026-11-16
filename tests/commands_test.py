# /llm_harness/tests/commands_test.py
"""Command-list test for llm_harness: the footer lists the commands this chat has not used yet, every chat keeps its own record, and @HELP COMMANDS still gives the full list."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-commands-")
RESULTS = []
STEP = [0]


def run(session, *lines):
    STEP[0] += 1
    head = ["@SCRIPT [P: step %d]" % STEP[0]] + (["@SESSION " + session] if session else []) + ["@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def commands_line(out):
    return ([l for l in out.splitlines() if l.startswith("[L1-Commands]")] or [""])[-1]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-700:].replace("\n", "\n    "))


def main():
    with open(os.path.join(WS, "a.txt"), "w") as f:
        f.write("some text here\n")
    out = run(None, "@GREP some text")
    line = commands_line(out)
    check("without a session the footer lists every command", line.startswith("[L1-Commands] @SCRIPT @WORKSPACE") and "@GREP" in line, line)
    out = run("alpha | look around", "@GREP some text")
    line = commands_line(out)
    check("a chat's footer lists only the commands it has not used yet", "not used yet in this chat:" in line and " @GREP " not in line + " " and "@SCRIPT" not in line and "@VERDICT" in line, line)
    out = run("alpha | look around", "@FIND a.txt")
    line = commands_line(out)
    check("each script's commands drop out of that chat's list", "@FIND" not in line and " @GREP " not in line + " ", line)
    out = run("beta | other work", "@LIST_DIR /")
    line = commands_line(out)
    check("another chat keeps its own record", "@GREP" in line and "@FIND" in line and "@LIST_DIR" not in line, line)
    out = run("alpha | look around", "@HELP COMMANDS")
    check("@HELP COMMANDS prints the full list", "=== HELP: all commands ===" in out and "@CAMPAIGN_END" in out.split("=== HELP: all commands ===")[1].split("===")[0], out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
