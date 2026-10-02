import React from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import TierPicker from "./TierPicker";

describe("TierPicker", () => {
  it("chooses between the quick and full attack sets", () => {
    const onChange = vi.fn();
    render(<TierPicker tier="quick" onChange={onChange} />);
    expect(screen.getByRole("radio", { name: /Quick/ })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: /Full/ })).toHaveAttribute("aria-checked", "false");
    fireEvent.click(screen.getByRole("radio", { name: /Full/ }));
    expect(onChange).toHaveBeenCalledWith("full");
  });
});
