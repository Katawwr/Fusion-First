/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        fusion: {
          purple: '#504d9a',
          'purple-light': 'rgba(80, 77, 154, 0.25)',
          'purple-medium': 'rgba(80, 77, 154, 0.4)',
          cyan: '#66c4e1',
          'cyan-light': 'rgba(102, 196, 225, 0.2)',
          'cyan-medium': 'rgba(102, 196, 225, 0.4)',
          pink: '#f38f95',
          'dark-pink': '#db418b',
        },
        severity: {
          critical: '#ef4444',
          high: '#fb923c',
          medium: '#facc15',
          low: '#22c55e',
        }
      },
      backgroundImage: {
        'fusion-gradient': 'linear-gradient(135deg, #504d9a 0%, #66c4e1 50%, #504d9a 100%)',
        'fusion-pink-gradient': 'linear-gradient(to right, #f38f95, #db418b)',
        'fusion-cyan-pink': 'linear-gradient(to right, #66c4e1, #f38f95)',
      },
      backdropBlur: {
        xs: '2px',
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['Courier New', 'monospace'],
      },
    },
  },
  plugins: [],
}