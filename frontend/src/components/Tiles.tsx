import type { ReactNode } from "react";

export interface TileData {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
}

export default function Tiles({ tiles }: { tiles: TileData[] }) {
  return (
    <div className="tiles">
      {tiles.map((t) => (
        <div className="tile" key={t.label}>
          <span>{t.label}</span>
          <b>{t.value}</b>
          <span>{t.sub ?? " "}</span>
        </div>
      ))}
    </div>
  );
}
