# /llm_harness/tests/kb_search_test.py
"""Knowledge-search test for llm_harness: the technologies a project uses are detected from its manifests, file types, file names and imports; a search shows only those (or ones the words name, or all), an entry needs a strong match or two matched words and must cover most of what the best entry covers, and retired entries wait for the word obsolete."""
import importlib.util, os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
LIB = os.environ.get("LLM_TEST_LIBRARY") or os.path.join(os.path.dirname(os.path.abspath(HARNESS)), "knowledge")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-700:].replace("\n", "\n    "))


def put(folder, name, text):
    path = os.path.join(folder, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="\n") as f:
        f.write(text)


def entry(id, tags, symptom, trap, fix):
    return "## %s\ntags: %s\nsymptom: %s\ntrap: %s\nfix: %s\nverified: tested 2026-11\n\n" % (id, tags, symptom, trap, fix)


def main():
    spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS)
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    lib, proj = tempfile.mkdtemp(prefix="harness-kblib-"), tempfile.mkdtemp(prefix="harness-kbproj-")
    put(lib, "one.txt", "# tech: one-lang\n# detect: one-lib\n\n" + entry("one-a", "event loop, freeze, hang", "The window freezes.", "A call blocks.", "Do not block.") + entry("one-b", "other", "Slow.", "It uses a lot of memory.", "Use less.") + entry("one-c", "hang", "Stuck.", "A wait.", "Do not wait."))
    put(lib, "two.txt", "# tech: two-ext\n# detect: *.two\n\n" + entry("two-a", "twotag", "S.", "T.", "F."))
    put(lib, "three.txt", "# tech: three-file\n# detect: three.config\n\n" + entry("three-a", "threetag", "S.", "T.", "F."))
    put(lib, "four.txt", "# tech: four-import\n# detect: fourlib\n\n" + entry("four-a", "fourtag", "S.", "T.", "F."))
    put(lib, "five.txt", "# tech: five-all\n# detect: *\n\n" + entry("five-a", "fivetag", "S.", "T.", "F."))
    put(lib, "six.txt", "# tech: six-unused\n# detect: six-lib\n\n" + entry("six-a", "freeze, hang", "The tool freezes.", "A trap.", "A fix."))
    put(proj, "requirements.txt", "one-lib==1.0\n")
    put(proj, "data.two", "x\n")
    put(proj, "three.config", "x\n")
    put(proj, "main.py", "import os\nimport fourlib\n")
    E = hh.kb_entries(lib)
    active = hh.kb_active(E, hh.kb_project_facts(proj))
    check("a technology is detected from a manifest word, a file extension, a file name, an import line, or always", set(active) == {"one-lang", "two-ext", "three-file", "four-import", "five-all"}, sorted(active))
    ids = lambda words, act=active: [e["id"] for e in hh.kb_rank(words, E, act)[0]]
    hits, hidden = hh.kb_rank("freeze hang", E, active)
    check("a technology the project does not use stays out, and is counted", "six-a" not in [e["id"] for e in hits] and hidden == 1, (ids("freeze hang"), hidden))
    check("naming the technology shows it", "six-a" in ids("six-unused freeze"))
    check("the word all includes technologies the project does not use", "six-a" in ids("freeze hang all"))
    check("the words of a tag phrase match it, and a plural matches its stem", "one-a" in ids("event loop") and "one-a" in ids("freezes"), (ids("event loop"), ids("freezes")))
    check("one common word that is only in an entry's text pulls nothing in", ids("memory") == [], ids("memory"))
    check("an entry that covers little of the question is left out next to one that covers it", ids("event loop freeze hang") == ["one-a"], ids("event loop freeze hang"))
    env = dict(os.environ, LLM_HARNESS_KNOWLEDGE=lib)

    def ask(words):
        text = "@SCRIPT [C: kb]\n@WORKSPACE %s\n@HELP KB %s\n" % (proj, words)
        p = subprocess.run([sys.executable, HARNESS], input=text.encode(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=60)
        return p.stdout.decode("utf-8", "replace").replace("\r", "").split("=== L1 CONTRACT")[0]

    out = ask("freeze")
    check("@HELP KB shows the project's technologies and says how many matches it left out", "[one-lang] one-a" in out and "six-a" not in out and "1 more match in technologies this project does not seem to use" in out, out)
    out = ask("")
    check("@HELP KB without words marks the technologies used here", "one-lang" in out and "[used here" in out and out.count("[used here") == 5, out)
    real = hh.kb_entries(LIB)
    py, go = tempfile.mkdtemp(prefix="harness-kbpy-"), tempfile.mkdtemp(prefix="harness-kbgo-")
    put(py, "requirements.txt", "fastapi==0.115\n")
    put(py, "app.py", "import asyncio\n")
    put(go, "go.mod", "module example.com/x\n")
    top = hh.kb_rank("asyncio to_thread blocks event loop", real, hh.kb_active(real, hh.kb_project_facts(py)))[0]
    check("in a Python project a question about to_thread finds the matching entry first", top and top[0]["id"] == "py-thread-handoff-eager", [e["id"] for e in top])
    hits, hidden = hh.kb_rank("freeze thread memory", real, hh.kb_active(real, hh.kb_project_facts(go)))
    check("in a Go project the same kind of question shows no Python, SQL or grid entries", hits == [] and hidden >= 1, ([e["id"] for e in hits], hidden))
    why = hh.kb_active(E, hh.kb_project_facts(proj))
    check("each technology says why it counts as used", why["one-lang"] == "'one-lib' in requirements.txt" and why["two-ext"] == "a .two file" and why["three-file"] == "file three.config" and why["four-import"] == "'fourlib' imported in main.py" and why["five-all"] == "every project" and "[used here: 'one-lib' in requirements.txt]" in ask(""), why)
    text = "@SCRIPT [C: kb]\n@WORKSPACE %s\n@KB freeze\n" % proj
    p = subprocess.run([sys.executable, HARNESS], input=text.encode(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=60)
    out = p.stdout.decode("utf-8", "replace").replace("\r", "")
    check("@KB <words> works like @HELP KB <words> and is a known directive", "[one-lang] one-a" in out and "unknown directive" not in out, out)

    def run_script():
        head = "@SCRIPT [C: hint]\n@WORKSPACE %s\n@SESSION kbhint | hint aim\n" % proj
        q = subprocess.run([sys.executable, HARNESS], input=head.encode(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=60)
        return q.stdout.decode("utf-8", "replace").replace("\r", "")

    first, second = run_script(), run_script()
    put(proj, "requirements.txt", "one-lib==1.0\nsix-lib==2.0\n")
    third = run_script()
    check("the footer names the technologies on file once, and again only when they change", "[KNOWLEDGE] pitfalls on file for what this project uses:" in first and "[KNOWLEDGE]" not in second and "six-unused" in third, (first[-400:], second[-400:], third[-400:]))
    put(lib, "seven.txt", "# tech: seven-nuget\n# detect: sevenlib\n\n" + entry("seven-a", "seventag", "S.", "T.", "F."))
    nug = tempfile.mkdtemp(prefix="harness-kbnuget-")
    put(nug, "app.csproj", '<Project><ItemGroup><Reference Include="sevenlib" /></ItemGroup></Project>\n')
    E2 = hh.kb_entries(lib)
    before = hh.kb_active(E2, hh.kb_project_facts(nug))
    put(nug, "app.csproj", '<Project><ItemGroup><PackageReference Include="sevenlib" Version="1.0" /></ItemGroup></Project>\n')
    after = hh.kb_active(E2, hh.kb_project_facts(nug))
    check("in a .csproj only PackageReference lines count, and the reason names the file", "seven-nuget" not in before and after.get("seven-nuget") == "'sevenlib' in app.csproj", (before, after))
    put(lib, "eight.txt", "# tech: eight-python\n# detect: eightlib\n\n" + entry("eight-a", "eighttag, freeze", "The tool freezes.", "T.", "F."))
    E3 = hh.kb_entries(lib)
    act3 = hh.kb_active(E3, hh.kb_project_facts(proj))
    generic = [e["id"] for e in hh.kb_rank("python freeze", E3, act3)[0]]
    check("a common word such as python does not name a technology, but its full name does", "eight-a" not in generic and "eight-a" in [e["id"] for e in hh.kb_rank("eight-python freeze", E3, act3)[0]], generic)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
