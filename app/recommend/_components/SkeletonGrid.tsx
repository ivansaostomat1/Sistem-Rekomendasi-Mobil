"use client";

// app/recommend/_components/SkeletonGrid.tsx
import type { Theme } from "../_types/theme";

export function SkeletonGrid({ n = 6, theme }: { n?: number; theme: Theme }) {
  return (
    <div className="grid lg:grid-cols-3 md:grid-cols-2 gap-8">
      {Array.from({ length: n }).map((_, i) => (
        <div
          key={i}
          className={`rounded-2xl overflow-hidden border animate-pulse ${
            theme === "dark" ? "bg-[#1a1a1a] border-gray-800" : "bg-red border-gray-200"
          }`}
        >
          <div className="relative w-full h-40" />
          <div className="p-5">
            <div className="h-4 w-24 opacity-30 mb-2" />
            <div className="h-5 w-40 opacity-40 mb-3" />
            <div className="h-6 w-32 opacity-30 rounded-full" />
          </div>
        </div>
      ))}
    </div>
  );
}
