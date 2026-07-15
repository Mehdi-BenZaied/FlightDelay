/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#0f172a",
        card: "rgba(30, 41, 59, 0.7)",
        primary: "#6366f1",
        secondary: "#94a3b8",
      },
      backdropBlur: {
        xs: '2px',
      }
    },
  },
  plugins: [],
}
