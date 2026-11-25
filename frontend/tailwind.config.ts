import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/features/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Official Vortexen Brand Palette (from vortexen.com)
        vortexen: {
          blue: "#0052cc",
          blueHover: "#003d99",
          blueBright: "#2684ff",
          cyan: "#29a9ea",
          navy: "#0b111e",
          ink: "#0f172a",
          ink2: "#1e293b",
          ink3: "#334155",
          slate: "#475569",
          muted: "#64748b",
          border: "#e2e8f0",
          surfaceSoft: "#f8fafc",
          surfaceTint: "#fafbfd",
          accent: "#e85e15",
          accentBright: "#ff6b1a",
        },
        brand: {
          50: "#eff6ff",
          100: "#d9eaff",
          500: "#0052cc",
          600: "#003d99",
          700: "#002e73",
          900: "#0b111e",
        },
      },
      fontFamily: {
        sans: ['"Manrope"', "-apple-system", "BlinkMacSystemFont", '"Segoe UI"', "Roboto", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "Menlo", "Monaco", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
