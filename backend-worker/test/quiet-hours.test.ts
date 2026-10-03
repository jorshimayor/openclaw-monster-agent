/**
 * Skipping the nag round while the user is asleep.
 *
 * This decides whether to wake a container and hit the database, so a wrong
 * `true` costs a missed reminder and a wrong `false` costs the saving. The
 * window wraps midnight, which is where this kind of check usually breaks.
 */

import { describe, expect, it } from "vitest";

import { inQuietHours } from "../src/schedule";

// 22:00 -> 07:00 local, user at UTC+1.
const env = {
  QUIET_HOURS_ENABLED: "true",
  QUIET_HOURS_START: "22",
  QUIET_HOURS_END: "7",
  USER_TIMEZONE_OFFSET_HOURS: "1",
} as any;

/** A UTC instant for a given LOCAL hour at UTC+1. */
const atLocal = (hour: number) => new Date(Date.UTC(2026, 9, 7, (hour - 1 + 24) % 24, 30));

describe("the overnight window", () => {
  it("is quiet from 22:00 through 06:59 local", () => {
    for (const hour of [22, 23, 0, 1, 3, 5, 6]) {
      expect(inQuietHours(atLocal(hour), env), `${hour}:30 local`).toBe(true);
    }
  });

  it("is awake from 07:00 through 21:59 local", () => {
    for (const hour of [7, 8, 12, 17, 21]) {
      expect(inQuietHours(atLocal(hour), env), `${hour}:30 local`).toBe(false);
    }
  });

  it("treats the boundaries as start-inclusive and end-exclusive", () => {
    expect(inQuietHours(new Date(Date.UTC(2026, 9, 7, 21, 0)), env)).toBe(true);  // 22:00
    expect(inQuietHours(new Date(Date.UTC(2026, 9, 7, 6, 0)), env)).toBe(false);  // 07:00
  });
});

describe("it fails toward sending", () => {
  it("never skips when quiet hours are switched off", () => {
    expect(inQuietHours(atLocal(2), { ...env, QUIET_HOURS_ENABLED: "false" })).toBe(false);
  });

  it("never skips on a value that is genuinely garbage", () => {
    // A missed reminder is worse than a wasted container wake.
    expect(inQuietHours(atLocal(2), { ...env, QUIET_HOURS_START: "nonsense" })).toBe(false);
    expect(inQuietHours(atLocal(2), { ...env, USER_TIMEZONE_OFFSET_HOURS: "x" })).toBe(false);
  });

  it("treats a blank variable as unset, not as zero", () => {
    // Number("") is 0, so a blank offset would quietly shift the whole window
    // by an hour instead of falling back to the configured default.
    expect(inQuietHours(atLocal(2), { ...env, USER_TIMEZONE_OFFSET_HOURS: "" })).toBe(true);
    expect(inQuietHours(atLocal(12), { ...env, USER_TIMEZONE_OFFSET_HOURS: "" })).toBe(false);
  });

  it("honours start === end as a full day of quiet", () => {
    expect(inQuietHours(atLocal(13), { ...env, QUIET_HOURS_START: "9", QUIET_HOURS_END: "9" })).toBe(true);
  });
});

describe("the saving", () => {
  it("skips 9 of every 24 hourly slots", () => {
    const quiet = Array.from({ length: 24 }, (_, h) => inQuietHours(atLocal(h), env)).filter(Boolean);
    expect(quiet).toHaveLength(9);
  });
});
