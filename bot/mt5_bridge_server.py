import sys
import os
import time
import logging
import threading

# Force unbuffered output in Wine Python stdout/stderr
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("mt5_bridge")


try:
    import MetaTrader5 as mt5
except ImportError:
    log.error("MetaTrader5 package not installed in Wine Python!")
    sys.exit(1)

try:
    from rpyc.utils.server import ThreadedServer
    from rpyc.core import SlaveService
except ImportError:
    log.error("rpyc package not installed in Wine Python!")
    sys.exit(1)

log.info("Starting MT5 Bridge Server in Wine...")

login_str = os.environ.get("MT5_LOGIN", "0")
password = os.environ.get("MT5_PASSWORD", "")
server_name = os.environ.get("MT5_SERVER", "")
login_acc = int(login_str) if login_str.isdigit() else 0


def connect_mt5_in_background():
    time.sleep(1)
    # Search for actual terminal64.exe location inside Wine drive_c
    mt5_path = r"C:\MetaTrader5\terminal64.exe"
    wine_drive_c = os.environ.get("WINEPREFIX", "/root/.wine") + "/drive_c"
    for candidate in [r"C:\MetaTrader5\terminal64.exe", r"C:\Program Files\MetaTrader 5\terminal64.exe"]:
        rel_path = candidate[3:].replace("\\", "/")
        if os.path.exists(os.path.join(wine_drive_c, rel_path)):
            mt5_path = candidate
            break

    log.info(f"Connecting to MT5 terminal (path='{mt5_path}', login={login_acc}, server='{server_name}')...")

    # Pastikan terminal64.exe diluncurkan langsung di dalam konteks Wine Python
    try:
        log.info(f"Spawning MT5 process directly in Wine Python context: {mt5_path}")
        subprocess.Popen([mt5_path, "/portable"])
        time.sleep(2)
    except Exception as ex:
        log.warning(f"Subprocess spawn warning: {ex}")

    init_ok = False
    for attempt in range(1, 30):
        try:
            # 1. Connect to running MT5 process
            init_ok = mt5.initialize()
            if not init_ok:
                init_ok = mt5.initialize(path=mt5_path)

            if init_ok:
                log.info(f"MT5 terminal IPC initialized successfully on attempt #{attempt}!")
                # 2. Attempt login if credentials are provided
                if login_acc > 0 and password:
                    log.info(f"Logging in to broker account #{login_acc} @ {server_name}...")
                    login_res = mt5.login(login_acc, password=password, server=server_name)
                    log.info(f"MT5 login result: {login_res}, last_error: {mt5.last_error()}")
                break
        except Exception as e:
            log.warning(f"Attempt #{attempt} error: {e}")

        log.info(f"Attempt #{attempt}/30 failed (last_error={mt5.last_error()}), retrying in 3s...")
        time.sleep(3)

    if not init_ok:
        log.error("FAILED to initialize MT5 terminal after 30 attempts!")
        return

    # 3. Verify account info and login status
    acc_info = mt5.account_info()
    if acc_info:
        log.info(f"SUCCESSFULLY LOGGED IN! Account Name: {getattr(acc_info, 'name', 'N/A')}, Balance: {getattr(acc_info, 'balance', 'N/A')}, Server: {getattr(acc_info, 'server', 'N/A')}")
    else:
        log.warning(f"MT5 initialized, but account_info() is None. Attempting manual mt5.login({login_acc})...")
        if login_acc > 0 and password:
            login_ok = mt5.login(login_acc, password=password, server=server_name)
            log.info(f"Manual login result: {login_ok}, last_error: {mt5.last_error()}")

    # 3. Check & Force-enable Algo Trading in MT5 GUI if disabled
    t_info = mt5.terminal_info()
    if t_info:
        trade_allowed = getattr(t_info, 'trade_allowed', False)
        log.info(f"MT5 Terminal Status: Connected={getattr(t_info, 'connected', False)}, Trade Allowed={trade_allowed}")
        if not trade_allowed:
            log.warning("MT5 Algo Trading is DISABLED (trade_allowed=False). Force-toggling Ctrl+E via xdotool...")
            try:
                os.system(r'Z:\bin\bash -c "DISPLAY=:99 xdotool key ctrl+e"')
                time.sleep(1)
                t_info_updated = mt5.terminal_info()
                log.info(f"Updated MT5 Trade Allowed status: {getattr(t_info_updated, 'trade_allowed', False)}")
            except Exception as e:
                log.error(f"Failed to toggle xdotool Ctrl+E: {e}")

    # 3. Check and load key trading symbols (Gold & Major Forex) into Market Watch
    symbols = mt5.symbols_get()
    if symbols:
        log.info(f"Total symbols available from broker: {len(symbols)}")
        gold_syms = [s.name for s in symbols if 'GOLD' in s.name.upper() or 'XAU' in s.name.upper()]
        log.info(f"Available Gold symbols from broker: {gold_syms}")

        selected_count = 0
        key_keywords = ["XAU", "GOLD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "BTC"]
        for s in symbols:
            name_upper = s.name.upper()
            if any(k in name_upper for k in key_keywords):
                if mt5.symbol_select(s.name, True):
                    selected_count += 1
        log.info(f"Successfully selected {selected_count} key trading symbols into MT5 Market Watch.")
    else:
        log.warning("No symbols loaded yet from MT5 broker.")


# Start MT5 terminal connection in daemon background thread so port 18812 opens instantly
bg_thread = threading.Thread(target=connect_mt5_in_background, daemon=True)
bg_thread.start()

# Launch RPyC SlaveServer on port 18812 immediately
log.info("Launching RPyC SlaveServer on 0.0.0.0:18812...")
rpyc_server = ThreadedServer(
    SlaveService,
    hostname="0.0.0.0",
    port=18812,
    reuse_addr=True,
    protocol_config={"sync_request_timeout": 120, "allow_public_attrs": True, "allow_all_attrs": True}
)
rpyc_server.start()


