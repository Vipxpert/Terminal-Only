# OpenCode adapter (auto-shell)

OpenCode can do everything Claude Code does here; this adapter gives it the same auto-shell experience. In a Terminal-Only project (a folder with `.llm_harness/`) OpenCode pipes harness scripts through its shell tool, gets `MODE: auto-shell` and a briefing on each prompt, and may use only the harness; in every other project OpenCode works as usual. The chat-browser flow is unchanged.

Written for OpenCode 2.4.1 (V2 plugin API). Not yet installed live and not security-validated: until the trial below passes on your version, treat OpenCode as unguarded.

## Setup

Run `setup.cmd` once. If OpenCode's config folder exists (`%USERPROFILE%\.config\opencode`, or `%XDG_CONFIG_HOME%\opencode`), setup copies the plugin to `plugins\terminal-only\` there, where OpenCode loads it automatically. Nothing per project or per session. If OpenCode is installed later, run `setup.cmd` again. Existing sessions keep their agent; start a new session.

Optionally, allow at your own terminal each command the AI may run through `@RUN` (empty by default): `python harness.py --workspace <project> --agent-allow <program> [<argument pattern>]`, `list`, `clear`.

## What the plugin does

- **Prompt hook:** reads the session's project folder, finds the Terminal-Only project from it (the nearest folder with `.llm_harness/`, never the install or home folder), and only there starts a harness turn with the message id, appends `MODE: auto-shell` and the briefing, and rejects the prompt if the turn cannot start.
- **Tool hook (`execute.before`):** only in a Terminal-Only project, allows only the `shell` tool running exactly one single-quoted here-string piped into `python` and the installed `harness.py`; every other tool, and every other command, is rejected with the way to do it through the harness. Subagents and child sessions run the same hook. If the session's folder cannot be read, nothing is blocked.
- **Shell hook:** sets the auto-shell environment for the AI's shell commands.
- In auto-shell the harness itself refuses terminal questions, any `@RUN` not on the allowlist, and every git change; the AI asks you in its reply for anything that needs approval.

## Emergency exit

`%USERPROFILE%\.llm_harness\unblock_auto_shell.cmd` (no Python) also switches the plugin off by renaming its `index.ts` to `index.ts.disabled`; run `setup.cmd` again to switch it back on. Or toggle the plugin in OpenCode's plugin manager, or add `"-terminal-only"` to its plugin list.

## Limits

OpenCode's tool guard is not an operating-system sandbox; the shell has your Windows user's rights. Do not use the explore agent. Inferred and to confirm in the trial: where the session's subpath sits, and that `@opencode/plugin` resolves for a plugin in the global folder.

## Trial (run once after setup; mark the adapter validated only when all pass)

Harness project:
- one prompt runs the prompt hook once; the briefing names the right OpenCode session and turn; several harness scripts in that prompt do not repeat the full rules; the exact piped harness command works
- main agent: direct read, edit, write, search, web and MCP attempts are rejected, and so is any other shell command (`Get-ChildItem`, `python -c "print(1)"`)
- subagent: the same attempts are rejected, and the plugin sees the child session id
- Code Mode: nested tool calls are rejected (the event carries a `codemode` flag)
- Batch: confirm it cannot run nested tools around the guard (an old upstream report said it could)
- a failed briefing (temporarily rename harness.py) keeps the prompt from being admitted
- a harness script with `@RUN` not on the allowlist, or `@GIT_COMMIT` / `@GIT_PUSH`, is refused

Ordinary project:
- OpenCode works as usual: no briefing, no refusals, and the emergency exit leaves other settings alone
