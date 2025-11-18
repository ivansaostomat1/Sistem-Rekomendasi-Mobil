"use client";

import React, { useMemo, useRef, useState, useEffect } from "react";
import { motion, useMotionValue, useSpring } from "framer-motion";

interface TiltedCardProps {
  imageSrc: React.ComponentProps<"img">["src"];
  altText?: string;
  captionText?: string;
  containerHeight?: React.CSSProperties["height"];
  containerWidth?: React.CSSProperties["width"];
  imageHeight?: React.CSSProperties["height"];
  imageWidth?: React.CSSProperties["width"];
  scaleOnHover?: number;
  rotateAmplitude?: number;          // derajat maksimum (±)
  showMobileWarning?: boolean;
  showTooltip?: boolean;             // tooltip ikut mouse
  overlayContent?: React.ReactNode;  // konten overlay (selalu terlihat jika displayOverlayContent=true)
  displayOverlayContent?: boolean;
}

export default function TiltedCard({
  imageSrc,
  altText = "Tilted card image",
  captionText = "",
  containerHeight = "300px",
  containerWidth = "100%",
  imageHeight = "300px",
  imageWidth = "100%",
  scaleOnHover = 1.8,
  rotateAmplitude = 14,
  showMobileWarning = false,
  showTooltip = false,
  overlayContent = null,
  displayOverlayContent = false,
}: TiltedCardProps) {
  const figRef = useRef<HTMLElement>(null);

  // sumber gerak
  const rx = useMotionValue(0);
  const ry = useMotionValue(0);

  // pegas mengikuti sumber
  const springCfg = { stiffness: 100, damping: 30, mass: 2 };
  const rotateX = useSpring(rx, springCfg);
  const rotateY = useSpring(ry, springCfg);
  const scale = useSpring(1, springCfg);
  const opacity = useSpring(0, { stiffness: 200, damping: 30 });

  // tooltip follow
  const tipX = useMotionValue(0);
  const tipY = useMotionValue(0);
  const tipRotate = useSpring(0, { stiffness: 350, damping: 30, mass: 1 });

  const [lastY, setLastY] = useState(0);

  const prefersReduced = useMemo(() => {
    if (typeof window === "undefined") return false;
    try { return window.matchMedia("(prefers-reduced-motion: reduce)").matches; }
    catch { return false; }
  }, []);

  const pointerFine = useMemo(() => {
    if (typeof window === "undefined") return true;
    try { return window.matchMedia("(pointer: fine)").matches; }
    catch { return true; }
  }, []);

  const effectiveAmp = prefersReduced || !pointerFine ? 0 : Math.min(Math.max(rotateAmplitude, 0), 35);

  // raf throttle
  const rafId = useRef<number | null>(null);
  useEffect(() => () => { if (rafId.current) cancelAnimationFrame(rafId.current); }, []);

  function handleMouse(e: React.MouseEvent<HTMLElement>) {
    if (!figRef.current) return;
    if (rafId.current) cancelAnimationFrame(rafId.current);

    rafId.current = requestAnimationFrame(() => {
      const rect = figRef.current!.getBoundingClientRect();
      const offsetX = e.clientX - rect.left - rect.width / 2;
      const offsetY = e.clientY - rect.top - rect.height / 2;

      const rotX = ((offsetY / (rect.height / 2)) * -effectiveAmp) || 0;
      const rotY = ((offsetX / (rect.width / 2)) *  effectiveAmp) || 0;

      rx.set(rotX);
      ry.set(rotY);

      tipX.set(e.clientX - rect.left);
      tipY.set(e.clientY - rect.top);

      const vY = offsetY - lastY;
      tipRotate.set(-vY * 0.6);
      setLastY(offsetY);
    });
  }

  function handleMouseEnter() {
    if (effectiveAmp === 0) return;
    scale.set(scaleOnHover);
    opacity.set(1);
  }

  function handleMouseLeave() {
    opacity.set(0);
    scale.set(1);
    rx.set(0);
    ry.set(0);
    tipRotate.set(0);
  }

  return (
    <figure
      ref={figRef as any}
      className="relative w-full h-full overflow-hidden rounded-2xl [perspective:800px] flex flex-col items-center justify-center"
      style={{ height: containerHeight, width: containerWidth }}
      onMouseMove={handleMouse}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {showMobileWarning && (
        <div className="absolute top-4 text-center text-sm block sm:hidden">
          This effect is not optimized for mobile. Check on desktop.
        </div>
      )}

      <motion.div
        className="relative w-full h-full [transform-style:preserve-3d]"
        style={{ rotateX, rotateY, scale }}
      >
        {/* gambar full-cover */}
        <motion.img
          src={imageSrc}
          alt={altText}
          className="absolute inset-0 w-full h-full object-cover rounded-[15px] will-change-transform [transform:translateZ(0)]"
          style={{ width: imageWidth, height: imageHeight }}
        />

        {/* overlay full-size, selalu terlihat jika diminta */}
        {displayOverlayContent && overlayContent && (
          <motion.div
            className="absolute inset-0 w-full h-full z-[2] pointer-events-none will-change-transform [transform:translateZ(30px)]"
          >
            {overlayContent}
          </motion.div>
        )}
      </motion.div>

      {showTooltip && (
        <motion.figcaption
          className="pointer-events-none absolute left-0 top-0 rounded-[4px] bg-white px-[10px] py-[4px] text-[10px] text-[#2d2d2d] opacity-0 z-[3] hidden sm:block"
          style={{ x: tipX, y: tipY, opacity, rotate: tipRotate }}
        >
          {captionText}
        </motion.figcaption>
      )}
    </figure>
  );
}
