"use client";

import Link from "next/link";
import { Theme } from "@/types";
import Shuffle from "@/components/ui/Shuffle";

interface HeaderProps {
  theme: Theme;
  toggleTheme: () => void;
}

export function Header({ theme, toggleTheme }: HeaderProps) {
  return (
    <header
      className={`flex justify-between items-center px-8 py-5 shadow-md ${
        theme === "dark" ? "bg-[#1a1a1a] shadow-black/30" : "bg-white"
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
            threshold={0}        // langsung main saat terlihat
            rootMargin="0px"
            triggerOnce={false}  // boleh main ulang saat terlihat lagi
            triggerOnHover={true} // bisa dipicu ulang saat hover
            loop={false}         // TIDAK loop terus-menerus
            loopDelay={1}
            respectReducedMotion={true}
            className="!text-2xl md:!text-3xl normal-case font-extrabold tracking-tight
                       !text-gray-900 dark:!text-white cursor-pointer select-none"
            style={{ textAlign: "left" }}
          />
        </Link>
      </div>

      <div className="flex items-center gap-4">
        <button
          onClick={toggleTheme}
          className={`border px-4 py-2 rounded-lg text-sm font-semibold transition ${
            theme === "dark"
              ? "border-gray-700 hover:bg-[#2a2a2a]"
              : "border-gray-300 hover:bg-gray-100"
          }`}
          aria-label="Toggle tema"
          title="Toggle tema"
        >
          {theme === "dark" ? "☀️" : "🌑"}
        </button>
      </div>
    </header>
  );
}
