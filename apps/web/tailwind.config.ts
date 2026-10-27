import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#F7F8FC",
        surface: "#FFFFFF",
        border: "#D8DEE9",
        "border-input": "#8B98AA",
        text: "#172033",
        "text-muted": "#536176",
        accent: "#6246C7",
        "on-accent": "#FFFFFF",
        danger: "#B42332",
        success: "#16794B",
        warning: "#8A5300",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      fontSize: {
        h1: ["32px", { lineHeight: "1.2" }],
        h2: ["24px", { lineHeight: "1.25" }],
        h3: ["20px", { lineHeight: "1.3" }],
        body: ["16px", { lineHeight: "1.5" }],
        small: ["14px", { lineHeight: "1.5" }],
        caption: ["12px", { lineHeight: "1.4" }],
      },
      spacing: {
        "4": "4px",
        "8": "8px",
        "12": "12px",
        "16": "16px",
        "24": "24px",
        "32": "32px",
        "48": "48px",
        "64": "64px",
      },
      borderRadius: {
        sm: "6px",
        md: "10px",
        lg: "16px",
        pill: "9999px",
      },
      maxWidth: {
        dashboard: "1200px",
        booking: "720px",
      },
    },
  },
  plugins: [],
};
export default config;