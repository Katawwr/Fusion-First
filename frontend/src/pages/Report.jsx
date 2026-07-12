import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import Button from '../components/ui/Button';
import ReportOverview from '../components/report/ReportOverview';
import ReportCard from '../components/report/ReportCard';
import { getScan, reportHtmlUrl } from '../lib/scanApi';

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
        <a href="/scan" className="text-fusion-cyan underline">
          Run a new scan
        </a>
      </div>
    );
  }
  if (!result) {
    return <div className="mx-auto max-w-2xl px-4 py-16 text-center text-app-muted">Loading report…</div>;
  }

  const perCheckOutcomes = (check) => (result.outcomes || []).filter((o) => o.check === check);

  return (
    <div className="mx-auto max-w-4xl space-y-5 px-4 py-8">
      <Helmet>
        <title>Safety Report — {result.target_name} — Fusion First</title>
      </Helmet>
      <ReportOverview result={result} />
      {result.checks.map((check) => (
        <ReportCard key={check} card={result.cards.find((c) => c.check === check)} outcomes={perCheckOutcomes(check)} />
      ))}
      <div className="flex flex-wrap gap-3">
        <a href={reportHtmlUrl(scanId)} target="_blank" rel="noreferrer">
          <Button variant="outline">Download report (HTML)</Button>
        </a>
        <a href="/scan">
          <Button>Scan another prompt</Button>
        </a>
      </div>
    </div>
  );
}
