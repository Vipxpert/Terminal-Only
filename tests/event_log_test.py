# /llm_harness/tests/event_log_test.py
"""Event-log test for llm_harness: the shared event log keeps the newest 200 events and also any event addressed to a session that has not read it yet, so a message for a chat that stays idle while others work is not trimmed away; once the chat has read it, or when it is addressed to nobody, it is trimmed like the rest."""
import importlib.util, os, sys, tempfile, time

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-700:].replace("\n", "\n    "))


def main():
    spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS)
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    err = hh.enter_workspace(tempfile.mkdtemp(prefix="harness-events-"))
    os.makedirs(hh.HARNESS_DIR, exist_ok=True)

    def sessions(**seen):
        hh.save_json(hh.sessions_path(), {name: {"seen_seq": n, "last_active": time.time()} for name, n in seen.items()})

    def log():
        return hh.load_json(hh.events_path(), {})

    with hh.state_lock():
        sessions(alpha=0)
        hh.log_event({"session": "beta", "kind": "message", "to": "alpha", "text": "keep me"})
        hh.log_event({"session": "beta", "kind": "message", "to": "nobody", "text": "to nobody"})
        for i in range(250):
            hh.log_event({"session": "beta", "kind": "scope", "text": "noise %d" % i})
    events = log()["events"]
    texts = [e.get("text") for e in events]
    check("an unread message survives 250 newer events", not err and "keep me" in texts, (err, len(texts)))
    check("a message to a session that does not exist is trimmed like the rest", "to nobody" not in texts, len(texts))
    check("the log stays bounded: the newest 200 plus the one unread message", len(texts) == 201, len(texts))
    with hh.state_lock():
        sessions(alpha=log()["seq"])
        hh.log_event({"session": "beta", "kind": "scope", "text": "one more"})
    texts = [e.get("text") for e in log()["events"]]
    check("once the chat has read it, it is trimmed like the rest", "keep me" not in texts and len(texts) == 200, len(texts))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
