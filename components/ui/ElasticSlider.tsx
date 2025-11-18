"use client";

import React, { useRef, useMemo, useCallback } from "react";
import {
  animate,
  motion,
  useMotionValue,
  useMotionValueEvent,
  useTransform,
} from "framer-motion";

const MAX_OVERFLOW = 50;

type ThemeMode = "dark" | "light";

export type ElasticSliderProps = {
  value: number;                // <-- WAJIB number (bukan undefined)
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
  theme: ThemeMode;             // "dark" | "light"
  className?: string;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  ariaLabel?: string;
};

function clamp(n: number, min: number, max: number) {
  return Math.min(Math.max(n, min), max);
}

function decay(value: number, max: number): number {
  if (max === 0) return 0;
  const entry = value / max;
  const sig = 2 * (1 / (1 + Math.exp(-entry)) - 0.5);
  return sig * max;
}

export default function ElasticSlider({
  value,
  min,
  max,
  step = 1,
  onChange,
  theme,
  className = "",
  leftIcon = <>➖</>,
  rightIcon = <>➕</>,
  ariaLabel = "slider",
}: ElasticSliderProps) {
  const sliderRef = useRef<HTMLDivElement>(null);
  const clientX = useMotionValue(0);
  const overflow = useMotionValue(0);
  const scale = useMotionValue(1);

  const pct = useMemo(() => {
    const span = max - min;
    if (span <= 0) return 0;
    return ((value - min) / span) * 100;
  }, [value, min, max]);

  useMotionValueEvent(clientX, "change", (latest) => {
    const el = sliderRef.current;
    if (!el) return;
    const { left, right } = el.getBoundingClientRect();
    let diff = 0;
    if (latest < left) diff = left - latest;
    else if (latest > right) diff = latest - right;
    overflow.jump(decay(diff, MAX_OVERFLOW));
  });

  const handlePointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      const el = sliderRef.current;
      if (!el || e.buttons <= 0) return;
      const { left, width } = el.getBoundingClientRect();
      const ratio = (e.clientX - left) / Math.max(width, 1);
      const raw = min + ratio * (max - min);
      // langkah (step)
      const stepped = Math.round(raw / step) * step;
      const next = clamp(stepped, min, max);
      onChange(next);
      clientX.jump(e.clientX);
    },
    [min, max, step, onChange, clientX]
  );

  const handlePointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      handlePointerMove(e);
      e.currentTarget.setPointerCapture(e.pointerId);
    },
    [handlePointerMove]
  );

  const handlePointerUp = useCallback(() => {
    animate(overflow, 0, { type: "spring", bounce: 0.5 });
  }, [overflow]);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      const big = Math.max(step * 10, (max - min) / 10);
      if (e.key === "ArrowRight") onChange(clamp(value + step, min, max));
      else if (e.key === "ArrowLeft") onChange(clamp(value - step, min, max));
      else if (e.key === "PageUp") onChange(clamp(value + big, min, max));
      else if (e.key === "PageDown") onChange(clamp(value - big, min, max));
      else if (e.key === "Home") onChange(min);
      else if (e.key === "End") onChange(max);
    },
    [value, min, max, step, onChange]
  );

  const barScaleX = useTransform(overflow, (ov) => {
    const el = sliderRef.current;
    if (!el) return 1;
    const { width } = el.getBoundingClientRect();
    return 1 + ov / Math.max(width, 1);
  });
  const barScaleY = useTransform(overflow, [0, MAX_OVERFLOW], [1, 0.9]);
  const barOrigin = useTransform(clientX, () => {
    const el = sliderRef.current;
    if (!el) return "center";
    const { left, width } = el.getBoundingClientRect();
    return clientX.get() < left + width / 2 ? "right" : "left";
  });

  return (
    <div className={`flex flex-col items-stretch gap-2 ${className}`}>
      <motion.div
        onHoverStart={() => animate(scale, 1.08)}
        onHoverEnd={() => animate(scale, 1)}
        onTouchStart={() => animate(scale, 1.08)}
        onTouchEnd={() => animate(scale, 1)}
        style={{ scale, opacity: useTransform(scale, [1, 1.08], [0.9, 1]) }}
        className="flex w-full items-center justify-center gap-3"
      >
        {/* Tombol minus */}
        <motion.button
          type="button"
          onClick={() => onChange(clamp(value - step, min, max))}
          aria-label="kurangi"
          className={`grid place-items-center rounded-full w-8 h-8 ${
            theme === "dark"
              ? "bg-[#0a0a0a] border border-gray-700"
              : "bg-white border border-gray-300"
          }`}
          animate={{ scale: [1, 1.05, 1] }}
          transition={{ duration: 0.25 }}
        >
          {leftIcon}
        </motion.button>

        {/* Track */}
        <div
          ref={sliderRef}
          role="slider"
          aria-label={ariaLabel}
          aria-valuemin={min}
          aria-valuemax={max}
          aria-valuenow={value}
          tabIndex={0}
          onKeyDown={onKeyDown}
          className="relative flex w-full cursor-grab select-none items-center py-3 focus:outline-none"
          onPointerMove={handlePointerMove}
          onPointerDown={handlePointerDown}
          onPointerUp={handlePointerUp}
        >
          <motion.div
            style={{
              scaleX: barScaleX,
              scaleY: barScaleY,
              transformOrigin: barOrigin as any,
            }}
            className="relative flex-grow"
          >
            {/* Base track */}
            <div
              className={`h-3 w-full rounded-full ${
                theme === "dark" ? "bg-gray-700" : "bg-gray-300"
              }`}
            />
            {/* Filled */}
            <div
              className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-amber-400 to-orange-600"
              style={{ width: `${pct}%` }}
            />
            {/* Handle */}
            <div className="absolute -top-1.5" style={{ left: `calc(${pct}% - 10px)` }}>
              <div className="w-5 h-5 rounded-full bg-white border-2 border-orange-500 shadow" />
            </div>
          </motion.div>
        </div>

        {/* Tombol plus */}
        <motion.button
          type="button"
          onClick={() => onChange(clamp(value + step, min, max))}
          aria-label="tambah"
          className={`grid place-items-center rounded-full w-8 h-8 ${
            theme === "dark"
              ? "bg-[#0a0a0a] border border-gray-700"
              : "bg-white border border-gray-300"
          }`}
          animate={{ scale: [1, 1.05, 1] }}
          transition={{ duration: 0.25 }}
        >
          {rightIcon}
        </motion.button>
      </motion.div>
    </div>
  );
}
