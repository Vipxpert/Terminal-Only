# /llm_harness/tests/cmd_front_test.py
"""Cmd-front test (Windows) for the Claude Code auto-shell hooks: an ordinary folder is answered at once with nothing (the time is printed); a Terminal-Only project is guarded from its root and from a nested folder; when the working folder falls back to the home folder while the real cwd was a deleted folder inside a project, it is still guarded; a folder holding the harness install is no project."""
import json, os, subprocess, sys, tempfile, time

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
FRONT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "adapters", "claude-code", "auto_shell_hook.cmd")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def front(cwd, json_cwd=None, extra=None):
    env = dict(os.environ, LLM_HARNESS_PATH=HARNESS)
    env.update(extra or {})
    payload = {"cwd": json_cwd or cwd, "tool_name": "Read", "tool_input": {"file_path": "x.txt"}}
    t = time.time()
    p = subprocess.run(["cmd", "/d", "/q", "/c", FRONT, "pretool"], input=json.dumps(payload).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, env=env, cwd=cwd)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace"), time.time() - t


def main():
    if os.name != "nt":
        print("SKIP cmd_front_test: Windows only")
        return
    base = tempfile.mkdtemp(prefix="harness-front-")
    plain, proj, home, inst = (os.path.join(base, n) for n in ("plain", "proj", "home", "inst"))
    nested = os.path.join(proj, "src", "a", "b")
    for d in (plain, nested, home, os.path.join(proj, ".llm_harness"), os.path.join(inst, ".llm_harness")):
        os.makedirs(d, exist_ok=True)
    open(os.path.join(inst, ".llm_harness", "harness.py"), "w").close()
    runs = [front(plain) for _ in range(3)]
    print("  (ordinary-project overhead per tool call with the cmd front: %d ms, average of 3)" % (sum(r[3] for r in runs) / 3 * 1000))
    check("an ordinary folder gets no answer at once, without PowerShell or Python", all(r[0] == 0 and not r[1].strip() for r in runs), runs[0][1:3])
    code, out, err, _ = front(proj)
    check("a Terminal-Only project root is guarded", '"deny"' in out, (out, err))
    code, out, err, _ = front(nested)
    check("a folder three levels inside the project is guarded", '"deny"' in out, (out, err))
    code, out, err, _ = front(home, json_cwd=os.path.join(proj, "src", "gone"), extra={"USERPROFILE": home})
    check("when the working folder falls back to home but the real cwd was a deleted folder in the project, it is still guarded", '"deny"' in out, (out, err))
    code, out, err, _ = front(inst)
    check("a folder holding the harness install is no project", code == 0 and not out.strip(), (out, err))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
