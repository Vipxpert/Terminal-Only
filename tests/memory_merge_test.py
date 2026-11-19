# /llm_harness/tests/memory_merge_test.py
"""Memory-merge test for llm_harness: notes.md merges by note id and verdicts.json by key, so two devices that both add notes or verdicts do not leave conflict markers; the merge runs as a git merge driver that the harness registers in each clone, new repositories get the .gitattributes lines, and incoming memory without those lines gets a hint."""
import importlib.util, json, os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
BASE = tempfile.mkdtemp(prefix="harness-memmerge-")
RESULTS = []
STEP = [0]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def git(cwd, *args):
    r = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t"] + list(args), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return r.returncode, r.stdout.decode("utf-8", "replace").strip()


def run(ws, *lines):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0], "@WORKSPACE " + ws]
    env = dict(os.environ, LLM_HARNESS_FETCH="off")
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120, env=env)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def put(ws, rel, text):
    path = os.path.join(ws, rel)
    os.makedirs(os.path.dirname(path) or ws, exist_ok=True)
    with open(path, "w", newline="\n") as f:
        f.write(text)


def get(ws, rel):
    with open(os.path.join(ws, rel)) as f:
        return f.read()


def notes(next_id, *lines):
    return "<!-- llm_harness_notes_next_id: %d -->\n" % next_id + "".join("- %s\n" % l for l in lines)


def main():
    spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS)
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    base = notes(2, "[N001] base")
    m = hh.merge_notes_text("", notes(2, "[N001] from ours"), notes(2, "[N001] from theirs"))
    check("two new notes with the same id are both kept, the other side's gets a fresh id", "[N001] from ours" in m and "[N002] from theirs" in m and "next_id: 3" in m, m)
    check("identical additions stay one note", hh.merge_notes_text("", notes(2, "[N001] same"), notes(2, "[N001] same")).count("same") == 1)
    m = hh.merge_notes_text(base, notes(3, "[N001] base edited here", "[N002] mine"), notes(3, "[N001] base", "[N002] theirs new"))
    check("an edit on one side and a new note on the other both survive", "base edited here" in m and "[N002] mine" in m and "theirs new" in m, m)
    check("a note removed by one side stays removed", "[N001]" not in hh.merge_notes_text(base, base, notes(2)) and "[N001]" not in hh.merge_notes_text(base, notes(2), base))
    m = hh.merge_notes_text(base, notes(2, "[N001] our edit"), notes(2, "[N001] their edit"))
    check("when both edit one note, this side's text stays and the other's becomes a new note", "[N001] our edit" in m and "the other side's edit of N001) their edit" in m, m)
    m = hh.merge_notes_text("", notes(2, "[N001] [pin: a, b] pinned"), notes(2))
    check("pins survive a merge", "[N001] [pin: a, b] pinned" in m, m)
    try:
        hh.merge_notes_text(base, base, "<<<<<<< ours\n- [N001] x\n=======\n")
        refused = False
    except ValueError:
        refused = True
    check("a side that cannot be read is refused, not guessed at", refused)
    notes_a, _ = hh.parse_notes_text(hh.merge_notes_text("", notes(3, "[N001] a", "[N002] b"), notes(3, "[N001] c", "[N002] d")))
    check("the merged file reads back with no duplicate ids", len({n["id"] for n in notes_a}) == len(notes_a) == 4, notes_a)
    j = lambda d: json.dumps(d)
    m = json.loads(hh.merge_verdicts_text(j({}), j({"verdicts": {"x\ta": {"time": 1, "verdict": "ok"}}}), j({"verdicts": {"y\tb": {"time": 2, "verdict": "bad"}}})))
    check("verdicts only one side has are all kept", set(m["verdicts"]) == {"x\ta", "y\tb"}, m)
    b = {"verdicts": {"k": {"time": 1, "verdict": "old"}}}
    m = json.loads(hh.merge_verdicts_text(j(b), j({"verdicts": {"k": {"time": 5, "verdict": "mine"}}}), j({"verdicts": {"k": {"time": 9, "verdict": "theirs"}}})))
    check("when both changed a verdict the newer one wins", m["verdicts"]["k"]["verdict"] == "theirs", m)
    m = json.loads(hh.merge_verdicts_text(j(b), j(b), j({"verdicts": {}})))
    check("a verdict removed by one side stays removed", "k" not in m["verdicts"], m)
    m = json.loads(hh.merge_verdicts_text(j({}), j({"campaigns": {"c1": {"time": 1}}}), j({"campaigns": {"c2": {"time": 1}}})))
    check("campaigns merge by name", set(m["campaigns"]) == {"c1", "c2"}, m)
    origin, seed, clone_a, clone_b = (os.path.join(BASE, n) for n in ("origin.git", "seed", "a", "b"))
    git(BASE, "init", "-q", "--bare", origin)
    git(origin, "symbolic-ref", "HEAD", "refs/heads/main")
    os.makedirs(seed)
    git(seed, "init", "-q")
    git(seed, "checkout", "-q", "-b", "main")
    put(seed, "a.txt", "x\n")
    put(seed, ".gitattributes", hh.GITATTRIBUTES_DEFAULT)
    git(seed, "add", ".")
    git(seed, "commit", "-q", "-m", "chore: start")
    git(seed, "remote", "add", "origin", origin)
    git(seed, "push", "-q", "-u", "origin", "main")
    git(BASE, "clone", "-q", origin, clone_a)
    git(BASE, "clone", "-q", origin, clone_b)
    out = run(clone_a, "@NOTE_ADD Decision: written on device A")
    registered = git(clone_a, "config", "--local", "--get", "merge.llm-harness-notes.driver")[1]
    check("the harness registers the merge driver in the clone it runs in", "--merge-memory notes" in registered and "[NOTE ADDED]" in out, registered + out)
    git(clone_a, "push", "-q", "origin", "main")
    run(clone_b, "@NOTE_ADD Decision: written on device B")
    code, merge_out = git(clone_b, "pull", "--no-rebase", "--no-edit", "-q", "origin", "main")
    text = get(clone_b, ".llm_harness/notes.md")
    check("two devices' notes merge through git with no conflict markers", code == 0 and "<<<<<<<" not in text and "written on device A" in text and "written on device B" in text, merge_out + text)
    out = run(clone_b, "@NOTE_LIST")
    check("and the harness reads the merged notes, ids distinct", "written on device A" in out and "written on device B" in out and "NOTE ERROR" not in out and "WARNING" not in out, out)
    put(clone_a, ".llm_harness/verdicts.json", json.dumps({"verdicts": {"a.txt\tdevA": {"time": 1, "verdict": "fine"}}}, indent=1))
    git(clone_a, "add", "-f", ".llm_harness/verdicts.json")
    git(clone_a, "commit", "-q", "-m", "chore(harness): verdict from A")
    git(clone_a, "push", "-q", "origin", "main")
    put(clone_b, ".llm_harness/verdicts.json", json.dumps({"verdicts": {"a.txt\tdevB": {"time": 2, "verdict": "risky"}}}, indent=1))
    git(clone_b, "add", "-f", ".llm_harness/verdicts.json")
    git(clone_b, "commit", "-q", "-m", "chore(harness): verdict from B")
    code, merge_out = git(clone_b, "pull", "--no-rebase", "--no-edit", "-q", "origin", "main")
    try:
        merged = json.loads(get(clone_b, ".llm_harness/verdicts.json"))
    except ValueError:
        merged = {}
    check("two devices' verdicts merge through git into valid JSON with both entries", code == 0 and set(merged.get("verdicts", {})) == {"a.txt\tdevA", "a.txt\tdevB"}, merge_out)
    fresh = os.path.join(BASE, "fresh")
    os.makedirs(fresh)
    out = run(fresh, "@GIT_INIT Tester <t@t.t>")
    check("@GIT_INIT writes the merge rules for a new repository", os.path.exists(os.path.join(fresh, ".gitattributes")) and "merge=llm-harness-notes" in get(fresh, ".gitattributes"), out)
    origin2, proj, other = (os.path.join(BASE, n) for n in ("origin2.git", "proj", "other"))
    git(BASE, "init", "-q", "--bare", origin2)
    git(origin2, "symbolic-ref", "HEAD", "refs/heads/main")
    os.makedirs(proj)
    git(proj, "init", "-q")
    git(proj, "checkout", "-q", "-b", "main")
    put(proj, "a.txt", "x\n")
    git(proj, "add", ".")
    git(proj, "commit", "-q", "-m", "chore: start")
    git(proj, "remote", "add", "origin", origin2)
    git(proj, "push", "-q", "-u", "origin", "main")
    git(BASE, "clone", "-q", origin2, other)
    put(other, ".llm_harness/notes.md", notes(2, "[N001] incoming"))
    git(other, "add", "-f", ".")
    git(other, "commit", "-q", "-m", "chore(harness): note")
    git(other, "push", "-q", "origin", "main")
    env = dict(os.environ, LLM_HARNESS_FETCH="0")
    head = "@SCRIPT [C: hint 1]\n@WORKSPACE %s\n" % proj
    out = subprocess.run([sys.executable, HARNESS], input=head.encode(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=60).stdout.decode("utf-8", "replace")
    check("incoming memory without the merge rules in .gitattributes gets a hint", "project memory: .llm_harness/notes.md" in out and "merge rules for notes and verdicts are not in .gitattributes" in out, out)
    put(proj, ".gitattributes", hh.GITATTRIBUTES_DEFAULT)
    git(proj, "add", ".")
    git(proj, "commit", "-q", "-m", "chore: merge rules")
    head = "@SCRIPT [C: hint 2]\n@WORKSPACE %s\n" % proj
    out = subprocess.run([sys.executable, HARNESS], input=head.encode(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=60).stdout.decode("utf-8", "replace")
    check("with the rules in place there is no hint", "project memory: .llm_harness/notes.md" in out and "not in .gitattributes" not in out, out)
    print("test workspace: " + BASE)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
