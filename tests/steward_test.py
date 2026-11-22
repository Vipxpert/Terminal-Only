# /llm_harness/tests/steward_test.py
"""Steward test for llm_harness: the backlog and review rule is printed only where the user switched stewardship on with their own terminal command (kept per project on this machine), switching it off removes it again, and a script cannot switch it."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def run(ws, title, *extra):
    text = "\n".join(["@SCRIPT [C: %s]" % title, "@WORKSPACE " + ws, "@SESSION steward-test | steward test", "@LIST_DIR /"] + list(extra)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def steward(ws, *words):
    p = subprocess.run([sys.executable, HARNESS, "--workspace", ws, "--steward"] + list(words), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def main():
    ws = tempfile.mkdtemp(prefix="harness-steward-")
    off = run(ws, "default")
    check("by default the footer has no steward rule and says nothing about the backlog", "[L1-Steward]" not in off and "docs/backlog.md" not in off, [l[:160] for l in off.split("\n") if "backlog" in l or "L1-Steward" in l])
    report = steward(ws)
    check("--steward alone reports that it is off and changes nothing", "STEWARDSHIP IS OFF" in report, report)
    switched = steward(ws, "on")
    check("--steward on switches it on and says so", "STEWARDSHIP IS ON" in switched, switched)
    on = run(ws, "switched on")
    check("with it on, the footer carries the rule with the backlog and the review", "[L1-Steward]" in on and "docs/backlog.md" in on and "@PLAYBOOK review" in on, [l[:160] for l in on.split("\n") if "backlog" in l or "L1-Steward" in l])
    steward(ws, "off")
    check("switching it off removes the rule again", "[L1-Steward]" not in run(ws, "switched off"))
    out = run(ws, "attempt", '@RUN python "%s" --workspace "%s" --steward on' % (HARNESS, ws))
    check("a script that runs --steward is refused and changes nothing", "[REFUSED]" in out and "STEWARDSHIP IS OFF" in steward(ws), out)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
