import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Header from "./Header";

describe("Header", () => {
  it("labels the /use link 'Use'", () => {
    render(
      <MemoryRouter>
        <Header />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Use" })).toHaveAttribute("href", "/use");
  });

  it("sets the wordmark in the title face", () => {
    render(
      <MemoryRouter>
        <Header />
      </MemoryRouter>,
    );
    expect(screen.getByText("Fusion First")).toHaveClass("brand-wordmark");
  });

  it("shows the FF monogram, not the retired logo image", () => {
    const { container } = render(
      <MemoryRouter>
        <Header />
      </MemoryRouter>,
    );
    expect(container.querySelector("header svg.brand-mark")).not.toBeNull();
    expect(container.querySelector('header img[src="/logo.png"]')).toBeNull();
  });
});
