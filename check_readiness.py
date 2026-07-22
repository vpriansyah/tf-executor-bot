"""
Script Pengecekan Kesiapan (Readiness Checklist) TF Executor Bot
================================================================
Jalankan script ini untuk mengecek apakah .env dan koneksi awal sudah siap.
Usage: python check_readiness.py
"""

import os
import sys

# Ensure UTF-8 output encoding if supported
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def check_env():
    print("--- 1. Checking .env File ---")
    if not os.path.exists(".env"):
        print("[ERROR] File .env TIDAK ditemukan!")
        print("        Silakan buat .env dari .env.example terlebih dahulu.")
        return False
    
    print("[OK] File .env ditemukan.")
    
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        print("[ERROR] Package 'python-dotenv' belum ter-install. Jalankan: pip install python-dotenv")
        return False

    bot_token = os.environ.get("BOT_TOKEN", "").strip()
    allowed_user_id = os.environ.get("ALLOWED_USER_ID", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    mt5_login = os.environ.get("MT5_LOGIN", "").strip()
    mt5_server = os.environ.get("MT5_SERVER", "Finex-Demo").strip()
    
    is_ok = True
    if not bot_token or "YOUR_TELEGRAM_BOT_TOKEN_HERE" in bot_token or "isi_token" in bot_token:
        print("[ERROR] BOT_TOKEN belum diisi dengan benar di file .env")
        is_ok = False
    else:
        print(f"[OK] BOT_TOKEN terdeteksi: {bot_token[:5]}***")
        
    if not allowed_user_id or "YOUR_TELEGRAM_USER_ID_HERE" in allowed_user_id or not allowed_user_id.isdigit():
        print("[ERROR] ALLOWED_USER_ID belum diisi angka Chat ID Telegram di file .env")
        is_ok = False
    else:
        print(f"[OK] ALLOWED_USER_ID terdeteksi: {allowed_user_id}")

    if not gemini_key or "YOUR_GEMINI_API_KEY" in gemini_key or "isi_gemini" in gemini_key:
        print("[WARN] GEMINI_API_KEY belum diisi di .env (Fitur ekstraksi gambar tidak akan aktif)")
    else:
        print(f"[OK] GEMINI_API_KEY terdeteksi: {gemini_key[:5]}***")

    if not mt5_login or not mt5_login.isdigit():
        print(f"[WARN] MT5_LOGIN belum diisi di .env. Menggunakan akun MT5 lokal jika ada.")
    else:
        print(f"[OK] Kredensial Broker MT5: Login #{mt5_login} (Server: {mt5_server})")
        
    return is_ok

def check_dependencies():
    print("\n--- 2. Checking Python Dependencies ---")
    dependencies = ["telegram", "dotenv", "mt5linux"]
    all_ok = True
    for dep in dependencies:
        try:
            __import__(dep)
            print(f"[OK] Package '{dep}' terinstall.")
        except ImportError:
            print(f"[ERROR] Package '{dep}' BELUM terinstall.")
            all_ok = False

    # Check Vision SDK
    has_genai = False
    try:
        from google import genai
        print("[OK] Package 'google-genai' terinstall.")
        has_genai = True
    except ImportError:
        try:
            import google.generativeai
            print("[OK] Package 'google-generativeai' terinstall.")
            has_genai = True
        except ImportError:
            print("[WARN] Package 'google-genai' / 'google-generativeai' BELUM terinstall (diperlukan untuk baca screenshot).")
    
    return all_ok and has_genai

def check_bridge_connection():
    print("\n--- 3. Checking MT5 Bridge Connection ---")
    host = os.environ.get("MT5_BRIDGE_HOST", "localhost")
    port = int(os.environ.get("MT5_BRIDGE_PORT", "18812"))

    if sys.platform == "win32" and host in ("localhost", "127.0.0.1"):
        print(f"[INFO] Menjalankan pengecekan koneksi dari Windows Host ke MT5 Bridge di {host}:{port}...")

    try:
        from mt5linux import MetaTrader5
        mt5 = MetaTrader5(host=host, port=port)
        print(f"Mengontak mt5linux bridge di {host}:{port}...")

        login_str = os.environ.get("MT5_LOGIN", "").strip()
        pwd_str = os.environ.get("MT5_PASSWORD", "").strip()
        server_str = os.environ.get("MT5_SERVER", "Finex-Demo").strip()

        if login_str.isdigit() and pwd_str:
            init_ok = mt5.initialize(login=int(login_str), password=pwd_str, server=server_str)
        else:
            init_ok = mt5.initialize()

        if init_ok:
            terminal_info = mt5.terminal_info()
            account_info = mt5.account_info()
            print("[OK] Berhasil terhubung ke MT5 Terminal & Broker!")
            if account_info:
                print(f"     Akun MT5: {account_info.login} | Equity: {account_info.equity} | Server: {account_info.server}")
            mt5.shutdown()
            return True
        else:
            print(f"[WARN] Gagal inisialisasi MT5 / Login Broker. Error: {mt5.last_error()}")
            print("       Isi MT5_LOGIN dan MT5_PASSWORD di .env jika belum diisi.")
            return False
    except Exception as e:
        print(f"[WARN] Gagal menghubungkan ke mt5linux bridge di {host}:{port}.")
        print(f"       Detail error: {e}")
        if "111" in str(e) or "refused" in str(e).lower():
            print("       💡 SOLUSI:")
            print("       1. Jika menggunakan Docker, jalankan: docker-compose up -d --build")
            print("       2. Pastikan container 'tf_executor_bot' aktif: docker ps")
            print("       3. Cek log container jika server bridge error: docker logs tf_executor_bot")
        return False


def main():
    print("==================================================")
    print("   TF EXECUTOR BOT - READINESS & DIAGNOSTIC CHECK")
    print("==================================================\n")
    
    env_ok = check_env()
    deps_ok = check_dependencies()
    bridge_ok = check_bridge_connection()
    
    print("\n==================================================")
    print("SUMMARY KESIAPAN:")
    print(f"- File .env & Konfigurasi : {'[OK]' if env_ok else '[PERLU DIISI]'}")
    print(f"- Library Python Dependencies: {'[OK]' if deps_ok else '[PERLU INSTALL]'}")
    print(f"- Koneksi MT5 Terminal & Broker: {'[CONNECTED]' if bridge_ok else '[BELUM LOGIN BROKER - Isi MT5_LOGIN]'}")
    print("==================================================")

if __name__ == "__main__":
    main()
