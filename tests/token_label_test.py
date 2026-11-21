# /llm_harness/tests/token_label_test.py
"""Token-label test for llm_harness: the placeholder account name Credential Manager gives token sign-ins ('Personal Access Token') is never used to label token usage; real account names pass through."""
import importlib.util, os, sys

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out))


def main():
    spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS)
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    check("the placeholder alone leaves no usable account", hh.usable_accounts(["Personal Access Token"]) == [], hh.usable_accounts(["Personal Access Token"]))
    check("real accounts pass through, next to the placeholder or alone", hh.usable_accounts(["Personal Access Token", "bob"]) == ["bob"] and hh.usable_accounts(["alice", "bob"]) == ["alice", "bob"])
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
