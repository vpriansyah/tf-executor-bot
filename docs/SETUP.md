# Setup Guide — 1 VPS Linux

Panduan ini mengasumsikan VPS Ubuntu/Debian dengan akses root/sudo. Sesuaikan kalau
distro Anda berbeda (script MT5 juga support Mint & Fedora).

Cek dulu spek VPS: minimal disarankan 1-2GB RAM tersedia setelah OS & servis lain
jalan. Wine + MT5 + virtual display punya overhead lebih besar dari script Python biasa.

## 1. Install Wine + MT5

```bash
# Download & jalankan script instalasi resmi MetaTrader (auto-detect distro)
sudo bash -c "$(wget -O - https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5ubuntu.sh)"
```

Kalau diminta install paket tambahan (Mono, Gecko), setujui — dibutuhkan agar MT5 jalan.

Setelah instalasi selesai, MT5 akan otomatis coba membuka GUI. Login manual sekali
ke akun Finex Anda untuk memastikan kredensial benar dan Algo Trading bisa diaktifkan
(toolbar icon jadi hijau).

## 2. Jalankan headless dengan Xvfb + systemd

Install Xvfb:
```bash
sudo apt install -y xvfb
```

Buat unit file `/etc/systemd/system/xvfb.service`:
```ini
[Unit]
Description=Virtual display for MT5
After=network.target

[Service]
ExecStart=/usr/bin/Xvfb :99 -screen 0 1024x768x16
Restart=always

[Install]
WantedBy=multi-user.target
```

Buat wrapper script `/opt/mt5/start-mt5.sh`:
```bash
#!/bin/bash
export DISPLAY=:99
export WINEPREFIX=/root/.wine   # sesuaikan path wine prefix Anda
wine "/root/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe" /portable
```

Buat unit file `/etc/systemd/system/mt5-wine.service`:
```ini
[Unit]
Description=MT5 terminal via Wine
After=xvfb.service
Requires=xvfb.service

[Service]
ExecStart=/opt/mt5/start-mt5.sh
Restart=no

[Install]
WantedBy=multi-user.target
```

> Catatan: Wine sering fork-and-exit di proses awal. Kalau systemd menganggap
> service "mati" padahal MT5 masih jalan, cek dokumentasi `Type=forking` atau
> pakai wrapper yang menunggu proses child.

Aktifkan semua service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now xvfb.service
sudo systemctl enable --now mt5-wine.service
```

## 3. Install Python-Windows di dalam Wine + package MetaTrader5

```bash
export WINEPREFIX=/root/.wine
cd ~/Downloads
wget https://www.python.org/ftp/python/3.11.0/python-3.11.0-amd64.exe
wine python-3.11.0-amd64.exe
```

Ikuti instalasi GUI Python (centang "Add to PATH" kalau muncul opsinya).

Cari path `python.exe` hasil instalasi (biasanya di
`~/.wine/drive_c/users/<user>/AppData/Local/Programs/Python/Python311/python.exe`),
lalu install package yang dibutuhkan:
```bash
wine ~/.wine/drive_c/users/root/AppData/Local/Programs/Python/Python311/python.exe -m pip install MetaTrader5 mt5linux
```

## 4. Jalankan mt5linux server

```bash
export WINEPREFIX=/root/.wine
wine ~/.wine/drive_c/.../python.exe -m mt5linux ~/.wine/drive_c/.../python.exe
```

Sebaiknya bungkus ini juga jadi systemd service (`mt5-bridge.service`) yang
`After=mt5-wine.service`, supaya auto-start.

## 5. Setup bot Python native Linux

```bash
sudo apt install -y python3-pip
pip3 install python-telegram-bot==21.* mt5linux python-dotenv
```

Buat file `.env` (JANGAN commit ke git):
```
BOT_TOKEN=isi_token_dari_botfather
ALLOWED_USER_ID=isi_chat_id_anda
```

Update `bot/telegram_mt5_executor.py` untuk baca dari `.env` (pakai `python-dotenv`)
alih-alih hardcode, dan ganti import jadi:
```python
from mt5linux import MetaTrader5
mt5 = MetaTrader5()  # default connect ke localhost:18812
```

Jalankan:
```bash
python3 bot/telegram_mt5_executor.py
```

Kalau sudah stabil, bungkus jadi systemd service (`tf-bot.service`) yang
`After=mt5-bridge.service`.

## 6. Checklist verifikasi sebelum live

- [ ] `/start` di Telegram membalas dengan chat ID yang benar
- [ ] `/positions` dan `/orders` berhasil connect ke MT5 (tidak error koneksi)
- [ ] Test `/buy` di akun **demo** dulu, cek muncul di MT5 mobile
- [ ] Test `/cancel` pada pending order demo, pastikan hilang dari MT5 mobile
- [ ] Reboot VPS, pastikan semua systemd service auto-start dan bot tetap responsif
- [ ] Baru setelah semua di atas lolos, ganti kredensial ke akun live Finex
