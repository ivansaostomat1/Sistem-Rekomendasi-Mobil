"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import Shuffle from "@/components/ui/Shuffle";
import { FuelIcon } from "@/components/icons/FuelIcons";
import { FUEL_DATA } from "@/constants";
import { useTheme } from "@/hooks/useTheme";

export default function HomePage() {
  /**
   * @returns {JSX.Element} The rendered JSX element.
   */
  const { theme, toggleTheme } = useTheme();

  return (
    <div className={`min-h-screen transition-colors duration-300 ${theme === "dark" ? "bg-black text-white" : "bg-gray-50 text-gray-900"}`}>
      {/* HEADER */}

      <header
  className={`flex justify-between items-center px-8 py-4 shadow-md ${
    theme === "dark" ? "bg-[#111] shadow-black/30" : "bg-white shadow-gray-100"
  }`}
>
   <div className="flex items-center gap-3">
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
      className="!text-2xl md:!text-3xl normal-case font-extrabold tracking-tight
                 !text-gray-900 dark:!text-white"
      style={{ textAlign: "left" }}
    />
  </div>
  </div>

  <button
    onClick={toggleTheme}
    className={`border px-4 py-2 rounded-lg text-sm font-semibold transition ${
      theme === "dark"
        ? "border-gray-700 bg-gray-800 hover:bg-gray-700"
        : "border-gray-300 hover:bg-gray-100"
    }`}
  >
    {theme === "dark" ? "☀️" : "🌑"}
  </button>
</header>



      {/* HERO SECTION */}
      <section className="text-center py-20 px-6">
        <h1 className="text-5xl md:text-6xl font-extrabold leading-tight">
          Temukan Mobil Impianmu.
          <br />
          Pahami Jenisnya, Rasakan Kenyamanannya.
        </h1>
        <p className={`${theme === "dark" ? "text-gray-300" : "text-gray-700"} mt-4`}>
          Bingung pilih Bensin, Diesel, atau Mobil Listrik? Kami akan kasih solusi terbaik.
        </p>

        <motion.div
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          className="inline-block mt-8"
        >
          <Link
            href="/recommend"
            className="bg-orange-400 text-white font-semibold px-6 py-3 rounded-lg shadow-md hover:shadow-orange-500/50 transition"
          >
            Mulai Cari Sekarang →
          </Link>
        </motion.div>
      </section>

      {/* SECTION: Jenis Mesin & Bahan Bakar */}
      <section className="max-w-6xl mx-auto px-6 py-12">
        <h2 className="text-2xl md:text-3xl font-bold text-center mb-8">
          Jenis-jenis Mesin & Bahan Bakar
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-6">
          {FUEL_DATA.map((fuel, index) => (
            <motion.div
              key={index}
              whileHover={{ scale: 1.05 }}
              className={`rounded-2xl p-6 text-center shadow-lg transition-all ${theme === "dark" ? "bg-[#111] border border-gray-800" : "bg-white border border-gray-200"}`}
            >
              <div className="flex justify-center mb-3">
                <FuelIcon iconKey={fuel.iconKey} className="w-12 h-12 text-orange-400" />
              </div>
              <h3 className="text-orange-400 font-semibold">{fuel.title}</h3>
              <p className={`text-sm ${theme === "dark" ? "text-gray-300" : "text-gray-700"} mt-2`}>{fuel.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>
    </div>
  );
}