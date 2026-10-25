import type { Status } from "../types";

export default function StatusTag({ status }: { status: Status }) {
  return <span className={`tag ${status}`}>{status.toUpperCase()}</span>;
}
