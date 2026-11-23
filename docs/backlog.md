# Backlog

What is known to be missing, deferred, unverified or worth doing, so that nothing lives only in a chat. The AI adds a line in the same script that leaves something undone; whoever finishes an item removes it in the commit that finishes it. The owner reorders, rewrites or deletes lines at will. Kinds: unverified (built but never proven where it matters), question (waiting on someone), gap (a known shortcoming), friction (the same manual step, workaround or reminder more than once), deferred (decided to do later), idea (speculative: no evidence yet).

## Unverified
- setup.cmd's failed-pull message (PULL_FAILED) has not run on a checkout whose pull really fails; only :getver is tested. Try it on the next diverged checkout. (2026-11-23)
- The gh provider for @GIT_ACCOUNT (JSON list, switch, setup-git hint) has been tested only against a fake gh, built from ChatGPT's reading of GitHub's docs; try it once with the real gh on a machine with two accounts. SSH-key selection per account stays unsupported by design. (2026-11-23)
- The setup.cmd version lines (the :getver subroutine, a PowerShell call inside a batch file) have not run on Windows; setup.sh's are tested. Run setup.cmd once and read the "Harness version" and "Installed version now" lines. (2026-11-22)
- The intro playbook and its [L1-Notes] trigger have not met a real newcomer; check that a chat told "I'm new to this tool" opens @PLAYBOOK intro and stays short. (2026-11-22)
- An own note ([own: <session>]) through the two-machine notes.md merge: the merge's own parser was not read, so the mark is inferred to survive as part of the note's text; memory_merge_test runs at the next full run, and a merge case with an own note would prove it. (2026-11-22)
- The framing step ([L1-Notes] clause, and "Frame first" in plan-first and plan-project) has not been seen in a real chat. Owner's case to recheck it against: a request to code Geometry Dash into a codebase whose broader aim was a platform that installs apps; the AI should ask about the platform before planning the game. Watch for the opposite failure too: challenging small, clear requests. (2026-11-22)
- The new [L1-Notes] exception (the AI keeps one short Todo note pinned to its own session) has not been seen followed in a real chat; check the notes after the next multi-step task (it should be one note, pinned, short, removed when done) and shorten [L1-Notes] if it is ignored or overused. (2026-11-22)
- The @TAKEOVER question has not been seen at a real terminal (the test replaced the console with a fake one, as the @STEWARD test did before the owner pressed Enter); try it once when a second chat exists. (2026-11-22)
- The accidental-paste wording ("one or two short lines, no manifest, remind what is pending") has not been seen working in a real chat: the owner reported that the old sample reply ("beep boop") was not followed. The harness cannot see a paste into the chat, so only the wording can help; check on the next accidental paste, and shorten [L1-Harness], the longest rule, if it still fails. Seen once (2026-11-22): the rule counted "[REPLAY] in it" as already answered, though a replay can be the first sight of an output that never reached the chat; that clause is reworded. (2026-11-22)

- A session that ends (@SESSION_END) or is released while messages for it are unread may lose them silently, because a message can only be sent to a session still in the registry; not tested. (2026-11-22)

- setup.cmd copying knowledge/ and playbooks/ has never run on Windows; they were copied by hand. Run setup.cmd once and look in ~/.llm_harness. (2026-11-22)
- The planning trigger and the three playbooks have never met a real request; the first big task is the trial. (2026-11-22)
- The Unity sql false positive fix (a .csproj counts only PackageReference lines) is proven only on a Unity-like sample; run @KB in Big&Small to confirm. (2026-11-22)
- macOS has never been tested, and CI on GitHub is off (Actions disabled until billing is sorted). (2026-11-22)

## Questions

- Gemini (another project, script ids not visible here) reported a message that never appeared in the recipient's footers. Ask it for the sender's [SENT] line and the recipient's exact @SESSION name; the loss paths found so far are listed under Gaps. (2026-11-22)

- MongoDB entries for the knowledge library: what Motor's AsyncIOMotorGridFSBucket.find() yields, and the documented fix for $$ROOT memory use inside $group. Ask ChatGPT. (2026-11-22)
- The halagames knowledge file says a synchronous def /health route keeps answering while the ASGI event loop is frozen; that looks wrong, since the loop still receives the request. Owner to confirm what was observed. (2026-11-22)

## Gaps
- tree_master.txt lists brief_rules_test.py twice under /tests (seen in the node list a missing-node message printed); find and remove the duplicate line. (2026-11-23)
- setup.cmd printed "Setup successful" after git pull failed on a diverged branch and installed the old files, and gave no instruction; it should say that the pull failed and what the installed version is, and name the way out. Seen on the desktop, 2026-11-23. (2026-11-23)
- README: several Safety-model bullets pack six to eight mechanics into one paragraph (upstream fetching with accounts, the paste loop with clipboard and loop detection); split them under short sub-headings. Raised by Gemini, confirmed by reading. (2026-11-23)



- The other "once only" marks may share the weakness (code unread; the README says once): [CHANGED] and [NEW] on rules, the knowledge hint, the git greeting, the first look at other sessions' scopes and [WAKE]. (2026-11-22)





- The tree's /tests node lists brief_rules_test.py twice, with two different descriptions. (2026-11-22)

- A pitfall proven in another project has no path into the shared knowledge library: the AI there cannot write to the harness repository. Needs a proposal file or a ready-to-paste entry. (2026-11-22)
- halagames-tools' own docs/knowledge.txt still holds the contradictory Split-Brain and headless-API entries that the shared library merged into one. (2026-11-22)
- [L1-Notes] is printed in full on every footer and keeps growing; give it a short form once the planning and backlog clauses have proven themselves. (2026-11-22)

## Friction
- Two tests failed after a rule and a refusal message were reworded (loop_check, handoff) because they assert exact sentences; the behaviour was right both times. Assert a stable token (the refusal marker and the command name) instead, and reread tests that quote wording when a message changes. (2026-11-22)
- The owner had to remember and type --steward on, and said so: the AI is the harness's main user. A user-only command should be a directive the AI sends, with the terminal asking the owner one key (as @CHAT_LINK does), never a command to type; @STEWARD is done; --check, --grant, --merge and the others remain where it fits. (2026-11-22)
- @SCOPE_END is refused when this session once changed a file it later dropped and another session now owns; the way out (@SCOPE_END handover) cost one extra script (reported once by Gemini). The refusal could name handover for exactly that case. (2026-11-22)
- A script that installs a new harness.py and then probes with it runs the probes with the old code, because the harness running the script was loaded before the install; only subprocess tests see the new code. Hit twice: @HELP LANGUAGES right after its install, and the tree drift check right after the anchor fix. The probe has to go in the next script, or the harness could say so when a script installs it. (2026-11-22)
- Checks in a second project need a second pasted script: the Unity @KB check was skipped three times in one session. A read-only probe of another workspace from the same script would remove the second paste. (2026-11-22)
- @TEXT_REPLACE refuses old text under 12 characters, so renaming .sql to .csv in one test took 15 whole-line replacements, and a three-character token in the pull test needed whole statements again; a short token with a stated count could be allowed. (2026-11-22)

## Deferred

- Desktop: run setup.cmd (many commits behind), send @STEWARD on for this repository (one question at its terminal), end its old harness-dev session, decide what to do with its local-only v3.10.0 tag. (2026-11-22)
- halagames-tools: pin the HalaGames account with @GIT_ACCOUNT; add !.llm_harness/git.json to .gitignore with the git.json branch policy; add the .gitattributes merge lines. (2026-11-22)
- Laptop: point origin at the Terminal-Only repository on GitHub instead of the old llm_harness name. (2026-11-22)
- Unity project Big&Small: no goal pinned, and the checkout is 9 commits behind its remote. (2026-11-22)

## Ideas
- The AUTO status line and @ASK_USER are built but off and hidden: switch on with harness.py --workspace <folder> --auto on (off to hide again). Not built: a desktop notification on PAUSE (could ride the same switch) and any runner. A runner for the chat websites (Playwright) is declined: the services generally forbid bots on consumer accounts; use a provider API, or an agent product, if a loop is ever wanted. @HELP COMMANDS may still list @ASK_USER. (2026-11-23)
- Gemini's RunContext idea: group the module-level run state (CURRENT_SESSION, CURRENT_SCRIPT and the like) in one object; declined for now, since no failure comes from it. (2026-11-23)


- A manual step the user must do BEFORE the script (an authentication, say) belongs in the first line of Talk, never only in the checklist after the script: reported by Gemini, where it was run in the wrong order. One short clause in [L1-Harness]. (2026-11-22)
- Speculative: the harness could count its own repeated refusals, mismatches and failed commands from saved runs and hand them to the review, so friction is measured rather than remembered. (2026-11-22)
- When an @RUN command fails, search the knowledge library with its error text and print the matching entries automatically. (2026-11-22)
- Parked earlier: campaign progress counts, a [MALFORMED] hint, --grant with several paths, a [GONE] notice, ready-to-paste user commands in refusals, a switch for automatic delegation, relaxed claims for a solo session, shared claims through a git ref, a warning when a stored account disappears. (2026-11-22)
