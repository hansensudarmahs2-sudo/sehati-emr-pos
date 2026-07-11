/** @type {import('tailwindcss').Config} */
// B3.1 — config build Tailwind statis (gantikan cdn.tailwindcss.com).
// `content` = file yang di-scan untuk cari class Tailwind yang dipakai,
// supaya CSS output kecil (hanya class terpakai).
module.exports = {
  content: [
    "./app/web/templates/**/*.html",
  ],
  theme: {
    extend: {},   // app pakai utility default Tailwind, tidak ada custom theme
  },
  // safelist: class yang dibangun DINAMIS di JavaScript (template literal)
  // tidak terdeteksi scanner. Kalau ada style hilang setelah build, daftarkan
  // di sini. Contoh umum (badge status warna-warni yang di-set via JS):
  safelist: [
    // Tambahkan di sini kalau ada class yang hilang, mis:
    // 'bg-green-100', 'text-green-700', 'bg-red-100', 'text-red-700',
  ],
  plugins: [],
};
