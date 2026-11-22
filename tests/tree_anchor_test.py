# /llm_harness/tests/tree_anchor_test.py
"""Tree-anchor test for llm_harness: the drift check recognises '# Stage:' comments decorated with a run of dashes and '#*' section headings as anchors, still reports an anchor that does not exist, and does not take a trailing comment for an anchor."""
import os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []
G = "\u251c\u2500\u2500 "


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def put(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main():
    ws = tempfile.mkdtemp(prefix="harness-anchor-")
    proj = os.path.basename(ws)
    put(ws, "code.py", "x = 1\n# ------------------------------------ Stage: Alpha\ndef f():\n    pass\nvalue = 2  # Stage: Hidden\n# Stagecoach is not a stage\n")
    put(ws, "notes.txt", "#* Section Beta [extra words]\ntext\n")
    tree = "/%s (demo)\n%scode.py (code)\n    %s# Stage: Alpha (decorated with dashes)\n    %s# Stage: Missing (not in the file)\n    %s# Stage: Hidden (only in a trailing comment)\n%snotes.txt (rules)\n    %s#* Section Beta (a hash-star heading)\n" % (proj, G, G, G, G, G, G)
    put(ws, "docs/trees/tree_anchor.txt", tree)
    text = "@SCRIPT [C: anchors]\n@WORKSPACE %s\n@PROBE /docs/trees/tree_anchor.txt | Check\n" % ws
    p = subprocess.run([sys.executable, HARNESS], input=text.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    out = p.stdout.decode("utf-8", "replace").replace("\r", "").split("=== L1 CONTRACT")[0]
    stale = [l for l in out.split("\n") if "anchor not found" in l]
    check("all four anchors are looked up", "4 anchor(s) checked" in out, out)
    check("only the anchor that does not exist and the one that is only a trailing comment are reported", len(stale) == 2 and any("Stage: Missing" in l for l in stale) and any("Stage: Hidden" in l for l in stale), stale)
    check("the dash-decorated stage comment and the hash-star heading are found", not any("Alpha" in l or "Beta" in l for l in stale), stale)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
