# 🤖 TF Executor Bot — MetaTrader 5 (Finex) Telegram Executor

**TF Executor Bot** adalah sistem eksekutor order MetaTrader 5 (MT5) otomatis & manual berbasis Docker yang dikendalikan melalui **Telegram Bot**. Bot ini dirancang khusus untuk memproses perintah trading teks manual maupun membaca **screenshot/gambar sinyal trading** menggunakan AI (Google Gemini Vision) untuk dipasang secara presisi pada akun broker **Finex** di MT5.

---

## ⚡ Quick Start (Jalankan di VPS Linux via Docker)

Hanya butuh **1 Perintah Docker Compose** di VPS Linux Anda (Ubuntu 22.04 / 24.04 disarankan).

### Langkah 1: Clone Repository & Masuk Folder
```bash
git clone https://github.com/username/tf-executor-bot.git
cd tf-executor-bot
```

### Langkah 2: Salin & Isi Konfigurasi `.env`
```bash
cp .env.example .env
nano .env
```
Isi variabel berikut:
* `BOT_TOKEN`: Token dari `@BotFather`
* `ALLOWED_USER_ID`: User ID Telegram Anda dari `@userinfobot`
* `GEMINI_API_KEY`: API Key dari [Google AI Studio](https://aistudio.google.com)
* `MT5_LOGIN`: Nomor login akun MT5 Finex Anda
* `MT5_PASSWORD`: Password akun MT5 Finex Anda
* `MT5_SERVER`: `FinexBisnisSolusi-Demo` atau `FinexBisnisSolusi-Real`
* `DEFAULT_LOT`: Default lot (contoh: `0.01` atau `0.10`)
* `AUTO_EXECUTE_IMAGE`: `false` (dengan tombol konfirmasi) atau `true` (langsung pasang)

### Langkah 3: Jalankan Container Docker
```bash
docker compose up -d --build
```

### Langkah 4: Cek Log Status Bot
```bash
docker compose logs -f
```
*(Selesai! Bot Telegram & MT5 Terminal siap menerima command Anda).*

---

## 🛠️ Perintah Telegram lengkap

### 📸 Sinyal Screenshot Sinyal Trading (AI Gemini Vision)
Cukup **kirimkan foto / screenshot sinyal trading** dari aplikasi mana pun ke Telegram Bot.
- Bot membaca `Action`, `Symbol`, `Lot`, `Entry Price`, `SL`, `TP`, dan `Expired`.
- Jika `AUTO_EXECUTE_IMAGE=false`: Bot menampilkan ringkasan & tombol `[✅ Eksekusi]` / `[❌ Batal]`.
- Jika `AUTO_EXECUTE_IMAGE=true`: Bot langsung mengeksekusi order secara otomatis ke MT5.

### ⚙️ Pengaturan & Konfigurasi Bot (Direct Telegram)
* `/config` — Melihat status konfigurasi saat ini.
* `/setautoimage <on|off>` — Mengubah mode auto eksekusi foto sinyal (`on` / `off`).
* `/setlot <lot_size>` — Mengubah default lot order.
* `/setaccount <login> <password> <server>` — Mengubah akun MT5 & server broker.
* `/setlogin <login> <password>` — Mengubah login & password akun MT5.
* `/setserver <server_name>` — Mengubah nama server broker MT5.

### 📈 Trading Manual
* `/buy XAUUSD 0.10 SL2640 TP2670`
* `/sell EURUSD 0.05 SL1.0850 TP1.0750`
* `/buylimit XAUUSD 0.10 2620 SL2600 TP2650`
* `/selllimit XAUUSD 0.10 2680 SL2700 TP2650`
* `/order XAUUSD 0.10 2620` — (Smart Order) Otomatis menentukan *Limit / Stop / Market* berdasarkan harga saat ini.

### 💼 Kelola Posisi & Pending Order
* `/status` — Cek status koneksi MT5, nama akun, balance & equity.
* `/positions` — Melihat daftar posisi terbuka.
* `/orders` — Melihat daftar pending order aktif.
* `/close 1` — Menutup posisi urutan #1 dari list (atau `/close all`).
* `/cancel 1` — Membatalkan pending order urutan #1 dari list (atau `/cancel all`).

---

## 📚 Dokumentasi Pendukung

- [`docs/PANDUAN_INSTALASI_AWAM.md`](docs/PANDUAN_INSTALASI_AWAM.md) — Panduan lengkap langkah demi langkah untuk awam/pemula.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — Arsitektur teknis Wine + Xvfb + mt5linux + Docker.
- [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) — Spesifikasi fungsional command & aturan bisnis.
- [`CLAUDE.md`](CLAUDE.md) — Catatan arsitektur & panduan untuk AI Agent.

---

## ⚠️ Peringatan Risiko

Trading forex berisiko tinggi. Bot ini adalah alat bantu eksekusi otomatis/manual. Uji coba selalu di **Akun Demo** sebelum menggunakannya pada akun real.
