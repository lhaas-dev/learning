/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: "#050505",
          secondary: "#0A0A0A",
          tertiary: "#121212",
          surface: "#161b22",
        },
        brand: {
          primary: "#00E5FF",
          secondary: "#2F81F7",
        },
        risk: {
          high: "#FF2D55",
          medium: "#FFCC00",
          low: "#00C853",
        },
        text: {
          primary: "#E6EDF3",
          secondary: "#8B949E",
          muted: "#484F58",
        },
      },
      fontFamily: {
        heading: ['"Space Grotesk"', '"JetBrains Mono"', "monospace"],
        body: ["Manrope", "sans-serif"],
        mono: ['"JetBrains Mono"', "monospace"],
      },
      boxShadow: {
        glow: "0 0 20px rgba(0, 229, 255, 0.25)",
        "glow-sm": "0 0 10px rgba(0, 229, 255, 0.15)",
      },
    },
  },
  plugins: [],
};
