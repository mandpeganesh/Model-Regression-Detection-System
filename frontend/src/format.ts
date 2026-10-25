export const pct = (v: number) => `${Math.round(v * 100)}%`;
export const points = (d: number | null) => (d === null ? "—" : `${d >= 0 ? "+" : ""}${(d * 100).toFixed(1)} pts`);
