"use client";

import React, { useMemo } from "react";
import TiltedCard from "@/components/ui/TiltedCard";
import { StickyResultBar } from "./StickyResultBar";
import { SkeletonGrid } from "./SkeletonGrid";
import type { Theme } from "../_types/theme";
import type { RecommendItem, RecommendResponse } from "@/types";
import { fmtIDR } from "@/utils";

type Props = {
  theme: Theme;
  loading: boolean;
  error: string | null;
  data: RecommendResponse | null;
  onBackToForm: () => void;
};

const FUEL_VISUAL: Record<string, { color: string; label: string }> = {
  g: { color: "#f59e0b", label: "Bensin" },
  d: { color: "#6b7280", label: "Diesel" },
  h: { color: "#10b981", label: "Hybrid" },
  p: { color: "#8b5cf6", label: "PHEV" },
  e: { color: "#06b6d4", label: "BEV" },
  o: { color: "#6b7280", label: "Lainnya" },
};

function fuelToCodeLoose(raw?: string | null): string {
  const s = String(raw ?? "").trim().toLowerCase();
  if (!s || s === "na" || s === "n/a" || s === "-") return "o";
  if (s.includes("phev") || s.includes("plug-in") || s.includes("plugin") || s.includes("plug in")) return "p";
  if (s === "h" || s.includes("hybrid") || s.includes("hev")) return "h";
  if (s === "e" || s.includes("bev") || s.includes("electric") || s === "ev") return "e";
  if (s === "d" || s.includes("diesel") || s.includes("dsl") || s.includes("solar")) return "d";
  if (s === "g" || s.includes("bensin") || s.includes("gasoline") || s.includes("petrol")) return "g";
  return "o";
}

/** ——— ROBUST FIT% ——— **/
const SCORE_FLOOR = 5; // ubah jika ingin lebih tinggi/rendah
const SCORE_CEIL = 99;
const TIGHT_SPAN = 1e-3; // ambang "sebaran sempit" untuk fallback rank

function percentile(arr: number[], q: number): number {
  if (!arr.length) return 0;
  const s = [...arr].sort((a, b) => a - b);
  const pos = (s.length - 1) * q;
  const base = Math.floor(pos);
  const rest = pos - base;
  return s[base + 1] !== undefined ? s[base] + rest * (s[base + 1] - s[base]) : s[base];
}

function buildFitLabelers(items: RecommendItem[]) {
  const fs = items.map((x) => (typeof x.fit_score === "number" ? x.fit_score : 0));
  const p10 = percentile(fs, 0.10);
  const p90 = percentile(fs, 0.90);
  const span = Math.max(1e-6, p90 - p10);

  // rank vector (ascending) untuk fallback
  const sorted = [...fs].sort((a, b) => a - b);
  const n = Math.max(1, sorted.length - 1);

  return {
    pctByValue: (v: number) => {
      if (p90 - p10 < TIGHT_SPAN) {
        // Fallback rank-based agar tetap tersebar
        const idx = sorted.lastIndexOf(v); // nilai lebih besar → indeks lebih besar
        const t = idx / n;
        return Math.round(SCORE_FLOOR + t * (SCORE_CEIL - SCORE_FLOOR));
      }
      // Winsorized min–max (P10–P90) + clamp
      const t = Math.min(1, Math.max(0, (v - p10) / span));
      return Math.round(SCORE_FLOOR + t * (SCORE_CEIL - SCORE_FLOOR));
    },
  };
}

export function ResultsSection({ theme, loading, error, data, onBackToForm }: Props) {
  const isDark = theme === "dark";

  const safeCount =
    (data && typeof (data as any).count === "number" ? (data as any).count : data?.items?.length) ?? 0;

  const labeler = useMemo(() => buildFitLabelers(data?.items ?? []), [data]);

  const cards = useMemo(() => {
    if (!data?.items?.length) return [];

    return data.items.map((it: RecommendItem, i: number) => {
      const fuelCode = ((it as any).fuel_code as string | undefined)?.toLowerCase?.() || fuelToCodeLoose(it.fuel);
      const fv = FUEL_VISUAL[fuelCode] ?? FUEL_VISUAL.o;

      const title = `${it.brand ?? ""} ${it.model ?? ""}`.trim();
      const priceStr = it.price != null ? fmtIDR(Number(it.price)) : "-";
      const fs = typeof it.fit_score === "number" ? it.fit_score : 0;
      const fitPct = labeler.pctByValue(fs); // <<— pakai robust label
      const fuelLabel = fv.label;
      const trans = it.trans ? String(it.trans) : "-";
      const seats = typeof it.seats === "number" && isFinite(it.seats) ? `${it.seats} kursi` : "-";
      const img = (it as any).image || (it as any).image_url || "/cars/default.jpg";

      const overlay = (
        <div className="absolute inset-0">
          {/* harga kanan-atas */}
          <div className="absolute top-2 right-2 bg-black/60 text-white text-xs font-semibold px-2 py-1 rounded-md whitespace-nowrap">
            OTR{priceStr}
          </div>
          {/* footer judul + meta */}
          <div className="absolute inset-x-0 bottom-0 p-2 bg-gradient-to-t from-black/80 via-black/20 to-transparent">
            <div className="text-white text-[13px] font-semibold leading-tight line-clamp-2 w-fit bg-black/80 px-1 py-0.5 rounded">
              {title}
            </div>
            <div className="mt-0.5 text-[11px] text-white/90 flex items-center gap-1 whitespace-nowrap overflow-hidden">
              <span className="bg-black/50 text-white text-[11px] px-2 py-0.5 rounded-md">#{i + 1}</span>
              <span className="bg-black/50 px-1.5 py-0.5 rounded">{fitPct}%</span>
              <span>•</span>
              <span>{fuelLabel}</span>
              <span>•</span>
              <span>{trans}</span>
              <span>•</span>
              <span>{seats}</span>
            </div>
          </div>
        </div>
      );

      return (
        <div key={`${it.brand}-${it.model}-${i}`} className="w-full">
          <TiltedCard
            imageSrc={img}
            altText={title || "Mobil"}
            captionText={title}
            containerHeight="220px"
            containerWidth="100%"
            imageHeight="220px"
            imageWidth="100%"
            rotateAmplitude={5}
            scaleOnHover={1}
            showMobileWarning={false}
            showTooltip={false}
            displayOverlayContent={true}
            overlayContent={overlay}
          />
        </div>
      );
    });
  }, [data, labeler]);

  return (
    <>
      <StickyResultBar count={loading ? null : safeCount} theme={theme} onBackToForm={onBackToForm} />

      {error && (
        <div className="mt-6 mb-4 rounded-2xl border border-red-800 bg-red-950/40 p-3 text-red-200">
          Error: {error}
        </div>
      )}

      <div className="mt-6 mb-8">
        <h2 className="text-2xl font-bold mb-2">
          {loading
            ? "Menyiapkan Rekomendasi…"
            : data
              ? safeCount > 0
                ? `Hasil Rekomendasi Mobil Terbaik Untuk Anda ✨ (${safeCount})`
                : "Maaf, Tidak Ada Rekomendasi Mobil Ditemukan 😔"
              : "Hasil Rekomendasi"}
        </h2>
      </div>

      {loading ? (
        <div className="p-4 md:p-6 rounded-2xl border border-gray-800/50">
          <SkeletonGrid n={6} theme={theme} />
        </div>
      ) : data ? (
        safeCount > 0 ? (
          <div className={`rounded-2xl ${isDark ? "border border-gray-800/60" : "border border-gray-200"} p-3`}>
            <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
              {cards}
            </div>
          </div>
        ) : (
          <div className={`p-8 text-center rounded-2xl ${isDark ? "bg-[#121212] border border-gray-800/60" : "bg-white border border-gray-200"}`}>
            <p className="text-lg opacity-80">
              Coba sesuaikan budget atau hilangkan beberapa kriteria filter untuk mendapatkan hasil.
            </p>
            <div className="mt-4">
              <button
                onClick={onBackToForm}
                className={`${isDark ? "border border-gray-700 hover:bg-[#2a2a2a]" : "border border-gray-300 hover:bg-gray-100"} px-6 py-3 rounded-xl`}
              >
                Ubah Kriteria
              </button>
            </div>
          </div>
        )
      ) : (
        <div className={`p-8 text-center rounded-2xl ${isDark ? "bg-[#121212] border border-gray-800/60" : "bg-white border border-gray-200"}`}>
          <p className="text-neutral-400">Menunggu hasil...</p>
        </div>
      )}
    </>
  );
}
