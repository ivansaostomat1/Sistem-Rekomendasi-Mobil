// index.tsx

"use client";

import React, { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Theme, RecommendResponse, MetaResponse } from "@/types/index";
import { API_BASE, BUDGET_MIN } from "@/constants";
import { BudgetField } from "./BudgetField";
import { NeedsPicker } from "./NeedsPicker";
import { FuelPicker } from "./FuelPicker";
import { TransmissionBrandRow } from "./TransmissionBrandRow";
import { AlertCircle } from "lucide-react"; // untuk alert kebutuhan & fuel

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
  const sectionVariant = {
    hidden: { opacity: 0, y: 30 },
    visible: { opacity: 1, y: 0 },
  };

  // ---------------- State & Defaults ----------------
  const [form, setForm] = useState<FormState>({
    budget: pickBudget(meta),
    topn: DEFAULT_TOPN,
    filters: { fuels: [] }, // default: semua OFF
  });
  const [brand, setBrand] = useState("");
  const [selectedNeeds, setSelectedNeeds] = useState<string[]>([]);
  const [fuelError, setFuelError] = useState<string | null>(null);
  const [needsError, setNeedsError] = useState<string | null>(null); // <- alert kebutuhan

  // ---------------- Fuel Options (meta → bersih & urut) ----------------
  const fuelOptions: FuelOption[] = useMemo(() => {
    const fallback: FuelOption[] = [
      { code: "g", label: "Bensin" },
      { code: "d", label: "Diesel" },
      { code: "h", label: "Hybrid" },
      { code: "p", label: "PHEV" },
      { code: "e", label: "BEV" },
    ];
    if (!meta?.fuels || !Array.isArray(meta.fuels) || meta.fuels.length === 0)
      return fallback;

    const first = meta.fuels[0] as any;
    // kalau backend sudah kirim {code,label}
    if (typeof first === "object" && "code" in first && "label" in first) {
      const allow = new Set(["g", "d", "h", "p", "e"]);
      return (meta.fuels as any[])
        .map((f) => ({
          code: String(f.code).toLowerCase(),
          label: String(f.label),
        }))
        .filter((f) => allow.has(f.code));
    }

    // kalau backend kirim string bebas
    const toCode = (s: string): FuelOption => {
      const v = (s || "").toLowerCase();
      if (["g", "bensin", "gasoline", "petrol"].includes(v))
        return { code: "g", label: "Bensin" };
      if (["d", "diesel", "dsl", "solar"].includes(v))
        return { code: "d", label: "Diesel" };
      if (
        ["p", "phev", "plug-in", "plugin", "plug in", "plug in hybrid"].includes(
          v,
        )
      )
        return { code: "p", label: "PHEV" };
      if (["h", "hybrid", "hev"].includes(v))
        return { code: "h", label: "Hybrid" };
      if (["e", "bev", "ev", "electric", "full electric"].includes(v))
        return { code: "e", label: "BEV" };
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
        .sort(
          (a, b) =>
            FUEL_ORDER.indexOf(a as (typeof FUEL_ORDER)[number]) -
            FUEL_ORDER.indexOf(b as (typeof FUEL_ORDER)[number]),
        ),
    [fuelOptions],
  );

  // Budget default dari meta (opsional—hanya kalau valid number)
  useEffect(() => {
    if (
      typeof meta?.budgetDefault === "number" &&
      Number.isFinite(meta.budgetDefault)
    ) {
      setForm((s) => ({
        ...s,
        budget: meta.budgetDefault as number,
      }));
    }
  }, [meta?.budgetDefault]);

  // ---------------- Handlers ----------------
  const toggleNeed = (key: string) => {
    // begitu user mulai pilih kebutuhan, error di-clear
    setNeedsError(null);
    setSelectedNeeds((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  };

  const toggleFuel = (code: string) => {
    setFuelError(null); // bersihkan alert ketika user ganti pilihan
    setForm((s) => {
      const cur = new Set((s.filters as FiltersState).fuels || []);
      if (cur.has(code)) cur.delete(code);
      else cur.add(code);
      return {
        ...s,
        filters: {
          ...(s.filters as FiltersState),
          fuels: Array.from(cur),
        },
      };
    });
  };

  const allSelected = useMemo(() => {
    const cur = new Set((form.filters as FiltersState).fuels || []);
    return allFuelCodes.length > 0 && allFuelCodes.every((c) => cur.has(c));
  }, [form.filters, allFuelCodes]);

  const handleToggleAllFuels = () => {
    setFuelError(null); // bersihkan alert juga saat klik "Semua"
    setForm((s) => {
      const cur = new Set((s.filters as FiltersState).fuels || []);
      const isAll =
        allFuelCodes.length > 0 && allFuelCodes.every((c) => cur.has(c));

      return {
        ...s,
        filters: {
          ...(s.filters as FiltersState),
          fuels: isAll ? [] : [...allFuelCodes],
        },
      };
    });
  };

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault(); // cegah reload & reset form

    setError(null);
    setData(null);

    const selectedFuels = ((form.filters as FiltersState).fuels ||
      []) as string[];

    // VALIDASI: minimal 1 kebutuhan & minimal 1 fuel
    const hasNeeds = selectedNeeds.length > 0;
    if (!hasNeeds) {
      setNeedsError("Pilih minimal satu kebutuhan terlebih dahulu.");
    }

    if (selectedFuels.length === 0) {
      setFuelError("Pilih minimal satu jenis bahan bakar terlebih dahulu.");
    }

    // kalau salah satu belum diisi, hentikan submit
    if (!hasNeeds || selectedFuels.length === 0) {
      return;
    }

    setLoading(true);

    try {
      const body = {
        budget: form.budget,
        topn: form.topn,
        needs: selectedNeeds,
        filters: {
          trans_choice:
            (form.filters as FiltersState).trans_choice || undefined,
          brand: brand || undefined,
          fuels: selectedFuels, // misal ["e"] kalau cuma BEV
        },
      };

      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 20000);

      const res = await fetch(`${API_BASE}/recommendations`, {
        method: "POST",
        cache: "no-store",
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "no-cache",
        },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });

      clearTimeout(t);

      if (!res.ok) throw new Error((await res.text()) || `HTTP ${res.status}`);

      const j = (await res.json()) as RecommendResponse;
      setData(j);
      setIsSearched(true);
    } catch (err: any) {
      if (err?.name === "AbortError") {
        setError("Permintaan timeout. Coba lagi atau perkecil filter.");
      } else {
        setError(err?.message || "Terjadi kesalahan");
      }
    } finally {
      setLoading(false);
    }
  }

  const handleReset = () => {
    setForm({
      budget: pickBudget(meta),
      topn: DEFAULT_TOPN,
      filters: { fuels: [] }, // reset: semua OFF
    });
    setSelectedNeeds([]);
    setData(null);
    setError(null);
    setIsSearched(false);
    setBrand("");
    setFuelError(null);
    setNeedsError(null); // sekaligus hilangkan alert kebutuhan
  };

  // ---------------- Render ----------------
  return (
    <motion.section
      initial="hidden"
      animate="visible"
      variants={sectionVariant}
      className={`mb-16 rounded-3xl p-8 shadow-xl ${
        isDark ? "bg-[#1a1a1a] shadow-black/30" : "bg-white"
      }`}
    >
      <h2 className="text-xl font-bold mb-6">
        Atur Kriteria Mobil Impianmu
      </h2>

      <form
        id="rec-form-form"
        onSubmit={handleSubmit}
        className="grid gap-8"
      >
        <BudgetField
          isDark={isDark}
          value={form.budget}
          onChange={(v) =>
            setForm((s) => ({
              ...s,
              budget: v,
            }))
          }
        />

        <NeedsPicker
          isDark={isDark}
          needs={(meta?.needs || []) as any[]}
          selected={selectedNeeds}
          onToggle={toggleNeed}
        />

        {needsError && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-1 flex items-center gap-2 rounded-xl border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-500"
          >
            <AlertCircle className="h-4 w-4" />
            <span>{needsError}</span>
          </motion.div>
        )}

        <FuelPicker
          isDark={isDark}
          fuelOptions={fuelOptions}
          selectedFuels={(form.filters as FiltersState).fuels || []}
          allSelected={allSelected}
          onToggleFuel={toggleFuel}
          onToggleAll={handleToggleAllFuels}
        />

        {fuelError && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-1 flex items-center gap-2 rounded-xl border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-500"
          >
            <AlertCircle className="h-4 w-4" />
            <span>{fuelError}</span>
          </motion.div>
        )}

        <TransmissionBrandRow
          isDark={isDark}
          transChoice={
            (form.filters as FiltersState).trans_choice || ""
          }
          setTransChoice={(v) =>
            setForm((s) => ({
              ...s,
              filters: {
                ...(s.filters as FiltersState),
                trans_choice: v || undefined,
              },
            }))
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
            className={`${
              isDark
                ? "border border-gray-700 hover:bg-[#2a2a2a]"
                : "border border-gray-300 hover:bg-gray-100"
            } px-6 py-3 rounded-xl`}
          >
            Reset Filter
          </button>
        </div>
      </form>
    </motion.section>
  );
}
