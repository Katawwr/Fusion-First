import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Use from "./Use";
import content from "../content/integrations.json";

describe("Use page", () => {
  it("renders every integration section with its commands", () => {
    render(
      <MemoryRouter>
        <Use />
      </MemoryRouter>,
    );
    for (const section of content.sections) {
      expect(screen.getByRole("heading", { name: section.title })).toBeInTheDocument();
    }
    expect(screen.getByText(/fusion doctor/)).toBeInTheDocument();
    expect(screen.getByText(/claude plugin install fusion@fusion-first/)).toBeInTheDocument();
  });

  it("never asks for an API key", () => {
    const text = JSON.stringify(content).toLowerCase();
    expect(text).not.toMatch(/api[_ ]key\s*[:=]|anthropic_api_key|openai_api_key/);
    expect(text).toMatch(/no api key/);
  });
});
