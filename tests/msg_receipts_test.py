# /llm_harness/tests/msg_receipts_test.py
"""Message receipts, broadcast *, auto-shell @WAIT_MSG, and manual @PING test for llm_harness."""
import os, re, subprocess, sys, tempfile, threading, time

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []
COUNT = [0]
AGENT = dict(os.environ, LLM_HARNESS_AGENT="test-host", LLM_HARNESS_HOST_SESSION="h1")
CHAT = {k: v for k, v in os.environ.items() if k != "LLM_HARNESS_AGENT"}


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def run(ws, session, env, *lines):
    COUNT[0] += 1
    text = "\n".join(["@SCRIPT [P: msg %d]" % COUNT[0], "@WORKSPACE " + ws, "@SESSION %s | %s work" % (session, session)] + list(lines)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120, env=env)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def main():
    ws = tempfile.mkdtemp(prefix="harness-msgrec-")
    run(ws, "alpha", CHAT, "@LIST_DIR /")
    run(ws, "beta", CHAT, "@LIST_DIR /")
    run(ws, "gamma", CHAT, "@LIST_DIR /")

    sent = run(ws, "alpha", CHAT, "@MESSAGE beta | please review")
    m = re.search(r"\[M-\d+\]", sent)
    mid = m.group(0).strip("[]") if m else ""
    check("@MESSAGE assigns a stable M-### ID", bool(mid) and "[SENT] message [%s] to beta: please review" % mid in sent, sent)

    deliv = run(ws, "beta", CHAT, "@LIST_DIR /")
    check("recipient sees [M-###] message and marks it delivered", ("[%s] message from alpha: please review" % mid) in deliv, deliv)

    ack = run(ws, "beta", CHAT, "@MSG_ACK %s | accept | on it" % mid)
    check("@MSG_ACK transitions state to accepted with note", "[MSG_ACK] %s -> accepted (by beta): on it" % mid in ack, ack)

    ping = run(ws, "alpha", CHAT, "@REPEATABLE", "@PING")
    check("@PING shows sent receipt and suppresses L1 footer", ("[%s]" % mid) in ping and "beta=accepted(on it)" in ping and "=== L1 CONTRACT" not in ping, ping)

    bcast = run(ws, "alpha", CHAT, "@MESSAGE * | sync up")
    bm = re.search(r"broadcast \[(M-\d+)\]", bcast)
    bmid = bm.group(1) if bm else ""
    check("@MESSAGE * broadcasts to beta and gamma", bool(bmid) and "beta, gamma" in bcast, bcast)

    def ack_later():
        time.sleep(0.4)
        run(ws, "beta", CHAT, "@MSG_ACK %s | done | beta ok" % bmid)
        run(ws, "gamma", CHAT, "@MSG_ACK %s | done | gamma ok" % bmid)

    t = threading.Thread(target=ack_later)
    t.start()
    waited = run(ws, "alpha", CHAT, "@WAIT_MSG %s | done | 5" % bmid)
    t.join()
    check("chat-mode @WAIT_MSG blocks until both broadcast recipients reach done", "[WAIT_MSG] reached" in waited and "beta: completed (beta ok)" in waited and "gamma: completed (gamma ok)" in waited, waited)

    def reply_later():
        time.sleep(0.35)
        run(ws, "beta", CHAT, "@MESSAGE alpha | answer from beta")

    t2 = threading.Thread(target=reply_later)
    t2.start()
    sw = run(ws, "alpha", CHAT, "@MESSAGE beta | quick question", "@WAIT_MSG last | done | 4")
    t2.join()
    check("same-turn @MESSAGE + @WAIT_MSG last wakes on reply and delivers it", "[REPLY]" in sw and "answer from beta" in sw and "[WAIT_MSG] reached" in sw, sw)

    to_out = run(ws, "alpha", CHAT, "@MESSAGE beta | hang test", "@WAIT_MSG last | done | 0.2")
    hm = re.search(r"\[(M-\d+)\]", to_out)
    hmid = hm.group(1) if hm else ""
    check("timed-out @WAIT_MSG persists waiting_msg on session", bool(hmid) and "WAITING_MSG" in to_out, to_out)

    locked = run(ws, "alpha", dict(CHAT, LLM_HARNESS_WAIT_BREAK_CMD="BREAK M-999"), "@LIST_DIR /")
    check("wrong BREAK ID keeps session locked in WAITING_MSG", "[WAIT_LOCKED]" in locked and "WAITING_MSG" in locked, locked)

    broken = run(ws, "alpha", dict(CHAT, LLM_HARNESS_WAIT_BREAK_CMD="BREAK %s" % hmid), "@LIST_DIR /")
    check("exact BREAK <id> clears persisted wait and reports [WAIT_BROKEN] to the AI", "[WAIT_BROKEN]" in broken and hmid in broken and "WAITING_MSG" not in broken, broken)

    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
