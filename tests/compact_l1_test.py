# /llm_harness/tests/compact_l1_test.py
"""Compaction-aware L1 test: footer-only anchor (no AI echo), clean-turn omission, @L1_REFRESH reason/certainty reporting, --compacted host hook, periodic safety refresh, and --compact off."""
import os, re, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []
COUNT = [0]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def run(ws, session, *lines, env_extra=None):
    COUNT[0] += 1
    text = "\n".join(["@SCRIPT [P: compact %d]" % COUNT[0], "@WORKSPACE " + ws, "@SESSION %s | test compact L1" % session] + list(lines)) + "\n"
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120, env=env)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def extract_anchor(out):
    m = re.search(r"anchor:\s*(\d+-[0-9a-f]{6})", out)
    return m.group(1) if m else ""


def main():
    ws = tempfile.mkdtemp(prefix="harness-compact-")
    t1 = run(ws, "alpha", "@LIST_DIR /")
    anc1 = extract_anchor(t1)
    check("Turn 1 prints full L1, ephemeral footer anchor, and [L1-Syntax]", bool(anc1) and "[L1-Harness]" in t1 and "[L1-Compact] full L1 printed" in t1 and "omit from conversation summaries" in t1 and "[L1-Syntax] @PROBE /file | Scope | symbol" in t1, t1)

    t2 = run(ws, "alpha", "@LIST_DIR /")
    check("Turn 2 omits all unchanged L1 rules with zero AI echo and keeps same anchor", "[L1-Harness]" not in t2 and ("anchor: %s" % anc1) in t2 and "turn 1/40 since full L1" in t2 and "[L1-Syntax] @PROBE /file | Scope | symbol" in t2, t2)

    t3 = run(ws, "alpha", "@L1_REFRESH anchor %s missing from raw history + summary header | High" % anc1, "@LIST_DIR /")
    anc2 = extract_anchor(t3)
    check("@L1_REFRESH with reason & certainty prints [COMPACTION DETECTED — AI report], restores full L1, and rotates anchor", bool(anc2) and anc2 != anc1 and "[COMPACTION DETECTED — AI report] anchor %s missing" % anc1 in t3 and "[L1-Harness]" in t3, t3)

    cp = subprocess.run([sys.executable, HARNESS, "--workspace", ws, "--compacted", "alpha", "PreCompact hook fired | High"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60).stdout.decode("utf-8", "replace")
    t4 = run(ws, "alpha", "@LIST_DIR /")
    anc3 = extract_anchor(t4)
    check("--compacted records reason and next run prints [COMPACTION DETECTED — host hook] + rotates anchor", "COMPACTED:" in cp and bool(anc3) and anc3 != anc2 and "[COMPACTION DETECTED — host hook] PreCompact hook fired | High" in t4 and "[L1-Harness]" in t4, cp + t4)

    t5 = run(ws, "alpha", "@LIST_DIR /", env_extra={"LLM_HARNESS_COMPACT_MAX_TURNS": "3"})
    t6 = run(ws, "alpha", "@LIST_DIR /", env_extra={"LLM_HARNESS_COMPACT_MAX_TURNS": "3"})
    t7 = run(ws, "alpha", "@LIST_DIR /", env_extra={"LLM_HARNESS_COMPACT_MAX_TURNS": "3"})
    anc4 = extract_anchor(t7)
    check("periodic safety ceiling reprints full L1 with Scheduled banner (not false-positive compaction) and rotates anchor", "[L1-Harness]" not in t5 and "[L1-Harness]" not in t6 and "[L1 PERIODIC REFRESH] 3 clean turns elapsed" in t7 and "[L1-Harness]" in t7 and bool(anc4) and anc4 != anc3, t5 + "\n---\n" + t6 + "\n---\n" + t7)

    sw = subprocess.run([sys.executable, HARNESS, "--workspace", ws, "--compact", "off"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60).stdout.decode("utf-8", "replace")
    check("--compact off disables compaction-aware L1", "COMPACTION-AWARE L1 IS OFF" in sw, sw)

    t8 = run(ws, "alpha", "@LIST_DIR /")
    check("with --compact off, subsequent turns print full L1 without [L1-Compact]", "[L1-Harness]" in t8 and "\n[L1-Compact]" not in t8, t8)

    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
