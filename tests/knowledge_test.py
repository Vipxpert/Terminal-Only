# /llm_harness/tests/knowledge_test.py
"""Knowledge-library test for llm_harness: entries are read from knowledge/<technology>.txt, @HELP KB lists the technologies, finds entries by technology, tag or symptom words, hides retired entries unless asked, keeps its output short, and the shipped library has no malformed, duplicated or contradicted entries."""
import importlib.util, os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
LIB = os.environ.get("LLM_TEST_LIBRARY") or os.path.join(os.path.dirname(os.path.abspath(HARNESS)), "knowledge")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-700:].replace("\n", "\n    "))


def entry(id, tags, symptom, trap, fix, extra=""):
    return "## %s\ntags: %s\nsymptom: %s\ntrap: %s\nfix: %s\nverified: tested 2026-11\n%s\n" % (id, tags, symptom, trap, fix, extra)


def main():
    spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS)
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    fx = tempfile.mkdtemp(prefix="harness-kb-")
    alpha = "# tech: alpha-lang\n# detect: alpha\n\n"
    alpha += entry("alpha-eager-call", "eager, callback, freeze", "The window freezes during a callback.", "Calling the function instead of passing it runs it early.", "Pass the function itself.")
    alpha += entry("alpha-old-way", "eager", "Old advice.", "Old trap.", "Old fix.", "obsolete: alpha-eager-call")
    alpha += "## alpha-wrapped\ntags: wrap\nsymptom: A long note\ntrap: first part\n  continued on the next line\nfix: the fix\nverified: tested 2026-11\n"
    with open(os.path.join(fx, "alpha.txt"), "w", newline="\n") as f:
        f.write(alpha)
    with open(os.path.join(fx, "beta.txt"), "w", newline="\n") as f:
        f.write("# tech: beta-db\n\n" + "".join(entry("beta-%d" % i, "join, memory", "Memory blows up after a join %d." % i, "trap %d" % i, "fix %d" % i) for i in range(1, 9)))
    entries = hh.kb_entries(fx)
    first = entries[0]
    check("entries are read with their technology, id and fields", len(entries) == 11 and first["tech"] == "alpha-lang" and first["id"] == "alpha-eager-call" and first["fix"] == "Pass the function itself.", entries[:1])
    wrapped = next(e for e in entries if e["id"] == "alpha-wrapped")
    check("a value continues on an indented line", wrapped["trap"] == "first part continued on the next line" and wrapped["fix"] == "the fix", wrapped)
    hits = [e["id"] for e in hh.kb_search("alpha-lang", entries)]
    check("a technology name finds its entries, retired ones left out", hits == ["alpha-eager-call", "alpha-wrapped"], hits)
    check("a symptom word finds the entry", [e["id"] for e in hh.kb_search("freezes callback", entries)][:1] == ["alpha-eager-call"])
    check("a tag finds the entries that carry it", [e["id"] for e in hh.kb_search("wrap", entries)] == ["alpha-wrapped"])
    check("retired entries appear when asked for", "alpha-old-way" in [e["id"] for e in hh.kb_search("eager obsolete", entries)])
    env = dict(os.environ, LLM_HARNESS_KNOWLEDGE=fx)

    def ask(words):
        text = "@SCRIPT [C: kb]\n@WORKSPACE %s\n@HELP KB %s\n" % (fx, words)
        p = subprocess.run([sys.executable, HARNESS], input=text.encode(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=60)
        return p.stdout.decode("utf-8", "replace").replace("\r", "").split("=== L1 CONTRACT")[0]

    out = ask("")
    check("@HELP KB without words lists the technologies and how to search", "alpha-lang" in out and "beta-db" in out and "8 entries" in out and "@HELP KB <technology or symptom words>" in out, out)
    out = ask("freezes callback")
    check("@HELP KB with words prints the trap and the fix", "[alpha-lang] alpha-eager-call" in out and "trap: Calling the function" in out and "fix: Pass the function itself." in out, out)
    out = ask("memory join")
    check("many matches: at most six are printed in full and the rest are named", out.count("[beta-db] beta-") == 6 and "(2 more match: beta-7, beta-8" in out, out)
    out = ask("nonexistent-thing")
    check("no match says so and lists the technologies", "nothing matches" in out and "alpha-lang" in out, out)
    real = hh.kb_entries(LIB)
    check("the shipped library has entries", len(real) >= 10, "%d entries in %s" % (len(real), LIB))
    check("the shipped library has no malformed, repeated or contradicted entries", not hh.kb_lint(real), hh.kb_lint(real))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
