# Backlog

What is known to be missing, deferred, unverified or worth doing, so that nothing lives only in a chat. The AI adds a line in the same script that leaves something undone; whoever finishes an item removes it in the commit that finishes it. The owner reorders, rewrites or deletes lines at will. Kinds: unverified (built but never proven where it matters), question (waiting on someone), gap (a known shortcoming), friction (the same manual step, workaround or reminder more than once), deferred (decided to do later), idea (speculative: no evidence yet).

## Unverified
- setup.cmd copying knowledge/ and playbooks/ has never run on Windows; they were copied by hand. Run setup.cmd once and look in ~/.llm_harness. (2026-11-22)
- The planning trigger and the three playbooks have never met a real request; the first big task is the trial. (2026-11-22)
- The Unity sql false positive fix (a .csproj counts only PackageReference lines) is proven only on a Unity-like sample; run @KB in Big&Small to confirm. (2026-11-22)
- macOS has never been tested, and CI on GitHub is off (Actions disabled until billing is sorted). (2026-11-22)

## Questions
- MongoDB entries for the knowledge library: what Motor's AsyncIOMotorGridFSBucket.find() yields, and the documented fix for $$ROOT memory use inside $group. Ask ChatGPT. (2026-11-22)
- The halagames knowledge file says a synchronous def /health route keeps answering while the ASGI event loop is frozen; that looks wrong, since the loop still receives the request. Owner to confirm what was observed. (2026-11-22)

## Gaps
- A @REPEATABLE script that carries a script number is refused before the session is named, so that one refusal's footer probably still has no session lines; the lines above the naming point were not read. Check after the replay fix. (2026-11-22)

- @GIT_BRANCH and @GIT_TAG switches probably share the tokens.json problem that @GIT_PULL had (git refuses a switch that would overwrite a locally modified tokens.json); not tested, and park_tokens / unpark_tokens could wrap them. (2026-11-22)

- The tree's /tests node lists brief_rules_test.py twice, with two different descriptions. (2026-11-22)
- The tree drift check (@PROBE tree | Check) reports 41 stale nodes, seen after the README script: 14 harness.py "# Stage:" anchors and 8 workflow_commands.txt anchors read as not found, and the 19 knowledge/ and playbooks/ file nodes read as files at the repository root (their parent nodes are probably not recognised as folders). Find out which were already stale before this session, then fix the nodes. (2026-11-22)

- A pitfall proven in another project has no path into the shared knowledge library: the AI there cannot write to the harness repository. Needs a proposal file or a ready-to-paste entry. (2026-11-22)
- halagames-tools' own docs/knowledge.txt still holds the contradictory Split-Brain and headless-API entries that the shared library merged into one. (2026-11-22)
- [L1-Notes] is printed in full on every footer and keeps growing; give it a short form once the planning and backlog clauses have proven themselves. (2026-11-22)

## Friction
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
- Speculative: the harness could count its own repeated refusals, mismatches and failed commands from saved runs and hand them to the review, so friction is measured rather than remembered. (2026-11-22)
- When an @RUN command fails, search the knowledge library with its error text and print the matching entries automatically. (2026-11-22)
- Parked earlier: campaign progress counts, a [MALFORMED] hint, --grant with several paths, a [GONE] notice, ready-to-paste user commands in refusals, a switch for automatic delegation, relaxed claims for a solo session, shared claims through a git ref, a warning when a stored account disappears. (2026-11-22)
