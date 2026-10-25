import { useState } from "react";
import { api, DEMO } from "../data";
import { pct } from "../format";
import type { PageProps, Prompt } from "../types";

type Op = { t: " " | "+" | "-"; s: string };

// Text form of a prompt, one field per line block, for diffing.
function text(p: Prompt): string[] {
  const lines = [`version: ${p.version}`, `model: ${p.model}`, "system_prompt:", ...p.system_prompt.split("\n").map((l) => "  " + l)];
  for (const ex of p.few_shot_examples) {
    lines.push("- email: " + ex.email.replace(/\n/g, " "), `  category: ${ex.output.category}`, `  summary: ${ex.output.summary}`);
  }
  return lines;
}

// Line diff via longest-common-subsequence table.
function diff(a: string[], b: string[]): Op[] {
  const n = a.length, m = b.length;
  const l = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--) l[i][j] = a[i] === b[j] ? l[i + 1][j + 1] + 1 : Math.max(l[i + 1][j], l[i][j + 1]);
  const out: Op[] = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) { out.push({ t: " ", s: a[i] }); i++; j++; }
    else if (l[i + 1][j] >= l[i][j + 1]) out.push({ t: "-", s: a[i++] });
    else out.push({ t: "+", s: b[j++] });
  }
  while (i < n) out.push({ t: "-", s: a[i++] });
  while (j < m) out.push({ t: "+", s: b[j++] });
  return out;
}

function nextVersion(prompts: Prompt[]): string {
  const max = Math.max(0, ...prompts.map((p) => Number(/^v(\d+)$/.exec(p.version)?.[1] ?? 0)));
  return `v${max + 1}`;
}

interface Draft { version: string; model: string; system_prompt: string; shots: { email: string; category: string; summary: string }[] }

function Editor({ base, prompts, onDone, onCancel }: { base: Prompt; prompts: Prompt[]; onDone: () => void; onCancel: () => void }) {
  const [d, setD] = useState<Draft>({
    version: nextVersion(prompts),
    model: base.model,
    system_prompt: base.system_prompt,
    shots: base.few_shot_examples.map((e) => ({ email: e.email, ...e.output })),
  });
  const [error, setError] = useState<string | null>(null);
  const setShot = (i: number, k: string, v: string) => setD({ ...d, shots: d.shots.map((s, x) => (x === i ? { ...s, [k]: v } : s)) });

  async function submit() {
    setError(null);
    try {
      await api.createPrompt({
        version: d.version.trim(),
        model: d.model,
        system_prompt: d.system_prompt,
        few_shot_examples: d.shots.map((s) => ({ email: s.email, output: { category: s.category, summary: s.summary } })),
      });
      onDone();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="editor">
      <h3>New version from {base.version}</h3>
      <label>Version <input value={d.version} onChange={(e) => setD({ ...d, version: e.target.value })} /></label>
      <label>Model <input value={d.model} onChange={(e) => setD({ ...d, model: e.target.value })} /></label>
      <label>System prompt <textarea rows={8} value={d.system_prompt} onChange={(e) => setD({ ...d, system_prompt: e.target.value })} /></label>
      {d.shots.map((s, i) => (
        <fieldset key={i}>
          <legend>Few-shot {i + 1} <button className="btn ghost" onClick={() => setD({ ...d, shots: d.shots.filter((_, x) => x !== i) })}>remove</button></legend>
          <textarea rows={3} placeholder="email" value={s.email} onChange={(e) => setShot(i, "email", e.target.value)} />
          <input placeholder="category" value={s.category} onChange={(e) => setShot(i, "category", e.target.value)} />
          <input placeholder="summary" value={s.summary} onChange={(e) => setShot(i, "summary", e.target.value)} />
        </fieldset>
      ))}
      <div className="row">
        <button className="btn ghost" onClick={() => setD({ ...d, shots: [...d.shots, { email: "", category: "", summary: "" }] })}>+ few-shot</button>
        <span className="sp" />
        <button className="btn ghost" onClick={onCancel}>Cancel</button>
        <button className="btn" onClick={submit}>Create {d.version}</button>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

export default function Prompts({ snapshot, reload }: PageProps) {
  const prompts = [...snapshot.prompts].sort((a, b) => b.created_at.localeCompare(a.created_at));
  const [sel, setSel] = useState<[string, string]>([prompts[1]?.version ?? prompts[0]?.version ?? "", prompts[0]?.version ?? ""]);
  const [editing, setEditing] = useState(false);
  const find = (v: string) => prompts.find((p) => p.version === v);
  const [from, to] = [find(sel[0]), find(sel[1])];
  const latestRate = new Map<string, number>(); // snapshot.runs is oldest first, so later runs overwrite
  for (const r of snapshot.runs) latestRate.set(r.prompt_version, r.pass_rate);
  const rate = (v: string) => (latestRate.has(v) ? pct(latestRate.get(v)!) : "—");
  const newest = prompts[0];

  return (
    <>
      <div className="row">
        <h2>Prompts</h2>
        <span className="sp" />
        {!DEMO && newest && !editing && <button className="btn" onClick={() => setEditing(true)}>+ New version from {newest.version}</button>}
      </div>
      {editing && newest && (
        <Editor base={newest} prompts={prompts} onCancel={() => setEditing(false)} onDone={() => { setEditing(false); void reload(); }} />
      )}
      <table>
        <thead><tr><th>Version</th><th>Created</th><th>Model</th><th>Latest pass rate</th></tr></thead>
        <tbody>
          {prompts.map((p) => (
            <tr key={p.version}>
              <td>{p.version}</td><td>{p.created_at.slice(0, 10)}</td><td>{p.model}</td><td>{rate(p.version)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {prompts.length > 1 && from && to && (
        <>
          <h3>
            Diff{" "}
            <select value={sel[0]} onChange={(e) => setSel([e.target.value, sel[1]])}>{prompts.map((p) => <option key={p.version}>{p.version}</option>)}</select>
            {" → "}
            <select value={sel[1]} onChange={(e) => setSel([sel[0], e.target.value])}>{prompts.map((p) => <option key={p.version}>{p.version}</option>)}</select>
          </h3>
          <pre className="diff">
            {diff(text(from), text(to)).map((o, i) => <div key={i} className={`d${o.t.trim() || "0"}`}>{o.t} {o.s}</div>)}
          </pre>
        </>
      )}
    </>
  );
}
