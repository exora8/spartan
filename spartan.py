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
import shutil # Untuk mendapatkan lebar terminal (opsional)

# --- Inquirer Integration ---
try:
    import inquirer
    # Coba tema lain yg mungkin lebih simpel atau kontras di Termux
    # from inquirer.themes import Default as InquirerTheme
    from inquirer.themes import GreenPassion as InquirerTheme # Tetap pakai ini dulu
    INQUIRER_AVAILABLE = True
except ImportError:
    INQUIRER_AVAILABLE = False
    print("\n!!! WARNING: Library 'inquirer' tidak ditemukan. !!!")
    print("!!!          Menu akan menggunakan input teks biasa.     !!!")
    print("!!!          Install dengan: pip install inquirer       !!!\n")
    time.sleep(3)
    # Definisikan dummy theme jika inquirer tidak ada
    class InquirerTheme: pass

# --- Binance Integration ---
# (Kode Binance Integration tetap sama)
try:
    from binance.client import Client
    import requests # Ditambahkan untuk menangani network error spesifik Binance
    from binance.exceptions import BinanceAPIException, BinanceOrderException
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False
    print("\n!!! WARNING: Library 'python-binance' tidak ditemukan. !!!")
    print("!!!          Fitur eksekusi order Binance tidak akan berfungsi. !!!")
    print("!!!          Install dengan: pip install python-binance requests !!!\n") # Tambah requests
    class BinanceAPIException(Exception): pass
    class BinanceOrderException(Exception): pass
    class Client:
        SIDE_BUY = 'BUY'
        SIDE_SELL = 'SELL'
        ORDER_TYPE_MARKET = 'MARKET'
    # Definisikan dummy requests jika binance tidak ada tapi script jalan
    if 'requests' not in sys.modules:
        class requests:
            class exceptions:
                RequestException = Exception

# --- Konfigurasi & Variabel Global ---
# (Konfigurasi & Variabel Global tetap sama)
CONFIG_FILE = "config.json"
DEFAULT_SETTINGS = {
    "email_address": "", "app_password": "", "imap_server": "imap.gmail.com",
    "check_interval_seconds": 10, "target_keyword": "Exora AI", "trigger_keyword": "order",
    "binance_api_key": "", "binance_api_secret": "", "trading_pair": "BTCUSDT",
    "buy_quote_quantity": 11.0, "sell_base_quantity": 0.0, "execute_binance_orders": False
}
running = True

# --- Kode Warna ANSI ---
# (Kode Warna ANSI tetap sama)
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"

# --- Fungsi Penanganan Sinyal (Ctrl+C) ---
# (Signal Handler tetap sama)
def signal_handler(sig, frame):
    global running
    print(f"\n{YELLOW}{BOLD}[WARN] Ctrl+C terdeteksi. Menghentikan program...{RESET}")
    running = False
    time.sleep(1.5)
    print(f"{RED}{BOLD}[EXIT] Keluar dari program.{RESET}")
    sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)

# --- Fungsi Utilitas (Termasuk Helper Tampilan) ---
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def get_terminal_width(default=70):
    """Mencoba mendapatkan lebar terminal, fallback ke default."""
    try:
        # Berfungsi di Linux/macOS, mungkin perlu penyesuaian untuk Windows
        return shutil.get_terminal_size(fallback=(default, 24)).columns
    except Exception:
        return default

def print_centered(text, color=RESET, style=BOLD):
    """Mencetak teks di tengah terminal."""
    width = get_terminal_width()
    padding = (width - len(text)) // 2
    print(f"{' ' * padding}{style}{color}{text}{RESET}")

def print_header(title):
    """Mencetak header menu yang lebih menarik."""
    width = get_terminal_width()
    print(f"\n{BOLD}{MAGENTA}╭{'─' * (width - 2)}╮{RESET}")
    print_centered(title, MAGENTA, BOLD)
    print(f"{BOLD}{MAGENTA}╰{'─' * (width - 2)}╯{RESET}")

def print_separator(char='─', color=DIM):
    """Mencetak garis pemisah."""
    width = get_terminal_width()
    print(f"{color}{char * width}{RESET}")

# --- Fungsi Konfigurasi ---
# (load_settings & save_settings tetap sama)
def load_settings():
    """Memuat pengaturan dari file JSON, memastikan semua kunci ada."""
    settings = DEFAULT_SETTINGS.copy() # Mulai dengan default
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_settings = json.load(f)
                valid_keys = set(DEFAULT_SETTINGS.keys())
                filtered_settings = {k: v for k, v in loaded_settings.items() if k in valid_keys}
                settings.update(filtered_settings) # Timpa default dengan yg dari file

                # Validasi tambahan (minimal)
                if not isinstance(settings.get("check_interval_seconds", 10), int) or settings.get("check_interval_seconds") < 5:
                    settings["check_interval_seconds"] = 10
                if not isinstance(settings.get("buy_quote_quantity"), (int, float)) or settings.get("buy_quote_quantity") <= 0:
                    settings["buy_quote_quantity"] = DEFAULT_SETTINGS['buy_quote_quantity']
                if not isinstance(settings.get("sell_base_quantity"), (int, float)) or settings.get("sell_base_quantity") < 0:
                    settings["sell_base_quantity"] = DEFAULT_SETTINGS['sell_base_quantity']
                if not isinstance(settings.get("execute_binance_orders"), bool):
                    settings["execute_binance_orders"] = False

                # Save back jika ada koreksi atau penambahan default key
                current_settings_in_file = json.dumps({k: loaded_settings.get(k) for k in DEFAULT_SETTINGS if k in loaded_settings}, sort_keys=True)
                potentially_corrected_settings = json.dumps({k: settings.get(k, DEFAULT_SETTINGS[k]) for k in DEFAULT_SETTINGS}, sort_keys=True)
                if current_settings_in_file != potentially_corrected_settings:
                     save_settings(settings) # Save hanya jika ada perbedaan

        except json.JSONDecodeError:
            print(f"{RED}[ERROR] File konfigurasi '{CONFIG_FILE}' rusak. Menggunakan default & menyimpan ulang.{RESET}")
            save_settings(settings)
        except Exception as e:
            print(f"{RED}[ERROR] Gagal memuat konfigurasi: {e}{RESET}")
    else:
        print(f"{YELLOW}[INFO] File konfigurasi '{CONFIG_FILE}' tidak ditemukan. Membuat dengan nilai default.{RESET}")
        save_settings(settings)
    return settings

def save_settings(settings):
    """Menyimpan pengaturan ke file JSON."""
    try:
        # Pastikan tipe data benar sebelum menyimpan
        settings['check_interval_seconds'] = int(settings.get('check_interval_seconds', DEFAULT_SETTINGS['check_interval_seconds']))
        settings['buy_quote_quantity'] = float(settings.get('buy_quote_quantity', DEFAULT_SETTINGS['buy_quote_quantity']))
        settings['sell_base_quantity'] = float(settings.get('sell_base_quantity', DEFAULT_SETTINGS['sell_base_quantity']))
        settings['execute_binance_orders'] = bool(settings.get('execute_binance_orders', DEFAULT_SETTINGS['execute_binance_orders']))

        settings_to_save = {k: settings.get(k, DEFAULT_SETTINGS[k]) for k in DEFAULT_SETTINGS}

        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings_to_save, f, indent=2, sort_keys=True) # Indent 2 untuk file lebih kecil
        # Pesan sukses simpan biasanya dipanggil setelah user edit, bukan saat load
    except Exception as e:
        print(f"{RED}[ERROR] Gagal menyimpan konfigurasi: {e}{RESET}")


# --- Fungsi Utilitas Email & Beep ---
# (decode_mime_words, get_text_from_email, trigger_beep tetap sama)
def decode_mime_words(s):
    if not s: return ""
    try:
        decoded_parts = decode_header(s)
        result = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(encoding or 'utf-8', errors='replace'))
            else:
                result.append(str(part))
        return "".join(result)
    except Exception: return str(s) if isinstance(s, str) else "[DecodeErr]"

def get_text_from_email(msg):
    text_content = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdisp = str(part.get("Content-Disposition"))
            if ctype == "text/plain" and "attachment" not in cdisp.lower():
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    if payload: text_content += payload.decode(charset, errors='replace') + "\n"
                except Exception: pass # Abaikan bagian yg error decode
    else:
        if msg.get_content_type() == "text/plain":
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                if payload: text_content = payload.decode(charset, errors='replace')
            except Exception: pass
    return " ".join(text_content.split()).lower()

def trigger_beep(action):
    try:
        prefix = f"{MAGENTA}{BOLD}[ACTION]{RESET}"
        if action == "buy":
            print(f"{prefix} Beep 'BUY'")
            subprocess.run(["beep", "-f", "1000", "-l", "300"], check=True, capture_output=True)
            time.sleep(0.1)
            subprocess.run(["beep", "-f", "1200", "-l", "200"], check=True, capture_output=True)
        elif action == "sell":
            print(f"{prefix} Beep 'SELL'")
            subprocess.run(["beep", "-f", "700", "-l", "500"], check=True, capture_output=True)
        else: print(f"{YELLOW}[WARN] Aksi beep '{action}' tidak dikenal.{RESET}")
    except FileNotFoundError:
        print(f"{YELLOW}[WARN] Perintah 'beep' tidak ditemukan. {DIM}(Coba: pkg install beep){RESET}")
    except Exception: pass # Jangan crash jika beep error

# --- Fungsi Eksekusi Binance ---
# (get_binance_client & execute_binance_order tetap sama, mungkin sedikit penyesuaian pesan)
def get_binance_client(settings):
    """Membuat instance Binance client."""
    if not BINANCE_AVAILABLE: return None
    api_key = settings.get('binance_api_key')
    api_secret = settings.get('binance_api_secret')
    if not api_key or not api_secret:
        print(f"{RED}[!] Kunci API Binance belum diatur.{RESET}")
        return None
    try:
        print(f"{CYAN}[...] Menghubungkan ke Binance API...{RESET}")
        client = Client(api_key, api_secret)
        client.ping()
        print(f"{GREEN}[OK] Koneksi Binance API berhasil.{RESET}")
        return client
    except (BinanceAPIException, BinanceOrderException) as e:
        print(f"{RED}{BOLD}[X] Gagal koneksi/autentikasi Binance!{RESET}")
        print(f"{RED}    └─ Error {e.status_code}/{e.code}: {e.message}{RESET}")
        if "timestamp" in str(e.message).lower(): print(f"{YELLOW}       ↳ Periksa sinkronisasi waktu HP/PC Anda.{RESET}")
        if "signature" in str(e.message).lower() or "invalid key" in str(e.message).lower(): print(f"{YELLOW}       ↳ Periksa API Key/Secret.{RESET}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"{RED}{BOLD}[X] Gagal menghubungi Binance API (Network Error)!{RESET}")
        print(f"{RED}    └─ {e}{RESET}")
        print(f"{YELLOW}       ↳ Periksa koneksi internet.{RESET}")
        return None
    except Exception as e:
        print(f"{RED}{BOLD}[X] Error tidak dikenal saat membuat Binance client:{RESET}")
        print(f"{RED}    └─ {e}{RESET}")
        # traceback.print_exc() # Aktifkan jika perlu debug detail
        return None

def execute_binance_order(client, settings, side):
    """Mengeksekusi order MARKET BUY atau SELL di Binance."""
    if not client: return False # Sudah ada pesan error dari get_client
    if not settings.get("execute_binance_orders", False): return False # Safety check

    pair = settings.get('trading_pair', '').upper()
    if not pair:
        print(f"{RED}[!] Trading pair belum diatur.{RESET}")
        return False

    order_details = {}
    action_desc = ""
    qty = 0
    is_buy = side == Client.SIDE_BUY

    try:
        if is_buy:
            qty = settings.get('buy_quote_quantity', 0.0)
            if qty <= 0: print(f"{RED}[!] Kuantitas Beli ({qty}) harus > 0.{RESET}"); return False
            order_details = {'symbol': pair, 'side': side, 'type': Client.ORDER_TYPE_MARKET, 'quoteOrderQty': qty}
            action_desc = f"BUY {qty} USDT senilai {pair}" # Asumsi quote = USDT
        else: # SELL
            qty = settings.get('sell_base_quantity', 0.0)
            if qty <= 0: print(f"{YELLOW}[!] Kuantitas Jual ({qty}) <= 0. Order dilewati.{RESET}"); return False # Info, bukan error fatal
            order_details = {'symbol': pair, 'side': side, 'type': Client.ORDER_TYPE_MARKET, 'quantity': qty}
            action_desc = f"SELL {qty} {pair.replace('USDT', '')}" # Asumsi base

        print(f"{MAGENTA}{BOLD}[ACTION]{RESET} Eksekusi Binance: {action_desc}...")
        order_result = client.create_order(**order_details)

        print(f"{GREEN}{BOLD}[SUCCESS]{RESET} Order {side} {pair} berhasil!")
        # Tampilkan info penting saja
        filled_qty = float(order_result.get('executedQty', 0))
        filled_quote_qty = float(order_result.get('cummulativeQuoteQty', 0))
        avg_price = filled_quote_qty / filled_qty if filled_qty else 0
        print(f"  {DIM}├─ ID     : {order_result.get('orderId')}{RESET}")
        print(f"  {DIM}├─ Status : {order_result.get('status')}{RESET}")
        if filled_qty > 0:
            print(f"  {DIM}├─ Terisi : {filled_qty:.8f} {pair.replace('USDT', '')}{RESET}")
            print(f"  {DIM}└─ Harga Avg: {avg_price:.4f} USDT{RESET}") # Asumsi USDT

        return True

    except (BinanceAPIException, BinanceOrderException) as e:
        print(f"{RED}{BOLD}[X] Gagal eksekusi order Binance!{RESET}")
        print(f"{RED}    └─ Error {e.status_code}/{e.code}: {e.message}{RESET}")
        # Error umum
        if e.code == -2010: print(f"{YELLOW}       ↳ Saldo tidak cukup?{RESET}")
        elif e.code == -1121: print(f"{YELLOW}       ↳ Pair '{pair}' tidak valid?{RESET}")
        elif e.code in [-1013, -2015] or 'MIN_NOTIONAL' in str(e.message): print(f"{YELLOW}       ↳ Nilai order terlalu kecil? (Cek MIN_NOTIONAL){RESET}")
        elif e.code == -1111 or 'LOT_SIZE' in str(e.message): print(f"{YELLOW}       ↳ Kuantitas tidak sesuai LOT_SIZE?{RESET}")
        return False
    except requests.exceptions.RequestException as e:
         print(f"{RED}{BOLD}[X] Gagal mengirim order (Network Error)!{RESET}")
         print(f"{RED}    └─ {e}{RESET}")
         return False
    except Exception as e:
        print(f"{RED}{BOLD}[X] Error tidak dikenal saat eksekusi order:{RESET}")
        print(f"{RED}    └─ {e}{RESET}")
        # traceback.print_exc()
        return False

# --- Fungsi Pemrosesan Email ---
# (process_email tetap sama, mungkin penyesuaian pesan log)
def process_email(mail, email_id, settings, binance_client):
    global running
    if not running: return

    target_kw = settings['target_keyword'].lower()
    trigger_kw = settings['trigger_keyword'].lower()
    email_id_str = email_id.decode('utf-8')
    log_prefix = f"[{BLUE}EMAIL {email_id_str}{RESET}]"

    try:
        status, data = mail.fetch(email_id, "(RFC822)")
        if status != 'OK':
            print(f"{log_prefix} {RED}Gagal fetch: {status}{RESET}")
            return

        msg = email.message_from_bytes(data[0][1])
        subject = decode_mime_words(msg["Subject"])
        sender = decode_mime_words(msg["From"])
        timestamp = datetime.datetime.now().strftime("%H:%M") # Waktu lebih ringkas

        print(f"\n{CYAN}╭─ Email Baru [{timestamp}] {'─'*15}{RESET}")
        print(f"{CYAN}│{RESET} {DIM}ID    :{RESET} {email_id_str}")
        print(f"{CYAN}│{RESET} {DIM}Dari  :{RESET} {sender[:40]}{'...' if len(sender)>40 else ''}") # Batasi panjang sender
        print(f"{CYAN}│{RESET} {DIM}Subjek:{RESET} {subject[:50]}{'...' if len(subject)>50 else ''}") # Batasi panjang subjek
        # print(f"{CYAN}╰{'─' * 30}{RESET}") # Footer sementara sebelum proses body

        body = get_text_from_email(msg)
        full_content = (subject.lower() + " " + body)

        if target_kw in full_content:
            print(f"{CYAN}│{RESET} {GREEN}[✓] Target '{settings['target_keyword']}' ditemukan.{RESET}")
            try:
                target_idx = full_content.find(target_kw)
                trigger_idx = full_content.find(trigger_kw, target_idx + len(target_kw))

                if trigger_idx != -1:
                    text_after = full_content[trigger_idx + len(trigger_kw):].lstrip()
                    action_word = text_after.split(maxsplit=1)[0].strip('.,!?:;()[]{}').lower() if text_after else ""

                    if action_word in ["buy", "sell"]:
                        print(f"{CYAN}│{RESET} {GREEN}[✓] Trigger '{settings['trigger_keyword']}' -> Aksi: {BOLD}{action_word.upper()}{RESET}")
                        # --- Trigger Aksi ---
                        execute_binance = settings.get("execute_binance_orders", False)
                        order_attempted = False

                        if action_word == "buy":
                            trigger_beep("buy")
                            if execute_binance and binance_client:
                                order_attempted = execute_binance_order(binance_client, settings, Client.SIDE_BUY)
                        elif action_word == "sell":
                            trigger_beep("sell")
                            # Cek Qty > 0 sebelum mencoba eksekusi
                            if settings.get('sell_base_quantity', 0) > 0:
                                if execute_binance and binance_client:
                                    order_attempted = execute_binance_order(binance_client, settings, Client.SIDE_SELL)
                            # else: # Info jika qty 0 sudah ada di execute_binance_order
                            #    print(f"{CYAN}│{RESET} {YELLOW}[i] Aksi Sell, tapi Qty=0. Order dilewati.{RESET}")

                        # Warning jika eksekusi aktif tapi client bermasalah atau Qty=0 untuk sell
                        if execute_binance and not order_attempted:
                            if not binance_client:
                                 print(f"{CYAN}│{RESET} {YELLOW}[!] Eksekusi aktif, tapi koneksi Binance bermasalah.{RESET}")
                            # Kasus lain (misal qty 0 untuk sell) sudah ditangani di execute_binance_order
                    elif action_word:
                        print(f"{CYAN}│{RESET} {YELLOW}[?] Trigger ditemukan, tapi kata '{action_word}' bukan 'buy'/'sell'.{RESET}")
                    else:
                        print(f"{CYAN}│{RESET} {YELLOW}[?] Trigger ditemukan, tapi tidak ada kata aksi setelahnya.{RESET}")
                else:
                     print(f"{CYAN}│{RESET} {YELLOW}[?] Target ditemukan, tapi trigger '{settings['trigger_keyword']}' tidak ada SETELAHNYA.{RESET}")
            except Exception as e:
                 print(f"{CYAN}│{RESET} {RED}[X] Error parsing setelah trigger: {e}{RESET}")
        else:
             print(f"{CYAN}│{RESET} {BLUE}[-] Target '{settings['target_keyword']}' tidak ditemukan.{RESET}")

        # Tandai sudah dibaca
        try:
            mail.store(email_id, '+FLAGS', '\\Seen')
            print(f"{CYAN}│{RESET} {DIM}Email ditandai sudah dibaca.{RESET}")
        except Exception as e:
            print(f"{CYAN}│{RESET} {RED}[X] Gagal tandai dibaca: {e}{RESET}")

        print(f"{CYAN}╰{'─' * (get_terminal_width() - 1)}{RESET}") # Footer akhir

    except Exception as e:
        print(f"{log_prefix} {RED}{BOLD}FATAL Error proses email:{RESET}")
        traceback.print_exc()

# --- Fungsi Listening Utama ---
# (start_listening perlu penyesuaian pesan log dan waiting indicator)
def start_listening(settings):
    global running
    running = True
    mail = None
    binance_client = None
    last_check_time = time.time()
    consecutive_errors = 0
    max_errors = 5
    wait_time = 2
    long_wait = 60

    # --- Setup Binance (jika aktif) ---
    execute_binance = settings.get("execute_binance_orders", False)
    if execute_binance:
        if not BINANCE_AVAILABLE:
            print(f"{RED}{BOLD}[X] FATAL: Eksekusi Binance aktif tapi library tidak ada!{RESET}")
            print(f"{DIM}   (Install: pip install python-binance requests){RESET}")
            running = False; return
        print_separator('─', CYAN)
        print_centered("Inisialisasi Binance", CYAN, BOLD)
        binance_client = get_binance_client(settings)
        if not binance_client:
            print(f"{YELLOW}[!] Gagal koneksi awal Binance. Eksekusi order tidak akan jalan.{RESET}")
            print(f"{YELLOW}    Program lanjut untuk Email saja.{RESET}")
        print_separator('─', CYAN)
        time.sleep(1) # Jeda sedikit

    elif BINANCE_AVAILABLE: # Beri info jika library ada tapi fitur nonaktif
         print_separator('─', YELLOW)
         print_centered("Eksekusi Binance: NONAKTIF", YELLOW, BOLD)
         print(f"{DIM}   (Mode Email Listener Only. Aktifkan di Pengaturan jika perlu){RESET}")
         print_separator('─', YELLOW)
         time.sleep(1)

    # --- Loop Utama ---
    print(f"\n{GREEN}{BOLD}Memulai listener... (Ctrl+C untuk berhenti){RESET}")
    wait_indicator_chars = ['∙', '·', '˙', ' '] # Karakter indikator tunggu
    indicator_idx = 0

    while running:
        try:
            # --- Koneksi IMAP ---
            if not mail or mail.state != 'SELECTED':
                print(f"\n{CYAN}[...] Menghubungkan ke IMAP {settings['imap_server']}...{RESET}")
                try:
                    mail = imaplib.IMAP4_SSL(settings['imap_server'], timeout=20) # Timeout lebih pendek
                    rv, desc = mail.login(settings['email_address'], settings['app_password'])
                    if rv != 'OK': raise imaplib.IMAP4.error(f"Login failed: {desc}")
                    mail.select("inbox")
                    print(f"{GREEN}[OK] Terhubung & Login ke {settings['email_address']}. Mendengarkan...{RESET}")
                    consecutive_errors = 0; wait_time = 2 # Reset error & wait time
                except (imaplib.IMAP4.error, OSError, socket.error) as login_err:
                    print(f"{RED}{BOLD}[X] Gagal koneksi/login IMAP!{RESET}")
                    print(f"{RED}    └─ {login_err}{RESET}")
                    if "authentication failed" in str(login_err).lower():
                         print(f"{YELLOW}       ↳ Periksa Email/App Password & Izin IMAP.{RESET}")
                         running = False # Berhenti jika otentikasi gagal
                    else:
                        print(f"{YELLOW}       ↳ Periksa server IMAP & koneksi internet.{RESET}")
                        consecutive_errors += 1
                    mail = None # Pastikan state bersih
                    # Jangan langsung break, biarkan loop luar handle backoff/exit

            # --- Loop Cek Email & Koneksi ---
            if mail and mail.state == 'SELECTED':
                while running:
                    current_time = time.time()
                    if current_time - last_check_time < settings['check_interval_seconds']:
                        time.sleep(0.5)
                        continue

                    # NOOP Check
                    try:
                        status, _ = mail.noop()
                        if status != 'OK': raise imaplib.IMAP4.abort("NOOP Failed")
                    except (imaplib.IMAP4.abort, imaplib.IMAP4.readonly, BrokenPipeError, OSError) as noop_err:
                        print(f"\n{YELLOW}[!] Koneksi IMAP terputus ({type(noop_err).__name__}). Reconnecting...{RESET}")
                        try: mail.logout()
                        except Exception: pass
                        mail = None; consecutive_errors += 1
                        break # Keluar loop inner, reconnect di loop luar

                    # Binance Ping Check (lebih jarang)
                    if binance_client and current_time - getattr(binance_client, '_last_ping', 0) > 60:
                         try:
                             binance_client.ping()
                             setattr(binance_client, '_last_ping', current_time)
                         except Exception:
                             print(f"\n{YELLOW}[!] Ping Binance gagal. Mencoba reconnect Binance...{RESET}")
                             binance_client = get_binance_client(settings) # Coba buat ulang
                             setattr(binance_client, '_last_ping', current_time) # Update waktu coba

                    # Cek Email UNSEEN
                    status, messages = mail.search(None, '(UNSEEN)')
                    if status != 'OK':
                         print(f"\n{RED}[X] Gagal cari email UNSEEN: {status}. Reconnecting...{RESET}")
                         try: mail.close(); mail.logout()
                         except Exception: pass
                         mail = None; consecutive_errors += 1
                         break # Reconnect

                    email_ids = messages[0].split()
                    if email_ids:
                        num = len(email_ids)
                        print(f"\n{GREEN}{BOLD}[!] {num} email baru ditemukan!{RESET}")
                        for i, eid in enumerate(email_ids):
                            if not running: break
                            # print(f"{DIM}--- Proses email {i+1}/{num} ---{RESET}") # Opsi: lebih detail
                            process_email(mail, eid, settings, binance_client)
                        if not running: break
                        print(f"{GREEN}[OK] Selesai proses {num} email. Mendengarkan lagi...{RESET}")
                    else:
                        # Tampilkan indikator tunggu
                        indicator_idx = (indicator_idx + 1) % len(wait_indicator_chars)
                        wait_char = wait_indicator_chars[indicator_idx]
                        print(f"{BLUE}[{wait_char}] Menunggu email baru... {DIM}(Interval: {settings['check_interval_seconds']}s){RESET}   ", end='\r')

                    last_check_time = current_time
                    if not running: break # Cek lagi sebelum tidur

                # Keluar loop inner (jika running=False atau ada error)
                if mail and mail.state == 'SELECTED': # Coba close jika state masih selected
                   try: mail.close()
                   except Exception: pass

        # --- Exception Handling Loop Luar ---
        except (imaplib.IMAP4.error, imaplib.IMAP4.abort, socket.error, OSError) as e:
             print(f"\n{RED}{BOLD}[X] Error IMAP/Network di loop utama: {e}{RESET}")
             consecutive_errors += 1
             # Jika error login sudah ditangani di atas, ini lebih ke koneksi
        except Exception as e:
             print(f"\n{RED}{BOLD}[X] Error tak terduga di loop utama:{RESET}")
             traceback.print_exc()
             consecutive_errors += 1

        finally:
            if mail and mail.state != 'LOGOUT': # Logout jika belum
                try: mail.logout()
                except Exception: pass
            mail = None # Pastikan reconnect

            if not running: break # Keluar jika dihentikan

            # Backoff logic
            if consecutive_errors > 0:
                current_wait = wait_time * (2**(consecutive_errors-1)) # Exponential backoff
                current_wait = min(current_wait, long_wait) # Batasi maks wait time
                print(f"{YELLOW}[!] Terjadi error ({consecutive_errors}x). Mencoba lagi dalam {current_wait} detik...{RESET}")
                sleep_start = time.time()
                while time.time() - sleep_start < current_wait:
                     if not running: break # Bisa diinterupsi saat tidur
                     time.sleep(1)
                if not running: break
            else:
                 time.sleep(0.5) # Jeda normal antar loop utama jika tidak error

    print(f"\n{YELLOW}{BOLD}[INFO] Listener dihentikan.{RESET}")


# --- Fungsi Menu Pengaturan (MODIFIED for Termux) ---
def show_settings(settings):
    while True:
        clear_screen()
        print_header("Pengaturan")

        print(f"\n{BOLD}{CYAN} E M A I L {RESET}")
        print(f"{DIM}─────────────────────────────{RESET}")
        print(f" {CYAN}1. Alamat Email{RESET}   : {settings['email_address'] or f'{DIM}[Kosong]{RESET}'}")
        app_pass_disp = f"{GREEN}Terisi{RESET}" if settings['app_password'] else f"{RED}Kosong{RESET}"
        print(f" {CYAN}2. App Password{RESET}   : {app_pass_disp} {DIM}(Input tersembunyi saat edit){RESET}")
        print(f" {CYAN}3. Server IMAP{RESET}    : {settings['imap_server']}")
        print(f" {CYAN}4. Interval Cek{RESET}   : {settings['check_interval_seconds']} detik")
        print(f" {CYAN}5. Keyword Target{RESET} : '{settings['target_keyword']}'")
        print(f" {CYAN}6. Keyword Trigger{RESET}: '{settings['trigger_keyword']}'")

        print(f"\n{BOLD}{CYAN} B I N A N C E {RESET}")
        print(f"{DIM}─────────────────────────────{RESET}")
        if BINANCE_AVAILABLE:
            print(f" {DIM}Library Status{RESET}   : {GREEN}Terinstall{RESET}")
            api_key_disp = f"{GREEN}Terisi{RESET}" if settings['binance_api_key'] else f"{RED}Kosong{RESET}"
            api_sec_disp = f"{GREEN}Terisi{RESET}" if settings['binance_api_secret'] else f"{RED}Kosong{RESET}"
            print(f" {CYAN}7. API Key{RESET}        : {api_key_disp} {DIM}(Hidden Input){RESET}")
            print(f" {CYAN}8. API Secret{RESET}     : {api_sec_disp} {DIM}(Hidden Input){RESET}")
            print(f" {CYAN}9. Trading Pair{RESET}   : {settings['trading_pair'] or f'{DIM}[Kosong]{RESET}'}")
            buy_qty_valid = settings.get('buy_quote_quantity', 0) > 0
            sell_qty_valid = settings.get('sell_base_quantity', 0) >= 0
            print(f" {CYAN}10. Buy Quote Qty{RESET} : {settings['buy_quote_quantity']} {GREEN if buy_qty_valid else RED}[{'+' if buy_qty_valid else '!'}] {DIM}(USDT){RESET}")
            print(f" {CYAN}11. Sell Base Qty{RESET} : {settings['sell_base_quantity']} {GREEN if sell_qty_valid else RED}[{'+' if sell_qty_valid else '!'}] {DIM}(BTC/Base){RESET}")
            exec_status = f"{GREEN}{BOLD}Aktif{RESET}" if settings['execute_binance_orders'] else f"{YELLOW}Nonaktif{RESET}"
            print(f" {CYAN}12. Eksekusi Order{RESET}  : {exec_status}")
        else:
             print(f" {DIM}Library Status{RESET}   : {RED}Tidak Terinstall{RESET}")
             print(f" {DIM}(Install: pip install python-binance requests){RESET}")

        print_separator(color=MAGENTA)

        # --- Opsi Menu Pengaturan ---
        if INQUIRER_AVAILABLE:
            questions = [
                inquirer.List('action',
                              message=f"{YELLOW}Pilih Aksi{RESET}",
                              choices=[
                                  ('✏️  Edit Pengaturan', 'edit'),
                                  ('💾 Simpan & Kembali', 'back'), # Otomatis simpan saat kembali
                                  # ('<binary data, 1 bytes><binary data, 1 bytes><binary data, 1 bytes> Kembali Tanpa Simpan', 'cancel') # Opsi jika perlu cancel
                              ],
                              carousel=True)
            ]
            try:
                 answers = inquirer.prompt(questions, theme=InquirerTheme()) # Gunakan theme
                 choice = answers['action'] if answers else 'back'
            except Exception as e:
                 print(f"{RED}Error menu: {e}{RESET}"); choice = 'back'
            except KeyboardInterrupt:
                 print(f"\n{YELLOW}Edit dibatalkan.{RESET}"); choice = 'back'; time.sleep(1)
        else: # Fallback
             choice_input = input("Pilih (E=Edit, K=Kembali): ").lower().strip()
             choice = 'edit' if choice_input == 'e' else 'back'

        # --- Proses Pilihan ---
        if choice == 'edit':
            print(f"\n{BOLD}{MAGENTA}--- Edit Pengaturan ---{RESET}")
            print(f"{DIM}(Kosongkan input untuk skip){RESET}")

            # Edit Email (tetap pakai input, getpass untuk password)
            print(f"\n{CYAN}--- Email ---{RESET}")
            if val := input(f" 1. Email [{settings['email_address']}]: ").strip(): settings['email_address'] = val
            print(f" 2. App Password (input tersembunyi): ", end='', flush=True)
            try: pwd = getpass.getpass("")
            except Exception: pwd = input(" App Password [***]: ").strip()
            if pwd: settings['app_password'] = pwd; print(f"{GREEN}OK{RESET}")
            else: print(f"{DIM}Skip{RESET}")
            if val := input(f" 3. IMAP Server [{settings['imap_server']}]: ").strip(): settings['imap_server'] = val
            while True:
                val_str = input(f" 4. Interval (detik) [{settings['check_interval_seconds']}], min 5: ").strip()
                if not val_str: break
                try:
                    iv = int(val_str)
                    if iv >= 5: settings['check_interval_seconds'] = iv; break
                    else: print(f"{RED}[!] Min 5 detik.{RESET}")
                except ValueError: print(f"{RED}[!] Angka bulat.{RESET}")
            if val := input(f" 5. Keyword Target [{settings['target_keyword']}]: ").strip(): settings['target_keyword'] = val
            if val := input(f" 6. Keyword Trigger [{settings['trigger_keyword']}]: ").strip(): settings['trigger_keyword'] = val

            # Edit Binance (tetap pakai input, getpass untuk secret)
            print(f"\n{CYAN}--- Binance ---{RESET}")
            if not BINANCE_AVAILABLE: print(f"{YELLOW}(Library tidak ada){RESET}")
            if val := input(f" 7. API Key [***]: ").strip(): settings['binance_api_key'] = val
            print(f" 8. API Secret (input tersembunyi): ", end='', flush=True)
            try: sec = getpass.getpass("")
            except Exception: sec = input(" API Secret [***]: ").strip()
            if sec: settings['binance_api_secret'] = sec; print(f"{GREEN}OK{RESET}")
            else: print(f"{DIM}Skip{RESET}")
            if val := input(f" 9. Trading Pair [{settings['trading_pair']}]: ").strip().upper(): settings['trading_pair'] = val
            while True: # Buy Qty
                 val_str = input(f"10. Buy Quote Qty [{settings['buy_quote_quantity']}], > 0: ").strip()
                 if not val_str: break
                 try:
                     qty = float(val_str)
                     if qty > 0: settings['buy_quote_quantity'] = qty; break
                     else: print(f"{RED}[!] Harus > 0.{RESET}")
                 except ValueError: print(f"{RED}[!] Angka desimal.{RESET}")
            while True: # Sell Qty
                 val_str = input(f"11. Sell Base Qty [{settings['sell_base_quantity']}], >= 0: ").strip()
                 if not val_str: break
                 try:
                     qty = float(val_str)
                     if qty >= 0: settings['sell_base_quantity'] = qty; break
                     else: print(f"{RED}[!] Harus >= 0.{RESET}")
                 except ValueError: print(f"{RED}[!] Angka desimal.{RESET}")
            while True: # Execute Toggle
                 curr = settings['execute_binance_orders']
                 prompt = f"{GREEN}Aktif{RESET}" if curr else f"{YELLOW}Nonaktif{RESET}"
                 val_str = input(f"12. Eksekusi Order? ({prompt}) [y/n]: ").lower().strip()
                 if not val_str: break
                 if val_str == 'y':
                     if BINANCE_AVAILABLE: settings['execute_binance_orders'] = True; break
                     else: print(f"{RED}[!] Library Binance tidak ada!{RESET}"); break
                 elif val_str == 'n': settings['execute_binance_orders'] = False; break
                 else: print(f"{RED}[!] y/n saja.{RESET}")

            # Simpan otomatis setelah edit selesai
            save_settings(settings)
            print(f"\n{GREEN}{BOLD}[OK] Pengaturan disimpan!{RESET}")
            input(f"{DIM}Tekan Enter untuk kembali...{RESET}")
            # Loop akan kembali ke awal show_settings untuk menampilkan nilai baru

        elif choice == 'back':
            save_settings(settings) # Simpan perubahan terakhir sebelum kembali
            print(f"\n{GREEN}Pengaturan disimpan. Kembali ke Menu Utama...{RESET}")
            time.sleep(1.5)
            break # Keluar dari loop pengaturan

# --- Fungsi Menu Utama (MODIFIED for Termux) ---
def main_menu():
    settings = load_settings() # Muat sekali di awal

    while True:
        clear_screen()
        print_header("Exora AI - Email & Binance Listener")

        # --- Tampilkan Status Ringkas ---
        print(f"\n{BOLD}{CYAN} S T A T U S {RESET}")
        print(f"{DIM}─────────────────────────────{RESET}")

        # Email Status
        email_ok = bool(settings.get('email_address'))
        pass_ok = bool(settings.get('app_password'))
        print(f" {CYAN}Email:{RESET}")
        print(f"   ├─ Config: [{GREEN if email_ok else RED}{'✓' if email_ok else 'X'}{RESET}] Email | [{GREEN if pass_ok else RED}{'✓' if pass_ok else 'X'}{RESET}] App Pass")
        print(f"   └─ Server: {settings.get('imap_server', '?')}")

        # Binance Status
        print(f" {CYAN}Binance:{RESET}")
        if BINANCE_AVAILABLE:
            lib_status = f"{GREEN}✓ Terinstall{RESET}"
            api_ok = bool(settings.get('binance_api_key'))
            sec_ok = bool(settings.get('binance_api_secret'))
            pair_ok = bool(settings.get('trading_pair'))
            buy_qty_ok = settings.get('buy_quote_quantity', 0) > 0
            sell_qty_ok = settings.get('sell_base_quantity', 0) >= 0 # Boleh 0
            exec_active = settings.get("execute_binance_orders", False)
            exec_status = f"{GREEN}{BOLD}AKTIF{RESET}" if exec_active else f"{YELLOW}NONAKTIF{RESET}"

            print(f"   ├─ Library : {lib_status}")
            print(f"   ├─ Akun    : API [{GREEN if api_ok else RED}{'✓' if api_ok else 'X'}{RESET}] | Secret [{GREEN if sec_ok else RED}{'✓' if sec_ok else 'X'}{RESET}] | Pair [{GREEN if pair_ok else RED}{settings.get('trading_pair', 'X')}{RESET}]")
            print(f"   ├─ Qty     : Buy [{GREEN if buy_qty_ok else RED}{'✓' if buy_qty_ok else '!'}{RESET}] | Sell [{GREEN if sell_qty_ok else RED}{'✓' if sell_qty_ok else '!'}{RESET}]")
            print(f"   └─ Eksekusi: {exec_status}")
        else:
            lib_status = f"{RED}X Tidak Terinstall{RESET}"
            print(f"   └─ Library : {lib_status} {DIM}(Fitur Binance nonaktif){RESET}")

        print_separator(color=MAGENTA)

        # --- Pilihan Menu Utama ---
        menu_prompt = f"{YELLOW}Pilih Menu {DIM}(↑/↓ Enter){RESET}" if INQUIRER_AVAILABLE else f"{YELLOW}Ketik Pilihan:{RESET}"

        if INQUIRER_AVAILABLE:
            choices = []
            # Opsi Mulai
            start_label = f"▶️  Mulai Listener"
            start_mode = ""
            if BINANCE_AVAILABLE and settings.get("execute_binance_orders"):
                start_mode = f" {DIM}(Email & {BOLD}Binance{DIM}){RESET}"
            else:
                start_mode = f" {DIM}(Email Only){RESET}"
            choices.append((start_label + start_mode, 'start'))
            # Opsi Pengaturan
            choices.append(('⚙️  Pengaturan', 'settings'))
            # Opsi Keluar
            choices.append(('🚪 Keluar', 'exit'))

            questions = [inquirer.List('main_choice', message=menu_prompt, choices=choices, carousel=True)]
            try:
                answers = inquirer.prompt(questions, theme=InquirerTheme())
                choice_key = answers['main_choice'] if answers else 'exit'
            except Exception as e: print(f"{RED}Menu error: {e}{RESET}"); choice_key = 'exit'
            except KeyboardInterrupt: print(f"\n{YELLOW}Keluar...{RESET}"); choice_key = 'exit'; time.sleep(1)
        else: # Fallback
            print(f"\n{menu_prompt}")
            print(f" 1. Mulai Listener")
            print(f" 2. Pengaturan")
            print(f" 3. Keluar")
            print_separator(color=MAGENTA)
            choice_input = input("Pilihan (1/2/3): ").strip()
            choice_map = {'1': 'start', '2': 'settings', '3': 'exit'}
            choice_key = choice_map.get(choice_input, 'invalid')

        # --- Proses Pilihan ---
        if choice_key == 'start':
            print_separator()
            # Validasi sebelum memulai (sedikit lebih ringkas)
            errors = []
            if not settings.get('email_address') or not settings.get('app_password'):
                errors.append("Email/App Password belum lengkap.")
            execute_binance = settings.get("execute_binance_orders", False)
            if execute_binance:
                if not BINANCE_AVAILABLE: errors.append("Library Binance tidak ada (Nonaktifkan eksekusi atau install).")
                else:
                    if not settings.get('binance_api_key'): errors.append("Binance API Key kosong.")
                    if not settings.get('binance_api_secret'): errors.append("Binance API Secret kosong.")
                    if not settings.get('trading_pair'): errors.append("Binance Trading Pair kosong.")
                    if settings.get('buy_quote_quantity', 0) <= 0: errors.append("Binance Buy Qty harus > 0.")
                    # Tidak perlu error jika sell qty 0, itu valid
                    # if settings.get('sell_base_quantity', 0) <= 0: errors.append("Binance Sell Qty harus > 0.")

            if errors:
                print(f"\n{BOLD}{RED}--- TIDAK BISA MEMULAI ---{RESET}")
                for i, err in enumerate(errors): print(f" {RED}{i+1}. {err}{RESET}")
                print(f"\n{YELLOW}Perbaiki di menu 'Pengaturan'.{RESET}")
                input(f"{DIM}Tekan Enter untuk kembali...{RESET}")
            else:
                clear_screen()
                mode = "Email & Binance Order" if execute_binance and BINANCE_AVAILABLE else "Email Listener Only"
                print_header(f"Memulai Mode: {mode}")
                start_listening(settings)
                # Setelah listener berhenti (Ctrl+C atau error fatal), kembali ke menu
                print(f"\n{YELLOW}[INFO] Kembali ke Menu Utama...{RESET}")
                time.sleep(2)

        elif choice_key == 'settings':
            show_settings(settings)
            settings = load_settings() # Muat ulang setelah dari settings

        elif choice_key == 'exit':
            print(f"\n{CYAN}Terima kasih! Sampai jumpa lagi 👋{RESET}")
            sys.exit(0)

        elif choice_key == 'invalid': # Hanya untuk fallback
            print(f"{RED}[!] Pilihan tidak valid.{RESET}")
            time.sleep(1)

# --- Entry Point ---
if __name__ == "__main__":
    if sys.version_info < (3, 6):
        print("Error: Butuh Python 3.6+"); sys.exit(1)
    try:
        main_menu()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Program dihentikan paksa.{RESET}"); sys.exit(1)
    except Exception as e:
        clear_screen()
        print(f"\n{BOLD}{RED}===== ERROR KRITIS TAK TERDUGA ====={RESET}")
        traceback.print_exc()
        print(f"\n{RED}Error: {e}{RESET}")
        input("Tekan Enter untuk keluar...")
        sys.exit(1)
