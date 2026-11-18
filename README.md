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
4. You paste the full output back (at a terminal the harness offers to copy it for you: press C, or X to skip).

Lost an output, or pasted twice? Paste the same script again. An identical re-paste replays the saved output and runs nothing; an old read-only script with no saved output simply runs again.

## Several chats on one project

Several chats can work in the same project at once, each with its own aim:

- Each chat names itself with `@SESSION <name>` on every script and leaves the script number out; the harness assigns numbers under a lock, so two chats never collide.
- Before changing files, a chat declares `@SCOPE <aim> | <paths or globs>`. A scope that overlaps another session's is refused when it is declared.
- Every other session is told about a scope change once, the next time it runs. The harness cannot push a message into another chat window; it informs each chat when that chat runs.
- File changes made through the harness inside another session's scope are refused. Changes made by `@RUN` commands are detected and reported, not prevented, because the harness cannot know in advance what a command will write.
- `@UNDO` only reverses the session's own scripts, and `@GIT_FOLD` is refused while other sessions hold scopes.
- Each chat states its own aim with `@SESSION <name> | <aim>`; the project goal stays shared, and the footer shows this chat's session first, then the others.
- Uncommitted work has an owner: a session cannot release its scope until its changes are committed (or explicitly handed over), cannot commit a file holding another active session's uncommitted changes, and is warned when it edits such a file.
- Chats can leave each other notes with `@MESSAGE` and `@SCOPE_REQUEST`, shown once and labelled as coming from an AI, not from you. `@BRAKE` pauses another chat's changes until it acknowledges with `@BRAKE_ACK`; you can lift a brake with `--unbrake <session>`, and end a closed chat's session with `--release <session>`.
- Only you can override a scope: `python harness.py --workspace <folder> --grant <session> <path or glob>` (or `--revoke`), typed in your own terminal. A script that tries to run it is refused.
- Chats that work on different branches at the same time should each use their own folder: `@GIT_WORKTREE add <branch>` creates `../<project>.<branch>` and prints the `@WORKSPACE` line to continue there. Script numbering stays shared; claims and undo are each folder's own. Switching branches inside a shared folder is refused while other chats are active.

## Install (once per machine)

The harness is two files, `harness.py` and `workflow_commands.txt`, installed into `.llm_harness` in your home folder. The setup scripts first pull the latest changes when their folder is a git clone, then copy them there from the folder they sit in, keep a backup of the previous version, offer to install or update the optional code graph (CBM, which needs internet), and pause at the end so you can read the result.

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

Then open a new chat and paste three things: `workflow_commands.txt`, the handshake output, and your task. The handshake prints the syntax card (every directive and the exact fence wrapper for your shell), the project's goal and its notes. Projects with a `.git` folder or file (a worktree has a file) run in git mode; any other folder runs in no-git mode, which keeps undo but has no git directives until `@GIT_INIT [Name <email>]` turns it into a repository, carrying its numbering and undo history over.

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
| History | `@UNDO` (whole scripts, or only some files with `| /path, /other, /ye*`; `/old -> /new` recovers a file to another path), `@GIT_INIT`, `@GIT_STATUS`, `@GIT_COMMIT` (message checked), `@GIT_FOLD`, `@GIT_BRANCH`, `@GIT_WORKTREE`, `@GIT_TAG` |

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
- After three scripts in a row that did nothing, the footer says `LOOP CHECK`: the AI then drops its manifest and script and asks whether you are still there.
- At a terminal the harness waits for a key after a run: C copies the whole output to the clipboard (the Windows clipboard, with PowerShell as a fallback; `pbcopy`, `wl-copy`, `xclip` or `xsel` elsewhere); X skips it (other keys are ignored), and `LLM_HARNESS_NO_COPY=1` turns the prompt off.
- Commits happen only through git directives, after you confirm the change works. The harness aborts during a merge or rebase, never pushes, and refuses `@RUN git commit` and similar commands. Commit messages must have the form `type(scope): subject` with a conventional type. An optional `.llm_harness/git.json` (`{"version": 1, "protected": ["main", "dev"], "branches": "<regex>", "header_max": 100}`) refuses commits on protected branches and over-long headers and warns about branch names; it is a harness safety rule, while GitHub branch protection and commitlint, where installed, remain the real enforcement. A git worktree (a second checkout of the same repository, usually on another branch) runs in git mode, shares script numbering with the main checkout, and keeps its own sessions, scopes and undo journal, so chats working on different branches in different worktrees never touch each other's files. `@GIT_BRANCH`, `@GIT_WORKTREE add / list / remove` and `@GIT_TAG` all pass one safety check (no local changes, no unfinished git operation, and for branch switches no other active chat in the checkout) plus the project's `git.json` policy (branch-name pattern; `tags_from` and `tag_changelog` for release tags). Merging, and pushing branches or tags, stay yours: pushing a release tag may start a deployment.
- Script numbers only go up: an old or reused number is refused, apart from the replay and re-run cases above. A second chat can work alongside with `@SIDE` scripts, which skip the numbering and may only read, search and run commands. A script marked `@REPEATABLE` runs on every paste, even an identical one, so you can rerun a test or tweak its values by hand; it may only read, search and run commands. To undo a stretch of a chat's work, paste the first script you regret into the terminal again: the harness asks whether to replay it, undo it together with everything that chat did after it (committed work is kept), or execute it again. The first time a chat's session runs at a terminal, the harness asks once for that chat's address (paste it from the browser, or press Enter to skip); the session list and every refusal involving that session then show it, so you can open the other chat. `--link <session> <address>` sets or changes it later. Work a chat could not do because another chat held the files stays listed under WAITING ON in its footer until it is free (then `[UNBLOCKED]` says so once), and that chat cannot end its session without finishing it or giving it up with `@SESSION_END drop`. A chat changes only files inside its own write scope (a claim in the same script counts, and so does a user grant); anything else is refused.

## Project memory and machine state

- `.llm_harness/goal.md` and `.llm_harness/notes.md` are project memory: they travel with the project, and in a git project the harness commits them for you (see the Safety model). Notes are yours: the AI writes, edits or removes one only when you ask, and may suggest one in its reply otherwise. A note can be pinned to particular chats with `@NOTE_ADD pin <session or pattern> | <text>` (for example `pin migration-* | ...`): only those chats get it printed in their footers, while any chat can still read it with `@NOTE_LIST`. `@NOTE_LIST <words>` finds notes by category (a leading `Bug:`, `Decision:`, `Env:` ...) or by content. `.llm_harness/verdicts.json` keeps the AIs' recorded conclusions about folders, files and definitions (`@VERDICT`), so they travel too; a later change in a verdict's area marks it stale. For a sweep that needs a verdict on every area, you can start a `@CAMPAIGN` with its own verdict words: its rule and progress show in every footer while it runs, Tree probes mark finished nodes, and `@CAMPAIGN_END` removes its verdicts.
- Script numbering, the undo journal, saved run outputs and the graph stamp are machine-local: in `.git/llm_harness/` for git projects, in `.llm_harness/` otherwise, and ignored by git.
- `docs/trees/tree_master.txt` is the curated architecture tree. It is read level by level, updated in the same script as the code it describes, and `| Check` reports nodes that no longer match the code.

## Optional: the code graph (CBM)

Install codebase-memory-mcp (github.com/DeusData/codebase-memory-mcp) to enable `callers / callees / impact`, the graph half of `| Unused`, and coverage warnings. The harness calls CBM's command-line mode, so no MCP connection is needed. It keeps CBM on its default per-user cache, re-indexes automatically when source files change, and warns when CBM parsed files only partly. Known limits: the graph misses Python method calls made through an object (the text checks compensate), and on some Windows setups CBM refuses a cache folder inside the project tree. Treat every graph answer as static evidence to confirm in source.

## Rules (L1)

`workflow_commands.txt` holds every rule exactly once. Its `L1 Rule` lines are printed in the footer after every run; rules tagged `(git)` print only for git projects, and `(campaign)` rules only while a campaign runs. A rule with an `L1 Brief` line prints as that brief; the harness prints the full rule in its place after a failed change or command, or while a debug ledger is open, and `@HELP L1-<name>` prints any rule in full. A rule that changed since a chat last saw it is marked `[CHANGED]` once, a newly applying one `[NEW]`; a project without git says `NO GIT HERE`; and the command list shows only the commands that chat has not used yet. Edit a rule there and the next run everywhere uses the new wording.

## Repository layout

- `harness.py`: the harness.
- `workflow_commands.txt`: the workflow and rules the AI follows.
- `setup.cmd`, `setup.sh`: installers.
- `docs/trees/tree_master.txt`: this project's architecture tree.
- `.llm_harness/goal.md`, `.llm_harness/notes.md`: this project's memory.
- `tests/`: the test suites; `python tests/run_all.py` runs them all.
- `.github/workflows/tests.yml`: runs the suites on Windows and Linux for every push and pull request.
- `CHANGELOG.md`: what changed in each release.

## Developing the harness

Work on this repository through the harness itself, with this folder as the workspace, then copy `harness.py` and `workflow_commands.txt` into `~/.llm_harness` (or rerun setup). Keep the tree in sync in the same script as each change. After changing the harness, run `python tests/scopes_test.py` and `python tests/concurrency_test.py` through `@RUN`; each prints PASS or FAIL per check and tests the installed copy. `python tests/run_all.py [path to harness.py]` runs every suite in tests/ and prints one summary; GitHub Actions runs it on Windows and Linux for every push and pull request.

## Limitations

- You are in the loop for every step: one script per turn, pasted by hand.
- Day-to-day use is on Windows PowerShell; Linux is covered by the test suites (GitHub Actions runs them on Linux and Windows) but exercised less by hand, and macOS is untested.
- Graph searches pay CBM's start-up cost, a few seconds per run.

## Tools evaluated and not used

Coding agents print execution output (tool calls, paths, logs, progress) that is written for the agent itself; chat interfaces already explain things for people. This harness keeps the two layers apart: its own output is compact and written for the AI, and each reply's Talk part and checklist are written for you. That is why the tools below add little here. Their descriptions are as reported, not tested here, except RTK.

- RTK: filters noisy terminal output (tests, git, logs, searches, builds). Tested in this flow: it saved nothing, because the harness output is already compact.
- Headroom: compresses what an agent reads (tool output, files, context). It targets agent apps; here the chat receives only what the harness prints.
- Caveman: shortens what an agent says (answer first, less filler). Replies here follow the Talk and manifest format instead.
- Ponytail: pushes agents to reuse existing capabilities instead of overbuilding. A different problem, which the rules on the current request only and no unrequested refactors address.

Execution and judgment are different jobs: significant architecture or business changes deserve an independent review by a second chat before they land.
