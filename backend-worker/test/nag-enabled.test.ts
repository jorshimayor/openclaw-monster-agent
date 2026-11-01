import { describe, expect, it } from "vitest";
import { nagEnabled } from "../src/schedule";

describe("nagEnabled", () => {
  it("is off when nothing is configured", () => {
    // The Worker and the container have to agree, and the container ships off.
    expect(nagEnabled({})).toBe(false);
  });

  it("is off for an empty or blank value", () => {
    expect(nagEnabled({ NAG_ENABLED: "" })).toBe(false);
    expect(nagEnabled({ NAG_ENABLED: " " })).toBe(false);
  });

  it("is off for anything that is not exactly true", () => {
    for (const value of ["false", "0", "no", "TRUE", "True", "yes"]) {
      expect(nagEnabled({ NAG_ENABLED: value })).toBe(false);
    }
  });

  it("is on only for the exact string the config uses", () => {
    expect(nagEnabled({ NAG_ENABLED: "true" })).toBe(true);
  });
});
