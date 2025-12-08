"use client";

import React, { useEffect, useRef, useState } from "react";
import type { Theme } from "../_types/theme";
import { API_BASE } from "@/constants";
import type { ChatRecommendation, ChatbotApiResponse, ParsedConstraints } from "../page";

// Tipe Message Manual
type Message = { from: 'user' | 'bot'; text: string };

type ChatPanelProps = {
    theme: Theme;
    onClose: () => void;
    onChatRecommendation?: (rec: ChatRecommendation | null) => void;
    onChatConstraints?: (pc: ParsedConstraints | null) => void;
    externalQuery?: string | null;
    setExternalQuery?: React.Dispatch<React.SetStateAction<string | null>>;
};

export default function SmartChatPanel({
    theme,
    onClose,
    onChatRecommendation,
    onChatConstraints,
    externalQuery,
    setExternalQuery
}: ChatPanelProps) {
    const isDark = theme === "dark";
    
    // --- STATE MANAGEMENT ---
    const [messages, setMessages] = useState<Message[]>([
         { from: 'bot', text: "Hai! Saya AI VRoom. Tanyakan rekomendasi mobil atau **klik gambar mobil** di hasil rekomendasi untuk analisis detail." }
    ]);
    const [input, setInput] = useState("");
    const [isSending, setIsSending] = useState(false);
    const [suggested] = useState(["Cari mobil keluarga 300jt", "Mobil irit buat dalam kota", "SUV tangguh buat offroad"]);
    const listRef = useRef<HTMLDivElement | null>(null);
    const textareaRef = useRef<HTMLTextAreaElement | null>(null);
    const lastAutoMsgTime = useRef<number>(0);

    // Auto Scroll
    useEffect(() => {
        if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
    }, [messages]);

    // Auto Resize Textarea
    useEffect(() => {
        const el = textareaRef.current;
        if (!el) return;
        el.style.height = "0px";
        const base = 40; 
        const newHeight = Math.max(base, el.scrollHeight);
        el.style.height = `${newHeight}px`;
    }, [input]);

    // External Trigger
    useEffect(() => {
        if (externalQuery && setExternalQuery) {
            const now = Date.now();
            if (now - lastAutoMsgTime.current > 1000) {
                handleSend(externalQuery);
                lastAutoMsgTime.current = now;
                setExternalQuery(null);
            }
        }
    }, [externalQuery, setExternalQuery]);

    const handleSend = async (text?: string) => {
        const final = (text ?? input).trim();
        if (!final || isSending) return;

        // Clean internal prompt
        let uiText = final;
        if (final.includes('[ANALISIS_KOMPARASI]') || final.includes('[ANALISIS_RANKING]')) {
            try {
                const match = final.match(/\((.*?)\)\./); 
                if (match && match[1]) {
                    uiText = `Bagaimana pendapatmu soal ${match[1]}?`;
                } else {
                    uiText = "Tolong analisis mobil ini.";
                }
            } catch (e) {
                uiText = "Tolong analisis mobil ini.";
            }
        }

        setMessages(prev => [...prev, { from: 'user', text: uiText }]);
        setInput("");
        setIsSending(true);

        try {
            const res = await fetch(`${API_BASE}/chat`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: final }),
            });
            if (!res.ok) throw new Error("Gagal");
            const json = (await res.json()) as ChatbotApiResponse;
            const reply = json.reply || "Maaf, error.";

            setMessages(prev => [...prev, { from: 'bot', text: reply }]);
            
            if (json.parsed_constraints && onChatConstraints) onChatConstraints(json.parsed_constraints);
            if (json.recommendation && onChatRecommendation) onChatRecommendation(json.recommendation);

        } catch (e) {
            setMessages(prev => [...prev, { from: 'bot', text: "Maaf, ada gangguan koneksi." }]);
        } finally {
            setIsSending(false);
        }
    };

    const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    return (
        <div className={`rounded-2xl flex flex-col h-[500px] w-full shadow-2xl overflow-hidden border ${
            isDark ? "bg-[#0a1014] border-teal-900/50" : "bg-white border-teal-100"
        }`}>
            {/* Header: Gradient Emerald -> Cyan */}
            <div className="px-4 py-3 bg-gradient-to-r from-emerald-600 to-cyan-600 text-white flex justify-between items-center shadow-md">
                <div className="flex flex-col gap-0.5">
                    <span className="text-[10px] uppercase opacity-80 tracking-wider font-semibold">AI Assistant</span>
                    <span className="text-sm font-bold">VRoom Chat</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="flex items-center justify-center w-7 h-7 rounded-full bg-white/20 backdrop-blur-sm text-[10px] font-bold text-white shadow-sm">
                        AI
                    </div>
                    <button onClick={onClose} className="w-7 h-7 hover:bg-white/20 rounded-full flex items-center justify-center transition">✕</button>
                </div>
            </div>

            {/* Chat Area */}
            <div ref={listRef} className={`flex-1 overflow-y-auto p-4 space-y-3 ${
                 isDark ? "bg-[#0c1619]" : "bg-slate-50"
            }`}>
                {messages.map((m, i) => {
                    const isUser = m.from === 'user';
                    return (
                        <div key={i} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
                            <div className={`max-w-[85%] px-3.5 py-2.5 rounded-2xl text-xs sm:text-sm leading-relaxed shadow-sm ${
                                isUser 
                                    // BUBBLE USER: Emerald -> Cyan
                                    ? "bg-gradient-to-br from-emerald-500 to-cyan-600 text-white rounded-br-sm" 
                                    : isDark 
                                        // BUBBLE BOT: Teal Dark
                                        ? "bg-[#162a2b] text-teal-50 border border-teal-900/50 rounded-bl-sm" 
                                        // BUBBLE BOT: Teal Light
                                        : "bg-emerald-200 border border-teal-100 text-slate-700 rounded-bl-sm"
                            }`}>
                                {m.text}
                            </div>
                        </div>
                    )
                })}
                {isSending && <div className="text-xs text-center opacity-50 animate-zoom mt-2">Sedang berpikir...</div>}
            </div>

            

            {/* Input Area */}
            <div className={`p-3 border-t ${isDark ? "border-white/10 bg-[#0a1014]" : "border-gray-100 bg-white"}`}>
                <div className="flex gap-2">
                    <textarea 
                        ref={textareaRef}
                        className={`flex-1 rounded-xl px-4 py-3 text-xs sm:text-sm outline-none border focus:ring-2 focus:ring-teal-500/50 transition ${
                            isDark ? "bg-[#132226] border-teal-900 text-emerald-100 placeholder:text-teal-700" : "bg-emerald-200 border-gray-200 text-gray-900 placeholder:text-gray-900"
                        }`}
                        placeholder="Ketik pesan..."
                        rows={1}
                        style={{ resize: "none", overflowY: "hidden", minHeight: "44px" }}
                        value={input}
                        onChange={e => setInput(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && handleSend()}
                    />
                    <button 
                        onClick={() => handleSend()}
                        disabled={!input.trim() || isSending}
                        // TOMBOL KIRIM: Emerald -> Cyan
                        className={`h-[44px] w-[44px] rounded-xl flex items-center justify-center transition shadow-md ${
                            !input.trim() || isSending
                            ? "bg-gray-200 text-gray-400 cursor-not-allowed dark:bg-cyan-600 dark:text-emerald-100"
                            : "bg-gradient-to-br from-emerald-500 to-cyan-600 text-white hover:scale-105 active:scale-95"
                        }`}
                    >
                        ➤
                    </button>
                </div>
            </div>
        </div>
    );
}