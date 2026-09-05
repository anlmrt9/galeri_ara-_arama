import AsyncStorage from "@react-native-async-storage/async-storage";

const API_BASE_KEY = "otogaleri_api_base";
let cachedBase = null;

export async function getApiBase() {
  if (cachedBase !== null) return cachedBase;
  const stored = await AsyncStorage.getItem(API_BASE_KEY);
  cachedBase = stored || "";
  return cachedBase;
}

export async function setApiBase(url) {
  const clean = url.trim().replace(/\/+$/, "");
  cachedBase = clean;
  await AsyncStorage.setItem(API_BASE_KEY, clean);
}

async function request(path, options = {}) {
  const base = await getApiBase();
  if (!base) {
    throw new Error("API adresi ayarlanmamış. Lütfen Ayarlar sekmesinden girin.");
  }
  const res = await fetch(`${base}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch (e) {
      // ignore parse error, keep statusText
    }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

export const checkHealth = () => request("/api/health");
export const getConfig = () => request("/api/config");
export const getListings = () => request("/api/listings");
export const clearListings = () => request("/api/listings", { method: "DELETE" });
export const getScanStatus = () => request("/api/scan/status");
export const startScan = (criteria) =>
  request("/api/scan/start", { method: "POST", body: JSON.stringify(criteria) });
export const stopScan = () => request("/api/scan/stop", { method: "POST" });
