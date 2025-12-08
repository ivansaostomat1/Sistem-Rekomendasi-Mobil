"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import Shuffle from "@/components/ui/Shuffle";
import { FuelIcon } from "@/components/icons/FuelIcons";
import { FUEL_DATA } from "@/constants";
import { useTheme } from "@/hooks/useTheme";

export default function HomePage() {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";

  return (
    <div
      className={`min-h-screen transition-colors duration-300 ${
        isDark ? "bg-[#0a0a0a] text-gray-100" : "bg-gray-50 text-gray-900"
      }`}
    >
      {/* --- HEADER --- */}
      <header
        className={`flex justify-between items-center px-8 py-5 shadow-sm sticky top-0 z-50 backdrop-blur-md ${
          isDark
            ? "bg-[#0a0a0a]/90 border-b border-white/5 shadow-teal-900/10"
            : "bg-white/90 border-b border-teal-50 shadow-teal-100/50"
        }`}
      >
        <div className="flex items-center gap-3">
          <Shuffle
            text="VRoom"
            shuffleDirection="right"
            duration={1}
            animationMode="evenodd"
            shuffleTimes={3}
            ease="back.out"
            stagger={0.02}
            threshold={0}
            rootMargin="0px"
            triggerOnce={false}
            triggerOnHover={true}
            loop={false}
            loopDelay={1.2}
            respectReducedMotion={true}
            // PERBAIKAN DI SINI:
            // Hapus 'text-transparent bg-clip-text...'
            // Ganti dengan warna solid yang kontras sesuai tema
            className={`!text-2xl md:!text-3xl normal-case font-extrabold tracking-tight cursor-pointer select-none
                ${isDark ? "!text-teal-500" : "!text-emerald-700"}
            `}
            style={{ textAlign: "left" }}
          />
        </div>

        <button
          onClick={toggleTheme}
          className={`border px-4 py-2 rounded-full text-sm font-semibold transition flex items-center gap-2 ${
            isDark
              ? "border-teal-800 bg-teal-950/30 text-teal-100 hover:bg-teal-900"
              : "border-teal-200 bg-teal-50 text-teal-800 hover:bg-teal-100"
          }`}
          aria-label="Toggle tema"
        >
          {isDark ? "🌙 Dark" : "☀️ Light"}
        </button>
      </header>

      {/* --- HERO SECTION --- */}
      <section className="text-center py-24 px-6 relative overflow-hidden">
        {/* Background Blob Effect (Optional) */}
        {isDark && (
           <div className="pointer-events-none absolute inset-0 opacity-20 mix-blend-screen">
             <div className="absolute top-10 left-1/4 h-64 w-64 rounded-full bg-teal-600 blur-[100px]" />
             <div className="absolute bottom-10 right-1/4 h-64 w-64 rounded-full bg-emerald-600 blur-[100px]" />
           </div>
        )}

        <div className="relative z-10 max-w-4xl mx-auto">
          <h1 className="text-5xl md:text-7xl font-extrabold leading-tight tracking-tight mb-6">
            Temukan Mobil Impianmu Hanya di
            <br />
            {/* Gradient Text tetap BISA digunakan di elemen statis (h1/span), 
                tapi tidak disarankan di komponen animasi Shuffle */}
            <span className={`text-transparent bg-clip-text bg-gradient-to-r ${
                isDark ? "from-emerald-400 to-cyan-400" : "from-teal-600 to-sky-600"
            }`}>
               VRoom.
            </span>
          </h1>
          
          <p className={`text-lg md:text-xl max-w-2xl mx-auto mb-10 ${
              isDark ? "text-gray-400" : "text-gray-600"
          }`}>
            Bingung pilih Bensin, Diesel, atau Mobil Listrik? Biarkan AI kami membantu menemukan solusi terbaik untuk kebutuhan Anda.
          </p>

          <motion.div
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            className="inline-block"
          >
            <Link
              href="/recommend"
              className="bg-gradient-to-r from-emerald-500 to-cyan-600 hover:from-emerald-400 hover:to-cyan-500 text-white text-lg font-bold px-8 py-4 rounded-full shadow-lg shadow-teal-500/30 transition-all flex items-center gap-2"
            >
              Mulai Cari Sekarang 
              <span className="text-xl">→</span>
            </Link>
          </motion.div>
        </div>
      </section>

      {/* --- SECTION: Jenis Mesin & Bahan Bakar --- */}
      <section className="max-w-7xl mx-auto px-6 py-16">
        <div className="text-center mb-12">
            <h2 className="text-3xl md:text-4xl font-bold mb-4">
            Kenali Jenis Bahan Bakar
            </h2>
            <p className={`${isDark ? "text-gray-400" : "text-gray-600"}`}>
                Setiap jenis mesin memiliki karakter unik. Mana yang cocok untuk gaya hidup Anda?
            </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-6">
          {FUEL_DATA.map((fuel, index) => (
            <motion.div
              key={index}
              whileHover={{ y: -5 }}
              className={`rounded-3xl p-6 text-center shadow-xl transition-all border ${
                isDark
                  ? "bg-[#0c1214] border-teal-900/30 hover:border-teal-700/50"
                  : "bg-white border-teal-50 hover:border-teal-200"
              }`}
            >
              <div className={`flex justify-center mb-4 p-4 rounded-full w-20 h-20 mx-auto items-center ${
                  isDark ? "bg-teal-900/20" : "bg-teal-50"
              }`}>
                <FuelIcon 
                    iconKey={fuel.iconKey} 
                    className={`w-10 h-10 ${isDark ? "text-teal-400" : "text-teal-600"}`} 
                />
              </div>
              
              <h3 className={`font-bold text-lg mb-2 ${isDark ? "text-teal-200" : "text-teal-800"}`}>
                  {fuel.title}
              </h3>
              
              <p className={`text-sm leading-relaxed ${isDark ? "text-gray-400" : "text-gray-600"}`}>
                  {fuel.desc}
              </p>
            </motion.div>
          ))}
        </div>
      </section>
    </div>
  );
}