import React from "react";
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter } from "react-router-dom";
import Privacy from "./Privacy";
import Footer from "../components/layout/Footer";

describe("Privacy page", () => {
  it("names every browser storage the app uses and the API-spend gate", () => {
    const { container } = render(
      <HelmetProvider>
        <MemoryRouter>
          <Privacy />
        </MemoryRouter>
      </HelmetProvider>,
    );
    const text = container.textContent;
    expect(text).toMatch(/localStorage/);
    expect(text).toMatch(/sessionStorage/); // src/lib/session.js keeps the last scan
    expect(text).toMatch(/Google Fonts/);
    expect(text).toMatch(/and FUSION_ALLOW_API_SPEND=1/);
    expect(text).toMatch(/never to a model: the responses are recorded/);
  });
});

describe("Footer", () => {
  it("holds only Privacy & Terms and the copyright", () => {
    const { container } = render(
      <MemoryRouter>
        <Footer />
      </MemoryRouter>,
    );
    expect(container.querySelectorAll("a")).toHaveLength(1);
    expect(container.textContent).toBe("Privacy & Terms© 2026 Fusion First");
  });
});
