/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        solar: {
          light: '#fef08a',
          DEFAULT: '#eab308',
          dark: '#ca8a04',
        },
        battery: {
          light: '#86efac',
          DEFAULT: '#22c55e',
          dark: '#16a34a',
        },
      },
      animation: {
        'flow-fast': 'dash 0.6s linear infinite',
        'flow-normal': 'dash 1.2s linear infinite',
        'flow-slow': 'dash 2.0s linear infinite',
      },
      keyframes: {
        dash: {
          to: {
            strokeDashoffset: '-20',
          },
        },
      },
    },
  },
  plugins: [],
}
