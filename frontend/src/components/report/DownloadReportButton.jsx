import React, { useState } from "react";
import Button from "../ui/Button";
import { downloadReportHtml } from "../../lib/scanApi";

// Renders the report from the result the page holds, so it works whichever API container answers
// (the hosted API keeps scans in memory per container).
export default function DownloadReportButton({ result, filename = "fusion-report.html", children = "Download Report" }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const onClick = async () => {
    setBusy(true);
    setError("");
    try {
      await downloadReportHtml(result, filename);
    } catch (e) {
      setError(e?.message || "The report could not be built.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <span className="inline-flex flex-col items-center gap-1">
      <Button variant="outline" onClick={onClick} disabled={busy || !result}>
        {busy ? "Preparing…" : children}
      </Button>
      {error && (
        <span role="alert" className="text-xs text-app-muted">
          {error}
        </span>
      )}
    </span>
  );
}
