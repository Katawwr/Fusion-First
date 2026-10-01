import React from "react";
import GradeBadge from "./GradeBadge";
import DemoBanner from "../ui/DemoBanner";
import { summarize } from "../../lib/summary";

// One plain sentence + the overall grade, derived from what was actually measured. An example
// report's headline already says the prompt was not run, so it carries no second demo banner.
export default function ReportOverview({ result }) {
  const s = summarize(result);
  const example = s.kind === "example";
  return (
    <div className="flex flex-col gap-4">
      {result.demonstration && !example && <DemoBanner />}
      <div className="flex items-center gap-5">
        <GradeBadge grade={example ? "?" : result.overall_grade} size="lg" />
        <div>
          <h2 className="text-2xl font-bold text-app-text">{s.headline}</h2>
          <p className="mt-1 text-app-muted">{s.sentence}</p>
        </div>
      </div>
    </div>
  );
}
