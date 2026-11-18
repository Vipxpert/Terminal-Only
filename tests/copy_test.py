# /llm_harness/tests/copy_test.py
"""Copy test for llm_harness: at a real terminal the harness waits for a key after a run: C copies the whole output to the clipboard through the system's tool (checked here with a stand-in xclip), X skips, other keys are ignored; nothing waits when the output is captured."""
import importlib.util, os, subprocess, sys, tempfile, time

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-copy-")
FAKE = tempfile.mkdtemp(prefix="harness-copy-bin-")
CLIP = os.path.join(FAKE, "clipboard.txt")
RESULTS = []
STEP = [0]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-800:].replace("\n", "\n    "))


def script():
    STEP[0] += 1
    return "@SCRIPT [P: step %d]\n@WORKSPACE %s\n@GREP nothing\n" % (STEP[0], WS)


def pty_run(answer):
    import pty, select
    path = os.path.join(FAKE, "script%d.txt" % STEP[0])
    with open(path, "w") as f:
        f.write(script())
    env = dict(os.environ, PATH=FAKE, LLM_TEST_CLIP=CLIP)
    env.pop("LLM_HARNESS_NO_COPY", None)
    env.pop("LLM_HARNESS_NO_PROMPT", None)
    pid, master = pty.fork()
    if pid == 0:
        os.dup2(os.open(path, os.O_RDONLY), 0)
        os.execve(sys.executable, [sys.executable, HARNESS], env)
    buf, sent, deadline = b"", False, time.time() + 40
    while time.time() < deadline:
        ready, _, _ = select.select([master], [], [], 1)
        if not ready:
            continue
        try:
            chunk = os.read(master, 65536)
        except OSError:
            break
        if not chunk:
            break
        buf += chunk
        if not sent and b"Press C to copy" in buf:
            os.write(master, answer)
            sent = True
    os.waitpid(pid, 0)
    return buf.decode("utf-8", "replace")


def main():
    if os.name == "nt":
        print("SKIP the clipboard checks use a stand-in xclip and a pseudo-terminal; on Windows try them by hand")
        sys.exit(0)
    with open(os.path.join(FAKE, "xclip"), "w") as f:
        f.write('#!/bin/sh\n/bin/cat > "$LLM_TEST_CLIP"\n')
    os.chmod(os.path.join(FAKE, "xclip"), 0o755)
    os.environ["PATH"], os.environ["LLM_TEST_CLIP"] = FAKE, CLIP
    spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS)
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    sample = "h\u00e9llo \u2014 \u251c\u2500\u2500 line two\n"
    ok, how = hh.copy_to_clipboard(sample)
    with open(CLIP, "rb") as f:
        got = f.read()
    check("the clipboard tool receives the text exactly, accents and box glyphs included", ok and how == "xclip" and got == sample.encode("utf-8"), "%s %s %r" % (ok, how, got))
    os.remove(CLIP)
    p = subprocess.run([sys.executable, HARNESS], input=script().encode(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60, env=dict(os.environ))
    check("captured output never waits for Enter and never copies", p.returncode == 0 and b"Press Enter" not in p.stdout and not os.path.exists(CLIP), p.stdout.decode("utf-8", "replace"))
    out = pty_run(b"c")
    with open(CLIP, "rb") as f:
        copied = f.read().decode("utf-8", "replace")
    check("at a terminal, one press of C copies the whole run output (no Enter needed)", "[COPIED]" in out and "=== RUN TIME" in copied and "=== GREP: nothing" in copied, out + copied)
    os.remove(CLIP)
    out = pty_run(b"x")
    check("X skips the copy", "Press C to copy" in out and "[COPIED]" not in out and not os.path.exists(CLIP), out)
    out = pty_run(b"\nzqc")
    with open(CLIP, "rb") as f:
        copied = f.read().decode("utf-8", "replace")
    check("Enter and other keys are ignored until C or X is pressed", "[COPIED]" in out and "=== RUN TIME" in copied, out + copied)
    os.remove(CLIP)
    out = pty_run(b"\x1b")
    check("Esc skips the copy too", "[COPIED]" not in out and not os.path.exists(CLIP), out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
