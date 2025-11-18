"use client";

import React, { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Theme, RecommendResponse, MetaResponse } from "@/types/index";
import { API_BASE, BUDGET_MIN } from "@/constants"; // ← tambahkan BUDGET_MIN
import { BudgetField } from "./BudgetField";
import { NeedsPicker } from "./NeedsPicker";
import { FuelPicker } from "./FuelPicker";
import { TransmissionBrandRow } from "./TransmissionBrandRow";

const DEFAULT_TOPN = 18;
const DEFAULT_BUDGET = BUDGET_MIN;

// selalu kembalikan number
const pickBudget = (m?: MetaResponse | null, fallback = DEFAULT_BUDGET) => {
  const bd = m?.budgetDefault;
  return typeof bd === "number" && Number.isFinite(bd) ? bd : fallback;
};

interface RecommendationFormProps {
  theme: Theme;
  loading: boolean;
  error: string | null;
  data: RecommendResponse | null;
  meta: MetaResponse | null;
  isSearched: boolean;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setData: (data: RecommendResponse | null) => void;
  setIsSearched: (searched: boolean) => void;
}

type FuelOption = { code: string; label: string };

type FiltersState = {
  trans_choice?: "Matic" | "Manual";
  fuels?: string[]; // ['g','d','h','p','e']
};

type FormState = {
  budget: number;
  topn: number;
  filters: FiltersState | Record<string, never>;
};

export function RecommendationForm({
  theme,
  loading,
  error: _error,
  data: _data,
  meta,
  isSearched: _isSearched,
  setLoading,
  setError,
  setData,
  setIsSearched,
}: RecommendationFormProps) {
  const isDark = theme === "dark";
  const sectionVariant = { hidden: { opacity: 0, y: 30 }, visible: { opacity: 1, y: 0 } };

  // ---------------- State & Defaults ----------------
  const [form, setForm] = useState<FormState>({
    budget: pickBudget(meta),             // ← selalu number
    topn: DEFAULT_TOPN,
    filters: { fuels: [] },
  });
  const [fuelsTouched, setFuelsTouched] = useState(false);
  const [brand, setBrand] = useState("");
  const [selectedNeeds, setSelectedNeeds] = useState<string[]>([]);

  // ---------------- Fuel Options (meta → bersih & urut) ----------------
  const fuelOptions: FuelOption[] = useMemo(() => {
    const fallback: FuelOption[] = [
      { code: "g", label: "Bensin" },
      { code: "d", label: "Diesel" },
      { code: "h", label: "Hybrid" },
      { code: "p", label: "PHEV" },
      { code: "e", label: "BEV" },
    ];
    if (!meta?.fuels || !Array.isArray(meta.fuels) || meta.fuels.length === 0) return fallback;

    const first = meta.fuels[0] as any;
    if (typeof first === "object" && "code" in first && "label" in first) {
      const allow = new Set(["g", "d", "h", "p", "e"]);
      return (meta.fuels as any[])
        .map((f) => ({ code: String(f.code).toLowerCase(), label: String(f.label) }))
        .filter((f) => allow.has(f.code));
    }
    const toCode = (s: string): FuelOption => {
      const v = (s || "").toLowerCase();
      if (["g", "bensin", "gasoline", "petrol"].includes(v)) return { code: "g", label: "Bensin" };
      if (["d", "diesel", "dsl", "solar"].includes(v)) return { code: "d", label: "Diesel" };
      if (["p", "phev", "plug-in", "plugin", "plug in", "plug in hybrid"].includes(v)) return { code: "p", label: "PHEV" };
      if (["h", "hybrid", "hev"].includes(v)) return { code: "h", label: "Hybrid" };
      if (["e", "bev", "ev", "electric", "full electric"].includes(v)) return { code: "e", label: "BEV" };
      return { code: "g", label: "Bensin" };
    };
    const uniq = new Map<string, FuelOption>();
    (meta.fuels as any[]).forEach((raw) => {
      const opt = toCode(String(raw));
      if (!uniq.has(opt.code)) uniq.set(opt.code, opt);
    });
    return Array.from(uniq.values());
  }, [meta]);

  const FUEL_ORDER = ["g", "d", "h", "p", "e"] as const;
  const allFuelCodes = useMemo(
    () =>
      fuelOptions
        .map((f) => f.code.toLowerCase())
        .filter((c) => FUEL_ORDER.includes(c as any))
        .sort((a, b) => FUEL_ORDER.indexOf(a as any) - FUEL_ORDER.indexOf(b as any)),
    [fuelOptions]
  );

  // Default nyalakan semua fuels saat options tersedia
  useEffect(() => {
    if (!fuelsTouched && allFuelCodes.length > 0) {
      setForm((s) => ({ ...s, filters: { ...(s.filters as FiltersState), fuels: [...allFuelCodes] } }));
    }
  }, [allFuelCodes, fuelsTouched]);

  // Budget default dari meta (opsional—hanya kalau valid number)
  useEffect(() => {
    if (typeof meta?.budgetDefault === "number" && Number.isFinite(meta.budgetDefault)) {
      setForm((s) => ({ ...s, budget: meta.budgetDefault as number }));
    }
  }, [meta?.budgetDefault]);

  // ---------------- Handlers ----------------
  const toggleNeed = (key: string) =>
    setSelectedNeeds((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));

  const toggleFuel = (code: string) => {
    setFuelsTouched(true);
    setForm((s) => {
      const cur = new Set((s.filters as FiltersState).fuels || []);
      if (cur.has(code)) cur.delete(code);
      else cur.add(code);
      return { ...s, filters: { ...(s.filters as FiltersState), fuels: Array.from(cur) } };
    });
  };

  const allSelected = useMemo(() => {
    const cur = new Set((form.filters as FiltersState).fuels || []);
    return allFuelCodes.length > 0 && allFuelCodes.every((c) => cur.has(c));
  }, [form.filters, allFuelCodes]);

  const handleToggleAllFuels = () => {
    setFuelsTouched(true);
    setForm((s) => {
      const cur = new Set((s.filters as FiltersState).fuels || []);
      const isAll = allFuelCodes.length > 0 && allFuelCodes.every((c) => cur.has(c));
      return { ...s, filters: { ...(s.filters as FiltersState), fuels: isAll ? [] : [...allFuelCodes] } };
    });
  };

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setData(null);
    setLoading(true);

    try {
      // kirim undefined jika semua terpilih (anggap tidak membatasi)
      const selectedFuels = ((form.filters as FiltersState).fuels || []) as string[];
      const fuelsForApi =
        allFuelCodes.length > 0 && selectedFuels.length === allFuelCodes.length
          ? undefined
          : selectedFuels.length
          ? selectedFuels
          : undefined;

      const body = {
        budget: form.budget,
        topn: form.topn,
        needs: selectedNeeds,
        filters: {
          trans_choice: (form.filters as FiltersState).trans_choice || undefined,
          brand: brand || undefined,
          fuels: fuelsForApi,
        },
      };

      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 20000);
      const res = await fetch(`${API_BASE}/recommendations`, {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json", "Cache-Control": "no-cache" },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
      clearTimeout(t);

      if (!res.ok) throw new Error((await res.text()) || `HTTP ${res.status}`);

      const j = (await res.json()) as RecommendResponse;
      setData(j);
      setIsSearched(true);
    } catch (err: any) {
      if (err?.name === "AbortError") setError("Permintaan timeout. Coba lagi atau perkecil filter.");
      else setError(err?.message || "Terjadi kesalahan");
    } finally {
      setLoading(false);
    }
  }

  const handleReset = () => {
    setForm({ budget: pickBudget(meta), topn: DEFAULT_TOPN, filters: { fuels: [] } }); // ← selalu number
    setFuelsTouched(false);
    setSelectedNeeds([]);
    setData(null);
    setError(null);
    setIsSearched(false);
    setBrand("");
  };

  // ---------------- Render ----------------
  return (
    <motion.section
      initial="hidden"
      animate="visible"
      variants={sectionVariant}
      className={`mb-16 rounded-3xl p-8 shadow-xl ${isDark ? "bg-[#1a1a1a] shadow-black/30" : "bg-white"}`}
    >
      <h2 className="text-xl font-bold mb-6">Atur Kriteria Mobil Impianmu</h2>

      <form id="rec-form-form" onSubmit={handleSubmit} className="grid gap-8">
        <BudgetField isDark={isDark} value={form.budget} onChange={(v) => setForm((s) => ({ ...s, budget: v }))} />

        <NeedsPicker
          isDark={isDark}
          needs={(meta?.needs || []) as any[]}
          selected={selectedNeeds}
          onToggle={toggleNeed}
        />

        <FuelPicker
          isDark={isDark}
          fuelOptions={fuelOptions}
          selectedFuels={(form.filters as FiltersState).fuels || []}
          allSelected={allSelected}
          onToggleFuel={toggleFuel}
          onToggleAll={handleToggleAllFuels}
        />

        <TransmissionBrandRow
          isDark={isDark}
          transChoice={(form.filters as FiltersState).trans_choice || ""}
          setTransChoice={(v) =>
            setForm((s) => ({ ...s, filters: { ...(s.filters as FiltersState), trans_choice: v || undefined } }))
          }
          brand={brand}
          setBrand={setBrand}
          brands={meta?.brands || []}
        />

        <div className="flex gap-4">
          <button
            type="submit"
            disabled={loading}
            className="bg-gradient-to-r from-amber-400 to-orange-600 px-6 py-3 rounded-xl text-white font-semibold hover:opacity-90 disabled:opacity-60"
          >
            {loading ? "Menghitung…" : "Tampilkan Rekomendasi"}
          </button>

          <button
            type="button"
            onClick={handleReset}
            className={`${isDark ? "border border-gray-700 hover:bg-[#2a2a2a]" : "border border-gray-300 hover:bg-gray-100"} px-6 py-3 rounded-xl`}
          >
            Reset Filter
          </button>
        </div>
      </form>
    </motion.section>
  );
}
