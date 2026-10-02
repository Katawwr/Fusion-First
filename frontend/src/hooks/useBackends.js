import { useEffect, useState } from "react";
import { API_URL } from "../lib/scanApi";

// What this server can run (/api/version -> backends); null = unknown.
export function useBackends() {
  const [state, setState] = useState({ backends: null, loading: true });

  useEffect(() => {
    let alive = true;
    fetch(`${API_URL}/api/version`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => alive && setState({ backends: d?.backends || null, loading: false }))
      .catch(() => alive && setState({ backends: null, loading: false }));
    return () => {
      alive = false;
    };
  }, []);

  return state;
}
