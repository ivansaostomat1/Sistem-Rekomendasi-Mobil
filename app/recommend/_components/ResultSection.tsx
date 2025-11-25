// file: app/(main)/_components/ResultsSection.tsx
"use client";

import React, { useMemo, useState, useEffect, useRef } from "react";
import TiltedCard from "@/components/ui/TiltedCard";
import { StickyResultBar } from "./StickyResultBar";
import { SkeletonGrid } from "./SkeletonGrid";
import type { Theme } from "../_types/theme";
import type { RecommendItem, RecommendResponse } from "@/types";
import { fmtIDR } from "@/utils";
import { API_BASE } from "@/constants";

type Props = {
  theme: Theme;
  loading: boolean;
  error: string | null;
  data: RecommendResponse | null;
  onBackToForm: () => void;
};

const FUEL_VISUAL: Record<string, { color: string; label: string }> = {
  g: { color: "#f59e0b", label: "Bensin" },
  d: { color: "#6b7280", label: "Diesel" },
  h: { color: "#10b981", label: "Hybrid" },
  p: { color: "#8b5cf6", label: "PHEV" },
  e: { color: "#06b6d4", label: "BEV" },
  o: { color: "#6b7280", label: "Lainnya" },
};

function fuelToCodeLoose(raw?: string | null): string {
  const s = String(raw ?? "").trim().toLowerCase();
  if (!s || s === "na" || s === "n/a" || s === "-") return "o";
  if (s.includes("phev") || s.includes("plug-in") || s.includes("plugin") || s.includes("plug in")) return "p";
  if (s === "h" || s.includes("hybrid") || s.includes("hev")) return "h";
  if (s === "e" || s.includes("bev") || s.includes("electric") || s === "ev") return "e";
  if (s === "d" || s.includes("diesel") || s.includes("dsl") || s.includes("solar")) return "d";
  if (s === "g" || s.includes("bensin") || s.includes("gasoline") || s.includes("petrol")) return "g";
  return "o";
}

/** ——— ROBUST FIT% ——— **/
const SCORE_FLOOR = 5;
const SCORE_CEIL = 100;
const TIGHT_SPAN = 1e-1;

function percentile(arr: number[], q: number): number {
  if (!arr.length) return 0;
  const s = [...arr].sort((a, b) => a - b);
  const pos = (s.length - 1) * q;
  const base = Math.floor(pos);
  const rest = pos - base;
  return s[base + 1] !== undefined ? s[base] + rest * (s[base + 1] - s[base]) : s[base];
}

function buildFitLabelers(items: RecommendItem[]) {
  const fs = items.map((x) => (typeof x.fit_score === "number" ? x.fit_score : 0));
  const p10 = percentile(fs, 0.1);
  const p90 = percentile(fs, 0.9);
  const span = Math.max(1e-6, p90 - p10);

  const sorted = [...fs].sort((a, b) => a - b);
  const n = Math.max(1, sorted.length - 1);

  return {
    pctByValue: (v: number) => {
      if (p90 - p10 < TIGHT_SPAN) {
        const idx = sorted.lastIndexOf(v);
        const t = idx / n;
        return Math.round(SCORE_FLOOR + t * (SCORE_CEIL - SCORE_FLOOR));
      }
      const t = Math.min(1, Math.max(0, (v - p10) / span));
      return Math.round(SCORE_FLOOR + t * (SCORE_CEIL - SCORE_FLOOR));
    },
  };
}

/* =================================================================== */
/*                           CHAT PANEL (SMART)                        */
/* =================================================================== */

type ChatMessage = {
  from: "user" | "bot";
  text: string;
};

type ChatbotApiResponse = {
  reply: string;
  suggested_questions?: string[];
};

function SmartChatPanel({
  theme,
  onClose,
}: {
  theme: Theme;
  onClose: () => void;
}) {
  const isDark = theme === "dark";
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      from: "bot",
      text:
        "Hai! Aku bisa jelasin kenapa mobil tertentu jadi peringkat 1, bedain mobil peringkat atas, " +
        "atau bantu simulasi 'what-if' (naik/turun budget, hindari jenis BBM, ubah fokus kebutuhan).",
    },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [suggested, setSuggested] = useState<string[]>([
    "Kenapa mobil ini nomor 1?",
    "Apa beda mobil 1 dan 2 untuk keluarga?",
    "Kenapa kok banyak yang diesel?",
    "Kalau budget saya naikin 50 juta gimana?",
  ]);

  const listRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async (text?: string) => {
    const final = (text ?? input).trim();
    if (!final || sending) return;

    setInput("");
    setMessages((prev) => [...prev, { from: "user", text: final }]);
    setSending(true);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: final }),
      });

      if (!res.ok) {
        throw new Error(`Gagal memanggil /chat (${res.status})`);
      }

      const json = (await res.json()) as ChatbotApiResponse;
      const reply = json.reply?.trim() || "Maaf, aku belum bisa menjawab sekarang.";
      setMessages((prev) => [...prev, { from: "bot", text: reply }]);

      if (json.suggested_questions?.length) {
        setSuggested(json.suggested_questions);
      }
    } catch (err) {
      console.error(err);
      setMessages((prev) => [
        ...prev,
        {
          from: "bot",
          text:
            "Maaf, ada kendala saat menghubungi asisten AI. " +
            "Silakan coba lagi sebentar lagi.",
        },
      ]);
    } finally {
      setSending(false);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div
      className={`rounded-2xl flex flex-col max-h-[70vh] min-h-[260px] w-full shadow-2xl ${
        isDark ? "bg-[#05070b]/95 border border-gray-800/80" : "bg-white border border-gray-200"
      }`}
    >
      {/* Header */}
      <div className="px-4 pt-3 pb-2 border-b border-white/5 flex items-center justify-between gap-3">
        <div className="flex flex-col gap-1">
          <div className="text-[10px] uppercase tracking-wide opacity-70">
            Asisten Rekomendasi Mobil
          </div>
          <div className="text-sm font-semibold">
            Chat AI – Penjelasan & Simulasi
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center justify-center w-8 h-8 rounded-full bg-gradient-to-br from-orange-500 to-amber-400 text-[11px] font-bold text-black shadow-md">
            AI
          </div>
          <button
            type="button"
            onClick={onClose}
            className={`w-7 h-7 inline-flex items-center justify-center rounded-full text-xs ${
              isDark ? "hover:bg-white/10 text-gray-300" : "hover:bg-gray-100 text-gray-600"
            }`}
            aria-label="Tutup chat"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Isi chat */}
      <div ref={listRef} className="flex-1 px-4 py-3 space-y-2 overflow-y-auto text-sm">
        {messages.map((m, idx) => {
          const isUser = m.from === "user";
          return (
            <div key={idx} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[85%] px-3 py-2 rounded-2xl text-xs sm:text-sm leading-relaxed shadow-sm ${
                  isUser
                    ? "bg-orange-500 text-white rounded-br-sm"
                    : isDark
                    ? "bg-[#0c111b] border border-gray-800/80 text-gray-100 rounded-bl-sm"
                    : "bg-gray-50 border border-gray-200 text-gray-900 rounded-bl-sm"
                }`}
              >
                {m.text}
              </div>
            </div>
          );
        })}
      </div>

      {/* Suggested questions */}
      {suggested.length > 0 && (
        <div className="px-4 pb-2 pt-1 border-t border-white/5">
          <div className="text-[11px] uppercase tracking-wide mb-1 opacity-70">
            Coba tanya:
          </div>
          <div className="flex flex-wrap gap-1.5">
            {suggested.slice(0, 4).map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => handleSend(q)}
                className={`text-[11px] px-2.5 py-1 rounded-full border transition ${
                  isDark
                    ? "border-gray-700 hover:bg-gray-800 text-gray-200"
                    : "border-gray-300 hover:bg-gray-100 text-gray-800"
                }`}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div className="px-4 pb-3 pt-2 border-t border-white/5">
        <div className="flex items-center gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            className={`flex-1 text-xs sm:text-sm rounded-xl px-3 py-2 outline-none border ${
              isDark
                ? "bg-black/40 border-gray-700 placeholder:text-gray-500 text-gray-100 focus:border-orange-400"
                : "bg-white border-gray-300 placeholder:text-gray-400 text-gray-900 focus:border-orange-400"
            }`}
          />
          <button
            type="button"
            onClick={() => handleSend()}
            disabled={sending || !input.trim()}
            className={`px-3 py-2 rounded-xl text-xs sm:text-sm font-semibold transition flex items-center gap-1 ${
              sending || !input.trim()
                ? "bg-gray-500/40 text-gray-300 cursor-not-allowed"
                : "bg-orange-500 hover:bg-orange-600 text-white shadow-sm"
            }`}
          >
            {sending ? "Mengirim…" : "Kirim"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* =================================================================== */
/*                       HASIL REKOMENDASI (GRID)                      */
/* =================================================================== */

export function ResultsSection({ theme, loading, error, data, onBackToForm }: Props) {
  const isDark = theme === "dark";
  const [chatOpen, setChatOpen] = useState(false);

  const safeCount =
    (data && typeof (data as any).count === "number" ? (data as any).count : data?.items?.length) ?? 0;

  const labeler = useMemo(() => buildFitLabelers(data?.items ?? []), [data]);

  const emptyHint: any = data && (data as any).hint ? (data as any).hint : null;
  const filtersSummary: any = emptyHint?.filters_summary ?? null;
  const needsDiag: any[] = emptyHint?.needs_diag ?? [];

  const cards = useMemo(() => {
    if (!data?.items?.length) return [];

    return data.items.map((it: RecommendItem, i: number) => {
      const fuelCode =
        ((it as any).fuel_code as string | undefined)?.toLowerCase?.() || fuelToCodeLoose(it.fuel);
      const fv = FUEL_VISUAL[fuelCode] ?? FUEL_VISUAL.o;

      const title = `${it.brand ?? ""} ${it.model ?? ""}`.trim();
      const priceStr = it.price != null ? fmtIDR(Number(it.price)) : "-";
      const fs = typeof it.fit_score === "number" ? it.fit_score : 0;
      const fitPct = labeler.pctByValue(fs);
      const fuelLabel = fv.label;
      const trans = it.trans ? String(it.trans) : "-";
      const seats =
        typeof it.seats === "number" && isFinite(it.seats) ? `${it.seats} kursi` : "-";
      const img = (it as any).image || (it as any).image_url || "/cars/default.jpg";

      const overlay = (
        <div className="absolute inset-0">
          {/* harga kanan-atas */}
          <div className="absolute top-2 right-2 bg-black/60 text-white text-xs font-semibold px-2 py-1 rounded-md whitespace-nowrap">
            Harga OTR {priceStr}
          </div>
          {/* footer judul + meta */}
          <div className="absolute inset-x-0 bottom-0 p-2 bg-gradient-to-t from-black/80 via-black/20 to-transparent">
            <div className="text-white text-[13px] font-semibold leading-tight line-clamp-2 w-fit bg-black/80 px-1 py-0.5 rounded">
              {title}
            </div>
            <div className="mt-0.5 text-[11px] text-white/90 flex items-center gap-1 whitespace-nowrap overflow-hidden">
              <span className="bg-black/50 text-white text-[11px] px-2 py-0.5 rounded-md">
                #{i + 1}
              </span>
              <span className="bg-black/50 px-1.5 py-0.5 rounded">{fitPct}%</span>
              <span>•</span>
              <span>{fuelLabel}</span>
              <span>•</span>
              <span>{trans}</span>
              <span>•</span>
              <span>{seats}</span>
            </div>
          </div>
        </div>
      );

      return (
        <div key={`${it.brand}-${it.model}-${i}`} className="w-full">
          <TiltedCard
            imageSrc={img}
            altText={title || "Mobil"}
            captionText={title}
            containerHeight="220px"
            containerWidth="100%"
            imageHeight="220px"
            imageWidth="100%"
            rotateAmplitude={5}
            scaleOnHover={1}
            showMobileWarning={false}
            showTooltip={false}
            displayOverlayContent={true}
            overlayContent={overlay}
          />
        </div>
      );
    });
  }, [data, labeler]);

  return (
    <>
      <StickyResultBar count={loading ? null : safeCount} theme={theme} onBackToForm={onBackToForm} />

      {error && (
        <div className="mt-6 mb-4 rounded-2xl border border-red-800 bg-red-950/40 p-3 text-red-200">
          Error: {error}
        </div>
      )}

      <div className="mt-6 mb-4">
        <h2 className="text-2xl font-bold mb-1">
          {loading
            ? "Menyiapkan Rekomendasi…"
            : data
            ? safeCount > 0
              ? `Hasil Rekomendasi Mobil Terbaik Untuk Anda ✨ (${safeCount})`
              : "Belum Ada Mobil yang Cocok dengan Kriteria Saat Ini"
            : "Hasil Rekomendasi"}
        </h2>
      </div>

      {loading ? (
        <div className="p-4 md:p-6 rounded-2xl border border-gray-800/50">
          <SkeletonGrid n={6} theme={theme} />
        </div>
      ) : data ? (
        safeCount > 0 ? (
          <div
            className={`rounded-2xl ${
              isDark ? "border border-gray-800/60" : "border border-gray-200"
            } p-3`}
          >
            <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">{cards}</div>
          </div>
        ) : (
          <div
            className={`p-8 text-center rounded-2xl ${
              isDark
                ? "bg-[#121212] border border-gray-800/60"
                : "bg-white border border-gray-200"
            }`}
          >
            <p className="text-lg font-semibold mb-2">
              Belum ada mobil yang bisa direkomendasikan dengan kriteria ini.
            </p>

            {/* Paragraf utama tergantung reason dari backend */}
            {(() => {
              const r = emptyHint?.reason as string | undefined;

              if (r === "BUDGET_TOO_LOW" || r === "BUDGET_TOO_LOW_FOR_NEEDS") {
                const cur = Number(emptyHint?.current_budget ?? 0);
                const cap = Number(
                  emptyHint?.max_price_allowed ?? emptyHint?.current_budget ?? 0
                );
                const minFiltered =
                  emptyHint?.min_price_filtered != null
                    ? Number(emptyHint.min_price_filtered)
                    : null;
                const suggested =
                  emptyHint?.suggested_budget != null
                    ? Number(emptyHint.suggested_budget)
                    : null;

                return (
                  <>
                    <p className="text-sm text-neutral-400">
                      Dengan budget sekarang{" "}
                      <span className="font-semibold">{fmtIDR(cur)}</span> dan batas
                      perhitungan sistem sekitar{" "}
                      <span className="font-semibold">{fmtIDR(cap)}</span>, semua mobil
                      yang cocok filter jatuh di luar jangkauan harga ini.
                    </p>
                    {minFiltered != null && (
                      <p className="text-sm text-neutral-400 mt-1">
                        Di antara mobil yang sudah lolos filter dasar, harga termurah
                        sekitar{" "}
                        <span className="font-semibold">{fmtIDR(minFiltered)}</span>.
                      </p>
                    )}
                    {suggested != null && (
                      <p className="text-sm text-neutral-400 mt-1">
                        Sebagai gambaran awal, coba naikkan budget ke kisaran{" "}
                        <span className="font-semibold">{fmtIDR(suggested)}</span>.
                      </p>
                    )}
                  </>
                );
              }

              if (r === "NO_MATCH_FILTERS") {
                const minOverall =
                  emptyHint?.min_price_overall != null
                    ? Number(emptyHint.min_price_overall)
                    : null;
                return (
                  <>
                    <p className="text-sm text-neutral-400">
                      Tidak ada mobil di data yang cocok dengan kombinasi brand /
                      transmisi / jenis BBM yang kamu pilih.
                    </p>
                    {minOverall != null && (
                      <p className="text-sm text-neutral-400 mt-1">
                        Sebagai konteks, harga mobil termurah di seluruh data sekitar{" "}
                        <span className="font-semibold">{fmtIDR(minOverall)}</span>.
                      </p>
                    )}
                  </>
                );
              }

              if (r === "NO_MATCH_NEEDS") {
                return (
                  <p className="text-sm text-neutral-400">
                    Di data saat ini belum ada mobil yang bisa memenuhi salah satu
                    kebutuhan yang kamu pilih. Coba kurangi jumlah kebutuhan atau pilih
                    kombinasi yang lebih umum.
                  </p>
                );
              }

              if (r === "CONSTRAINTS_TOO_STRICT") {
                return (
                  <p className="text-sm text-neutral-400">
                    Budget dan filter dasar sebenarnya sudah cukup, tapi kombinasi
                    kebutuhan dan aturan sistem membuat semua kandidat gugur. Coba
                    kurangi jumlah kebutuhan atau longgarkan filter lain.
                  </p>
                );
              }

              if (r === "ERROR") {
                return (
                  <p className="text-sm text-neutral-400">
                    Terjadi kendala saat menghitung saran. Coba ubah kriteria sedikit
                    lalu jalankan ulang.
                  </p>
                );
              }

              return (
                <p className="text-sm text-neutral-400">
                  Coba sesuaikan budget atau hilangkan beberapa kriteria filter untuk
                  mendapatkan hasil.
                </p>
              );
            })()}

            {/* Ringkasan filter yang terpakai */}
            {filtersSummary && (
              <div className="mt-4 text-xs sm:text-sm text-neutral-400 text-left max-w-xl mx-auto">
                <div className="font-semibold text-neutral-300 mb-1">
                  Ringkasan filter yang terpakai:
                </div>
                <ul className="space-y-0.5">
                  <li>
                    • Brand:{" "}
                    {filtersSummary.brand
                      ? `hanya merek yang mengandung "${filtersSummary.brand}"`
                      : "semua merek diizinkan"}
                  </li>
                  <li>
                    • Transmisi:{" "}
                    {filtersSummary.trans_choice
                      ? `difilter ke tipe "${filtersSummary.trans_choice}"`
                      : "manual & otomatis diizinkan"}
                  </li>
                  <li>
                    • Jenis BBM:{" "}
                    {Array.isArray(filtersSummary.fuels) &&
                    filtersSummary.fuels.length > 0 ? (
                      filtersSummary.fuels.length === 5 ? (
                        "semua jenis BBM (bensin, diesel, hybrid, PHEV, BEV)"
                      ) : (
                        filtersSummary.fuels
                          .map((c: string) => {
                            const code = (c || "").toLowerCase();
                            if (code === "g") return "bensin";
                            if (code === "d") return "diesel";
                            if (code === "h") return "hybrid";
                            if (code === "p") return "PHEV";
                            if (code === "e") return "BEV";
                            return code;
                          })
                          .join(", ")
                      )
                    ) : (
                      "tidak dibatasi (semua jenis BBM diizinkan)"
                    )}
                  </li>
                </ul>
              </div>
            )}

            {/* Ringkasan kebutuhan (khususnya offroad dll) */}
            {needsDiag.length > 0 && (
              <div className="mt-3 text-xs sm:text-sm text-neutral-400 text-left max-w-xl mx-auto">
                <div className="font-semibold text-neutral-300 mb-1">
                  Ringkasan kebutuhan yang dipilih:
                </div>
                <ul className="space-y-0.5">
                  {needsDiag.map((d) => {
                    const needKey = String(d.need || "");
                    const labelMap: Record<string, string> = {
                      perjalanan_jauh: "Perjalanan Jauh",
                      keluarga: "Keluarga",
                      fun: "Fun to Drive",
                      perkotaan: "Perkotaan",
                      niaga: "Niaga",
                      offroad: "Offroad",
                    };
                    const label = labelMap[needKey] ?? needKey;
                    const total = Number(d.total ?? 0);
                    const underCap = Number(d.under_cap ?? 0);
                    const minAll =
                      d.min_price_all != null ? Number(d.min_price_all) : null;

                    if (total === 0) {
                      return (
                        <li key={needKey}>
                          • {label}: di data belum ada mobil yang memenuhi definisi
                          kebutuhan ini.
                        </li>
                      );
                    }

                    if (underCap === 0) {
                      return (
                        <li key={needKey}>
                          • {label}: ada {total} mobil di data yang cocok dari sisi
                          spesifikasi, tetapi semuanya di atas batas harga yang
                          dihitung dari budget saat ini
                          {minAll != null && (
                            <>
                              {" "}
                              (mobil termurah sekitar{" "}
                              <span className="font-semibold">
                                {fmtIDR(minAll)}
                              </span>
                              ).
                            </>
                          )}
                        </li>
                      );
                    }

                    return (
                      <li key={needKey}>
                        • {label}: masih ada {underCap} mobil yang cocok di data, tetapi
                        kombinasi dengan kebutuhan lain / aturan sistem membuat semuanya
                        gugur di ranking akhir.
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            <div className="mt-5">
              <button
                onClick={onBackToForm}
                className={`${
                  isDark
                    ? "border border-gray-700 hover:bg-[#2a2a2a]"
                    : "border border-gray-300 hover:bg-gray-100"
                } px-6 py-3 rounded-xl text-sm font-medium`}
              >
                Ubah Kriteria
              </button>
            </div>
          </div>
        )
      ) : (
        <div
          className={`p-8 text-center rounded-2xl ${
            isDark
              ? "bg-[#121212] border border-gray-800/60"
              : "bg-white border border-gray-200"
          }`}
        >
          <p className="text-neutral-400">Menunggu hasil...</p>
        </div>
      )}

      {/* Floating tombol chat – hanya muncul kalau sudah ada hasil & tidak loading */}
      {safeCount > 0 && !loading && (
        <>
          <button
            type="button"
            onClick={() => setChatOpen(true)}
            className="fixed bottom-4 right-4 z-40 flex items-center gap-2 rounded-full px-3 py-2 text-xs sm:text-sm bg-orange-500 hover:bg-orange-600 text-white shadow-lg"
          >
            <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-black/20 text-xl font-bold">
              👤
            </span>
            <span className="hidden sm:inline">Tanya / Simulasi dengan AI</span>
          </button>

          {chatOpen && (
            <div className="fixed bottom-16 right-4 z-50 w-[min(100%-2rem,380px)] sm:w-96">
              <SmartChatPanel theme={theme} onClose={() => setChatOpen(false)} />
            </div>
          )}
        </>
      )}
    </>
  );
}
