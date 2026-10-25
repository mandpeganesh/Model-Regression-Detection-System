import { useCallback, useEffect, useState } from "react";
import { DEMO, loadSnapshot } from "./data";
import { useRoute } from "./router";
import type { Snapshot } from "./types";
import Overview from "./pages/Overview";
import Runs from "./pages/Runs";
import RunDetail from "./pages/RunDetail";
import Golden from "./pages/Golden";
import Prompts from "./pages/Prompts";
import RunEvalDialog from "./components/RunEvalDialog";

const NAV = [
  ["#/", "/", "Overview"],
  ["#/runs", "/runs", "Runs"],
  ["#/golden", "/golden", "Golden cases"],
  ["#/prompts", "/prompts", "Prompts"],
] as const;

export default function App() {
  const route = useRoute();
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [datasetVersion, setDatasetVersion] = useState<string | null>(null);
  const [dialog, setDialog] = useState(false);

  const reload = useCallback(async () => {
    try {
      setSnapshot(await loadSnapshot());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);
  useEffect(() => { void reload(); }, [reload]);

  const version = datasetVersion ?? snapshot?.dataset.version ?? "";
  const versions = snapshot
    ? [...new Set([snapshot.dataset.version, ...snapshot.runs.map((r) => r.dataset_version)])]
    : [];

  let page = <p className="muted">Loading…</p>;
  if (error) page = <p className="error">Could not load data: {error}</p>;
  else if (snapshot) {
    const props = { snapshot, datasetVersion: version, reload };
    const [id = ""] = route.params;
    if (route.path === "/runs" && id) page = <RunDetail {...props} runId={id} isPr={false} />;
    else if (route.path === "/pr" && id) page = <RunDetail {...props} runId={id} isPr />;
    else if (route.path === "/runs") page = <Runs {...props} />;
    else if (route.path === "/golden") page = <Golden {...props} />;
    else if (route.path === "/prompts") page = <Prompts {...props} />;
    else page = <Overview {...props} />;
  }

  return (
    <div className="app">
      <header className="bar">
        regress
        {DEMO && <span className="badge">Read-only demo · data from CI</span>}
        <span className="sp" />
        {versions.length > 1 && (
          <label className="ver">
            dataset{" "}
            <select value={version} onChange={(e) => setDatasetVersion(e.target.value)}>
              {versions.map((v) => <option key={v}>{v}</option>)}
            </select>
          </label>
        )}
        {!DEMO && snapshot && <button className="btn" onClick={() => setDialog(true)}>▶ Run eval</button>}
      </header>
      <div className="body">
        <nav className="side">
          {NAV.map(([hash, path, label]) => (
            <a key={hash} href={hash} className={route.path === path || (path === "/runs" && route.path === "/pr") ? "on" : ""}>{label}</a>
          ))}
        </nav>
        <main className="main">{page}</main>
      </div>
      {dialog && snapshot && <RunEvalDialog snapshot={snapshot} onClose={() => setDialog(false)} reload={reload} />}
    </div>
  );
}
