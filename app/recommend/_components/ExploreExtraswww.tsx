"use client";

// app/recommend/_components/ExploreExtras.tsx
import React from "react";
import { BrandGrid } from "@/components/ui/BrandGrid";
import { SegmentCarousel } from "@/components/ui/SegmentCarousel";
import type { Theme } from "../_types/theme";

export function ExploreExtras({ theme }: { theme: Theme }) {
  return (
    <section className="mt-12">
      <details>
        <summary className="cursor-pointer text-sm opacity-80 select-none">
          Jelajahi brand & segmen (opsional)
        </summary>
        <div className="mt-6">
          <BrandGrid theme={theme} />
        </div>
        <div className="mt-8">
          <SegmentCarousel theme={theme} />
        </div>
      </details>
    </section>
  );
}
