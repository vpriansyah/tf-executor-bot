#!/bin/bash
# Note: set -e removed to prevent premature exits during wine/xdotool subshell commands

export DISPLAY=:99
export WINEPREFIX=/root/.wine
export WINEARCH=win64
export WINEDEBUG=-all
export WINEDLLOVERRIDES="mscoree,mshtml="

echo "=================================================="
echo "   STARTING TF EXECUTOR BOT DOCKER CONTAINER      "
echo "=================================================="

# 1. Start Xvfb Virtual Display
echo "[1/4] Starting Xvfb Virtual Display (DISPLAY=:99)..."
if [ -f /tmp/.X99-lock ]; then
    rm -f /tmp/.X99-lock
fi
Xvfb :99 -screen 0 1024x768x16 &
sleep 2

# Configure Wine GDI Rendering & Windows 10 mode for headless Xvfb
winecfg -v=win10 >/dev/null 2>&1 || true
wine reg add "HKCU\Software\Wine\Direct3D" /v "renderer" /t REG_SZ /d "gdi" /f >/dev/null 2>&1 || true
wine reg add "HKCU\Software\Wine\Direct3D" /v "OffscreenRenderingMode" /t REG_SZ /d "backbuffer" /f >/dev/null 2>&1 || true
wine reg add "HKCU\Software\MetaQuotes\Terminal" /v "Path" /t REG_SZ /d "C:\Program Files\MetaTrader 5" /f >/dev/null 2>&1 || true

# 2. Setup Portable Python 3.11 Windows di Wine C:\Python311 jika belum ada
PY_WIN="$WINEPREFIX/drive_c/Python311/python.exe"
if [ ! -f "$PY_WIN" ]; then
    echo "[SETUP] Installing Portable Python 3.11 Windows in Wine (C:\Python311)..."
    mkdir -p "$WINEPREFIX/drive_c/Python311"
    cd /tmp
    wget -q https://www.python.org/ftp/python/3.11.0/python-3.11.0-embed-amd64.zip -O python-embed.zip
    python3 -m zipfile -e python-embed.zip "$WINEPREFIX/drive_c/Python311"
    rm -f python-embed.zip

    # Enable site-packages in embedded python
    sed -i 's/#import site/import site/' "$WINEPREFIX/drive_c/Python311/python311._pth"

    # Install pip inside Wine Python
    echo "[SETUP] Installing pip in Wine Python..."
    wget -q https://bootstrap.pypa.io/get-pip.py -O /tmp/get-pip.py
    wine "$PY_WIN" /tmp/get-pip.py --no-warn-script-location || true
    rm -f /tmp/get-pip.py

    # Install MetaTrader5, mt5linux, and rpyc packages
    echo "[SETUP] Installing MetaTrader5, mt5linux & rpyc in Wine Python..."
    wine "$PY_WIN" -m pip install --no-cache-dir MetaTrader5 mt5linux rpyc || true
    cd /app
fi

# 3. Copy custom broker config & full profile jika ada
if [ -d "/app/mt5_profile" ]; then
    echo "[PROFILE] Syncing full MT5 profile (bases, config, servers)..."
    TARGET_PROFILE="$WINEPREFIX/drive_c/users/root/AppData/Roaming/MetaQuotes/Terminal/D0E8209F77C8CF37AD8BF550E51FF075"
    mkdir -p "$TARGET_PROFILE"
    cp -rf /app/mt5_profile/* "$TARGET_PROFILE/"
fi

if [ -d "/app/config" ]; then
    echo "[CONFIG] Copying custom MT5 config files (servers.dat, accounts.dat, etc)..."
    mkdir -p "$WINEPREFIX/drive_c/Program Files/MetaTrader 5/Config"
    cp -rf /app/config/* "$WINEPREFIX/drive_c/Program Files/MetaTrader 5/Config/"

    # Copy juga ke AppData Hash dir MT5 jika ada
    APPDATA_MQ="$WINEPREFIX/drive_c/users/root/AppData/Roaming/MetaQuotes/Terminal"
    if [ -d "$APPDATA_MQ" ]; then
        for hash_dir in "$APPDATA_MQ"/*; do
            if [ -d "$hash_dir" ] && [ "$(basename "$hash_dir")" != "Common" ] && [ "$(basename "$hash_dir")" != "Community" ]; then
                mkdir -p "$hash_dir/config"
                cp -rf /app/config/* "$hash_dir/config/"
            fi
        done
    fi
fi

# 4. Preparing & Launching MT5 Terminal startup config
MT5_EXE="$WINEPREFIX/drive_c/Program Files/MetaTrader 5/terminal64.exe"
MT5_CONFIG_DIR="$WINEPREFIX/drive_c/Program Files/MetaTrader 5/Config"
mkdir -p "$MT5_CONFIG_DIR"

# Write common.ini to force-enable Algo Trading and DLL imports in MT5
cat <<EOF > "$MT5_CONFIG_DIR/common.ini"
[Common]
Login=$MT5_LOGIN
Password=$MT5_PASSWORD
Server=$MT5_SERVER
EnableNews=0
ExpertsEnable=1
ExpertsDll=1
ExpertsExp=1
EOF

# Copy common.ini into AppData hash config dirs
APPDATA_MQ="$WINEPREFIX/drive_c/users/root/AppData/Roaming/MetaQuotes/Terminal"
if [ -d "$APPDATA_MQ" ]; then
    for hash_dir in "$APPDATA_MQ"/*; do
        if [ -d "$hash_dir" ] && [ "$(basename "$hash_dir")" != "Common" ] && [ "$(basename "$hash_dir")" != "Community" ]; then
            mkdir -p "$hash_dir/config"
            cp -f "$MT5_CONFIG_DIR/common.ini" "$hash_dir/config/common.ini"
        fi
    done
fi

echo "[2/4] Checking MetaTrader 5 Terminal in Wine..."
FOUND_EXE=$(find "$WINEPREFIX/drive_c" \( -iname "terminal64.exe" -o -iname "terminal.exe" \) 2>/dev/null | head -n 1 || true)
if [ -n "$FOUND_EXE" ] && [ -f "$FOUND_EXE" ]; then
    SIZE=$(stat -c%s "$FOUND_EXE" 2>/dev/null || echo 0)
    if [ "$SIZE" -gt 5000000 ]; then
        MT5_EXE="$FOUND_EXE"
    fi
fi

if [ ! -f "$MT5_EXE" ] || [ $(stat -c%s "$MT5_EXE" 2>/dev/null || echo 0) -lt 5000000 ]; then
    echo "[INFO] MT5 Terminal belum lengkap/ter-install. Mengunduh WebView2 & MetaTrader 5..."
    mkdir -p /tmp/mt5-install
    cd /tmp/mt5-install

    # Install Microsoft Edge WebView2 Runtime (Wajib untuk installer MT5 versi terbaru)
    if [ ! -f "$WINEPREFIX/drive_c/wv2_installed" ]; then
        echo "[SETUP] Mengunduh & menginstall Microsoft Edge WebView2 Runtime di Wine..."
        wget -q "https://msedge.sf.dl.delivery.mp.microsoft.com/filestreamingservice/files/c1336fd6-a2eb-4669-9b03-949fc70ace0e/MicrosoftEdgeWebview2Setup.exe" -O WebView2Setup.exe || true
        DISPLAY=:99 wine WebView2Setup.exe /silent /install >/dev/null 2>&1 || true
        touch "$WINEPREFIX/drive_c/wv2_installed"
        sleep 3
    fi

    # Pastikan Wine Prefix ter-inisialisasi sempurna sebelum menjalankan installer
    echo "[SETUP] Menyiapkan environment Wine prefix..."
    WINEARCH=win64 wineboot -u >/dev/null 2>&1 || true
    sleep 3

    if [ -f "/app/mt5_app/terminal64.exe" ]; then
        echo "[SETUP] Menggunakan instalasi MT5 lokal dari /app/mt5_app..."
        TARGET_DIR="$WINEPREFIX/drive_c/Program Files/MetaTrader 5"
        mkdir -p "$TARGET_DIR"
        cp -rf /app/mt5_app/* "$TARGET_DIR/" 2>/dev/null || true
        MT5_EXE="$TARGET_DIR/terminal64.exe"
        echo "[OK] Berhasil menyalin MT5 dari /app/mt5_app!"
    else
        echo "[SETUP] Mengunduh installer MetaTrader 5 resmi dengan Desktop User-Agent..."
        UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        wget --user-agent="$UA" -q https://download.mql5.com/cdn/web/finex.bisnis.solusi/mt5/finex5setup.exe -O finex5setup.exe || true
        wget --user-agent="$UA" -q https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe -O mt5setup.exe || true

        # Ekstraksi Biner MT5 secara langsung menggunakan 7z jika installer terunduh (>500KB)
        SETUP_BIN=""
        if [ -s finex5setup.exe ] && [ $(stat -c%s finex5setup.exe || echo 0) -gt 500000 ]; then
            SETUP_BIN="finex5setup.exe"
        elif [ -s mt5setup.exe ] && [ $(stat -c%s mt5setup.exe || echo 0) -gt 500000 ]; then
            SETUP_BIN="mt5setup.exe"
        fi

        if [ -n "$SETUP_BIN" ]; then
            echo "[SETUP] Meng-ekstrak biner MT5 (2-stage 7z unpack) dari $SETUP_BIN..."
            TARGET_DIR="$WINEPREFIX/drive_c/Program Files/MetaTrader 5"
            mkdir -p "$TARGET_DIR"
            rm -rf /tmp/mt5-step1 /tmp/mt5-step2
            7z x -y "$SETUP_BIN" -o/tmp/mt5-step1 >/dev/null 2>&1 || true
            SUB_ARCH=$(find /tmp/mt5-step1 -name "[0]" -o -name "*.cab" -o -size +10M 2>/dev/null | head -n 1 || true)
            if [ -n "$SUB_ARCH" ]; then
                echo "[SETUP] Unpacking biner utama dari sub-arsip $SUB_ARCH..."
                7z x -y "$SUB_ARCH" -o/tmp/mt5-step2/ >/dev/null 2>&1 || true
            fi
            
            FOUND_REAL=$(find /tmp/mt5-step1 /tmp/mt5-step2 -type f -size +5M 2>/dev/null | grep -i "terminal" | head -n 1 || true)
            if [ -n "$FOUND_REAL" ] && [ -f "$FOUND_REAL" ]; then
                REAL_DIR=$(dirname "$FOUND_REAL")
                echo "[SETUP] Memindahkan berkas MT5 dari $REAL_DIR ke $TARGET_DIR..."
                cp -rf "$REAL_DIR"/* "$TARGET_DIR/" 2>/dev/null || true
                mkdir -p "$WINEPREFIX/drive_c/MetaTrader5"
                cp -rf "$REAL_DIR"/* "$WINEPREFIX/drive_c/MetaTrader5/" 2>/dev/null || true
                MT5_EXE="$TARGET_DIR/terminal64.exe"
                SIZE=$(stat -c%s "$MT5_EXE" 2>/dev/null || echo 0)
                echo "[OK] Berhasil mengekstrak & memindahkan terminal64.exe PE32+ ($SIZE bytes) ke $MT5_EXE!"
            fi
        fi

        if [ -s "$SETUP_BIN" ]; then
            echo "[SETUP] Menjalankan Wine setup $SETUP_BIN secara silent (/auto /path:C:\\MetaTrader5)..."
            DISPLAY=:99 wine "$SETUP_BIN" /auto /path:C:\MetaTrader5 &
        fi

        echo "[SETUP] Mengunduh & memasang komponen MetaTrader 5 (membutuhkan 1-3 menit)..."
        COUNTER=0
        while [ $COUNTER -lt 90 ]; do
            COUNTER=$((COUNTER + 1))
            sleep 3
            FOUND_EXE=$(find "$WINEPREFIX/drive_c" \( -iname "terminal64.exe" -o -iname "terminal.exe" \) -size +5M 2>/dev/null | head -n 1 || true)
            if [ -z "$FOUND_EXE" ]; then
                FOUND_EXE=$(find "$WINEPREFIX/drive_c" \( -iname "terminal64.exe" -o -iname "terminal.exe" \) 2>/dev/null | head -n 1 || true)
            fi
            if [ -n "$FOUND_EXE" ] && [ -f "$FOUND_EXE" ]; then
                SIZE=$(stat -c%s "$FOUND_EXE" 2>/dev/null || echo 0)
                if [ "$SIZE" -gt 5000000 ]; then
                    MT5_EXE="$FOUND_EXE"
                    TARGET_DIR="$WINEPREFIX/drive_c/Program Files/MetaTrader 5"
                    mkdir -p "$TARGET_DIR"
                    REAL_DIR=$(dirname "$FOUND_EXE")
                    if [ "$REAL_DIR" != "$TARGET_DIR" ]; then
                        echo "[SETUP] Memindahkan berkas MT5 dari $REAL_DIR ke $TARGET_DIR..."
                        cp -rf "$REAL_DIR"/* "$TARGET_DIR/" 2>/dev/null || true
                    fi
                    echo "[OK] MetaTrader 5 Terminal BERHASIL ter-install ($SIZE bytes) di $TARGET_DIR/terminal64.exe!"
                    sleep 2
                    break
                else
                    echo "[SETUP #$COUNTER/90] MT5 sedang mengekstrak biner (ukuran saat ini: $SIZE bytes)..."
                fi
            else
                echo "[SETUP #$COUNTER/90] Menunggu installer MT5 mengekstrak biner ke C:\Program Files\MetaTrader 5..."
            fi
        done
    fi
    cd /app
fi

FOUND_EXE=""
for p in "$WINEPREFIX/drive_c/Program Files/MetaTrader 5/terminal64.exe" "$WINEPREFIX/drive_c/MetaTrader5/terminal64.exe"; do
    if [ -f "$p" ] && [ $(stat -c%s "$p" 2>/dev/null || echo 0) -gt 5000000 ]; then
        FOUND_EXE="$p"
        break
    fi
done
if [ -z "$FOUND_EXE" ]; then
    FOUND_EXE=$(find "$WINEPREFIX/drive_c" \( -iname "terminal64.exe" -o -iname "terminal.exe" \) 2>/dev/null | head -n 1 || true)
fi
if [ -n "$FOUND_EXE" ] && [ -f "$FOUND_EXE" ] && [ $(stat -c%s "$FOUND_EXE" 2>/dev/null || echo 0) -gt 5000000 ]; then
    MT5_EXE="$FOUND_EXE"
    MT5_DIR=$(dirname "$MT5_EXE")
    EXE_NAME=$(basename "$MT5_EXE")
    echo "[OK] Launching MT5 Terminal in Wine ($MT5_DIR/$EXE_NAME) (DISPLAY=:99)..."
    cd "$MT5_DIR"
    if [ -n "$MT5_LOGIN" ] && [ "$MT5_LOGIN" != "0" ]; then
        DISPLAY=:99 wine "$EXE_NAME" /login:"$MT5_LOGIN" /password:"$MT5_PASSWORD" /server:"$MT5_SERVER" &
    else
        DISPLAY=:99 wine "$EXE_NAME" &
    fi
    cd /app
    sleep 2
    DISPLAY=:99 xdotool key Escape 2>/dev/null || true
    sleep 1
else
    echo "⚠️ WARNING: MT5 Terminal ($MT5_EXE) belum terinstall dengan sempurna (file belum lengkap)."
fi

# 5. Start mt5linux server bridge di Wine
echo "[3/4] Starting mt5linux bridge server di Wine..."
DISPLAY=:99 wine "$PY_WIN" -u /app/bot/mt5_bridge_server.py &
BRIDGE_PID=$!


# Menunggu mt5linux bridge siap di port 18812
echo "Menunggu mt5linux bridge server di localhost:18812..."
BRIDGE_READY=0
COUNTER=0
while [ $COUNTER -lt 45 ]; do
    COUNTER=$((COUNTER + 1))
    if nc -z localhost 18812 2>/dev/null; then
        echo "[OK] mt5linux bridge server SIAP di localhost:18812!"
        BRIDGE_READY=1
        break
    fi
    sleep 1
done

if [ $BRIDGE_READY -eq 0 ]; then
    echo "⚠️ WARNING: mt5linux bridge belum siap di port 18812 setelah 45 detik."
    echo "   Melanjutkan ke Telegram Bot, bot akan terus mencoba rekonek secara otomatis."
fi

# 6. Start Telegram Bot Python Native
echo "[4/4] Starting Telegram MT5 Executor Bot..."
exec python3 bot/telegram_mt5_executor.py

