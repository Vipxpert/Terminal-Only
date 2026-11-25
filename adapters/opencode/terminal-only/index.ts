// /llm_harness/adapters/opencode/terminal-only/index.ts
// Terminal-Only (llm_harness) adapter for OpenCode V2 (written for v2.4.1). On every admitted prompt it starts a harness prompt turn and appends the briefing to the prompt; it fails closed (a throw keeps the prompt from being admitted). It also sets the agent-mode environment for the AI's shell commands.
import { Plugin } from "@opencode/plugin";
import { spawn } from "node:child_process";
import * as os from "node:os";
import * as path from "node:path";
import * as fs from "node:fs";

const PYTHON = process.env.LLM_HARNESS_PYTHON || "python";
const HARNESS = process.env.LLM_HARNESS_PATH || path.join(os.homedir(), ".llm_harness", "harness.py");
// Comment (constraint): the shell allow rule matches the exact command string, written with forward slashes, so the command the AI is told to use is built the same way
const HARNESS_CMD = PYTHON + " '" + HARNESS.replace(/\\/g, "/") + "'";

function runTurn(cwd: string, sessionID: string, messageID: string): Promise<string> {
  return new Promise((resolve, reject) => {
    // Comment (decision): a direct child process with an argument list and no shell; the turn is keyed by OpenCode's messageID, so a duplicate submission does not start a second turn
    const child = spawn(PYTHON, [HARNESS, "--workspace", cwd, "--new-turn", messageID], {
      cwd,
      env: { ...process.env, LLM_HARNESS_AGENT: "1", LLM_HARNESS_HOST: "opencode", LLM_HARNESS_HOST_SESSION: sessionID },
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
    let out = "";
    let err = "";
    const timer = setTimeout(() => { child.kill(); reject(new Error("llm_harness: the prompt turn timed out")); }, 25000);
    child.stdout.on("data", (d) => { out += d; });
    child.stderr.on("data", (d) => { err += d; });
    child.on("error", (e) => { clearTimeout(timer); reject(e); });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (code === 0 && out.includes("AGENT TURN")) resolve(out.trim());
      else reject(new Error("llm_harness: the prompt turn could not start (exit " + code + "): " + (err || out).slice(-500)));
    });
  });
}

const HOME = path.resolve(os.homedir()).toLowerCase();

// Comment (decision): the same rule as the Claude Code adapter: the nearest folder with .llm_harness/ (not the install folder, which holds harness.py) or .git/llm_harness/, never the home folder
function harnessRoot(start: string): string | null {
  let cur = path.resolve(start);
  while (true) {
    const mem = path.join(cur, ".llm_harness");
    const isMem = fs.existsSync(mem) && fs.statSync(mem).isDirectory() && !fs.existsSync(path.join(mem, "harness.py"));
    const isState = fs.existsSync(path.join(cur, ".git", "llm_harness"));
    if ((isMem || isState) && cur.toLowerCase() !== HOME) return cur;
    const parent = path.dirname(cur);
    if (parent === cur) return null;
    cur = parent;
  }
}

// Comment (decision): when the session's folder cannot be read, nothing is blocked, so a lookup failure never locks the user out of unrelated projects
async function sessionFolder(ctx: any, sessionID: string): Promise<string | null> {
  try {
    const session: any = await ctx.session.get({ sessionID });
    const loc: any = session?.location ?? {};
    const sub = loc.subpath ?? session?.subpath;
    if (!loc.directory) return null;
    return sub ? path.join(loc.directory, sub) : loc.directory;
  } catch (e) {
    return null;
  }
}

function harnessCallProblem(cmd: string): string {
  const m = /^\s*@'\r?\n([\s\S]*?)\r?\n'@[ \t]*\|[ \t]*(\S+)[ \t]+'([^'\r\n]+)'\s*$/.exec(cmd);
  if (!m) return "the command is not one here-string piped into the harness";
  const body = m[1], exe = m[2], target = m[3];
  // Comment (invariant): a line starting with '@ ends a PowerShell here-string early, and whatever follows would run as a second command
  if (body.split("\n").some((l) => l.replace(/\r$/, "").startsWith("'@"))) return "a line inside the script starts with '@, which would end the here-string early";
  if (["python", "python3"].indexOf(exe.toLowerCase()) < 0) return "Python must be named python (found on the PATH), not given by path";
  if (path.resolve(target).toLowerCase() !== path.resolve(HARNESS).toLowerCase()) return "that is not the installed harness";
  return "";
}

export default Plugin.define({
  id: "terminal-only",
  async setup(ctx: any) {
    await ctx.session.hook("prompt", async (event: any) => {
      const folder = await sessionFolder(ctx, event.sessionID);
      const root = folder ? harnessRoot(folder) : null;
      // Comment (decision): not a Terminal-Only project, so OpenCode works as usual there
      if (!root) return;
      const briefing = await runTurn(root, event.sessionID, event.messageID);
      event.prompt.text += "\n\nMODE: auto-shell (this folder is a Terminal-Only project: " + root + ")";
      event.prompt.text += "\n\n--- Terminal-Only briefing ---\n" + briefing +
        "\nWork only through the harness: every terminal action is ONE script piped into it, exactly as  @'<script>'@ | " + HARNESS_CMD +
        "  (the only command allowed: no other command and no $OutputEncoding prefix). Its first output in this prompt prints the full standing rules; follow them, and answer the user in plain prose.";
    });
    await ctx.shell.hook("create.before", (event: any) => {
      event.env.LLM_HARNESS_AGENT = "1";
      event.env.LLM_HARNESS_HOST = "opencode";
      event.env.LLM_HARNESS_HOST_SESSION = event.env.OPENCODE_SESSION_ID ?? "";
    });
    await ctx.tool.hook("execute.before", async (event: any) => {
      const folder = await sessionFolder(ctx, event.sessionID);
      const root = folder ? harnessRoot(folder) : null;
      if (!root) return;
      const input: any = event.input;
      // Comment (constraint): in OpenCode V2 the shell tool is exactly "shell" and its command is input.command; the event's input is untyped, so it must be an object holding a string command, and anything else is refused; subagents and child sessions run these same hooks
      let why = "";
      if (event.tool !== "shell") why = "the " + String(event.tool) + " tool is not used in a Terminal-Only project";
      else if (!input || typeof input !== "object" || typeof input.command !== "string") why = "the shell call has no command string";
      else why = harnessCallProblem(input.command);
      if (why) throw new Error("Terminal-Only auto-shell (" + root + "): " + why + ". Send the terminal work as ONE harness script, exactly as  @'<script>'@ | " + HARNESS_CMD);
    });
  },
});
