# /llm_harness/adapters/claude-code/install_hooks.py
"""Registers the Terminal-Only auto-shell hooks in Claude Code's user settings (~/.claude/settings.json), once per computer, so every Terminal-Only project opens in auto-shell and every other project stays normal Claude Code. It keeps every other setting, writes a backup first, replaces its own older entries instead of adding duplicates, leaves a file it cannot read untouched, and --uninstall removes only its own entries. Windows only for now: the tool guard allows the PowerShell tool."""
import json, os, shutil, sys

MARKS = ("auto_shell_hook.cmd", "auto_shell_hook.ps1", "new_turn_hook.py", "pretooluse_hook.py")


def ours(hook):
    text = " ".join([str(hook.get("command", ""))] + [str(a) for a in (hook.get("args") or [])])
    return any(m in text for m in MARKS)


def strip(settings):
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return
    for event in list(hooks):
        groups = hooks[event]
        if not isinstance(groups, list):
            continue
        kept = []
        for g in groups:
            if isinstance(g, dict) and isinstance(g.get("hooks"), list):
                g = dict(g, hooks=[h for h in g["hooks"] if not (isinstance(h, dict) and ours(h))])
                if not g["hooks"]:
                    continue
            kept.append(g)
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks:
        settings.pop("hooks", None)


def entry(launcher, mode, timeout):
    # Comment (decision): the hooks start with a cmd front that recognises the project from the working folder without PowerShell or Python (/q keeps its output clean, /d skips AutoRun), so ordinary projects pay almost nothing and a broken Python blocks only Terminal-Only projects
    return {"type": "command", "command": "cmd", "args": ["/d", "/q", "/c", launcher, mode], "timeout": timeout, "onFailure": "block"}


def main(argv):
    def opt(name, default):
        return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default
    uninstall = "--uninstall" in argv
    target = opt("--settings", os.path.join(os.path.expanduser("~"), ".claude", "settings.json"))
    hooks_dir = opt("--hooks-dir", os.path.dirname(os.path.abspath(__file__)))
    if os.name != "nt" and "--any-os" not in argv:
        print("Claude Code auto-shell: Windows only for now (its tool guard allows the PowerShell tool); skipped.")
        return 0
    if not os.path.isdir(os.path.dirname(target)):
        print("Claude Code auto-shell: Claude Code's settings folder %s was not found, so nothing was installed; run setup again after installing Claude Code." % os.path.dirname(target))
        return 0
    settings = {}
    if os.path.exists(target):
        try:
            with open(target, encoding="utf-8") as f:
                settings = json.load(f)
            if not isinstance(settings, dict):
                raise ValueError("not a JSON object")
        except (ValueError, OSError) as e:
            print("WARNING: Claude Code auto-shell: %s could not be read as JSON (%s); it was left untouched and the hooks were not installed." % (target, e))
            return 0
        shutil.copy2(target, target + ".llm_harness-backup")
    strip(settings)
    if not uninstall:
        hooks = settings.setdefault("hooks", {})
        hooks.setdefault("UserPromptSubmit", []).append({"hooks": [entry(os.path.join(hooks_dir, "auto_shell_hook.cmd"), "prompt", 30)]})
        hooks.setdefault("PreToolUse", []).append({"matcher": "*", "hooks": [entry(os.path.join(hooks_dir, "auto_shell_hook.cmd"), "pretool", 15)]})
        env = settings.setdefault("env", {})
        if isinstance(env, dict):
            env.setdefault("CLAUDE_CODE_USE_POWERSHELL_TOOL", "1")
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    os.replace(tmp, target)
    print("Claude Code auto-shell: %s %s (backup next to it when it existed)." % ("hooks removed from" if uninstall else "hooks registered in", target))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
