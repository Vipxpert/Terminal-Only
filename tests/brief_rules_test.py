# /llm_harness/tests/brief_rules_test.py
"""Collapsed-rule test for llm_harness: a rule with a brief prints the brief normally and its full text, replacing the brief, when its condition holds (a failure in this run, an open debug ledger); @HELP L1-<name> prints any rule in full."""
import os, shutil, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
WS = tempfile.mkdtemp(prefix="harness-brief-")
INSTALL = tempfile.mkdtemp(prefix="harness-brief-install-")
RESULTS = []
STEP = [0]


def run(*lines):
    STEP[0] += 1
    head = ["@SCRIPT [C: step %d]" % STEP[0], "@SESSION alpha | try briefs", "@WORKSPACE " + WS]
    p = subprocess.run([sys.executable, os.path.join(INSTALL, "harness.py")], input="\n".join(head + list(lines) + [""]).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def footer(out):
    return out.split("=== L1 CONTRACT")[-1]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + out[-900:].replace("\n", "\n    "))


def main():
    shutil.copy(HARNESS, os.path.join(INSTALL, "harness.py"))
    with open(os.path.join(INSTALL, "workflow_commands.txt"), "w", encoding="utf-8") as f:
        f.write("- **L1 Rule \u2014 `[L1-Alpha]`:** `the full alpha rule with every detail`\n"
                "- **L1 Rule \u2014 `[L1-Beta]`:** `beta always in full`\n"
                "- **L1 Brief \u2014 `[L1-Alpha]` (failed, ledger):** `short alpha`\n")
    with open(os.path.join(WS, "a.txt"), "w") as f:
        f.write("some text here\n")
    out = footer(run("@GREP some"))
    check("normally the brief replaces the full rule", "[L1-Alpha] (brief; full rule: @HELP L1-Alpha) short alpha" in out and "every detail" not in out and "beta always in full" in out, out)
    out = footer(run("@FILE /a.txt", "@HUNK TOP | e", "--- [OLD CODE] ---", "text that is not there", "+++ [NEW CODE] +++", "x", "=== [END HUNK] ==="))
    check("a failed change expands it, replacing the brief", "[L1-Alpha] (expanded: this run had a failure) the full alpha rule with every detail" in out and "short alpha" not in out, out)
    out = footer(run("@RUN exit 3"))
    check("a failed command expands it too", "(expanded: this run had a failure)" in out, out)
    os.makedirs(os.path.join(WS, "docs", "debug"))
    with open(os.path.join(WS, "docs", "debug", "bug_freeze.txt"), "w") as f:
        f.write("# Stage: Symptom\nvideo freezes\n")
    out = footer(run("@GREP some"))
    check("an open debug ledger expands it", "(expanded: 1 open debug ledger)" in out, out)
    with open(os.path.join(WS, "docs", "debug", "bug_freeze.txt"), "a") as f:
        f.write("RESOLVED by P-12\n")
    out = footer(run("@GREP some"))
    check("a resolved ledger lets it collapse again, without a [CHANGED] mark", "(brief; full rule: @HELP L1-Alpha)" in out and "[CHANGED]" not in out, out)
    out = run("@HELP L1-Alpha")
    check("@HELP L1-<name> prints the rule in full", "=== HELP: L1-ALPHA (full rule) ===" in out and "the full alpha rule with every detail" in out.split("=== HELP: L1-ALPHA")[1].split("===")[1], out)
    print("test workspace: " + WS)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
