import { motion } from "framer-motion";
import { Theme } from "@/types";
import { BRANDS } from "@/constants";

interface BrandGridProps {
  theme: Theme;
}

export function BrandGrid({ theme }: BrandGridProps) {
  return (
    <motion.section
      initial="hidden"
      animate="visible"
      variants={{
        hidden: { opacity: 0, y: 30 },
        visible: { opacity: 1, y: 0 }
      }}
      transition={{ delay: 0.1 }}
      className="mb-12"
    >
      <h2 className="text-2xl font-bold mb-6">10 Brand Dengan Penjualan Terbaik</h2>
      <div className="grid grid-cols-5 md:grid-cols-10 gap-4">
        {BRANDS.map((brand, i) => (
          <a
            key={brand.name}
            href={`/brands/${brand.name.toLowerCase().replace(/ /g, '-')}`}
          >
            <motion.div
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className={`flex flex-col items-center justify-center gap-2 rounded-2xl p-4 transition-all duration-300 cursor-pointer ${
                theme === "dark"
                  ? "bg-[#1a1a1a] border border-neutral-800 hover:border-neutral-700 hover:bg-[#2a2a2a]"
                  : "bg-white border border-gray-200 hover:border-gray-300 hover:bg-gray-100"
              }`}
            >
              <div className="relative w-10 h-10">
                <img
                  src={brand.logo}
                  alt={`${brand.name} logo`}
                  className="absolute inset-0 w-full h-full object-contain"
                />
              </div>
              <p className="text-xs font-medium opacity-80">{brand.name}</p>
            </motion.div>
          </a>
        ))}
      </div>
    </motion.section>
  );
}