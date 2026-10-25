import { Fragment, useState } from "react";
import type { CaseResult, PageProps } from "../types";
import StatusTag from "../components/StatusTag";
import Tiles from "../components/Tiles";

const pct = (v: number) => `${Math.round(v * 100)}%`;
const points = (d: number | null) => (d === null ? "—" : `${d >= 0 ? "+" : ""}${(d * 100).toFixed(1)} pts`);
const cell = (c?: CaseResult) =>
  c ? `${c.actual_category ?? "error"} · ${c.relevance}/5 ${c.passed ? "✓" : "✗"}` : "—";
type Filter = "Regressions" | "Improvements" | "All failing" | "All";
const FILTERS: Filter[] = ["Regressions", "Improvements", "All failing", "All"];

export default function RunDetail({ snapshot, runId, isPr }: PageProps & { runId: string; isPr: boolean }) {
  const run = (isPr ? snapshot.pr_runs : snapshot.runs).find((r) => r.run_id === runId);
  const [filter, setFilter] = useState<Filter | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  if (!run) return <p className="error">Run {runId} not found.</p>;

  const c = run.comparison;
  const base = snapshot.runs.find((r) => r.run_id === c.baseline_run_id);
  const baseCases = new Map(base?.cases.map((x) => [x.case_id, x]));
  const golden = run.dataset_version === snapshot.dataset.version
    ? new Map(snapshot.dataset.cases.map((g) => [g.id, g]))
    : null;
  const active = filter ?? (c.regressions.length ? "Regressions" : "All failing");
  const show = (x: CaseResult) =>
    active === "Regressions" ? c.regressions.includes(x.case_id)
    : active === "Improvements" ? c.improvements.includes(x.case_id)
    : active === "All failing" ? !x.passed
    : true;
  const pr = "pr_number" in run ? run.pr_number : null;
  const repo = import.meta.env.VITE_REPO;

  return (
    <>
      <h2>{run.run_id} <StatusTag status={c.status} /></h2>
      <p className="muted">
        {isPr && pr !== null && (
          <>PR #{pr} · not merged into history{repo && <> (<a href={`https://github.com/${repo}/pull/${pr}`}>view on GitHub</a>)</>} · </>
        )}
        prompt {run.prompt_version} · {run.model} · dataset {run.dataset_version} · {run.created_at} ·{" "}
        {base ? `baseline ${base.run_id} (prompt ${base.prompt_version})` : c.baseline_run_id ? `baseline ${c.baseline_run_id}` : "first run for this dataset version"}
      </p>
      <Tiles
        tiles={[
          { label: "Pass rate", value: c.baseline_pass_rate === null ? pct(run.pass_rate) : `${pct(c.baseline_pass_rate)} → ${pct(run.pass_rate)}`, sub: points(c.pass_rate_delta) },
          { label: "Regressions", value: c.regressions.length },
          { label: "Improvements", value: c.improvements.length },
          { label: "Tokens / latency", value: run.total_tokens.toLocaleString(), sub: `${(run.mean_latency_ms / 1000).toFixed(1)} s avg` },
        ]}
      />
      <h3>Accuracy by category <span className="muted">(reported, not gated)</span></h3>
      {Object.entries(run.category_accuracy).map(([cat, acc]) => (
        <div className="catbar" key={cat}>
          <span>{cat}</span>
          <div className="track"><div className="fill" style={{ width: pct(acc) }} /></div>
          <span>{pct(acc)} ({points(c.category_deltas[cat] ?? null)})</span>
        </div>
      ))}
      <div className="chips">
        {FILTERS.map((f) => (
          <button key={f} className={`chip${f === active ? " on" : ""}`} onClick={() => setFilter(f)}>{f}</button>
        ))}
      </div>
      {!golden && <p className="muted">Case text is from a different dataset version and isn't shown.</p>}
      <table>
        <thead>
          <tr><th>Case</th><th>Difficulty</th><th>Expected</th><th>Before</th><th>After</th></tr>
        </thead>
        <tbody>
          {run.cases.filter(show).map((x) => {
            const g = golden?.get(x.case_id);
            const b = baseCases.get(x.case_id);
            return (
              <Fragment key={x.case_id}>
                <tr className="link" onClick={() => setOpen(open === x.case_id ? null : x.case_id)}>
                  <td>{x.case_id}</td>
                  <td>{g?.expected_difficulty ?? "—"}</td>
                  <td>{x.expected_category}</td>
                  <td>{cell(b)}</td>
                  <td>{cell(x)}</td>
                </tr>
                {open === x.case_id && (
                  <tr>
                    <td colSpan={5} className="detail">
                      {g && <><p><b>Email</b><br />{g.input}</p><p><b>Expected summary</b><br />{g.expected.summary}</p></>}
                      <p><b>Before</b><br />{b?.actual_summary ?? "—"}</p>
                      <p><b>After</b><br />{x.actual_summary ?? "—"}</p>
                      {x.error && <p className="error"><b>Error</b><br />{x.error}</p>}
                      {g && <p className="muted"><b>Notes</b><br />{g.notes}</p>}
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </>
  );
}
