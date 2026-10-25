import { useState } from "react";
import { DEMO, api } from "../data";
import type { GoldenCase, PageProps } from "../types";

const CATS = ["billing", "technical", "account", "general"];
const DIFFS = ["easy", "medium", "hard"] as const;

// Patch bump for x.y.z; anything else is left for the owner to type.
const bump = (v: string) => {
  const m = /^(\d+)\.(\d+)\.(\d+)$/.exec(v);
  return m ? `${m[1]}.${m[2]}.${+m[3] + 1}` : v;
};

const blank: GoldenCase = {
  id: "", input: "", expected_difficulty: "medium", notes: "",
  expected: { category: "billing", summary: "" },
};

export default function Golden({ snapshot, datasetVersion, reload }: PageProps) {
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const [diff, setDiff] = useState("");
  const [form, setForm] = useState<GoldenCase | null>(null);
  const [adding, setAdding] = useState(false);
  const [newVersion, setNewVersion] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const { cases } = snapshot.dataset;
  const run = snapshot.runs
    .filter((r) => r.dataset_version === datasetVersion)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  const last = new Map(run?.cases.map((c) => [c.case_id, c.passed]));

  const needle = q.toLowerCase();
  const rows = cases.filter((c) =>
    (!cat || c.expected.category === cat) &&
    (!diff || c.expected_difficulty === diff) &&
    (!needle || [c.id, c.input, c.expected.summary].some((s) => s.toLowerCase().includes(needle))));

  const open = (c: GoldenCase | null) => {
    setAdding(c === null);
    setForm(c ?? blank);
    setNewVersion(bump(snapshot.dataset.version));
    setErr(null);
  };
  const set = (patch: Partial<GoldenCase>) => setForm((f) => f && { ...f, ...patch });

  const save = async () => {
    if (!form) return;
    setBusy(true);
    setErr(null);
    try {
      await (adding ? api.addCase : api.editCase)(form, newVersion);
      setForm(null);
      await reload();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const perCat = CATS.map((c) => `${cases.filter((x) => x.expected.category === c).length} ${c}`).join(" · ");

  return (
    <>
      <div className="row">
        <b>Dataset {snapshot.dataset.version}</b>
        <span className="muted">{cases.length} cases · {perCat}</span>
        <span className="sp" />
        <input placeholder="search id, email, summary" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={cat} onChange={(e) => setCat(e.target.value)}>
          <option value="">all categories</option>
          {CATS.map((c) => <option key={c}>{c}</option>)}
        </select>
        <select value={diff} onChange={(e) => setDiff(e.target.value)}>
          <option value="">all difficulties</option>
          {DIFFS.map((d) => <option key={d}>{d}</option>)}
        </select>
        {!DEMO && <button className="btn" onClick={() => open(null)}>+ Add case</button>}
      </div>
      <div className="row top">
        <table style={{ flex: 1.2 }}>
          <thead><tr><th>ID</th><th>Category</th><th>Diff.</th><th>Last result{run ? ` (${run.run_id.slice(0, 8)})` : ""}</th></tr></thead>
          <tbody>
            {rows.map((c) => {
              const p = last.get(c.id);
              return (
                <tr key={c.id} className={DEMO ? "" : "link"} onClick={DEMO ? undefined : () => open(c)}>
                  <td><b>{c.id}</b></td>
                  <td>{c.expected.category}</td>
                  <td>{c.expected_difficulty}</td>
                  <td>{p === undefined ? <span className="muted">no run</span> : <span className={`tag ${p ? "pass" : "critical"}`}>{p ? "pass" : "fail"}</span>}</td>
                </tr>
              );
            })}
            {rows.length === 0 && <tr><td colSpan={4} className="muted">No matching cases.</td></tr>}
          </tbody>
        </table>
        {!DEMO && form && (
          <div className="panel">
            <div className="muted">{adding ? "ADD CASE" : "EDIT CASE"}</div>
            <div className="row">
              <input value={form.id} disabled={!adding} placeholder="ID" style={{ width: 90 }}
                onChange={(e) => set({ id: e.target.value })} />
              {!adding && <span title="IDs can't be renamed">🔒</span>}
              <select value={form.expected.category} onChange={(e) => set({ expected: { ...form.expected, category: e.target.value } })}>
                {CATS.map((c) => <option key={c}>{c}</option>)}
              </select>
              <select value={form.expected_difficulty} onChange={(e) => set({ expected_difficulty: e.target.value as GoldenCase["expected_difficulty"] })}>
                {DIFFS.map((d) => <option key={d}>{d}</option>)}
              </select>
            </div>
            <textarea rows={6} placeholder="Email text" value={form.input} onChange={(e) => set({ input: e.target.value })} />
            <textarea rows={2} placeholder="Expected summary (one sentence)" value={form.expected.summary}
              onChange={(e) => set({ expected: { ...form.expected, summary: e.target.value } })} />
            <textarea rows={2} placeholder="Why this case matters (notes, required)" value={form.notes} onChange={(e) => set({ notes: e.target.value })} />
            <div className="warnbox">
              ⚠ Saving changes the eval bar. New dataset version:{" "}
              <input value={newVersion} style={{ width: 90 }} onChange={(e) => setNewVersion(e.target.value)} />
              <div className="muted">The next run starts a fresh baseline. IDs can't be renamed or reused. There's no AI fill; you write every label.</div>
            </div>
            {err && <p className="error">{err}</p>}
            <div className="row">
              <button className="btn" disabled={busy || !form.id.trim() || !form.input.trim() || !form.expected.summary.trim() || !form.notes.trim() || !newVersion.trim()} onClick={save}>
                Save as {newVersion}
              </button>
              <button className="btn ghost" onClick={() => setForm(null)}>Cancel</button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
