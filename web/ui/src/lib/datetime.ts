export function toIso(value: string): string {
  if (!value) {
    return "";
  }
  return value.length === 16 ? `${value}:00` : value;
}

export function toLocalInput(value: string): string {
  return value ? value.slice(0, 16) : "";
}

export function formatTime(value: string): string {
  return value.replace("T", " ").slice(0, 19);
}
