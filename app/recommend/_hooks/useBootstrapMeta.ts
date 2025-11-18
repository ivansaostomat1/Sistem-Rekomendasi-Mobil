// app/recommend/_hooks/useBootstrapMeta.ts
"use client";

import { useCallback, useEffect, useState } from "react";
import { API_BASE } from "@/constants";
import type { MetaResponse } from "@/types";

type Ready = { specs: boolean; retail: boolean; wholesale: boolean };

export function useBootstrapMeta() {
  const [meta, setMeta] = useState<MetaResponse | null>(null);
  const [dataReady, setDataReady] = useState<Ready>({
    specs: false,
    retail: false,
    wholesale: false,
  });

  const refetchMeta = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/meta`, {
        method: "GET",
        cache: "no-store",
        headers: { "Cache-Control": "no-cache" },
      });
      if (!res.ok) throw new Error(await res.text());
      const j = (await res.json()) as MetaResponse;
      setMeta(j);
      setDataReady(j?.data_ready ?? { specs: false, retail: false, wholesale: false });
    } catch (e) {
      // diamkan saja; panel dev akan nunjukin status
    }
  }, []);

  useEffect(() => {
    refetchMeta();
  }, [refetchMeta]);

  return { meta, dataReady, refetchMeta };
}
