# /llm_harness/tests/install_hooks_test.py
"""Installer test for the Claude Code auto-shell hooks: it keeps existing settings and other hooks while adding its own two hooks and the PowerShell-tool switch, adds no duplicates on a second run, leaves an unreadable settings file untouched, removes only its own entries with --uninstall, and writes nothing when Claude Code's folder is missing."""
import json, os, subprocess, sys, tempfile

INSTALLER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "adapters", "claude-code", "install_hooks.py")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def inst(*args):
    p = subprocess.run([sys.executable, INSTALLER, "--any-os"] + list(args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def count(s, event, name):
    return sum(1 for g in s.get("hooks", {}).get(event, []) for h in g.get("hooks", []) if name in " ".join(h.get("args", [])))


def main():
    base = tempfile.mkdtemp(prefix="harness-install-")
    claude = os.path.join(base, ".claude")
    os.makedirs(claude)
    settings = os.path.join(claude, "settings.json")
    other = {"matcher": "Write", "hooks": [{"type": "command", "command": "other-tool"}]}
    with open(settings, "w", encoding="utf-8") as f:
        json.dump({"model": "x", "permissions": {"allow": ["Bash(ls)"]}, "hooks": {"PreToolUse": [other]}}, f)
    hd = os.path.join(base, "hooks")
    code, out = inst("--settings", settings, "--hooks-dir", hd)
    s = load(settings)
    check("existing settings and another tool's hook are kept, and both hooks and the PowerShell switch are added", code == 0 and s.get("model") == "x" and s["permissions"]["allow"] == ["Bash(ls)"] and other in s["hooks"]["PreToolUse"]
          and count(s, "PreToolUse", "auto_shell_hook.cmd") == 1 and count(s, "UserPromptSubmit", "auto_shell_hook.cmd") == 1 and s["env"].get("CLAUDE_CODE_USE_POWERSHELL_TOOL") == "1", (out, s))
    inst("--settings", settings, "--hooks-dir", hd)
    s = load(settings)
    check("a second run adds no duplicates", count(s, "PreToolUse", "auto_shell_hook.cmd") == 1 and count(s, "UserPromptSubmit", "auto_shell_hook.cmd") == 1, s)
    broken = os.path.join(base, ".claude", "broken.json")
    with open(broken, "w", encoding="utf-8") as f:
        f.write("{ not json")
    code, out = inst("--settings", broken, "--hooks-dir", hd)
    check("an unreadable settings file is left untouched", code == 0 and open(broken, encoding="utf-8").read() == "{ not json" and "left untouched" in out, out)
    code, out = inst("--settings", settings, "--hooks-dir", hd, "--uninstall")
    s = load(settings)
    check("--uninstall removes only its own entries", count(s, "PreToolUse", "auto_shell_hook.cmd") == 0 and "UserPromptSubmit" not in s.get("hooks", {}) and other in s["hooks"]["PreToolUse"] and s.get("model") == "x", (out, s))
    missing = os.path.join(base, "nowhere", ".claude", "settings.json")
    code, out = inst("--settings", missing, "--hooks-dir", hd)
    check("without Claude Code's folder nothing is written", code == 0 and not os.path.exists(missing) and "nothing was installed" in out, out)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
