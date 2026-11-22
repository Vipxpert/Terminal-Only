# /llm_harness/tests/replay_footer_test.py
"""Replay test for llm_harness: re-pasting a script replays the execution output it saved, but the footer is live: the goal, the notes and the other sessions' scopes are the latest, not the ones from the original run."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def run(ws, *lines):
    text = "\n".join(["@SCRIPT [C: replay]", "@WORKSPACE " + ws] + list(lines)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def main():
    ws = tempfile.mkdtemp(prefix="harness-replay-")
    with open(os.path.join(ws, "a.txt"), "w", newline="\n") as f:
        f.write("x\n")
    alpha = ("@SESSION alpha | alpha work", "@LIST_DIR /")
    first = run(ws, *alpha)
    with open(os.path.join(ws, "b2.txt"), "w", newline="\n") as f:
        f.write("y\n")
    run(ws, "@SESSION beta | beta work", "@SCOPE beta aim | b.txt", "@GOAL The latest goal", "@NOTE_ADD A fresh note made after the first run", "@MESSAGE alpha | hello from beta after the first run")
    again = run(ws, *alpha)
    check("the first run lists a.txt and knows nothing of what came later", "a.txt" in first and "The latest goal" not in first and "fresh note" not in first, first)
    check("the replay keeps the saved execution output (the folder as it was, without b2.txt)", "a.txt" in again and "b2.txt" not in again, again)
    check("the replay's footer shows the latest goal", "The latest goal" in again, again)
    check("the replay's footer shows a note added since the original run", "A fresh note made after the first run" in again, again)
    check("the replay's footer lists another session's scope set since", "beta" in again and "b.txt" in again, [l[:200] for l in again.split("\n") if "SESSION" in l or "beta" in l or "[REPLAY]" in l or l.startswith("[L1-Commands]")])
    check("control: a normal run's footer names the session and lists the chat's own unused commands", "=== THIS SESSION: alpha" in first and "not used yet in this chat" in first, [l[:200] for l in first.split("\n") if "SESSION" in l or l.startswith("[L1-Commands]")])
    check("the replay's footer names this chat's own session", "=== THIS SESSION: alpha" in again, [l[:200] for l in again.split("\n") if "SESSION" in l])
    check("the replay's command list is this chat's own, not the full list", "not used yet in this chat" in again, [l[:160] for l in again.split("\n") if l.startswith("[L1-Commands]")])
    third = run(ws, *alpha)
    check("the replay delivers a message sent since the original run", "hello from beta after the first run" in again, [l[:200] for l in again.split("\n") if "MESSAGE" in l or "hello" in l])
    check("a second replay still shows it, since nothing has confirmed it was read", "hello from beta after the first run" in third, [l[:200] for l in third.split("\n") if "MESSAGE" in l or "hello" in l])
    fourth = run(ws, "@SESSION alpha | alpha work", "@LIST_DIR /", "@LIST_DIR /")
    fifth = run(ws, "@SESSION alpha | alpha work", "@LIST_DIR /", "@LIST_DIR /", "@LIST_DIR /")
    check("the chat's next numbered script still carries it, since only a numbered script's output counts as read", "hello from beta after the first run" in fourth, [l[:200] for l in fourth.split("\n") if "MESSAGE" in l or "hello" in l])
    check("the numbered script after that does not repeat it", "hello from beta after the first run" not in fifth, [l[:200] for l in fifth.split("\n") if "MESSAGE" in l or "hello" in l])
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
