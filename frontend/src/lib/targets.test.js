import { describe, expect, it } from "vitest";
import { targetOptions } from "./targets";

const byId = (opts) => Object.fromEntries(opts.map((o) => [o.id, o]));
const ids = (opts) => opts.map((o) => o.id);

describe("targetOptions", () => {
  it("offers any model by spec on a local server", () => {
    const opts = byId(targetOptions({ local_backends_enabled: true, spec: true, cli: false, ollama: false }));
    expect(opts.spec.title).toBe("Any model");
    expect(opts.spec.disabled).toBe(false);
  });

  it("lists every live target on a local server, disabled ones with a reason", () => {
    const opts = targetOptions({ local_backends_enabled: true, spec: true, cli: false, cli_reason: "not logged in", ollama: false });
    expect(ids(opts)).toEqual(["demo", "ollama", "cli", "spec"]);
    expect(byId(opts).cli).toMatchObject({ disabled: true, note: "Unavailable: not logged in." });
  });

  it("offers only the demo where the server can't run live models, and while unknown", () => {
    expect(ids(targetOptions({ local_backends_enabled: false, spec: false }))).toEqual(["demo"]);
    expect(ids(targetOptions(null))).toEqual(["demo"]);
  });

  it("adds a hosted scan only when the hosted server enabled one", () => {
    expect(ids(targetOptions({ local_backends_enabled: false, api: true }))).toEqual(["demo", "hosted"]);
    expect(targetOptions({ local_backends_enabled: false, api: true })[1].disabled).toBeFalsy();
  });
});
