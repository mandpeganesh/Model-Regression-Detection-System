import type { PageProps } from "../types";
import { pct, points } from "../format";
import { navigate } from "../router";
import StatusTag from "../components/StatusTag";


export default function Runs({ snapshot, datasetVersion }: PageProps) {
  const runs = snapshot.runs.filter((r) => r.dataset_version === datasetVersion).reverse();
  if (!runs.length) return <p className="muted">No runs yet for dataset {datasetVersion}.</p>;
  return (
    <>
      <h3>Runs · dataset {datasetVersion}</h3>
      <table>
        <thead>
          <tr><th>Run</th><th>Created</th><th>Prompt</th><th>Model</th><th>Pass</th><th>Δ</th><th>Status</th></tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.run_id} className="link" onClick={() => navigate(`#/runs/${r.run_id}`)}>
              <td>{r.run_id}</td>
              <td>{r.created_at}</td>
              <td>{r.prompt_version}</td>
              <td>{r.model}</td>
              <td>{pct(r.pass_rate)}</td>
              <td>{points(r.comparison.pass_rate_delta)}</td>
              <td><StatusTag status={r.comparison.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
