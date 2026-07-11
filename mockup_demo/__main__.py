"""
Entry point untuk demo Klinik ABC.

Behavior:
1. Start uvicorn di port 8765, bind ke 0.0.0.0 (network-accessible)
2. Auto-open browser ke http://localhost:8765 di laptop yang jalanin
3. Show 2 URL di console:
   - Local: http://localhost:8765 (untuk laptop ini)
   - Network: http://<IP>:8765 (untuk laptop lain di Wi-Fi sama)
4. Press Ctrl+C atau close console untuk exit
"""

import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Add current dir to sys.path supaya import demo_data + main bisa jalan
if hasattr(sys, "_MEIPASS"):
    sys.path.insert(0, sys._MEIPASS)
else:
    sys.path.insert(0, str(Path(__file__).parent))

import uvicorn


PORT = 8765


def get_local_ip() -> str:
    """Detect IP laptop di jaringan lokal (untuk akses dari laptop lain di Wi-Fi sama)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Trick: connect ke alamat publik untuk dapat IP routing — tidak benar-benar kirim data
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def open_browser_delayed():
    """Tunggu 2 detik supaya server siap, lalu buka browser ke localhost."""
    time.sleep(2)
    try:
        webbrowser.open(f"http://localhost:{PORT}")
    except Exception:
        pass


def main():
    local_ip = get_local_ip()

    print("=" * 64)
    print("  Klinik ABC — eMR + POS Demo")
    print("=" * 64)
    print()
    print("  Demo server starting...")
    print()
    print("  ╔══════════════════════════════════════════════════════════╗")
    print("  ║  Untuk laptop ini (sendiri):                             ║")
    print(f"  ║    → http://localhost:{PORT}                              ║")
    print("  ║                                                          ║")
    print("  ║  Untuk laptop partner (via Wi-Fi sama):                  ║")
    print(f"  ║    → http://{local_ip}:{PORT}".ljust(63) + "║")
    print("  ╚══════════════════════════════════════════════════════════╝")
    print()
    print("  Browser di laptop ini akan terbuka otomatis dalam 2 detik...")
    print()
    print("  TIPS untuk akses dari laptop partner:")
    print("    1. Pastikan kedua laptop terhubung Wi-Fi yang sama")
    print("    2. Pertama kali Windows mungkin tanya 'Allow on private network?'")
    print("       → Klik 'Allow access' supaya partner bisa buka URL Network")
    print("    3. Partner cukup ketik URL Network di browser mereka")
    print()
    print("  Untuk keluar: tutup window ini atau tekan Ctrl+C")
    print("=" * 64)
    print()

    # Open browser di background thread
    threading.Thread(target=open_browser_delayed, daemon=True).start()

    # Start uvicorn — bind ke 0.0.0.0 supaya network-accessible
    try:
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=PORT,
            log_level="warning",
            access_log=False,
        )
    except KeyboardInterrupt:
        print("\nDemo server stopped. Sampai jumpa!")


if __name__ == "__main__":
    main()
