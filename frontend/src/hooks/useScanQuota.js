import { useEffect, useState } from "react";
import { API_URL } from "../lib/scanApi";

// Replaces the legacy credits hook. Demo scans are unlimited; real scans are gated (enforced
// server-side in M4). During beta this just reports availability from /api/version.
export function useScanQuota() {
  const [quota, setQuota] = useState({
    liveAvailable: false,
    freePerDay: 3,
    loading: true,
  });

  useEffect(() => {
    let alive = true;
    fetch(`${API_URL}/api/version`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (alive && d) {
          setQuota({
            liveAvailable: !!d.live_available,
            freePerDay: 3,
            loading: false,
          });
        } else if (alive) {
          setQuota((q) => ({ ...q, loading: false }));
        }
      })
      .catch(() => alive && setQuota((q) => ({ ...q, loading: false })));
    return () => {
      alive = false;
    };
  }, []);

  return quota;
}
