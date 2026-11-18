# Changelog

Notable changes to llm_harness, newest first. Each `feat`, `fix` or `perf` commit adds a line under **Unreleased**; a version bump moves those lines under the new version's heading.

## Unreleased

- Fixed: the tree check treats extensionless files (Dockerfile, Makefile, Jenkinsfile, LICENSE, dotfiles) as files, so a missing one is reported, and a `# Stage` node must match a real anchor comment rather than the same words anywhere in the file.
- `@GIT_COMMIT` checks the message (`type(scope): subject`, conventional types) before committing; an optional `.llm_harness/git.json` refuses commits on protected branches and over-long headers, warns about branch names, and is shown in the footer.
- Git worktrees run in git mode: script numbering and its lock are shared through the repository's common git folder, while sessions, scopes, the undo journal and saved runs stay with each worktree.
- `@GIT_BRANCH <name> [from <base>]`, `@GIT_WORKTREE add <branch> [from <base>] / list / remove <branch or path>` and `@GIT_TAG <vX.Y.Z> [| message]`, all through one repository safety guard (no local changes, no unfinished git operation, no other active chat for branch switches) and the optional `git.json` policy (`branches`, `tags_from`, `tag_changelog`); new repositories keep `.llm_harness/git.json` tracked (existing ones add `!.llm_harness/git.json` to `.gitignore`).
- Fixed: a `@TEXT_REPLACE` on a file renamed earlier in the same script counts in the file's old location and edits it after the rename (it used to be refused with 0 occurrences); a rename rewrites the line-1 path header at once, so later hunks in the same script see the new header.

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
