"use client";
//components/forms/Header.tsx
import Link from "next/link";
import { Theme } from "@/types";
import Shuffle from "@/components/ui/Shuffle";

interface HeaderProps {
  theme: Theme;
  toggleTheme: () => void;
}

export function Header({ theme, toggleTheme }: HeaderProps) {
  const isDark = theme === "dark";

  return (
    <header
      className={`flex justify-between items-center px-8 py-5 shadow-sm sticky top-0 z-50 backdrop-blur-md transition-colors duration-300 ${
        isDark
          ? "bg-[#0a0a0a]/90 border-b border-white/5 shadow-teal-900/10"
          : "bg-white/90 border-b border-teal-50 shadow-teal-100/50"
      }`}
    >
      <div className="flex items-center gap-3">
        {/* Klik logo → kembali ke beranda (/) */}
        <Link
          href="/"
          aria-label="Kembali ke beranda"
          className="inline-flex items-center gap-3 group"
        >
          <Shuffle
            text="VRoom"
            shuffleDirection="right"
            duration={1}
            animationMode="evenodd"
            shuffleTimes={2}
            ease="back.out"
            stagger={0.02}
            threshold={0}
            rootMargin="0px"
            triggerOnce={false}
            triggerOnHover={true}
            loop={false}
            loopDelay={1}
            respectReducedMotion={true}
            // PERBAIKAN TEMA:
            // - Dark Mode: Putih (!text-white) agar kontras.
            // - Light Mode: Teal Gelap (!text-teal-700) agar sesuai tema Green-Blue tapi tetap terbaca jelas.
            className={`!text-2xl md:!text-3xl normal-case font-extrabold tracking-tight cursor-pointer select-none
              ${isDark ? "!text-teal-500" : "!text-teal-600"}`}
            style={{ textAlign: "left" }}
          />
        </Link>
      </div>

      <div className="flex items-center gap-4">
        <button
          onClick={toggleTheme}
          // PERBAIKAN TOMBOL: Style pill (rounded-full) dengan warna Teal
          className={`border px-4 py-2 rounded-full text-sm font-semibold transition flex items-center gap-2 ${
            isDark
              ? "border-black-800 bg-black-950/30 text-teal-100 hover:bg-black-900"
              : "border-black-200 bg-black-50 text-teal-800 hover:bg-black-100"
          }`}
          aria-label="Toggle tema"
          title="Toggle tema"
        >
          {isDark ? "🌙" : "☀️"}
        </button>
      </div>
    </header>
  );
}