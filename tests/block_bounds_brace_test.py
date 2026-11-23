# /llm_harness/tests/block_bounds_brace_test.py
"""Brace-scope test for llm_harness: block_bounds keeps a brace-language definition together when a line at the definition's own indent continues its header (a C# where clause) or sits inside its body (a C label), instead of ending the block there."""
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
    cs = ["class A", "{", "    public void Foo<T>(int a)", "    where T : class", "    {", "        x();", "    }", "", "    public void Bar()", "    {", "    }", "}"]
    got = hh.block_bounds(cs, 2, False)
    check("a C# method with a where clause at its own indent ends at its closing brace", got[1] == 7, (got, cs[got[0]:got[1]]))
    c = ["int main()", "{", "    goto cleanup;", "cleanup:", "    return 0;", "}"]
    got = hh.block_bounds(c, 0, False)
    check("a C function with a label at column 0 ends at its closing brace", got[1] == 6, (got, c[got[0]:got[1]]))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
