# Changelog

Notable changes to llm_harness, newest first. Each `feat`, `fix` or `perf` commit adds a line under **Unreleased**; a version bump moves those lines under the new version's heading.

## Unreleased

- Fix: @GIT_BRANCH no longer refuses to switch to an existing branch whose committed tokens.json differs while the local one is modified (git said the local changes would be overwritten by checkout): the local token counts are set aside and merged back with the branch's, as @GIT_PULL does.

- The AI may keep its own to-do list as one short "Todo:" note pinned to its own session, and is encouraged to for work that spans several scripts or chats (it says so when it creates it, edits it as steps finish and removes it when done); standing-fact notes still need the user's ask, and a log of scripts, decisions or progress is still never written. A new user no longer has to know the capability exists.

- Fix: the safety rule that refuses history-changing git commands in @RUN no longer refuses the listing forms git tag -n1 and git tag -n5 (it knew -n but not -n with a number).

## 3.14

- @TEXT_REPLACE with an empty replacement now removes the whole line when nothing else is left on it (it left a blank line behind, which piled up in files edited this way); a replacement that leaves other text on the line, and any ordinary replacement, behave as before.

- Fix: a @REPEATABLE script that carries a number and a @REDO that cannot run are refused with a footer that names the chat's own session (THIS SESSION, OTHER SESSIONS, its own command list), like every other run; the session is now named as soon as the saved state is loaded (name_session).

- @TAKEOVER <session>: the AI asks to continue another chat's work, and the user's terminal asks one question (Enter agrees); it does what the --merge command does (write scope, grants, notes, verdicts, queues, unread messages), so the user never types --merge. With no terminal, or in a @SIDE or @REPEATABLE script, nothing changes. The merge itself is one shared function (merge_sessions), and a note pinned with "pin *" is documented on the card as reaching every chat with a session, those that appear later too.

- Fix: an @RUN directly followed by a line that is not a directive (a command broken across lines, such as a multi-line python -c) is no longer run as its first line alone: the command is not run, and the warning says to put a longer program in a @NEW_FILE.

- Fix: a message from another chat, a scope change and an [UNBLOCKED] notice no longer count as delivered when the harness prints them: they stay in the footers of that chat until it sends its next numbered script, the only proof it read the output, so a script pasted again because its output never reached the chat shows them again. A replay, an undo from a re-paste, a refused script and a @SIDE or @REPEATABLE script show them without confirming them (at worst one repeat, never a loss).

- Fix: the rule for an accidental paste (an output the chat already answered, or one with no new information and no words from the user) and the LOOP CHECK line now ask the AI for one or two short, unformatted, discardable lines that say so and remind what is pending, instead of a manifest, a script and a checklist; the playful sample reply is gone, and a replay of a script whose output the chat never saw counts as new, not as an accidental paste.

- Fix: a message another chat sent to a session that was then merged away (--merge) is sent again to the session it was merged into, with a note, and the shared event log keeps every event addressed to a chat that has not read it yet (it kept only the newest 200, so a message for an idle chat could be trimmed away while others worked).

- @GIT_REMOTE [<name> [<url>]] lists the remotes, or adds a remote or changes its address (https or ssh only, no password or token inside, never removes or renames one) and prints the old and the new address; the rule "git only via @GIT_*" no longer leaves the AI without a way to set where code is published.
- @STEWARD [on | off]: the AI asks, the user's terminal asks one question (Enter agrees), and with no terminal, or in a @SIDE or @REPEATABLE script, nothing changes, so the user never has to remember the --steward command (it stays as a manual fallback).
- Fix: a .git folder counts as a git repository only with a HEAD inside it (or as a file, for a worktree); a folder holding only harness state ran in git mode, and @GIT_INIT answered that it was a repository already.

- Project stewardship is opt-in: the terminal command `harness.py --workspace <folder> --steward on|off` (kept per project on that machine, never inside the project; no argument says which) switches the new [L1-Steward] rule, which carries the backlog and review clauses that used to ride in [L1-Notes] for everyone, so a project that does not switch it on pays no footer words and gets no backlog file. A rule header may now carry the condition (steward). The @RUN refusal of the user's own commands now includes --link and --steward.

- Fix: a replayed script (an identical re-paste), an undo from a re-paste and a stale-script refusal now print a footer for the pasted script's own session (THIS SESSION, OTHER SESSIONS, WAITING ON, INHERITED, DELEGATED, the chat's pinned notes and its own list of unused commands) instead of a footer with no session, and they deliver what a normal run delivers, once (work that became free, messages and scope changes since); the saved execution output is still replayed as it was.

- Fix: the tree drift check (@PROBE <tree> | Check) recognises "# Stage:" comments that carry a run of dashes (as harness.py's own do) and "#*" section headings (as workflow_commands.txt's do); before, every tree node for them read as stale although the anchors existed. The same pattern drives the table-of-contents probe, scope anchors and block bounds.

- Fix: @GIT_PULL no longer aborts when the incoming commits change .llm_harness/tokens.json while it is modified here (it changes with every paste and is never committed alone): the local counts are set aside, the fast-forward runs, and they are merged back with the tokens merge rule, still uncommitted, with a note in the report.

- Fix: saved run outputs are pruned separately for numbered runs and @SIDE runs, so a flood of side runs no longer deletes the numbered runs (which broke @REDO and replay for them), and side runs are bounded too; a merged verdict record keeps its path field.

- Fix: the git rule no longer stays expanded for good in a project whose only uncommitted item is an untracked .llm_harness folder holding just tokens.json (a project that never pinned a goal or note): the status check lists untracked files one by one, so the token counts, which are never committed alone, are recognised.

- Planning procedures: `@PLAYBOOK` prints `plan-first` (one feature with a few decisions) and `plan-project` (a new project or a big redesign) from the `playbooks` folder on demand; they install next to the harness, while `docs/plan.md` stays in the project as a decision record. `[L1-Notes]` tells the AI to propose them only when a request forces several consequential decisions across systems, never for small work or one open question. A backlog, where stewardship is switched on: anything deferred, skipped, unverified or noticed is written to docs/backlog.md in the same script, and the review playbook reads it (with the Todo notes, stale verdicts, open debug ledgers and the Unreleased changelog) before work is called complete and at the end of a milestone or session; the review also records repeated friction and proposes improvements only from evidence, labelling the rest as speculative.

## 3.13

- A shared knowledge library of pitfalls that AIs keep falling into: `knowledge/<technology>.txt` (one entry per pitfall with id, tags, symptom, trap, fix, verified and optionally versions, replaces, obsolete), searched with `@HELP KB <technology or symptom words>` (or `@HELP KB` for the list), with a lint that catches missing fields, repeated ids and notes naming unknown entries; fifty-three seed entries (web pitfalls for NiceGUI, Vite, Vue, Quasar, AG Grid, SPA hosting and Google OAuth, plus Python, FastAPI, Docker, Polars and Discord); `[L1-Knowledge]` now tells the AI to search before using a library and after a failure. The search is project-aware: it shows only the technologies the project seems to use (judged from manifests, file types and imports) unless the words name one or include `all`, an entry needs a strong match or two matched words, and one common word pulls in nothing; setup.cmd and setup.sh install the library next to harness.py. `@KB <words>` is a short form of `@HELP KB <words>`, the listing says why each technology counts as used (a manifest word, an import, a file type), the footer names the technologies on file for the project the first time in a chat and again only when they change, and `sql` is detected by `*.sql` files and specific drivers, not by the bare word. The reason names the file that matched, a .csproj counts only its PackageReference lines (a generated project file lists libraries the project never uses), common words such as python do not name a technology, and an entry must cover at least 70% as much of the question as the best entry.

## 3.12

- Optional per-project check command for any file type: the user's terminal command `--check <.ext> <command>` (kept in a file in the harness's own folder, keyed by the project path, never in the project; `--check` alone lists, `--check <.ext> --clear` removes) makes the harness run that command once after a script changes a file of that type and report `PASS`, `CHECK FAILED` with the command's output, `CHECK UNCHECKED` or `CHECK TIMED OUT`; it never rolls anything back, and a script cannot set it.

- C# and Java methods with no modifier and the brace on the next line (Unity's `void Start()`, `void Update()`) are found: a type-shaped return type plus a `Type name` parameter list is enough, while prose lines, aligned tables and control-flow lines are not; `object`, `record` and `mod` need the shape of a declaration. On 660,000 lines of real Python the finder invents no definitions except genuine C code embedded in the files.

- `@HELP LANGUAGES` prints, from the harness's own tables, the comment marker per file extension, where the first-line header goes, which languages get symbol scoping and which get an automatic syntax check.

- Symbol scoping, `@XREF` and the Unused probe understand C#, Java, Kotlin, Swift, Rust, C and C++: modifiers such as `internal sealed partial virtual open suspend`, methods with a return type (with a modifier, or with a closing `{` or in column 0), constructors, Kotlin `fun`, `record`, `object`, `mod`, a bare `{` line as part of its block, and C# attribute lines above a definition; calls, conditions and control-flow lines are not mistaken for definitions, and `.cs .java .kt .rs .c .h .cpp .swift` and friends are scanned.

- Comment syntax is one table: the first-line `/<project>/<path>` header now uses the file's own marker for C#, Java, Kotlin, Swift, Dart, Scala, PHP, C and C++ variants, JSX and TSX (`//`), SQL and Lua (`--`), HTML, XML and Vue (`<!-- -->`), CSS and SCSS (`/* */`), TOML and PowerShell (`#`), below an HTML doctype, XML declaration or PHP opening tag; `[COMMENT REMOVED]` recognises `/* Comment`, `<!-- Comment` and `-- Comment` lines too, and `[L1-Scope]` tells the AI to write `Comment` lines in the file's own marker.
- A modified `tokens.json` alone no longer keeps `[L1-Git Gate]` expanded, so the idle rule folding can fold.

- `tokens.json` is no longer committed after every script: it is committed together with other memory changes and when a session ends, so the history is not buried in memory commits.

- Token tracking ignores Credential Manager's placeholder account name "Personal Access Token" and falls back to the git user name, so usage is filed under a real login.

- `[L1-Sessions]` and `[L1-Git Gate]` now fold into concise `L1 Brief` summaries when the workspace is single-session and git-clean, automatically expanding in full whenever multiple sessions, waiting/delegation/brake states, uncommitted changes, unpushed commits, or protected branches are active.
- `[COPIED]` now reports the estimated token count of the current paste, the active session's cumulative total, and the project-wide total across `<github_account>@<machine>` buckets (`~X tok this paste, ~Y tok session <name>, ~Z tok project total [<account>@<machine>]`), persisted in `.llm_harness/tokens.json` so uploaded branches keep account+machine usage cleanly separated and merge without conflicts.
- Users can now run `harness.py --workspace <folder> --merge <from_session> <into_session>` from their terminal to absorb a dead or already-released session's write scope, user grants, uncommitted history/undo ownership, pinned notes (`[pin: ...]`), verdicts, and delegation/waiting queues into an ongoing session.
- `LOOP CHECK` prompt wording now suggests a clearer, playful human-loop check when a user pastes three idle scripts in a row.
- POSIX and SSH terminals now track xterm `DECSET 1004` focus events (`\033[?1004h` / `\033[?1004l` on `/dev/tty` with `ECHO` suppressed and `termios` restored on exit) so runs auto-copy immediately when the SSH/POSIX terminal stays focused (or regains focus via `\033[I`) and fall back to prompting `Press C or Enter` if focus left via `\033[O`.
- Clipboard copy over SSH and headless POSIX terminals now sends an OSC 52 escape sequence (`\033]52;c;...\a`, with `tmux` passthrough when `TMUX` is set) to `/dev/tty` so output copies straight to the local client clipboard instead of failing on remote X11 `xclip`, and reports tool `stderr` when local clipboard commands fail.
- `[L1-Harness]` now explicitly names `Talk:` (with zero prose before the script header) and all 11 manifest labels in order so long chats never drift away from the manifest format.
- `[L1-Debug]` and its brief now distinguish fast-path fixes (proven cause in code/traceback, including Bug A exposing downstream Bug B) from structured escalation (`@INIT_DEBUG <slug>` when the next edit would be a guess, the same failure survives 2 fixes, or symptoms loop), choosing between real-module standalone reproduction (progressively reintroducing app state when standalone passes) and in-pipeline telemetry on coupled systems.
- `@SCOPE` accepts tree node paths (`docs/trees/tree_*.txt#Node > Path`) with validation that the target node resolves uniquely, and `[L1-Notes]` allows user-approved to-do list notes (`Todo: ...`).

## 3.11

- Bare `@CHAT_LINK` prompts the user directly at the terminal (retrying invalid addresses) so a chat inheriting a session or fixing a wrong address never has to ask the user to paste the URL into the chat.
- Footer and pre-push/pull account announcements warn when the project's pinned account is no longer signed in.
- `setup.sh` installs `xclip` (or `wl-clipboard` on Wayland) automatically on Linux when no clipboard tool is present.
- `tests/run_all.py` runs test suites in parallel and Linux pty tests disable the copy prompt (`LLM_HARNESS_NO_COPY=1`).
- Both account pickers offer A to sign another account in first (Git Credential Manager's `github login`) and then list again; with one account the prompt says "Press 1 to pin it", and without a terminal the listing names the command to run by hand.

- A push or pull you ask for names the pinned account first (`[ACCOUNT] signing in to github.com as <account> ...`), so a sign-in window that opens can be answered with the right account.

- The account listing and the first-push question show one account per line with the pinned one marked, and `[PINNED]` is one short line.
- A chat's address is required at a terminal (an empty or wrong answer asks again; sessions that skipped it before are asked on their next script), and the new `@CHAT_LINK <address>` replaces a wrong one: the user gives the address, the chat sends it.

- A push or pull you asked for asks once, with one key, which account to use when several are signed in and none is pinned for the project, and keeps the answer in the clone's git config (per project and per machine); the footer says why when the automatic fetch cannot sign in and nothing is pinned.

- `@GIT_ACCOUNT` lists the accounts signed in for the remote's host (GitHub through Git Credential Manager, or the Windows credential list) and pins one for the project (a number at the terminal, or by name; `clear` removes it) in the clone's git config, so git hands that username to the credential helper and stops showing the account chooser; an account that is not signed in is refused, and SSH remotes have nothing to pin.

- The automatic fetch behind the `UPSTREAM` line asks Git Credential Manager not to open a sign-in or account window (`GCM_INTERACTIVE=never`) and is skipped when it cannot authenticate by itself; a fetch you ask for with `@GIT_PULL` may still ask.

## 3.10

- The harness's committed notes and verdicts merge by themselves: with the two `.gitattributes` lines (`@GIT_INIT` writes them), git merges `notes.md` by note id (both sides' new notes kept, a clashing id renumbered) and `verdicts.json` by key (the newer wins), through a merge driver the harness registers in each clone; the UPSTREAM line hints when incoming memory arrives without the lines.
- A refusal about uncommitted or untracked changes (branch, worktree, tag, pull) now names the files in the way; `@GIT_INIT` says to commit `.gitattributes` with `.gitignore`.

- The footer says `UPSTREAM` when the branch's remote has commits this checkout lacks (fetched at most once a minute, quietly; `LLM_HARNESS_FETCH=off` or a number of seconds), sorting the incoming files into inside your scope, project memory and other files. `@GIT_PULL` fast-forwards a clean checkout and bookmarks where it was; a diverged branch is only reported (a dry-run merge says whether it would conflict) and nothing changes.

- `@RUN` allows the reading forms of `git tag` (listing) and `git stash` (`list`, `show`); creating or deleting a tag and stashing are still refused.

- On Windows, when the terminal is still the window in front at the end of a run, the output is copied at once without the question (also after a replay, or with `LLM_HARNESS_COPY=auto`); a terminal in the background still waits for a key, and `LLM_HARNESS_COPY=ask` always asks.

- `@GIT_PUSH` publishes the current branch's commits (setting the upstream the first time) or, as `@GIT_PUSH tag <name>`, one tag: never forced, never a protected branch, a rejected push is reported and never overridden; a raw `git push` through `@RUN` is still refused, now pointing to `@GIT_PUSH`.
- After a replay the output is copied to the clipboard at once, without the question.

- `@DELEGATE <chat> | <paths> | <task>` and `@RETURN <chat> | <result>`: a chat hands files and a task to another chat at once (no acceptance step), with its uncommitted work in them; the receiver's footer says `INHERITED`. Returned files are released, not handed back; a chat holding delegated work cannot release or end until it returns it or ends with `drop`. The `DEADLOCK` line offers delegation as a way out.

- When chats wait on each other's files in a circle (two or more), every footer in the circle says `DEADLOCK` and names who waits on whom; a wait whose holder has let go does not count.

## 3.9

- `@FIND` and the `| in` filter of `@GREP` accept `re:<regex>` on the path.
- `@UNDO`: several lines in one script all run (the last used to win); paths may be comma-separated or globs; `/old -> /new` (or `-> /folder/`) recovers a file as it was to another path.
- Folders emptied by a rename or delete are removed up to the workspace root (`__pycache__`-only counts as empty); one that cannot be removed is named, with its holder when `psutil` is installed.
- Fixed: a glob in `@SCOPE` collided with every file in the workspace (`/why*.txt`) or with other folders and extensions; it now collides only with files it really matches. A file name with a space can stay in scope after the file is deleted.
- In a git project the harness commits its project memory (goal, notes, verdicts, `git.json`) after each script that changes it (not on a protected branch).
- After three footer-only scripts in a row the footer says `LOOP CHECK` and the rules tell the AI to drop the manifest and ask the user whether they are still there.
- At a terminal the harness offers to copy the run's output to the clipboard (press C or Enter to copy, X to skip; `LLM_HARNESS_NO_COPY=1` turns the prompt off).
- Fixed: state files were rewritten in place, so another chat could read one empty or half-written (an empty `sessions.json` read as "no scope"); they are now replaced whole, and if a reader holds the file for seconds the save falls back to rewriting in place instead of failing.
- The clipboard copy on Windows uses the clipboard API directly, with PowerShell as a fallback; when both fail, the message says why.
- `@RUN` tells Python children to write UTF-8 to the pipe the harness reads, so Vietnamese and other non-Latin text prints correctly on Windows without `sys.stdout.reconfigure` in the script.
- Fixed (Windows): a state file that another chat is replacing, and that is refused for a moment, is retried instead of being read as missing (which read a live `sessions.json` as "no scope").
- `setup.cmd` and `setup.sh` pull the latest changes first (`git pull --ff-only`) when their folder is a git clone, then install; a pull that fails warns and installs the files already there.

## 3.8

- Fixed: the tree check treats extensionless files (Dockerfile, Makefile, Jenkinsfile, LICENSE, dotfiles) as files, so a missing one is reported, and a `# Stage` node must match a real anchor comment rather than the same words anywhere in the file.
- `@GIT_COMMIT` checks the message (`type(scope): subject`, conventional types) before committing; an optional `.llm_harness/git.json` refuses commits on protected branches and over-long headers, warns about branch names, and is shown in the footer.
- Git worktrees run in git mode: script numbering and its lock are shared through the repository's common git folder, while sessions, scopes, the undo journal and saved runs stay with each worktree.
- `@GIT_BRANCH <name> [from <base>]`, `@GIT_WORKTREE add <branch> [from <base>] / list / remove <branch or path>` and `@GIT_TAG <vX.Y.Z> [| message]`, all through one repository safety guard (no local changes, no unfinished git operation, no other active chat for branch switches) and the optional `git.json` policy (`branches`, `tags_from`, `tag_changelog`); new repositories keep `.llm_harness/git.json` tracked (existing ones add `!.llm_harness/git.json` to `.gitignore`).
- Fixed: a `@TEXT_REPLACE` on a file renamed earlier in the same script counts in the file's old location and edits it after the rename (it used to be refused with 0 occurrences); a rename rewrites the line-1 path header at once, so later hunks in the same script see the new header.
- `@RENAME` on a folder moves it file by file through the journal (`@UNDO` brings it back; claims apply per file; refused whole when the destination exists, the folder holds a symbolic link, or the move is into itself or case-only).
- Fixed: renaming a file keeps its exact bytes; a renamed binary file used to gain a trailing newline.
- `tests/run_all.py [path to harness.py]` runs every suite with one summary; a GitHub Actions workflow (`.github/workflows/tests.yml`) runs it on Windows and Linux for every push and pull request.

## 3.7

- Rules: chats leave knowledge, not narration: non-obvious reasons go into `Comment` lines above the code they explain, optionally categorised as constraint, workaround, invariant, order or decision; a nuance in code not being changed is reported instead of commented.
- A change that deletes a `Comment` line prints `[COMMENT REMOVED]` with its text, so the reason gets a second look; nothing is refused.
- Fixed: the closing hint after `[REFUSED]` no longer always blames the path; it points at each refusal's stated reason. A space-separated `@SCOPE` entry that names nothing gets "separate scope paths with commas".
- The tree reminder skips names the tree files already describe, and reports a removed name only while a tree still mentions it.
- `@UNDO <script> | /path` (or a range) restores only that file; the rest of those scripts stays.
- A standing rule that changed since a chat last saw it is printed once as `[CHANGED] [L1-...]` in that chat's footer.
- Rules invite `+++ [LINE EDITS] +++` for small changes in long blocks and show its syntax; a hunk that resent a long, mostly unchanged block gets a `[TIP]` with how many line edits it would have needed.
- Line edits that rewrite most of their block get the reverse `[TIP]`: plain `+++ [NEW CODE] +++` is clearer for rewrites. Tips never stop an edit.
- `@DELETE_FILE` takes folders and globs; every deleted file goes into the script's journal first and the scorecard says how to get it back with `@UNDO`; claims apply file by file. Fixed: deleting a folder no longer reports "already applied" while doing nothing.
- `@UNDO` skips files that another chat now holds, naming that chat.
- Notes are pinned with `@NOTE_ADD pin <sessions> | <text>` (`for` still works) and listed as `[pin: ...]`; `@NOTE_LIST <words>` finds notes by category (a leading `Bug:`, `Decision:` ...) or content.
- Rules: no payload line may begin with an apostrophe followed by @, because PowerShell's script block ends there.
- A project without git says so in every footer (`NO GIT HERE`); when it becomes a git repository, each chat is told once and newly applying rules are marked `[NEW]` once.
- Collapsed rules: a rule with an `L1 Brief` line prints as its brief, and the harness prints the full rule in its place when this run had a failure or a debug ledger is open; `@HELP L1-<name>` prints any rule in full. Knowledge and Debug collapse; the others stay in full.
- `@REDO <n>` reruns script n's saved text under a new number, with `OLD TEXT` / `NEW TEXT` corrections and any extra directives, instead of resending the whole script; numbered runs now keep their script text.

## 3.6

- A chat with a session changes only files inside its own write scope or a user grant; anything else is refused, and a claim in the same script counts.
- Fixed: a folder scope with a depth no longer counts as overlapping files below that depth.

- Scopes on `# Stage` anchors (`file#Class.method > # Stage: Name`, `file## Stage: Name`) are compared by line range, so claiming a function that contains another session's stage is refused; claims on part of a file no longer trigger the width warning.
- A script that commits its work and releases its scope (`@SCOPE_END` / `@SESSION_END`) now commits first, so the release is no longer refused.
- Each session can remember its chat's address: asked once at the terminal or set with `--link`, and shown in the session list and in every refusal involving that session.
- Terminal questions discard anything typed or pasted before they appear, so a second paste can no longer answer them; only web addresses are stored as chat addresses, and a bad one is asked for again.
- In a chat, the footer's `[L1-Commands]` lists only the commands that chat has not used yet (directives it sent, not text inside hunks or replacements); `@HELP COMMANDS` prints the full list.
- Work refused because another session holds it is remembered under WAITING ON, the holder is told once, `[UNBLOCKED]` announces when it is free, and `@SESSION_END` waits for it unless followed by `drop`.
- Notes can be aimed at particular chats or a session-name pattern (`@NOTE_ADD for <sessions> | <text>`); only those chats see them in their footers, and `@NOTE_LIST` shows each note's audience.
- Rules: reason comments (`Comment:`) record non-obvious constraints, workarounds and orderings directly above the code they cover, and are kept while their reason holds, beside the `# Stage` anchors used for navigation.
- `@PART <i>/<n>` lets one reply carry several scripts (for example a long command run apart from many inspections); only the last part prints the goal, notes and standing rules.
- Each chat keeps its own verdict on a path: a second chat's verdict no longer overwrites the first, listings, reads and tree marks show both, and `| clear` removes only the calling chat's.
- Releasing a scope (`@SCOPE_END`, `@SESSION_END` or the user's `--release`) prints `[WAKE]` for every chat that was waiting on it, with its chat address, so the user can open it.

## 3.5

- `gofmt -w` formats Go files after a hunk, so tabs pasted as spaces no longer roll the file back; only real syntax errors do.
- A `@GIT_COMMIT` path list without `@END_GIT_COMMIT` closes at the next directive instead of dropping the commit.
- The cross-process state lock treats Windows' "delete pending" error as busy, so concurrent sessions no longer crash on it.
- `CHANGELOG.md`, and a reminder when a `feat`, `fix` or `perf` commit leaves it out.
- README: step-by-step install for Windows and Linux, session start for both, and moving to another computer.
- `+++ [LINE EDITS] +++` in hunks: change, delete or insert lines by their number inside the matched OLD CODE, without reciting the block twice.
- `| depth N` on `@FIND`, `@GREP`, `@LIST_RECURSIVE` and `@TEXT_REPLACE`, and one glob rule for all of them: with a `/` a glob starts at the root and `*` stays in one folder; without one it matches file names at any depth.
- Scopes may own a single definition (`file#Class.method`), leaving the rest of the file to other sessions, or a folder to a set depth (`pkg depth 1`).
- A hunk counts as already applied only when its OLD CODE is found nowhere in the file, not merely outside its named scope.
- A last matching pass ignores whitespace inside lines, so tabs pasted as spaces no longer cause mismatches.
- `[MALFORMED]` hints fit the actual problem, and `# Stage` changes only trigger the tree reminder in files whose stages the trees track.
- Pasting a script that already ran asks at the terminal: replay it, undo it with that chat's later scripts (after a preview and a yes; committed work is kept), or execute it again.

## 3.4

- `@TEXT_REPLACE`: count-locked text edits inside a line, a definition (`file#Class.method`) or a whole folder.
- Inspection log and `[REVISIT]`: rereads of unchanged definitions say who read them and when.
- `@VERDICT` / `@VERDICTS`: conclusions about folders, files and definitions that travel with git, go stale when their area changes, and show on reads.
- `@CAMPAIGN` / `@CAMPAIGN_END`: a sweep's verdict legend, footer line and rule while it runs, tree overlay, one-step cleanup.
- `@REPEATABLE`: scripts the user reruns by hand run on every paste.
- Sessions: each chat's own aim, uncommitted work owned per session (release and commit guards, hand-over), `@MESSAGE`, `@SCOPE_REQUEST`, `@BRAKE` / `@BRAKE_ACK`, and the user's `--release` / `--unbrake`.
- The user's notes show in every footer.
- Rule: files are edited by content only, never by line numbers or `@RUN` rewrites.

## 3.3

- Harness-assigned script numbers under a cross-process lock, and `@SESSION`.
- `@SCOPE` write scopes: overlaps refused, edits into another session's scope refused, `@RUN` changes there reported, scope changes announced once, the user's `--grant`.
- `@HELP` and the full command list in every footer.
- A nudge when a script only did git work, and a hint when a one-line OLD CODE is only part of a line.

## 3.2 and earlier

- Content-matched hunks with syntax rollback, an undo journal, a git gate, and replay of lost output.
- Code graph through codebase-memory-mcp (callers, callees, impact, coverage warnings), `| Unused`, `| Refs` and call-site lines.
- Tree drift check, `@SIDE`, `@GIT_INIT`, user-owned notes, timings, and the README.
