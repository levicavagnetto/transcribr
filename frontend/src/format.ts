// Small display helpers shared by the screens.

export function minutesAgo(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "never";
  const minutes = Math.floor((now.getTime() - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.floor(hours / 24)} d ago`;
}

export function clockTime(iso: string | null): string {
  if (!iso) return "never";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// Ravon's start times are store time, "YYYY-MM-DD HH:MM:SS"; they are shown as written, never converted.
function localParts(startLocal: string): { date: Date; day: string; time: string } {
  const [day = "", clock = ""] = startLocal.split(" ");
  const [year, month, date] = day.split("-").map(Number);
  const [hour = "0", minute = "00"] = clock.split(":");
  return {
    date: new Date(year ?? 0, (month ?? 1) - 1, date ?? 1),
    day,
    time: `${Number(hour)}:${minute}`,
  };
}

function isoDay(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

// "Today 11:41", "Yesterday 17:12", "Thu Oct 23 16:40". The shop PC's own date stands in for store time.
export function startLabel(startLocal: string, now: Date = new Date()): string {
  const { date, day, time } = localParts(startLocal);
  const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
  if (day === isoDay(now)) return `Today ${time}`;
  if (day === isoDay(yesterday)) return `Yesterday ${time}`;
  const label = date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
  return `${label.replace(",", "")} ${time}`;
}

// "Sat Oct 25 2026"
export function fullDate(startLocal: string): string {
  const { date } = localParts(startLocal);
  return date
    .toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" })
    .replaceAll(",", "");
}

// "10:42", as Ravon wrote it.
export function startClock(startLocal: string): string {
  return (startLocal.split(" ")[1] ?? "").slice(0, 5);
}

// Seconds as "m:ss", for lengths and positions in a call.
export function mss(seconds: number): string {
  const whole = Math.round(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

// "4 min 37 s", or "31 s" for short calls.
export function longLength(minutes: number): string {
  const whole = Math.round(minutes * 60);
  const m = Math.floor(whole / 60);
  return m > 0 ? `${m} min ${whole % 60} s` : `${whole} s`;
}
