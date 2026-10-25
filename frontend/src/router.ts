import { useEffect, useState } from "react";

// "#/runs/abc" -> {path: "/runs", params: ["abc"]}; "#/" or "" -> {path: "/", params: []}
function parse(): { path: string; params: string[] } {
  const [first = "", ...params] = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  return { path: "/" + first, params: params.map(decodeURIComponent) };
}

export function useRoute() {
  const [route, setRoute] = useState(parse);
  useEffect(() => {
    const on = () => setRoute(parse());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export function navigate(hash: string) {
  location.hash = hash;
}
