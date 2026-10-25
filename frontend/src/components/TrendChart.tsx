import { pct } from "../format";
import type { RunView } from "../types";

const W = 600, H = 160, PAD = 28;

// Pass rate over the last 20 runs; dashed line is the drift floor.
export default function TrendChart({ runs, floor }: { runs: RunView[]; floor: number }) {
  const pts = runs.slice(-20);
  const rates = [...pts.map((r) => r.pass_rate), floor];
  const lo = Math.max(0, Math.min(...rates) - 0.05);
  const hi = Math.min(1, Math.max(...rates) + 0.05);
  const y = (v: number) => PAD + (H - 2 * PAD) * (1 - (v - lo) / (hi - lo || 1));
  const x = (i: number) => PAD + (pts.length > 1 ? ((W - 2 * PAD) * i) / (pts.length - 1) : (W - 2 * PAD) / 2);
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`}>
      <line x1={0} x2={W} y1={y(floor)} y2={y(floor)} stroke="#fca5a5" strokeDasharray="4 3" />
      <polyline fill="none" stroke="#2563eb" strokeWidth={2} points={pts.map((r, i) => `${x(i)},${y(r.pass_rate)}`).join(" ")} />
      {pts.map((r, i) => (
        <g key={r.run_id}>
          <circle cx={x(i)} cy={y(r.pass_rate)} r={3} fill="#2563eb">
            <title>{`${r.run_id} · ${pct(r.pass_rate)}`}</title>
          </circle>
          <text x={x(i)} y={y(r.pass_rate) - 8} fontSize={9} textAnchor="middle" fill="#374151">{r.prompt_version}</text>
        </g>
      ))}
      <text x={4} y={H - 6} fontSize={9} fill="#6b7280">
        pass rate over runs · dashed = drift floor {pct(floor)}
      </text>
    </svg>
  );
}
