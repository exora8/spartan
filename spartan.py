# -*- coding: utf-8 -*-
import imaplib
import email
from email.header import decode_header
import time
import datetime # Untuk timestamp
import subprocess
import json
import os
import getpass
import sys
import signal # Untuk menangani Ctrl+C
import traceback # Untuk mencetak traceback error
import socket # Untuk error koneksi
import curses # --- CURSES ---: Import library curses
from curses import wrapper # --- CURSES ---: Untuk setup/teardown aman
import threading # --- CURSES ---: Untuk menjalankan listener di thread terpisah
import queue # --- CURSES ---: Untuk komunikasi antar thread
from collections import deque # --- CURSES ---: Untuk buffer log yang efisien

# --- Binance Integration ---
try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException, BinanceOrderException
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False
    # Definisikan exception dummy jika library tidak ada agar script tidak crash
    class BinanceAPIException(Exception): pass
    class BinanceOrderException(Exception): pass
    class Client: # Dummy class
         # Tambahkan konstanta dummy jika library tidak ada
        SIDE_BUY = 'BUY'
        SIDE_SELL = 'SELL'
        ORDER_TYPE_MARKET = 'MARKET'

# --- Konfigurasi & Variabel Global ---
CONFIG_FILE = "config.json"
DEFAULT_SETTINGS = {
    # Email Settings
    "email_address": "",
    "app_password": "",
    "imap_server": "imap.gmail.com",
    "check_interval_seconds": 10, # Default 10 detik
    "target_keyword": "Exora AI",
    "trigger_keyword": "order",
    # Binance Settings
    "binance_api_key": "",
    "binance_api_secret": "",
    "trading_pair": "BTCUSDT", # Contoh: BTCUSDT, ETHUSDT, dll.
    "buy_quote_quantity": 11.0, # Jumlah quote currency untuk dibeli (misal: 11 USDT)
    "sell_base_quantity": 0.0, # Jumlah base currency untuk dijual (misal: 0.0005 BTC) - default 0 agar aman
    "execute_binance_orders": False # Default: Jangan eksekusi order (safety)
}

# Variabel global untuk mengontrol loop utama dan thread
running = True
ui_stop_event = threading.Event() # --- CURSES ---: Sinyal untuk menghentikan UI
message_queue = queue.Queue() # --- CURSES ---: Antrian pesan untuk UI dari thread lain
status_info = { # --- CURSES ---: Menyimpan status terkini untuk ditampilkan di UI
    "email_conn": "Initializing",
    "binance_conn": "N/A",
    "last_check": "N/A",
    "last_email_time": "N/A",
    "last_action": "None",
    "listening": False,
    "error_count": 0,
    "mode": "Idle",
    "new_emails": 0,
}

# --- Kode Warna ANSI (akan dipetakan ke curses) ---
# Definisikan ulang untuk kemudahan pemetaan nanti
COLOR_RESET = 0
COLOR_BOLD = 1 # Akan menggunakan curses.A_BOLD
COLOR_RED = 2
COLOR_GREEN = 3
COLOR_YELLOW = 4
COLOR_BLUE = 5
COLOR_MAGENTA = 6
COLOR_CYAN = 7
COLOR_WHITE = 8 # Default

# --- Fungsi Penanganan Sinyal (Ctrl+C) ---
def signal_handler(sig, frame):
    global running
    # --- CURSES ---: Beri tahu UI dan thread listener untuk berhenti
    if running:
        running = False
        ui_stop_event.set()
        # Beri sedikit waktu untuk thread lain merespon
        time.sleep(0.1)
        # Tidak perlu print di sini karena curses akan menangani layar keluar
        # Mungkin tambahkan pesan ke queue jika ingin log terlihat di UI sesaat sebelum keluar
        try:
            message_queue.put(("LOG", "[WARN] Ctrl+C detected. Stopping...", COLOR_YELLOW))
        except: # Abaikan jika queue sudah tidak bisa diakses
            pass
    # sys.exit(0) akan dipanggil setelah curses.wrapper selesai

# Pasang signal handler
signal.signal(signal.SIGINT, signal_handler)

# --- Fungsi Konfigurasi (Tetap sama, tidak perlu curses) ---
def load_settings():
    """Memuat pengaturan dari file JSON, memastikan semua kunci ada."""
    settings = DEFAULT_SETTINGS.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_settings = json.load(f)
                settings.update(loaded_settings)

                # Validasi (sedikit disederhanakan outputnya untuk curses)
                if settings.get("check_interval_seconds", 10) < 5:
                    settings["check_interval_seconds"] = 10
                if not isinstance(settings.get("buy_quote_quantity"), (int, float)) or settings.get("buy_quote_quantity") <= 0:
                     settings["buy_quote_quantity"] = DEFAULT_SETTINGS['buy_quote_quantity']
                if not isinstance(settings.get("sell_base_quantity"), (int, float)) or settings.get("sell_base_quantity") < 0:
                     settings["sell_base_quantity"] = DEFAULT_SETTINGS['sell_base_quantity']
                if not isinstance(settings.get("execute_binance_orders"), bool):
                    settings["execute_binance_orders"] = False
                save_settings(settings, quiet=True) # Simpan koreksi tanpa print

        except json.JSONDecodeError:
            save_settings(settings, quiet=True)
        except Exception as e:
            # Log error ini mungkin tidak terlihat jika terjadi sebelum UI curses aktif
            print(f"[ERROR] Failed to load config: {e}")
    else:
        save_settings(settings, quiet=True)
    return settings

def save_settings(settings, quiet=False):
    """Menyimpan pengaturan ke file JSON."""
    try:
        settings['check_interval_seconds'] = int(settings.get('check_interval_seconds', 10))
        settings['buy_quote_quantity'] = float(settings.get('buy_quote_quantity', 11.0))
        settings['sell_base_quantity'] = float(settings.get('sell_base_quantity', 0.0))
        settings['execute_binance_orders'] = bool(settings.get('execute_binance_orders', False))

        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings, f, indent=4, sort_keys=True)
        # --- CURSES ---: Jangan print jika quiet
        if not quiet:
             # Jika UI curses aktif, kirim ke queue. Jika tidak, print biasa.
             if 'stdscr' in globals() and not ui_stop_event.is_set(): # Cek kasar jika UI aktif
                 message_queue.put(("LOG", f"[INFO] Settings saved to '{CONFIG_FILE}'", COLOR_GREEN))
             else:
                 print(f"\033[92m[INFO] Pengaturan berhasil disimpan ke '{CONFIG_FILE}'\033[0m")
    except Exception as e:
        if not quiet:
            if 'stdscr' in globals() and not ui_stop_event.is_set():
                 message_queue.put(("LOG", f"[ERROR] Failed to save config: {e}", COLOR_RED))
            else:
                 print(f"\033[91m[ERROR] Gagal menyimpan konfigurasi: {e}\033[0m")

# --- Fungsi Utilitas (Beberapa diubah untuk curses) ---
# clear_screen tidak diperlukan lagi dengan curses

def decode_mime_words(s):
    # Fungsi ini tetap sama
    if not s:
        return ""
    try:
        decoded_parts = decode_header(s)
        result = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                # Coba encoding yang diberikan, fallback ke utf-8, ganti error
                try:
                    result.append(part.decode(encoding or 'utf-8', errors='replace'))
                except LookupError: # Jika encoding tidak dikenal
                    result.append(part.decode('utf-8', errors='replace'))
            else:
                result.append(part)
        return "".join(result)
    except Exception:
        # Fallback jika decode_header gagal total
        return str(s)


def get_text_from_email(msg):
    # Fungsi ini tetap sama, tapi log errornya akan diarahkan ke UI
    text_content = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                    charset = part.get_content_charset()
                    payload = part.get_payload(decode=True)
                    if payload:
                         # Coba charset, fallback ke utf-8
                        try:
                            text_content += payload.decode(charset or 'utf-8', errors='replace')
                        except LookupError:
                            text_content += payload.decode('utf-8', errors='replace')
                except Exception as e:
                    # --- CURSES ---: Kirim peringatan ke UI
                    message_queue.put(("LOG", f"[WARN] Could not decode email part: {e}", COLOR_YELLOW))
    else:
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            try:
                charset = msg.get_content_charset()
                payload = msg.get_payload(decode=True)
                if payload:
                    try:
                        text_content = payload.decode(charset or 'utf-8', errors='replace')
                    except LookupError:
                        text_content = payload.decode('utf-8', errors='replace')
            except Exception as e:
                 # --- CURSES ---: Kirim peringatan ke UI
                 message_queue.put(("LOG", f"[WARN] Could not decode email body: {e}", COLOR_YELLOW))
    return text_content.lower()

# --- Fungsi Beep (Output diubah untuk curses) ---
def trigger_beep(action):
    global status_info
    try:
        # --- CURSES ---: Kirim log ke UI
        message_queue.put(("LOG", f"[ACTION] Triggering BEEP for '{action.upper()}'", COLOR_MAGENTA))
        status_info["last_action"] = f"Beep ({action.upper()})" # Update status
        if action == "buy":
            subprocess.run(["beep", "-f", "1000", "-l", "500", "-D", "500", "-r", "5"], check=True, capture_output=True, text=True)
        elif action == "sell":
            subprocess.run(["beep", "-f", "700", "-l", "1000", "-D", "500", "-r", "2"], check=True, capture_output=True, text=True)
        else:
             message_queue.put(("LOG", f"[WARN] Unknown beep action '{action}'.", COLOR_YELLOW))
    except FileNotFoundError:
        message_queue.put(("LOG", f"[WARN] 'beep' command not found. Skipping beep.", COLOR_YELLOW))
    except subprocess.CalledProcessError as e:
        message_queue.put(("LOG", f"[ERROR] Failed to run 'beep': {e}", COLOR_RED))
        if e.stderr: message_queue.put(("LOG", f"         Stderr: {e.stderr.strip()}", COLOR_RED))
    except Exception as e:
        message_queue.put(("LOG", f"[ERROR] Unexpected error during beep: {e}", COLOR_RED))

# --- Fungsi Eksekusi Binance (Output diubah untuk curses) ---
def get_binance_client(settings):
    """Membuat instance Binance client."""
    global status_info
    if not BINANCE_AVAILABLE:
        message_queue.put(("LOG", "[ERROR] python-binance library not installed. Cannot create client.", COLOR_RED))
        status_info["binance_conn"] = "Lib Missing"
        return None
    if not settings.get('binance_api_key') or not settings.get('binance_api_secret'):
        message_queue.put(("LOG", "[ERROR] Binance API Key or Secret not set in config.", COLOR_RED))
        status_info["binance_conn"] = "No API Key"
        return None
    try:
        message_queue.put(("LOG", "[BINANCE] Attempting to connect...", COLOR_CYAN))
        client = Client(settings['binance_api_key'], settings['binance_api_secret'])
        client.ping() # Test connection
        message_queue.put(("LOG", "[BINANCE] Connection to Binance API successful.", COLOR_GREEN))
        status_info["binance_conn"] = "Connected"
        return client
    except (BinanceAPIException, BinanceOrderException) as e:
        message_queue.put(("LOG", f"[BINANCE ERROR] Failed to connect/authenticate: {e}", COLOR_RED))
        status_info["binance_conn"] = "Auth Error"
        return None
    except (ConnectionError, socket.error) as e:
        message_queue.put(("LOG", f"[BINANCE ERROR] Connection error: {e}", COLOR_RED))
        status_info["binance_conn"] = "Conn Error"
        return None
    except Exception as e:
        message_queue.put(("LOG", f"[ERROR] Failed to create Binance client: {e}", COLOR_RED))
        status_info["binance_conn"] = "Error"
        return None

def execute_binance_order(client, settings, side):
    """Mengeksekusi order MARKET BUY atau SELL di Binance."""
    global status_info
    if not client:
        message_queue.put(("LOG", "[BINANCE] Execution cancelled, client not valid.", COLOR_RED))
        return False
    if not settings.get("execute_binance_orders", False):
        message_queue.put(("LOG", "[BINANCE] Order execution disabled in settings. Skipping.", COLOR_YELLOW))
        return False # Skipped, not failed

    pair = settings.get('trading_pair', '').upper()
    if not pair:
        message_queue.put(("LOG", "[BINANCE ERROR] Trading pair not set in config.", COLOR_RED))
        return False

    order_details = {}
    action_desc = ""
    order_side_str = "BUY" if side == Client.SIDE_BUY else "SELL"

    try:
        if side == Client.SIDE_BUY:
            quote_qty = settings.get('buy_quote_quantity', 0.0)
            if quote_qty <= 0:
                 message_queue.put(("LOG", "[BINANCE ERROR] Buy Quote Quantity must be > 0.", COLOR_RED))
                 return False
            order_details = {'symbol': pair, 'side': Client.SIDE_BUY, 'type': Client.ORDER_TYPE_MARKET, 'quoteOrderQty': quote_qty}
            action_desc = f"MARKET BUY {quote_qty} (quote) of {pair}"

        elif side == Client.SIDE_SELL:
            base_qty = settings.get('sell_base_quantity', 0.0)
            if base_qty <= 0:
                 message_queue.put(("LOG", "[BINANCE ERROR] Sell Base Quantity must be > 0.", COLOR_RED))
                 return False
            order_details = {'symbol': pair, 'side': Client.SIDE_SELL, 'type': Client.ORDER_TYPE_MARKET, 'quantity': base_qty}
            action_desc = f"MARKET SELL {base_qty} (base) of {pair}"
        else:
            message_queue.put(("LOG", f"[BINANCE ERROR] Invalid order side: {side}", COLOR_RED))
            return False

        message_queue.put(("LOG", f"[BINANCE] Attempting execution: {action_desc}...", COLOR_MAGENTA))
        status_info["last_action"] = f"Binance {order_side_str} ({pair})" # Update status

        # --- PLACE ORDER ---
        order_result = client.create_order(**order_details)
        # -----------------

        message_queue.put(("LOG", f"[BINANCE SUCCESS] Order executed!", COLOR_GREEN | COLOR_BOLD)) # Green & Bold
        message_queue.put(("LOG", f"  Order ID : {order_result.get('orderId')}", COLOR_GREEN))
        message_queue.put(("LOG", f"  Symbol   : {order_result.get('symbol')}", COLOR_GREEN))
        message_queue.put(("LOG", f"  Side     : {order_result.get('side')}", COLOR_GREEN))
        message_queue.put(("LOG", f"  Status   : {order_result.get('status')}", COLOR_GREEN))

        if order_result.get('fills'):
            total_qty = sum(float(f['qty']) for f in order_result['fills'])
            total_quote_qty = sum(float(f['qty']) * float(f['price']) for f in order_result['fills'])
            avg_price = total_quote_qty / total_qty if total_qty else 0
            message_queue.put(("LOG", f"  Avg Price: {avg_price:.8f}", COLOR_GREEN))
            message_queue.put(("LOG", f"  Filled Qty: {total_qty:.8f}", COLOR_GREEN))
        status_info["last_action"] = f"Binance {order_side_str} OK ({pair})"
        return True

    except (BinanceAPIException, BinanceOrderException) as e:
        message_queue.put(("LOG", f"[BINANCE API/ORDER ERROR] Failed: {e.status_code} - {e.message}", COLOR_RED | COLOR_BOLD))
        if hasattr(e, 'code'):
            if e.code == -2010: message_queue.put(("LOG", "         -> Likely insufficient balance.", COLOR_RED))
            elif e.code == -1121: message_queue.put(("LOG", f"         -> Invalid trading pair '{pair}'.", COLOR_RED))
            elif e.code == -1013 or 'MIN_NOTIONAL' in e.message or 'LOT_SIZE' in e.message:
                 message_queue.put(("LOG", "         -> Order size too small (check MIN_NOTIONAL/LOT_SIZE).", COLOR_RED))
        status_info["last_action"] = f"Binance {order_side_str} FAILED ({pair})"
        status_info["error_count"] += 1
        return False
    except Exception as e:
        message_queue.put(("LOG", f"[ERROR] Unexpected error during Binance order: {e}", COLOR_RED | COLOR_BOLD))
        # traceback.print_exc() # Avoid printing directly to console in curses
        message_queue.put(("LOG", f"  Traceback: {traceback.format_exc(limit=1)}", COLOR_RED)) # Log brief traceback
        status_info["last_action"] = f"Binance {order_side_str} ERROR ({pair})"
        status_info["error_count"] += 1
        return False

# --- Fungsi Pemrosesan Email (Output diubah untuk curses) ---
def process_email(mail, email_id, settings, binance_client):
    """Mengambil, mem-parsing, dan memproses satu email, lalu eksekusi order jika sesuai."""
    global running, status_info
    if not running: return

    target_keyword_lower = settings['target_keyword'].lower()
    trigger_keyword_lower = settings['trigger_keyword'].lower()
    email_id_str = email_id.decode('utf-8')

    try:
        status, data = mail.fetch(email_id, "(RFC822)")
        if status != 'OK':
            message_queue.put(("LOG", f"[ERROR] Failed to fetch email ID {email_id_str}: {status}", COLOR_RED))
            status_info["error_count"] += 1
            return

        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        subject = decode_mime_words(msg["Subject"])
        sender = decode_mime_words(msg["From"])
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status_info["last_email_time"] = timestamp # Update status

        message_queue.put(("LOG", f"--- New Email ({timestamp}) ---", COLOR_CYAN))
        message_queue.put(("LOG", f" ID    : {email_id_str}", COLOR_WHITE))
        message_queue.put(("LOG", f" From  : {sender}", COLOR_WHITE))
        message_queue.put(("LOG", f" Subject: {subject}", COLOR_WHITE))

        body = get_text_from_email(msg)
        # Batasi panjang body yang dicari agar tidak terlalu berat
        full_content_search = (subject.lower() + " " + body[:2000]) # Cari hanya di awal body + subjek

        if target_keyword_lower in full_content_search:
            message_queue.put(("LOG", f"[INFO] Target keyword '{settings['target_keyword']}' found.", COLOR_GREEN))
            try:
                target_index = full_content_search.index(target_keyword_lower)
                # Cari trigger *setelah* target
                trigger_index = full_content_search.index(trigger_keyword_lower, target_index + len(target_keyword_lower))
                start_word_index = trigger_index + len(trigger_keyword_lower)
                text_after_trigger = full_content_search[start_word_index:].lstrip()
                words_after_trigger = text_after_trigger.split(maxsplit=1)

                if words_after_trigger:
                    action_word = words_after_trigger[0].strip('.,!?:;()[]{}').lower()
                    message_queue.put(("LOG", f"[INFO] Trigger '{settings['trigger_keyword']}' found. Next word: '{action_word}'", COLOR_GREEN | COLOR_BOLD))

                    order_executed = False
                    if action_word == "buy":
                        trigger_beep("buy")
                        if binance_client and settings.get("execute_binance_orders"):
                           execute_binance_order(binance_client, settings, Client.SIDE_BUY)
                           order_executed = True
                        elif settings.get("execute_binance_orders"):
                            message_queue.put(("LOG", "[WARN] Binance execution active but client invalid/unavailable.", COLOR_YELLOW))
                            status_info["last_action"] = "Binance BUY Skipped (No Client)"

                    elif action_word == "sell":
                        trigger_beep("sell")
                        if binance_client and settings.get("execute_binance_orders"):
                           execute_binance_order(binance_client, settings, Client.SIDE_SELL)
                           order_executed = True
                        elif settings.get("execute_binance_orders"):
                           message_queue.put(("LOG", "[WARN] Binance execution active but client invalid/unavailable.", COLOR_YELLOW))
                           status_info["last_action"] = "Binance SELL Skipped (No Client)"
                    else:
                        message_queue.put(("LOG", f"[WARN] Word after '{settings['trigger_keyword']}' ({action_word}) is not 'buy' or 'sell'. No market action.", COLOR_YELLOW))
                        status_info["last_action"] = f"Action Skipped ('{action_word}')"

                    if not order_executed and settings.get("execute_binance_orders") and action_word in ["buy", "sell"]:
                         message_queue.put(("LOG", "[BINANCE] Execution not performed (see logs above or check client status).", COLOR_YELLOW))

                else:
                    message_queue.put(("LOG", f"[WARN] No word found after '{settings['trigger_keyword']}'.", COLOR_YELLOW))
                    status_info["last_action"] = "Action Skipped (No Word)"

            except ValueError:
                message_queue.put(("LOG", f"[WARN] Trigger '{settings['trigger_keyword']}' not found *after* target '{settings['target_keyword']}'.", COLOR_YELLOW))
            except Exception as e:
                 message_queue.put(("LOG", f"[ERROR] Failed parsing word after trigger: {e}", COLOR_RED))
                 status_info["error_count"] += 1
        else:
            message_queue.put(("LOG", f"[INFO] Target keyword '{settings['target_keyword']}' not found in this email.", COLOR_BLUE))

        # Tandai email sebagai sudah dibaca ('Seen')
        try:
            # message_queue.put(("LOG", f"[INFO] Marking email {email_id_str} as read.", COLOR_BLUE))
            mail.store(email_id, '+FLAGS', '\\Seen')
        except Exception as e:
            message_queue.put(("LOG", f"[ERROR] Failed to mark email {email_id_str} as 'Seen': {e}", COLOR_RED))
            status_info["error_count"] += 1
        message_queue.put(("LOG", "-------------------------------------------", COLOR_CYAN))

    except Exception as e:
        message_queue.put(("LOG", f"[ERROR] Failed to process email ID {email_id_str}:", COLOR_RED | COLOR_BOLD))
        message_queue.put(("LOG", f"  {traceback.format_exc(limit=1)}", COLOR_RED)) # Log brief traceback
        status_info["error_count"] += 1

# --- CURSES: Fungsi untuk Listener yang berjalan di thread terpisah ---
def email_listener_thread(settings):
    global running, status_info, message_queue
    mail = None
    binance_client = None
    wait_time = 30 # Waktu tunggu sebelum retry koneksi

    # --- Setup Binance Client di Awal (jika diaktifkan) ---
    if settings.get("execute_binance_orders"):
        status_info["mode"] = "Email & Binance"
        if not BINANCE_AVAILABLE:
             message_queue.put(("LOG", "[FATAL] Binance execution enabled but library missing!", COLOR_RED | COLOR_BOLD))
             status_info["binance_conn"] = "Lib Missing"
             # Kita tidak menghentikan thread di sini, biarkan UI yang memutuskan
        else:
            message_queue.put(("LOG", "[SYS] Initializing Binance connection...", COLOR_CYAN))
            binance_client = get_binance_client(settings) # Output sudah ke queue
            if not binance_client:
                message_queue.put(("LOG", "[FATAL] Failed to initialize Binance Client. Check API Key/Secret & connection.", COLOR_RED | COLOR_BOLD))
                message_queue.put(("LOG", "       Execution will fail. Disable in Settings or fix.", COLOR_YELLOW))
                # Tetap jalan untuk email
            else:
                message_queue.put(("LOG", "[SYS] Binance Client ready.", COLOR_GREEN))
    else:
        status_info["mode"] = "Email Only"
        status_info["binance_conn"] = "Disabled"
        message_queue.put(("LOG", "[INFO] Binance order execution disabled.", COLOR_YELLOW))

    # --- Loop Utama Email Listener ---
    while running:
        try:
            message_queue.put(("LOG", f"[SYS] Connecting to IMAP server ({settings['imap_server']})...", COLOR_CYAN))
            status_info["email_conn"] = "Connecting"
            mail = imaplib.IMAP4_SSL(settings['imap_server'], timeout=20) # Tambah timeout
            message_queue.put(("LOG", f"[SYS] Connected to {settings['imap_server']}", COLOR_GREEN))
            message_queue.put(("LOG", f"[SYS] Logging in as {settings['email_address']}...", COLOR_CYAN))
            status_info["email_conn"] = "Logging In"
            mail.login(settings['email_address'], settings['app_password'])
            message_queue.put(("LOG", f"[SYS] Email login successful as {settings['email_address']}", COLOR_GREEN | COLOR_BOLD))
            status_info["email_conn"] = "Connected"
            mail.select("inbox")
            message_queue.put(("LOG", "[INFO] Listening started in INBOX...", COLOR_GREEN | COLOR_BOLD))
            status_info["listening"] = True
            status_info["error_count"] = 0 # Reset error count on successful connect

            last_noop_time = time.time()

            while running:
                current_time = time.time()
                status_info["last_check"] = datetime.datetime.now().strftime("%H:%M:%S")

                # 1. Cek koneksi IMAP secara berkala (misal setiap 60 detik)
                if current_time - last_noop_time > 60:
                    try:
                        status, _ = mail.noop()
                        if status != 'OK':
                            message_queue.put(("LOG", f"[WARN] IMAP NOOP failed ({status}). Reconnecting...", COLOR_YELLOW))
                            status_info["email_conn"] = "NOOP Failed"
                            break # Keluar loop inner untuk reconnect
                        last_noop_time = current_time # Reset timer noop
                        # message_queue.put(("LOG", "[DEBUG] IMAP NOOP OK", COLOR_BLUE)) # Pesan debug opsional
                    except Exception as NopErr:
                         message_queue.put(("LOG", f"[WARN] IMAP connection lost ({NopErr}). Reconnecting...", COLOR_YELLOW))
                         status_info["email_conn"] = "Conn Lost"
                         status_info["error_count"] += 1
                         break # Keluar loop inner untuk reconnect

                # 2. Cek koneksi Binance jika aktif & client ada (misal setiap 5 menit)
                #    Ini hanya contoh, sesuaikan frekuensinya
                # if binance_client and current_time - last_binance_ping_time > 300:
                #     try:
                #          binance_client.ping()
                #          last_binance_ping_time = current_time
                #          # message_queue.put(("LOG", "[DEBUG] Binance Ping OK", COLOR_BLUE))
                #     except Exception as PingErr:
                #          message_queue.put(("LOG", f"[WARN] Ping to Binance API failed ({PingErr}). Re-creating client...", COLOR_YELLOW))
                #          status_info["binance_conn"] = "Ping Failed"
                #          status_info["error_count"] += 1
                #          binance_client = get_binance_client(settings) # Coba buat ulang
                #          if not binance_client:
                #               message_queue.put(("LOG", "       Failed re-creating Binance client. Execution might fail.", COLOR_RED))
                #          time.sleep(5) # Jeda setelah error ping

                # 3. Cari email UNSEEN
                try:
                    status, messages = mail.search(None, '(UNSEEN)')
                    if status != 'OK':
                         message_queue.put(("LOG", f"[ERROR] Failed to search emails: {status}", COLOR_RED))
                         status_info["email_conn"] = "Search Failed"
                         status_info["error_count"] += 1
                         break # Keluar loop inner untuk reconnect

                    email_ids = messages[0].split()
                    if email_ids:
                        status_info["new_emails"] = len(email_ids)
                        message_queue.put(("LOG", f"[INFO] Found {len(email_ids)} new email(s)!", COLOR_GREEN | COLOR_BOLD))
                        for email_id in email_ids:
                            if not running: break
                            process_email(mail, email_id, settings, binance_client)
                        if not running: break
                        message_queue.put(("LOG", "[INFO] Processing complete. Resuming listening...", COLOR_GREEN))
                        status_info["new_emails"] = 0 # Reset counter
                    else:
                        # Tidak ada email baru, tunggu interval
                        wait_interval = settings['check_interval_seconds']
                        # message_queue.put(("LOG", f"[INFO] No new emails. Checking again in {wait_interval}s...", COLOR_BLUE)) # Bisa jadi terlalu berisik
                        # Tidur dengan cara yang bisa diinterupsi oleh Ctrl+C
                        for _ in range(wait_interval):
                            if not running: break
                            time.sleep(1)
                        if not running: break

                except (imaplib.IMAP4.error, imaplib.IMAP4.abort, socket.error, OSError) as search_err:
                     message_queue.put(("LOG", f"[ERROR] Error during email search/processing: {search_err}. Reconnecting...", COLOR_RED))
                     status_info["email_conn"] = "Search Error"
                     status_info["error_count"] += 1
                     break # Keluar loop inner untuk reconnect


            # Tutup koneksi IMAP jika keluar loop inner
            if mail and mail.state == 'SELECTED':
                try: mail.close()
                except Exception: pass

        # Exception Handling untuk koneksi/login awal
        except (imaplib.IMAP4.error, imaplib.IMAP4.abort) as e:
            message_queue.put((f"LOG", f"[ERROR] IMAP Error: {e}", COLOR_RED | COLOR_BOLD))
            status_info["error_count"] += 1
            if "authentication failed" in str(e).lower() or "invalid credentials" in str(e).lower():
                message_queue.put(("LOG", "[FATAL] Email Login FAILED! Check email/App Password.", COLOR_RED | COLOR_BOLD))
                status_info["email_conn"] = "Login Failed"
                running = False # Hentikan total jika login gagal
                ui_stop_event.set()
                break # Keluar loop utama thread
            else:
                status_info["email_conn"] = "IMAP Error"
            message_queue.put(("LOG", f"[WARN] Retrying connection in {wait_time} seconds...", COLOR_YELLOW))
            time.sleep(wait_time)
        except (ConnectionError, OSError, socket.error, socket.gaierror) as e:
             message_queue.put(("LOG", f"[ERROR] Connection Error: {e}", COLOR_RED | COLOR_BOLD))
             status_info["email_conn"] = "Network Error"
             status_info["error_count"] += 1
             message_queue.put(("LOG", f"[WARN] Check internet. Retrying in {wait_time} seconds...", COLOR_YELLOW))
             time.sleep(wait_time)
        except Exception as e:
            message_queue.put(("LOG", f"[ERROR] Unexpected error in listener loop:", COLOR_RED | COLOR_BOLD))
            message_queue.put(("LOG", f"  {traceback.format_exc(limit=2)}", COLOR_RED))
            status_info["email_conn"] = "Unknown Error"
            status_info["error_count"] += 1
            message_queue.put(("LOG", f"[WARN] Retrying connection in {wait_time} seconds...", COLOR_YELLOW))
            time.sleep(wait_time)
        finally:
            status_info["listening"] = False
            if mail:
                try:
                    if mail.state != 'LOGOUT': mail.logout()
                    message_queue.put(("LOG", "[SYS] Logged out from IMAP server.", COLOR_CYAN))
                except Exception: pass
            mail = None
        if running:
             # Beri jeda singkat sebelum mencoba koneksi lagi setelah error
             for _ in range(2):
                if not running: break
                time.sleep(1)

    message_queue.put(("LOG", "[INFO] Email listener thread stopped.", COLOR_YELLOW))
    status_info["listening"] = False
    status_info["email_conn"] = "Stopped"
    status_info["binance_conn"] = "N/A"


# --- CURSES: Fungsi untuk menggambar UI ---
def draw_ui(stdscr, log_buffer, settings):
    global status_info
    try:
        stdscr.erase() # Hapus layar lama
        curses.curs_set(0) # Sembunyikan kursor
        h, w = stdscr.getmaxyx() # Dapatkan ukuran terminal

        # --- Ukuran Area ---
        header_h = 1
        status_h = 4 # Tinggi area status
        log_h = h - header_h - status_h
        log_win_h = log_h - 2 # Tinggi window log (kurangi border)
        log_win_w = w - 2 # Lebar window log (kurangi border)

        # --- Warna (pastikan init_colors sudah dipanggil) ---
        # Definisikan pasangan warna di init_colors
        HEADER_PAIR = curses.color_pair(10)
        STATUS_PAIR = curses.color_pair(11)
        BORDER_PAIR = curses.color_pair(8) # Cyan border
        ERROR_PAIR = curses.color_pair(COLOR_RED)
        WARN_PAIR = curses.color_pair(COLOR_YELLOW)
        INFO_PAIR = curses.color_pair(COLOR_BLUE)
        SUCCESS_PAIR = curses.color_pair(COLOR_GREEN)
        ACTION_PAIR = curses.color_pair(COLOR_MAGENTA)
        DEFAULT_PAIR = curses.color_pair(COLOR_WHITE)

        # --- 1. Header ---
        title = " Exora AI Listener "
        stdscr.attron(HEADER_PAIR | curses.A_BOLD)
        stdscr.addstr(0, 0, title.center(w, "="), HEADER_PAIR | curses.A_BOLD)
        stdscr.attroff(HEADER_PAIR | curses.A_BOLD)

        # --- 2. Status Window ---
        status_win = curses.newwin(status_h, w, header_h, 0)
        status_win.bkgd(' ', STATUS_PAIR) # Latar belakang window status
        status_win.box()

        # Informasi Status (contoh)
        mode_str = f"Mode: {status_info['mode']}"
        email_str = f"Email: {status_info['email_conn']}"
        binance_str = f"Binance: {status_info['binance_conn']}"
        listen_str = f"Listening: {'Yes' if status_info['listening'] else 'No'}"
        check_str = f"Last Check: {status_info['last_check']}"
        email_time_str = f"Last Email: {status_info['last_email_time']}"
        action_str = f"Last Action: {status_info['last_action'][:w-16]}" # Potong jika terlalu panjang
        errors_str = f"Errors: {status_info['error_count']}"
        time_str = datetime.datetime.now().strftime("%H:%M:%S")
        new_mail_str = f"New: {status_info['new_emails']}" if status_info['new_emails'] > 0 else ""

        # Tampilkan status
        status_win.addstr(1, 2, f"{mode_str.ljust(25)} {listen_str.ljust(15)} {check_str}", STATUS_PAIR)
        status_win.addstr(2, 2, f"{email_str.ljust(25)} {binance_str.ljust(15)} {email_time_str}", STATUS_PAIR)

        # Warna dinamis untuk status koneksi
        email_color = SUCCESS_PAIR if "Connected" in status_info["email_conn"] else (WARN_PAIR if "Connecting" in status_info["email_conn"] else ERROR_PAIR)
        binance_color = SUCCESS_PAIR if "Connected" in status_info["binance_conn"] else (INFO_PAIR if "Disabled" in status_info["binance_conn"] or "N/A" in status_info["binance_conn"] else ERROR_PAIR)
        status_win.addstr(1, 9, status_info["email_conn"], email_color | curses.A_BOLD)
        status_win.addstr(1, 35, "Yes" if status_info["listening"] else "No", SUCCESS_PAIR if status_info["listening"] else WARN_PAIR)
        status_win.addstr(2, 10, status_info["binance_conn"], binance_color | curses.A_BOLD)


        # Tampilkan last action & error count di baris bawah status
        status_win.addstr(status_h - 2, 2, action_str, STATUS_PAIR)
        status_win.addstr(status_h - 2, w - len(errors_str) - 2 - len(time_str) - 2, errors_str, ERROR_PAIR if status_info["error_count"] > 0 else STATUS_PAIR)
        # Tampilkan waktu di kanan bawah status
        status_win.addstr(status_h - 2, w - len(time_str) - 2, time_str, STATUS_PAIR)

        # Animasi sederhana saat menunggu
        if not status_info['listening'] and running:
             spinner = "|/-\\"
             spin_char = spinner[int(time.time()*2) % 4]
             status_win.addstr(1, w - 3, spin_char, WARN_PAIR)
        elif status_info['new_emails'] > 0:
            status_win.addstr(1, w - 3 - len(new_mail_str), new_mail_str, SUCCESS_PAIR | curses.A_BOLD | curses.A_BLINK) # Berkedip jika ada email baru

        status_win.refresh()


        # --- 3. Log Window ---
        log_win_y = header_h + status_h
        log_win = curses.newwin(log_h, w, log_win_y, 0)
        log_win.box()
        log_win.addstr(0, 2, " Logs ", BORDER_PAIR | curses.A_BOLD) # Judul di border

        # Tampilkan log dari buffer (hanya yg muat di window)
        log_start_index = max(0, len(log_buffer) - log_win_h)
        for i, log_entry in enumerate(list(log_buffer)[log_start_index:]):
            if i >= log_win_h: break # Pastikan tidak melebihi tinggi window
            log_time, log_text, log_color_code = log_entry
            log_pair_code = log_color_code if isinstance(log_color_code, int) else COLOR_WHITE # Default white
            is_bold = bool(log_pair_code & COLOR_BOLD) # Cek flag bold
            actual_color = log_pair_code & ~COLOR_BOLD # Hilangkan flag bold untuk cari color pair
            log_pair = curses.color_pair(actual_color if actual_color <= 8 else COLOR_WHITE) # Dapatkan color pair
            if is_bold: log_pair |= curses.A_BOLD

            # Potong pesan jika terlalu panjang
            display_text = f"{log_time} {log_text}"
            max_len = log_win_w - 1 # Kurangi 1 untuk padding/border
            if len(display_text) > max_len:
                display_text = display_text[:max_len-3] + "..."

            try:
                 log_win.addstr(i + 1, 1, display_text, log_pair) # Mulai dari y=1, x=1 di dalam border
            except curses.error:
                 # Terjadi jika mencoba menulis di luar batas (misal saat resize)
                 pass # Abaikan error menggambar

        log_win.refresh()

    except curses.error as e:
        # Tangani error curses (misal terminal terlalu kecil)
        # Di production, mungkin ingin log ke file
        # print(f"Curses error: {e}") # Hindari print saat curses aktif
        pass
    except Exception as e:
        # Tangani error lain saat menggambar UI
        # print(f"UI draw error: {e}")
        # print(traceback.format_exc())
         pass


# --- CURSES: Fungsi inisialisasi warna ---
def init_colors():
    curses.start_color()
    curses.use_default_colors() # Gunakan background terminal default jika bisa

    # Define color pairs (pair_number, foreground, background)
    # Background -1 berarti default terminal background
    curses.init_pair(COLOR_RED, curses.COLOR_RED, -1)
    curses.init_pair(COLOR_GREEN, curses.COLOR_GREEN, -1)
    curses.init_pair(COLOR_YELLOW, curses.COLOR_YELLOW, -1)
    curses.init_pair(COLOR_BLUE, curses.COLOR_BLUE, -1)
    curses.init_pair(COLOR_MAGENTA, curses.COLOR_MAGENTA, -1)
    curses.init_pair(COLOR_CYAN, curses.COLOR_CYAN, -1)
    curses.init_pair(COLOR_WHITE, curses.COLOR_WHITE, -1) # Default text
    curses.init_pair(8, curses.COLOR_CYAN, -1) # Border pair (contoh)

    # Warna khusus untuk UI elements
    curses.init_pair(10, curses.COLOR_BLACK, curses.COLOR_CYAN)   # Header: Black on Cyan
    curses.init_pair(11, curses.COLOR_WHITE, curses.COLOR_BLUE) # Status: White on Blue

# --- CURSES: Fungsi utama yang menjalankan UI loop ---
def curses_main(stdscr, settings):
    global running, ui_stop_event, message_queue, status_info
    init_colors() # Inisialisasi warna
    stdscr.nodelay(True) # Jangan block saat menunggu input (getch)
    curses.curs_set(0)   # Sembunyikan kursor

    log_buffer = deque(maxlen=200) # Buffer untuk menyimpan log (misal max 200 baris)
    listener_thread = None

    # --- Mulai thread listener email ---
    status_info["email_conn"] = "Starting..."
    status_info["binance_conn"] = "N/A" if not settings.get("execute_binance_orders") else "Starting..."
    listener_thread = threading.Thread(target=email_listener_thread, args=(settings,), daemon=True)
    listener_thread.start()

    # --- Loop Utama UI ---
    while running and not ui_stop_event.is_set():
        # 1. Proses pesan dari queue
        while not message_queue.empty():
            try:
                msg_type, *data = message_queue.get_nowait()
                if msg_type == "LOG":
                    log_text, log_color = data
                    log_time = datetime.datetime.now().strftime("%H:%M:%S")
                    log_buffer.append((log_time, log_text, log_color))
                elif msg_type == "STATUS_UPDATE": # Contoh jika perlu update status spesifik
                    status_key, status_value = data
                    if status_key in status_info:
                        status_info[status_key] = status_value
                message_queue.task_done()
            except queue.Empty:
                break
            except Exception as e:
                 # Log error processing queue ke buffer log itu sendiri
                 log_time = datetime.datetime.now().strftime("%H:%M:%S")
                 log_buffer.append((log_time, f"[UI ERROR] Failed processing queue: {e}", COLOR_RED))


        # 2. Gambar ulang UI
        draw_ui(stdscr, log_buffer, settings)

        # 3. Cek input (misal 'q' untuk keluar) - opsional
        key = stdscr.getch()
        if key == ord('q') or key == ord('Q'):
            message_queue.put(("LOG", "[INFO] 'Q' pressed. Exiting...", COLOR_YELLOW))
            running = False
            ui_stop_event.set()
            break # Keluar loop UI

        # Beri sedikit jeda agar tidak 100% CPU usage
        time.sleep(0.1) # Refresh rate UI (10 FPS)

    # --- Cleanup setelah loop ---
    # Pastikan thread listener berhenti jika belum
    if listener_thread and listener_thread.is_alive():
        # Beri waktu sedikit lagi untuk thread berhenti secara normal
        listener_thread.join(timeout=1.0)

    # Tampilkan pesan terakhir sebelum keluar (jika terminal mengizinkan)
    try:
        h, w = stdscr.getmaxyx()
        stdscr.erase()
        exit_msg = "Exiting listener..."
        stdscr.addstr(h // 2, (w - len(exit_msg)) // 2, exit_msg)
        stdscr.refresh()
        time.sleep(1)
    except:
        pass # Abaikan error saat keluar


# --- Fungsi Menu Pengaturan (Menggunakan print biasa SEBELUM curses) ---
def show_settings_menu(settings):
    """Menampilkan dan mengedit pengaturan via menu teks biasa."""
    while True:
        # Gunakan print biasa karena ini sebelum curses aktif
        clear_screen()
        print(f"\033[1m\033[96m--- Pengaturan Email & Binance Listener ---\033[0m") # Bold Cyan
        print("\n--- Email Settings ---")
        print(f" 1. \033[96mAlamat Email\033[0m   : {settings['email_address'] or '[Belum diatur]'}")
        # Password tidak ditampilkan demi keamanan di log/screenshot
        print(f" 2. \033[96mApp Password\033[0m   : {'*' * len(settings['app_password']) if settings['app_password'] else '[Belum diatur]'}")
        print(f" 3. \033[96mServer IMAP\033[0m    : {settings['imap_server']}")
        print(f" 4. \033[96mInterval Cek\033[0m   : {settings['check_interval_seconds']} detik")
        print(f" 5. \033[96mKeyword Target\033[0m : {settings['target_keyword']}")
        print(f" 6. \033[96mKeyword Trigger\033[0m: {settings['trigger_keyword']}")

        print("\n--- Binance Settings ---")
        binance_status_color = "\033[92m" if BINANCE_AVAILABLE else "\033[91m" # Green or Red
        binance_status = f"{binance_status_color}{'Tersedia' if BINANCE_AVAILABLE else 'Tidak Tersedia (Install python-binance)'}\033[0m"
        print(f" Library Status      : {binance_status}")
        # API Keys tidak ditampilkan penuh
        api_key_display = settings['binance_api_key'][:5] + '...' if settings['binance_api_key'] else '[Belum diatur]'
        api_secret_display = settings['binance_api_secret'][:5] + '...' if settings['binance_api_secret'] else '[Belum diatur]'
        print(f" 7. \033[96mAPI Key\033[0m        : {api_key_display}")
        print(f" 8. \033[96mAPI Secret\033[0m     : {api_secret_display}")
        print(f" 9. \033[96mTrading Pair\033[0m   : {settings['trading_pair'] or '[Belum diatur]'}")
        print(f"10. \033[96mBuy Quote Qty\033[0m  : {settings['buy_quote_quantity']} (e.g., USDT)")
        print(f"11. \033[96mSell Base Qty\033[0m  : {settings['sell_base_quantity']} (e.g., BTC)")
        exec_status_color = "\033[92m" if settings['execute_binance_orders'] else "\033[91m" # Green or Red
        exec_status = f"{exec_status_color}{'Aktif' if settings['execute_binance_orders'] else 'Nonaktif'}\033[0m"
        print(f"12. \033[96mEksekusi Order\033[0m : {exec_status}")
        print("-" * 30)

        print("\nOpsi:")
        print(f" \033[93mE\033[0m - Edit Pengaturan")
        print(f" \033[93mK\033[0m - Kembali ke Menu Utama")
        print("-" * 30)

        choice = input("Pilih opsi (E/K): ").lower().strip()

        if choice == 'e':
            print(f"\n\033[1m\033[95m--- Edit Pengaturan ---\033[0m") # Bold Magenta
            # --- Edit Email ---
            print(f"\033[96m--- Email ---\033[0m")
            new_val = input(f" 1. Email [{settings['email_address']}]: ").strip()
            if new_val: settings['email_address'] = new_val
            # Gunakan getpass untuk menyembunyikan input password
            prompt = f" 2. App Password ({'masukkan ulang' if settings['app_password'] else 'baru'}): "
            new_pass = getpass.getpass(prompt).strip()
            if new_pass: settings['app_password'] = new_pass

            new_val = input(f" 3. Server IMAP [{settings['imap_server']}]: ").strip()
            if new_val: settings['imap_server'] = new_val
            while True:
                new_val_str = input(f" 4. Interval (detik) [{settings['check_interval_seconds']}], min 5: ").strip()
                if not new_val_str: break
                try:
                    new_interval = int(new_val_str)
                    if new_interval >= 5: settings['check_interval_seconds'] = new_interval; break
                    else: print(f"   \033[91m[ERROR] Interval minimal 5 detik.\033[0m")
                except ValueError: print(f"   \033[91m[ERROR] Masukkan angka.\033[0m")
            new_val = input(f" 5. Keyword Target [{settings['target_keyword']}]: ").strip()
            if new_val: settings['target_keyword'] = new_val
            new_val = input(f" 6. Keyword Trigger [{settings['trigger_keyword']}]: ").strip()
            if new_val: settings['trigger_keyword'] = new_val

             # --- Edit Binance ---
            print(f"\n\033[96m--- Binance ---\033[0m")
            if not BINANCE_AVAILABLE:
                 print(f"\033[93m   (Library Binance tidak terinstall, pengaturan Binance mungkin tidak berpengaruh)\033[0m")

            prompt_key = f" 7. API Key ({'masukkan ulang' if settings['binance_api_key'] else 'baru'}): "
            new_key = input(prompt_key).strip()
            if new_key: settings['binance_api_key'] = new_key

            prompt_secret = f" 8. API Secret ({'masukkan ulang' if settings['binance_api_secret'] else 'baru'}): "
            # Gunakan getpass untuk secret key
            new_secret = getpass.getpass(prompt_secret).strip()
            if new_secret: settings['binance_api_secret'] = new_secret

            new_val = input(f" 9. Trading Pair (e.g., BTCUSDT) [{settings['trading_pair']}]: ").strip().upper()
            if new_val: settings['trading_pair'] = new_val
            while True:
                 new_val_str = input(f"10. Buy Quote Qty (e.g., 11.0 USDT) [{settings['buy_quote_quantity']}], > 0: ").strip()
                 if not new_val_str: break
                 try:
                     new_qty = float(new_val_str)
                     if new_qty > 0: settings['buy_quote_quantity'] = new_qty; break
                     else: print(f"   \033[91m[ERROR] Kuantitas Beli harus > 0.\033[0m")
                 except ValueError: print(f"   \033[91m[ERROR] Masukkan angka desimal (e.g., 11.0).\033[0m")
            while True:
                 new_val_str = input(f"11. Sell Base Qty (e.g., 0.0005 BTC) [{settings['sell_base_quantity']}], >= 0: ").strip()
                 if not new_val_str: break
                 try:
                     new_qty = float(new_val_str)
                     if new_qty >= 0: settings['sell_base_quantity'] = new_qty; break
                     else: print(f"   \033[91m[ERROR] Kuantitas Jual harus >= 0.\033[0m")
                 except ValueError: print(f"   \033[91m[ERROR] Masukkan angka desimal (e.g., 0.0005).\033[0m")
            while True:
                 current_exec = settings['execute_binance_orders']
                 exec_prompt_text = "Aktif" if current_exec else "Nonaktif"
                 new_val_str = input(f"12. Eksekusi Order Binance? (y/n) [{exec_prompt_text}]: ").lower().strip()
                 if not new_val_str: break
                 if new_val_str == 'y': settings['execute_binance_orders'] = True; break
                 elif new_val_str == 'n': settings['execute_binance_orders'] = False; break
                 else: print(f"   \033[91m[ERROR] Masukkan 'y' atau 'n'.\033[0m")

            save_settings(settings) # Simpan tanpa print status jika berhasil
            print(f"\n\033[92m[INFO] Pengaturan diperbarui.\033[0m")
            time.sleep(2)

        elif choice == 'k':
            break # Keluar dari loop pengaturan
        else:
            print(f"\033[91m[ERROR] Pilihan tidak valid. Coba lagi.\033[0m")
            time.sleep(1.5)

# --- Fungsi Menu Utama (Menggunakan print biasa SEBELUM curses) ---
def main_menu():
    """Menampilkan menu utama aplikasi."""
    settings = load_settings()

    while True:
        # Reset status info sebelum menampilkan menu
        global status_info
        status_info = { k: ("N/A" if k != "error_count" else 0) for k in status_info }
        status_info["mode"] = "Idle"
        status_info["listening"] = False

        clear_screen()
        # ANSI Colors for menu
        BOLD = "\033[1m"
        MAGENTA = "\033[95m"
        GREEN = "\033[92m"
        CYAN = "\033[96m"
        YELLOW = "\033[93m"
        RED = "\033[91m"
        RESET = "\033[0m"

        print(f"{BOLD}{MAGENTA}========================================{RESET}")
        print(f"{BOLD}{MAGENTA}   Exora AI - Email & Binance Listener  {RESET}")
        print(f"{BOLD}{MAGENTA}========================================{RESET}")
        print("\nSilakan pilih opsi:\n")
        exec_mode_str = f" & {BOLD}Binance{RESET}" if settings.get("execute_binance_orders") else ""
        print(f" {GREEN}1.{RESET} Mulai Mendengarkan (Email{exec_mode_str})")
        print(f" {CYAN}2.{RESET} Pengaturan")
        print(f" {YELLOW}3.{RESET} Keluar")
        print("-" * 40)

        # Tampilkan status konfigurasi penting
        email_status = f"{GREEN}OK{RESET}" if settings['email_address'] else f"{RED}X{RESET}"
        pass_status = f"{GREEN}OK{RESET}" if settings['app_password'] else f"{RED}X{RESET}"
        api_status = f"{GREEN}OK{RESET}" if settings['binance_api_key'] else f"{RED}X{RESET}"
        secret_status = f"{GREEN}OK{RESET}" if settings['binance_api_secret'] else f"{RED}X{RESET}"
        pair_status = f"{GREEN}{settings['trading_pair']}{RESET}" if settings['trading_pair'] else f"{RED}X{RESET}"
        exec_mode = f"{GREEN}AKTIF{RESET}" if settings['execute_binance_orders'] else f"{YELLOW}NONAKTIF{RESET}"

        print(f" Status Email : [{email_status}] Email | [{pass_status}] App Pass")
        print(f" Status Binance: [{api_status}] API | [{secret_status}] Secret | [{pair_status}] Pair | Eksekusi [{exec_mode}]")
        print(f" Library Binance: {'OK' if BINANCE_AVAILABLE else f'{RED}Tidak Ada{RESET}'}")
        print("-" * 40)

        choice = input("Masukkan pilihan Anda (1/2/3): ").strip()

        if choice == '1':
            # Validasi sebelum memulai
            valid_email = settings['email_address'] and settings['app_password']
            execute_binance = settings.get("execute_binance_orders")
            # Binance valid jika eksekusi aktif & semua field terisi & qty > 0
            valid_binance = (settings['binance_api_key']
                             and settings['binance_api_secret']
                             and settings['trading_pair']
                             and settings['buy_quote_quantity'] > 0
                             and settings['sell_base_quantity'] > 0) # Perlu sell > 0 jika mau sell
            valid_binance_config = valid_binance if execute_binance else True # Hanya validasi jika eksekusi aktif

            if not valid_email:
                print(f"\n{RED}[ERROR] Pengaturan Email (Alamat/App Password) belum lengkap!{RESET}")
                print(f"{YELLOW}         Silakan masuk ke menu 'Pengaturan' (pilihan 2).{RESET}")
                time.sleep(4)
            elif execute_binance and not BINANCE_AVAILABLE:
                 print(f"\n{RED}[ERROR] Eksekusi Binance aktif tapi library 'python-binance' tidak ditemukan!{RESET}")
                 print(f"{YELLOW}         Install library ('pip install python-binance') atau nonaktifkan eksekusi di Pengaturan.{RESET}")
                 time.sleep(4)
            elif execute_binance and not valid_binance_config:
                 print(f"\n{RED}[ERROR] Eksekusi Binance aktif tapi Pengaturan Binance belum lengkap/valid!{RESET}")
                 if not settings['binance_api_key'] or not settings['binance_api_secret']: print(f"{YELLOW}         -> API Key/Secret belum diatur.{RESET}")
                 if not settings['trading_pair']: print(f"{YELLOW}         -> Trading Pair belum diatur.{RESET}")
                 if not settings['buy_quote_quantity'] > 0: print(f"{YELLOW}         -> Buy Quote Qty harus > 0.{RESET}")
                 if not settings['sell_base_quantity'] > 0: print(f"{YELLOW}         -> Sell Base Qty harus > 0 untuk eksekusi Sell.{RESET}")
                 print(f"{YELLOW}         Silakan periksa menu 'Pengaturan' (pilihan 2).{RESET}")
                 time.sleep(5)
            else:
                # Siap memulai - panggil wrapper curses
                global running, ui_stop_event
                running = True
                ui_stop_event.clear() # Pastikan event stop direset
                try:
                    # --- CURSES ---: Jalankan fungsi utama UI di dalam wrapper
                    wrapper(curses_main, settings)
                except curses.error as e:
                    # Jika curses gagal (misal terminal tidak support), keluar dengan pesan
                    print(f"\n{RED}Curses Error: {e}{RESET}")
                    print(f"{YELLOW}Tidak dapat menjalankan UI Curses. Pastikan terminal Anda mendukungnya.")
                    print(f"{YELLOW}(Untuk Windows, pastikan 'windows-curses' terinstall: pip install windows-curses){RESET}")
                except Exception as e:
                    print(f"\n{RED}Unexpected error starting UI: {e}{RESET}")
                    traceback.print_exc()

                print(f"\n{YELLOW}[INFO] Listener dihentikan. Kembali ke Menu Utama...{RESET}")
                running = False # Pastikan status running false setelah keluar dari curses
                time.sleep(2)

        elif choice == '2':
            show_settings_menu(settings)
            settings = load_settings() # Load ulang jika ada perubahan
        elif choice == '3':
            print(f"\n{CYAN}Terima kasih! Sampai jumpa!{RESET}")
            sys.exit(0)
        else:
            print(f"\n{RED}[ERROR] Pilihan tidak valid. Masukkan 1, 2, atau 3.{RESET}")
            time.sleep(1.5)

# --- Utility clear screen (digunakan sebelum curses) ---
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

# --- Entry Point ---
if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        # Signal handler sudah diatur, jadi ini mungkin tidak akan tercapai
        # kecuali jika terjadi sebelum signal handler terpasang
        print(f"\n{YELLOW}[WARN] Program dihentikan paksa (Interrupt).{RESET}")
        sys.exit(1)
    except Exception as e:
        # Tangkap error kritis yang mungkin terjadi di luar loop utama/curses
        print(f"\n{BOLD}{RED}===== CRITICAL ERROR ====={RESET}")
        traceback.print_exc()
        print(f"\n{RED}Terjadi error kritis yang tidak tertangani: {e}{RESET}")
        print("Program akan keluar.")
        # Coba cleanup curses jika masih aktif (jarang terjadi di sini)
        if 'stdscr' in globals() and globals()['stdscr'] is not None:
            try: curses.endwin()
            except: pass
        sys.exit(1)
