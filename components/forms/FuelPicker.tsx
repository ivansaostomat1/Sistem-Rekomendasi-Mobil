"use client";

import React, { useMemo, useState } from "react";
import GlassIcons from "@/components/ui/GlassIcons";
import { CarIcon, EvChargerIcon, FuelIcon as FuelPumpIcon } from "lucide-react";

/* Ikon inline — persis seperti yang dipakai di form */
const BoltIcon = () => (
  <svg viewBox="0 0 24 24" width="1em" height="1em" fill="currentColor">
    <path d="M13 2L3 14h7l-1 8 10-12h-7l1-8z" />
  </svg>
);

const BatteryIcon = () => (
  <svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" strokeWidth="2">
    <rect x="2" y="7" width="18" height="10" rx="2" />
    <path d="M22 10v4" />
  </svg>
);

type FuelOption = { code: string; label: string };

// ===============================
// Komponen FuelPicker (presentasi)
// ===============================
export function FuelPicker({
  isDark,
  fuelOptions,
  selectedFuels,
  allSelected,
  onToggleFuel,
  onToggleAll,
}: {
  isDark: boolean;
  fuelOptions: FuelOption[];
  selectedFuels: string[];
  allSelected: boolean;
  onToggleFuel: (code: string) => void;
  onToggleAll: () => void;
}) {
  const FUEL_ORDER = ["g", "d", "h", "p", "e"] as const;

  const fuelPalette: Record<
    string,
    { label: string; gradient: string; icon: React.ReactElement }
  > = {
    g: {
      label: "Bensin",
      gradient: "linear-gradient(145deg,#ffdd03,#0b0900)",
      icon: <FuelPumpIcon />,
    },
    d: {
      label: "Diesel",
      gradient: "linear-gradient(145deg,#cf1204,#0b0600)",
      icon: <CarIcon />,
    },
    h: {
      label: "Hybrid",
      gradient: "linear-gradient(145deg,#04d465,#00140e)",
      icon: <BoltIcon />,
    },
    p: {
      label: "PHEV",
      gradient: "linear-gradient(145deg,#00f2ff,#001210)",
      icon: <EvChargerIcon />,
    },
    e: {
      label: "BEV",
      gradient: "linear-gradient(145deg,#0008ed,#00101f)",
      icon: <BatteryIcon />,
    },
  };

  // susun items untuk GlassIcons
  const items = useMemo(() => {
    const codes = fuelOptions
      .map((f) => f.code.toLowerCase())
      .filter((c) => FUEL_ORDER.includes(c as any))
      .sort(
        (a, b) =>
          FUEL_ORDER.indexOf(a as (typeof FUEL_ORDER)[number]) -
          FUEL_ORDER.indexOf(b as (typeof FUEL_ORDER)[number]),
      );

    const selected = new Set(selectedFuels);
    return codes.map((code) => {
      const p = fuelPalette[code] || fuelPalette.g;
      return {
        id: code,
        icon: p.icon,
        color: p.gradient,
        label: p.label,
        selected: selected.has(code),
        customClass: selected.has(code)
          ? "opacity-100"
          : "opacity-95 hover:opacity-100",
      };
    });
  }, [fuelOptions, selectedFuels]);

  return (
    <div className="grid gap-2">
      <div className="flex items-center justify-between">
        <label className="text-l font-bold">Bahan Bakar</label>

        <button
          type="button"
          onClick={onToggleAll}
          aria-pressed={allSelected}
          className={`px-4 py-2 rounded-xl text-sm font-semibold transition
            ${
              allSelected
                ? "bg-orange-500 text-white shadow-orange-500/40 shadow"
                : isDark
                ? "border border-gray-700 hover:bg-[#2a2a2a]"
                : "border border-gray-300 hover:bg-gray-100"
            }`}
          title="Pilih/Batalkan semua bahan bakar"
        >
          {allSelected ? "Semua ✓" : "Semua"}
        </button>
      </div>

      <GlassIcons
        items={items}
        className="mt-4"
        onItemClick={(it) => onToggleFuel(String(it.id))}
      />
    </div>
  );
}

// =======================================================
// Contoh pemakaian + validasi tanpa reload & tanpa reset
// =======================================================
// Opsional: kamu bisa merge logic ini ke form rekomendasi utamamu.
const ALL_FUEL_OPTIONS: FuelOption[] = [
  { code: "g", label: "Bensin" },
  { code: "d", label: "Diesel" },
  { code: "h", label: "Hybrid" },
  { code: "p", label: "PHEV" },
  { code: "e", label: "BEV" },
];

export function FuelPickerWithValidation({ isDark }: { isDark: boolean }) {
  // default OFF semua
  const [selectedFuels, setSelectedFuels] = useState<string[]>([]);
  const [allSelected, setAllSelected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleToggleFuel = (code: string) => {
    setSelectedFuels((prev) => {
      const c = code.toLowerCase();
      const exists = prev.includes(c);
      const next = exists ? prev.filter((x) => x !== c) : [...prev, c];

      setAllSelected(next.length === ALL_FUEL_OPTIONS.length);
      return next;
    });
    setError(null);
  };

  const handleToggleAll = () => {
    setSelectedFuels((prev) => {
      if (prev.length === ALL_FUEL_OPTIONS.length) {
        // sebelumnya semua -> clear
        setAllSelected(false);
        return [];
      }
      // pilih semua
      setAllSelected(true);
      return ALL_FUEL_OPTIONS.map((f) => f.code);
    });
    setError(null);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault(); // penting: cegah reload + reset form

    if (selectedFuels.length === 0) {
      // boleh ganti ke window.alert kalau mau popup
      setError("Pilih minimal satu jenis bahan bakar.");
      // window.alert("Pilih minimal satu jenis bahan bakar.");
      return;
    }

    setError(null);

    // di sini nanti kamu panggil API /recommendations
    // dan kirim selectedFuels sebagai spec_filters.fuels
    // contoh:
    // fetch("/api/recommendations", { body: JSON.stringify({ spec_filters: { fuels: selectedFuels } }) })
    console.log("Fuel terpilih:", selectedFuels);
  };

  return (
    <form onSubmit={handleSubmit} className="grid gap-3">
      <FuelPicker
        isDark={isDark}
        fuelOptions={ALL_FUEL_OPTIONS}
        selectedFuels={selectedFuels}
        allSelected={allSelected}
        onToggleFuel={handleToggleFuel}
        onToggleAll={handleToggleAll}
      />

      {error && <p className="text-sm text-red-500">{error}</p>}

      <button
        type="submit"
        className="mt-2 px-4 py-2 rounded-xl bg-orange-500 text-white font-semibold"
      >
        Rekomendasi
      </button>
    </form>
  );
}
