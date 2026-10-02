import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import Button from "../components/ui/Button";
import ReportOverview from "../components/report/ReportOverview";
import ReportCard from "../components/report/ReportCard";
import { getScan } from "../lib/scanApi";
import DownloadReportButton from "../components/report/DownloadReportButton";

export default function Report() {
  const { scanId } = useParams();
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    getScan(scanId)
      .then((r) => alive && setResult(r))
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [scanId]);

  if (error) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16 text-center text-app-muted">
        <p className="mb-4">{error}</p>
        <a href="/scan" className="text-fusion-accent underline">
          Run a new scan
        </a>
      </div>
    );
  }
  if (!result) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16 text-center text-app-muted">
        Loading report…
      </div>
    );
  }

  const perCheckOutcomes = (check) =>
    (result.outcomes || []).filter((o) => o.check === check);

  return (
    <div
      style={{
        maxWidth: "820px",
        margin: "0 auto",
        padding: "clamp(2rem, 5vw, 3.5rem) 1rem",
        display: "flex",
        flexDirection: "column",
        gap: "1.5rem",
      }}
    >
      <Helmet>
        <title>Safety Report: {result.target_name} | Fusion First</title>
      </Helmet>
      {/* Same centred header treatment as the scan steps, so a shared report link
          does not land on a page that looks unlike the rest of the product. */}
      <header style={{ textAlign: "center", marginBottom: "0.5rem" }}>
        <h1
          style={{
            fontSize: "clamp(1.75rem, 4vw, 2.5rem)",
            fontWeight: 700,
            color: "var(--text)",
            marginBottom: "0.75rem",
          }}
        >
          Safety report card
        </h1>
      </header>
      <ReportOverview result={result} />
      {result.checks.map((check) => (
        <ReportCard
          key={check}
          card={result.cards.find((c) => c.check === check)}
          outcomes={perCheckOutcomes(check)}
        />
      ))}
      <div className="flex flex-wrap gap-3">
        <DownloadReportButton result={result} filename={`fusion-report-${scanId}.html`}>
          Download report (HTML)
        </DownloadReportButton>
        <a href="/scan">
          <Button>Scan another prompt</Button>
        </a>
      </div>
    </div>
  );
}
