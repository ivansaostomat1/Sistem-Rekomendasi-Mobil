// ====== Core Types ======
export type Theme = "dark" | "light";

// Kode bahan bakar dari API
export type FuelCode = "g" | "d" | "h" | "p" | "e" | "o";

export interface SpecFilters {
  trans_choice?: "Matic" | "Manual" | "";
  segmentasi?: string;
  ef_choice?: "irit" | "normal" | "";
  seats_min?: number | "";
  brand?: string;
  // ganti single fuel -> multi fuels (kode)
  fuels?: FuelCode[];
}

export interface RecommendItem {
  image_url?: string | null;
  image?: string | null;

  brand?: string | null;
  model?: string | null;

  price?: number | null;
  fit_score?: number | null;
  points?: number | null;          // <- sudah didukung backend

  segmentasi?: string | null;
  fuel?: string | null;
  fuel_code?: FuelCode | string;   // <- tambahkan ini

  trans?: string | null;
  seats?: number | null;
  cc_kwh?: number | string | null; // <- aman kalau backend kirim string
  alasan?: string | null;
}

export interface RecommendResponse {
  pred_years?: number;
  count: number;
  items: RecommendItem[];
  message?: string;
  budget?: number;     // dipakai untuk CarCard
  needs?: string[];
}

// ====== UI Types ======
export interface Brand { name: string; logo: string; }
export interface SegmentInfo { title: string; desc: string; }
export interface FuelType { title: string; desc: string; iconKey: string; }
export interface TopResaleCar { brand: string; model: string; resale: string; image: string; }

// ====== Form Types ======
export interface LocalForm {
  budget?: number;
  pred_years?: number;
  trusted_only?: boolean;
  topn?: number;
  filters: SpecFilters;
}

// ====== Component Props ======
export interface HeaderProps {
  theme: Theme;
  toggleTheme: () => void;
}

export interface CarCardProps {
  item: RecommendItem;
  index: number;
  theme: Theme;
  budget?: number;
  showMetrics?: boolean;
}

// ====== Meta dari /meta ======
export type Need = { key: string; label: string; image: string };
export type MetaFuel = { code: FuelCode; label: string };

export interface MetaResponse {
  brands: string[];
  fuels: MetaFuel[];
  needs: Need[];
  data_ready: { specs: boolean; retail: boolean; wholesale: boolean };
  budgetDefault?: number; // ← perbaikan: tambahkan field opsional ini (ejaan benar)
}


// ====== Request ke /recommendations ======
export interface RecommendRequest {
  budget: number;
  topn: number;
  needs: string[];
  filters?: {
    trans_choice?: "Matic" | "Manual";
    brand?: string;
    fuels?: FuelCode[];   // <- multi-select fuel yang dikirim ke API
  };
}
