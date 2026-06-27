import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#0b0f17",
        panel: "#141a26",
        edge: "#222b3d",
      },
    },
  },
  plugins: [],
};

export default config;
