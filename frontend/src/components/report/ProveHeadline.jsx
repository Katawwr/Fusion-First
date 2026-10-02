import React from "react";
import { ArrowRight } from "lucide-react";
import Card from "../ui/Card";
import GradeBadge from "./GradeBadge";

// The prompt fix's before/after headline: the prompt as written vs with the fix. `canned` (the demo)
// replays recorded answers, so it is never called a measurement.
export default function ProveHeadline({ baselineGrade, hardenedGrade, canned = false }) {
  return (
    <Card variant="elevated">
      <div style={{ textAlign: "center" }}>
        <p
          style={{
            fontSize: "0.75rem",
            fontWeight: 700,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: "var(--subtle)",
          }}
        >
          Safety grade
        </p>
        <div
          style={{
            margin: "1.5rem 0",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "2rem",
          }}
        >
          <div>
            <GradeBadge grade={baselineGrade} size="lg" />
            <p style={{ marginTop: "0.65rem", fontSize: "0.9375rem", color: "var(--muted)" }}>
              as written
            </p>
          </div>
          <ArrowRight size={28} color="var(--accent)" style={{ marginBottom: "1.75rem" }} aria-hidden />
          <div>
            <GradeBadge grade={hardenedGrade} size="lg" />
            <p style={{ marginTop: "0.65rem", fontSize: "0.9375rem", color: "var(--muted)" }}>
              with fix
            </p>
          </div>
        </div>
        {!canned && <p style={{ color: "var(--muted)", margin: 0 }}>Paired measurement on your model.</p>}
      </div>
    </Card>
  );
}
