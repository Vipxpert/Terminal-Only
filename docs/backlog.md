# Backlog

What is known to be missing, deferred, unverified or worth doing, so that nothing lives only in a chat. The AI adds a line in the same script that leaves something undone; whoever finishes an item removes it in the commit that finishes it. The owner reorders, rewrites or deletes lines at will. Kinds: unverified (built but never proven where it matters), question (waiting on someone), gap (a known shortcoming), friction (the same manual step, workaround or reminder more than once), deferred (decided to do later), idea (speculative: no evidence yet).

## Unverified
- The accidental-paste wording ("one or two short lines, no manifest, remind what is pending") has not been seen working in a real chat: the owner reported that the old sample reply ("beep boop") was not followed. The harness cannot see a paste into the chat, so only the wording can help; check on the next accidental paste, and shorten [L1-Harness], the longest rule, if it still fails. (2026-11-22)
- A @SIDE script that carries the same @SESSION as a numbered chat runs the same end-of-run delivery for that session (seen in main), so it could print that chat's messages into an output meant for a second chat and consume them there; never tested. (2026-11-22)
- A session that ends (@SESSION_END) or is released while messages for it are unread may lose them silently, because a message can only be sent to a session still in the registry; not tested. (2026-11-22)

- setup.cmd copying knowledge/ and playbooks/ has never run on Windows; they were copied by hand. Run setup.cmd once and look in ~/.llm_harness. (2026-11-22)
- The planning trigger and the three playbooks have never met a real request; the first big task is the trial. (2026-11-22)
- The Unity sql false positive fix (a .csproj counts only PackageReference lines) is proven only on a Unity-like sample; run @KB in Big&Small to confirm. (2026-11-22)
- macOS has never been tested, and CI on GitHub is off (Actions disabled until billing is sorted). (2026-11-22)

## Questions
- Owner's old note "Note renaming": rename what (a note's id, a chat name inside pins, a category)? Asked 2026-11-22. @NOTE_EDIT changes the text and its category prefix; --merge already renames a chat inside pins. (2026-11-22)
- Gemini (another project, script ids not visible here) reported a message that never appeared in the recipient's footers. Ask it for the sender's [SENT] line and the recipient's exact @SESSION name; the loss paths found so far are listed under Gaps. (2026-11-22)

- MongoDB entries for the knowledge library: what Motor's AsyncIOMotorGridFSBucket.find() yields, and the documented fix for $$ROOT memory use inside $group. Ask ChatGPT. (2026-11-22)
- The halagames knowledge file says a synchronous def /health route keeps answering while the ASGI event loop is frozen; that looks wrong, since the loop still receives the request. Owner to confirm what was observed. (2026-11-22)

## Gaps
- README, the tree and the session rules still say messages, scope changes and [UNBLOCKED] are shown once; after the keep-until-progress fix they are shown until the chat's next numbered script. Update them with the commit. (2026-11-22)
- A message, an [UNBLOCKED] notice and a scope event count as delivered when the harness prints them, because the recipient's cursor is saved before the print (seen in announce_scope_changes and check_waiting); if that output never reaches the chat (not pasted, a wrong clipboard), the notice is gone. Keep it in the footer until the chat sends its next numbered script, the only proof it read the output. tests/message_flows_test.py checks it. (2026-11-22)

- The other "once only" marks may share the weakness (code unread; the README says once): [CHANGED] and [NEW] on rules, the knowledge hint, the git greeting, the first look at other sessions' scopes and [WAKE]. (2026-11-22)

- @GIT_ACCOUNT knows only Git Credential Manager and, on Windows, the credential list (seen in known_accounts), so a headless Linux machine that has only the gh tool finds no accounts; offering gh needs gh's exact output formats, which ChatGPT is looking up. (2026-11-22)
- @RUN is one line: the lines after it become stray lines with a warning while the first line runs alone (reported by Gemini with a truncated python -c; the warning code is seen in main). Running a truncated command is the hazard; refuse a script whose @RUN is directly followed by stray lines and say to put a longer program in a @NEW_FILE. (2026-11-22)

- A @REPEATABLE script that carries a script number is refused before the session is named, so that one refusal's footer probably still has no session lines; the lines above the naming point were not read. Check after the replay fix. (2026-11-22)

- @GIT_BRANCH and @GIT_TAG switches probably share the tokens.json problem that @GIT_PULL had (git refuses a switch that would overwrite a locally modified tokens.json); not tested, and park_tokens / unpark_tokens could wrap them. (2026-11-22)

- The tree's /tests node lists brief_rules_test.py twice, with two different descriptions. (2026-11-22)
- The tree drift check (@PROBE tree | Check) reports 41 stale nodes, seen after the README script: 14 harness.py "# Stage:" anchors and 8 workflow_commands.txt anchors read as not found, and the 19 knowledge/ and playbooks/ file nodes read as files at the repository root (their parent nodes are probably not recognised as folders). Find out which were already stale before this session, then fix the nodes. (2026-11-22)

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

- Releases: push tag v3.13.0 when the owner says so; cut 3.14 for the playbooks, backlog and review work. (2026-11-22)
- Desktop: run setup.cmd (many commits behind), run --steward on for this repository, end its old harness-dev session, decide what to do with its local-only v3.10.0 tag. (2026-11-22)
- halagames-tools: pin the HalaGames account with @GIT_ACCOUNT; add !.llm_harness/git.json to .gitignore with the git.json branch policy; add the .gitattributes merge lines. (2026-11-22)
- Laptop: point origin at the Terminal-Only repository on GitHub instead of the old llm_harness name. (2026-11-22)
- Unity project Big&Small: no goal pinned, and the checkout is 9 commits behind its remote. (2026-11-22)

## Ideas
- @TAKEOVER <old chat>: a directive that absorbs a dead or finished chat's scope, grants, notes, verdicts, queues and unread messages into this chat, with one question at the user's terminal (Enter agrees), so the owner never types --merge to move work to a new chat (owner's old note: transfer work to another chat, or several at once, with minimal conflicts; the rest of that is built: scopes, @DELEGATE, --merge, worktrees, messages). (2026-11-22)
- Owner's old note: a note pin mode for every chat including ones that appear later; a plain @NOTE_ADD and "pin *" should already do it, tests/note_pin_all_test.py checks; document it on the card if so. (2026-11-22)
- A manual step the user must do BEFORE the script (an authentication, say) belongs in the first line of Talk, never only in the checklist after the script: reported by Gemini, where it was run in the wrong order. One short clause in [L1-Harness]. (2026-11-22)
- Speculative: the harness could count its own repeated refusals, mismatches and failed commands from saved runs and hand them to the review, so friction is measured rather than remembered. (2026-11-22)
- When an @RUN command fails, search the knowledge library with its error text and print the matching entries automatically. (2026-11-22)
- Parked earlier: campaign progress counts, a [MALFORMED] hint, --grant with several paths, a [GONE] notice, ready-to-paste user commands in refusals, a switch for automatic delegation, relaxed claims for a solo session, shared claims through a git ref, a warning when a stored account disappears. (2026-11-22)
