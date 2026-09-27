import React from "react";
import { ArrowRight } from "lucide-react";
import Card from "../ui/Card";
import GradeBadge from "./GradeBadge";

// The Prove step's headline: the prompt as written vs the hardened prompt. `canned` (the demo)
// replays hand-written "after" answers, so it must never read as a measurement.
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
          Safety, before and after
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
              your prompt
            </p>
          </div>
          <ArrowRight size={28} color="var(--accent)" style={{ marginBottom: "1.75rem" }} aria-hidden />
          <div>
            <GradeBadge grade={hardenedGrade} size="lg" />
            <p style={{ marginTop: "0.65rem", fontSize: "0.9375rem", color: "var(--muted)" }}>
              hardened
            </p>
          </div>
        </div>
        <p style={{ color: "var(--muted)", margin: 0 }}>
          {canned ? (
            <>
              An example: in this demo the hardened answers are hand-written to show how a report reads.
              It is not a measurement. Run a live scan to see what the fix does on your model —{" "}
              <a href="/trust" className="underline">
                on small open-weight models it rarely helped
              </a>
              .
            </>
          ) : (
            "The same attacks, run against your original and hardened agent. An apples-to-apples measurement."
          )}
        </p>
      </div>
    </Card>
  );
}
