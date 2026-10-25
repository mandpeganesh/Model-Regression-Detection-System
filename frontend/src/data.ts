import type { GoldenCase, Snapshot } from "./types";

export const DEMO = import.meta.env.VITE_DEMO === "1";

export interface RunState {
  state: "idle" | "running" | "done" | "error";
  done: number;
  total: number;
  run_id: string | null;
  error: string | null;
}

export async function loadSnapshot(): Promise<Snapshot> {
  const res = await fetch(DEMO ? "./data/snapshot.json" : "/api/snapshot");
  if (!res.ok) throw new Error(`snapshot: HTTP ${res.status}`);
  return res.json();
}

async function call<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `HTTP ${res.status}`);
  return data as T;
}

// Owner mode only; never called when DEMO.
export const api = {
  startRun: (prompt_version: string) =>
    call<{ run_id: string | null }>("POST", "/api/runs", { prompt_version }),
  currentRun: () => call<RunState>("GET", "/api/runs/current"),
  addCase: (c: GoldenCase, new_version: string) =>
    call<{ version: string }>("POST", "/api/golden/cases", { case: c, new_version }),
  editCase: (c: GoldenCase, new_version: string) =>
    call<{ version: string }>("PUT", `/api/golden/cases/${encodeURIComponent(c.id)}`, { case: c, new_version }),
  createPrompt: (p: { version: string; model: string; system_prompt: string; few_shot_examples: unknown[] }) =>
    call<{ path: string }>("POST", "/api/prompts", p),
};

export function prUrl(n: number): string | null {
  const repo = import.meta.env.VITE_REPO;
  return repo ? `https://github.com/${repo}/pull/${n}` : null;
}
