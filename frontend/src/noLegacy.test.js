import { describe, expect, it } from "vitest";

// No accounts and no billing: fails if the retired backend, auth or checkout creeps back into shipped source.
const sources = import.meta.glob(["./**/*.{js,jsx}", "!./**/*.test.{js,jsx}"], {
  query: "?raw",
  import: "default",
  eager: true,
});

const FORBIDDEN = [
  /fusion-quality-tester/i,
  /modal\.run/i,
  /supabase/i,
  /lemonsqueezy/i,
  /license key/i,
];

describe("no legacy auth/billing in shipped source", () => {
  it("scans a meaningful number of files", () => {
    expect(Object.keys(sources).length).toBeGreaterThan(20);
  });

  for (const pattern of FORBIDDEN) {
    it(`contains no ${pattern}`, () => {
      const hits = Object.entries(sources)
        .filter(([, text]) => pattern.test(text))
        .map(([file]) => file);
      expect(hits).toEqual([]);
    });
  }
});
