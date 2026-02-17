/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Softer stat colors for Bento Grid aesthetic
        'stat-green': '#22c55e',
        'stat-yellow': '#f59e0b',
        'stat-red': '#ef4444',
        'stat-dim': '#9ca3af',
        // Neutral palette
        'neutral': {
          50: '#fafafa',
          100: '#f5f5f5',
          150: '#eeeeee',
          850: '#262626',
          900: '#171717',
          950: '#0a0a0a',
        },
      },
      borderRadius: {
        'xl': '0.75rem',   // 12px
        '2xl': '1rem',     // 16px
        '3xl': '1.25rem',  // 20px
      },
      boxShadow: {
        'card': '0 1px 3px 0 rgb(0 0 0 / 0.05)',
        'card-hover': '0 4px 6px -1px rgb(0 0 0 / 0.08)',
      },
    },
  },
  plugins: [],
}

