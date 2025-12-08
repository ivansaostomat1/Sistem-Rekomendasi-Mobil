"use client";

// app/recommend/_components/SkeletonGrid.tsx
import type { Theme } from "../_types/theme";

export function SkeletonGrid({ n = 6, theme }: { n?: number; theme: Theme }) {
  const isDark = theme === "dark";

  return (
    <div className="grid lg:grid-cols-3 md:grid-cols-2 gap-8">
      {Array.from({ length: n }).map((_, i) => (
        <div
          key={i}
          className={`rounded-2xl overflow-hidden border animate-pulse ${
            isDark 
              ? "bg-[#0a1014] border-teal-900/30" // Dark: Deep Teal Background
              : "bg-white border-teal-100"        // Light: Clean White dengan border Teal
          }`}
        >
          {/* Image Area Placeholder */}
          <div className={`relative w-full h-[220px] ${
              isDark ? "bg-teal-900/20" : "bg-teal-50"
          }`} />

          {/* Text Content Placeholder */}
          <div className="p-5 space-y-3">
            {/* Brand Label */}
            <div className={`h-3 w-20 rounded-md ${
                isDark ? "bg-teal-800/30" : "bg-teal-100"
            }`} />
            
            {/* Model Name (Lebih besar) */}
            <div className={`h-6 w-3/4 rounded-md ${
                isDark ? "bg-teal-800/50" : "bg-teal-200/50"
            }`} />

            {/* Price Tag */}
            <div className={`h-4 w-1/2 rounded-md ${
                isDark ? "bg-teal-800/30" : "bg-teal-100"
            }`} />
            
            {/* Feature Chips */}
            <div className="flex gap-2 pt-2">
                <div className={`h-5 w-12 rounded-full ${
                    isDark ? "bg-teal-800/30" : "bg-teal-100"
                }`} />
                <div className={`h-5 w-12 rounded-full ${
                    isDark ? "bg-teal-800/30" : "bg-teal-100"
                }`} />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}