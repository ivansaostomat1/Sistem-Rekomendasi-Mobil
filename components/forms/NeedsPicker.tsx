"use client";

import React, { useMemo, useCallback } from "react";

type Need = { key: string; label: string; image: string };

const CANON: Record<string, string> = {
  // long trip
  "perjalanan_jauh": "perjalanan_jauh",
  "long trip": "perjalanan_jauh",
  "long_trip": "perjalanan_jauh",
  "longtrip": "perjalanan_jauh",
  "trip jauh": "perjalanan_jauh",

  // short trip / city
  "perkotaan": "perkotaan",
  "short trip": "perkotaan",
  "short_trip": "perkotaan",
  "shorttrip": "perkotaan",
  "city": "perkotaan",
  "urban": "perkotaan",

  // fun to drive
  "fun": "fun",
  "fun to drive": "fun",
  "fun_to_drive": "fun",
  "fun2drive": "fun",
  "sporty": "fun",

  // offroad
  "offroad": "offroad",
  "off road": "offroad",
  "off_road": "offroad",

  // niaga
  "niaga": "niaga",
  "usaha": "niaga",
  "commercial": "niaga",

  // keluarga
  "keluarga": "keluarga",
  "family": "keluarga",
};

function canonKey(k: string): string {
  const s = (k || "").toString().trim().toLowerCase();
  return CANON[s] ?? s; // fallback: pakai s apa adanya
}

export function NeedsPicker({
  isDark,
  needs,
  selected,
  onToggle,
  maxSelect = 3,
  onBlocked,
}: {
  isDark: boolean;
  needs: Need[];
  selected: string[];
  onToggle: (canonicalKey: string) => void; // sekarang kirimkan key KANONIK
  maxSelect?: number;
  onBlocked?: (reason: string, key: string) => void;
}) {
  // peta konflik berbasis KEY KANONIK (selaras backend)
  const MU_EX: Record<string, string[]> = useMemo(
    () => ({
      fun: ["offroad", "niaga"],
      offroad: ["fun"],
      niaga: ["fun"],
      perjalanan_jauh: ["perkotaan"],
      perkotaan: ["perjalanan_jauh"],
    }),
    []
  );

  const selectedCanon = useMemo(
    () => new Set((selected || []).map(canonKey)),
    [selected]
  );

  const labelOf = useCallback(
    (k: string) => needs.find((n) => canonKey(n.key) === k)?.label || k,
    [needs]
  );

  const disableReasonOf = useCallback(
    (rawKey: string): string => {
      const key = canonKey(rawKey);

      // batas jumlah
      if (!selectedCanon.has(key) && selectedCanon.size >= maxSelect) {
        return `Maksimal ${maxSelect} kebutuhan`;
      }

      // cek konflik dua arah antar-kanon
      for (const s of selectedCanon) {
        if ((MU_EX[s] || []).includes(key)) return `Tidak bisa dipadukan dengan ${labelOf(s)}`;
        if ((MU_EX[key] || []).includes(s)) return `Tidak bisa dipadukan dengan ${labelOf(s)}`;
      }
      return "";
    },
    [MU_EX, selectedCanon, maxSelect, labelOf]
  );

  const onToggleSafe = useCallback(
    (rawKey: string) => {
      const key = canonKey(rawKey);
      const reason = disableReasonOf(key);
      if (reason) {
        onBlocked?.(reason, key);
        return;
      }
      onToggle(key); // kirim KEY KANONIK ke state parent
    },
    [disableReasonOf, onToggle, onBlocked]
  );

  return (
    <div className="grid gap-3">
      <div className="flex items-center justify-between">
        <label className="font-semibold">Pilih Kebutuhan</label>
        <span className="text-xs opacity-70">{selectedCanon.size}/{maxSelect}</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-3 xl:grid-cols-3 gap-3">
        {(needs || []).map((n) => {
          const keyCanon = canonKey(n.key);
          const active = selectedCanon.has(keyCanon);
          const reason = disableReasonOf(n.key);
          const disabled = !!reason && !active;

          return (
            <button
              type="button"
              key={n.key}
              onClick={() => onToggleSafe(n.key)}
              className={[
                "rounded-2xl border overflow-hidden text-left shadow-sm transition relative",
                active
                  ? "ring-2 ring-orange-500 border-orange-500"
                  : isDark
                  ? "border-gray-700 hover:border-gray-500"
                  : "border-gray-300 hover:border-gray-400",
                disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer",
              ].join(" ")}
              aria-pressed={active}
              aria-disabled={disabled}
              title={reason || ""}
            >
              {active && (
                <span className="absolute top-2 right-2 text-[10px] px-2 py-0.5 rounded-full bg-orange-500 text-white">
                  Dipilih
                </span>
              )}

              <img
                src={n.image}
                alt={n.label}
                className="w-full aspect-square object-cover"
                draggable={false}
              />
              <div className={["px-3 py-2 text-sm text-center", active ? "bg-orange-500 text-white" : ""].join(" ")}>
                {n.label}
              </div>
            </button>
          );
        })}
      </div>

      <div className="text-xs opacity-70 leading-relaxed">
        <div>Pilih hingga {maxSelect} kebutuhan.</div>
        <div>
          Aturan: <span className="font-medium">Fun</span> tidak bisa dengan{" "}
          <span className="font-medium">Offroad</span>/<span className="font-medium">Niaga</span>;{" "}
          <span className="font-medium">Perjalanan Jauh</span> tidak bisa dengan{" "}
          <span className="font-medium">Perkotaan</span>.
        </div>
      </div>
    </div>
  );
}
