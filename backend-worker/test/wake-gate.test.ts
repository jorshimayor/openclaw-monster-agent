import { describe, expect, it } from "vitest";
import { shouldWakeContainer } from "../src/schedule";

/** Daytime and the small hours, in UTC, against the default WAT offset of +1. */
const NOON = new Date("2026-11-06T11:00:00Z");   // 12:00 local
const NIGHT = new Date("2026-11-06T02:00:00Z");  //  3:00 local

/** The timetable sync's trigger. Must stay in step with wrangler.jsonc. */
const SYNC = "5 6 * * *";

describe("shouldWakeContainer", () => {
  it("lets the timetable sync through during the day", () => {
    expect(shouldWakeContainer(SYNC, NOON, {})).toBe(true);
  });

  it("skips the timetable sync overnight", () => {
    // Nine fires a night, each holding a Postgres pool open for fifteen
    // minutes, to re-read a sheet nobody is editing.
    expect(shouldWakeContainer(SYNC, NIGHT, {})).toBe(false);
  });

  it("honours quiet hours being switched off", () => {
    expect(
      shouldWakeContainer(SYNC, NIGHT, { QUIET_HOURS_ENABLED: "false" })
    ).toBe(true);
  });

  it("skips the nag safety net while reminders are off", () => {
    expect(shouldWakeContainer("*/30 * * * *", NOON, {})).toBe(false);
  });

  it("lets the nag safety net through when reminders are on", () => {
    expect(
      shouldWakeContainer("*/30 * * * *", NOON, { NAG_ENABLED: "true" })
    ).toBe(true);
  });

  it("allows anything it does not know about", () => {
    // A new trigger should opt into being skipped, not discover by accident
    // that it was.
    for (const cron of ["15 6 * * *", "0 8 1 * *", "0 7 * * 6"]) {
      expect(shouldWakeContainer(cron, NIGHT, {})).toBe(true);
    }
  });
});
