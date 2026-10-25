import { useEffect, useState } from "react";
import { api, type RunState } from "../data";
import { navigate } from "../router";
import type { Snapshot } from "../types";

export default function RunEvalDialog({ snapshot, onClose, reload }: { snapshot: Snapshot; onClose: () => void; reload: () => Promise<void> }) {
  const [version, setVersion] = useState(snapshot.prompts[0]?.version ?? "");
  const [started, setStarted] = useState(false);
  const [state, setState] = useState<RunState | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setError(null);
    try {
      await api.startRun(version);
      setStarted(true);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    if (!started) return;
    const t = setInterval(async () => {
      try {
        const s = await api.currentRun();
        setState(s);
        if (s.state === "done") {
          clearInterval(t);
          await reload();
          onClose();
          if (s.run_id) navigate(`#/runs/${encodeURIComponent(s.run_id)}`);
        } else if (s.state === "error") {
          clearInterval(t);
          setError(s.error ?? "run failed");
        }
      } catch (e) {
        clearInterval(t);
        setError((e as Error).message);
      }
    }, 1000);
    return () => clearInterval(t);
  }, [started]);

  const running = started && !error;
  return (
    <div className="overlay">
      <div className="dialog">
        <h3>Run eval</h3>
        <label>Prompt version
          <select value={version} disabled={started} onChange={(e) => setVersion(e.target.value)}>
            {snapshot.prompts.map((p) => <option key={p.version}>{p.version}</option>)}
          </select>
        </label>
        <label>Dataset <input readOnly value={`${snapshot.dataset.version} (${snapshot.dataset.cases.length} cases)`} /></label>
        {running && (
          <>
            <progress max={state?.total || 1} value={state?.done ?? 0} />
            <span className="muted">{state ? `${state.done} / ${state.total}` : "starting…"}</span>
          </>
        )}
        {error && <p className="error">{error}</p>}
        <div className="row">
          <button className="btn ghost" onClick={onClose}>{running ? "Hide" : "Cancel"}</button>
          {!started && <button className="btn" disabled={!version} onClick={start}>Start run</button>}
        </div>
      </div>
    </div>
  );
}
