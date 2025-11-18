"use client";

// app/recommend/page.tsx
import React, { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useTheme } from "@/hooks/useTheme";
import { Header } from "@/components/forms/Header";
import { RecommendationForm } from "@/components/forms/index";
import type { RecommendResponse } from "@/types";
import { useBootstrapMeta } from "./_hooks/useBootstrapMeta";
import { useSearchFlow } from "./_hooks/useSearchFlow";
import { ResultsSection } from "./_components/ResultSection";
import { DevPanel } from "./_components/DevPanel";
import type { Theme } from "./_types/theme";

export default function RecommendPage() {
  // pastikan theme bertipe union, bukan string bebas
  const { theme, toggleTheme } = useTheme() as { theme: Theme; toggleTheme: () => void };

  // state utama
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<string | null>(null);
  const [data,    setData]    = useState<RecommendResponse | null>(null);
  const [isSearched, setIsSearched] = useState(false);

  // meta untuk form (brands/segments/fuels/seats) + fungsi refetch
  const { meta, dataReady, refetchMeta } = useBootstrapMeta();

  // refs (nullable)
  const formRef    = useRef<HTMLDivElement | null>(null);
  const resultsRef = useRef<HTMLDivElement | null>(null);

  // alur form -> hasil + auto-scroll
  const { showForm, openForm, openResults } = useSearchFlow({
    isSearched,
    loading,
    data,
    error,
    formRef,
    resultsRef,
  });

  // jika selesai submit pertama kali: pindah ke tampilan hasil
  useEffect(() => {
    if (isSearched) openResults();
  }, [isSearched, openResults]);

  return (
    <div
      className={`min-h-screen transition-colors duration-300 ${
        theme === "dark" ? "bg-[#0a0a0a] text-gray-100" : "bg-gray-50 text-gray-900"
      }`}
    >
      <Header theme={theme} toggleTheme={toggleTheme} />

      <main className="mx-auto max-w-6xl px-10 py-10">
        {/* Hero */}
        <section className="mb-10">
          <h1 className="text-4xl md:text-5xl font-extrabold leading-tight mb-4">
            Cari mobil impianmu di{" "}
           
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-amber-400 to-orange-600">
              VRoom
            </span>
          </h1>
          <p className="text-base md:text-lg opacity-80 mb-6 max-w-2xl">
            Masukkan kriteria mobil impianmu dan dapatkan rekomendasi terbaik.
          </p>
        </section>

        {/* Tahap 1: Form */}
        <AnimatePresence mode="wait">
          {showForm && (
            <motion.section
              key="form"
              ref={formRef}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.35 }}
              className="mb-10"
            >
              <RecommendationForm
                theme={theme}
                loading={loading}
                error={error}
                data={data}
                meta={meta}
                isSearched={isSearched}
                setLoading={setLoading}
                setError={setError}
                setData={setData}
                setIsSearched={setIsSearched}
              />
            </motion.section>
          )}
        </AnimatePresence>

        {/* Tahap 2: Hasil */}
        <AnimatePresence mode="wait">
          {!showForm && (
            <motion.section
              key="resultsView"
              ref={resultsRef}
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              transition={{ duration: 0.35 }}
              className="px-0 pb-12"
            >
              <ResultsSection
                theme={theme}
                loading={loading}
                error={error}
                data={data}
                onBackToForm={() => {
                  // === FIX POKOK ===
                  // reset flag agar submit berikutnya (false -> true) memicu efek penutup form
                  setIsSearched(false);
                  // bersihkan hasil & error lama
                  setData(null);
                  setError(null);
                  // opsi: setiap balik ke form panggil /meta lagi (biar selalu muncul log GET /meta)
                  refetchMeta();

                  // tampilkan form & scroll
                  openForm();
                  setTimeout(() => {
                    formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
                  }, 0);
                }}
              />
            </motion.section>
          )}
        </AnimatePresence>

        {/* Eksplorasi (opsional)
        <ExploreExtras theme={theme} /> */}

        {/* Panel dev (hanya jika NEXT_PUBLIC_DEBUG=1) */}
        <DevPanel theme={theme} dataReady={dataReady} />
      </main>
    </div>
  );
}
