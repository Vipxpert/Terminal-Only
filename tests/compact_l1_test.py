# /llm_harness/tests/compact_l1_test.py
"""Compaction-aware L1 test: ON by default (opt out with --compact off), Turn 1 prints full L1, Turn 2+ omits unchanged untriggered rules while keeping [L1-Compact] and [L1-Syntax] visible, and @L1_REFRESH restores full L1."""
import os, re, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []
COUNT = [0]


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def run(ws, session, *lines):
    COUNT[0] += 1
    text = "\n".join(["@SCRIPT [P: compact %d]" % COUNT[0], "@WORKSPACE " + ws, "@SESSION %s | test compact L1" % session] + list(lines)) + "\n"
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.stdout.decode("utf-8", "replace").replace("\r", "")


def extract_proof(out):
    m = re.search(r"proof:\s*([0-9a-f]{6})", out)
    return m.group(1) if m else ""


def main():
    ws = tempfile.mkdtemp(prefix="harness-compact-")
    t1 = run(ws, "alpha", "@LIST_DIR /")
    tok1 = extract_proof(t1)
    check("Turn 1 prints full L1, proof token, and [L1-Syntax]", bool(tok1) and "[L1-Harness]" in t1 and "[L1-Compact] full L1 printed" in t1 and "[L1-Syntax] @PROBE /file | Scope | symbol" in t1, t1)

    t2 = run(ws, "alpha", "@L1_PROOF " + tok1, "@LIST_DIR /")
    check("Turn 2 with valid @L1_PROOF omits unchanged L1 rules", "[L1-Harness]" not in t2 and ("proof %s verified" % tok1) in t2 and "[L1-Syntax] @PROBE /file | Scope | symbol" in t2, t2)

    t3 = run(ws, "alpha", "@LIST_DIR /")
    tok2 = extract_proof(t3)
    check("missing @L1_PROOF (silent compaction) auto-restores full L1 and rotates token", bool(tok2) and tok2 != tok1 and "[L1-Harness]" in t3 and "proof missing or mismatched" in t3, t3)

    t4 = run(ws, "alpha", "@L1_PROOF dead00", "@LIST_DIR /")
    tok3 = extract_proof(t4)
    check("wrong @L1_PROOF auto-restores full L1 and rotates token", bool(tok3) and tok3 != tok2 and "[L1-Harness]" in t4 and "proof missing or mismatched" in t4, t4)

    t5 = run(ws, "alpha", "@L1_REFRESH", "@LIST_DIR /")
    tok4 = extract_proof(t5)
    check("@L1_REFRESH restores full L1 on demand with fresh token", bool(tok4) and "[L1-Harness]" in t5 and "[L1-Compact] full L1 printed" in t5, t5)

    cp = subprocess.run([sys.executable, HARNESS, "--workspace", ws, "--compacted", "alpha"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60).stdout.decode("utf-8", "replace")
    t6 = run(ws, "alpha", "@L1_PROOF " + tok4, "@LIST_DIR /")
    check("--compacted clears proof so next run restores full L1 even with old token", "COMPACTED:" in cp and "[L1-Harness]" in t6, cp + t6)

    sw = subprocess.run([sys.executable, HARNESS, "--workspace", ws, "--compact", "off"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60).stdout.decode("utf-8", "replace")
    check("--compact off disables compaction-aware L1", "COMPACTION-AWARE L1 IS OFF" in sw, sw)

    t7 = run(ws, "alpha", "@LIST_DIR /")
    check("with --compact off, subsequent turns print full L1 without [L1-Compact]", "[L1-Harness]" in t7 and "[L1-Compact]" not in t7, t7)

    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
