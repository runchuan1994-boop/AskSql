/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // 品牌主色 - 紫蓝渐变系列
        brand: {
          50: '#EEF2FF',
          100: '#E0E7FF',
          200: '#C7D2FE',
          300: '#A5B4FC',
          400: '#818CF8',
          500: '#6366F1',
          600: '#4F46E5',
          700: '#4338CA',
          800: '#3730A3',
          900: '#312E81',
        },
        // 紫调辅助色
        violet: {
          50: '#F5F3FF',
          100: '#EDE9FE',
          200: '#DDD6FE',
          300: '#C4B5FD',
          400: '#A78BFA',
          500: '#8B5CF6',
          600: '#7C3AED',
          700: '#6D28D9',
          800: '#5B21B6',
          900: '#4C1D95',
        },
        // 玻璃表面色
        glass: {
          surface: 'rgba(255, 255, 255, 0.7)',
          'surface-strong': 'rgba(255, 255, 255, 0.9)',
          'surface-soft': 'rgba(255, 255, 255, 0.5)',
          border: 'rgba(255, 255, 255, 0.6)',
          'border-soft': 'rgba(255, 255, 255, 0.3)',
        },
        // 文字色（石板灰系列）
        slate: {
          50: '#F8FAFC',
          100: '#F1F5F9',
          200: '#E2E8F0',
          300: '#CBD5E1',
          400: '#94A3B8',
          500: '#64748B',
          600: '#475569',
          700: '#334155',
          800: '#1E293B',
          900: '#0F172A',
          950: '#020617',
        },
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', "'Segoe UI'", 'Roboto', "'Helvetica Neue'", 'Arial', 'sans-serif'],
        mono: ["'JetBrains Mono'", "'SF Mono'", 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
      borderRadius: {
        '2xl': '16px',
        '3xl': '24px',
        '4xl': '32px',
      },
      boxShadow: {
        'glass': '0 8px 32px rgba(15, 23, 42, 0.05)',
        'glass-lg': '0 12px 48px rgba(15, 23, 42, 0.08)',
        'glass-xl': '0 20px 64px rgba(15, 23, 42, 0.1)',
        'glow': '0 0 20px rgba(99, 102, 241, 0.3)',
        'glow-lg': '0 0 40px rgba(99, 102, 241, 0.2)',
      },
      backdropBlur: {
        '2xl': '40px',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'float': 'float 6s ease-in-out infinite',
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' },
        },
      },
    },
  },
  plugins: [],
}
