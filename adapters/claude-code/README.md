# Claude Code adapter (auto-shell)

Claude Code drives the harness itself inside one prompt: it thinks, pipes harness scripts into `harness.py` through its PowerShell tool, reads the output and answers you in plain prose. It does this by itself in any Terminal-Only project (a folder with `.llm_harness/`); in every other project Claude Code works as usual. The chat-browser flow is unchanged.

Windows, PowerShell tool. Needs Claude Code 2.1.295 or later (for the hooks' `onFailure: "block"`).

## Setup

Run `setup.cmd` once. It copies this folder's hooks into `%USERPROFILE%\.llm_harness` and registers two hooks in your user Claude Code settings (`%USERPROFILE%\.claude\settings.json`), keeping every other setting and writing a backup first. Nothing is needed per project or per chat. If Claude Code is installed later, run `setup.cmd` again. `python %USERPROFILE%\.llm_harness\install_hooks.py --uninstall` removes the two hooks.

Optionally, allow at your own terminal each command the AI may run through `@RUN` (empty by default, so every `@RUN` is refused): `python harness.py --workspace <project> --agent-allow pytest -q tests` (program by name, then a pattern the whole argument string must match), `--agent-allow list`, `--agent-allow clear`.

## What happens on each prompt

Both hooks start with a tiny `auto_shell_hook.cmd` that looks for the project from the working folder and its parents, so ordinary projects never start PowerShell or Python; inside a project (or when Claude Code falls back to the home or temp folder) it hands over to a PowerShell launcher (`auto_shell_hook.ps1`) that finds the project from the hook's cwd, still without Python: the nearest folder with `.llm_harness/` or `.git/llm_harness/` (never the harness's install folder or your home folder). Outside such a project they stay silent. Inside one, the `UserPromptSubmit` hook runs `harness.py --workspace <project> --new-turn <prompt_id>` and hands Claude Code `MODE: auto-shell`, the turn number, the harness session this Claude Code session works as, and the one command it may use; the first harness run of the prompt prints the full standing rules, later runs only new, changed or newly triggered ones. If the turn cannot start, the hook exits 2 and the prompt is held back. The `PreToolUse` hook (every tool) allows only that harness call through the PowerShell tool and denies every other tool, with the way to do it through the harness. The prompt hook briefs on every prompt, including scheduled tasks, subagent reports and messages from other sessions, because Claude Code does not reliably tell them apart.

In agent mode the harness itself also refuses: terminal questions (they get no answer), every `@RUN` not on the allowlist or using shell operators, and every git change (commit, push, pull, branch, tag). The agent asks you in its reply for anything that needs approval; commit from the chat-browser flow or your own terminal.

## Emergency exit

If Python breaks, only Terminal-Only projects are blocked (tools denied, prompts held back); other projects keep working, because the launcher recognises the project without Python. To switch auto-shell off completely:

- Double-click `%USERPROFILE%\.llm_harness\unblock_auto_shell.cmd`. It needs no Python, backs up `%USERPROFILE%\.claude\settings.json`, removes only Terminal-Only's two hooks (every other hook and setting stays) and tells you to restart Claude Code. Run `setup.cmd` again to reinstall them.
- Claude Code's own switch, which turns off all hooks, not only these: `"disableAllHooks": true` in its settings (a project's settings can override it), or for one run `claude --settings '{"disableAllHooks": true}'`. `/hooks` only shows hooks; it does not switch them off.
- OpenCode: toggle the terminal-only plugin in its plugin manager, or add `"-terminal-only"` to its plugin list.

## Limits

Claude Code's permissions restrict its tools; they are not an operating-system sandbox. Code running inside an allowed Python process has your Windows user's rights. That is why the harness keeps its own allowlist and refusals. For a stronger boundary, use a restricted account or a separate sandbox.

## Bypass trial (run once after setup)

Ask Claude Code to do each of these, and check the result. Everything in the first list must be refused; the second list must work.

Must be refused:
- read a file directly (Read tool), search files (Grep, Glob), edit or write a file directly (Edit, Write)
- run a plain PowerShell command, such as `Get-ChildItem`
- run `python -c "print(1)"`, or `python` with any other script
- fetch a web page (WebFetch, WebSearch)
- a harness script with `@RUN` of a command that is not on the allowlist, or with `;` or `|` after an allowlisted one
- a harness script with `@GIT_COMMIT` or `@GIT_PUSH`

Must work:
- a harness script that lists, probes or searches the project
- a harness script that edits a file inside a claimed `@SCOPE`
- the reply comes back as plain prose, and the full rules appear once per prompt; and in a project that is not Terminal-Only, Claude Code works as usual (no briefing, no refusals)
