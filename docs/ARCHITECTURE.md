# Architecture

## Diagram alur

```
[Pemilik akun]
     |  baca sinyal manual dari signal provider (di luar sistem ini)
     |  kirim command via Telegram, contoh: /buy XAUUSD 0.10 SL1945 TP1965
     v
[Telegram Bot API]
     v
[bot/telegram_mt5_executor.py]   <-- Python native Linux, jalan di VPS
     |  from mt5linux import MetaTrader5
     |  panggil lewat rpyc/localhost
     v
[mt5linux server]                <-- Python-Windows, jalan DI DALAM Wine prefix
     v
[MetaTrader5 terminal64.exe]     <-- jalan via Wine + Xvfb (headless), di VPS yang sama
     v
[Server broker Finex]
     v
[Akun MT5 Finex] --- posisi/order juga terlihat di MT5 mobile pemilik (akun sama)
```

Semua komponen (kecuali Telegram API dan server broker) jalan di **satu VPS Linux**
yang sama. Tidak ada mesin kedua.

## Komponen

### 1. Telegram Bot (`bot/telegram_mt5_executor.py`)
- Library: `python-telegram-bot`
- Menerima command, validasi `ALLOWED_USER_ID`, parsing argumen
- Memanggil `mt5linux.MetaTrader5` untuk eksekusi
- Membalas hasil (retcode, ticket) ke chat

### 2. mt5linux bridge
- Jalan sebagai proses terpisah di dalam Wine prefix (Python-Windows)
- Dijalankan dengan: `wine python.exe -m mt5linux <path/to/python.exe>`
- Expose RPyC server di localhost, default port `18812`
- Bot Python native connect ke sini, bukan langsung ke MT5

### 3. MT5 Terminal (via Wine)
- Diinstal dengan script resmi dari metatrader5.com (auto-detect distro Linux)
- Login ke akun Finex (kredensial disimpan di terminal, bukan di kode)
- Algo Trading harus aktif (toolbar icon hijau)
- Jalan headless pakai Xvfb (virtual display `:99`), dikelola systemd service

### 4. Process management (systemd)
Tiga service disarankan agar semuanya auto-start setelah VPS reboot:
- `xvfb.service` — virtual display
- `mt5-wine.service` — MT5 terminal + mt5linux server (depends on xvfb.service)
- `tf-bot.service` — bot Telegram (depends on mt5-wine.service)

Detail unit file ada di `docs/SETUP.md`.

## Kenapa arsitektur ini (bukan alternatif lain)

| Alternatif | Alasan tidak dipakai |
|---|---|
| VPS Windows terpisah + EA MQL5 polling (`ea/CommandPoller.mq5`) | Butuh server kedua = biaya tambahan |
| Baca sinyal otomatis dari signal provider | Risiko ToS & akurasi (screenshot/OCR) |
| Jalankan semua di laptop pribadi | Laptop tidak selalu nyala 24 jam |

`ea/CommandPoller.mq5` disimpan di repo sebagai referensi kalau di masa depan mau
migrasi ke VPS Windows terpisah, tapi **bukan** arsitektur yang aktif dipakai sekarang.

## Data flow untuk satu command

1. User kirim `/buy XAUUSD 0.10 SL1945 TP1965` di Telegram
2. Bot cek `update.effective_user.id == ALLOWED_USER_ID`
3. Bot parsing: symbol=XAUUSD, lot=0.10, sl=1945, tp=1965
4. Bot panggil `mt5.symbol_info_tick()` untuk harga terkini via bridge
5. Bot build `request` dict, panggil `mt5.order_send(request)`
6. mt5linux meneruskan request ke MT5 terminal (dalam Wine)
7. MT5 kirim order ke server Finex, dapat hasil (retcode, ticket)
8. Hasil dikembalikan lewat rantai yang sama ke bot, bot balas ke Telegram
9. Bot log command + hasil ke file audit
