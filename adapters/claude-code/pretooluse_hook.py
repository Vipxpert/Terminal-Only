# /llm_harness/adapters/claude-code/pretooluse_hook.py
"""Claude Code PreToolUse hook (matcher *) for Terminal-Only auto-shell. In a Terminal-Only project it allows only the harness call through the PowerShell tool (one single-quoted here-string piped into python and the installed harness.py) and denies every other tool call with the reason and the way to do it through the harness; in any other project it says nothing, so Claude Code behaves as usual. Inside a project, anything unexpected blocks (exit 2) rather than letting a tool through."""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness_project import harness_root

HARNESS = os.environ.get("LLM_HARNESS_PATH") or os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
CALL = "@'<script>'@ | python '%s'" % HARNESS.replace("\\", "/")


def decide(kind, reason):
    json.dump({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": kind, "permissionDecisionReason": reason}}, sys.stdout)
    return 0


def allowed_command(cmd):
    m = re.fullmatch(r"\s*@'\r?\n(.*?)\r?\n'@[ \t]*\|[ \t]*(\S+)[ \t]+'([^'\r\n]+)'\s*", cmd, re.S)
    if not m:
        return "the command is not one here-string piped into the harness"
    body, exe, path = m.groups()
    # Comment (invariant): a line starting with '@ ends a PowerShell here-string early, and whatever follows would run as a second command
    if any(line.lstrip("\r").startswith("'@") for line in body.split("\n")):
        return "a line inside the script starts with '@, which would end the here-string early"
    if exe.lower() not in ("python", "python3"):
        return "Python must be named python (found on the PATH), not given by path"
    if os.path.normcase(os.path.abspath(path)) != os.path.normcase(os.path.abspath(HARNESS)):
        return "that is not the installed harness"
    return ""


def main():
    root = None
    try:
        try:
            data = json.load(sys.stdin)
            if not isinstance(data, dict):
                data = {}
        except ValueError:
            data = {}
        root = harness_root(str(data.get("cwd") or os.getcwd()))
        if not root:
            return 0
        tool = str(data.get("tool_name") or "")
        if tool == "PowerShell":
            why = allowed_command(str((data.get("tool_input") or {}).get("command") or ""))
            if not why:
                return decide("allow", "Terminal-Only auto-shell: the harness call")
            return decide("deny", "Terminal-Only auto-shell: %s. Send the terminal work as ONE harness script, exactly as  %s" % (why, CALL))
        return decide("deny", "Terminal-Only auto-shell: the %s tool is not used in a Terminal-Only project (%s); do this through a harness script (read with @PROBE or @GREP, edit with @FILE hunks), sent exactly as  %s" % (tool or "requested", root, CALL))
    except Exception as e:
        if root:
            sys.stderr.write("llm_harness: the tool check failed in a Terminal-Only project, so the call is blocked: %s\n" % e)
            return 2
        return 0


if __name__ == "__main__":
    sys.exit(main())
