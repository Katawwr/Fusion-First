import React from "react";
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { Inline } from "./index";

describe("Inline", () => {
  it("sets backticked spans as code and keeps the spaces around them", () => {
    const { container } = render(
      <p>
        <Inline text="Your key and `FUSION_ALLOW_API_SPEND=1`. Also `hf:` (`HF_TOKEN`)." />
      </p>,
    );
    const codes = [...container.querySelectorAll("code")].map((c) => c.textContent);
    expect(codes).toEqual(["FUSION_ALLOW_API_SPEND=1", "hf:", "HF_TOKEN"]);
    expect(container.textContent).toBe("Your key and FUSION_ALLOW_API_SPEND=1. Also hf: (HF_TOKEN).");
  });

  it("renders plain text unchanged", () => {
    const { container } = render(<Inline text="No code here" />);
    expect(container.querySelector("code")).toBeNull();
    expect(container.textContent).toBe("No code here");
  });
});
