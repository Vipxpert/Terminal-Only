# OpenCode adapter (agent mode)

OpenCode can run harness scripts without this adapter, but then it is unguarded: full rules after every run, and nothing stops it from running other commands or using its own file tools. This adapter adds the guarded agent mode, the same as the Claude Code adapter: the rules once per prompt, the harness as the only allowed command, and the harness's own refusals. Not yet tried: until the bypass trial below passes, treat OpenCode as unguarded.

Written for OpenCode 2.4.1 (V2 plugin and permission API). V1 uses a different API: check `opencode --version`.

## Setup

1. Install the plugin outside your projects, so an unfamiliar repository cannot auto-load a plugin that starts processes: copy the `terminal-only` folder from here to `%USERPROFILE%\.llm_harness\opencode\terminal-only\`, and add its absolute path (`C:/Users/<you>/.llm_harness/opencode/terminal-only/index.ts`) to the plugins array of your user OpenCode configuration (see OpenCode's docs for where that file lives on Windows). Do not put it under a project's `.opencode/plugins/`.
2. Copy `opencode.jsonc.example` to `<project>\.opencode\opencode.jsonc` and replace `<USER>`. The shell rule must match the command exactly; if you set `LLM_HARNESS_PYTHON` to a full path to Python, the rule must use that same path.
3. Start a new session, or switch an existing one to the `terminal-only` agent: an existing session keeps the agent it was created with.
4. Allow, at your own terminal, each command the agent may run through `@RUN` (empty by default): `python harness.py --workspace <project> --agent-allow <program> [<argument pattern>]`, `list`, `clear`.

## What happens on each prompt

The plugin's prompt hook reads the project folder from the session, runs `harness.py --workspace <folder> --new-turn <messageID>` directly (no shell), and appends the result to your prompt: the turn number, the harness session this OpenCode session works as, and the one command the AI may use. If that fails, the hook throws and OpenCode does not admit the prompt. The shell hook sets `LLM_HARNESS_AGENT`, `LLM_HARNESS_HOST=opencode` and the host session for the AI's shell commands, so the harness knows it runs in agent mode. In agent mode the harness refuses terminal questions, any `@RUN` not on the allowlist, and every git change; the AI asks you in its reply for anything that needs approval.

## Limits

OpenCode's permissions restrict its tools; they are not an operating-system sandbox, and shell commands have your Windows user's rights. Do not use the explore agent (its built-in rules re-allow tools). Two details are inferred and the trial will show them: where the session's subpath sits, and whether the plugin package resolves for a plugin loaded from outside the project.

## Bypass trial (run once after setup)

Must happen:
- one prompt runs the prompt hook once, and the briefing names the right OpenCode session and turn
- several harness scripts in that prompt do not repeat the full rules
- the exact piped harness command works
- a failed briefing (for example, temporarily rename harness.py) keeps the prompt from being admitted

Must be refused:
- direct read, edit, write, search, web and MCP tools, and Code Mode
- any other shell command (`Get-ChildItem`, `python -c "print(1)"`, another script)
- launching a subagent, or switching to the build or plan agent
- a harness script with `@RUN` not on the allowlist, or `@GIT_COMMIT` / `@GIT_PUSH`
