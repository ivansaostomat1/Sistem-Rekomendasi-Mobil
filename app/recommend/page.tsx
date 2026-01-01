// app/recommend/page.tsx
"use client";

import React, { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { motion, AnimatePresence, useDragControls } from "framer-motion"; // Import useDragControls
import { useTheme } from "@/hooks/useTheme";
import { Header } from "@/components/forms/Header";
import { RecommendationForm } from "@/components/forms/index";
import type { RecommendResponse, RecommendItem } from "@/types";
import { useBootstrapMeta } from "./_hooks/useBootstrapMeta";
import { useSearchFlow } from "./_hooks/useSearchFlow";
import { ResultsSection } from "./_components/ResultSection";
import { DevPanel } from "./_components/DevPanel";
import type { Theme } from "./_types/theme";
import SmartChatPanel from "./_components/ChatPanel";
import ModelViewer from "@/components/ui/ModelViewer";

// Dynamic Import
const Antigravity = dynamic(() => import("@/components/ui/Antigravity"), { ssr: false });

const CHAT_ENABLED = true;

const fmtIDR = (n: number | string | null | undefined): string => {
    if (n == null || isNaN(Number(n))) return "N/A";
    const num = Math.round(Number(n));
    return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(num).replace('Rp', 'Rp ');
};

export type ParsedConstraints = {
    budget: number | null;
    needs: string[] | null;
    filters: { brand: string | null; trans_choice: string | null; fuels: string[] | null; } | null;
};

export type ChatRecommendation = {
    budget: number; needs: string[]; filters: any; count: number; items: any[];
};

export type ChatbotApiResponse = {
    reply: string; recommendation?: ChatRecommendation | null; parsed_constraints?: ParsedConstraints | null; state?: any;
};

export default function RecommendPage() {
    const { theme, toggleTheme } = useTheme() as { theme: Theme; toggleTheme: () => void };
    const constraintsRef = useRef(null);
    const dragControls = useDragControls(); // Inisialisasi Drag Controls
    const chatInitialY = useRef<number | null>(null);

    // State Utama
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [data, setData] = useState<RecommendResponse | null>(null);
    const [isSearched, setIsSearched] = useState(false);

    // State Chat
    const [externalQuery, setExternalQuery] = useState<string | null>(null);
    const [chatOpen, setChatOpen] = useState(false);

    // Data Helpers
    const { meta, dataReady, refetchMeta } = useBootstrapMeta();
    const formRef = useRef<HTMLDivElement | null>(null);
    const resultsRef = useRef<HTMLDivElement | null>(null);
    const { showForm, openForm, openResults } = useSearchFlow({ isSearched, loading, data, error, formRef, resultsRef });

    useEffect(() => { if (isSearched) openResults(); }, [isSearched, openResults]);

    // Handle Rekomendasi dari Chat
    const handleChatRecommendation = (rec: ChatRecommendation | null) => {
        if (!rec || rec.count === 0 || !rec.items.length) {
            setData(null); setIsSearched(false); openForm(); return;
        }
        const mapped: RecommendResponse = { count: rec.count, items: rec.items, needs: rec.needs ?? [] };
        setData(mapped); setError(null); setIsSearched(true); openResults();
        setTimeout(() => { resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }); }, 100);
    };

    // Handle Klik Kartu
    const handleCardClick = (item: RecommendItem) => {
        const brandModel = `${item.brand} ${item.model}`;
        const query = `[ANALISIS] Tolong jelaskan kenapa ${brandModel} (Harga: ${fmtIDR(item.price)}) cocok untuk saya?`;
        setExternalQuery(query);
        if (CHAT_ENABLED) setChatOpen(true);
    };

    const [isMobile, setIsMobile] = useState(false);
    useEffect(() => {
        const onResize = () => setIsMobile(window.innerWidth <= 768);
        onResize();
        window.addEventListener("resize", onResize);
        return () => window.removeEventListener("resize", onResize);
    }, []);

    return (
        <div ref={constraintsRef} className={`min-h-screen transition-colors duration-300 relative overflow-hidden ${theme === "dark" ? "bg-[#0a0a0a] text-gray-100" : "bg-gray-50 text-gray-900"}`}>

            <Header theme={theme} toggleTheme={toggleTheme} />

            <main className="w-full px-4 sm:px-8 lg:px-20 xl:px-30 py-8 relative z-10">
                <section className="mb-10">
                    <h1 className="text-4xl md:text-5xl font-extrabold leading-tight mb-4">
                        Cari mobil impianmu di <span className="text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 via-teal-500 to-cyan-600">VRoom</span>
                    </h1>
                </section>

                <AnimatePresence mode="wait">
                    {showForm && (
                        <motion.section key="form" ref={formRef} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.35 }} className="mb-10">
                            <RecommendationForm theme={theme} loading={loading} error={error} data={data} meta={meta} isSearched={isSearched}
                                setLoading={setLoading} setError={setError} setData={setData} setIsSearched={setIsSearched}
                            />
                        </motion.section>
                    )}
                </AnimatePresence>

                <AnimatePresence mode="wait">
                    {!showForm && (
                        <motion.section key="resultsView" ref={resultsRef} initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }} transition={{ duration: 0.35 }} className="px-0 pb-12">
                            <ResultsSection theme={theme} loading={loading} error={error} data={data}
                                onBackToForm={() => { setIsSearched(false); setData(null); setError(null); refetchMeta(); openForm(); }}
                                onCardClick={handleCardClick}
                            />
                        </motion.section>
                    )}
                </AnimatePresence>

                <DevPanel theme={theme} dataReady={dataReady} />
            </main>

            <div aria-hidden className="pointer-events-none absolute inset-0 z-0">
                <Antigravity count={isMobile ? 120 : 700} magnetRadius={9} ringRadius={10} waveSpeed={0.2} waveAmplitude={5} particleSize={0.15} lerpSpeed={0.35} color={theme === "dark" ? "#38BDF8" : "rgba(0, 114, 101, 1)"} autoAnimate={true} particleVariance={1} rotationSpeed={0.5} depthFactor={1} pulseSpeed={5} particleShape="capsule" fieldStrength={0} />
            </div>

            {/* --- FITUR FLOATING --- */}

            {/* 1. TOMBOL 3D (FIXED - TIDAK BISA DIGESER) */}
            {CHAT_ENABLED && (
                <div className="fixed bottom-0 right-0 z-50 cursor-pointer">
                    <ModelViewer
                        url="/288.glb"
                        width={180}
                        height={180}
                        onClick={() => setChatOpen(prev => !prev)}
                    />
                </div>
            )}

            {/* 2. PANEL CHAT (DRAGGABLE & RESIZABLE) */}
            {CHAT_ENABLED && (
                <motion.div
                    drag={!isMobile}
                    dragListener={!isMobile}
                    dragControls={dragControls}
                    dragMomentum={false}
                    dragConstraints={
                        isMobile
                            ? undefined
                            : {
                                top: -1000, // boleh ke atas (besar supaya bebas)
                                bottom: 0,  // ❗ TIDAK BOLEH ke bawah
                                left: -1000,
                                right: 1000,
                            }
                    }
                    onDragStart={(e, info) => {
                        if (chatInitialY.current === null) {
                            chatInitialY.current = info.point.y;
                        }
                    }}
                    style={{
                        y: 0, // posisi default dianggap titik nol
                    }}
                    initial={{ opacity: 0, y: 20, scale: 0.95 }}
                    animate={{
                        opacity: chatOpen ? 1 : 0,
                        y: chatOpen ? 0 : 20,
                        scale: chatOpen ? 1 : 0.95,
                        display: chatOpen ? "block" : "none",
                    }}
                    transition={{ duration: 0.2 }}
                    className={
                        isMobile
                            ? "fixed inset-0 z-50"
                            : "fixed bottom-24 right-8 z-50 w-auto h-auto"
                    }
                >

                    <SmartChatPanel
                        theme={theme}
                        onClose={() => setChatOpen(false)}
                        onChatRecommendation={handleChatRecommendation}
                        externalQuery={externalQuery}
                        setExternalQuery={setExternalQuery}
                        dragControls={dragControls}
                        isMobile={isMobile}
                    />
                </motion.div>

            )}

        </div>
    );
}