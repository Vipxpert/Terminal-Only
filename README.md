# Terminal Only (Chat Interface LLM Harness)

A workflow harness for doing real coding work with an AI **chat interface** (ChatGPT, Claude, Gemini in a browser) instead of an agent app.

## Why a chat-interface harness

Agent apps run commands on your machine by themselves. In a chat window the AI cannot touch your machine at all: it writes, you paste. This harness turns that loop into a dependable protocol:

- The AI answers each turn with one script. You paste it into a terminal and paste the output back.
- `harness.py` executes the script safely: exact-match patches, syntax rollback, an undo journal, a git gate.
- Every run ends with a footer: the next script number, the project's pinned goal and the standing rules (L1). The rules arrive at the end of every paste, so long chats do not drift away from them.

No API key, no MCP server, no agent permissions. Python 3 standard library only; the code graph (CBM) and `psutil` (to name a program that holds a folder open) are optional extras.

## Cost model

The harness runs locally and makes no model API calls of its own, so it needs no separately metered LLM API. You can drive it from a monthly AI chat subscription, using that plan's included usage rather than paying per API request. That can be more predictable or more economical than an API-metered agent workflow. Some coding agents are also offered through subscriptions, and every plan has usage limits, so the actual cost depends on the provider, the plan, the workload and how much context each session consumes.

## The loop

1. You describe the task.
2. The AI replies with a short manifest (Talk, Current aim, what it will change, inspect and run, After), one script fence, and a test checklist.
3. You paste the fence into PowerShell (or bash).
4. You paste the full output back (at a terminal the harness offers to copy it for you: press C or Enter, or X to skip).

Lost an output, or pasted twice? Paste the same script again. An identical re-paste replays the saved output and runs nothing; an old read-only script with no saved output simply runs again.

## Several chats on one project

Several chats can work in the same project at once, each with its own aim:

- Each chat names itself with `@SESSION <name>` on every script and leaves the script number out; the harness assigns numbers under a lock, so two chats never collide.
- Before changing files, a chat declares `@SCOPE <aim> | <paths or globs>`. A scope that overlaps another session's is refused when it is declared.
- Every other session is told about a scope change in its footers until it sends its next numbered script (a replay shows it again). The harness cannot push a message into another chat window; it informs each chat when that chat runs.
- File changes made through the harness inside another session's scope are refused. Changes made by `@RUN` commands are detected and reported, not prevented, because the harness cannot know in advance what a command will write.
- `@UNDO` only reverses the session's own scripts, and `@GIT_FOLD` is refused while other sessions hold scopes.
- Each chat states its own aim with `@SESSION <name> | <aim>`; the project goal stays shared, and the footer shows this chat's session first, then the others.
- Uncommitted work has an owner: a session cannot release its scope until its changes are committed (or explicitly handed over), cannot commit a file holding another active session's uncommitted changes, and is warned when it edits such a file.
- Chats can leave each other notes with `@MESSAGE` and `@SCOPE_REQUEST`, shown until that chat sends its next numbered script (so a paste that never reached the chat cannot lose them) and labelled as coming from an AI, not from you. `@BRAKE` pauses another chat's changes until it acknowledges with `@BRAKE_ACK`; you can lift a brake with `--unbrake <session>`, and end a closed chat's session with `--release <session>`.
- Only you can override a scope: `python harness.py --workspace <folder> --grant <session> <path or glob>` (or `--revoke`), typed in your own terminal. A script that tries to run it is refused.
- Chats that work on different branches at the same time should each use their own folder: `@GIT_WORKTREE add <branch>` creates `../<project>.<branch>` and prints the `@WORKSPACE` line to continue there. Script numbering stays shared; claims and undo are each folder's own. Switching branches inside a shared folder is refused while other chats are active.
- `@DELEGATE <chat> | <paths> | <task>` hands files and a task to another chat on the same machine: the files move at once (there is no acceptance step), with your uncommitted work in them, and that chat's footer says `INHERITED`. It finishes the task and answers `@RETURN <chat> | <result>`: the files are released and the result reaches you as a note, and you claim them again with `@SCOPE` to continue. A chat cannot release or end while it still holds delegated work, unless it ends with `drop`. It is also a way out of a `DEADLOCK`.
- Chats on different machines share nothing but git: claims, waits and delegations live in each machine's own harness state. Use one branch per chat and merge through git. A chat that died or was closed while work and claims were still on it can be absorbed into a live one when the live chat sends `@TAKEOVER <from_session>` (your terminal asks you one question: Enter agrees, and with no terminal nothing changes) or with your terminal command `harness.py --workspace <folder> --merge <from_session> <into_session>`: its write scope, grants, uncommitted-work ownership, pinned notes, verdicts and waiting or delegation queues move over.
- The harness's own committed memory merges itself. With two lines in `.gitattributes` (`@GIT_INIT` writes them for new repositories: `.llm_harness/notes.md merge=llm-harness-notes` and `.llm_harness/verdicts.json merge=llm-harness-verdicts`), git merges notes by id (both sides' new notes are kept and a clashing id is renumbered) and verdicts by key (the newer one wins), instead of leaving conflict markers that would make the notes unreadable. The harness registers the merge driver in each clone's local git config the next time it runs there.

## Install (once per machine)

The harness is `harness.py` and `workflow_commands.txt`, plus the `knowledge` and `playbooks` folders, installed into `.llm_harness` in your home folder. The setup scripts first pull the latest changes when their folder is a git clone, then copy them there from the folder they sit in, keep a backup of the previous version, offer to install or update the optional code graph (CBM, which needs internet), and pause at the end so you can read the result.

**Windows (PowerShell)**

1. Check that Python 3 and git are installed (the test suites run on Python 3.12 and 3.14):

        python --version; git --version

2. Clone the harness into a folder of your choice, for example `E:\Work\Me`:

        Set-Location E:\Work\Me; git clone https://github.com/Vipxpert/Terminal-Only.git llm_harness

3. Run the setup from the clone (or double-click `setup.cmd` in Explorer):

        Set-Location E:\Work\Me\llm_harness; .\setup.cmd

4. To update later, run the setup again; it pulls the latest changes first:

        Set-Location E:\Work\Me\llm_harness; .\setup.cmd

**Linux / macOS (terminal)**

1. Check that Python 3 and git are installed (the test suites run on Python 3.12 and 3.14):

        python3 --version; git --version

2. Clone the harness, for example into your home folder:

        git clone https://github.com/Vipxpert/Terminal-Only.git ~/llm_harness

3. Run the setup (it uses curl or wget for the optional CBM; `NO_PAUSE=1` skips the final pause):

        sh ~/llm_harness/setup.sh

4. To update later, run the setup again; it pulls the latest changes first:

        cd ~/llm_harness && sh setup.sh

## Start a session

Run the handshake for the project folder you want to work on.

Windows (PowerShell):

    python "$HOME\.llm_harness\harness.py" --workspace "D:\path\to\project"

Linux / macOS:

    python3 ~/.llm_harness/harness.py --workspace ~/path/to/project

On Windows with Git Bash or WSL, add `--shell bash` so the syntax card shows the bash wrapper.

Then open a new chat and paste three things: `workflow_commands.txt`, the handshake output, and your task. The handshake prints the syntax card (every directive and the exact fence wrapper for your shell), the project's goal and its notes. Projects with a git repository (a `.git` folder with a HEAD inside it, or a `.git` file for a worktree) run in git mode; any other folder runs in no-git mode, which keeps undo but has no git directives until `@GIT_INIT [Name <email>]` turns it into a repository, carrying its numbering and undo history over.

## Moving to another computer

1. Install the harness on the new computer (the steps above), then clone or pull your project there.
2. Run the handshake for the project. Your goal, notes, verdicts and campaigns come with the project, because they are committed in `.llm_harness/`.
3. If the project uses its own commit identity, set it again: repository-local git settings do not travel with a clone.

        git config user.name "Your Name"; git config user.email "you@example.com"

Script numbering, undo history, saved run outputs, the session list and the reread log stay on each machine and start fresh on the new one; that is by design and harmless.

## What the AI can do

| Purpose | Directives |
|---|---|
| Change files | `@FILE` + `@HUNK` (with `+++ [LINE EDITS] +++` for a few lines inside a long block), `@NEW_FILE`, `@DELETE_FILE` (files, folders or globs; every file stays recoverable with `@UNDO`), `@RENAME` (a file or a whole folder, undoable), `@TEXT_REPLACE` (count-locked text edits inside a line, a scope or a whole folder), `@REDO <n>` (rerun a failed script with small corrections) |
| Read code | `@PROBE <file> \| Scope / Lines / TOC`, `@PROBE <file> \| Refs \| <scope>` (what a scope uses and where each piece is defined) |
| Search | `@FIND` (files by name), `@GREP` (text or regex), both with an optional `| depth N` and a path filter (a fragment, a glob, or `re:<regex>`), `@XREF <name>` (references), `@XREF <name> \| callers / callees / impact` (code graph) |
| Architecture tree | `@PROBE <tree> \| Tree \| <node> \| <depth>`, `@PROBE <tree> \| Check` (drift check) |
| Dead code | `@PROBE <file> \| Unused` (candidates with call-graph and text evidence) |
| Run anything else | `@RUN [--timeout <s>] <command>` (tests, builds, installs, CLI tools); `@PART i/n` keeps a long run apart from many inspections, with the standing rules printed once |
| Project memory | `@GOAL`, `@NOTE_ADD / EDIT / REMOVE / LIST` (pin to chats, search by category or content), `@VERDICT` / `@VERDICTS`, `@CAMPAIGN`, `@INIT_DEBUG` |
| History | `@UNDO` (whole scripts, or only some files with `| /path, /other, /ye*`; `/old -> /new` recovers a file to another path), `@GIT_INIT`, `@GIT_STATUS`, `@GIT_COMMIT` (message checked), `@GIT_FOLD`, `@GIT_BRANCH`, `@GIT_WORKTREE`, `@GIT_TAG`, `@GIT_PUSH`, `@GIT_PULL`, `@GIT_ACCOUNT`, `@GIT_REMOTE` (add a remote or change its address: https or ssh, no password or token inside, never removed) |
| Knowledge and planning | `@KB <words>` (pitfalls for the technologies the project uses), `@PLAYBOOK [name]` (`plan-first`, `plan-project`, `review`) |

The syntax card printed by the handshake is the authoritative reference.

## Safety model

- A hunk applies only where its old code matches exactly one place; a mismatch prints the real on-disk lines to rebuild from.
- A Python or Go syntax error after patching restores the file.
- Every change is journaled; `@UNDO` restores the exact previous files, for whole scripts or one file (`@UNDO <n> | /path`), and skips files another chat now holds.
- Deletions go through the journal too: `@DELETE_FILE` on a file, folder or glob keeps every file recoverable, and the scorecard says how to get it back. A change that deletes a `Comment` line (a recorded reason in the code) is flagged with `[COMMENT REMOVED]`.
- When the harness patches itself, the previous version is kept as `harness.prev.py`.
- Inspection memory: reads are fingerprinted, so reading an unchanged definition again prints `[REVISIT]` with who read it and when.
- Failures and refusals end with a `->` line saying what to rebuild or check next; `[TIP]` lines point out cheaper edit forms. Neither blocks anything.
- Script numbers are assigned by the harness under a cross-process lock, so several chats can paste at the same time, and its state files are replaced whole, so no chat ever reads one half-written.
- Folders emptied by a rename or delete are removed up to the workspace root (a folder holding only `__pycache__` counts as empty); one that cannot be removed is named, with the process holding it when the optional `psutil` package is installed. Nothing is ever stopped for you.
- In a git project the harness commits its own project memory (`.llm_harness` goal, notes, verdicts and `git.json`) after each script that changes it, except on a protected branch; if `.gitignore` hides those files, it says so.
- `@GIT_PUSH` publishes the current branch's commits (it sets the upstream the first time) or, as `@GIT_PUSH tag <name>`, one tag. It is never forced and never takes a protected branch, a rejected push is reported and not overridden, and a raw `git push` through `@RUN` is still refused.
- At the end of each run (at most once a minute, quietly, and silently when offline) the harness fetches the branch's upstream. When the remote has commits this checkout lacks, the footer says `UPSTREAM` and sorts the incoming files into those inside your scope, project memory and other files; fetching changes no file and nothing is pulled by itself. `@GIT_PULL` fast-forwards a clean checkout and bookmarks where it was; when the branches have diverged it only says whether a merge would be clean or would conflict, and changes nothing. `LLM_HARNESS_FETCH=off` stops the fetching, and a number sets the interval in seconds. The automatic fetch never opens a login window: it asks Git Credential Manager not to prompt and is simply skipped when it cannot sign in by itself (`@GIT_PULL` and `@GIT_PUSH` may still ask). With several accounts signed in, `@GIT_ACCOUNT` lists them and lets you pin the one this project uses (a number at the terminal, or by name): it is kept in this clone's git config, so git passes that username to Git Credential Manager and stops showing the account chooser; `@GIT_ACCOUNT clear` removes it, and pressing A in the list signs another account in first (Git Credential Manager's own `github login`). The first time a push or pull you asked for finds several accounts and none pinned, the harness asks once (one key) instead of letting the chooser appear, and the choice is kept for that project on that machine only (it lives in the clone's `.git/config`, which is not committed), so another project or another machine asks once for itself.
- After three scripts in a row that did nothing, the footer says `LOOP CHECK`: the AI then drops its manifest and script and replies in one or two short lines. The same short, discardable reply is asked for an accidental paste (an output the chat already answered, or one with no new information and no words from you): it says so and reminds what is pending.
- At a terminal the harness waits for a key after a run: C or Enter copies the whole output to the clipboard (the Windows clipboard, with PowerShell as a fallback; `pbcopy`, `wl-copy`, `xclip` or `xsel` elsewhere); X skips it (other keys are ignored; after a replay, or on Windows while the terminal is still in front, it copies at once without asking; `LLM_HARNESS_COPY=ask` always asks), and `LLM_HARNESS_NO_COPY=1` turns the prompt off.
- Commits happen only through git directives, after you confirm the change works. The harness aborts during a merge or rebase, pushes only through `@GIT_PUSH` (never forced), and refuses `@RUN git commit` and similar commands. Commit messages must have the form `type(scope): subject` with a conventional type. An optional `.llm_harness/git.json` (`{"version": 1, "protected": ["main", "dev"], "branches": "<regex>", "header_max": 100}`) refuses commits on protected branches and over-long headers and warns about branch names; it is a harness safety rule, while GitHub branch protection and commitlint, where installed, remain the real enforcement. A git worktree (a second checkout of the same repository, usually on another branch) runs in git mode, shares script numbering with the main checkout, and keeps its own sessions, scopes and undo journal, so chats working on different branches in different worktrees never touch each other's files. `@GIT_BRANCH`, `@GIT_WORKTREE add / list / remove` and `@GIT_TAG` all pass one safety check (no local changes, no unfinished git operation, and for branch switches no other active chat in the checkout) plus the project's `git.json` policy (branch-name pattern; `tags_from` and `tag_changelog` for release tags). Merging stays yours; `@GIT_PUSH` publishes the current branch (never forced, never a protected branch) and a tag only when you say so, because pushing a release tag may start a deployment.
- Script numbers only go up: an old or reused number is refused, apart from the replay and re-run cases above. A second chat can work alongside with `@SIDE` scripts, which skip the numbering and may only read, search and run commands. A script marked `@REPEATABLE` runs on every paste, even an identical one, so you can rerun a test or tweak its values by hand; it may only read, search and run commands. To undo a stretch of a chat's work, paste the first script you regret into the terminal again: the harness asks whether to replay it, undo it together with everything that chat did after it (committed work is kept), or execute it again. The first time a chat's session runs at a terminal, the harness asks for that chat's address (paste it from the browser's address bar; it cannot be skipped, and an empty or wrong answer asks again); the session list and every refusal involving that session then show it, so you can open the other chat. When a new chat inherits a session or the address on file is wrong, the chat sends bare `@CHAT_LINK` so the terminal asks you directly (or pass `@CHAT_LINK <address>` / run `--link <session> <address>`). Work a chat could not do because another chat held the files stays listed under WAITING ON in its footer until it is free (then `[UNBLOCKED]` says so until that chat's next numbered script; if two or more chats wait on each other in a circle, every footer in it says `DEADLOCK` and names who waits on whom), and that chat cannot end its session without finishing it or giving it up with `@SESSION_END drop`. A chat changes only files inside its own write scope (a claim in the same script counts, and so does a user grant); anything else is refused.

## Project memory and machine state

- `.llm_harness/goal.md` and `.llm_harness/notes.md` are project memory: they travel with the project, and in a git project the harness commits them for you (see the Safety model). Notes are yours: the AI writes, edits or removes a standing-fact note only when you ask, and may suggest one in its reply otherwise. The exception is its own to-do list: for work that spans several scripts or chats it keeps one short `Todo:` note pinned to its own session (it tells you when it creates it, updates it as steps finish and removes it when done), so the plan survives a lost paste or a new chat; `@TAKEOVER` moves a chat's pinned notes to the chat that continues its work. A note can be pinned to particular chats with `@NOTE_ADD pin <session or pattern> | <text>` (for example `pin migration-* | ...`; the pattern is matched whenever a footer is printed, so `pin *` reaches every chat that has a session, including chats that appear later, and a plain `@NOTE_ADD` also reaches runs without a session): only those chats get it printed in their footers, while any chat can still read it with `@NOTE_LIST`. `@NOTE_LIST <words>` finds notes by category (a leading `Bug:`, `Decision:`, `Env:` ...) or by content. `.llm_harness/verdicts.json` keeps the AIs' recorded conclusions about folders, files and definitions (`@VERDICT`), so they travel too; a later change in a verdict's area marks it stale. For a sweep that needs a verdict on every area, you can start a `@CAMPAIGN` with its own verdict words: its rule and progress show in every footer while it runs, Tree probes mark finished nodes, and `@CAMPAIGN_END` removes its verdicts.
- Script numbering, the undo journal, saved run outputs and the graph stamp are machine-local: in `.git/llm_harness/` for git projects, in `.llm_harness/` otherwise, and ignored by git.
- The copy line estimates how many tokens each paste, each chat and the whole project have sent (an estimate of harness output only, at about four characters per token). The counts are kept per GitHub account and machine in `.llm_harness/tokens.json`, which is committed together with other memory changes and when a session ends.
- `docs/trees/tree_master.txt` is the curated architecture tree. It is read level by level, updated in the same script as the code it describes, and `| Check` reports nodes that no longer match the code.

## Languages

Edits work byte for byte in any language. Comment markers (for the `Comment` convention) and the first-line header are built in for Python, Go, JS, TS, Vue, C#, Java, Kotlin, Swift, Rust, C, C++ and several more (`@HELP LANGUAGES` lists every one), and `@SCOPE` can own a single class or method in the brace languages. Only Python and Go get an automatic syntax check. For any other file type you can give your own check command with `harness.py --workspace <folder> --check <.ext> <command>`: it is kept on your machine for that project only (never inside the project, so a cloned repository cannot make the harness run its commands), runs after a script changes a file of that type, and only reports PASS or CHECK FAILED, never rolling anything back.

## Knowledge library

`knowledge/<technology>.txt` holds pitfalls that AIs keep falling into, one entry each: the symptom, the wrong default, the fix, and how and when it was verified. An AI searches it with `@KB <technology or symptom words>` (the same as `@HELP KB ...`); `@KB` alone lists the technologies. Only the technologies your project seems to use are searched (judged from its manifests, file types and imports, and shown as `[used here: ...]` with the reason), unless the words name another one or include `all`, so unrelated entries never reach the AI. The footer names the technologies on file for the project when a chat starts and whenever they change. Setup installs the folder next to `harness.py`.

## Planning and the backlog

- `@PLAYBOOK` prints a short procedure on demand: `plan-first` for one feature with a few decisions to agree on, `plan-project` for a new project or a big redesign (it ends in a living `docs/plan.md`, a decision record, and Todo notes for the first milestone only), and `review`, the check before anything is called complete. The playbooks install next to `harness.py`; `docs/plan.md` and the backlog belong to your project. The AI is told to propose a playbook only when a request would force several consequential decisions, never for small work, and to treat your "we could" ideas as proposals, not decisions.
- Project stewardship is off until you switch it on for a project with `@STEWARD on` (the AI sends it and your terminal asks one question: Enter agrees, and with no terminal nothing changes) or the terminal command `harness.py --workspace <folder> --steward on` (kept on your machine for that project only; `off` switches it off, no argument says which; a script cannot run it); `@PLAYBOOK review` works by hand either way. While it is on, anything the AI defers, skips, leaves unverified or notices on the way goes into `docs/backlog.md` in the same script, grouped as unverified, question, gap, friction, deferred or idea, so nothing lives only in a chat. The review reads it before work is called complete and at the end of a milestone or session, and proposes improvements only from evidence, labelling the rest speculative.

## Optional: the code graph (CBM)

Install codebase-memory-mcp (github.com/DeusData/codebase-memory-mcp) to enable `callers / callees / impact`, the graph half of `| Unused`, and coverage warnings. The harness calls CBM's command-line mode, so no MCP connection is needed. It keeps CBM on its default per-user cache, re-indexes automatically when source files change, and warns when CBM parsed files only partly. Known limits: the graph misses Python method calls made through an object (the text checks compensate), and on some Windows setups CBM refuses a cache folder inside the project tree. Treat every graph answer as static evidence to confirm in source.

## Rules (L1)

`workflow_commands.txt` holds every rule exactly once. Its `L1 Rule` lines are printed in the footer after every run; rules tagged `(git)` print only for git projects, `(campaign)` rules only while a campaign runs, and the `(steward)` rule only where you switched stewardship on. A rule with an `L1 Brief` line prints as that brief; the harness prints the full rule in its place after a failed change or command, or while a debug ledger is open, and `@HELP L1-<name>` prints any rule in full. A rule that changed since a chat last saw it is marked `[CHANGED]` once, a newly applying one `[NEW]`; a project without git says `NO GIT HERE`; and the command list shows only the commands that chat has not used yet. Edit a rule there and the next run everywhere uses the new wording.

## Repository layout

- `harness.py`: the harness.
- `workflow_commands.txt`: the workflow and rules the AI follows.
- `knowledge/`: the shared library of pitfalls, one file per technology, searched with `@KB`.
- `playbooks/`: the planning and review procedures printed by `@PLAYBOOK`.
- `setup.cmd`, `setup.sh`: installers.
- `docs/trees/tree_master.txt`: this project's architecture tree.
- `docs/backlog.md`: what is known to be missing, deferred, unverified or worth doing.
- `.llm_harness/goal.md`, `.llm_harness/notes.md`: this project's memory.
- `tests/`: the test suites; `python tests/run_all.py` runs them all.
- `.github/workflows/tests.yml`: runs the suites on Windows and Linux for every push and pull request, where GitHub Actions is enabled.
- `CHANGELOG.md`: what changed in each release.

## Developing the harness

Work on this repository through the harness itself, with this folder as the workspace, then copy `harness.py`, `workflow_commands.txt` and the `knowledge` and `playbooks` folders into `~/.llm_harness` (or rerun setup). Keep the tree in sync in the same script as each change. After changing the harness, run `python tests/run_all.py` through `@RUN`: it runs every suite in tests/, prints PASS or FAIL per check and one summary, and tests the installed copy (give it the path of a `harness.py` to test that file instead). The workflow in `.github/workflows/tests.yml` runs it on Windows and Linux for every push and pull request wherever GitHub Actions is enabled.

## Limitations

- You are in the loop for every step: one script per turn, pasted by hand.
- Day-to-day use is on Windows PowerShell; Linux is covered by the test suites (the included GitHub Actions workflow runs them on Linux and Windows where Actions is enabled) but exercised less by hand, and macOS is untested.
- Graph searches pay CBM's start-up cost, a few seconds per run.

## Tools evaluated and not used

Coding agents print execution output (tool calls, paths, logs, progress) that is written for the agent itself; chat interfaces already explain things for people. This harness keeps the two layers apart: its own output is compact and written for the AI, and each reply's Talk part and checklist are written for you. That is why the tools below add little here. Their descriptions are as reported, not tested here, except RTK.

- RTK: filters noisy terminal output (tests, git, logs, searches, builds). Tested in this flow: it saved nothing, because the harness output is already compact.
- Headroom: compresses what an agent reads (tool output, files, context). It targets agent apps; here the chat receives only what the harness prints.
- Caveman: shortens what an agent says (answer first, less filler). Replies here follow the Talk and manifest format instead.
- Ponytail: pushes agents to reuse existing capabilities instead of overbuilding. A different problem, which the rules on the current request only and no unrequested refactors address.

Execution and judgment are different jobs: significant architecture or business changes deserve an independent review by a second chat before they land.
