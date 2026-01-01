"use client";

import React, { useEffect, useRef, useState } from "react";
import { API_BASE } from "@/constants";
import type { ChatRecommendation, ParsedConstraints } from "../page";
import type { Theme } from "../_types/theme";
import { DragControls } from "framer-motion";

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
  onChatConstraints?: (pc: ParsedConstraints | null) => void;
  externalQuery?: string | null;
  setExternalQuery?: React.Dispatch<React.SetStateAction<string | null>>;
  dragControls?: DragControls;
  isMobile?: boolean;
};

const loadingTexts = [
  "Mencocokkan kebutuhan Anda...",
  "Menyaring mobil terbaik...",
  "Menganalisa spesifikasi & harga...",
  "Menghitung kecocokan penggunaan...",
];

export default function SmartChatPanel({
  theme,
  onClose,
  onChatRecommendation,
  externalQuery,
  setExternalQuery,
  dragControls,
  isMobile = false,
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

  const [showResizeHint, setShowResizeHint] = useState(() => {
    if (typeof window === "undefined") return false;
    return !localStorage.getItem("vroom_resize_hint_seen");
  });

  const listRef = useRef<HTMLDivElement | null>(null);

  /* --- LOAD STORAGE --- */
  useEffect(() => {
    const savedMsgs = localStorage.getItem("vroom_msgs");
    const savedState = localStorage.getItem("vroom_state");

    if (savedMsgs) {
      setMessages(JSON.parse(savedMsgs));
    } else {
      setMessages([
        {
          from: "bot",
          text: "Halo Kak! 👋 Saya AI VRoom. Mau cari mobil apa nih? Ketik 'Mulai' atau sebutkan budget Anda.",
        },
      ]);
    }

    if (savedState) {
      setChatState(JSON.parse(savedState));
    }
  }, []);

  /* --- SAVE STORAGE --- */
  useEffect(() => {
    if (messages.length > 0)
      localStorage.setItem("vroom_msgs", JSON.stringify(messages));
  }, [messages]);

  useEffect(() => {
    localStorage.setItem("vroom_state", JSON.stringify(chatState));
  }, [chatState]);

  /* --- AUTO SCROLL --- */
  useEffect(() => {
    listRef.current?.scrollTo({
      top: listRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, isSending]);

  /* --- EXTERNAL QUERY --- */
  useEffect(() => {
    if (externalQuery && setExternalQuery) {
      handleSend(externalQuery);
      setExternalQuery(null);
    }
  }, [externalQuery, setExternalQuery]);

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

      if (!res.ok) throw new Error("error");
      const json = await res.json();

      setMessages((p) => [...p, { from: "bot", text: json.reply }]);
      if (json.state) setChatState(json.state);
      if (json.recommendation && onChatRecommendation) {
        onChatRecommendation(json.recommendation);
      }
    } catch {
      setMessages((p) => [
        ...p,
        { from: "bot", text: "Maaf, terjadi gangguan koneksi." },
      ]);
    } finally {
      setIsSending(false);
    }
  };

  const handleReset = () => {
    localStorage.removeItem("vroom_msgs");
    localStorage.removeItem("vroom_state");
    setMessages([
      {
        from: "bot",
        text: "Chat direset. Silakan mulai ulang dengan menyebutkan kebutuhan Anda.",
      },
    ]);
    setChatState({ budget: null, needs: [], filters: {}, step: "INIT" });
  };

  /* --- RESIZE HINT DISMISS --- */
  useEffect(() => {
    if (!isMobile && showResizeHint) {
      const t = setTimeout(() => {
        localStorage.setItem("vroom_resize_hint_seen", "1");
        setShowResizeHint(false);
      }, 4000);
      return () => clearTimeout(t);
    }
  }, [showResizeHint, isMobile]);

  return (
    <div
      className={`relative rounded-2xl flex flex-col shadow-2xl border ${
        isDark ? "bg-[#0a1014] border-teal-900/50" : "bg-white border-teal-100"
      }`}
      style={{
        resize: isMobile ? "none" : "both",
        minHeight: isMobile ? "100%" : "500px",
        minWidth: isMobile ? "100%" : "420px",
        width: "100%",
        height: "100%",
        overflow: "hidden",
      }}
    >
      {/* HEADER (DRAG HANDLE) */}
      <div
        onPointerDown={(e) => !isMobile && dragControls?.start(e)}
        className="px-4 py-3 bg-gradient-to-r from-emerald-600 to-cyan-600 text-white flex justify-between items-center cursor-grab active:cursor-grabbing select-none"
      >
        <div className="text-sm font-bold pointer-events-none">
          AI VRoom Assistant
        </div>
        <div
          className="flex gap-2"
          onPointerDown={(e) => e.stopPropagation()}
        >
          <button
            onClick={handleReset}
            title="Hapus percakapan & mulai ulang rekomendasi"
            className="text-[10px] bg-white/20 px-2 rounded hover:bg-white/30"
          >
            ↻ Ulangi Chat
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

      {/* RESIZE AFFORDANCE */}
      {!isMobile && (
        <>
          <div className="absolute bottom-1 right-1 opacity-70 pointer-events-none">
            <div
              className={`w-4 h-4 border-r-2 border-b-2 ${
                isDark ? "border-teal-400/70" : "border-teal-600/60"
              }`}
            />
          </div>

          {showResizeHint && (
            <div className="absolute bottom-6 right-6 text-[10px] bg-black/70 text-white px-2 py-1 rounded">
              Tarik sudut untuk ubah ukuran
            </div>
          )}
        </>
      )}
    </div>
  );
}
