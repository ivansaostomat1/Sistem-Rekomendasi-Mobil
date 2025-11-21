"use client";

import React, { useState } from "react";
import ElasticSlider from "@/components/ui/ElasticSlider";
import { BUDGET_MIN, BUDGET_MAX, BUDGET_STEP } from "@/constants";
import { fmtIDR } from "@/utils";

export function BudgetField({
  isDark,
  value,
  onChange,
}: {
  isDark: boolean;
  value: number;
  onChange: (v: number) => void;
}) {
  const [touched, setTouched] = useState(false);

  const parseBudgetText = (s: string) => {
    const n = Number((s || "").replace(/[^\d]/g, ""));
    return Number.isFinite(n) ? n : 0;
  };

  // Clamp untuk INPUT: boleh di atas 2M (mis. batasi 9M sebagai pagar atas longgar)
  const clampInput = (v: number) => Math.min(Math.max(v, BUDGET_MIN), 10_000_000_000);

  // Clamp untuk SLIDER: TETAP mentok di BUDGET_MAX (2M)
  const clampSlider = (v: number) => Math.min(Math.max(v, BUDGET_MIN), BUDGET_MAX);

  const roundToStep = (v: number) => Math.round(v / BUDGET_STEP) * BUDGET_STEP;

  // Nilai yang dipakai slider selalu dijepit ke maksimal 2M,
  // meski nilai input sebenarnya bisa > 2M
  const sliderValue = Math.min(value, BUDGET_MAX);

  return (
    <div className="grid gap-3">
      <label className="font-semibold">Budget</label>
        <span id="budget-help" className="text-xs opacity-70">
          Rentang harga di form {fmtIDR(BUDGET_MIN)} – Rp 10.000.000.000
        </span>
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="text"
          inputMode="numeric"
          value={fmtIDR(touched ? value : value)}
          onChange={(e) => {
            setTouched(true);
            const raw = parseBudgetText(e.target.value);
            onChange(raw); // biarkan raw (bisa > 2M)
          }}
          onBlur={() => onChange(clampInput(roundToStep(value)))} // rapikan & tetap boleh > 2M
          placeholder="cth: 150.000.000"
          className={`${isDark ? "bg-[#0a0a0a] border border-gray-700 text-gray-100" : "bg-white border border-gray-300"} w-60 px-3 py-2 rounded-xl`}
          aria-describedby="budget-help"
        />
       
      </div>
        <span id="budget-help" className="text-xs mt-5 opacity-70">
          Rentang harga di slider {fmtIDR(BUDGET_MIN)} – {fmtIDR(BUDGET_MAX)}
        </span> 
      <ElasticSlider
        value={sliderValue}                // ← slider mentok 2M
        min={BUDGET_MIN}
        max={BUDGET_MAX}
        step={BUDGET_STEP}
        theme={isDark ? "dark" : "light"}
        ariaLabel="Budget"
        onChange={(v) => onChange(clampSlider(roundToStep(v)))} // slider selalu ≤ 2M
        className="w-full"
      />
        
      <div className="flex justify-between text-xs opacity-70 -mt-1">
        <span>{fmtIDR(BUDGET_MIN)}</span>
        <span>{fmtIDR(BUDGET_MAX)}</span>
      </div>
      
    </div>
  );
}
