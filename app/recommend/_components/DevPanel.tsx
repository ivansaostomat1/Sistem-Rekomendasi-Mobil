"use client";

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
  // Pastikan environment variable diset ke "1" di .env.local untuk melihat ini
  if (process.env.NEXT_PUBLIC_DEBUG !== "1") return null;

  const isDark = theme === "dark";

  return (
    <section className={`mt-12 pt-6 border-t ${
        isDark ? "border-teal-900/30" : "border-teal-100"
    }`}>
      <details className="group">
        <summary className={`cursor-pointer text-xs font-mono select-none transition-colors ${
            isDark 
            ? "text-teal-500 hover:text-teal-400 opacity-60 hover:opacity-100" 
            : "text-teal-600 hover:text-teal-800 opacity-70 hover:opacity-100"
        }`}>
          [ Developer Info ]
        </summary>
        
        <div className="mt-4 pl-2 border-l-2 border-teal-500/20">
          <DataStatus theme={theme} dataReady={dataReady} />
        </div>

        <div className={`mt-3 text-xs font-mono ${
            isDark ? "text-teal-600" : "text-teal-600/70"
        }`}>
          API Endpoint: 
          <code className={`ml-2 px-1.5 py-0.5 rounded ${
              isDark 
              ? "bg-teal-950/50 text-teal-300 border border-teal-900" 
              : "bg-teal-50 text-teal-700 border border-teal-100"
          }`}>
            {API_BASE}
          </code>
        </div>
      </details>
    </section>
  );
}