# /llm_harness/tests/pretool_hook_test.py
"""PreToolUse-hook test for the Claude Code auto-shell adapter: silent in an ordinary folder; in a Terminal-Only project it allows only the harness call (one here-string piped into python and the installed harness.py) and denies other tools, other commands, a here-string that ends early and python given by path; the harness install folder is not a project."""
import json, os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "adapters", "claude-code", "pretooluse_hook.py")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def hook(cwd, tool, command=None):
    env = dict(os.environ, LLM_HARNESS_PATH=HARNESS)
    payload = {"cwd": cwd, "tool_name": tool, "tool_input": {"command": command} if command is not None else {"file_path": "x.txt"}, "hook_event_name": "PreToolUse"}
    p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, env=env)
    out = p.stdout.decode("utf-8", "replace")
    try:
        decision = json.loads(out)["hookSpecificOutput"]["permissionDecision"]
    except (ValueError, KeyError, TypeError):
        decision = ""
    return p.returncode, out, decision


def main():
    base = tempfile.mkdtemp(prefix="harness-pretool-")
    plain, proj, inst = (os.path.join(base, n) for n in ("plain", "proj", "inst"))
    os.makedirs(plain)
    os.makedirs(os.path.join(proj, ".llm_harness"))
    os.makedirs(os.path.join(inst, ".llm_harness"))
    open(os.path.join(inst, ".llm_harness", "harness.py"), "w").close()
    call = "@'\n@SCRIPT [P: x]\n@LIST_DIR /\n'@ | python '%s'" % HARNESS.replace("\\", "/")
    code, out, d = hook(plain, "Read")
    check("an ordinary folder gets no answer at all, so Claude Code behaves as usual", code == 0 and not out.strip(), out)
    code, out, d = hook(proj, "PowerShell", call)
    check("in a Terminal-Only project the harness call is allowed", d == "allow", out)
    code, out, d = hook(proj, "Read")
    check("in a Terminal-Only project the Read tool is denied", d == "deny" and "harness script" in out, out)
    code, out, d = hook(proj, "PowerShell", "Get-ChildItem")
    check("another PowerShell command is denied", d == "deny", out)
    smuggle = "@'\n@SCRIPT [P: x]\n'@; Remove-Item x\n@'\n@LIST_DIR /\n'@ | python '%s'" % HARNESS.replace("\\", "/")
    code, out, d = hook(proj, "PowerShell", smuggle)
    check("a here-string that ends early to run a second command is denied", d == "deny" and "end the here-string early" in out, out)
    code, out, d = hook(proj, "PowerShell", call.replace("| python ", "| C:/evil/python.exe "))
    check("python given by path is denied", d == "deny" and "not given by path" in out, out)
    code, out, d = hook(inst, "Read")
    check("the harness install folder is not a Terminal-Only project", code == 0 and not out.strip(), out)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
