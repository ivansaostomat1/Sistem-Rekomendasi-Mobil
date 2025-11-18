import React from "react";

export interface GlassIconsItem {
  id: string;                 // kunci unik (mis. 'g','d','h','p','e')
  icon: React.ReactElement;   // elemen ikon (SVG / apa pun)
  color: string;              // bisa hex / gradient css
  label: string;
  selected?: boolean;
  customClass?: string;
}

export interface GlassIconsProps {
  items: GlassIconsItem[];
  className?: string;
  onItemClick?: (item: GlassIconsItem) => void;
}

const isGradient = (v: string) => v.includes("gradient(");
const bgStyle = (color: string): React.CSSProperties =>
  isGradient(color) ? { background: color } : { background: color };

const GlassIcons: React.FC<GlassIconsProps> = ({ items, className, onItemClick }) => {
  return (
    <div className={`grid gap-[1.2em] grid-cols-3 sm:grid-cols-4 md:grid-cols-5 ${className || ""}`}>
      {items.map((item) => {
        const active = !!item.selected;
        return (
          <button
            key={item.id}
            type="button"
            aria-label={item.label}
            aria-pressed={active}
            onClick={() => onItemClick?.(item)}
            className={[
              "relative bg-transparent outline-none w-[4.5em] h-[4.5em]",
              "[perspective:24em] [transform-style:preserve-3d]",
              "group rounded-2xl transition",
              active ? "ring-2 ring-purple-500" : "hover:opacity-95",
              item.customClass || "",
            ].join(" ")}
            style={{ WebkitTapHighlightColor: "transparent" } as React.CSSProperties}
          >
            {/* layer belakang berwarna */}
            <span
              className="absolute inset-0 rounded-[1.25em] block transition-transform duration-300 ease-[cubic-bezier(0.83,0,0.17,1)] origin-[100%_100%] rotate-[12deg] group-hover:[transform:rotate(18deg)_translate3d(-0.4em,-0.4em,0.4em)]"
              style={{
                ...bgStyle(item.color),
                boxShadow: "0.5em -0.5em 0.75em hsla(223, 10%, 10%, 0.15)",
              }}
            />
            {/* kartu kaca */}
            <span
              className={[
                "absolute inset-0 rounded-[1.25em] bg-[hsla(0,0%,100%,0.12)]",
                "flex items-center justify-center backdrop-blur-md",
                "transition-transform duration-300 ease-[cubic-bezier(0.83,0,0.17,1)]",
                "group-hover:[transform:translateZ(1.2em)]",
                active ? "ring-1 ring-orange-500/70" : "ring-1 ring-white/30",
              ].join(" ")}
            >
              {/* atur ukuran ikon via fontSize supaya universal */}
              <span className="text-white" style={{ fontSize: 22, lineHeight: 1 }}>
                {item.icon}
              </span>
            </span>

            {/* label */}
            <span
              className={[
                "absolute top-full left-0 right-0 text-center whitespace-nowrap leading-[2] text-[0.9rem]",
                "opacity-0 translate-y-0",
                "transition-[opacity,transform] duration-300 ease-[cubic-bezier(0.83,0,0.17,1)]",
                "group-hover:opacity-100 group-hover:translate-y-[20%]",
                active ? "text-orange-500" : "text-current",
              ].join(" ")}
            >
              {item.label}
            </span>
          </button>
        );
      })}
    </div>
  );
};

export default GlassIcons;
