# /llm_harness/tests/json_atomic_test.py
"""Atomic-state test for llm_harness: a state file written by one chat is never seen empty or half-written by another chat reading it at the same moment."""
import importlib.util, os, sys, tempfile, threading, time

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out)


def main():
    spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS)
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    path = os.path.join(tempfile.mkdtemp(prefix="harness-atomic-"), "sessions.json")
    big = dict(("session%d" % i, {"aim": "an aim that is long enough to make the file big " * 4, "n": i}) for i in range(400))
    hh.save_json(path, big)
    stop, bad = threading.Event(), []

    def reader():
        while not stop.is_set():
            got = hh.load_json(path, None)
            time.sleep(0.001)
            if got is None or len(got) != len(big):
                bad.append(None if got is None else len(got))

    t = threading.Thread(target=reader)
    t.start()
    try:
        for i in range(300):
            hh.save_json(path, big)
    finally:
        stop.set()
        t.join()
    check("a reader never sees a state file empty or half-written while it is being saved", not bad, "%d bad reads, e.g. %s" % (len(bad), bad[:5]))
    left = [n for n in os.listdir(os.path.dirname(path)) if n.endswith(".tmp")]
    check("no temp files are left behind", not left, str(left))
    other = os.path.join(os.path.dirname(path), "state.json")
    real_replace, real_sleep = os.replace, time.sleep

    def refuse(src, dst):
        raise PermissionError("[WinError 5] Access is denied (a reader holds the file)")

    os.replace, time.sleep = refuse, (lambda s: None)
    try:
        hh.save_json(other, {"k": "v"})
        failed = None
    except Exception as e:
        failed = e
    finally:
        os.replace, time.sleep = real_replace, real_sleep
    check("when the replace keeps being refused, the data is still written and nothing is left behind", failed is None and hh.load_json(other, None) == {"k": "v"} and not [n for n in os.listdir(os.path.dirname(path)) if n.endswith(".tmp")], str(failed))
    flaky = os.path.join(os.path.dirname(path), "flaky.json")
    hh.save_json(flaky, {"ok": 1})
    real_open, calls = open, [0]

    def sometimes_denied(p, *a, **k):
        calls[0] += 1
        if calls[0] <= 2:
            raise PermissionError("[WinError 32] The process cannot access the file because it is being used by another process")
        return real_open(p, *a, **k)

    hh.open = sometimes_denied
    try:
        got = hh.load_json(flaky, None)
    finally:
        del hh.open
    check("a read refused for a moment is retried, not taken as 'no file'", got == {"ok": 1}, str(got))
    check("a file that really is missing still gives the default at once", hh.load_json(os.path.join(os.path.dirname(path), "missing.json"), "none") == "none")
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
