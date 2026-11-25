"use client";

import React from "react";

interface VortexenLogoProps {
  variant?: "dark" | "light";
  compact?: boolean;
  subtitle?: string;
}

export function VortexenLogo({
  variant = "dark",
  compact = false,
  subtitle = "DYNAMICS INDUSTRIAL SOLUTIONS",
}: VortexenLogoProps) {
  const titleColor = variant === "dark" ? "text-white" : "text-[#0f172a]";
  const subColor = variant === "dark" ? "text-slate-400" : "text-[#475569]";

  return (
    <div className="inline-flex items-center gap-2.5 select-none">
      <img
        src="/brand/vortexen-mark.png"
        alt="Vortexen emblem"
        className={compact ? "h-7 w-7 object-contain" : "h-9 w-9 object-contain"}
      />
      <div className="leading-none">
        <div
          className={`font-extrabold tracking-[0.16em] ${
            compact ? "text-sm" : "text-base"
          } ${titleColor}`}
        >
          VORTEXEN
        </div>
        {!compact && subtitle && (
          <div className={`mt-1 text-[9px] font-semibold tracking-[0.18em] uppercase ${subColor}`}>
            {subtitle}
          </div>
        )}
      </div>
    </div>
  );
}
