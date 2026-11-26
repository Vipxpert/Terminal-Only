# /llm_harness/tests/message_flows_test.py
"""Message-flow test for llm_harness: a message one chat sends another must reach that chat's AI. These scenarios look for ways it could be lost: the run that delivered it never reached the chat and the same script is pasted again, and the recipient's session was merged into another before delivery; a message to a session that does not exist must at least be refused to the sender."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []
MSG = "ping from beta about the display file"


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def run(ws, title, *lines):
    text = "\n".join(["@SCRIPT [C: %s]" % title, "@WORKSPACE " + ws] + list(lines)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def merge(ws, src, dst):
    p = subprocess.run([sys.executable, HARNESS, "--workspace", ws, "--merge", src, dst], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def about(out):
    return [l[:200] for l in out.split("\n") if "MESSAGE" in l or "ping from beta" in l or "REPLAY" in l or "NOT SENT" in l or "MERGED" in l]


def main():
    ws = tempfile.mkdtemp(prefix="harness-msgflow-")
    run(ws, "alpha one", "@SESSION alpha | alpha work", "@LIST_DIR /")
    run(ws, "beta send", "@SESSION beta | beta work", "@MESSAGE alpha | " + MSG)
    delivered = run(ws, "alpha two", "@SESSION alpha | alpha work", "@LIST_DIR /")
    check("control: a message reaches the recipient's next run", MSG in delivered, about(delivered))
    again = run(ws, "alpha two", "@SESSION alpha | alpha work", "@LIST_DIR /")
    check("the same script pasted again because its output never reached the chat shows the message again", MSG in again, about(again))
    later = run(ws, "alpha three", "@SESSION alpha | alpha work", "@MSG_ACK M-001", "@LIST_DIR /")
    check("after @MSG_ACK the message does not repeat", MSG not in later, about(later))
    ws2 = tempfile.mkdtemp(prefix="harness-msgmerge-")
    run(ws2, "alpha one", "@SESSION alpha | alpha work", "@LIST_DIR /")
    run(ws2, "gamma one", "@SESSION gamma | gamma work", "@LIST_DIR /")
    run(ws2, "beta send", "@SESSION beta | beta work", "@MESSAGE alpha | " + MSG)
    merged = merge(ws2, "alpha", "gamma")
    after = run(ws2, "gamma two", "@SESSION gamma | gamma work", "@LIST_DIR /")
    check("a message sent to a session that was merged into another reaches the other one", MSG in after, about(merged) + about(after))
    sent = run(ws2, "beta wrong", "@SESSION beta | beta work", "@MESSAGE nobody | " + MSG)
    check("a message to a session that does not exist is refused to the sender", "NOT SENT" in sent, about(sent))
    ws3 = tempfile.mkdtemp(prefix="harness-msgside-")
    run(ws3, "alpha one", "@SESSION alpha | alpha work", "@LIST_DIR /")
    run(ws3, "beta send", "@SESSION beta | beta work", "@MESSAGE alpha | " + MSG)
    side = run(ws3, "side look", "@SIDE", "@SESSION alpha | alpha work", "@LIST_DIR /")
    numbered = run(ws3, "alpha two", "@SESSION alpha | alpha work", "@LIST_DIR /")
    check("a side script of the same chat shows the message without using it up: the numbered chat still gets it", MSG in side and MSG in numbered, about(side) + about(numbered))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
