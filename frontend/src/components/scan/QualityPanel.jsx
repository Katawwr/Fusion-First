import React, { useState } from "react";
import { X } from "lucide-react";
import Card from "../ui/Card";
import Button from "../ui/Button";
import GradeBadge from "../report/GradeBadge";
import { gradeQuality } from "../../lib/scanApi";
import { qualityMeta } from "../../lib/jargon";

// Live-only: a 402/403 means this server has no live backend, so point to the local path.
export default function QualityPanel({ systemPrompt }) {
  const [state, setState] = useState("idle"); // idle | loading | done | unavailable | error
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const meta = qualityMeta("instruction_following");

  const run = async () => {
    setState("loading");
    setErr("");
    try {
      const res = await gradeQuality(systemPrompt);
      setData(res);
      setState("done");
    } catch (e) {
      if (e.status === 402 || e.status === 403) setState("unavailable");
      else {
        setErr(e.message || "Failed to grade quality");
        setState("error");
      }
    }
  };

  const q = data?.quality_checks?.[0];

  return (
    <Card>
      <p className="mb-2 font-semibold text-app-text">{meta.label}</p>
      <p className="mb-3 text-sm text-app-muted">{meta.scenario}</p>

      {state === "idle" && (
        <Button variant="outline" onClick={run}>
          Grade Quality
        </Button>
      )}

      {state === "loading" && (
        <p className="text-sm text-app-muted">Grading sample tasks…</p>
      )}

      {state === "unavailable" && (
        <p className="text-sm text-app-muted">
          Needs a live model: <code>fusion serve</code>, or{" "}
          <code>
            fusion run start --prompt prompt.txt --check quality --target
            ollama:llama3.2:1b --grader claude-cli
          </code>
          .
        </p>
      )}

      {state === "error" && (
        <p className="text-sm" style={{ color: "var(--danger)" }}>
          {err}
        </p>
      )}

      {state === "done" && q && (
        <div>
          <div className="flex items-center gap-3">
            <GradeBadge grade={q.grade} size="lg" />
            <p className="text-sm text-app-muted">
              {q.n_defects} of {q.n} responses had a defect
              {data.judge ? ` · graded by ${data.judge}` : ""}
            </p>
          </div>
          {q.defects?.length > 0 && (
            <ul className="mt-3 flex flex-col gap-2 text-sm">
              {q.defects.slice(0, 3).map((d, i) => (
                <li key={i} className="flex items-start gap-2 text-app-muted">
                  <X
                    size={15}
                    color="var(--danger)"
                    style={{ flexShrink: 0, marginTop: "0.2rem" }}
                    aria-hidden
                  />
                  <span>
                    <span className="text-app-text">{d.input}</span>
                    {d.issue_type
                      ? `, ${d.issue_type.replace(/_/g, " ")}`
                      : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Card>
  );
}
