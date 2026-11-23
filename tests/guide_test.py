# /llm_harness/tests/guide_test.py
"""Guide test for llm_harness: @GUIDE makes a session the project's guide, a second guide and a guide that holds code are refused, a guide may claim docs/ but not code, the guide's footer and every worker's footer say so, and @GUIDE off ends the role."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []
COUNT = [0]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-1200:].replace("\n", "\n    "))


def run(ws, session, *lines):
    COUNT[0] += 1
    text = "\n".join(["@SCRIPT [C: guide %d]" % COUNT[0], "@WORKSPACE " + ws, "@SESSION %s | %s work" % (session, session)] + list(lines)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "").split("=== L1 CONTRACT")[0]


def main():
    ws = tempfile.mkdtemp(prefix="harness-guide-")
    os.makedirs(os.path.join(ws, "docs"))
    for rel in ("a.py", os.path.join("docs", "plan.md")):
        with open(os.path.join(ws, rel), "w", newline="\n") as f:
            f.write("x\n")
    out = run(ws, "lead", "@GUIDE")
    check("@GUIDE makes the session the project's guide", "[GUIDE] lead is now the project's guide" in out, out)
    run(ws, "coder", "@SCOPE coder aim | a.py")
    out = run(ws, "coder", "@GUIDE")
    check("a second guide is refused while one exists", "[GUIDE REFUSED] lead is already" in out, out)
    out = run(ws, "lead", "@SCOPE plan | a.py")
    ok_code = "the project's guide: it may claim only docs/" in out
    out = run(ws, "lead", "@SCOPE plan | docs/plan.md")
    check("the guide may claim docs/ but not code", ok_code and "[SCOPE] lead scope set" in out, out)
    out = run(ws, "lead", "@LIST_DIR /")
    lead_foot = "=== YOU ARE THE PROJECT'S GUIDE" in out
    out = run(ws, "coder", "@LIST_DIR /")
    check("the guide's footer reminds it of its job, and a worker's footer names the guide", lead_foot and "=== GUIDE: lead" in out, out)
    out = run(ws, "lead", "@GUIDE off")
    after = run(ws, "coder", "@LIST_DIR /")
    check("@GUIDE off ends the role and the workers' footers drop it", "is no longer the project's guide" in out and "=== GUIDE:" not in after, (out, after))
    out = run(ws, "coder", "@GUIDE")
    check("a session that holds code files cannot become the guide", "[GUIDE REFUSED] this session holds code files" in out, out)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
