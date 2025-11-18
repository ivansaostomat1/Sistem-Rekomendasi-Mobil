"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { StickyResultBar } from "./StickyResultBar";
import { SkeletonGrid } from "./SkeletonGrid";
import { RecommendationForm } from "@/components/forms/RecommendationForm";
import { API_BASE } from "@/constants";
import type { Theme, RecommendResponse, MetaResponse, RecommendItem } from "@/types";

export default function RecommendClient({ theme }: { theme: Theme }) {
  // ====== State global halaman rekomendasi ======
  const [meta, setMeta] = useState<MetaResponse | null>(null);
  const [data, setData] = useState<RecommendResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSearched, setIsSearched] = useState(false);

  // Kunci untuk force re-mount view agar memo/stale state tidak nempel
  const [viewKey, setViewKey] = useState(0);

  // ====== Ambil meta di awal & setiap kali kembali ke form (sesuai kebutuhanmu) ======
  const fetchMeta = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/meta`, {
        method: "GET",
        cache: "no-store",
        headers: { "Cache-Control": "no-cache" },
      });
      if (!res.ok) throw new Error(`META HTTP ${res.status}`);
      const j = (await res.json()) as MetaResponse;
      setMeta(j);
    } catch (err: any) {
      console.error(err);
    }
  }, []);

  useEffect(() => {
    // load meta saat pertama kali halaman dibuka
    fetchMeta();
  }, [fetchMeta]);

  // (Opsional sesuai permintaanmu) – setiap klik "Ubah Kriteria" akan refetch meta
  const handleBackToForm = useCallback(() => {
    // Kosongkan hasil, matikan mode hasil, paksa re-mount form
    setData(null);
    setIsSearched(false);
    setViewKey((k) => k + 1);

    // refetch meta agar log server selalu ada GET /meta seperti yang kamu minta
    fetchMeta();

    // scroll ke atas agar form terlihat
    if (typeof window !== "undefined") {
      window.requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: "smooth" }));
    }
  }, [fetchMeta]);

  // Hitung jumlah hasil secara aman
  const count = data?.count ?? (data?.items?.length ?? 0);

  // Untuk grid hasil, gunakan key yang berubah tiap kali berhasil submit
  const resultsKey = useMemo(() => {
    // gabungkan viewKey + count supaya re-mount ketika submit ulang
    return `results-${viewKey}-${count}`;
  }, [viewKey, count]);

  return (
    <section className="mx-auto max-w-6xl px-6 md:px-10 py-8">
      {/* Bar info hasil (sticky) muncul hanya saat sudah pernah search */}
      {isSearched && (
        <StickyResultBar
          count={data ? count : (loading ? null : 0)}
          theme={theme}
          onBackToForm={handleBackToForm}
        />
      )}

      {/* TAMPILKAN FORM saat belum cari, atau ketika user menekan "Ubah Kriteria" */}
      {!isSearched && (
        <div key={`form-${viewKey}`} className="mt-4">
          <RecommendationForm
            key={`form-inner-${viewKey}`} // paksa form remount lengkap
            theme={theme}
            loading={loading}
            error={error}
            data={data}
            meta={meta}
            isSearched={isSearched}
            setLoading={setLoading}
            setError={setError}
            setData={(d) => {
              setData(d);
            }}
            setIsSearched={setIsSearched}
          />
        </div>
      )}

      {/* TAMPILKAN HASIL setelah pencarian */}
      {isSearched && (
        <div className="mt-8" key={resultsKey}>
          {loading && <SkeletonGrid n={6} theme={theme} />}

          {!loading && error && (
            <div
              className={`p-4 rounded-xl border ${theme === "dark" ? "border-red-700 bg-red-900/20" : "border-red-300 bg-red-50"
                }`}
            >
              <p className="text-sm font-medium">Gagal memuat rekomendasi</p>
              <p className="text-xs opacity-80 mt-1">{error}</p>
              <button
                type="button"
                onClick={handleBackToForm}
                className={`mt-3 border px-3 py-1.5 rounded-lg text-xs font-semibold ${theme === "dark"
                    ? "border-gray-700 bg-[#1a1a1a] hover:bg-[#111]"
                    : "border-gray-300 bg-white hover:bg-gray-100"
                  }`}
              >
                Ubah Kriteria
              </button>
            </div>
          )}

          {!loading && !error && data && (
            <>
              {count === 0 ? (
                <div
                  className={`p-4 rounded-xl border ${theme === "dark" ? "border-gray-700 bg-[#0a0a0a]" : "border-gray-300 bg-white"
                    }`}
                >
                  <p className="text-sm">Tidak ada hasil yang cocok.</p>
                  <div className="mt-3">
                    <button
                      type="button"
                      onClick={handleBackToForm}
                      className={`border px-3 py-1.5 rounded-lg text-xs font-semibold ${theme === "dark"
                          ? "border-gray-700 bg-[#1a1a1a] hover:bg-[#111]"
                          : "border-gray-300 bg-white hover:bg-gray-100"
                        }`}
                    >
                      Ubah Kriteria
                    </button>
                  </div>
                </div>
              ) : (
                <div className="grid lg:grid-cols-3 md:grid-cols-2 gap-8">
                  {data.items.map((it: RecommendItem, idx: number) => (
                    <article
                      key={`${it.brand}-${it.model}-${idx}`}
                      className={`rounded-2xl overflow-hidden border ${theme === "dark" ? "bg-[#1a1a1a] border-gray-800" : "bg-white border-gray-200"
                        }`}
                    >
                      <div className="relative w-full h-44 bg-gray-200">
                        {/* image_url dari API (sudah kamu tambahkan di backend) */}
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={it.image_url ?? "/cars/default.jpg"}
                          alt={`${it.brand} ${it.model}`}
                          className="w-full h-full object-cover"
                          loading="lazy"
                          onError={(e) => {
                            const img = e.currentTarget;
                            // cegah loop fallback kalau default.jpg juga 404
                            if (img.dataset.fallback) return;
                            img.dataset.fallback = "1";
                            img.src = "/cars/default.jpg";
                          }}
                        />

                      </div>
                      <div className="p-5">
                        <div className="text-xs opacity-60">{it.brand}</div>
                        <h3 className="text-base font-semibold">{it.model}</h3>
                        <div className="mt-2 text-sm">
                          Harga OTR: <span className="font-semibold">
                            {Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 }).format(it.price || 0)}
                          </span>
                        </div>
                        {/* <div className="mt-1 text-xs opacity-70">
                          Prediksi jual {Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 }).format(it.predicted_resale_value || 0)}
                        </div> */}
                        <div className="mt-3 text-xs opacity-80">{it.alasan}</div>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}
