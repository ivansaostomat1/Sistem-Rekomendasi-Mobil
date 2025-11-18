import { motion, AnimatePresence } from "framer-motion";
import { useState, useEffect } from "react";
import { Theme } from "@/types";
import { SEGMENTASI_INFO } from "@/constants";

interface SegmentCarouselProps {
  theme: Theme;
}

export function SegmentCarousel({ theme }: SegmentCarouselProps) {
  const [currentSegmentIndex, setCurrentSegmentIndex] = useState(0);
  const segmentsPerSlide = 3;
  const totalSegments = SEGMENTASI_INFO.length;
  const totalSlides = Math.ceil(totalSegments / segmentsPerSlide);
  const startIndex = currentSegmentIndex * segmentsPerSlide;
  const visibleSegments = SEGMENTASI_INFO.slice(startIndex, startIndex + segmentsPerSlide);

  useEffect(() => {
    const slideInterval = setInterval(() => {
      setCurrentSegmentIndex((prevIndex) => (prevIndex + 1) % totalSlides);
    }, 5000);
    return () => clearInterval(slideInterval);
  }, [totalSlides]);

  return (
    <motion.section 
      initial="hidden" 
      animate="visible" 
      variants={{
        hidden: { opacity: 0, y: 30 },
        visible: { opacity: 1, y: 0 }
      }} 
      className="mb-12"
    >
      <h2 className="text-2xl font-bold mb-6">Penjelasan Segmentasi Mobil :</h2>

      <div className="relative">
        <div className="overflow-hidden">
          <AnimatePresence initial={false} mode="wait">
            <motion.div
              key={currentSegmentIndex}
              initial={{ opacity: 0, x: 50 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -50 }}
              transition={{ duration: 0.5 }}
              className="grid md:grid-cols-3 gap-6"
            >
              {visibleSegments.map((seg) => (
                <motion.div
                  key={seg.title}
                  whileHover={{ scale: 1.03 }}
                  className={`rounded-2xl p-6 shadow-md ${
                    theme === "dark" 
                      ? "bg-[#1a1a1a] hover:bg-[#2a2a2a] shadow-black/20" 
                      : "bg-white hover:bg-gray-100"
                  } transition`}
                >
                  <h3 className="text-lg font-bold mb-2 text-orange-400">{seg.title}</h3>
                  <p className="text-sm opacity-80 leading-relaxed">{seg.desc}</p>
                </motion.div>
              ))}
            </motion.div>
          </AnimatePresence>
        </div>

        {totalSlides > 1 && (
          <div className="flex justify-center items-center gap-4 mt-6">
            <button
              onClick={() => setCurrentSegmentIndex((prev) => (prev - 1 + totalSlides) % totalSlides)}
              className={`p-2 rounded-full transition ${
                currentSegmentIndex === 0 
                  ? "opacity-50 cursor-pointer" 
                  : "bg-orange-500 hover:bg-orange-600 text-white"
              }`}
              aria-label="Previous segment"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" />
              </svg>
            </button>

            <div className="flex space-x-2">
              {Array.from({ length: totalSlides }).map((_, index) => (
                <button
                  key={index}
                  onClick={() => setCurrentSegmentIndex(index)}
                  className={`w-3 h-3 rounded-full transition ${
                    index === currentSegmentIndex 
                      ? "bg-orange-500 scale-110" 
                      : "bg-gray-400 opacity-50 hover:bg-gray-300"
                  }`}
                  aria-label={`Go to slide ${index + 1}`}
                />
              ))}
            </div>

            <button
              onClick={() => setCurrentSegmentIndex((prev) => (prev + 1) % totalSlides)}
              className={`p-2 rounded-full transition ${
                currentSegmentIndex === totalSlides - 1 
                  ? "opacity-50 cursor-pointer" 
                  : "bg-orange-500 hover:bg-orange-600 text-white"
              }`}
              aria-label="Next segment"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        )}
      </div>
    </motion.section>
  );
}