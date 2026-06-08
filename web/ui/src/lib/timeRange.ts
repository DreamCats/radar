export type RangePreset = "yesterdayClose" | "today" | "yesterday" | "last24h" | "last7d" | "last30d" | "custom";

export type LocalRange = {
  startDate: string;
  startTime: string;
  endDate: string;
  endTime: string;
};

export const RANGE_PRESETS: Array<[RangePreset, string]> = [
  ["today", "今天"],
  ["yesterday", "昨天"],
  ["last24h", "近 24 小时"],
  ["last7d", "近 7 天"],
  ["last30d", "近 30 天"],
];

export function buildYesterdayCloseRange(now = new Date()): LocalRange {
  return buildRange(yesterdayClose(now), now);
}

export function buildPresetRange(preset: RangePreset): LocalRange {
  const now = new Date();
  if (preset === "yesterdayClose") {
    return buildYesterdayCloseRange(now);
  }
  if (preset === "yesterday") {
    const day = addDays(startOfDay(now), -1);
    return buildRange(day, endOfDay(day));
  }
  if (preset === "last24h") {
    return buildRange(addHours(now, -24), now);
  }
  if (preset === "last7d") {
    return buildRange(addDays(now, -7), now);
  }
  if (preset === "last30d") {
    return buildRange(addDays(now, -30), now);
  }
  return buildRange(startOfDay(now), now);
}

export function toLocalIso(date: string, time: string): string {
  return date && time ? `${date}T${time}:00` : "";
}

export function rangeLabel(range: LocalRange): string {
  return `${range.startDate} ${range.startTime} - ${range.endDate} ${range.endTime}`;
}

function buildRange(start: Date, end: Date): LocalRange {
  return {
    startDate: formatDate(start),
    startTime: formatClock(start),
    endDate: formatDate(end),
    endTime: formatClock(end),
  };
}

function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate(), 0, 0);
}

function endOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate(), 23, 59);
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function addHours(date: Date, hours: number): Date {
  return new Date(date.getTime() + hours * 60 * 60 * 1000);
}

function yesterdayClose(now: Date): Date {
  const close = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 15, 0);
  close.setDate(close.getDate() - 1);
  return close;
}

function formatDate(date: Date): string {
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

function formatClock(date: Date): string {
  const hour = `${date.getHours()}`.padStart(2, "0");
  const minute = `${date.getMinutes()}`.padStart(2, "0");
  return `${hour}:${minute}`;
}
