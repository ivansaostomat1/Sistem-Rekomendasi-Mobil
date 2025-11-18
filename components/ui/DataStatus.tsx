import { Theme } from "@/types";

interface DataStatusProps {
  theme: Theme;
  dataReady: {
    specs: boolean;
    retail: boolean;
    wholesale: boolean;
  };
}

export function DataStatus({ theme, dataReady }: DataStatusProps) {
  return (
    <section className="mb-6 grid grid-cols-1 sm:grid-cols-3 gap-3">
      <div className={`rounded-2xl p-3 ${theme === "dark" ? "bg-[#1a1a1a] border border-neutral-800" : "bg-white border border-gray-200"}`}>
        <p className="text-xs opacity-70">Specs</p>
        <p className={`font-medium ${dataReady.specs ? "text-emerald-400" : "text-red-400"}`}>
          {dataReady.specs ? "Siap" : "Belum"}
        </p>
      </div>
      <div className={`rounded-2xl p-3 ${theme === "dark" ? "bg-[#1a1a1a] border border-neutral-800" : "bg-white border border-gray-200"}`}>
        <p className="text-xs opacity-70">Retail 2020–2025</p>
        <p className={`font-medium ${dataReady.retail ? "text-emerald-400" : "text-red-400"}`}>
          {dataReady.retail ? "Ada" : "Tidak ada"}
        </p>
      </div>
      <div className={`rounded-2xl p-3 ${theme === "dark" ? "bg-[#1a1a1a] border border-neutral-800" : "bg-white border border-gray-200"}`}>
        <p className="text-xs opacity-70">Wholesale 2020–2025</p>
        <p className={`font-medium ${dataReady.wholesale ? "text-emerald-400" : "text-red-400"}`}>
          {dataReady.wholesale ? "Ada" : "Tidak ada"}
        </p>
      </div>
    </section>
  );
}