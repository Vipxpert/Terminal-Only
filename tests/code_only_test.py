# /llm_harness/tests/code_only_test.py
"""code_only test for llm_harness: strings and comments are stripped from a line, including strings with escaped quotes, backtick strings and one-line block comments, so a name or a URL inside them is not read as code and a // inside a string does not hide the code after it."""
import importlib.util, os, sys

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-600:].replace("\n", "\n    "))


def main():
    spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS)
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    a = hh.code_only('a("say \\"hi\\" //x") + b')
    check("an escaped quote does not end the string early", "hi" not in a and "a(" in a and a.rstrip().endswith("b"), a)
    b = hh.code_only("f(`http://example.com`) + g")
    check("a backtick string with // inside is stripped whole and the code after it stays", "example" not in b and b.rstrip().endswith("g"), b)
    c = hh.code_only("x = 1; /* note */ y = 2 // tail")
    check("a one-line block comment and a line comment are stripped, the code between stays", "note" not in c and "tail" not in c and "x = 1;" in c and "y = 2" in c, c)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
