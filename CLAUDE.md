# CLAUDE.md — Konteks Proyek untuk AI Coding Agent

Baca file ini dulu sebelum mengerjakan apa pun di repo ini. Ini rangkuman keputusan
desain yang sudah diambil, supaya AI agent tidak mengusulkan ulang hal yang sudah
dipertimbangkan dan ditolak/diterima dengan alasan tertentu.

## Apa proyek ini

Sebuah **eksekutor order manual-terpicu** untuk trading forex. Pemilik proyek membaca
sinyal trading secara manual (dari sumber signal provider pihak ketiga, dibaca sendiri
oleh manusia — bukan dibaca otomatis oleh sistem ini), lalu mengirim command singkat
lewat Telegram. Bot menerjemahkan command itu menjadi order di MetaTrader 5 (MT5) pada
akun broker Finex.

**Ini BUKAN signal-copier otomatis.** Sistem ini tidak pernah membaca/scrape sumber
sinyal manapun. Manusia yang memutuskan kapan buy/sell/cancel; bot hanya mempercepat
eksekusi supaya tidak perlu mengetik manual di aplikasi MT5.

## Batasan infrastruktur (penting, jangan diusulkan ulang)

- **Hanya ada 1 server**: VPS Linux yang sudah ada (tidak ada VPS Windows terpisah,
  tidak ada budget tambahan untuk servis lain).
- Laptop pribadi & HP **tidak** dipakai untuk menjalankan bagian eksekusi — keduanya
  cuma dipakai untuk kirim command via Telegram kapan saja.
- MetaTrader 5 **tidak punya binary native Linux**. Solusi yang dipakai: jalankan MT5
  di VPS yang sama via **Wine**, headless dengan **Xvfb**, dikelola **systemd** supaya
  survive reboot tanpa sesi GUI/RDP terbuka.
- Python native (Linux) tempat bot Telegram jalan **tidak** bisa langsung import
  `MetaTrader5` (package itu cuma jalan di Python-Windows). Jembatannya pakai
  **`mt5linux`** (atau `mt5-remote`): server kecil jalan di Python-Windows-di-dalam-Wine,
  bot Telegram (Python native Linux) connect ke situ lewat `localhost` (rpyc).
- Karena itu, kalau menulis kode Python untuk bot:
  ```python
  from mt5linux import MetaTrader5   # BUKAN: import MetaTrader5 as mt5
  mt5 = MetaTrader5()
  ```

## Keputusan yang sudah diambil dan alasannya (jangan diusulkan ulang tanpa alasan baru)

| Opsi yang dipertimbangkan | Kenapa tidak dipakai |
|---|---|
| Baca sinyal otomatis dari app/situs signal provider (scraping) | Melanggar ToS provider, akun bisa di-suspend |
| Copy Signal resmi provider ke broker partner mereka | Broker partner tidak sesuai preferensi pemilik proyek (masalah kepercayaan/regulasi) |
| VPS Windows terpisah untuk jalankan MT5 | Biaya tambahan, pemilik proyek tidak mau keluar uang ekstra |
| OCR baca screenshot sinyal otomatis | Rawan salah baca angka presisi (entry/SL/TP), risiko tinggi untuk eksekusi order |

## Prioritas keamanan (non-negotiable)

1. Bot **hanya** boleh merespons `ALLOWED_USER_ID` (Telegram user ID pemilik). Semua
   handler command wajib cek ini sebelum eksekusi apa pun.
2. Kredensial (`BOT_TOKEN`, login MT5) **tidak boleh** di-hardcode di kode yang commit
   ke git — pakai environment variable / file `.env` yang di-gitignore.
3. Setiap perintah yang mengeksekusi order (`/buy`, `/sell`, `/buylimit`, `/selllimit`,
   `/close`, `/cancel`) harus log ke file (timestamp, command mentah, hasil retcode)
   untuk audit trail.

## Struktur folder

```
tf-executor-bot/
├── CLAUDE.md              # file ini
├── README.md              # overview + quick start untuk manusia
├── docs/
│   ├── ARCHITECTURE.md    # detail arsitektur & alur data
│   ├── REQUIREMENTS.md    # spesifikasi fungsional command bot
│   └── SETUP.md           # langkah instalasi VPS step-by-step
├── bot/
│   └── telegram_mt5_executor.py   # bot Telegram + eksekutor MT5
└── ea/
    └── CommandPoller.mq5  # (opsional/alternatif) EA MQL5 kalau pakai arsitektur split
```

> Catatan: `ea/CommandPoller.mq5` adalah alternatif arsitektur (split server) yang
> dipertimbangkan sebelum memutuskan pakai `mt5linux` di satu VPS. Simpan sebagai
> referensi, tapi arsitektur yang aktif dipakai adalah `mt5linux`, bukan EA polling ini.

## Kalau menambah fitur baru

Sebelum menambah command atau fitur baru, cek `docs/REQUIREMENTS.md` dulu — pastikan
format command konsisten dengan yang sudah ada (`/action SYMBOL LOT [SLxxxx] [TPxxxx]`).
