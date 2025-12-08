"use client";

import React from "react";
import type { Theme } from "@/types";

export function StickyResultBar({
  count,
  theme,
  onBackToForm,
}: {
  count: number | null;
  theme: Theme;
  onBackToForm: () => void;
}) {
  const isDark = theme === "dark";

  return (
    <div
      className={`sticky top-0 z-20 backdrop-blur supports-[backdrop-filter]:bg-opacity-80 
      ${isDark 
          // DARK MODE: Background Deep Slate/Teal
          ? "bg-black/80 border-b border-teal-900/80" 
          // LIGHT MODE: Background Soft Cyan/Teal
          : "bg-cyan-50/80 border-b border-teal-100/80"
      }`}
      role="region"
      aria-label="Ringkasan hasil"
    >
      <div className="mx-auto max-w-6xl px-10 py-3 flex items-center justify-between">
        {/* Teks Status */}
        <div 
          className={`text-m font-semibold opacity-80 ${isDark ? "text-teal-200" : "text-teal-1000"}`} 
          aria-live="polite" 
          role="status"
        >
          {count === null
            ? "Menyiapkan hasil…"
            : count > 0
              ? `Hasil ditemukan: ${count}`
              : "Tidak ada hasil yang cocok"}
        </div>
        
        {/* Tombol Ubah Kriteria */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onBackToForm}
            // TEMA BARU: Border Teal, Background Hovering
            className={`border px-3 py-1.5 rounded-lg text-xs font-bold transition ${
              isDark
                ? "border-teal-700 bg-[#111111] text-teal-100 hover:bg-[#1a1a1a]"
                : "border-teal-200 bg-white text-teal-800 hover:bg-teal-50"
            }`}
          >
            Ubah Kriteria
          </button>
        </div>
      </div>
    </div>
  );
}