# /llm_harness/tests/copy_test.py
"""Copy test for llm_harness: at a real terminal the harness waits for a key after a run: C or Enter copies the whole output to the clipboard through the system's tool (checked here with a stand-in xclip), X skips, other keys are ignored; nothing waits when the output is captured."""
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


def pty_run(answer, marker=b"to copy this output", text=None, extra=None):
    import pty, select
    path = os.path.join(FAKE, "script%d.txt" % STEP[0])
    with open(path, "w") as f:
        f.write(text or script())
    env = dict(os.environ, PATH=FAKE, LLM_TEST_CLIP=CLIP, **(extra or {}))
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
        if not sent and marker in buf:
            os.write(master, answer)
            sent = True
    os.waitpid(pid, 0)
    return buf.decode("utf-8", "replace")


def main():
    spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS)
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    tty_out = os.path.join(FAKE, "tty_osc52.bin")
    open(tty_out, "wb").close()
    old_tmux = os.environ.pop("TMUX", None)
    try:
        ok, how = hh.osc52_copy("hello \u2014 ssh".encode("utf-8"), tty_out)
        raw = open(tty_out, "rb").read()
        check("OSC 52 writes base64 UTF-8 clipboard sequence to the terminal", ok and "OSC 52" in how and raw == b"\033]52;c;aGVsbG8g4oCUHNzaA==\a" or raw == b"\033]52;c;" + hh.base64.b64encode("hello \u2014 ssh".encode("utf-8")) + b"\a", repr(raw))
        open(tty_out, "wb").close()
        os.environ["TMUX"] = "/tmp/tmux-1000/default,123,0"
        hh.osc52_copy(b"hi", tty_out)
        raw_tmux = open(tty_out, "rb").read()
        check("OSC 52 wraps sequence for tmux passthrough when TMUX is set", raw_tmux.startswith(b"\033Ptmux;\033\033]52;c;") and raw_tmux.endswith(b"\033\\"), repr(raw_tmux))
        f1, r1, t1 = hh.parse_focus_events(b"", True, "SSH terminal stayed focused")
        f2, r2, t2 = hh.parse_focus_events(b"\033[O", True, "SSH terminal stayed focused")
        f3, r3, t3 = hh.parse_focus_events(b"\033[Onoise\033[I\033[", True, "SSH terminal stayed focused")
        f4, r4, t4 = hh.parse_focus_events(b"", None, "")
        check("DECSET 1004 focus parser tracks stay-focused, focus-out (\\033[O), refocus (\\033[I), and split escape tails",
              (f1, r1, t1) == (True, "SSH terminal stayed focused", b"") and (f2, r2) == (False, "") and (f3, r3, t3) == (True, "terminal focus event", b"\033[") and f4 is None,
              repr([(f1, r1, t1), (f2, r2, t2), (f3, r3, t3), (f4, r4, t4)]))
        ws = tempfile.mkdtemp(prefix="harness-tok-")
        old_cwd = os.getcwd()
        try:
            os.chdir(ws)
            os.makedirs(".llm_harness", exist_ok=True)
            t_a, tot_a, p_a = hh.record_copied_tokens("x" * 400, replay=False)
            t_b, tot_b, p_b = hh.record_copied_tokens("y" * 200, replay=False)
            t_rep, tot_rep, p_rep = hh.record_copied_tokens("z" * 280, replay=True)
            m_json = hh.merge_tokens_text('{"tokens":100,"pastes":1,"chars":400}', '{"tokens":150,"pastes":2,"chars":600}', '{"tokens":180,"pastes":3,"chars":720}')
            check("token estimation persists project totals in .llm_harness/tokens.json, replaces on replay, and merges additively",
                  (t_a, tot_a, p_a) == (100, 100, 1) and (t_b, tot_b, p_b) == (50, 150, 2) and (t_rep, tot_rep, p_rep) == (70, 170, 2) and '"tokens": 230' in m_json,
                  repr([(t_a, tot_a, p_a), (t_b, tot_b, p_b), (t_rep, tot_rep, p_rep), m_json]))
        finally:
            os.chdir(old_cwd)
    finally:
        if old_tmux is not None:
            os.environ["TMUX"] = old_tmux
        else:
            os.environ.pop("TMUX", None)
    if os.name == "nt":
        print("SKIP the remaining PTY clipboard checks use a stand-in xclip and a pseudo-terminal; on Windows try them by hand")
        sys.exit(0 if all(RESULTS) else 1)
    for k in ("SSH_CONNECTION", "SSH_TTY"):
        os.environ.pop(k, None)
    with open(os.path.join(FAKE, "xclip"), "w") as f:
        f.write('#!/bin/sh\n/bin/cat > "$LLM_TEST_CLIP"\n')
    os.chmod(os.path.join(FAKE, "xclip"), 0o755)
    os.environ["PATH"], os.environ["LLM_TEST_CLIP"] = FAKE, CLIP
    open(tty_out, "wb").close()
    os.environ["SSH_CONNECTION"] = "10.0.0.1 55555 10.0.0.2 22"
    try:
        ok_ssh, how_ssh = hh.copy_to_clipboard("ssh clip", tty_out)
        check("over SSH, copy_to_clipboard uses OSC 52 instead of remote X11 xclip", ok_ssh and "OSC 52" in how_ssh and not os.path.exists(CLIP) and open(tty_out, "rb").read().startswith(b"\033]52;c;"), how_ssh)
    finally:
        os.environ.pop("SSH_CONNECTION", None)
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
    check("X skips the copy", "to copy this output" in out and "[COPIED]" not in out and not os.path.exists(CLIP), out)
    out = pty_run(b"zqc")
    with open(CLIP, "rb") as f:
        copied = f.read().decode("utf-8", "replace")
    check("other keys are ignored until C or X is pressed", "[COPIED]" in out and "=== RUN TIME" in copied, out + copied)
    os.remove(CLIP)
    out = pty_run(b"\n")
    with open(CLIP, "rb") as f:
        copied = f.read().decode("utf-8", "replace")
    check("Enter copies too", "[COPIED]" in out and "=== RUN TIME" in copied, out + copied)
    os.remove(CLIP)
    out = pty_run(b"\x1b")
    check("Esc skips the copy too", "[COPIED]" not in out and not os.path.exists(CLIP), out)
    STEP[0] += 1
    again = "@SCRIPT [C: replay %d]\n@WORKSPACE %s\n@NEW_FILE /marker.txt\nhello\n@END_NEW_FILE\n" % (STEP[0], WS)
    subprocess.run([sys.executable, HARNESS], input=again.encode(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60, env=dict(os.environ))
    if os.path.exists(CLIP):
        os.remove(CLIP)
    out = pty_run(b"\n", marker=b"replay its saved output", text=again)
    copied = open(CLIP, "rb").read().decode("utf-8", "replace") if os.path.exists(CLIP) else ""
    check("a replay copies at once, without the question", "[COPIED]" in out and "[REPLAY]" in copied and "Press C" not in out, out + copied)
    check("the walk up a process table finds every ancestor and survives a loop", hh.ancestors(5, {5: 4, 4: 3, 3: 0}) == {4, 3} and hh.ancestors(1, {1: 2, 2: 1}) == {1, 2}, "")
    if os.path.exists(CLIP):
        os.remove(CLIP)
    out = pty_run(b"", extra={"LLM_HARNESS_COPY": "auto"})
    copied = open(CLIP, "rb").read().decode("utf-8", "replace") if os.path.exists(CLIP) else ""
    check("LLM_HARNESS_COPY=auto copies without asking and says why", "[COPIED]" in out and "(without asking: LLM_HARNESS_COPY=auto)" in out and "to copy this output to the clipboard, X" not in out and "=== RUN TIME" in copied, out + copied)
    if os.path.exists(CLIP):
        os.remove(CLIP)
    out = pty_run(b"x", extra={"LLM_HARNESS_COPY": "ask"})
    check("LLM_HARNESS_COPY=ask always asks", "to copy this output to the clipboard, X" in out and "[COPIED]" not in out and not os.path.exists(CLIP), out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
