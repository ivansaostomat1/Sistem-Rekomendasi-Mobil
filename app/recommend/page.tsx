// file: app/recommend/page.tsx  
"use client";

import React, { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { motion, AnimatePresence } from "framer-motion";
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

// dynamic import Antigravity agar aman di Next.js SSR
const Antigravity = dynamic(() => import("@/components/ui/Antigravity"), { ssr: false });

const CHAT_ENABLED = true;

const fmtIDR = (n: number | string | null | undefined): string => {
    if (n == null || isNaN(Number(n))) return "N/A";
    const num = Math.round(Number(n));
    return new Intl.NumberFormat('id-ID', {
        style: 'currency',
        currency: 'IDR',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
    }).format(num).replace('Rp', 'Rp ');
};

export type ParsedConstraints = {
    budget: number | null;
    needs: string[] | null;
    filters: {
        brand: string | null;
        trans_choice: string | null;
        fuels: string[] | null;
    } | null;
};

export type ChatRecommendation = {
    budget: number;
    needs: string[];
    filters: {
        brand: string | null;
        trans_choice: string | null;
        fuels: string[] | null;
    };
    topn?: number;
    count: number;
    items: any[];
};

export type ChatbotApiResponse = {
    reply: string;
    suggested_questions?: string[];
    recommendation?: ChatRecommendation | null;
    parsed_constraints?: ParsedConstraints | null;
};

export default function RecommendPage() {
    const { theme, toggleTheme } = useTheme() as { theme: Theme; toggleTheme: () => void };

    // State Utama
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [data, setData] = useState<RecommendResponse | null>(null);
    const [isSearched, setIsSearched] = useState(false);

    // State Chat
    const [externalQuery, setExternalQuery] = useState<string | null>(null);
    const [chatConstraints, setChatConstraints] = useState<ParsedConstraints | null>(null);
    const [chatOpen, setChatOpen] = useState(false);

    // Data Helpers
    const { meta, dataReady, refetchMeta } = useBootstrapMeta();
    const formRef = useRef<HTMLDivElement | null>(null);
    const resultsRef = useRef<HTMLDivElement | null>(null);
    const { showForm, openForm, openResults } = useSearchFlow({ isSearched, loading, data, error, formRef, resultsRef });

    useEffect(() => { if (isSearched) openResults(); }, [isSearched, openResults]);

    const handleChatConstraints = (pc: ParsedConstraints | null) => { setChatConstraints(pc); };

    const handleChatRecommendation = (rec: ChatRecommendation | null) => {
        console.log("Chat Rec Payload:", rec);
        if (!rec || rec.count === 0 || !rec.items.length) {
            console.warn("Chat empty.");
            setData(null); setIsSearched(false); openForm(); return;
        }
        const mapped: RecommendResponse = { count: rec.count, items: rec.items, needs: rec.needs ?? [] };
        setData(mapped); setError(null); setIsSearched(true); openResults();
        setTimeout(() => { resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }); }, 100);
    };

    const handleCardClick = (item: RecommendItem) => {
        const brandModel = `${item.brand} ${item.model}`;
        const specs = [
            `Model: ${brandModel}`,
            item.price != null ? `Harga: ${fmtIDR(item.price)}` : null,
            item.trans ? `Trans: ${item.trans}` : null,
            (item as any).fuel_label ? `BBM: ${(item as any).fuel_label}` : null,
            item.seats ? `Kursi: ${item.seats}` : null,
            (item as any).cc_kwh ? `Mesin: ${(item as any).cc_kwh} cc` : null,
            (item as any).drive_sys ? `Penggerak: ${(item as any).drive_sys}` : null,
            (item as any)['DIMENSION P x L x T'] ? `Dimensi: ${(item as any)['DIMENSION P x L x T']}` : null,
            (item as any)['WHEEL BASE'] ? `Wheelbase: ${(item as any)['WHEEL BASE']} m` : null,
            item.fit_score != null ? `Total Score: ${item.fit_score.toFixed(4)}` : null,
        ].filter(Boolean).join(' | ');

        const activeNeeds = (data?.needs ?? []).join(", ").toUpperCase();

        const query = `[ANALISIS_KOMPARASI] Tolong jelaskan mengapa ${brandModel} (Skor: ${item.fit_score?.toFixed(4)}) berada di ranking ini? Fokus pada perbandingan harga dan fitur terhadap kebutuhan: [${activeNeeds}]. \n\nData Mobil: ${specs}`;

        setExternalQuery(query);
        if (CHAT_ENABLED) setChatOpen(true);
    };

    // deteksi mobile aman untuk SSR: gunakan state & effect
    const [isMobile, setIsMobile] = useState(false);
    useEffect(() => {
        const onResize = () => setIsMobile(window.innerWidth <= 768);
        onResize();
        window.addEventListener("resize", onResize);
        return () => window.removeEventListener("resize", onResize);
    }, []);
    const particleCount = isMobile ? 120 : 700;
    // warna partikel disesuaikan: dark => #38BDF8, light => #00a199ff
    const particleColor = theme === "dark" ? "#38BDF8" : "rgba(0, 114, 101, 1)";

    return (
        <div className={`min-h-screen transition-colors duration-300 ${theme === "dark" ? "bg-[#0a0a0a] text-gray-100" : "bg-gray-50 text-gray-900"}`}>
            <Header theme={theme} toggleTheme={toggleTheme} />

            {/* Wrap utama jadi relative agar background absolute bisa menempel */}
            <main className="w-full px-4 sm:px-8 lg:px-20 xl:px-30 py-8 relative overflow-hidden">
                {/* Antigravity background layer */}
                <div aria-hidden className="pointer-events-none absolute inset-0 z-0">
                    <Antigravity
                        count={particleCount}
                        magnetRadius={9}
                        ringRadius={10}
                        waveSpeed={0.2}
                        waveAmplitude={5}
                        particleSize={0.15}
                        lerpSpeed={0.35}
                        color={particleColor}
                        autoAnimate={true}
                        particleVariance={1}
                        rotationSpeed={0.5}
                        depthFactor={1}
                        pulseSpeed={5}
                        particleShape="capsule"
                        fieldStrength={0}
                    />
                </div>

                {/* Konten utama di atas background */}
                <div className="relative z-10">
                    <section className="mb-10">
                        <h1 className="text-4xl md:text-5xl font-extrabold leading-tight mb-4">
                            Cari mobil impianmu di{" "}
                            <span className="text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 via-teal-500 to-cyan-600">
                                VRoom
                            </span>
                        </h1>
                    </section>

                    <AnimatePresence mode="wait">
                        {showForm && (
                            <motion.section key="form" ref={formRef} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.35 }} className="mb-10">
                                <RecommendationForm theme={theme} loading={loading} error={error} data={data} meta={meta} isSearched={isSearched}
                                    setLoading={setLoading} setError={setError} setData={setData} setIsSearched={setIsSearched}
                                    // @ts-ignore
                                    chatConstraints={chatConstraints}
                                />
                            </motion.section>
                        )}
                    </AnimatePresence>

                    <AnimatePresence mode="wait">
                        {!showForm && (
                            <motion.section key="resultsView" ref={resultsRef} initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }} transition={{ duration: 0.35 }} className="px-0 pb-12">
                                <ResultsSection theme={theme} loading={loading} error={error} data={data}
                                    onBackToForm={() => { setIsSearched(false); setData(null); setError(null); refetchMeta(); openForm(); setTimeout(() => { formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }); }, 0); }}
                                    onCardClick={handleCardClick}
                                />
                            </motion.section>
                        )}
                    </AnimatePresence>

                    <DevPanel theme={theme} dataReady={dataReady} />
                </div>
            </main>

            {/* --- 3D MODEL VIEWER BUTTON (hanya render bila CHAT_ENABLED = true) --- */}
            {CHAT_ENABLED && (
                <div className="fixed bottom-0 right-0 z-50">
                    <ModelViewer
                        url="/288.glb"  // File HARUS ada di folder public
                        width={180}
                        height={180}
                        onClick={() => setChatOpen(true)} // Prop onClick diteruskan
                    />
                </div>
            )}

            {/* PANEL CHAT (hanya render bila chatOpen=true AND CHAT_ENABLED=true) */}
            {CHAT_ENABLED && chatOpen && (
                <div className="fixed bottom-24 right-8 z-50 w-[min(100%-2rem,420px)] sm:w-[420px] md:w-[440px]">
                    <SmartChatPanel
                        theme={theme}
                        onClose={() => setChatOpen(false)}
                        onChatRecommendation={handleChatRecommendation}
                        onChatConstraints={handleChatConstraints}
                        externalQuery={externalQuery}
                        setExternalQuery={setExternalQuery}
                    />
                </div>
            )}
        </div>
    );
}
