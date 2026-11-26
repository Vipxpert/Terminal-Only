# /llm_harness/tests/msg_persist_test.py
"""Verify unacknowledged messages persist across stacked prompts and [REPLAY] until @MSG_ACK."""
import os
import re
import subprocess
import sys
import tempfile

HARNESS = os.path.abspath("harness.py")


def run_script(ws, session, title, body):
    script = "@SCRIPT [P: %s]\n@SESSION %s | test msg persist\n@WORKSPACE %s\n%s\n" % (title, session, ws, body)
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
        run_script(ws, "receiver", "init receiver", "@LIST_DIR /")
        send_out = run_script(ws, "sender", "send msg", "@MESSAGE receiver | Please keep this visible")
        m = re.search(r"\b(M-\d+)\b", send_out)
        mid = m.group(1) if m else ""
        check("message id assigned", bool(mid), send_out)

        t1 = run_script(ws, "receiver", "turn 1", "@LIST_DIR /")
        check("turn 1 shows pending message", mid in t1 and "Please keep this visible" in t1, t1)

        t2 = run_script(ws, "receiver", "turn 2 stacked", "@LIST_DIR /")
        check("stacked turn 2 still shows unacknowledged message", mid in t2 and "Please keep this visible" in t2, t2)

        rep = run_script(ws, "receiver", "turn 2 stacked", "@LIST_DIR /")
        check("replay of turn 2 still shows unacknowledged message", "[REPLAY]" in rep and mid in rep and "Please keep this visible" in rep, rep)

        ack_out = run_script(ws, "receiver", "ack msg", "@MSG_ACK %s | ack" % mid)
        check("after @MSG_ACK message no longer repeats in footer", "[MSG_ACK] %s -> ack" % mid in ack_out and "Please keep this visible" not in ack_out, ack_out)


if __name__ == "__main__":
    main()
