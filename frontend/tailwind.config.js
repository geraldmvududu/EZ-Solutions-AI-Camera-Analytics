/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        base: {
          950: "#0a0e14",
          900: "#0f1420",
          800: "#151b2b",
          700: "#1e2638",
          600: "#2a3448",
        },
        accent: {
          500: "#14b8a6",
          600: "#0d9488",
        },
        severity: {
          info: "#3b82f6",
          low: "#22c55e",
          medium: "#eab308",
          high: "#f97316",
          critical: "#ef4444",
        },
      },
    },
  },
  plugins: [],
};
