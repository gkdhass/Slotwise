/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: "#10243A",
        "deep-blue": "#183B56",
        teal: "#16A6A1",
        "pale-cyan": "#DDF5F3",
        critical: "#C94C4C",
        warning: "#F2B544",
        healthy: "#16A6A1",
        surface: "#F7FAFC",
        ink: "#10243A",
        muted: "#5B6B7C",
      },
      fontFamily: {
        sans: ["'DejaVu Sans'", "Arial", "sans-serif"],
      },
      borderRadius: {
        card: "8px",
        control: "6px",
      },
      spacing: {
        18: "4.5rem",
      },
      boxShadow: {
        panel: "0 1px 2px rgba(16, 36, 58, 0.08)",
      },
    },
  },
  plugins: [],
};
