# /llm_harness/tests/unblock_test.py
"""Emergency-exit test (Windows): after the installer, unblock_auto_shell.ps1 removes only Terminal-Only's hooks from Claude Code's settings (another tool's hook and the other settings survive, a backup is written), and running the installer again puts them back once."""
import json, os, subprocess, sys, tempfile

ADAPTER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "adapters", "claude-code")
RESULTS = []


def check(name, ok, out=""):
    RESULTS.append(ok)
    print("%s %s" % ("PASS" if ok else "FAIL", name))
    if not ok and out:
        print("    ..." + str(out)[-900:].replace("\n", "\n    "))


def ours(s):
    return sum(1 for groups in s.get("hooks", {}).values() for g in groups for h in g.get("hooks", []) if "auto_shell_hook.cmd" in " ".join(h.get("args", [])))


def load(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def main():
    if os.name != "nt":
        print("SKIP unblock_test: Windows only")
        return
    base = tempfile.mkdtemp(prefix="harness-unblock-")
    os.makedirs(os.path.join(base, ".claude"))
    settings = os.path.join(base, ".claude", "settings.json")
    other = {"matcher": "Write", "hooks": [{"type": "command", "command": "other-tool"}]}
    with open(settings, "w", encoding="utf-8") as f:
        json.dump({"model": "x", "hooks": {"PreToolUse": [other]}}, f)
    install = [sys.executable, os.path.join(ADAPTER, "install_hooks.py"), "--any-os", "--settings", settings, "--hooks-dir", ADAPTER]
    subprocess.run(install, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    before = ours(load(settings))
    p = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(ADAPTER, "unblock_auto_shell.ps1"), "-Settings", settings], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    out = p.stdout.decode("utf-8", "replace")
    s = load(settings)
    kept = [h for g in s.get("hooks", {}).get("PreToolUse", []) for h in g.get("hooks", [])]
    check("the emergency exit removes only Terminal-Only's hooks, keeps the other hook and settings, and writes a backup", before == 2 and ours(s) == 0 and any(h.get("command") == "other-tool" for h in kept) and s.get("model") == "x" and os.path.exists(settings + ".llm_harness-unblock-backup"), (out, s))
    check("it says how to restart and reinstall", "Restart Claude Code" in out and "setup.cmd" in out, out)
    subprocess.run(install, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    s = load(settings)
    kept = [h for g in s.get("hooks", {}).get("PreToolUse", []) for h in g.get("hooks", [])]
    check("running the installer again puts the hooks back once, and the other hook still survives", ours(s) == 2 and any(h.get("command") == "other-tool" for h in kept), s)
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
