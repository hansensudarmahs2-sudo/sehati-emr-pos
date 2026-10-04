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
    // ⚠ dashboard.html merakit kelas SAAT RENDER, mis:
    //     border-{{ st.color }}-200   bg-{{ st.color }}-50/30
    //     hover:bg-{{ s.color }}-50   text-{{ s.color }}-700
    // Scanner Tailwind TIDAK bisa melihat kelas yang dirakit begitu, jadi ia
    // tidak ikut ter-build dan kartu kehilangan warnanya TANPA error apa pun.
    //
    // Terbukti 2026-10-04: sesudah kompilasi ulang, `bg-blue-50/30` dan
    // `bg-teal-50/30` HILANG dari app.css sementara 5 warna lain kebetulan ada
    // (dipakai statis di template lain). Dua kartu dashboard tampil beda tanpa
    // ada yang menyadarinya.
    //
    // Nilai warnanya datang dari app/services/dashboard_service.py ("color").
    // Ke-7 didaftarkan semua, bukan hanya yang kebetulan hilang — kalau warna
    // di service itu diganti, yang baru sudah ter-cover.
    'border-amber-200', 'border-blue-200', 'border-emerald-200', 'border-purple-200', 'border-red-200', 'border-slate-200', 'border-teal-200',
    'bg-amber-50/30', 'bg-blue-50/30', 'bg-emerald-50/30', 'bg-purple-50/30', 'bg-red-50/30', 'bg-slate-50/30', 'bg-teal-50/30',
    'hover:bg-amber-50', 'hover:bg-blue-50', 'hover:bg-emerald-50', 'hover:bg-purple-50', 'hover:bg-red-50', 'hover:bg-slate-50', 'hover:bg-teal-50',
    'text-amber-700', 'text-blue-700', 'text-emerald-700', 'text-purple-700', 'text-red-700', 'text-slate-700', 'text-teal-700',
  ],
  plugins: [],
};
