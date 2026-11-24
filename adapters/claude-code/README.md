# Claude Code adapter (agent mode)

Claude Code drives the harness itself inside one prompt: it thinks, pipes harness scripts into `harness.py` through its PowerShell tool, reads the output and answers you in plain prose. The chat-browser flow is unchanged; agent mode is on only where `LLM_HARNESS_AGENT` is set, which this adapter's settings do.

Windows, PowerShell tool only. Needs Claude Code 2.1.295 or later (for the hook's `onFailure: "block"`).

## Setup

1. Copy `new_turn_hook.py` from this folder to `%USERPROFILE%\.llm_harness\new_turn_hook.py`.
2. Copy `settings.local.json.example` to `.claude\settings.local.json` in your project, and replace `<USER>` (twice) with your Windows user name. The allow rule must match the command exactly: `python 'C:\Users\<you>\.llm_harness\harness.py'`. Never widen it to `python *`, which would allow any Python script.
3. In Claude Code, check `/permissions` and `/status`: the PowerShell tool is on, Bash is off, the listed tools are denied. Tool names that your version does not know should be checked, not assumed.
4. Allow, at your own terminal, each command the agent may run through `@RUN` (empty by default, so every `@RUN` is refused): `python harness.py --workspace <project> --agent-allow pytest -q tests` (program by name, then a pattern the whole argument string must match), `--agent-allow list`, `--agent-allow clear`.

## What happens on each prompt

The `UserPromptSubmit` hook runs `harness.py --workspace <project> --new-turn <prompt_id>` for Claude Code's session and hands the result back as context: the turn number, the harness session this Claude Code session works as, and the one command it may use. The first harness run of the prompt prints the full standing rules; later runs in the same prompt print only new, changed or newly triggered ones. If the turn cannot start, the hook exits 2 and the prompt is held back, so the agent never works without its rules. The hook briefs on every prompt, including scheduled tasks, subagent reports and messages from other sessions, because Claude Code does not reliably tell them apart.

In agent mode the harness itself also refuses: terminal questions (they get no answer), every `@RUN` not on the allowlist or using shell operators, and every git change (commit, push, pull, branch, tag). The agent asks you in its reply for anything that needs approval; commit from the chat-browser flow or your own terminal.

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
- the reply comes back as plain prose, and the full rules appear once per prompt
