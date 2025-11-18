"use client";

import React, { useEffect, useState } from "react";

export function TransmissionBrandRow({
  isDark,
  transChoice,
  setTransChoice,
  brand,
  setBrand,
  brands,
}: {
  isDark: boolean;
  transChoice: "Matic" | "Manual" | "";
  setTransChoice: (v: "Matic" | "Manual" | "" ) => void;
  brand: string;
  setBrand: (v: string) => void;
  brands: string[];
}) {
  const [suggestions, setSuggestions] = useState<string[]>([]);

  useEffect(() => {
    if (!brand) {
      setSuggestions([]);
      return;
    }
    const pool = brands?.length
      ? brands
      : ["Toyota", "Honda", "Mitsubishi", "Suzuki", "Hyundai", "BMW", "Mercedes-Benz"];
    const filtered = pool.filter((b) => b.toLowerCase().startsWith(brand.toLowerCase()));
    setSuggestions(filtered.slice(0, 6));
  }, [brand, brands]);

  return (
    <div className="grid md:grid-cols-3 gap-4">
      {/* Transmisi */}
      <label className="flex flex-col gap-1">
        <span className="text-l font-semibold">Transmisi</span>
        <select
          value={transChoice}
          onChange={(e) => setTransChoice((e.target.value as "Matic" | "Manual") || "")}
          className={`${isDark ? "bg-[#0a0a0a] border border-gray-700 text-gray-100" : "bg-white border border-gray-300"} rounded-xl px-3 py-2`}
        >
          <option value=""> Pilih </option>
          <option value="Matic">Matic</option>
          <option value="Manual">Manual</option>
        </select>
      </label>

      {/* Brand autosuggest */}
      <div className="relative md:col-span-2">
        <label className="block mb-1 font-semibold text-l">Brand (opsional)</label>
        <input
          type="text"
          value={brand}
          onChange={(e) => setBrand(e.target.value)}
          placeholder="Ketik nama brand.."
          className={`${isDark ? "bg-[#0a0a0a] border border-gray-700 text-gray-100" : "bg-white border border-gray-300"} w-full p-3 rounded-xl`}
          aria-autocomplete="list"
          aria-expanded={suggestions.length > 0}
        />
        {suggestions.length > 0 && (
          <ul
            className={`absolute z-10 w-full mt-1 rounded-xl border shadow-lg max-h-40 overflow-y-auto ${
              isDark ? "bg-[#1a1a1a] border-gray-700 text-gray-100" : "bg-white border-gray-300"
            }`}
            role="listbox"
          >
            {suggestions.map((s, i) => (
              <li
                key={i}
                onClick={() => {
                  setBrand(s);
                  setSuggestions([]);
                }}
                className="px-3 py-2 cursor-pointer hover:bg-orange-500 hover:text-white transition"
                role="option"
              >
                {s}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
