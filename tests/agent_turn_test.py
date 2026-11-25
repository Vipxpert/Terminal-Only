# /llm_harness/tests/agent_turn_test.py
"""Agent-turn test for llm_harness: without LLM_HARNESS_AGENT (the chat-browser flow) every footer prints the full standing rules; with it, the first run of a prompt turn briefs them and later runs in the turn say they are not repeated; the same --new-turn event counts once, and a new one briefs again."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []
COUNT = [0]
AGENT = dict(os.environ, LLM_HARNESS_AGENT="test-host", LLM_HARNESS_HOST_SESSION="h1")
CHAT = {k: v for k, v in os.environ.items() if k != "LLM_HARNESS_AGENT"}


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def run(ws, env):
    COUNT[0] += 1
    text = "\n".join(["@SCRIPT [C: turn %d]" % COUNT[0], "@WORKSPACE " + ws, "@SESSION alpha | alpha work", "@LIST_DIR /"]) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120, env=env)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def turn(ws, event):
    return subprocess.run([sys.executable, HARNESS, "--workspace", ws, "--new-turn", event], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60, env=AGENT).stdout.decode("utf-8", "replace")


def main():
    ws = tempfile.mkdtemp(prefix="harness-turn-")
    subprocess.run([sys.executable, HARNESS, "--workspace", ws, "--compact", "off"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    a, b = run(ws, CHAT), run(ws, CHAT)
    check("the chat flow prints the full standing rules on every run", "[L1-Scope]" in a and "[L1-Scope]" in b and "agent turn" not in b, b[-600:])
    turn(ws, "e1")
    first, second = run(ws, AGENT), run(ws, AGENT)
    check("agent mode briefs once per turn, then says the rules are not repeated", "[L1-Scope]" in first and "[L1-Scope]" not in second and "not repeated" in second, (first[-400:], second[-600:]))
    again = turn(ws, "e1")
    third = run(ws, AGENT)
    check("the same event id does not start a second turn", "continues" in again and "[L1-Scope]" not in third, (again, third[-400:]))
    turn(ws, "e2")
    fourth = run(ws, AGENT)
    check("a new prompt turn briefs the full rules again", "[L1-Scope]" in fourth, fourth[-600:])
    out = run(ws, AGENT)
    mapped = turn(ws, "e3")
    check("the session line shows the host session, and a new turn names the harness session it maps to", "| host: test-host session h1" in out and "harness session: alpha" in mapped, (out[-1500:], mapped))
    oc = {k: v for k, v in os.environ.items() if k not in ("LLM_HARNESS_HOST_SESSION", "LLM_HARNESS_HOST", "CLAUDE_CODE_SESSION_ID")}
    oc.update(LLM_HARNESS_AGENT="1", OPENCODE_SESSION_ID="oc1")
    out = run(ws, oc)
    check("an OpenCode shell (LLM_HARNESS_AGENT=1 with OPENCODE_SESSION_ID) is recorded as host opencode", "| host: opencode session oc1" in out, out[-1500:])
    cc = {k: v for k, v in os.environ.items() if k not in ("LLM_HARNESS_AGENT", "LLM_HARNESS_HOST", "LLM_HARNESS_HOST_SESSION", "OPENCODE_SESSION_ID")}
    cc["CLAUDE_CODE_SESSION_ID"] = "cc1"
    out = run(ws, cc)
    check("inside Claude Code (CLAUDE_CODE_SESSION_ID alone) the run is auto-shell for host claude-code", "| host: claude-code session cc1" in out, out[-1500:])
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
