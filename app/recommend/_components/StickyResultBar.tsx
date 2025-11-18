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
  return (
    <div
      className={`sticky top-0 z-20 backdrop-blur supports-[backdrop-filter]:bg-opacity-80 ${
        theme === "dark" ? "bg-[#0a0a0a]" : "bg-gray-50"
      }`}
      role="region"
      aria-label="Ringkasan hasil"
    >
      <div className="mx-auto max-w-6xl px-10 py-3 flex items-center justify-between">
        <div className="text-sm opacity-80" aria-live="polite" role="status">
          {count === null
            ? "Menyiapkan hasil…"
            : count > 0
              ? `Hasil ditemukan: ${count}`
              : "Tidak ada hasil yang cocok"}
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onBackToForm}
            className={`border px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
              theme === "dark"
                ? "border-gray-700 bg-[#1a1a1a] hover:bg-[#111]"
                : "border-gray-300 bg-white hover:bg-gray-100"
            }`}
          >
            Ubah Kriteria
          </button>
        </div>
      </div>
    </div>
  );
}
