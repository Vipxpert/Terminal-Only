# /llm_harness/tests/adapter_hook_test.py
"""Adapter-hook test for llm_harness: the Claude Code UserPromptSubmit hook script, fed the hook's JSON, starts a harness turn for that host session, and the same prompt_id again does not start a second turn."""
import json, os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "adapters", "claude-code", "new_turn_hook.py")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def hook(payload, harness=None):
    env = {k: v for k, v in os.environ.items() if k not in ("LLM_HARNESS_AGENT", "CLAUDE_CODE_SESSION_ID", "LLM_HARNESS_HOST_SESSION")}
    env["LLM_HARNESS_PATH"] = harness or HARNESS
    p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90, env=env)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def context(out):
    try:
        return json.loads(out)["hookSpecificOutput"]["additionalContext"]
    except (ValueError, KeyError, TypeError):
        return ""


def main():
    ws = tempfile.mkdtemp(prefix="harness-hook-")
    prompt = {"session_id": "s9", "prompt_id": "p1", "cwd": ws, "hook_event_name": "UserPromptSubmit", "prompt": "hello"}
    code, out, err = hook(prompt)
    ctx = context(out)
    check("a prompt starts turn 1 and hands Claude Code the briefing as additionalContext, with the one allowed command", code == 0 and "AGENT TURN 1 starts for host session s9" in ctx and "| python '" in ctx, (out, err))
    code, out, err = hook(prompt)
    check("the same prompt_id again does not start a second turn", code == 0 and "continues" in context(out), (out, err))
    code, out, err = hook(dict(prompt, prompt_id="p2"), harness=os.path.join(ws, "missing", "harness.py"))
    check("when the turn cannot start, the hook exits 2 and says why, so the prompt is held back", code == 2 and "held back" in err and not out.strip(), (code, out, err))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
