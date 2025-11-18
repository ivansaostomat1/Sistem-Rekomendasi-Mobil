// app/recommend/_hooks/useSearchFlow.ts
"use client";

import { useCallback, useEffect, useState, RefObject } from "react";
import type { RecommendResponse } from "@/types";

export function useSearchFlow({
  isSearched,
  loading,
  data,
  error,
  formRef,
  resultsRef,
}: {
  isSearched: boolean;
  loading: boolean;
  data: RecommendResponse | null;
  error: string | null;
  formRef: RefObject<HTMLDivElement | null>;
  resultsRef: RefObject<HTMLDivElement | null>;
}) {
  const [showForm, setShowForm] = useState(true);

  const openForm = useCallback(() => {
    setShowForm(true);
  }, []);

  const openResults = useCallback(() => {
    setShowForm(false);
  }, []);

  // Saat isSearched = true → pindah ke hasil
  useEffect(() => {
    if (isSearched) setShowForm(false);
  }, [isSearched]);

  // Auto-scroll ke hasil ketika konten hasil siap/berubah
  useEffect(() => {
    if (!showForm && (loading || data || error)) {
      resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [showForm, loading, data, error, resultsRef]);

  return { showForm, openForm, openResults };
}
