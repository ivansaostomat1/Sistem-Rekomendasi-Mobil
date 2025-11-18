"use client";

// app/recommend/_components/DevPanel.tsx
import React from "react";
import { DataStatus } from "@/components/ui/DataStatus";
import { API_BASE } from "@/constants";
import type { Theme } from "../_types/theme";

export function DevPanel({
  theme,
  dataReady,
}: {
  theme: Theme;
  dataReady: { specs: boolean; retail: boolean; wholesale: boolean };
}) {
  if (process.env.NEXT_PUBLIC_DEBUG !== "1") return null;

  return (
    <section className="mt-10">
      <details>
        <summary className="cursor-pointer text-xs opacity-70 select-none">
          Developer Info
        </summary>
        <div className="mt-3">
          <DataStatus theme={theme} dataReady={dataReady} />
        </div>
        <div className="mt-3 text-center text-xs text-neutral-500">
          API: <code>{API_BASE}</code>
        </div>
      </details>
    </section>
  );
}
