// /llm_harness/adapters/opencode/terminal-only/index.ts
// Terminal-Only (llm_harness) adapter for OpenCode V2 (written for v2.4.1). On every admitted prompt it starts a harness prompt turn and appends the briefing to the prompt; it fails closed (a throw keeps the prompt from being admitted). It also sets the agent-mode environment for the AI's shell commands.
import { Plugin } from "@opencode/plugin";
import { spawn } from "node:child_process";
import * as os from "node:os";
import * as path from "node:path";

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

export default Plugin.define({
  id: "terminal-only",
  async setup(ctx: any) {
    await ctx.session.hook("prompt", async (event: any) => {
      const session: any = await ctx.session.get({ sessionID: event.sessionID });
      const loc: any = session?.location ?? {};
      const sub = loc.subpath ?? session?.subpath;
      const cwd = sub ? path.join(loc.directory, sub) : loc.directory;
      if (!cwd) throw new Error("llm_harness: the session has no project folder, so the prompt is held back");
      const briefing = await runTurn(cwd, event.sessionID, event.messageID);
      event.prompt.text += "\n\n--- Terminal-Only briefing ---\n" + briefing +
        "\nWork only through the harness: every terminal action is ONE script piped into it, exactly as  @'<script>'@ | " + HARNESS_CMD +
        "  (the only command allowed: no other command and no $OutputEncoding prefix). Its first output in this prompt prints the full standing rules; follow them, and answer the user in plain prose.";
    });
    await ctx.shell.hook("create.before", (event: any) => {
      event.env.LLM_HARNESS_AGENT = "1";
      event.env.LLM_HARNESS_HOST = "opencode";
      event.env.LLM_HARNESS_HOST_SESSION = event.env.OPENCODE_SESSION_ID ?? "";
    });
  },
});
