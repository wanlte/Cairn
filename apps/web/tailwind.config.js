/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#172033',
        muted: '#667085',
        canvas: '#F7F8FC',
        brand: {
          DEFAULT: '#4F46E5',
          light: '#6D5DF6',
          teal: '#14B8A6',
        },
      },
      fontFamily: {
        sans: ['PingFang SC', 'Microsoft YaHei', 'Inter', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        soft: '0 18px 48px rgba(23, 32, 51, 0.08)',
        glow: '0 12px 36px rgba(79, 70, 229, 0.18)',
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-6px)' },
        },
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
      animation: {
        float: 'float 6s ease-in-out infinite',
        'fade-up': 'fade-up .4s ease-out both',
        shimmer: 'shimmer 1.6s linear infinite',
      },
    },
  },
  plugins: [],
}
