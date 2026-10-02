import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import TrustStrip from "./TrustStrip";
import { scoredSentence } from "../../lib/trust";
import BeforeAfterBars from "./BeforeAfterBars";

describe("TrustStrip", () => {
  it("says a canned demo did not run your prompt", () => {
    render(<TrustStrip card={{ trust: { execution: "canned", n_planned: 8, n_scored: 8, n_errored: 0 } }} />);
    expect(screen.getByText("Recorded responses")).toBeInTheDocument();
    expect(screen.getByText(/stand-in grader/)).toBeInTheDocument();
  });

  it("shows the live grader, its independence and unscored attacks", () => {
    render(
      <TrustStrip
        card={{
          trust: {
            execution: "live",
            judge_id: "claude-sonnet-5",
            judge_backend: "claude_cli",
            independence: "cross_family",
            n_planned: 8,
            n_scored: 6,
            n_errored: 2,
            error_kinds: { judge_timeout: 2 },
            sampling_pinned: false,
          },
        }}
      />,
    );
    expect(screen.getByText(/claude-sonnet-5 via claude_cli/)).toBeInTheDocument();
    expect(screen.getByText(/different model family/)).toBeInTheDocument();
    expect(screen.getByText(/6 of 8 attacks scored/)).toBeInTheDocument();
    expect(screen.getByText(/grader timeout/)).toBeInTheDocument();
    expect(screen.getByText(/repeat runs may differ/)).toBeInTheDocument();
  });

  it("renders nothing without trust info", () => {
    const { container } = render(<TrustStrip card={{}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("builds a coverage sentence that never implies unscored = safe", () => {
    expect(scoredSentence({ n_planned: 4, n_scored: 4, n_errored: 0 })).toBe("4 of 4 attacks scored");
    expect(scoredSentence({ n_planned: 4, n_scored: 3, n_errored: 1, error_kinds: { judge_parse: 1 } })).toMatch(
      /never counted as safe/,
    );
  });
});

describe("honesty badge", () => {
  it("shows the badge without a reasons block or blurb", () => {
    render(
      <BeforeAfterBars
        ba={{ baseline_issue_rate: 0.5, hardened_issue_rate: 0.25, honesty: "PRELIMINARY", mcnemar_p: 0.2, n_pairs: 8, honesty_reasons: ["needs at least 20 paired attacks (had 8)"] }}
      />,
    );
    expect(screen.getByText("PRELIMINARY")).toBeInTheDocument();
    expect(screen.queryByText("Why not PROVEN?")).toBeNull();
    expect(screen.queryByText(/had 8/)).toBeNull();
    expect(screen.queryByText(/chance can't be ruled out/)).toBeNull();
  });
});
