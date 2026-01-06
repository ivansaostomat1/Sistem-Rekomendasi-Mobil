"use client";

import React, { useEffect, useRef, useState } from "react";
import { API_BASE } from "@/constants";
import type { ChatRecommendation } from "../page";
import type { Theme } from "../_types/theme";

/* ================== TYPES ================== */

type Message = { from: "user" | "bot"; text: string };

type ConversationState = {
  budget: number | null;
  needs: string[];
  filters: any;
  step: string;
};

type ChatPanelProps = {
  theme: Theme;
  onClose: () => void;
  onChatRecommendation?: (rec: ChatRecommendation | null) => void;
  externalQuery?: string | null;
  setExternalQuery?: React.Dispatch<React.SetStateAction<string | null>>;
  isMobile?: boolean;
};

/* ================== UTILS ================== */

function fmtIDR(v?: number | null) {
  if (!v || !isFinite(v)) return "-";
  return new Intl.NumberFormat("id-ID", {
    style: "currency",
    currency: "IDR",
    maximumFractionDigits: 0,
  }).format(v);
}

const loadingTexts = [
  "Mencocokkan kebutuhan Anda...",
  "Menyaring mobil terbaik...",
  "Menganalisa spesifikasi & harga...",
  "Menghitung kecocokan penggunaan...",
];

/* ================== COMPONENT ================== */

export default function ChatPanel({
  theme,
  onClose,
  onChatRecommendation,
  externalQuery,
  setExternalQuery,
}: ChatPanelProps) {
  const isDark = theme === "dark";

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [loadingText, setLoadingText] = useState(loadingTexts[0]);

  const [chatState, setChatState] = useState<ConversationState>({
    budget: null,
    needs: [],
    filters: {},
    step: "INIT",
  });

  const listRef = useRef<HTMLDivElement | null>(null);

  /* ---------- LOAD STORAGE ---------- */
  useEffect(() => {
    const savedMsgs = localStorage.getItem("vroom_msgs");
    const savedState = localStorage.getItem("vroom_state");

    if (savedMsgs) {
      setMessages(JSON.parse(savedMsgs));
    } else {
      setMessages([
        {
          from: "bot",
          text:
            "Halo Kak! 👋 Saya AI VRoom.\n" +
            "Mau cari mobil apa nih? Sebutkan budget atau ketik *Mulai*.",
        },
      ]);
    }

    if (savedState) {
      setChatState(JSON.parse(savedState));
    }
  }, []);

  /* ---------- SAVE STORAGE ---------- */
  useEffect(() => {
    localStorage.setItem("vroom_msgs", JSON.stringify(messages));
  }, [messages]);

  useEffect(() => {
    localStorage.setItem("vroom_state", JSON.stringify(chatState));
  }, [chatState]);

  /* ---------- AUTO SCROLL ---------- */
  useEffect(() => {
    listRef.current?.scrollTo({
      top: listRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, isSending]);

  /* ---------- EXTERNAL QUERY ---------- */
  useEffect(() => {
    if (externalQuery && setExternalQuery) {
      handleSend(externalQuery);
      setExternalQuery(null);
    }
  }, [externalQuery, setExternalQuery]);

  /* ================== SEND ================== */

  const handleSend = async (text?: string) => {
    const final = (text ?? input).trim();
    if (!final || isSending) return;

    setMessages((p) => [...p, { from: "user", text: final }]);
    setInput("");
    setIsSending(true);
    setLoadingText(
      loadingTexts[Math.floor(Math.random() * loadingTexts.length)]
    );

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: final, state: chatState }),
      });

      if (!res.ok) throw new Error("API Error");

      const json = await res.json();

      /* ===== CLEAR / RESET VIA CHAT ===== */
      const cmd = final.toLowerCase();
      if (
        cmd === "clear" ||
        cmd === "reset" ||
        cmd === "ulangi" ||
        cmd === "mulai baru"
      ) {
        localStorage.removeItem("vroom_msgs");
        localStorage.removeItem("vroom_state");

        setMessages([{ from: "bot", text: json.reply }]);

        if (json.state) setChatState(json.state);

        setIsSending(false);
        return; // ⬅️ STOP FLOW NORMAL
      }

      /* ===== NORMAL BOT REPLY ===== */
      setMessages((p) => [...p, { from: "bot", text: json.reply }]);

      if (json.state) setChatState(json.state);

      /* ===== RECOMMENDATION ===== */
      if (json.recommendation) {
        onChatRecommendation?.(json.recommendation);

        const items = json.recommendation.items ?? [];
        if (items.length > 0) {
          const summary = items
            .slice(0, 3)
            .map(
              (it: any, i: number) =>
                `${i + 1}. ${it.brand} ${it.model} (${fmtIDR(it.price)})`
            )
            .join("\n");

          setMessages((p) => [
            ...p,
            {
              from: "bot",
              text:
                "🚗 Rekomendasi terbaik:\n\n" +
                summary +
                "\n\nDetail lengkap ada di panel hasil.",
            },
          ]);
        }
      }
    } catch {
      setMessages((p) => [
        ...p,
        { from: "bot", text: "Maaf, terjadi gangguan koneksi 😵‍💫" },
      ]);
    } finally {
      setIsSending(false);
    }
  };

  /* ---------- BUTTON RESET ---------- */
  const handleReset = async () => {
    localStorage.removeItem("vroom_msgs");
    localStorage.removeItem("vroom_state");

    setMessages([{ from: "bot", text: "Chat direset 🔄" }]);
    setChatState({ budget: null, needs: [], filters: {}, step: "INIT" });

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: "reset", state: null }),
      });

      if (!res.ok) throw new Error("reset error");

      const json = await res.json();

      setMessages((p) => [...p, { from: "bot", text: json.reply }]);
      if (json.state) setChatState(json.state);
    } catch {
      setMessages((p) => [
        ...p,
        {
          from: "bot",
          text:
            "Halo Kak! 👋 Saya AI VRoom siap bantu.\n" +
            "🤔 Kira-kira budget maksimal berapa ya?",
        },
      ]);
    }
  };

  /* ================== RENDER ================== */

  return (
    <div
      className={`relative rounded-2xl flex flex-col shadow-2xl border ${
        isDark ? "bg-[#0a1014] border-teal-900/50" : "bg-white border-teal-100"
      }`}
      style={{
        width: "100%",
        height: "100%",
        minHeight: "520px",
        overflow: "hidden",
      }}
    >
      {/* HEADER */}
      <div className="px-4 py-3 bg-gradient-to-r from-emerald-600 to-cyan-600 text-white flex justify-between items-center select-none">
        <div className="text-sm font-bold">AI VRoom Assistant</div>
        <div className="flex gap-2">
          <button
            onClick={handleReset}
            className="text-[10px] bg-white/20 px-2 rounded hover:bg-white/30"
          >
            ↻ Reset
          </button>
          <button
            onClick={onClose}
            className="w-6 h-6 hover:bg-white/20 rounded-full"
          >
            ✕
          </button>
        </div>
      </div>

      {/* CHAT LIST */}
      <div
        ref={listRef}
        className={`flex-1 overflow-y-auto p-4 space-y-3 ${
          isDark ? "bg-[#0c1619]" : "bg-slate-50"
        }`}
      >
        {messages.map((m, i) => (
          <div
            key={i}
            className={`flex ${
              m.from === "user" ? "justify-end" : "justify-start"
            }`}
          >
            <div
              className={`max-w-[72%] px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed shadow-sm whitespace-pre-wrap ${
                m.from === "user"
                  ? "bg-gradient-to-br from-emerald-500 to-cyan-600 text-white rounded-br-sm"
                  : isDark
                  ? "bg-[#162a2b] text-teal-50 border border-teal-900/50 rounded-bl-sm"
                  : "bg-emerald-200 border border-teal-100 text-slate-700 rounded-bl-sm"
              }`}
            >
              {m.text}
            </div>
          </div>
        ))}

        {isSending && (
          <div className="flex items-center gap-2 text-xs italic opacity-70 animate-pulse">
            <span>🤔</span>
            <span>{loadingText}</span>
          </div>
        )}
      </div>

      {/* INPUT */}
      <div
        className={`p-3 border-t ${
          isDark ? "border-white/10 bg-[#0a1014]" : "border-gray-100 bg-white"
        }`}
      >
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Ketik pesan..."
            className={`flex-1 rounded-xl px-4 py-3 text-sm outline-none border focus:ring-2 focus:ring-teal-500/50 ${
              isDark
                ? "bg-[#132226] border-teal-900 text-emerald-100"
                : "bg-emerald-50 border-gray-200"
            }`}
          />
          <button
            onClick={() => handleSend()}
            disabled={!input.trim() || isSending}
            className="w-[44px] h-[44px] rounded-xl bg-gradient-to-br from-emerald-500 to-cyan-600 text-white"
          >
            ➤
          </button>
        </div>
      </div>
    </div>
  );
}
