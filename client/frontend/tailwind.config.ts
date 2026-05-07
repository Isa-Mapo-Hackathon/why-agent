import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        bg:       "#0d0b14",   /* single dark background                  */
        surface:  "#16112a",   /* cards/panels — clearly distinct from bg  */
        elevated: "#1e1838",   /* hover, active item backgrounds           */
        frame:    "#3b2d5c",   /* borders — strong, always visible         */
        dim:      "rgba(139,92,246,0.10)", /* subtle violet tint for callouts */
      },
      fontFamily: {
        display: ["var(--font-display)", "sans-serif"],
        mono:    ["var(--font-mono)",    "monospace"],
      },
      keyframes: {
        glow: {
          "0%, 100%": { boxShadow: "0 0 5px rgba(167,139,250,0.5)" },
          "50%":       { boxShadow: "0 0 16px rgba(167,139,250,1), 0 0 32px rgba(167,139,250,0.3)" },
        },
      },
      animation: {
        glow: "glow 2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
