/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        graphite: { 800: "#1f2937", 900: "#111827", 950: "#0b0f19" },
        navy: { 900: "#0f172a", 800: "#1e293b" },
        cyan: { 400: "#22d3ee", 500: "#06b6d4", 600: "#0891b2" },
        green: { 400: "#4ade80", 500: "#22c55e" },
        amber: { 400: "#fbbf24", 500: "#f59e0b" },
        red: { 500: "#ef4444", 600: "#dc2626", 900: "#7f1d1d" },
      },
      fontFamily: { sans: ["Inter", "system-ui", "sans-serif"] },
      animation: { "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite" },
    },
  },
  plugins: [],
};
