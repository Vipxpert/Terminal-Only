# /llm_harness/tests/git_write_re_test.py
"""Safety-rule test for llm_harness: the pattern that refuses history-changing git commands in @RUN refuses the writes (tag creation and deletion, commit, push) and lets the listing forms through, including git tag -n1 and -n5 (-n with a number)."""
import importlib.util, os, sys

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-700:].replace("\n", "\n    "))


def main():
    spec = importlib.util.spec_from_file_location("harness_under_test", HARNESS)
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    refused = ["git tag v1.0", "git tag -a v1.0 -m x", "git tag -d v1.0", "git commit -m x", "git push origin main", "git checkout main", "git worktree remove --force x", "git update-ref -d HEAD", "git symbolic-ref HEAD refs/heads/x", "git filter-branch -f"]
    allowed = ["git tag", "git tag -l", "git tag --list", "git tag -n", "git tag -n1 --list", "git tag -n5", "git tag --contains abc123", "git status", "git log --oneline", "git worktree list", "git symbolic-ref HEAD"]
    wrongly_allowed = [c for c in refused if not hh.GIT_WRITE_RE.search(c)]
    wrongly_refused = [c for c in allowed if hh.GIT_WRITE_RE.search(c)]
    check("writes are refused", not wrongly_allowed, wrongly_allowed)
    check("listing forms, including -n1 and -n5, are allowed", not wrongly_refused, wrongly_refused)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
