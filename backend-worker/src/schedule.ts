/**
 * Scheduling decisions the Worker can make without waking the container.
 *
 * Kept out of index.ts so it can be tested in plain node: importing the
 * entrypoint drags in @cloudflare/containers, which needs the Workers
 * runtime. Same reason access.ts is its own module.
 */

export type QuietHoursEnv = {
  QUIET_HOURS_ENABLED?: string;
  QUIET_HOURS_START?: string;
  QUIET_HOURS_END?: string;
  USER_TIMEZONE_OFFSET_HOURS?: string;
};

/**
 * True while the user is asleep and the nagger would send nothing anyway.
 *
 * The nag round refuses to fire during quiet hours — but it still wakes the
 * container and queries Neon to count what is waiting before returning. Over a
 * nine-hour window at one fire every ten minutes that is 54 wakes a night to
 * do nothing, and it is why the container never reaches its 15-minute idle
 * threshold. Deciding here costs nothing.
 *
 * The window wraps midnight, so it is a union of two ranges.
 */
export function inQuietHours(now: Date, env: QuietHoursEnv): boolean {
  if ((env.QUIET_HOURS_ENABLED ?? "true") !== "true") return false;
  // Number("") is 0, not NaN, so an empty variable would silently mean
  // "UTC offset zero" instead of "not configured". Blank is treated as unset.
  const num = (value: string | undefined, fallback: number): number =>
    value === undefined || value.trim() === "" ? fallback : Number(value);

  const start = num(env.QUIET_HOURS_START, 22);
  const end = num(env.QUIET_HOURS_END, 7);
  const offset = num(env.USER_TIMEZONE_OFFSET_HOURS, 1);
  if (!Number.isFinite(start) || !Number.isFinite(end) || !Number.isFinite(offset)) {
    return false; // never skip on a misconfiguration; a missed nag is worse
  }
  if (start === end) return true;
  const hour = (now.getUTCHours() + offset + 24) % 24;
  return start < end ? hour >= start && hour < end : hour >= start || hour < end;
}

