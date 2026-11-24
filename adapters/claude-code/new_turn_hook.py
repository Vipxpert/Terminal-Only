# /llm_harness/adapters/claude-code/new_turn_hook.py
"""Claude Code UserPromptSubmit hook for llm_harness: on EVERY prompt it starts a new harness prompt turn, so the next harness run briefs the full standing rules once.

Claude Code passes the hook a JSON object on stdin; this script uses only session_id (the host session), prompt_id (the idempotency key, so a retried hook never starts two turns) and cwd (the project folder). It does not try to tell typed prompts from scheduled, subagent or other-session messages: the prompt source is not reliably sent, and an extra briefing only costs tokens. On success it prints only Claude Code's hook JSON (hookSpecificOutput.additionalContext, injected as a system reminder); when the turn cannot start it exits 2 with the reason on stderr, which holds the prompt back, because work without the harness rules is worse than a held prompt.
"""
import json, os, subprocess, sys


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            data = {}
    except (ValueError, OSError):
        data = {}
    harness = os.environ.get("LLM_HARNESS_PATH") or os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
    env = dict(os.environ)
    env.setdefault("LLM_HARNESS_AGENT", "claude-code")
    sid = str(data.get("session_id") or env.get("CLAUDE_CODE_SESSION_ID") or "")
    if sid:
        env["LLM_HARNESS_HOST_SESSION"] = sid
    args = [sys.executable, harness, "--workspace", str(data.get("cwd") or os.getcwd()), "--new-turn"]
    if data.get("prompt_id"):
        args.append(str(data["prompt_id"]))
    try:
        p = subprocess.run(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=25)
        out = p.stdout.decode("utf-8", "replace").strip()
        ok = p.returncode == 0 and "AGENT TURN" in out
    except (OSError, subprocess.SubprocessError) as e:
        out, ok = str(e), False
    if not ok:
        # Comment (decision): fail closed: exit 2 holds this prompt back (the settings add onFailure block for crashes and timeouts), so the agent never works a prompt without the harness rules
        sys.stderr.write("llm_harness: the prompt turn could not start, so this prompt is held back rather than run without the harness rules: %s\n" % out[-500:])
        return 2
    context = out + "\nWork only through the harness: every terminal action is ONE script piped into it, exactly as  @'<script>'@ | python '%s'  (the only command allowed: no other command and no $OutputEncoding prefix). Its first output in this prompt prints the full standing rules; follow them, and answer the user in plain prose." % harness
    json.dump({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
