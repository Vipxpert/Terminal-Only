# /llm_harness/tests/note_pin_all_test.py
"""Note-pin test for llm_harness: a plain note and a note pinned with * reach a chat that appeared after they were written, while a note pinned to one chat stays out of the footer of another."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def run(ws, title, *lines):
    text = "\n".join(["@SCRIPT [C: %s]" % title, "@WORKSPACE " + ws] + list(lines)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def notes(out):
    return [l[:160] for l in out.split("\n") if "NOTE" in l or "zz" in l]


def main():
    ws = tempfile.mkdtemp(prefix="harness-notepin-")
    added = run(ws, "alpha adds", "@SESSION alpha | alpha work", "@NOTE_ADD zzplain note for everyone", "@NOTE_ADD pin * | zzstar note pinned to all", "@NOTE_ADD pin alpha | zzonly note pinned to alpha")
    late = run(ws, "omega late", "@SESSION omega | omega work", "@LIST_DIR /")
    alpha = run(ws, "alpha again", "@SESSION alpha | alpha work", "@LIST_DIR /")
    check("a plain note reaches a chat that appeared later", "zzplain" in late, notes(added) + notes(late))
    check("a note pinned with * reaches a chat that appeared later", "zzstar" in late, notes(added) + notes(late))
    check("a note pinned to alpha stays out of omega's footer and is in alpha's", "zzonly" not in late and "zzonly" in alpha, notes(late) + notes(alpha))
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
