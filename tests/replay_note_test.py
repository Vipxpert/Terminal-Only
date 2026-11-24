# /llm_harness/tests/replay_note_test.py
"""Replay-note test: pasting the same script twice gives a replay that explains itself to the AI (the same paste arrived twice, nothing ran, and what to do if the output was already answered or is new)."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")


def main():
    ws = tempfile.mkdtemp(prefix="harness-replay-")
    text = ("@SCRIPT [C: replay note]\n@WORKSPACE %s\n@SESSION alpha | alpha work\n@LIST_DIR /\n" % ws).encode("utf-8")
    run = lambda: subprocess.run([sys.executable, HARNESS], input=text, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120).stdout.decode("utf-8", "replace")
    run()
    out = run()
    ok = "[REPLAY]" in out and "the same paste arrived twice" in out and "if you already answered this script" in out
    print("%s a repeated paste explains the replay to the AI" % ("PASS" if ok else "FAIL"))
    if not ok:
        print("    ..." + out[:900].replace("\n", "\n    "))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
