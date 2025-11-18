// src/hooks/useTheme.ts
"use client";

import { useState, useEffect } from "react";
import { Theme } from "@/types";

export function useTheme() {  // <- Tambah 'export' di sini
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    const saved = localStorage.getItem("theme") as Theme;
    if (saved) setTheme(saved);
  }, []);

  const toggleTheme = () => {
    setTheme((prev) => {
      const newTheme = prev === "dark" ? "light" : "dark";
      localStorage.setItem("theme", newTheme);
      return newTheme;
    });
  };

  return { theme, toggleTheme };
}

// Tambah ini jika masih error
export default useTheme;