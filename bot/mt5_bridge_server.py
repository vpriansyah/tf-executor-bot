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
    mt5_path = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    log.info(f"Connecting to MT5 terminal (path='{mt5_path}', login={login_acc}, server='{server_name}')...")

    init_ok = False
    for attempt in range(1, 15):
        try:
            if login_acc > 0 and password and server_name:
                init_ok = mt5.initialize(path=mt5_path, login=login_acc, password=password, server=server_name)
            else:
                init_ok = mt5.initialize(path=mt5_path)

            if not init_ok:
                init_ok = mt5.initialize()

            if init_ok:
                log.info(f"MT5 initialize SUCCESS on attempt #{attempt}!")
                break
        except Exception as e:
            log.warning(f"Attempt #{attempt} error: {e}")

        log.info(f"Attempt #{attempt}/15 failed (last_error={mt5.last_error()}), retrying in 3s...")
        time.sleep(3)

    if not init_ok:
        log.error("FAILED to initialize MT5 terminal after 15 attempts!")
        return

    # 2. Verify account info and login status
    acc_info = mt5.account_info()
    if not acc_info and login_acc > 0 and password:
        log.info(f"MT5 initialized, attempting login for account #{login_acc} on server '{server_name}'...")
        for login_attempt in range(1, 8):
            login_ok = mt5.login(login_acc, password=password, server=server_name)
            acc_info = mt5.account_info()
            if login_ok and acc_info:
                break
            log.warning(f"Login attempt #{login_attempt} result: {login_ok}, last_error: {mt5.last_error()}. Retrying in 3s...")
            time.sleep(3)

    if acc_info:
        log.info(f"SUCCESSFULLY LOGGED IN! Account Name: {getattr(acc_info, 'name', 'N/A')}, Balance: {getattr(acc_info, 'balance', 'N/A')}, Server: {getattr(acc_info, 'server', 'N/A')}")
    else:
        log.warning("MT5 initialized, but account login is not completed yet.")

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




    # 3. Check and load all available symbols into Market Watch
    symbols = mt5.symbols_get(group="*")
    if not symbols:
        symbols = mt5.symbols_get()

    if symbols:
        log.info(f"Total symbols available from broker: {len(symbols)}")
        gold_syms = [s.name for s in symbols if 'GOLD' in s.name.upper() or 'XAU' in s.name.upper()]
        log.info(f"Available Gold symbols from broker: {gold_syms}")

        selected_count = 0
        for s in symbols:
            if mt5.symbol_select(s.name, True):
                selected_count += 1
        log.info(f"Successfully selected {selected_count}/{len(symbols)} symbols into MT5 Market Watch.")
    else:
        log.warning("No symbols loaded yet from MT5 broker.")




# Start MT5 terminal connection in background thread so port 18812 opens immediately
bg_thread = threading.Thread(target=connect_mt5_in_background, daemon=True)
bg_thread.start()

# 4. Launch RPyC ThreadedServer di port 18812 dengan timeout 30s
log.info("Launching RPyC SlaveServer on 0.0.0.0:18812...")
rpyc_server = ThreadedServer(
    SlaveService,
    hostname="0.0.0.0",
    port=18812,
    reuse_addr=True,
    protocol_config={"sync_request_timeout": 30, "allow_public_attrs": True}
)
rpyc_server.start()


