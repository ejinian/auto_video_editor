import fs from "node:fs";
import os from "node:os";
import path from "node:path";

/** The chat's Agent SDK signs in with ANTHROPIC_API_KEY when web/.env.local has one,
 *  else with the Claude Code login on this Mac (`claude` → `/login` once; the CLI keeps
 *  the token in the keychain and notes the account in ~/.claude.json). False = the chat
 *  cannot run; the buttons still work. Kept apart from agent.ts so the pages' health
 *  check does not load the SDK. */
export function hasChatAuth(): boolean {
  if (process.env.ANTHROPIC_API_KEY) return true;
  try {
    const j = JSON.parse(fs.readFileSync(path.join(os.homedir(), ".claude.json"), "utf8")) as { oauthAccount?: unknown };
    return !!j.oauthAccount;
  } catch {
    return false;
  }
}
