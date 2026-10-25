import type { PageProps } from "../types";
import { navigate } from "../router";
import { prUrl } from "../data";
import { pct, points } from "../format";
import StatusTag from "../components/StatusTag";
import Tiles from "../components/Tiles";
import TrendChart from "../components/TrendChart";


export default function Overview({ snapshot, datasetVersion }: PageProps) {
  const runs = snapshot.runs.filter((r) => r.dataset_version === datasetVersion);
  const latest = runs[runs.length - 1];
  if (!latest) return <p className="muted">No runs yet for dataset {datasetVersion}.</p>;

  const { drift, comparison } = latest;
  const driftSub = drift?.moving_average == null ? `needs ${snapshot.settings.drift_window} runs` : `${drift.drifting ? "below" : "above"} ${pct(drift.threshold)} floor`;
  // Latest PR run per PR number (runs are oldest first).
  const prs = [...new Map(snapshot.pr_runs.map((r) => [r.pr_number, r])).values()];

  return (
    <>
      <Tiles
        tiles={[
          { label: "Pass rate", value: pct(latest.pass_rate), sub: comparison.baseline_run_id ? `${points(comparison.pass_rate_delta)} vs ${comparison.baseline_run_id}` : "first run" },
          { label: "Status", value: <StatusTag status={comparison.status} /> },
          { label: `${snapshot.settings.drift_window}-run drift`, value: drift?.moving_average == null ? "—" : pct(drift.moving_average), sub: driftSub },
          { label: "Tokens / latency", value: latest.total_tokens.toLocaleString(), sub: `${(latest.mean_latency_ms / 1000).toFixed(1)} s avg` },
        ]}
      />
      <TrendChart runs={runs} floor={snapshot.settings.drift_threshold} />
      <h3>Recent runs</h3>
      <table>
        <thead>
          <tr><th>Run</th><th>Prompt</th><th>Pass</th><th>Δ</th><th>Status</th></tr>
        </thead>
        <tbody>
          {runs.slice(-10).reverse().map((r) => (
            <tr key={r.run_id} className="link" onClick={() => navigate(`#/runs/${r.run_id}`)}>
              <td>{r.run_id}</td>
              <td>{r.prompt_version}</td>
              <td>{pct(r.pass_rate)}</td>
              <td>{points(r.comparison.pass_rate_delta)}</td>
              <td><StatusTag status={r.comparison.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      {prs.length > 0 && (
        <>
          <h3>Pull requests</h3>
          <table>
            <thead>
              <tr><th>PR</th><th>Prompt</th><th>Pass</th><th>Δ</th><th>Result</th></tr>
            </thead>
            <tbody>
              {prs.map((r) => (
                <tr key={r.pr_number} className="link" onClick={() => navigate(`#/pr/${r.run_id}`)}>
                  <td>#{r.pr_number}</td>
                  <td>{r.prompt_version}</td>
                  <td>{pct(r.pass_rate)}</td>
                  <td>{points(r.comparison.pass_rate_delta)}</td>
                  <td>
                    <StatusTag status={r.comparison.status} /> {r.comparison.status === "critical" ? "blocked" : "passed"}
                    {prUrl(r.pr_number) && (
                      <> · <a href={prUrl(r.pr_number)!} onClick={(e) => e.stopPropagation()}>GitHub</a></>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </>
  );
}
