# /llm_harness/tests/chat_link_test.py
"""Chat-address test for llm_harness: a session can carry its chat's address, which the session list and every refusal involving that session show, so the user can find the other chat again."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-link-")
RESULTS = []
STEP = [0]
LINK = "https://chat.example/c/alpha-123"


def run(session, *lines, footer=False):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0], "@SESSION " + session, "@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, HARNESS], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout.decode("utf-8", "replace").replace("\r", "")
    return out if footer else out.split("=== L1 CONTRACT")[0]


def user(*args):
    p = subprocess.run([sys.executable, HARNESS, "--workspace", WS] + list(args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.stdout.decode("utf-8", "replace")


def run_tty(text, keys, limit=20):
    """Run the harness with the script on stdin and a pseudo-terminal for its questions; each line of keys answers the next question once it appears; killed after limit seconds."""
    import pty, select, signal, time
    path = os.path.join(tempfile.mkdtemp(), "payload.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    pid, fd = pty.fork()
    if pid == 0:
        os.dup2(os.open(path, os.O_RDONLY), 0)
        os.execve(sys.executable, [sys.executable, HARNESS], dict(os.environ, LLM_HARNESS_NO_COPY="1"))
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
        if answers and (tail.endswith(">") or tail.endswith("(y/n)") or tail.endswith("bar:") or tail.endswith("again:") or tail.endswith("one):") or tail.endswith("address:")):
            os.write(fd, (answers.pop(0) + "\n").encode())
            mark = len(out)
    else:
        os.kill(pid, signal.SIGKILL)
    os.waitpid(pid, 0)
    return out.decode("utf-8", "replace").replace("\r", "")


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-700:].replace("\n", "\n    "))


def main():
    link = LINK.replace("@@", "")
    with open(os.path.join(WS, "a.txt"), "w") as f:
        f.write("first line here\n")
    out = run("alpha | work on a", "@SCOPE edit a | a.txt")
    check("without a terminal no address question is asked", "needs its address" not in out, out)
    out = user("--link", "alpha", link)
    check("the user's --link command stores a chat address", "LINKED: session alpha" in out, out)
    out = user("--link", "nobody", link)
    check("--link refuses an unknown session", "no session named nobody" in out, out)
    out = run("beta | other work", "@FILE /a.txt", "@HUNK TOP | e", "--- [OLD CODE] ---", "first line here", "+++ [NEW CODE] +++", "changed line", "=== [END HUNK] ===")
    check("a refused change shows the owner's chat address", "inside session alpha's scope" in out and "(chat: %s)" % link in out, out)
    out = run("beta | other work", "@SCOPE overlap | a.txt")
    check("a refused scope shows the other chat's address", "[SCOPE REFUSED]" in out and "(chat: %s)" % link in out, out)
    check("the session list shows the address", "chat: %s" % link in out, out)
    if os.name == "nt":
        print("SKIP terminal checks: they need a POSIX pseudo-terminal; on Windows try it by hand")
    else:
        script = lambda n: "\n".join(["@SCRIPT [P: look %d]" % n, "@SESSION gamma | g", "@WORKSPACE " + WS, "@GREP first line", ""])
        out = run_tty(script(1), link.replace("alpha-123", "gamma") + "\n")
        check("at a terminal a new session is asked once for its chat address", "needs its address" in out, out)
        out = run_tty(script(2), "")
        check("the address is kept and not asked for again", "needs its address" not in out and "chat: " + link.replace("alpha-123", "gamma") in out, out)
        delta = lambda n: "\n".join(["@SCRIPT [P: delta %d]" % n, "@SESSION delta | d", "@WORKSPACE " + WS, "@GREP first line", ""])
        out = run_tty(delta(1), "not an address\n" * 5)
        check("an answer that is not a web address is not saved", "[NOT SAVED]" in out and "chat: not an address" not in out, out)
        out = run_tty(delta(2), "\n" * 5)
        check("after an invalid answer the question comes again", "needs its address" in out, out)
    out = run("alpha | work on a", "@CHAT_LINK https://chat.example/c/alpha-NEW")
    check("@CHAT_LINK replaces a wrong address and says what it replaced", "[CHAT LINK] alpha -> https://chat.example/c/alpha-NEW" in out and "(was %s)" % LINK in out, out)
    out = run("beta | other work", "@SCOPE overlap two | a.txt")
    check("the new address is the one other chats show", "(chat: https://chat.example/c/alpha-NEW)" in out and LINK not in out, out)
    out = run("alpha | work on a", "@CHAT_LINK banana")
    check("an address that is not a web address is refused and the old one stays", "[CHAT LINK REFUSED]" in out and "chat: https://chat.example/c/alpha-NEW" in run("beta | other work", "@SCOPE overlap three | a.txt"), out)
    out = run("alpha | work on a", "@CHAT_LINK")
    check("without an address and without a terminal it says what is on file and how to change it", "current: https://chat.example/c/alpha-NEW" in out and "@CHAT_LINK <address>" in out, out)
    STEP[0] += 1
    p = subprocess.run([sys.executable, HARNESS], input=("@SCRIPT [C: step %d]\n@WORKSPACE %s\n@CHAT_LINK https://chat.example/c/x\n" % (STEP[0], WS)).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = p.stdout.decode("utf-8", "replace")
    check("@CHAT_LINK needs a session", "needs an @SESSION line" in text, text)
    if os.name != "nt":
        scr = lambda n, *extra: "\n".join(["@SCRIPT [P: look %d]" % n, "@SESSION delta | d", "@WORKSPACE " + WS] + list(extra) + ["@GREP first line", ""])
        out = run_tty(scr(10), "\nnope\nhttps://chat.example/c/delta\n")
        check("at a terminal the address cannot be skipped: Enter and a wrong answer ask again", out.count("not a web address") >= 2 and "needs its address" in out, out)
        out = run_tty(scr(11), "")
        check("once given it is kept", "needs its address" not in out and "chat: https://chat.example/c/delta" in out, out)
        out = run_tty(scr(12, "@CHAT_LINK"), "https://chat.example/c/delta2\n")
        check("a bare @CHAT_LINK at a terminal asks for the new address", "[CHAT LINK] delta -> https://chat.example/c/delta2" in out, out)
        out = run_tty(scr(13, "@CHAT_LINK"), "bad-url\nhttps://chat.example/c/delta3\n")
        check("a bare @CHAT_LINK retries an invalid address and saves the valid one", "not a web address" in out and "[CHAT LINK] delta -> https://chat.example/c/delta3" in out, out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
