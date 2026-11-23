# /llm_harness/tests/scope_hint_test.py
"""Scope-hint test for llm_harness: a tree node that is not found lists the names at that level (under its parent, or at the top), and a refused @SCOPE counts its free and busy paths and names the free ones."""
import importlib.util, os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def run(ws, session, *lines):
    text = "\n".join(["@SCRIPT [C: %s]" % session, "@WORKSPACE " + ws, "@SESSION %s | %s work" % (session, session)] + list(lines)) + "\n"
    return subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120).stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0]


def main():
    spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS)
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    lines = open(os.path.join("docs", "trees", "tree_master.txt"), encoding="utf-8").read().split("\n")
    nodes = hh.tree_nodes(lines)
    j = next(k for k, n in enumerate(nodes) if "note_brief_test.py" in n[2])
    parent = " > ".join(hh.tree_path(nodes, j).split(" > ")[:-1])
    note = hh.resolve_tree_scope(lines, parent + " > no_such_node_xyz")[2] or ""
    check("a missing child lists the names under its parent", "not found under" in note and "_test.py" in note, note)
    top = hh.resolve_tree_scope(lines, "no_such_top_xyz")[2] or ""
    check("a missing top-level node lists the top-level names", "the nodes there are:" in top and "under" not in top.split(";")[0], top)
    ws = tempfile.mkdtemp(prefix="harness-scopehint-")
    run(ws, "alpha", "@SCOPE alpha work | a.py")
    out = run(ws, "beta", "@SCOPE beta work | a.py, b.py")
    check("a refused scope counts free and busy paths and names the free one", "[SCOPE REFUSED]" in out and "1 of 2 requested path(s) are free" in out and "(b.py)" in out, out)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
