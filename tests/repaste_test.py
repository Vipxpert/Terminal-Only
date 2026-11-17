# /llm_harness/tests/repaste_test.py
"""Re-paste test for llm_harness: pasting a script that already ran asks, at a terminal, whether to replay it, undo it with the rest of that chat's later scripts, or execute it again; without a terminal it simply replays."""
import os, subprocess, sys, tempfile, time

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-repaste-")
GWS = tempfile.mkdtemp(prefix="harness-repaste-git-")
RESULTS = []


def payload(ws, title, session, *lines):
    return "\n".join(["@SCRIPT [%s]" % title, "@SESSION " + session, "@WORKSPACE " + ws] + list(lines) + [""])


def run(text):
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.stdout.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def run_tty(text, keys, limit=20):
    """Run the harness with the script on stdin and a pseudo-terminal for its questions; each line of keys answers the next question once it appears; killed after limit seconds."""
    import pty, select, signal, time
    path = os.path.join(tempfile.mkdtemp(), "payload.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    pid, fd = pty.fork()
    if pid == 0:
        os.dup2(os.open(path, os.O_RDONLY), 0)
        os.execv(sys.executable, [sys.executable, HARNESS])
    answers = keys.split("\n")[:-1] if keys else []
    out, mark, end = b"", 0, time.time() + limit
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.3)
        if r:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
        tail = out[mark:].decode("utf-8", "replace").rstrip(" ")
        if answers and (tail.endswith(">") or tail.endswith("(y/n)") or tail.endswith("skip):")):
            os.write(fd, (answers.pop(0) + "\n").encode())
            mark = len(out)
    else:
        os.kill(pid, signal.SIGKILL)
    os.waitpid(pid, 0)
    return out.decode("utf-8", "replace").split("=== L1 CONTRACT")[0].replace("\r", "")


def exists(ws, rel):
    return os.path.exists(os.path.join(ws, rel))


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-700:].replace("\n", "\n    "))


def main():
    first = payload(WS, "C: create a", "alpha", "@SCOPE work | a.txt", "@NEW_FILE /a.txt", "first version", "@END_NEW_FILE")
    run(first)
    run(payload(WS, "C: change a", "alpha", "@SCOPE work | a.txt", "@FILE /a.txt", "@HUNK TOP | change", "--- [OLD CODE] ---", "first version", "+++ [NEW CODE] +++", "second version", "=== [END HUNK] ==="))
    run(payload(WS, "C: create b", "beta", "@SCOPE work | b.txt", "@NEW_FILE /b.txt", "other chat", "@END_NEW_FILE"))
    out = run(first)
    check("without a terminal a re-paste just replays", "[REPLAY]" in out and "This script already ran" not in out, out)
    if os.name == "nt":
        print("SKIP terminal checks: they need a POSIX pseudo-terminal; on Windows try it by hand")
        print("test workspace: " + WS)
        sys.exit(0 if all(RESULTS) else 1)
    out = run_tty(first, "\n")
    check("at a terminal the question appears and Enter replays", "This script already ran" in out and "[REPLAY]" in out, out)
    out = run_tty(first, "U\nn\n")
    check("undo shows its preview and 'n' changes nothing", "=== UNDO FROM SCRIPT" in out and "[UNDO CANCELLED]" in out and exists(WS, "a.txt"), out)
    out = run_tty(first, "U\ny\n")
    check("'U' then 'y' undoes that script and this chat's later ones", not exists(WS, "a.txt") and "[RESTORED]" in out, out)
    check("another chat's work is left alone", exists(WS, "b.txt"), out)
    probe = payload(WS, "P: look", "alpha", "@GREP other chat")
    run(probe)
    out = run_tty(probe, "E\n")
    check("'E' executes the script again under a new number", "[EXECUTE AGAIN]" in out and "[ASSIGNED] P-" in out and "/b.txt:" in out, out)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=GWS)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=GWS)
    subprocess.run(["git", "config", "user.name", "t"], cwd=GWS)
    make = payload(GWS, "C: create c", "alpha", "@SCOPE work | c.txt", "@NEW_FILE /c.txt", "committed text", "@END_NEW_FILE")
    run(make)
    run(payload(GWS, "G: commit c", "alpha", "@GIT_COMMIT chore: c", "/c.txt", "@END_GIT_COMMIT"))
    out = run_tty(make, "U\ny\n")
    check("committed scripts are kept and named", "[KEPT]" in out and exists(GWS, "c.txt"), out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
