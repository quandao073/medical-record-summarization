import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        clinical: {
          50:  "#f0f7ff",
          100: "#e0efff",
          500: "#2563eb",
          600: "#1d4ed8",
          700: "#1e3a8a",
        },
      },
    },
  },
  plugins: [],
};

export default config;
