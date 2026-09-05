// app.py'deki format_try ile aynı TR yerel biçimi (34980.5 -> "34.980,50").
export function formatTry(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "0,00";
  const parts = n.toFixed(2).split(".");
  const intPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${intPart},${parts[1]}`;
}

export function formatDateTime(iso) {
  if (!iso) return "--:--";
  try {
    const d = new Date(iso);
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return `${hh}:${mm}`;
  } catch (e) {
    return "--:--";
  }
}

export const SITE_EMOJI = {
  Otoplus: "🚗",
  VavaCars: "🚙",
  "Otokoç 2. El": "🚘",
  "Arabam.com": "🏎️",
  Sahibinden: "🚓",
};
