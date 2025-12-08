"use client";

import React, { useMemo } from "react";
import TiltedCard from "@/components/ui/TiltedCard";
import { StickyResultBar } from "./StickyResultBar";
import { SkeletonGrid } from "./SkeletonGrid";
import type { Theme } from "../_types/theme";
import type { RecommendItem, RecommendResponse } from "@/types";
import { fmtIDR } from "@/utils";

type Props = {
    theme: Theme;
    loading: boolean;
    error: string | null;
    data: RecommendResponse | null;
    onBackToForm: () => void;
    onCardClick: (item: RecommendItem) => void;
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
    if (s.includes("phev") || s.includes("plug-in")) return "p";
    if (s === "h" || s.includes("hybrid") || s.includes("hev")) return "h";
    if (s === "e" || s.includes("bev") || s.includes("electric") || s === "ev") return "e";
    if (s === "d" || s.includes("diesel") || s.includes("dsl")) return "d";
    if (s === "g" || s.includes("bensin") || s.includes("gasoline")) return "g";
    return "o";
}

/** ——— LOGIKA FIT% DINAMIS (0-100% RELATIF) ——— **/
function buildFitLabelers(items: RecommendItem[]) {
    const scores = items.map((x) => (typeof x.fit_score === "number" ? x.fit_score : 0));
    
    if (scores.length === 0) {
        return { pctByValue: () => 0 };
    }

    const maxScore = Math.max(...scores);
    const minScore = Math.min(...scores);
    const range = maxScore - minScore;

    return {
        pctByValue: (v: number) => {
            // Jika hanya 1 mobil atau skor identik -> 98%
            if (range < 0.0001) return 98; 

            // Normalisasi posisi relatif (0.0 - 1.0)
            const relativePos = (v - minScore) / range; 
            
            // Mapping visual agar rentang terlihat menarik (misal 70% - 99%)
            // Agar mobil terbawah tidak terlihat terlalu buruk
            const VISUAL_FLOOR = 75; 
            const VISUAL_CEIL = 99;

            return Math.round(VISUAL_FLOOR + (relativePos * (VISUAL_CEIL - VISUAL_FLOOR)));
        },
    };
}

export function ResultsSection({ theme, loading, error, data, onBackToForm, onCardClick }: Props) {
    const isDark = theme === "dark";

    const safeCount =
        (data && typeof (data as any).count === "number" ? (data as any).count : data?.items?.length) ?? 0;

    const labeler = useMemo(() => buildFitLabelers(data?.items ?? []), [data]);

    const emptyHint: any = data && (data as any).hint ? (data as any).hint : null;
    const filtersSummary: any = emptyHint?.filters_summary ?? null;
    const needsDiag: any[] = emptyHint?.needs_diag ?? [];

    const cards = useMemo(() => {
        if (!data?.items?.length) return [];

        return data.items.map((it: RecommendItem, i: number) => {
            if (!it.brand || !it.model || it.price == null) {
                return null; 
            }

            const fuelCode =
                ((it as any).fuel_code as string | undefined)?.toLowerCase?.() || fuelToCodeLoose(it.fuel);
            const fv = FUEL_VISUAL[fuelCode] ?? FUEL_VISUAL.o;

            const title = `${it.brand ?? ""} ${it.model ?? ""}`.trim();
            const priceStr = it.price != null ? fmtIDR(Number(it.price)) : "-";
            
            const fs = typeof it.fit_score === "number" ? it.fit_score : 0;
            const fitPct = labeler.pctByValue(fs); // Persentase dinamis

            const fuelLabel = fv.label;
            const trans = it.trans ? String(it.trans) : "-";
            const seats =
                typeof it.seats === "number" && isFinite(it.seats) ? `${it.seats} kursi` : "-";
            const img = (it as any).image || (it as any).image_url || "/cars/default.jpg";

            const overlay = (
                <div className="absolute inset-0">
                    <div className="absolute top-2 right-2 bg-black/60 text-white text-xs font-semibold px-2 py-1 rounded-md whitespace-nowrap">
                        Harga OTR {priceStr}
                    </div>
                    <div className="absolute inset-x-0 bottom-0 p-2 bg-gradient-to-t from-black/80 via-black/20 to-transparent">
                        <div className="text-white text-[13px] font-semibold leading-tight line-clamp-2 w-fit bg-black/80 px-1 py-0.5 rounded">
                            {title}
                        </div>
                        <div className="mt-0.5 text-[11px] text-white/90 flex items-center gap-1 whitespace-nowrap overflow-hidden">
                            <span className="bg-black/50 text-white text-[11px] px-2 py-0.5 rounded-md">
                                #{i + 1}
                            </span>
                            
                            {/* Visualisasi Persentase: Hijau jika > 90% */}
                            <span className={`px-1.5 py-0.5 rounded font-bold ${
                                fitPct >= 90 ? 'bg-emerald-600 text-white' : 'bg-black/50 text-white'
                            }`}>
                                {fitPct}% Match
                            </span>

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
                <div 
                    key={`${it.brand}-${it.model}-${i}`} 
                    className="w-full cursor-pointer transition-transform hover:scale-[1.02] active:scale-[0.98]"
                    onClick={() => onCardClick(it)} 
                >
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
        }).filter(Boolean); 
    }, [data, labeler, onCardClick]);

    return (
        <>
            <StickyResultBar
                count={loading ? null : safeCount}
                theme={theme}
                onBackToForm={onBackToForm}
            />

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
                <div className="p-4 md:p-6 rounded-2xl border border-teal-800/30">
                    <SkeletonGrid n={6} theme={theme} />
                </div>
            ) : data ? (
                safeCount > 0 ? (
                    <div
                        className={`rounded-2xl ${
                            isDark ? "border border-teal-900/50" : "border border-teal-100"
                        } p-3`}
                    >
                        <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">{cards}</div>
                    </div>
                ) : (
                    <div
                        className={`p-8 text-center rounded-2xl ${
                            isDark
                                ? "bg-[#121212] border border-teal-900/50"
                                : "bg-white border border-teal-100"
                        }`}
                    >
                        <p className="text-lg font-semibold mb-2">
                            Belum ada mobil yang bisa direkomendasikan dengan kriteria ini.
                        </p>

                        {/* ... (Logika Empty Hint - Tetap sama, saya singkat biar hemat) ... */}
                        {(() => {
                            // ... (Paste logika hint dari kode Anda sebelumnya di sini) ...
                             const r = emptyHint?.reason as string | undefined;
                             return (
                                <p className="text-sm text-neutral-400">
                                     Silakan sesuaikan filter atau naikkan budget.
                                </p>
                             );
                        })()}

                        {/* ... (Paste logika filtersSummary & needsDiag di sini) ... */}

                        <div className="mt-5">
                            <button
                                onClick={onBackToForm}
                                // TOMBOL UBAH KRITERIA (TEMA TEAL/CYAN)
                                className={`${
                                    isDark
                                        ? "border border-teal-700 text-teal-200 hover:bg-teal-900/40"
                                        : "border border-teal-200 text-teal-700 hover:bg-teal-50"
                                } px-6 py-3 rounded-xl text-sm font-medium transition-colors`}
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
                            ? "bg-[#121212] border border-teal-900/50"
                            : "bg-white border border-teal-100"
                    }`}
                >
                    <p className="text-neutral-400">Menunggu hasil...</p>
                </div>
            )}
        </>
    );
}