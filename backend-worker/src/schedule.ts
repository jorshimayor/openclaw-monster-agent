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



export type NagEnv = {
  NAG_ENABLED?: string;
};

/**
 * True when the reminder engine is switched on.
 *
 * The container's own config decides whether a reminder is sent, but the
 * Worker decides whether to wake the container to ask. Those have to agree:
 * the half-hourly safety net re-books a wake whenever none is stored, so with
 * the engine off the chain becomes wake -> start the container -> learn it is
 * disabled -> book nothing -> safety net re-arms, forever. A container start
 * every thirty minutes to be told there is nothing to say.
 *
 * Defaults to off, matching the backend.
 */
export function nagEnabled(env: NagEnv): boolean {
  return (env.NAG_ENABLED ?? "false") === "true";
}


export type WakeEnv = QuietHoursEnv & NagEnv;

/**
 * Whether a cron fire may wake the container.
 *
 * Waking it is the expensive act, not the work it then does. The container
 * lives 15 minutes after a wake and holds a Postgres pool open for all of it,
 * which stops Neon scaling to zero — so one fire costs roughly twenty minutes
 * of database compute whatever the request was. Deciding out here costs
 * nothing, which is the whole point of deciding out here.
 *
 * Anything not named is allowed through: a new trigger should have to opt into
 * being skipped, not discover by accident that it was.
 */
export function shouldWakeContainer(cron: string, now: Date, env: WakeEnv): boolean {
  switch (cron) {
    case "*/30 * * * *":
      // The nag safety net. It never touches the container itself, but it
      // books wakes that do, so with reminders off it has nothing to arm.
      return nagEnabled(env);
    case "5 * * * *":
      // The timetable sync. The sheet does not change while you are asleep,
      // and the day page reads it live on every request rather than from
      // this — so skipping overnight costs nothing and saves nine wakes.
      return !inQuietHours(now, env);
    default:
      return true;
  }
}
