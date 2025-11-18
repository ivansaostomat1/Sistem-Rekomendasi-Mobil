// FuelIcons.tsx (atau file ikonmu sekarang)
import { CarIcon, EvChargerIcon, FuelIcon as FuelPumpIcon } from "lucide-react";

type IconProps = { className?: string };

/* ====== INLINE ICONS (sama seperti di form) ====== */
export const BoltIcon = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" width="1em" height="1em" fill="currentColor" className={className}>
    <path d="M13 2L3 14h7l-1 8 10-12h-7l1-8z" />
  </svg>
);

export const BatteryIcon = ({ className }: IconProps) => (
  <svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" strokeWidth="2" className={className}>
    <rect x="2" y="7" width="18" height="10" rx="2" />
    <path d="M22 10v4" />
  </svg>
);

/* ====== ALIASES SESUAI KODE BAHAN BAKAR ====== */
export const IconBensin = ({ className }: IconProps) => <FuelPumpIcon className={className} />;
export const IconDiesel = ({ className }: IconProps) => <CarIcon className={className} />;
export const IconHybrid = ({ className }: IconProps) => <BoltIcon className={className} />;
export const IconPHEV   = ({ className }: IconProps) => <EvChargerIcon className={className} />;
export const IconBEV    = ({ className }: IconProps) => <BatteryIcon className={className} />;

/* ====== MAPPER (pakai nama yang sama agar drop-in replacement) ====== */
export function FuelIcon({ iconKey, className = "" }: { iconKey: string; className?: string }) {
  const key = String(iconKey).toLowerCase();

  switch (key) {
    // Kode huruf (g,d,h,p,e)
    case "g":
    case "bensin":
      return <IconBensin className={className} />;

    case "d":
    case "diesel":
      return <IconDiesel className={className} />;

    case "h":
    case "hybrid":
      return <IconHybrid className={className} />;

    case "p":
    case "phev":
      return <IconPHEV className={className} />;

    case "e":
    case "bev":
      return <IconBEV className={className} />;

    default:
      return null;
  }
}
