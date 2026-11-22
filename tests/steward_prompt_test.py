# /llm_harness/tests/steward_prompt_test.py
"""Steward prompt test for llm_harness: @STEWARD changes the switch only on the user's own answer at the terminal (Enter agrees, n declines, no terminal changes nothing), asks nothing when the switch already is as asked, and a side or repeatable script cannot ask. The console is replaced by a fake, since a real prompt needs a terminal."""
import contextlib, importlib.util, io, os, sys, tempfile

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
    err = hh.enter_workspace(tempfile.mkdtemp(prefix="harness-steward-prompt-"))
    asked, said = [], io.StringIO()

    def answer(value):
        def fake(prompt):
            asked.append(prompt)
            return value
        return fake

    def ask(word, **extra):
        asked.clear()
        said.truncate(0)
        said.seek(0)
        with contextlib.redirect_stdout(said):
            hh.steward_directive(dict({"steward": word}, **extra))

    hh.ask_console = answer("")
    ask("on")
    check("Enter at the terminal switches it on, after one question", not err and hh.steward_on() and len(asked) == 1, (err, said.getvalue()))
    ask("on")
    check("asking for what already is so asks nothing", hh.steward_on() and not asked, said.getvalue())
    hh.ask_console = answer("n")
    ask("off")
    check("answering n leaves it on", hh.steward_on() and len(asked) == 1, said.getvalue())
    hh.ask_console = answer(None)
    ask("off")
    check("with no terminal nothing changes", hh.steward_on() and "NOT CHANGED" in said.getvalue(), said.getvalue())
    hh.ask_console = answer("")
    ask("off", side=True)
    check("a side script cannot ask, so it stays on", hh.steward_on() and not asked and "REFUSED" in said.getvalue(), said.getvalue())
    ask("maybe")
    check("an unknown word is refused and asks nothing", hh.steward_on() and not asked and "REFUSED" in said.getvalue(), said.getvalue())
    hh.ask_console = answer("yes")
    ask("off")
    check("yes at the terminal switches it off", not hh.steward_on() and len(asked) == 1, said.getvalue())
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
