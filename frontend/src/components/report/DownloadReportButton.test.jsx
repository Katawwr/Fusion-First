import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const calls = [];
let fail = false;
vi.mock("../../lib/scanApi", () => ({
  downloadReportHtml: async (...args) => {
    calls.push(args);
    if (fail) throw new Error("Server said no");
  },
}));

import DownloadReportButton from "./DownloadReportButton";
import ReportCard from "./ReportCard";

afterEach(() => {
  calls.length = 0;
  fail = false;
});

describe("DownloadReportButton", () => {
  it("builds the report from the result the page holds, not a stored scan id", async () => {
    const result = { cards: [], outcomes: [], target_name: "Bot" };
    render(<DownloadReportButton result={result} filename="r.html" />);
    fireEvent.click(screen.getByRole("button", { name: "Download Report" }));
    await waitFor(() => expect(calls).toEqual([[result, "r.html"]]));
  });

  it("says so when the report cannot be built", async () => {
    fail = true;
    render(<DownloadReportButton result={{ cards: [] }} />);
    fireEvent.click(screen.getByRole("button", { name: "Download Report" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Server said no");
  });
});

describe("ReportCard honesty pill", () => {
  it("sits in the header row with only the badge word", () => {
    const card = {
      check: "direct_prompt_injection", kind: "safety", grade: "F", owasp_tags: [], trust: { execution: "canned" },
      before_after: {
        baseline_issue_rate: 0.88, hardened_issue_rate: 0, honesty: "PRELIMINARY", mcnemar_p: 0.2, n_pairs: 8,
        absolute_reduction: { point: 0.88, low: 0.63, high: 1 },
      },
    };
    render(<ReportCard card={card} />);
    const pill = screen.getByText("PRELIMINARY");
    expect(pill.closest("h3, div")?.querySelector("h3")).not.toBeNull();
    expect(screen.queryByText(/Reduction, not yet proven/)).toBeNull();
    expect(screen.getAllByText("PRELIMINARY")).toHaveLength(1);
  });
});
