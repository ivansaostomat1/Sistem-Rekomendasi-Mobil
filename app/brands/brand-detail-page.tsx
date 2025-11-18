"use client";

import { useTheme } from "@/hooks/useTheme";
import { Header } from "@/components/ui/Header";
import { BRANDS } from "@/constants";
import { notFound } from "next/navigation";

interface BrandDetailPageProps {
  params: {
    slug: string;
  };
}

export default function BrandDetailPage({ params }: BrandDetailPageProps) {
  const { theme, toggleTheme } = useTheme();
  
  // Decode slug to get brand name
  const brandName = params.slug.replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
  
  // Find brand data
  const brand = BRANDS.find(b => 
    b.name.toLowerCase() === brandName.toLowerCase() ||
    b.name.toLowerCase().replace(/ /g, '-') === params.slug
  );

  if (!brand) {
    notFound();
  }

  return (
    <div className={`min-h-screen transition-colors duration-300 ${theme === "dark" ? "bg-[#0a0a0a] text-gray-100" : "bg-gray-50 text-gray-900"}`}>
      <Header theme={theme} toggleTheme={toggleTheme} />
      
      <main className="max-w-6xl mx-auto px-6 py-10">
        {/* Brand Header */}
        <section className="mb-12 text-center">
          <div className="flex justify-center mb-6">
            <div className="w-32 h-32 relative">
              <img
                src={brand.logo}
                alt={`${brand.name} logo`}
                className="w-full h-full object-contain"
              />
            </div>
          </div>
          <h1 className="text-4xl md:text-5xl font-bold mb-4">{brand.name}</h1>
          <p className="text-lg opacity-80 max-w-2xl mx-auto">
            Detail informasi tentang brand {brand.name} dan model-model terpopuler.
          </p>
        </section>

        {/* Coming Soon Message */}
        <section className={`rounded-3xl p-12 text-center ${theme === "dark" ? "bg-[#1a1a1a]" : "bg-white border border-gray-200"}`}>
          <div className="max-w-md mx-auto">
            <div className="text-6xl mb-4">🚧</div>
            <h2 className="text-2xl font-bold mb-4">Halaman Dalam Pengembangan</h2>
            <p className="opacity-80 mb-6">
              Detail brand {brand.name} sedang dalam proses pengembangan. 
              Kami akan segera menampilkan informasi lengkap tentang model-model terbaru, 
              spesifikasi, dan rekomendasi terbaik.
            </p>
            <a
              href="/recommend"
              className="bg-gradient-to-r from-amber-400 to-orange-600 text-white px-6 py-3 rounded-xl font-semibold hover:opacity-90 transition inline-block"
            >
              Kembali ke Rekomendasi
            </a>
          </div>
        </section>

        {/* Quick Stats Placeholder */}
        <section className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className={`rounded-2xl p-6 text-center ${theme === "dark" ? "bg-[#1a1a1a]" : "bg-white border border-gray-200"}`}>
            <div className="text-2xl font-bold text-orange-400 mb-2">-</div>
            <p className="text-sm opacity-70">Model Tersedia</p>
          </div>
          <div className={`rounded-2xl p-6 text-center ${theme === "dark" ? "bg-[#1a1a1a]" : "bg-white border border-gray-200"}`}>
            <div className="text-2xl font-bold text-orange-400 mb-2">-</div>
            <p className="text-sm opacity-70">Harga Rata-rata</p>
          </div>
          <div className={`rounded-2xl p-6 text-center ${theme === "dark" ? "bg-[#1a1a1a]" : "bg-white border border-gray-200"}`}>
            <div className="text-2xl font-bold text-orange-400 mb-2">-</div>
            <p className="text-sm opacity-70">Resale Value</p>
          </div>
        </section>
      </main>
    </div>
  );
}