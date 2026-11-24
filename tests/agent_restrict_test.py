# /llm_harness/tests/agent_restrict_test.py
"""Agent-restriction test for llm_harness: in agent mode a terminal question gets no answer at once, @RUN runs only an allowlisted program with matching arguments and no shell (shell operators refused), and git changes are refused; the chat-browser flow runs @RUN through the shell as before."""
import importlib.util, os, subprocess, sys, tempfile

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


def run(ws, env, *lines):
    COUNT[0] += 1
    text = "\n".join(["@SCRIPT [C: restrict %d]" % COUNT[0], "@WORKSPACE " + ws, "@SESSION alpha | alpha work"] + list(lines)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120, env=env)
    return p.stdout.decode("utf-8", "replace").replace("\r", "").split("=== L1 CONTRACT")[0]


def main():
    spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS)
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    import threading
    real, os.environ["LLM_HARNESS_AGENT"] = os.isatty, "test-host"
    os.isatty = lambda fd: True
    box = []
    worker = threading.Thread(target=lambda: box.append(hh.ask_console("(agent_restrict_test: if you can read this the agent-mode guard failed; press Enter) ")), daemon=True)
    try:
        worker.start()
        worker.join(5)
    finally:
        os.isatty = real
        del os.environ["LLM_HARNESS_AGENT"]
    check("in agent mode a terminal question gets no answer at once (nothing waits on a hidden console)", not worker.is_alive() and box == [None], box)
    ws = tempfile.mkdtemp(prefix="harness-agentr-")
    out = run(ws, AGENT, "@RUN python -V")
    check("agent mode refuses @RUN when the command is not on the allowlist", "runs only commands on this project's allowlist" in out and "Python 3" not in out, out)
    out = run(ws, CHAT, "@RUN python -V")
    check("the chat flow still runs it through the shell", "Python 3" in out and "allowlist" not in out, out)
    allow = subprocess.run([sys.executable, HARNESS, "--workspace", ws, "--agent-allow", "python", "-V"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60).stdout.decode("utf-8", "replace")
    out = run(ws, AGENT, "@RUN python -V")
    check("an allowlisted program with matching arguments runs, without a shell", "Python 3" in out and "allowlist" not in out, (allow, out))
    out = run(ws, AGENT, "@RUN python -V; echo hi")
    check("shell operators are refused even after an allowlisted program", "shell operators" in out, out)
    out = run(ws, AGENT, "@GIT_COMMIT feat: x", "/a.txt", "@END_GIT_COMMIT")
    check("agent mode refuses git changes", "[REFUSED] agent mode: git changes" in out, out)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
