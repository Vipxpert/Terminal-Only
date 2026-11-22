# /llm_harness/tests/run_cutoff_test.py
"""Cut-off command test for llm_harness: an @RUN is one line, so a line that is not a directive directly after it means the command was probably cut at a line break; it is then not run, because its first line alone could do something else, and the run says so. A one-line @RUN, and one followed by a blank line, a comment or a directive, runs as before."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []
COUNT = [0]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def run(ws, *lines):
    COUNT[0] += 1
    text = "\n".join(["@SCRIPT [C: cutoff %d]" % COUNT[0], "@WORKSPACE " + ws] + list(lines)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "").split("=== L1 CONTRACT")[0]


def main():
    ws = tempfile.mkdtemp(prefix="harness-cutoff-")
    out = run(ws, "@RUN python -c \"print('fir' + 'st line ran')\"", "print('second line of the same command')", "@LIST_DIR /")
    check("a command followed by a line that is not a directive is not run, and the run says it was cut off", "first line ran" not in out and "cut off" in out, out)
    out = run(ws, "@RUN python -c \"print('co' + 'ntrol ran')\"", "@LIST_DIR /")
    check("control: a one-line @RUN followed by a directive runs", "control ran" in out and "cut off" not in out, out)
    out = run(ws, "@RUN python -c \"print('com' + 'mented ran')\"", "# a comment right after it", "@LIST_DIR /")
    check("an @RUN followed by a comment runs", "commented ran" in out and "cut off" not in out, out)
    out = run(ws, "@RUN python -c \"print('spa' + 'ced ran')\"", "", "@LIST_DIR /")
    check("an @RUN followed by a blank line runs", "spaced ran" in out and "cut off" not in out, out)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
