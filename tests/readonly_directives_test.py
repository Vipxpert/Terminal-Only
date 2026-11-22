# /llm_harness/tests/readonly_directives_test.py
"""Read-only test for llm_harness: a script holding @TAKEOVER or @STEWARD is never treated as one that only reads (so a stale re-paste does not ask the user again) nor as one a @SIDE or @REPEATABLE script may carry, while a plain listing still is."""
import importlib.util, os, sys

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

    def parse(line):
        return hh.parse_payload("@SCRIPT [C: x]\n@SESSION alpha | alpha work\n%s\n" % line)

    take, stew, plain = parse("@TAKEOVER beta"), parse("@STEWARD on"), parse("@LIST_DIR /")
    check("@TAKEOVER is neither read-only nor side-allowed", not hh.read_only(take) and not hh.side_allowed(take), take)
    check("@STEWARD is neither read-only nor side-allowed", not hh.read_only(stew) and not hh.side_allowed(stew), stew)
    check("control: a plain listing is both", hh.read_only(plain) and hh.side_allowed(plain), plain)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
