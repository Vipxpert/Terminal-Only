# /llm_harness/tests/kb_handshake_test.py
"""Verify fresh-chat @KB handshake cue and observed/variables output."""
import os
import subprocess
import sys
import tempfile

HARNESS = os.path.abspath("harness.py")


def run_script(ws, session, title, body):
    script = "@SCRIPT [P: %s]\n@SESSION %s | test kb handshake\n@WORKSPACE %s\n%s\n" % (title, session, ws, body)
    p = subprocess.run([sys.executable, HARNESS], input=script, text=True, capture_output=True, encoding="utf-8")
    return p.stdout + p.stderr


def check(name, ok, out=""):
    if ok:
        print("PASS %s" % name)
    else:
        print("FAIL %s\n%s" % (name, out[-600:]))
        sys.exit(1)


def main():
    with tempfile.TemporaryDirectory() as ws:
        t1 = run_script(ws, "fresh-chat", "turn 1", "@LIST_DIR /")
        check(
            "fresh chat prints @KB handshake cue on Turn 1",
            "[KNOWLEDGE] pitfalls on file" in t1 and "fresh-chat handshake: search relevant @KB" in t1 and "pin key findings to this session" in t1,
            t1,
        )
        t2 = run_script(ws, "fresh-chat", "turn 2", "@LIST_DIR /")
        check("Turn 2 does not repeat [KNOWLEDGE] hint when active techs unchanged", "[KNOWLEDGE] pitfalls on file" not in t2, t2)

        kb = run_script(ws, "fresh-chat", "kb search", "@KB compactor")
        check("@KB compactor prints observed and variables confidence fields", "observed:" in kb and "variables:" in kb, kb)


if __name__ == "__main__":
    main()
