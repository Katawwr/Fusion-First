import { describe, expect, it } from "vitest";
import { targetOptions } from "./targets";

const byId = (opts) => Object.fromEntries(opts.map((o) => [o.id, o]));

describe("targetOptions", () => {
  it("offers any model by spec on a local server", () => {
    const opts = byId(targetOptions({ local_backends_enabled: true, spec: true, cli: false, ollama: false }));
    expect(opts.spec.title).toBe("Any model");
    expect(opts.spec.disabled).toBe(false);
  });

  it("disables it where the server can't run local backends, and while unknown", () => {
    expect(byId(targetOptions({ local_backends_enabled: false, spec: false })).spec.disabled).toBe(true);
    expect(byId(targetOptions(null)).spec.disabled).toBe(true);
  });
});
