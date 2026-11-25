# /llm_harness/tests/launcher_test.py
"""Launcher test (Windows) for the Claude Code auto-shell: the PowerShell launcher is silent in an ordinary folder (and prints how long that takes); in a Terminal-Only project it hands over to the Python guard (Read denied, the harness call allowed); with Python missing it blocks only the project (tools denied, prompts held back) and still leaves an ordinary folder alone."""
import json, os, subprocess, sys, tempfile, time

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
LAUNCHER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "adapters", "claude-code", "auto_shell_hook.ps1")
RESULTS = []
NO_PY = {"LLM_HARNESS_PYTHON": "C:\\no\\such\\folder\\python.exe"}


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def launch(mode, cwd, tool="Read", command=None, extra=None):
    env = dict(os.environ, LLM_HARNESS_PATH=HARNESS)
    env.update(extra or {})
    payload = {"cwd": cwd, "tool_name": tool, "tool_input": {"command": command} if command else {"file_path": "x.txt"}, "session_id": "s1", "prompt_id": "p1"}
    t = time.time()
    p = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", LAUNCHER, mode], input=json.dumps(payload).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, env=env)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace"), time.time() - t


def main():
    if os.name != "nt":
        print("SKIP launcher_test: Windows only")
        return
    base = tempfile.mkdtemp(prefix="harness-launcher-")
    plain, proj = os.path.join(base, "plain"), os.path.join(base, "proj")
    os.makedirs(plain)
    os.makedirs(os.path.join(proj, ".llm_harness"))
    code, out, err, secs = launch("pretool", plain)
    print("  (ordinary-project overhead per tool call: %d ms)" % (secs * 1000))
    check("an ordinary folder gets no answer, without Python being started", code == 0 and not out.strip(), (out, err))
    code, out, err, _ = launch("pretool", proj)
    check("in a Terminal-Only project the launcher hands over to the Python guard, which denies Read", '"deny"' in out and "harness script" in out, (out, err))
    call = "@'\n@SCRIPT [P: x]\n'@ | python '%s'" % HARNESS.replace("\\", "/")
    code, out, err, _ = launch("pretool", proj, "PowerShell", call)
    check("and allows the harness call", '"allow"' in out, (out, err))
    code, out, err, _ = launch("pretool", proj, extra=NO_PY)
    check("with Python missing, tools are denied in the Terminal-Only project", '"deny"' in out and "could not be found" in out, (out, err))
    code, out, err, _ = launch("pretool", plain, extra=NO_PY)
    check("with Python missing, an ordinary folder is still left alone", code == 0 and not out.strip(), (out, err))
    code, out, err, _ = launch("prompt", proj, extra=NO_PY)
    check("with Python missing, a prompt in the Terminal-Only project is held back", code == 2 and "held back" in err, (code, out, err))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
