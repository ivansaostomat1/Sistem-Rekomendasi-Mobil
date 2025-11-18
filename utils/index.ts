// Currency formatting
export function fmtIDR(n: number | undefined | null): string {
  if (n == null || Number.isNaN(n)) return "-";
  try {
    return new Intl.NumberFormat("id-ID", {
      style: "currency",
      currency: "IDR",
      maximumFractionDigits: 0,
    }).format(Number(n));
  } catch {
    return String(n);
  }
}

// Number conversion
export function toNumber(v: string | number | undefined): number | undefined {
  if (typeof v === "number") return v;
  if (v == null) return undefined;
  const digits = String(v).replace(/[^\d-]/g, "");
  if (digits === "") return undefined;
  const n = Number(digits);
  return Number.isFinite(n) ? n : undefined;
}

// Percentage formatting
export function fmtPct(x?: number | null): string {
  if (x == null || !Number.isFinite(Number(x))) return "-";
  const p = Math.round(Number(x) * 100);
  return `${p}%`;
}

// Signed currency formatting
export function signIDR(n?: number | null): string {
  if (n == null || !Number.isFinite(Number(n))) return "-";
  const s = Number(n);
  const sign = s > 0 ? "+" : s < 0 ? "−" : "";
  return `${sign}${fmtIDR(Math.abs(s))}`;
}

// Slug generation for URLs
export function generateSlug(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9 -]/g, '') // Remove invalid chars
    .replace(/\s+/g, '-') // Replace spaces with -
    .replace(/-+/g, '-') // Replace multiple - with single -
    .replace(/^-|-$/g, ''); // Remove leading/trailing -
}

// Debounce function for search inputs
export function debounce<T extends (...args: any[]) => any>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: NodeJS.Timeout;
  return (...args: Parameters<T>) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  };
}

// Local storage utilities
export const storage = {
  get: (key: string): any => {
    try {
      const item = localStorage.getItem(key);
      return item ? JSON.parse(item) : null;
    } catch {
      return null;
    }
  },
  set: (key: string, value: any): void => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (error) {
      console.warn('Local storage set failed:', error);
    }
  },
  remove: (key: string): void => {
    try {
      localStorage.removeItem(key);
    } catch (error) {
      console.warn('Local storage remove failed:', error);
    }
  }
};