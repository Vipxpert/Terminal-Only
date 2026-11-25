# /llm_harness/tests/rule_tag_test.py
"""Rule-tag test for llm_harness: the chat-browser flow shows the (chat) version of [L1-Harness] (the manifest rule) and not the (agent) one; agent mode (LLM_HARNESS_AGENT) shows the (agent) version and not the manifest rule."""
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
    text = "\n".join(["@SCRIPT [C: tag %d]" % COUNT[0], "@WORKSPACE " + ws, "@SESSION alpha | alpha work", "@LIST_DIR /"]) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120, env=env)
    out = p.stdout.decode("utf-8", "replace").replace("\r", "")
    return out[out.find("=== L1 CONTRACT"):]


def main():
    ws = tempfile.mkdtemp(prefix="harness-tag-")
    chat = run(ws, CHAT)
    check("the chat flow shows the manifest version of [L1-Harness] and not the agent one", "Here's the script [" in chat and "plain conversational prose" not in chat, chat[:1200])
    agent = run(ws, AGENT)
    check("agent mode shows the agent version of [L1-Harness] and not the manifest rule", "plain conversational prose" in agent and "Here's the script [" not in agent, agent[:1200])
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
