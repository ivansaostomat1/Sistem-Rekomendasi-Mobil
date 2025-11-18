// @/types

export type Theme = "dark" | "light";

export interface RecommendItem {
  brand: string;
  model: string;
  price: number;
  predicted_resale_value: number;
  resale_multiplier: number;
  fit_score: number;
  segmentasi?: string;
  fuel?: string;
  trans?: string;
  seats?: number | null;
  cc_kwh?: number | null;
  alasan?: string;
  image_url?: string;        
}

export interface RecommendResponse {
  pred_years: number;
  count: number;
  items: RecommendItem[];
}

export interface MetaResponse {
  brands?: string[];
  segments?: string[];
  fuels?: string[];
  seats?: number[];
  data_ready?: { specs: boolean; retail: boolean; wholesale: boolean };
}
