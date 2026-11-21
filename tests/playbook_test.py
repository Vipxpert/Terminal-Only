# /llm_harness/tests/playbook_test.py
"""Playbook test for llm_harness: @PLAYBOOK lists the planning procedures and when to use each, prints one by name without its automatic first-line header, says so for an unknown name, and the shipped playbooks stay short and say when to use them."""
import importlib.util, os, subprocess, sys, tempfile

HARNESS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), ".llm_harness", "harness.py")
LIB = os.environ.get("LLM_TEST_PLAYBOOKS") or os.path.join(os.path.dirname(os.path.abspath(HARNESS)), "playbooks")
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
    fx = tempfile.mkdtemp(prefix="harness-pb-")
    with open(os.path.join(fx, "alpha.txt"), "w", newline="\n") as f:
        f.write("# /demo/playbooks/alpha.txt\n# use when: a small thing needs a plan\nStep one.\nStep two.\n")
    with open(os.path.join(fx, "beta.txt"), "w", newline="\n") as f:
        f.write("# use when: a large thing needs a plan\nOnly step.\n")
    env = dict(os.environ, LLM_HARNESS_PLAYBOOKS=fx)

    def ask(words):
        text = "@SCRIPT [C: pb]\n@WORKSPACE %s\n@PLAYBOOK %s\n" % (fx, words)
        p = subprocess.run([sys.executable, HARNESS], input=text.encode(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=60)
        return p.stdout.decode("utf-8", "replace").replace("\r", "").split("=== L1 CONTRACT")[0]

    os.environ["LLM_HARNESS_PLAYBOOKS"] = fx
    books = hh.playbook_files()
    check("each playbook is read without the automatic header line", sorted(books) == ["alpha", "beta"] and books["alpha"].startswith("# use when:") and "/demo/" not in books["alpha"], books)
    out = ask("")
    check("@PLAYBOOK alone lists the playbooks and when to use each", "alpha" in out and "a small thing needs a plan" in out and "beta" in out and "@PLAYBOOK <name>" in out and "unknown directive" not in out, out)
    out = ask("alpha")
    check("@PLAYBOOK <name> prints that playbook's steps", "Step one." in out and "Step two." in out and "beta" not in out, out)
    out = ask("nothing-like-this")
    check("an unknown name says so and lists the playbooks", "no playbook named 'nothing-like-this'" in out and "alpha" in out and "beta" in out, out)
    os.environ["LLM_HARNESS_PLAYBOOKS"] = LIB
    shipped = hh.playbook_files()
    check("the shipped playbooks include plan-first and plan-project", "plan-first" in shipped and "plan-project" in shipped and "review" in shipped, sorted(shipped))
    bad = [n for n, t in shipped.items() if "use when:" not in t.split("\n")[0] or len(t) > 3500 or len(t.split("\n")) > 40]
    check("every shipped playbook says when to use it and stays short", not bad, bad)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
