"""
Telegram Bot -> Eksekutor Order MT5 (Finex)
=============================================

CARA KERJA
----------
1. Kirim command manual ATAU kirim Gambar/Screenshot sinyal trading.
2. Bot menganalisis gambar dengan Gemini AI Vision / mengeksekusi command.
3. Bot mengeksekusi order ke terminal MT5 desktop yang login ke akun Finex.
4. Order langsung muncul di MT5 mobile Anda.

FORMAT COMMAND (contoh)
------------------------
/buy XAUUSD 0.10 SL1945 TP1965
/sell EURUSD 0.05
/buylimit XAUUSD 0.10 1950 SL1945 TP1965
/selllimit XAUUSD 0.10 1970
/positions
/orders
/close 123456789
/cancel 123456789
"""

import asyncio
import logging
import os
import re
import sys
import uuid
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv


def parse_expiration_timestamp(expiration_val, client=None, symbol="XAUUSD") -> int:
    """
    Mengonversi string expired time (misal '24 Jul 2026, 15:06 WIB')
    menjadi Unix Timestamp yang langsung memasang tanggal & jam 15:06 pada picker MT5.
    """
    if not expiration_val:
        return 0

    if isinstance(expiration_val, (int, float)):
        return int(expiration_val)

    exp_str = str(expiration_val).strip()

    # Hapus kata timezone (WIB, WITA, WIT, UTC, GMT)
    exp_clean = re.sub(r'\b(WIB|WITA|WIT|UTC|GMT)\b', '', exp_str, flags=re.IGNORECASE).strip()

    formats = [
        "%d %b %Y, %H:%M",
        "%d %b %Y %H:%M",
        "%d %b %Y, %H:%M:%S",
        "%d %b %Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d %B %Y, %H:%M",
        "%d %B %Y %H:%M",
    ]

    parsed_dt = None
    for fmt in formats:
        try:
            parsed_dt = datetime.strptime(exp_clean, fmt)
            break
        except ValueError:
            pass

    if parsed_dt is None:
        try:
            from dateutil import parser
            parsed_dt = parser.parse(exp_clean)
        except Exception:
            pass

    if parsed_dt is None:
        log.warning(f"Format expired time tidak dapat diparsing: '{expiration_val}' (cleaned: '{exp_clean}')")
        return 0

    # Gunakan tanggal dan jam hasil ekstrasi WIB secara langsung untuk timestamp MT5
    utc_broker_dt = datetime(
        parsed_dt.year, parsed_dt.month, parsed_dt.day,
        parsed_dt.hour, parsed_dt.minute, parsed_dt.second,
        tzinfo=timezone.utc
    )
    exp_ts = int(utc_broker_dt.timestamp())

    log.info(
        f"Expiration parse SUCCESS (Direct WIB): '{expiration_val}' -> {parsed_dt} "
        f"-> MT5 Exp Timestamp: {exp_ts}"
    )
    return exp_ts



def build_pending_request(symbol, lot, order_type, price, sl, tp, expiration=None):
    client = get_mt5()
    resolved_symbol = resolve_symbol(symbol)
    info_dict = get_symbol_info(client, resolved_symbol)

    if info_dict is None:
        all_syms = get_all_broker_symbols(client)
        if all_syms:
            sample_syms = ", ".join(all_syms[:20])
            err_msg = (
                f"Symbol '{symbol}' (resolved: '{resolved_symbol}') tidak terdaftar di Market Watch broker Finex Anda.\n"
                f"Simbol yang tersedia di broker Anda: {sample_syms}"
            )
        else:
            err_msg = (
                f"Symbol '{symbol}' tidak terdaftar di Market Watch broker Finex Anda.\n"
                f"Pastikan akun MT5 sudah login ke broker Finex dan Market Watch diaktifkan."
            )
        raise ValueError(err_msg)

    sl, tp = validate_and_adjust_stops(order_type, price, sl, tp, client)
    exp_ts = parse_expiration_timestamp(expiration, client=client, symbol=resolved_symbol) if expiration else 0

    req = {
        "action": client.TRADE_ACTION_PENDING,
        "symbol": resolved_symbol,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "magic": 990001,
        "comment": "telegram-executor",
        "type_filling": client.ORDER_FILLING_RETURN,
    }

    if exp_ts > 0:
        req["type_time"] = getattr(client, "ORDER_TIME_SPECIFIED", 2)
        req["expiration"] = exp_ts
    else:
        req["type_time"] = getattr(client, "ORDER_TIME_GTC", 0)

    return req


# ==== AUTO-DETECT OS: Windows pakai MT5 native, Linux pakai mt5linux bridge ====
IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import MetaTrader5 as _MT5Module  # native Windows — langsung konek ke terminal MT5
    log_platform = "Windows (native MT5)"
else:
    from mt5linux import MetaTrader5 as _MT5Module  # Linux — via rpyc bridge ke Wine
    log_platform = "Linux (mt5linux bridge)"

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from image_parser import parse_image_with_gemini

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mt5bot")

# ==== KONFIGURASI - dari .env ====
def reload_config():
    global BOT_TOKEN, ALLOWED_USER_ID, BRIDGE_HOST, BRIDGE_PORT, GEMINI_API_KEY, DEFAULT_LOT, AUTO_EXECUTE_IMAGE, MT5_LOGIN, MT5_PASSWORD, MT5_SERVER
    load_dotenv(override=True)
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "0")) if os.environ.get("ALLOWED_USER_ID", "").isdigit() else 0
    BRIDGE_HOST = os.environ.get("MT5_BRIDGE_HOST", "localhost")
    BRIDGE_PORT = int(os.environ.get("MT5_BRIDGE_PORT", "18812")) if os.environ.get("MT5_BRIDGE_PORT", "").isdigit() else 18812
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    DEFAULT_LOT = float(os.environ.get("DEFAULT_LOT", "0.10")) if os.environ.get("DEFAULT_LOT", "").replace(".", "", 1).isdigit() else 0.10
    AUTO_EXECUTE_IMAGE = os.environ.get("AUTO_EXECUTE_IMAGE", "false").lower() == "true"

    MT5_LOGIN = int(os.environ.get("MT5_LOGIN", "0")) if os.environ.get("MT5_LOGIN", "").isdigit() else None
    MT5_PASSWORD = os.environ.get("MT5_PASSWORD", "")
    MT5_SERVER = os.environ.get("MT5_SERVER", "FinexBisnisSolusi-Demo")

reload_config()

mt5 = None
PENDING_IMAGE_ORDERS = {}
# ======================================================


def get_mt5():
    """Lazy initialization untuk objek MetaTrader5.
    - Windows: langsung pakai modul MetaTrader5 (tanpa bridge).
    - Linux:   konek ke mt5linux bridge via rpyc (host:port).
    """
    global mt5
    if mt5 is None:
        if IS_WINDOWS:
            mt5 = _MT5Module  # modul MetaTrader5 dipanggil langsung (bukan instance)
        else:
            try:
                mt5 = _MT5Module(host=BRIDGE_HOST, port=BRIDGE_PORT)
                log.info(f"MT5 client initialized — platform: {log_platform}")
            except Exception as e:
                mt5 = None
                log.error(f"Gagal koneksi ke MT5 bridge di {BRIDGE_HOST}:{BRIDGE_PORT}: {e}")
                raise e
    return mt5




def is_owner(update: Update) -> bool:
    user = update.effective_user
    return user is not None and user.id == ALLOWED_USER_ID


MT5_INITIALIZED = False
USER_POSITION_INDEX = {}  # chat_id -> list of position tickets
USER_ORDER_INDEX = {}     # chat_id -> list of order tickets



async def guard(update: Update) -> bool:
    """Cek akses dan koneksi MT5 secara asinkron dengan timeout agar bot selalu responsif."""
    global MT5_INITIALIZED, mt5
    if not is_owner(update):
        if update.message:
            await update.message.reply_text("Bukan pemilik bot ini. Akses ditolak.")
        elif update.callback_query:
            await update.callback_query.answer("Bukan pemilik bot ini.", show_alert=True)
        return False

    if MT5_INITIALIZED and mt5 is not None:
        return True

    def _sync_init():
        global MT5_INITIALIZED
        client = get_mt5()
        if IS_WINDOWS:
            init_ok = client.initialize()
            if init_ok and MT5_LOGIN and MT5_PASSWORD:
                client.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
            MT5_INITIALIZED = init_ok
            return init_ok, str(client.last_error()) if not init_ok else ""
        else:
            # Di Linux/Wine (mt5linux bridge): MT5 di-initialize & login di mt5_bridge_server.py
            MT5_INITIALIZED = True
            return True, ""

    timeout = 15 if IS_WINDOWS else 30

    try:
        init_ok, err_msg = await asyncio.wait_for(
            asyncio.to_thread(_sync_init), timeout=timeout
        )
        if not init_ok:
            msg = f"⚠️ Gagal konek ke MT5 / Login Broker ({MT5_SERVER}): {err_msg}"
            if update.message:
                await update.message.reply_text(msg)
            elif update.callback_query:
                await update.callback_query.answer(msg, show_alert=True)
            return False
    except asyncio.TimeoutError:
        if not IS_WINDOWS:
            # Di Linux/Wine Docker: jika initialize menggantung karena Wine IPC, tandai initialized agar command trading tetap bisa diproses
            log.warning("Timeout initialize di Wine. Melanjutkan dengan bridge mt5linux...")
            MT5_INITIALIZED = True
            return True
        msg = f"⚠️ Koneksi ke MT5 timeout (>{timeout} detik). Terminal MT5 mungkin belum siap."
        log.warning(msg)
        if update.message:
            await update.message.reply_text(msg)
        elif update.callback_query:
            await update.callback_query.answer(msg, show_alert=True)
        return False
    except Exception as e:
        mt5 = None
        MT5_INITIALIZED = False
        msg = (
            f"⚠️ Belum terhubung ke MT5 Bridge ({BRIDGE_HOST}:{BRIDGE_PORT}): {e}\n"
            f"💡 Tips: Pastikan mt5_bridge_server.py berjalan di container Docker dan listening pada port {BRIDGE_PORT}."
        )
        log.warning(msg)
        if update.message:
            await update.message.reply_text(msg)
        elif update.callback_query:
            await update.callback_query.answer(msg, show_alert=True)
        return False

    return True



def parse_sl_tp(args):
    """Cari argumen SLxxxx / TPxxxx dari list args, kembalikan (sl, tp, sisa_args)."""
    sl = tp = 0.0
    rest = []
    for a in args:
        if a.upper().startswith("SL"):
            try:
                sl = float(a[2:])
            except ValueError:
                pass
        elif a.upper().startswith("TP"):
            try:
                tp = float(a[2:])
            except ValueError:
                pass
        else:
            rest.append(a)
    return sl, tp, rest


def get_symbol_info(client, symbol: str):
    """Mengambil symbol_info dan mengekstrak ke dict primitive agar aman dari deadlock RPyC."""
    try:
        sel_ok = client.symbol_select(symbol, True)
        info = client.symbol_info(symbol)
        if info is None and sel_ok:
            import time
            time.sleep(0.1)
            info = client.symbol_info(symbol)
        if info is not None:
            return {
                "name": str(info.name),
                "visible": bool(info.visible),
            }
    except Exception:
        pass
    return None


def get_symbol_tick(client, symbol: str):
    """Mengambil price tick dan mengekstrak ke dict primitive agar aman dari deadlock RPyC."""
    try:
        tick = client.symbol_info_tick(symbol)
        if tick is not None:
            return {
                "ask": float(tick.ask),
                "bid": float(tick.bid),
            }
    except Exception:
        pass
    return None


def get_all_broker_symbols(client):
    """Mengambil daftar nama simbol yang tersedia di broker MT5."""
    try:
        syms = client.symbols_get(group="*")
        if not syms:
            syms = client.symbols_get()
        if syms:
            return [str(s.name) for s in syms]
    except Exception as e:
        log.warning(f"Error fetching symbols_get: {e}")
    return []



def resolve_symbol(symbol: str) -> str:
    """Mencari nama simbol yang tepat yang terdaftar di broker Finex (misal XAUUSD -> GOLD / GOLD.f)."""
    client = get_mt5()
    symbol_upper = symbol.upper()

    # 1. Cek langsung simbol yang diminta
    info_dict = get_symbol_info(client, symbol_upper)
    if info_dict is not None:
        return symbol_upper

    # 2. Ambil semua simbol dari broker via symbols_get()
    all_syms = get_all_broker_symbols(client)

    ALIASES = {
        "XAUUSD": ["GOLD", "XAUUSD", "XAU"],
        "GOLD": ["GOLD", "XAUUSD", "XAU"],
        "EURUSD": ["EURUSD", "EUR"],
        "GBPUSD": ["GBPUSD", "GBP"],
        "USDJPY": ["USDJPY", "JPY"],
    }
    search_keywords = ALIASES.get(symbol_upper, [symbol_upper])

    if all_syms:
        # Match persis (case-insensitive)
        for s_name in all_syms:
            if s_name.upper() == symbol_upper:
                get_symbol_info(client, s_name)
                return s_name

        # Match kata kunci alias (misal kata 'GOLD' atau 'XAUUSD' di dalam nama s_name)
        for kw in search_keywords:
            for s_name in all_syms:
                if kw in s_name.upper():
                    get_symbol_info(client, s_name)
                    log.info(f"Symbol resolved via broker symbol list: {symbol_upper} -> {s_name}")
                    return s_name

    # 3. Fallback kandidat nama umum
    candidates = [symbol_upper]
    for kw in search_keywords:
        candidates.extend([kw, f"{kw}.f", f"{kw}m", f"{kw}#", f"{kw}_i", f"{kw}.ecn", f"{kw}_ecn", f"{kw}.a", f"{kw}.c"])

    for cand in candidates:
        info_dict = get_symbol_info(client, cand)
        if info_dict is not None:
            log.info(f"Symbol resolved via candidate list: {symbol_upper} -> {cand}")
            return cand

    return symbol_upper


def validate_and_adjust_stops(order_type, price, sl, tp, client):
    """Validasi arah SL dan TP terhadap harga masukan agar tidak ditolak MT5 dengan retcode=10016."""
    sl = float(sl) if sl else 0.0
    tp = float(tp) if tp else 0.0

    if sl == 0.0 and tp == 0.0:
        return 0.0, 0.0

    is_buy = order_type in (
        getattr(client, 'ORDER_TYPE_BUY', 0),
        getattr(client, 'ORDER_TYPE_BUY_LIMIT', 2),
        getattr(client, 'ORDER_TYPE_BUY_STOP', 4)
    )

    if is_buy:
        # Untuk BUY: SL harus < price, TP harus > price
        if sl > price and tp > 0 and tp < price:
            sl, tp = tp, sl  # Tukar jika terbalik
        if sl >= price and sl > 0:
            sl = 0.0
        if tp <= price and tp > 0:
            tp = 0.0
    else:
        # Untuk SELL: SL harus > price, TP harus < price
        if sl < price and sl > 0 and tp > price:
            sl, tp = tp, sl  # Tukar jika terbalik
        if sl <= price and sl > 0:
            sl = 0.0
        if tp >= price and tp > 0:
            tp = 0.0

    return sl, tp


def build_market_request(symbol, lot, order_type, sl, tp, deviation=20):
    client = get_mt5()
    resolved_symbol = resolve_symbol(symbol)
    info_dict = get_symbol_info(client, resolved_symbol)

    if info_dict is None:
        all_syms = get_all_broker_symbols(client)
        if all_syms:
            sample_syms = ", ".join(all_syms[:20])
            err_msg = (
                f"Symbol '{symbol}' (resolved: '{resolved_symbol}') tidak terdaftar di Market Watch broker Finex Anda.\n"
                f"Simbol yang tersedia di broker Anda: {sample_syms}"
            )
        else:
            err_msg = (
                f"Symbol '{symbol}' tidak terdaftar di Market Watch broker Finex Anda.\n"
                f"Pastikan akun MT5 sudah login ke broker Finex dan Market Watch diaktifkan."
            )
        raise ValueError(err_msg)

    tick_dict = get_symbol_tick(client, resolved_symbol)
    if tick_dict is None:
        raise ValueError(f"Gagal mengambil harga tick untuk {resolved_symbol}")

    price = tick_dict["ask"] if order_type == client.ORDER_TYPE_BUY else tick_dict["bid"]
    sl, tp = validate_and_adjust_stops(order_type, price, sl, tp, client)

    return {
        "action": client.TRADE_ACTION_DEAL,
        "symbol": resolved_symbol,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": deviation,
        "magic": 990001,
        "comment": "telegram-executor",
        "type_time": client.ORDER_TIME_GTC,
        "type_filling": client.ORDER_FILLING_IOC,
    }




def build_pending_request(symbol, lot, order_type, price, sl, tp, expiration=None):
    client = get_mt5()
    resolved_symbol = resolve_symbol(symbol)
    info_dict = get_symbol_info(client, resolved_symbol)

    if info_dict is None:
        all_syms = get_all_broker_symbols(client)
        if all_syms:
            sample_syms = ", ".join(all_syms[:20])
            err_msg = (
                f"Symbol '{symbol}' (resolved: '{resolved_symbol}') tidak terdaftar di Market Watch broker Finex Anda.\n"
                f"Simbol yang tersedia di broker Anda: {sample_syms}"
            )
        else:
            err_msg = (
                f"Symbol '{symbol}' tidak terdaftar di Market Watch broker Finex Anda.\n"
                f"Pastikan akun MT5 sudah login ke broker Finex dan Market Watch diaktifkan."
            )
        raise ValueError(err_msg)

    sl, tp = validate_and_adjust_stops(order_type, price, sl, tp, client)
    exp_ts = parse_expiration_timestamp(expiration) if expiration else 0

    req = {
        "action": client.TRADE_ACTION_PENDING,
        "symbol": resolved_symbol,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "magic": 990001,
        "comment": "telegram-executor",
        "type_filling": client.ORDER_FILLING_RETURN,
    }

    if exp_ts > 0:
        req["type_time"] = getattr(client, "ORDER_TIME_SPECIFIED", 2)
        req["expiration"] = exp_ts
    else:
        req["type_time"] = getattr(client, "ORDER_TIME_GTC", 0)

    return req



def safe_order_send(client, req):
    """Mengirimkan order_send ke MT5 dengan auto-recovery untuk error 10027 (AutoTrading) dan 10016 (Invalid Stops)."""
    result = client.order_send(req)

    # 1. Recovery retcode 10027: AutoTrading disabled
    if result is not None and getattr(result, "retcode", 0) == 10027:
        log.warning("Order gagal karena retcode=10027 (AutoTrading disabled). Menjalankan auto-fix via xdotool Ctrl+E...")
        try:
            import subprocess, os, time
            subprocess.run(["xdotool", "key", "ctrl+e"], env=dict(os.environ, DISPLAY=":99"), check=False)
            time.sleep(1)
            result = client.order_send(req)
            log.info(f"Hasil retry order_send setelah Ctrl+E: retcode={getattr(result, 'retcode', 'N/A')}")
        except Exception as e:
            log.error(f"Gagal auto-fix Ctrl+E: {e}")

    # 2. Recovery retcode 10016: Invalid Stops (SL/TP ditolak broker)
    if result is not None and getattr(result, "retcode", 0) == 10016:
        log.warning(f"Order ditolak retcode=10016 (Invalid stops: sl={req.get('sl')}, tp={req.get('tp')}). Auto-retry tanpa SL/TP...")
        req_copy = dict(req)
        req_copy["sl"] = 0.0
        req_copy["tp"] = 0.0
        result = client.order_send(req_copy)
        if result is not None and getattr(result, "retcode", 0) == getattr(client, "TRADE_RETCODE_DONE", 10009):
            log.info("Retry order_send tanpa SL/TP BERHASIL!")

    return result



def get_order_type_str(type_int: int) -> str:
    """Mengembalikan string tipe order yang mudah dibaca berdasarkan integer order_type MT5."""
    order_type_map = {
        0: "BUY",
        1: "SELL",
        2: "Buy Limit",
        3: "Sell Limit",
        4: "Buy Stop",
        5: "Sell Stop",
        6: "Buy Stop Limit",
        7: "Sell Stop Limit"
    }
    return order_type_map.get(type_int, f"Type {type_int}")


async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client = get_mt5()
    await _market_order(update, context, client.ORDER_TYPE_BUY)


async def cmd_sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client = get_mt5()
    await _market_order(update, context, client.ORDER_TYPE_SELL)


async def _market_order(update, context, order_type):
    if not await guard(update):
        return
    try:
        args = context.args
        if not args:
            await update.message.reply_text("⚠️ Format salah!\nGunakan: `/buy <symbol> <lot> [SL] [TP]`\nContoh: `/buy XAUUSD 0.10 SL1945 TP1965`", parse_mode="Markdown")
            return

        symbol = args[0].upper()
        lot = float(args[1]) if len(args) > 1 else DEFAULT_LOT
        sl, tp, _ = parse_sl_tp(args[2:]) if len(args) > 2 else (0.0, 0.0, 0)

        def _do_send():
            client = get_mt5()
            req = build_market_request(symbol, lot, order_type, sl, tp)
            return safe_order_send(client, req), req

        result, req = await asyncio.to_thread(_do_send)
        if result is not None and getattr(result, "retcode", 0) == getattr(get_mt5(), "TRADE_RETCODE_DONE", 10009):
            exec_price = getattr(result, "price", 0.0) if getattr(result, "price", 0.0) > 0 else req.get("price", 0.0)
            await update.message.reply_text(
                f"✅ **ORDER INSTANT MARKET BERHASIL!**\n"
                f"=================================\n"
                f"• Ticket: `#{result.order}`\n"
                f"• Symbol: **{symbol}**\n"
                f"• Action: **{'BUY' if order_type == 0 else 'SELL'}**\n"
                f"• Volume: **{lot:.2f} Lot**\n"
                f"• Price: `{exec_price}`\n"
                f"• Stop Loss: `{sl if sl else '-'}` | Take Profit: `{tp if tp else '-'}`",
                parse_mode="Markdown"
            )
        else:
            ret_code = getattr(result, "retcode", "N/A")
            comment = getattr(result, "comment", "N/A")
            await update.message.reply_text(f"⚠️ **Eksekusi Order Gagal** (retcode={ret_code}): {comment}", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal: {e}\nFormat: `/buy <symbol> <lot> [SL] [TP]`", parse_mode="Markdown")


async def cmd_buylimit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client = get_mt5()
    await _pending_order(update, context, client.ORDER_TYPE_BUY_LIMIT)


async def cmd_selllimit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client = get_mt5()
    await _pending_order(update, context, client.ORDER_TYPE_SELL_LIMIT)


async def _pending_order(update, context, order_type):
    if not await guard(update):
        return
    try:
        args = context.args
        if len(args) < 3:
            await update.message.reply_text("⚠️ Format salah!\nGunakan: `/buylimit <symbol> <lot> <price> [SL] [TP]`", parse_mode="Markdown")
            return

        symbol = args[0].upper()
        lot = float(args[1])
        price = float(args[2])
        sl, tp, _ = parse_sl_tp(args[3:]) if len(args) > 3 else (0.0, 0.0, 0)

        def _do_send():
            client = get_mt5()
            req, type_name = determine_smart_order_request(client, "BUY" if "BUY" in str(order_type) else "SELL", symbol, lot, price, sl, tp)
            return safe_order_send(client, req), type_name, req

        result, type_name, req = await asyncio.to_thread(_do_send)
        if result is not None and getattr(result, "retcode", 0) == getattr(get_mt5(), "TRADE_RETCODE_DONE", 10009):
            exec_price = price if price > 0 else req.get("price", 0.0)
            await update.message.reply_text(
                f"✅ **PENDING ORDER BERHASIL DIBUAT!**\n"
                f"=================================\n"
                f"• Ticket: `#{result.order}`\n"
                f"• Symbol: **{symbol}**\n"
                f"• Tipe Order: **{type_name}**\n"
                f"• Target Price: `{exec_price}`\n"
                f"• Volume: **{lot:.2f} Lot**\n"
                f"• Stop Loss: `{sl if sl else '-'}` | Take Profit: `{tp if tp else '-'}`",
                parse_mode="Markdown"
            )
        else:
            ret_code = getattr(result, "retcode", "N/A")
            comment = getattr(result, "comment", "N/A")
            await update.message.reply_text(f"⚠️ **Eksekusi Pending Order Gagal** (retcode={ret_code}): {comment}", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal: {e}\nFormat: `/buylimit SYMBOL LOT PRICE [SL] [TP]`", parse_mode="Markdown")


async def cmd_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /positions untuk menampilkan semua posisi terbuka aktif dengan penomoran list 1, 2, 3..."""
    if not await guard(update):
        return

    chat_id = update.effective_chat.id

    def _get_pos():
        client = get_mt5()
        pos_tuple = client.positions_get()
        ticks = {}
        if pos_tuple:
            for p in pos_tuple:
                if p.symbol not in ticks:
                    tick_data = get_symbol_tick(client, p.symbol)
                    ticks[p.symbol] = tick_data
        return pos_tuple, ticks

    try:
        positions, ticks = await asyncio.to_thread(_get_pos)
        if not positions or len(positions) == 0:
            USER_POSITION_INDEX[chat_id] = []
            await update.message.reply_text(
                "💼 **POSISI TRADING TERBUKA**\n"
                "---------------------------------\n"
                "ℹ️ Tidak ada posisi trading yang sedang terbuka.",
                parse_mode="Markdown"
            )
            return

        # Simpan daftar tiket berdasarkan index 1, 2, 3...
        USER_POSITION_INDEX[chat_id] = [p.ticket for p in positions]

        lines = [
            f"💼 **POSISI TRADING TERBUKA ({len(positions)})**\n"
        ]

        total_profit = 0.0
        for idx, p in enumerate(positions, 1):
            p_type_str = "BUY" if p.type == 0 else "SELL"
            p_emoji = "🟢" if p.type == 0 else "🔴"
            tick = ticks.get(p.symbol)
            curr_price = tick["bid"] if p.type == 0 else tick["ask"] if tick else getattr(p, "price_current", p.price_open)
            profit = getattr(p, "profit", 0.0)
            total_profit += profit

            profit_str = f"+${profit:.2f} USD 📈" if profit >= 0 else f"-${abs(profit):.2f} USD 📉"
            sl_str = f"{p.sl}" if p.sl else "-"
            tp_str = f"{p.tp}" if p.tp else "-"

            lines.append(
                f"{idx}. {p_emoji} **{p.symbol} ({p_type_str})** — **{p.volume:.2f} Lot**\n"
                f"   • Open: {p.price_open} ➔ Running: {curr_price}\n"
                f"   • SL: {sl_str} | TP: {tp_str}\n"
                f"   • Profit: **{profit_str}**\n"
                f"   • Ticket: #{p.ticket}\n"
            )

        tot_profit_str = f"+${total_profit:.2f} USD 📈" if total_profit >= 0 else f"-${abs(total_profit):.2f} USD 📉"
        lines.append(
            "---------------------------------\n"
            f"💰 Total Floating PnL: **{tot_profit_str}**\n\n"
            f"💡 *Ketik `/close 1` untuk menutup posisi no.1 atau `/close all` untuk tutup semua.*"
        )

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    except Exception as e:
        log.exception("Gagal mengambil posisi terbuka:")
        await update.message.reply_text(f"❌ Error saat mengambil posisi: {e}")


async def cmd_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /orders untuk menampilkan semua pending order aktif dengan penomoran list 1, 2, 3..."""
    if not await guard(update):
        return

    chat_id = update.effective_chat.id

    def _get_orders():
        client = get_mt5()
        orders_tuple = client.orders_get()
        ticks = {}
        if orders_tuple:
            for o in orders_tuple:
                if o.symbol not in ticks:
                    tick_data = get_symbol_tick(client, o.symbol)
                    ticks[o.symbol] = tick_data
        return orders_tuple, ticks

    try:
        orders, ticks = await asyncio.to_thread(_get_orders)
        if not orders or len(orders) == 0:
            USER_ORDER_INDEX[chat_id] = []
            await update.message.reply_text(
                "📑 **DAFTAR PENDING ORDER**\n"
                "---------------------------------\n"
                "ℹ️ Tidak ada pending order yang aktif saat ini.",
                parse_mode="Markdown"
            )
            return

        # Simpan daftar tiket berdasarkan index 1, 2, 3...
        USER_ORDER_INDEX[chat_id] = [o.ticket for o in orders]

        lines = [
            f"📑 **DAFTAR PENDING ORDER ({len(orders)})**\n"
        ]

        for idx, o in enumerate(orders, 1):
            type_str = get_order_type_str(o.type)
            tick = ticks.get(o.symbol)
            curr_ref = tick["ask"] if "BUY" in type_str.upper() else tick["bid"] if tick else getattr(o, "price_current", o.price_open)
            sl_str = f"{o.sl}" if o.sl else "-"
            tp_str = f"{o.tp}" if o.tp else "-"
            exp_str = datetime.fromtimestamp(o.time_expiration).strftime('%d %b %Y, %H:%M WIB') if o.time_expiration else "GTC"

            lines.append(
                f"{idx}. ⏳ **{o.symbol} ({type_str})** — **{o.volume_initial:.2f} Lot**\n"
                f"   • Target Price: {o.price_open} (Pasar: {curr_ref})\n"
                f"   • SL: {sl_str} | TP: {tp_str}\n"
                f"   • Expired: {exp_str}\n"
                f"   • Ticket: #{o.ticket}\n"
            )

        lines.append(
            "---------------------------------\n"
            f"💡 *Ketik `/cancel 1` untuk membatalkan order no.1 atau `/cancel all` untuk batal semua.*"
        )

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    except Exception as e:
        log.exception("Gagal mengambil pending order:")
        await update.message.reply_text(f"❌ Error saat mengambil pending order: {e}")


async def cmd_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /close <nomor_list|ticket|all> untuk menutup posisi trading."""
    if not await guard(update):
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ **Format Perintah /close**\n"
            "• `/close 1` — Tutup posisi nomor 1 dari list\n"
            "• `/close all` — Tutup SEMUA posisi terbuka\n"
            "• `/close 351723560` — Tutup berdasarkan nomor tiket",
            parse_mode="Markdown"
        )
        return

    arg = context.args[0].lower()
    chat_id = update.effective_chat.id

    if arg == "all":
        def _do_close_all():
            client = get_mt5()
            positions = client.positions_get()
            if not positions:
                return 0, []
            closed_count = 0
            errs = []
            for p in positions:
                close_type = client.ORDER_TYPE_SELL if p.type == 0 else client.ORDER_TYPE_BUY
                tick = get_symbol_tick(client, p.symbol)
                price = tick["bid"] if close_type == client.ORDER_TYPE_SELL else tick["ask"]
                req = {
                    "action": client.TRADE_ACTION_DEAL,
                    "position": p.ticket,
                    "symbol": p.symbol,
                    "volume": p.volume,
                    "type": close_type,
                    "price": price,
                    "deviation": 20,
                    "magic": 990001,
                    "comment": "telegram-executor-close-all",
                }
                res = safe_order_send(client, req)
                if res and getattr(res, "retcode", 0) == getattr(client, "TRADE_RETCODE_DONE", 10009):
                    closed_count += 1
                else:
                    errs.append(f"#{p.ticket}: retcode={getattr(res, 'retcode', 'N/A')}")
            return closed_count, errs

        status_msg = await update.message.reply_text("⏳ Menutup semua posisi terbuka...")
        count, errs = await asyncio.to_thread(_do_close_all)
        if count > 0:
            err_text = f"\n⚠️ Gagal tutup: {', '.join(errs)}" if errs else ""
            await status_msg.edit_text(f"✅ **Berhasil Menutup {count} Posisi Terbuka!**{err_text}", parse_mode="Markdown")
        else:
            await status_msg.edit_text("ℹ️ Tidak ada posisi terbuka yang dapat ditutup.")
        return

    # Tentukan Ticket berdasarkan list index 1, 2, 3... atau langsung Ticket ID
    target_ticket = None
    try:
        val = int(arg)
        cached_tickets = USER_POSITION_INDEX.get(chat_id, [])
        if 1 <= val <= len(cached_tickets):
            target_ticket = cached_tickets[val - 1]
        else:
            target_ticket = val
    except ValueError:
        await update.message.reply_text("❌ Input harus berupa nomor urut (1, 2...), ticket ID, atau 'all'!")
        return

    def _do_close_single(ticket):
        client = get_mt5()
        pos = client.positions_get(ticket=ticket)
        if not pos:
            all_pos = client.positions_get()
            pos = [p for p in all_pos if p.ticket == ticket] if all_pos else None

        if not pos:
            return None, f"⚠️ Posisi dengan Ticket #{ticket} tidak ditemukan / sudah ditutup."

        p = pos[0]
        close_type = client.ORDER_TYPE_SELL if p.type == 0 else client.ORDER_TYPE_BUY
        tick = get_symbol_tick(client, p.symbol)
        price = tick["bid"] if close_type == client.ORDER_TYPE_SELL else tick["ask"]
        req = {
            "action": client.TRADE_ACTION_DEAL,
            "position": p.ticket,
            "symbol": p.symbol,
            "volume": p.volume,
            "type": close_type,
            "price": price,
            "deviation": 20,
            "magic": 990001,
            "comment": "telegram-executor-close",
        }
        res = safe_order_send(client, req)
        return res, p

    res, pos_obj = await asyncio.to_thread(_do_close_single, target_ticket)
    if isinstance(pos_obj, str):
        await update.message.reply_text(pos_obj)
        return

    if res and getattr(res, "retcode", 0) == 10009:
        await update.message.reply_text(
            f"✅ **Posisi Berhasil Ditutup!**\n"
            f"• Simbol: **{pos_obj.symbol}**\n"
            f"• Ticket: `#{pos_obj.ticket}`\n"
            f"• Volume: **{pos_obj.volume:.2f} Lot**",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"⚠️ Gagal menutup posisi #{target_ticket} (retcode={getattr(res, 'retcode', 'N/A')})")


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /cancel <nomor_list|ticket|all> untuk membatalkan pending order."""
    if not await guard(update):
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ **Format Perintah /cancel**\n"
            "• `/cancel 1` — Batal order nomor 1 dari list\n"
            "• `/cancel all` — Batal SEMUA pending order\n"
            "• `/cancel 351728404` — Batal berdasarkan nomor tiket",
            parse_mode="Markdown"
        )
        return

    arg = context.args[0].lower()
    chat_id = update.effective_chat.id

    if arg == "all":
        def _do_cancel_all():
            client = get_mt5()
            orders = client.orders_get()
            if not orders:
                return 0, []
            canceled_count = 0
            errs = []
            for o in orders:
                req = {"action": client.TRADE_ACTION_REMOVE, "order": o.ticket}
                res = safe_order_send(client, req)
                if res and getattr(res, "retcode", 0) == getattr(client, "TRADE_RETCODE_DONE", 10009):
                    canceled_count += 1
                else:
                    errs.append(f"#{o.ticket}: retcode={getattr(res, 'retcode', 'N/A')}")
            return canceled_count, errs

        status_msg = await update.message.reply_text("⏳ Membatalkan semua pending order...")
        count, errs = await asyncio.to_thread(_do_cancel_all)
        if count > 0:
            err_text = f"\n⚠️ Gagal batalkan: {', '.join(errs)}" if errs else ""
            await status_msg.edit_text(f"✅ **Berhasil Membatalkan {count} Pending Order!**{err_text}", parse_mode="Markdown")
        else:
            await status_msg.edit_text("ℹ️ Tidak ada pending order yang aktif.")
        return

    # Tentukan Ticket berdasarkan list index 1, 2, 3... atau langsung Ticket ID
    target_ticket = None
    try:
        val = int(arg)
        cached_orders = USER_ORDER_INDEX.get(chat_id, [])
        if 1 <= val <= len(cached_orders):
            target_ticket = cached_orders[val - 1]
        else:
            target_ticket = val
    except ValueError:
        await update.message.reply_text("❌ Input harus berupa nomor urut (1, 2...), ticket ID, atau 'all'!")
        return

    def _do_cancel_single(ticket):
        client = get_mt5()
        req = {"action": client.TRADE_ACTION_REMOVE, "order": ticket}
        res = safe_order_send(client, req)
        return res

    res = await asyncio.to_thread(_do_cancel_single, target_ticket)
    if res and getattr(res, "retcode", 0) == 10009:
        await update.message.reply_text(f"✅ **Pending Order #{target_ticket} Berhasil Dibatalkan!**", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"⚠️ Gagal membatalkan pending order #{target_ticket} (retcode={getattr(res, 'retcode', 'N/A')})")




# ==================== HANDLER HANDSHAKE & SCREENSHOT ====================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler saat pengguna mengirimkan foto / screenshot sinyal."""
    if not await guard(update):
        return

    status_msg = await update.message.reply_text("🔍 Menganalisis screenshot sinyal dengan Gemini AI...")

    try:
        # Ambil foto kualitas tertinggi
        photo_file = await update.message.photo[-1].get_file()
        image_bytes = await photo_file.download_as_bytearray()

        result = await asyncio.to_thread(parse_image_with_gemini, bytes(image_bytes), GEMINI_API_KEY)

        if not result.get("is_valid_signal"):
            err_msg = result.get("error_message") or "Gambar tidak terdeteksi sebagai sinyal trading yang valid."
            await status_msg.edit_text(f"⚠️ {err_msg}")
            return

        action = str(result.get("action", "")).upper()
        symbol = str(result.get("symbol", "")).upper()
        lot = float(result.get("lot") or DEFAULT_LOT)
        entry_price = float(result.get("entry_price") or 0.0)
        sl = float(result.get("sl") or 0.0)
        tp = float(result.get("tp") or 0.0)
        expiration = result.get("expiration")

        summary_text = (
            f"🎯 **Sinyal Terdeteksi Dari Screenshot:**\n"
            f"• Action: **{action}**\n"
            f"• Symbol: **{symbol}**\n"
            f"• Lot: **{lot}**\n"
            f"• Entry: **{entry_price if entry_price else 'Market Price'}**\n"
            f"• SL: **{sl if sl else '-'}**\n"
            f"• TP: **{tp if tp else '-'}**\n"
            f"• Expired: **{expiration if expiration else 'GTC (Tanpa Expired)'}**\n"
        )

        order_data = {
            "action": action,
            "symbol": symbol,
            "lot": lot,
            "entry_price": entry_price,
            "sl": sl,
            "tp": tp,
            "expiration": expiration
        }

        # Jika AUTO_EXECUTE_IMAGE true, langsung eksekusi tanpa konfirmasi
        if AUTO_EXECUTE_IMAGE:
            await status_msg.edit_text(f"{summary_text}\n⚡ **Eksekusi Otomatis Berjalan...**", parse_mode="Markdown")
            exec_res = await asyncio.to_thread(execute_parsed_order, order_data)
            await update.message.reply_text(exec_res)
            return

        # Simpan order data ke dictionary pending untuk konfirmasi via tombol
        order_id = str(uuid.uuid4())[:8]
        PENDING_IMAGE_ORDERS[order_id] = order_data

        keyboard = [
            [
                InlineKeyboardButton("✅ Eksekusi Order", callback_data=f"exec_{order_id}"),
                InlineKeyboardButton("❌ Batal", callback_data=f"cancel_{order_id}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await status_msg.edit_text(
            f"{summary_text}\nTekan tombol di bawah untuk konfirmasi eksekusi:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

    except Exception as e:
        log.exception("Gagal memproses gambar sinyal:")
        await status_msg.edit_text(f"❌ Gagal memproses gambar sinyal: {e}")


def determine_smart_order_request(client, action_str: str, symbol: str, lot: float, entry_price: float, sl: float, tp: float, expiration=None):
    """
    Menentukan tipe order MT5 secara otomatis berdasarkan aturan perbandingan harga entry dengan harga pasar saat ini:
    1. Market Execution (BUY / SELL): jika entry_price <= 0 atau selisih harga entry dengan harga pasar < 0.05%.
    2. BUY:
       - entry_price < current_ask  -> Buy Limit  (ORDER_TYPE_BUY_LIMIT)
       - entry_price > current_ask  -> Buy Stop   (ORDER_TYPE_BUY_STOP)
    3. SELL:
       - entry_price > current_bid  -> Sell Limit (ORDER_TYPE_SELL_LIMIT)
       - entry_price < current_bid  -> Sell Stop  (ORDER_TYPE_SELL_STOP)
    """
    resolved_symbol = resolve_symbol(symbol)
    tick_dict = get_symbol_tick(client, resolved_symbol)
    action_upper = str(action_str).upper()
    is_buy = "BUY" in action_upper

    if not tick_dict or not entry_price or entry_price <= 0:
        order_type = client.ORDER_TYPE_BUY if is_buy else client.ORDER_TYPE_SELL
        return build_market_request(symbol, lot, order_type, sl, tp), "Market Execution"

    ask = tick_dict["ask"]
    bid = tick_dict["bid"]
    curr_ref = ask if is_buy else bid

    # Jika harga entry sangat dekat dengan harga pasar saat ini (< 0.05% selisih), gunakan Market Execution
    if abs(entry_price - curr_ref) / curr_ref < 0.0005:
        order_type = client.ORDER_TYPE_BUY if is_buy else client.ORDER_TYPE_SELL
        return build_market_request(symbol, lot, order_type, sl, tp), "Market Execution"

    if is_buy:
        if entry_price < ask:
            order_type = client.ORDER_TYPE_BUY_LIMIT
            type_name = "Buy Limit"
        else:
            order_type = client.ORDER_TYPE_BUY_STOP
            type_name = "Buy Stop"
    else:
        if entry_price > bid:
            order_type = client.ORDER_TYPE_SELL_LIMIT
            type_name = "Sell Limit"
        else:
            order_type = client.ORDER_TYPE_SELL_STOP
            type_name = "Sell Stop"

    log.info(f"Smart Order Logic: Action={action_upper}, Entry={entry_price}, RefMarketPrice={curr_ref} -> Executing as {type_name}")
    req = build_pending_request(symbol, lot, order_type, entry_price, sl, tp, expiration=expiration)
    return req, type_name


def execute_parsed_order(order_data: dict) -> str:
    """Eksekusi order yang telah diparsing dari gambar ke MT5 dengan aturan penentuan tipe order & expired time otomatis."""
    try:
        client = get_mt5()
        action = order_data["action"]
        symbol = order_data["symbol"]
        lot = order_data["lot"]
        entry = order_data["entry_price"]
        sl = order_data["sl"]
        tp = order_data["tp"]
        expiration = order_data.get("expiration")

        req, type_name = determine_smart_order_request(client, action, symbol, lot, entry, sl, tp, expiration=expiration)

        result = safe_order_send(client, req)
        if result is not None and getattr(result, "retcode", 0) == getattr(client, "TRADE_RETCODE_DONE", 10009):
            exec_price = result.price if (result is not None and getattr(result, "price", 0.0) > 0.0) else req.get("price", entry)
            exp_info = f"\nExpired At: {expiration}" if expiration and "Execution" not in type_name else ""
            return f"✅ Order ({type_name}) Berhasil Dieksekusi!\nTicket: #{result.order}\nHarga: {exec_price}{exp_info}"

        else:
            ret_code = getattr(result, "retcode", "N/A")
            comment = getattr(result, "comment", "N/A")
            return f"⚠️ Eksekusi Order ({type_name}) Gagal (retcode={ret_code}): {comment}"

    except Exception as e:
        log.exception("Gagal eksekusi order dari gambar:")
        return f"❌ Error eksekusi: {e}"




async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler tombol konfirmasi (InlineKeyboardButton)."""
    query = update.callback_query
    await query.answer()

    if not is_owner(update):
        await query.answer("Bukan pemilik bot ini.", show_alert=True)
        return

    data = query.data
    if data.startswith("exec_"):
        order_id = data.split("_")[1]
        order_data = PENDING_IMAGE_ORDERS.pop(order_id, None)
        if not order_data:
            await query.edit_message_text("⚠️ Order ini sudah kadaluarsa atau telah dieksekusi.")
            return

        await query.edit_message_text(f"⏳ Mengeksekusi order {order_data['action']} {order_data['symbol']}...")
        exec_result = await asyncio.to_thread(execute_parsed_order, order_data)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=exec_result)

    elif data.startswith("cancel_"):
        order_id = data.split("_")[1]
        PENDING_IMAGE_ORDERS.pop(order_id, None)
        await query.edit_message_text("❌ Eksekusi order dibatalkan.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /status ringkas & rapi untuk layar mobile."""
    reload_config()
    if not is_owner(update):
        await update.message.reply_text("Bukan pemilik bot ini. Akses ditolak.")
        return

    def _sync_check_status():
        client = get_mt5()
        t_info = client.terminal_info()
        a_info = client.account_info()
        all_syms = get_all_broker_symbols(client)
        return t_info, a_info, all_syms

    try:
        t_info, a_info, all_syms = await asyncio.wait_for(
            asyncio.to_thread(_sync_check_status), timeout=20
        )

        lines = ["📊 **STATUS SYSTEM MT5**\n"]

        if t_info and getattr(t_info, 'connected', False):
            trade_state = "AKTIF" if getattr(t_info, 'trade_allowed', False) else "NONAKTIF"
            lines.append(f"🟢 **MT5 Terminal**: Active (Algo Trading: {trade_state})")
        else:
            lines.append("⚠️ **MT5 Terminal**: Tidak Terhubung / Belum Initialize")

        if a_info:
            lines.append(
                f"🔑 **Broker**: `#{a_info.login}` ({a_info.server})\n"
                f"💰 **Balance**: `${getattr(a_info, 'balance', 0.0):.2f}` | Equity: `${getattr(a_info, 'equity', 0.0):.2f}`"
            )
        else:
            lines.append(f"❌ **Broker**: Belum Login (`#{MT5_LOGIN}` @ `{MT5_SERVER}`)")

        sym_count = len(all_syms) if all_syms else 0
        gold_syms = [s for s in all_syms if 'GOLD' in s.upper() or 'XAU' in s.upper()] if all_syms else []
        gold_str = f" ({', '.join(gold_syms)})" if gold_syms else ""
        lines.append(f"📈 **Market Watch**: {sym_count} Simbol Loaded{gold_str}")

    except Exception as e:
        lines = [f"❌ **Error Diagnostik**: {e}"]

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


def update_env_file(key: str, value: str, env_path: str = ".env"):
    """Update or add a key=value pair in the .env file while preserving existing lines."""
    value_str = str(value)
    if not os.path.exists(env_path):
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(f"{key}={value_str}\n")
        return

    lines = []
    found = False
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip().startswith(f"{key}=") or line.strip().startswith(f"{key} ="):
                lines.append(f"{key}={value_str}\n")
                found = True
            else:
                lines.append(line)

    if not found:
        lines.append(f"{key}={value_str}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /config ringkas & rapi untuk layar mobile."""
    if not is_owner(update):
        await update.message.reply_text("Bukan pemilik bot ini. Akses ditolak.")
        return

    auto_str = "ON ⚡ (Langsung Eksekusi)" if AUTO_EXECUTE_IMAGE else "OFF 🛡️ (Butuh Konfirmasi)"

    msg = (
        f"⚙️ **KONFIGURASI BOT MT5**\n\n"
        f"• **Server**: `{MT5_SERVER}`\n"
        f"• **Login**: `#{MT5_LOGIN}`\n"
        f"• **Default Lot**: `{DEFAULT_LOT}`\n"
        f"• **Auto Gambar**: `{auto_str}`\n\n"
        f"🛠️ **PERINTAH UBAH SETTING:**\n"
        f"• `/setaccount <login> <pass> <server>`\n"
        f"• `/setserver <server_name>`\n"
        f"• `/setlogin <login> <password>`\n"
        f"• `/setlot <lot_size>`\n"
        f"• `/setautoimage <on|off>`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_setautoimage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /setautoimage <on|off|true|false> untuk merubah mode eksekusi otomatis foto sinyal."""
    global AUTO_EXECUTE_IMAGE
    if not is_owner(update):
        await update.message.reply_text("Bukan pemilik bot ini. Akses ditolak.")
        return

    if not context.args:
        curr_status = "ON ⚡ (Langsung Eksekusi)" if AUTO_EXECUTE_IMAGE else "OFF 🛡️ (Butuh Tombol Konfirmasi)"
        await update.message.reply_text(
            f"ℹ️ Status Auto Gambar saat ini: **{curr_status}**\n\n"
            "⚠️ **Cara Mengubah:**\n"
            "• `/setautoimage on` — Foto sinyal langsung dieksekusi tanpa konfirmasi\n"
            "• `/setautoimage off` — Foto sinyal menampilkan tombol konfirmasi dulu",
            parse_mode="Markdown"
        )
        return

    val = context.args[0].lower()
    if val in ("true", "on", "1", "ya", "yes"):
        new_val = True
    elif val in ("false", "off", "0", "tidak", "no"):
        new_val = False
    else:
        await update.message.reply_text("❌ Nilai harus berupa `on`/`off` atau `true`/`false`!", parse_mode="Markdown")
        return

    AUTO_EXECUTE_IMAGE = new_val
    update_env_file("AUTO_EXECUTE_IMAGE", str(new_val).lower())

    status_str = "ON ⚡ (Langsung Eksekusi Otomatis)" if AUTO_EXECUTE_IMAGE else "OFF 🛡️ (Menggunakan Tombol Konfirmasi)"
    await update.message.reply_text(
        f"✅ **Pengaturan Auto Gambar Berhasil Diubah!**\n"
        f"• Mode Auto Gambar: **{status_str}**\n\n"
        f"Pengaturan baru telah disimpan secara permanen ke `.env`.",
        parse_mode="Markdown"
    )



async def cmd_setlot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /setlot <lot_size> untuk mengubah default lot order."""
    if not is_owner(update):
        await update.message.reply_text("Bukan pemilik bot ini.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Format salah!\nGunakan: `/setlot <lot_size>`\nContoh: `/setlot 0.05`", parse_mode="Markdown")
        return

    try:
        new_lot = float(context.args[0])
        if new_lot <= 0:
            raise ValueError("Lot harus lebih besar dari 0")

        global DEFAULT_LOT
        DEFAULT_LOT = new_lot
        update_env_file("DEFAULT_LOT", str(new_lot))

        await update.message.reply_text(f"✅ **Default Lot Berhasil Diubah!**\nDefault Lot Baru: **{DEFAULT_LOT}**", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal mengubah lot: {e}")


async def cmd_setaccount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /setaccount <login> <password> <server> untuk re-login MT5."""
    if not is_owner(update):
        await update.message.reply_text("Bukan pemilik bot ini.")
        return

    if len(context.args) < 3:
        await update.message.reply_text(
            "⚠️ Format salah!\nGunakan: `/setaccount <login> <password> <server>`\n"
            "Contoh: `/setaccount 61425413 mypass FinexBisnisSolusi-Demo`",
            parse_mode="Markdown"
        )
        return

    login_str = context.args[0]
    password_str = context.args[1]
    server_str = " ".join(context.args[2:])

    try:
        login_acc = int(login_str)
    except ValueError:
        await update.message.reply_text("❌ Nomor login harus berupa angka!")
        return

    global MT5_LOGIN, MT5_PASSWORD, MT5_SERVER
    MT5_LOGIN = login_acc
    MT5_PASSWORD = password_str
    MT5_SERVER = server_str

    update_env_file("MT5_LOGIN", str(MT5_LOGIN))
    update_env_file("MT5_PASSWORD", MT5_PASSWORD)
    update_env_file("MT5_SERVER", MT5_SERVER)

    status_msg = await update.message.reply_text(f"⏳ Menghubungkan ke broker Finex ({MT5_SERVER}) dengan Login #{MT5_LOGIN}...")

    def _sync_relogin():
        client = get_mt5()
        if not client.terminal_info():
            mt5_path = r"C:\Program Files\MetaTrader 5\terminal64.exe"
            try:
                client.initialize(path=mt5_path)
            except Exception:
                try:
                    client.initialize()
                except Exception:
                    pass

        login_ok = client.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
        a_info = client.account_info()
        last_err = client.last_error()
        if login_ok and a_info:
            all_syms = get_all_broker_symbols(client)
            if all_syms:
                for s in all_syms:
                    client.symbol_select(s, True)
        return login_ok, a_info, last_err

    try:
        login_ok, a_info, last_err = await asyncio.to_thread(_sync_relogin)
        if login_ok and a_info:
            await status_msg.edit_text(
                f"✅ **Koneksi Broker & Re-Login BERHASIL!**\n\n"
                f"• Akun Login: `#{a_info.login}`\n"
                f"• Nama Akun: `{getattr(a_info, 'name', 'N/A')}`\n"
                f"• Server: `{a_info.server}`\n"
                f"• Balance: `{getattr(a_info, 'balance', 0.0)} {getattr(a_info, 'currency', 'USD')}`\n\n"
                f"Pengaturan telah disimpan secara permanen ke file `.env`.",
                parse_mode="Markdown"
            )
        else:
            err_code, err_msg = last_err if isinstance(last_err, (tuple, list)) and len(last_err) >= 2 else ("N/A", str(last_err))
            await status_msg.edit_text(
                f"⚠️ **Login MT5 Gagal** (Error Code: `{err_code}` — `{err_msg}`)\n\n"
                f"• Target Login: `#{MT5_LOGIN}`\n"
                f"• Target Server: `{MT5_SERVER}`\n\n"
                f"💡 **Penyebab umum:**\n"
                f"1. Server `{MT5_SERVER}` salah (misal: akun Demo dimasukkan ke server Real).\n"
                f"2. Password MT5 salah (bukan password login website).\n"
                f"3. Jika baru ubah `.env`, jalankan `docker compose restart` di VPS.",
                parse_mode="Markdown"
            )
    except Exception as e:
        await status_msg.edit_text(f"❌ Error saat re-login MT5: {e}")


async def cmd_setserver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /setserver <server_name> untuk mengganti nama server Finex."""
    if not is_owner(update):
        await update.message.reply_text("Bukan pemilik bot ini.")
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ Format salah!\nGunakan: `/setserver <server_name>`\n"
            "Contoh: `/setserver FinexBisnisSolusi-Real` atau `/setserver FinexBisnisSolusi-Demo`",
            parse_mode="Markdown"
        )
        return

    new_server = " ".join(context.args)
    global MT5_SERVER
    MT5_SERVER = new_server
    update_env_file("MT5_SERVER", MT5_SERVER)

    status_msg = await update.message.reply_text(f"⏳ Mengganti server MT5 ke '{MT5_SERVER}' & merefresh koneksi...")

    def _sync_relogin_server():
        client = get_mt5()
        if not client.terminal_info():
            mt5_path = r"C:\Program Files\MetaTrader 5\terminal64.exe"
            try:
                client.initialize(path=mt5_path)
            except Exception:
                try:
                    client.initialize()
                except Exception:
                    pass
        login_ok = client.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
        a_info = client.account_info()
        last_err = client.last_error()
        return login_ok, a_info, last_err

    try:
        login_ok, a_info, last_err = await asyncio.to_thread(_sync_relogin_server)
        if login_ok and a_info:
            await status_msg.edit_text(
                f"✅ **Server MT5 Berhasil Diubah ke '{MT5_SERVER}'!**\n"
                f"Status Akun: Login #{a_info.login} ({a_info.server})\n"
                f"Pengaturan disimpan ke file `.env`.",
                parse_mode="Markdown"
            )
        else:
            err_code, err_msg = last_err if isinstance(last_err, (tuple, list)) and len(last_err) >= 2 else ("N/A", str(last_err))
            await status_msg.edit_text(
                f"⚠️ Server diubah ke '{MT5_SERVER}', tetapi MT5 gagal login (Error: `{err_code}` — `{err_msg}`).\n"
                f"Silakan cek kredensial & pastikan server benar!",
                parse_mode="Markdown"
            )
    except Exception as e:
        await status_msg.edit_text(f"❌ Error saat mengganti server: {e}")


async def cmd_setlogin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /setlogin <login> <password> untuk mengganti login & password MT5."""
    if not is_owner(update):
        await update.message.reply_text("Bukan pemilik bot ini.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ Format salah!\nGunakan: `/setlogin <login> <password>`\n"
            "Contoh: `/setlogin 61425413 mypassword`",
            parse_mode="Markdown"
        )
        return

    try:
        new_login = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Nomor login harus berupa angka!")
        return

    new_pass = context.args[1]

    global MT5_LOGIN, MT5_PASSWORD
    MT5_LOGIN = new_login
    MT5_PASSWORD = new_pass

    update_env_file("MT5_LOGIN", str(MT5_LOGIN))
    update_env_file("MT5_PASSWORD", MT5_PASSWORD)

    status_msg = await update.message.reply_text(f"⏳ Mencoba login ke MT5 dengan Login #{MT5_LOGIN}...")

    def _sync_relogin_acc():
        client = get_mt5()
        if not client.terminal_info():
            mt5_path = r"C:\Program Files\MetaTrader 5\terminal64.exe"
            try:
                client.initialize(path=mt5_path)
            except Exception:
                try:
                    client.initialize()
                except Exception:
                    pass
        login_ok = client.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
        a_info = client.account_info()
        last_err = client.last_error()
        return login_ok, a_info, last_err

    try:
        login_ok, a_info, last_err = await asyncio.to_thread(_sync_relogin_acc)
        if login_ok and a_info:
            await status_msg.edit_text(
                f"✅ **Login & Password MT5 Berhasil Diubah!**\n"
                f"Akun Login: #{a_info.login} ({a_info.name})\n"
                f"Server: {a_info.server}\n"
                f"Pengaturan disimpan ke file `.env`.",
                parse_mode="Markdown"
            )
        else:
            err_code, err_msg = last_err if isinstance(last_err, (tuple, list)) and len(last_err) >= 2 else ("N/A", str(last_err))
            await status_msg.edit_text(
                f"⚠️ Gagal login ke MT5 dengan Login #{MT5_LOGIN} (Error: `{err_code}` — `{err_msg}`).\n"
                f"Silakan cek password & server!",
                parse_mode="Markdown"
            )
    except Exception as e:
        await status_msg.edit_text(f"❌ Error saat login: {e}")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /start. Bebas dipanggil tanpa bergantung pada koneksi MT5."""
    if not is_owner(update):
        await update.message.reply_text("Bukan pemilik bot ini. Akses ditolak.")
        return

    await update.message.reply_text(
        f"🤖 **Bot TF Executor Aktif & Siap!**\n\n"
        f"• **Akun Finex**: `#{MT5_LOGIN}` ({MT5_SERVER})\n"
        f"• **Default Lot**: `{DEFAULT_LOT}`\n\n"
        f"💡 Ketik `/help` untuk Panduan Penggunaan Lengkap & Perintah Bot!",
        parse_mode="Markdown"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /help ringkas & rapi untuk layar mobile."""
    if not is_owner(update):
        await update.message.reply_text("Bukan pemilik bot ini. Akses ditolak.")
        return

    msg = (
        f"📖 **PANDUAN BOT EXECUTOR**\n\n"
        f"📸 **SINYAL SCREENSHOT**\n"
        f"Kirim foto sinyal ➔ Bot membaca & mengeksekusi otomatis.\n\n"
        f"📊 **INFORMASI & CONFIG**\n"
        f"• `/status` — Cek koneksi & saldo\n"
        f"• `/config` — Cek & ubah setting\n"
        f"• `/setaccount <login> <pass> <server>`\n"
        f"• `/setlot <lot>` — Set default lot\n"
        f"• `/setautoimage <on|off>` — Set mode auto foto sinyal\n\n"
        f"📈 **TRADING MANUAL**\n"
        f"• `/buy XAUUSD 0.10 SL2640 TP2670`\n"
        f"• `/sell XAUUSD 0.10 SL2670 TP2640`\n"
        f"• `/buylimit XAUUSD 0.10 2620 SL2600 TP2650`\n"
        f"• `/selllimit XAUUSD 0.10 2680 SL2700 TP2650`\n"
        f"• `/order XAUUSD 0.10 2620` (Smart Order)\n\n"
        f"💼 **POSISI & ORDER**\n"
        f"• `/positions` — Lihat posisi terbuka\n"
        f"• `/orders` — Lihat pending order\n"
        f"• `/close 1` — Tutup posisi #1 (atau `/close all`)\n"
        f"• `/cancel 1` — Batal order #1 (atau `/cancel all`)"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")



def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))

    app.add_handler(CommandHandler("config", cmd_config))
    app.add_handler(CommandHandler("settings", cmd_config))
    app.add_handler(CommandHandler("setaccount", cmd_setaccount))
    app.add_handler(CommandHandler("setserver", cmd_setserver))
    app.add_handler(CommandHandler("setlogin", cmd_setlogin))
    app.add_handler(CommandHandler("setlot", cmd_setlot))
    app.add_handler(CommandHandler("setautoimage", cmd_setautoimage))
    app.add_handler(CommandHandler("setautogambar", cmd_setautoimage))
    app.add_handler(CommandHandler("buy", cmd_buy))
    app.add_handler(CommandHandler("sell", cmd_sell))
    app.add_handler(CommandHandler("buylimit", cmd_buylimit))
    app.add_handler(CommandHandler("selllimit", cmd_selllimit))
    app.add_handler(CommandHandler("positions", cmd_positions))
    app.add_handler(CommandHandler("orders", cmd_orders))
    app.add_handler(CommandHandler("close", cmd_close))
    app.add_handler(CommandHandler("cancel", cmd_cancel))

    # Handler Foto Sinyal & Tombol Konfirmasi
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_callback))

    log.info(f"Bot Telegram siap & mendengarkan pesan... (platform: {log_platform})")
    app.run_polling(drop_pending_updates=True)



if __name__ == "__main__":
    main()

