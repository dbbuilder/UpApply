/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./sidebar.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        upwork: {
          green: '#14a800',
          'green-dark': '#108a00',
        },
      },
    },
  },
  plugins: [],
}
