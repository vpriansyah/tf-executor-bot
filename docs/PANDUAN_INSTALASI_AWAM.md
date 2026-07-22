# 📖 Panduan Lengkap Instalasi & Penggunaan TF Executor Bot (VPS Docker)

Selamat datang! Panduan ini dibuat khusus dengan langkah-demi-langhah yang ringkas dan jelas agar Anda dapat memasang dan menjalankan **TF Executor Bot** di VPS Linux Anda hanya dengan Docker.

---

## 📌 1. Persiapan Bahan

Sebelum mulai, siapkan data berikut:

1. **VPS Linux** (Ubuntu 22.04 / 24.04 disarankan, RAM minimal 1 GB - 2 GB).
2. **Token Bot Telegram** (dari `@BotFather`).
3. **Chat ID Telegram Anda** (dari `@userinfobot`).
4. **Google Gemini API Key** (Gratis dari [Google AI Studio](https://aistudio.google.com)).
5. **Kredensial Akun MT5 Finex** (Nomor Login, Password, Nama Server misal: `FinexBisnisSolusi-Demo` atau `FinexBisnisSolusi-Real`).

---

## 🤖 2. Cara Ambil Bahan Kredensial

### A. Buat Bot Telegram & Ambil Token
1. Buka Telegram ➔ Cari **`@BotFather`**.
2. Ketik `/newbot` ➔ Isi Nama Bot & Username Bot (harus akhiran `bot`).
3. Salin **HTTP API Token** yang diberikan (contoh: `8927886042:AAGT7-xxxxxxxxxxxx`).

### B. Cari User ID Telegram Anda (Pengaman Bot)
1. Buka Telegram ➔ Cari **`@userinfobot`**.
2. Klik **Start** ➔ Catat angka **Id** Anda (contoh: `1058168406`).

### C. Ambil Gemini API Key (Membaca Foto Sinyal)
1. Buka [Google AI Studio](https://aistudio.google.com).
2. Login akun Google ➔ Klik **Get API Key** ➔ **Create API Key**.
3. Salin kode API Key tersebut.

---

## 🚀 3. Jalankan di VPS Linux (Menggunakan Docker)

Masuk ke VPS via Terminal / PuTTY (`ssh root@IP_VPS_ANDA`), lalu jalankan langkah berikut:

### Langkah 1: Clone Repository
```bash
git clone https://github.com/username/tf-executor-bot.git
cd tf-executor-bot
```

### Langkah 2: Buat File `.env`
Salin dari contoh template `.env.example`:
```bash
cp .env.example .env
nano .env
```

Isi data kredensial Anda di file `.env`:
```env
BOT_TOKEN=8927886042:AAGT7-xxxxxxxxxxxx
ALLOWED_USER_ID=1058168406
MT5_BRIDGE_HOST=localhost
MT5_BRIDGE_PORT=18812
GEMINI_API_KEY=AIzaSyBxxxxxxxxxxxx
DEFAULT_LOT=0.01
AUTO_EXECUTE_IMAGE=false

MT5_LOGIN=61425413
MT5_PASSWORD=password_mt5_anda
MT5_SERVER=FinexBisnisSolusi-Demo
```
*(Tekan `Ctrl+O` lalu `Enter` untuk menyimpan, lalu `Ctrl+X` untuk keluar dari nano).*

### Langkah 3: Nyalakan Docker
```bash
docker compose up -d --build
```

### Langkah 4: Cek Log Kesiapan Bot
```bash
docker compose logs -f
```
Tunggu hingga log menunjukkan:
`[OK] mt5linux bridge server SIAP di localhost:18812!`
`Bot Telegram siap & mendengarkan pesan...`

*(Tekan `Ctrl+C` untuk keluar dari tampilan log).*

---

## 📸 4. Fitur Foto Screenshot Sinyal Trading (AI Vision)

Cukup **kirimkan foto / screenshot sinyal trading** dari channel sinyal atau aplikasi mana pun ke Bot Telegram Anda:
1. AI Gemini akan membaca simbol, tipe transaksi, lot, entry price, SL, TP, dan expired time.
2. Jika `AUTO_EXECUTE_IMAGE=false` *(default)*: Bot menampilkan ringkasan sinyal dan 2 tombol: `[ ✅ Eksekusi Order ]` dan `[ ❌ Batal ]`. Klik tombol untuk mengeksekusi ke MT5.
3. Jika `AUTO_EXECUTE_IMAGE=true`: Bot langsung memasang order otomatis ke MT5 Finex.

---

## 📱 5. Panduan Perintah Bot di Telegram

### A. Pengaturan & Config Langsung via Telegram
* **`/config`** — Melihat status semua konfigurasi bot saat ini.
* **`/setautoimage on`** atau **`/setautoimage off`** — Mengubah mode eksekusi foto sinyal otomatis / konfirmasi.
* **`/setlot 0.05`** — Mengubah default lot.
* **`/setaccount <login> <password> <server>`** — Mengubah akun MT5 & server broker sekaligus.
* **`/setlogin <login> <password>`** — Mengubah nomor login & password MT5.
* **`/setserver FinexBisnisSolusi-Real`** — Mengubah server broker MT5.

### B. Trading Manual
* **`/buy XAUUSD 0.01 SL2640 TP2670`**
* **`/sell EURUSD 0.05 SL1.0850 TP1.0750`**
* **`/buylimit XAUUSD 0.01 2620 SL2600 TP2650`**
* **`/selllimit XAUUSD 0.01 2680 SL2700 TP2650`**

### C. Cek Status & Tutup Posisi
* **`/status`** — Cek koneksi MT5, balance, & equity akun.
* **`/positions`** — Menampilkan daftar posisi terbuka aktif.
* **`/orders`** — Menampilkan daftar pending order aktif.
* **`/close 1`** — Menutup posisi urutan #1 (atau `/close all`).
* **`/cancel 1`** — Membatalkan pending order urutan #1 (atau `/cancel all`).

---

## 🛠️ Perintah Berguna untuk Pengelolaan Docker

* **Melihat Log Bot (Realtime):**
  ```bash
  docker compose logs -f
  ```
* **Restart Container Bot:**
  ```bash
  docker compose restart
  ```
* **Menghentikan Container:**
  ```bash
  docker compose down
  ```
