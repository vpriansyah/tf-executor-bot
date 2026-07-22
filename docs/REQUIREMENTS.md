# Requirements

## Functional Requirements

### FR1 — Autentikasi
- Bot hanya merespons command dari satu Telegram user ID (`ALLOWED_USER_ID`).
- User lain yang kirim command mendapat balasan "Akses ditolak", tanpa eksekusi apa pun.

### FR2 — Market order
| Command | Format | Keterangan |
|---|---|---|
| `/buy` | `/buy SYMBOL LOT [SLxxxx] [TPxxxx]` | Buka posisi buy market |
| `/sell` | `/sell SYMBOL LOT [SLxxxx] [TPxxxx]` | Buka posisi sell market |

SL/TP opsional. Kalau tidak diisi, order dikirim tanpa SL/TP.

### FR3 — Pending order
| Command | Format |
|---|---|
| `/buylimit` | `/buylimit SYMBOL LOT PRICE [SLxxxx] [TPxxxx]` |
| `/selllimit` | `/selllimit SYMBOL LOT PRICE [SLxxxx] [TPxxxx]` |

### FR4 — Manajemen posisi/order
| Command | Format | Efek |
|---|---|---|
| `/close` | `/close TICKET` | Tutup posisi terbuka sesuai ticket |
| `/cancel` | `/cancel TICKET` | Batalkan pending order sesuai ticket |
| `/positions` | `/positions` | List semua posisi terbuka + profit floating |
| `/orders` | `/orders` | List semua pending order |

### FR5 — Feedback eksekusi
Setiap command yang mengeksekusi order harus membalas ke chat dengan minimal:
retcode, ticket (kalau berhasil), atau pesan error yang jelas (kalau gagal).

### FR6 — Audit log
Setiap command yang menyentuh order (buy/sell/buylimit/selllimit/close/cancel) dicatat
ke file log lokal dengan format: `timestamp | command_mentah | user_id | hasil`.

## Non-Functional Requirements

### NFR1 — Infrastruktur
- Harus jalan di 1 VPS Linux (tidak boleh menambah server).
- Harus survive reboot VPS tanpa intervensi manual (systemd auto-start).

### NFR2 — Keamanan
- Kredensial tidak boleh hardcoded di source code yang di-commit.
- `.env` wajib masuk `.gitignore`.

### NFR3 — Latency
- Target waktu dari command dikirim sampai order tereksekusi: di bawah 3 detik
  dalam kondisi normal (belum termasuk latency jaringan ke server broker).

### NFR4 — Reliability
- Kalau `mt5linux` bridge putus koneksi, bot harus balas pesan error yang jelas
  ke user (bukan silent fail / hang tanpa respons).

## Out of scope (sengaja tidak dikerjakan)

- Membaca sinyal otomatis dari signal provider manapun (lihat `CLAUDE.md` § alasan).
- Auto-cancel/auto-expire mengikuti provider — ini tetap manual, user kirim `/cancel`
  sendiri saat melihat perubahan di sumber sinyal.
- Multi-user support — bot ini didesain single-owner.

## Command format reference (untuk AI agent yang menambah command baru)

Pola konsisten yang dipakai: `/action SYMBOL LOT [modifier...]`, modifier ditulis
sebagai `KEYxxxx` tanpa spasi (contoh `SL1945`, `TP1965`) supaya gampang di-parse
dengan fungsi `parse_sl_tp()` yang sudah ada di `bot/telegram_mt5_executor.py`.
Command baru sebaiknya ikuti pola ini, bukan format baru yang beda gaya.
