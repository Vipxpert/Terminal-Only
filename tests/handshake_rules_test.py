# /llm_harness/tests/handshake_rules_test.py
"""Handshake test for llm_harness: the handshake prints the whole workflow_commands.txt once, so one paste starts a chat, and an ordinary script run does not print it."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def main():
    ws = tempfile.mkdtemp(prefix="harness-handshake-")
    p = subprocess.run([sys.executable, HARNESS, "--workspace", ws], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    out = p.stdout.decode("utf-8", "replace").replace("\r", "")
    check("the handshake prints the whole rules file once", out.count("=== WORKFLOW AND RULES") == 1 and "[L1-Harness]" in out and "[L1-Notes]" in out, out)
    text = "@SCRIPT [C: plain]\n@WORKSPACE %s\n@LIST_DIR /\n" % ws
    q = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    run_out = q.stdout.decode("utf-8", "replace").replace("\r", "")
    check("an ordinary script run does not print the rules file", "=== WORKFLOW AND RULES" not in run_out and "L1 CONTRACT" in run_out, run_out)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
