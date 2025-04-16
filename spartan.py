# -*- coding: utf-8 -*-
import imaplib
import email
from email.header import decode_header
import time
import datetime # Untuk timestamp
import subprocess
import json
import os
import getpass # Masih digunakan untuk input password di edit (opsional)
import sys
import signal # Untuk menangani Ctrl+C
import traceback # Untuk mencetak traceback error
import socket # Untuk error koneksi
import shutil # Untuk mendapatkan lebar terminal

# --- Library TUI ---
try:
    from simple_term_menu import TerminalMenu
    TUI_AVAILABLE = True
except ImportError:
    TUI_AVAILABLE = False
    print("\n!!! WARNING: Library 'simple-term-menu' tidak ditemukan. !!!")
    print("!!!          Tampilan menu interaktif tidak akan berfungsi. !!!")
    print("!!!          Install dengan: pip install simple-term-menu    !!!\n")
    # Exit jika TUI tidak ada, karena jadi inti perubahan
    sys.exit("Error: simple-term-menu diperlukan. Silakan install dan coba lagi.")

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
    class Client: pass # Dummy class

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

# Variabel global untuk mengontrol loop utama
running = True

# --- Kode Warna ANSI ---
RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
UNDERLINE = "\033[4m"

# --- Fungsi Penanganan Sinyal (Ctrl+C) ---
def signal_handler(sig, frame):
    global running
    print(f"\n{YELLOW}{BOLD}[WARN] Ctrl+C terdeteksi. Menghentikan proses...{RESET}")
    running = False
    # Beri sedikit waktu jika ada proses I/O yang berjalan
    time.sleep(0.5)
    # Clear screen sebelum keluar agar terminal bersih
    clear_screen()
    print(f"{RED}{BOLD}[EXIT] Keluar dari program.{RESET}")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# --- Fungsi Utilitas ---
def clear_screen():
    """Membersihkan layar terminal."""
    os.system('cls' if os.name == 'nt' else 'clear')

def get_terminal_width(default=80):
    """Mendapatkan lebar terminal saat ini."""
    try:
        return shutil.get_terminal_size().columns
    except Exception:
        return default

def print_centered(text, color=RESET, style=BOLD):
    """Mencetak teks di tengah layar."""
    width = get_terminal_width()
    padding = (width - len(text)) // 2
    print(f"{' ' * padding}{style}{color}{text}{RESET}")

def print_separator(char="=", color=MAGENTA, style=BOLD):
    """Mencetak garis pemisah selebar layar."""
    width = get_terminal_width()
    print(f"{style}{color}{char * width}{RESET}")

# --- Fungsi Konfigurasi (Load/Save tetap sama, hanya pesan output disesuaikan) ---
def load_settings():
    """Memuat pengaturan dari file JSON, memastikan semua kunci ada."""
    settings = DEFAULT_SETTINGS.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_settings = json.load(f)
                settings.update(loaded_settings)

                # Validasi (pesan mungkin ditampilkan saat startup atau di menu)
                if settings.get("check_interval_seconds", 10) < 5:
                    # print(f"{YELLOW}[WARN] Interval cek di '{CONFIG_FILE}' < 5 detik, direset ke 10.{RESET}")
                    settings["check_interval_seconds"] = 10
                if not isinstance(settings.get("buy_quote_quantity"), (int, float)) or settings.get("buy_quote_quantity") <= 0:
                    settings["buy_quote_quantity"] = DEFAULT_SETTINGS['buy_quote_quantity']
                if not isinstance(settings.get("sell_base_quantity"), (int, float)) or settings.get("sell_base_quantity") < 0:
                    settings["sell_base_quantity"] = DEFAULT_SETTINGS['sell_base_quantity']
                if not isinstance(settings.get("execute_binance_orders"), bool):
                    settings["execute_binance_orders"] = False

                # Save back any corrections silently if needed on load
                save_settings(settings, silent=True)

        except json.JSONDecodeError:
            print(f"{RED}{BOLD}[ERROR] File konfigurasi '{CONFIG_FILE}' rusak! Menggunakan default.{RESET}")
            save_settings(settings)
            time.sleep(3)
        except Exception as e:
            print(f"{RED}{BOLD}[ERROR] Gagal memuat konfigurasi: {e}{RESET}")
            time.sleep(3)
            # Tidak menyimpan ulang jika error tidak diketahui
    else:
        # Jika file tidak ada, simpan default awal
        print(f"{YELLOW}[INFO] File konfigurasi '{CONFIG_FILE}' tidak ditemukan. Membuat dengan nilai default.{RESET}")
        save_settings(settings)
        time.sleep(2)
    return settings

def save_settings(settings, silent=False):
    """Menyimpan pengaturan ke file JSON."""
    try:
        settings['check_interval_seconds'] = int(settings.get('check_interval_seconds', 10))
        settings['buy_quote_quantity'] = float(settings.get('buy_quote_quantity', 11.0))
        settings['sell_base_quantity'] = float(settings.get('sell_base_quantity', 0.0))
        settings['execute_binance_orders'] = bool(settings.get('execute_binance_orders', False))

        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings, f, indent=4, sort_keys=True)
        if not silent:
            print(f"\n{GREEN}{BOLD}[INFO] Pengaturan berhasil disimpan ke '{CONFIG_FILE}'{RESET}")
            time.sleep(1.5)
    except Exception as e:
        if not silent:
            print(f"\n{RED}{BOLD}[ERROR] Gagal menyimpan konfigurasi: {e}{RESET}")
            time.sleep(2)

# --- Fungsi Decode & Parse Email (Tidak diubah) ---
def decode_mime_words(s):
    if not s:
        return ""
    decoded_parts = decode_header(s)
    result = []
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            try:
                result.append(part.decode(encoding or 'utf-8', errors='replace'))
            except LookupError: # Handle unknown encoding
                result.append(part.decode('utf-8', errors='replace'))
        else:
            result.append(part)
    return "".join(result)

def get_text_from_email(msg):
    text_content = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    text_content += payload.decode(charset, errors='replace')
                except Exception as e:
                    print(f"{YELLOW}[WARN] Tidak bisa mendekode bagian email: {e}{RESET}")
    else:
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                text_content = payload.decode(charset, errors='replace')
            except Exception as e:
                 print(f"{YELLOW}[WARN] Tidak bisa mendekode body email: {e}{RESET}")
    return text_content.lower()

# --- Fungsi Beep (Tidak diubah) ---
def trigger_beep(action):
    # ... (fungsi trigger_beep tetap sama) ...
    try:
        cmd = []
        if action == "buy":
            print(f"{MAGENTA}[ACTION] Memicu BEEP untuk '{BOLD}BUY{RESET}{MAGENTA}'{RESET}")
            cmd = ["beep", "-f", "1000", "-l", "500", "-D", "500", "-r", "5"]
        elif action == "sell":
            print(f"{MAGENTA}[ACTION] Memicu BEEP untuk '{BOLD}SELL{RESET}{MAGENTA}'{RESET}")
            cmd = ["beep", "-f", "700", "-l", "1000", "-D", "500", "-r", "2"]
        else:
             print(f"{YELLOW}[WARN] Aksi beep tidak dikenal '{action}'.{RESET}")
             return

        # Gunakan subprocess.run dengan timeout dan handle output
        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=10) # Timeout 10 detik
        if result.returncode != 0:
             print(f"{RED}[ERROR] Perintah 'beep' gagal (code: {result.returncode}).{RESET}")
             if result.stderr: print(f"{RED}         Stderr: {result.stderr.strip()}{RESET}")

    except FileNotFoundError:
        print(f"{YELLOW}[WARN] Perintah 'beep' tidak ditemukan. Beep dilewati.{RESET}")
    except subprocess.TimeoutExpired:
        print(f"{YELLOW}[WARN] Perintah 'beep' timeout.{RESET}")
    except Exception as e:
        print(f"{RED}[ERROR] Kesalahan tak terduga saat beep: {e}{RESET}")

# --- Fungsi Eksekusi Binance (Log disesuaikan sedikit) ---
def get_binance_client(settings):
    """Membuat instance Binance client."""
    if not BINANCE_AVAILABLE:
        print(f"{RED}{BOLD}[FATAL] Library python-binance tidak terinstall.{RESET}")
        return None
    if not settings.get('binance_api_key') or not settings.get('binance_api_secret'):
        print(f"{RED}{BOLD}[ERROR] API Key/Secret Binance belum diatur.{RESET}")
        return None
    try:
        # Sembunyikan output client saat inisialisasi jika perlu
        # client = Client(settings['binance_api_key'], settings['binance_api_secret'], requests_params={"timeout": 15}) # Tambah timeout
        client = Client(settings['binance_api_key'], settings['binance_api_secret'])
        client.ping() # Test koneksi
        print(f"{GREEN}[BINANCE] Koneksi API Binance {BOLD}BERHASIL{RESET}")
        return client
    except (BinanceAPIException, BinanceOrderException) as e:
        print(f"{RED}{BOLD}[BINANCE ERROR] Gagal konek/auth: {e}{RESET}")
        return None
    except requests.exceptions.ConnectionError:
         print(f"{RED}{BOLD}[NETWORK ERROR] Gagal terhubung ke Binance. Cek internet.{RESET}")
         return None
    except Exception as e:
        print(f"{RED}{BOLD}[ERROR] Gagal membuat Binance client: {e}{RESET}")
        traceback.print_exc()
        return None

def execute_binance_order(client, settings, side):
    """Mengeksekusi order MARKET BUY atau SELL di Binance."""
    if not client:
        print(f"{RED}[BINANCE] Eksekusi dibatalkan: client tidak valid.{RESET}")
        return False
    if not settings.get("execute_binance_orders", False):
        print(f"{YELLOW}[BINANCE] Eksekusi order dinonaktifkan di config. Dilewati.{RESET}")
        return False # Dianggap tidak gagal, hanya dilewati

    pair = settings.get('trading_pair', '').upper()
    if not pair:
        print(f"{RED}{BOLD}[BINANCE ERROR] Trading pair belum diatur!{RESET}")
        return False

    order_details = {}
    action_desc = ""

    try:
        if side == Client.SIDE_BUY:
            quote_qty = settings.get('buy_quote_quantity', 0.0)
            if quote_qty <= 0:
                 print(f"{RED}{BOLD}[BINANCE ERROR] Kuantitas Beli (buy_quote_quantity) harus > 0.{RESET}")
                 return False
            order_details = {'symbol': pair, 'side': Client.SIDE_BUY, 'type': Client.ORDER_TYPE_MARKET, 'quoteOrderQty': quote_qty}
            action_desc = f"MARKET BUY {quote_qty} (quote) of {pair}"

        elif side == Client.SIDE_SELL:
            base_qty = settings.get('sell_base_quantity', 0.0)
            if base_qty <= 0:
                 print(f"{RED}{BOLD}[BINANCE ERROR] Kuantitas Jual (sell_base_quantity) harus > 0 untuk eksekusi SELL.{RESET}")
                 return False
            order_details = {'symbol': pair, 'side': Client.SIDE_SELL, 'type': Client.ORDER_TYPE_MARKET, 'quantity': base_qty}
            action_desc = f"MARKET SELL {base_qty} (base) of {pair}"
        else:
            print(f"{RED}{BOLD}[BINANCE ERROR] Sisi order tidak valid: {side}{RESET}")
            return False

        print(f"{MAGENTA}{BOLD}[BINANCE] Mencoba eksekusi: {action_desc}...{RESET}")
        start_time = time.time()
        # Gunakan test order jika ingin menguji tanpa eksekusi nyata
        # order_result = client.create_test_order(**order_details)
        order_result = client.create_order(**order_details)
        end_time = time.time()
        print(f"{GREEN}{BOLD}[BINANCE SUCCESS] Order {side} berhasil dieksekusi! ({end_time - start_time:.2f} detik){RESET}")
        print(f"  {CYAN}Order ID : {order_result.get('orderId')}{RESET}")
        print(f"  {CYAN}Symbol   : {order_result.get('symbol')}{RESET}")
        print(f"  {CYAN}Status   : {order_result.get('status')}{RESET}")

        if order_result.get('fills'):
            total_qty = sum(float(f['qty']) for f in order_result['fills'])
            total_quote_qty = sum(float(f['commission']) if f['commissionAsset'] == settings['trading_pair'].replace('USDT','') else float(f['qty']) * float(f['price']) for f in order_result['fills']) # Hitung nilai quote
            avg_price = total_quote_qty / total_qty if total_qty else 0
            print(f"  {CYAN}Avg Price: {avg_price:.8f}{RESET}") # Sesuaikan presisi
            print(f"  {CYAN}Filled Qty: {total_qty:.8f}{RESET}")
        return True

    except BinanceAPIException as e:
        print(f"{RED}{BOLD}[BINANCE API ERROR] Gagal eksekusi: {e.status_code} - {e.message}{RESET}")
        if e.code == -2010: print(f"{RED}         -> Kemungkinan saldo tidak cukup.{RESET}")
        elif e.code == -1121: print(f"{RED}         -> Trading pair '{pair}' tidak valid.{RESET}")
        elif e.code == -1013 or 'MIN_NOTIONAL' in str(e.message): print(f"{RED}         -> Order size terlalu kecil (cek MIN_NOTIONAL/LOT_SIZE).{RESET}")
        return False
    except BinanceOrderException as e:
        print(f"{RED}{BOLD}[BINANCE ORDER ERROR] Gagal eksekusi: {e.status_code} - {e.message}{RESET}")
        return False
    except requests.exceptions.RequestException as e:
         print(f"{RED}{BOLD}[NETWORK ERROR] Gagal komunikasi dengan Binance: {e}{RESET}")
         return False
    except Exception as e:
        print(f"{RED}{BOLD}[ERROR] Kesalahan tak terduga saat eksekusi Binance: {e}{RESET}")
        traceback.print_exc()
        return False

# --- Fungsi Pemrosesan Email (Log disesuaikan sedikit) ---
def process_email(mail, email_id, settings, binance_client):
    """Mengambil, mem-parsing, dan memproses satu email, lalu eksekusi order jika sesuai."""
    global running
    if not running: return

    target_keyword_lower = settings['target_keyword'].lower()
    trigger_keyword_lower = settings['trigger_keyword'].lower()
    email_id_str = email_id.decode('utf-8')
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        status, data = mail.fetch(email_id, "(RFC822)")
        if status != 'OK':
            print(f"{RED}[ERROR][{timestamp}] Gagal fetch email ID {email_id_str}: {status}{RESET}")
            return

        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        subject = decode_mime_words(msg["Subject"])
        sender = decode_mime_words(msg["From"])

        print(f"\n{CYAN}{BOLD}--- Email Diterima [{timestamp}] ---{RESET}")
        print(f" ID     : {email_id_str}")
        print(f" Dari   : {sender}")
        print(f" Subjek : {subject}")

        body = get_text_from_email(msg)
        # Gabungkan subjek dan body untuk pencarian keyword yg lebih fleksibel
        full_content = (subject.lower() + " " + body)

        if target_keyword_lower in full_content:
            print(f"{GREEN}[MATCH] Keyword target '{BOLD}{settings['target_keyword']}{RESET}{GREEN}' ditemukan.{RESET}")
            try:
                # Cari trigger SETELAH target
                target_idx = full_content.find(target_keyword_lower)
                trigger_idx = full_content.find(trigger_keyword_lower, target_idx + len(target_keyword_lower))

                if trigger_idx != -1:
                    start_word_idx = trigger_idx + len(trigger_keyword_lower)
                    text_after_trigger = full_content[start_word_idx:].lstrip()
                    words_after_trigger = text_after_trigger.split(maxsplit=1)

                    if words_after_trigger:
                        action_word = words_after_trigger[0].strip('.,!?:;()[]{}').lower()
                        print(f"{GREEN}[TRIGGER] Keyword trigger '{BOLD}{settings['trigger_keyword']}{RESET}{GREEN}' ditemukan. Aksi: '{BOLD}{action_word.upper()}{RESET}{GREEN}'{RESET}")

                        # --- Trigger Aksi ---
                        order_executed = False
                        if action_word == "buy":
                            trigger_beep("buy")
                            if settings.get("execute_binance_orders"):
                                if binance_client:
                                    execute_binance_order(binance_client, settings, Client.SIDE_BUY)
                                    order_executed = True
                                else:
                                     print(f"{YELLOW}[WARN] Eksekusi Binance aktif tapi client tidak siap.{RESET}")
                            else:
                                print(f"{BLUE}[INFO] Eksekusi Binance nonaktif, aksi Beli tidak dieksekusi di market.{RESET}")


                        elif action_word == "sell":
                            trigger_beep("sell")
                            if settings.get("execute_binance_orders"):
                                if binance_client:
                                    execute_binance_order(binance_client, settings, Client.SIDE_SELL)
                                    order_executed = True
                                else:
                                     print(f"{YELLOW}[WARN] Eksekusi Binance aktif tapi client tidak siap.{RESET}")
                            else:
                                print(f"{BLUE}[INFO] Eksekusi Binance nonaktif, aksi Jual tidak dieksekusi di market.{RESET}")

                        else:
                            print(f"{YELLOW}[WARN] Kata setelah trigger '{action_word}' bukan 'buy'/'sell'. Tidak ada aksi market.{RESET}")

                    else:
                        print(f"{YELLOW}[WARN] Tidak ada kata setelah keyword trigger '{settings['trigger_keyword']}'.{RESET}")
                else:
                    print(f"{YELLOW}[WARN] Keyword trigger '{settings['trigger_keyword']}' tidak ditemukan SETELAH target.{RESET}")

            except Exception as e:
                 print(f"{RED}[ERROR] Gagal parsing setelah trigger: {e}{RESET}")
                 traceback.print_exc() # Tampilkan detail error parsing
        else:
            print(f"{BLUE}[INFO] Keyword target '{settings['target_keyword']}' tidak ditemukan.{RESET}")

        # Tandai email sebagai sudah dibaca ('Seen')
        try:
            # print(f"{BLUE}[INFO] Menandai email {email_id_str} sebagai 'Seen'.{RESET}")
            mail.store(email_id, '+FLAGS', '\\Seen')
        except Exception as e:
            print(f"{RED}[ERROR] Gagal menandai email {email_id_str} sbg 'Seen': {e}{RESET}")
        print(f"{CYAN}{BOLD}---------------------------------------{RESET}")

    except Exception as e:
        print(f"{RED}[ERROR] Gagal memproses email ID {email_id_str}:{RESET}")
        traceback.print_exc()

# --- Fungsi Listening Utama (Log disesuaikan) ---
def start_listening(settings):
    """Memulai loop untuk memeriksa email baru dan menyiapkan client Binance."""
    global running
    running = True
    mail = None
    binance_client = None
    wait_time = 30 # Waktu tunggu sebelum retry koneksi jika gagal
    consecutive_connection_errors = 0

    clear_screen()
    mode = f"Email & {BOLD}Binance Order{RESET}" if settings.get("execute_binance_orders") else "Email Listener Only"
    print_separator(char="*", color=GREEN)
    print_centered(f"MEMULAI MODE: {mode}", color=GREEN)
    print_separator(char="*", color=GREEN)
    print(f"\n{CYAN}[CONFIG] Interval Cek: {settings['check_interval_seconds']} detik")
    print(f"{CYAN}[CONFIG] Target Keyword: '{settings['target_keyword']}'")
    print(f"{CYAN}[CONFIG] Trigger Keyword: '{settings['trigger_keyword']}'")
    if settings.get("execute_binance_orders"):
        print(f"{CYAN}[CONFIG] Binance Pair: {settings['trading_pair']}")
        print(f"{CYAN}[CONFIG] Binance Buy Qty: {settings['buy_quote_quantity']} (Quote)")
        print(f"{CYAN}[CONFIG] Binance Sell Qty: {settings['sell_base_quantity']} (Base)")
        print(f"{GREEN}{BOLD}[CONFIG] Eksekusi Order Binance: AKTIF{RESET}")
    else:
        print(f"{YELLOW}[CONFIG] Eksekusi Order Binance: NONAKTIF{RESET}")
    print("")

    # --- Setup Binance Client di Awal (jika diaktifkan) ---
    if settings.get("execute_binance_orders"):
        if not BINANCE_AVAILABLE:
             print(f"{RED}{BOLD}[FATAL] Eksekusi Binance aktif tapi library python-binance tidak ada!{RESET}")
             running = False
             time.sleep(4)
             return
        print(f"{CYAN}[SYS] Menginisialisasi koneksi Binance API...{RESET}")
        binance_client = get_binance_client(settings)
        if not binance_client:
            print(f"{RED}{BOLD}[FATAL] Gagal inisialisasi Binance Client. Periksa API/Koneksi.{RESET}")
            print(f"{YELLOW}         Eksekusi order tidak akan berjalan. Nonaktifkan di Pengaturan jika hanya ingin notif email.{RESET}")
            # running = False # Hentikan jika koneksi awal gagal? Atau biarkan jalan untuk email? Biarkan jalan.
            # time.sleep(5)
            # return
        else:
            print(f"{GREEN}[SYS] Binance Client Siap.{RESET}")
    else:
        print(f"{BLUE}[INFO] Eksekusi order Binance dinonaktifkan.{RESET}")

    print_separator(char="-", color=BLUE)
    print(f"{CYAN}{BOLD}Memulai listener... Tekan Ctrl+C untuk berhenti.{RESET}")

    # --- Loop Utama Email Listener ---
    while running:
        try:
            # (Bagian koneksi IMAP)
            print(f"\n{BLUE}[IMAP] Menghubungkan ke {settings['imap_server']}...{RESET}", end='\r')
            mail = imaplib.IMAP4_SSL(settings['imap_server'], timeout=30) # Tambah timeout koneksi
            print(f"{GREEN}[IMAP] Terhubung ke {settings['imap_server']}. Login...{' '*20}{RESET}", end='\r')
            mail.login(settings['email_address'], settings['app_password'])
            print(f"{GREEN}{BOLD}[IMAP] Login berhasil: {settings['email_address']}{RESET}{' '*30}")
            mail.select("inbox")
            print(f"{GREEN}[INFO] Mendengarkan di INBOX...{RESET}")
            consecutive_connection_errors = 0 # Reset error counter on success

            # --- Loop Cek Email ---
            while running:
                try:
                    # Check koneksi IMAP (ringan)
                    status, _ = mail.noop()
                    if status != 'OK':
                        print(f"\n{YELLOW}[WARN] Koneksi IMAP NOOP gagal ({status}). Reconnecting...{RESET}")
                        break # Keluar loop cek, reconnect di loop luar
                    # Check koneksi Binance jika aktif (opsional, bisa memakan rate limit)
                    # if binance_client and settings.get("execute_binance_orders"):
                    #     try: binance_client.ping()
                    #     except Exception as PingErr:
                    #         print(f"\n{YELLOW}[WARN] Ping Binance gagal ({PingErr}). Mencoba re-init client...{RESET}")
                    #         binance_client = get_binance_client(settings) # Coba re-init

                except (imaplib.IMAP4.abort, imaplib.IMAP4.error, socket.error, OSError) as conn_err:
                     print(f"\n{YELLOW}[WARN] Koneksi IMAP terputus ({conn_err}). Reconnecting...{RESET}")
                     break # Keluar loop cek, reconnect di loop luar

                # Cek email UNSEEN
                status, messages = mail.search(None, '(UNSEEN)')
                if status != 'OK':
                     print(f"\n{RED}[ERROR] Gagal search email: {status}{RESET}")
                     break # Reconnect

                email_ids = messages[0].split()
                if email_ids:
                    print(f"\n{GREEN}{BOLD}[!] Menemukan {len(email_ids)} email baru! Memproses...{RESET}")
                    for email_id in email_ids:
                        if not running: break
                        process_email(mail, email_id, settings, binance_client)
                    if not running: break
                    print(f"{GREEN}--- Selesai proses batch. Kembali mendengarkan ---{RESET}")
                else:
                    # Tampilkan pesan tunggu yang rapi
                    wait_interval = settings['check_interval_seconds']
                    ts = datetime.datetime.now().strftime('%H:%M:%S')
                    print(f"{BLUE}[{ts}] No new emails. Checking again in {wait_interval}s... {RESET}        ", end='\r')
                    # Sleep dengan check `running` flag agar bisa stop cepat
                    for _ in range(wait_interval):
                         if not running: break
                         time.sleep(1)
                    if not running: break
                    # Hapus pesan tunggu sebelum cek berikutnya
                    print(" " * (get_terminal_width() -1) , end='\r')

            # --- End of Inner Loop ---
            if mail and mail.state == 'SELECTED':
                try: mail.close()
                except Exception: pass

        # (Exception Handling untuk Koneksi)
        except (imaplib.IMAP4.error, imaplib.IMAP4.abort) as e:
            print(f"\n{RED}{BOLD}[IMAP ERROR] {e}{RESET}")
            if "authentication failed" in str(e).lower() or "invalid credentials" in str(e).lower():
                print(f"{RED}{BOLD}[FATAL] Login Email GAGAL! Periksa email/App Password di config.{RESET}")
                running = False
                time.sleep(5)
                return
            consecutive_connection_errors += 1
            print(f"{YELLOW}[WARN] Mencoba menghubungkan kembali dlm {wait_time} detik... (Attempt: {consecutive_connection_errors}){RESET}")
            time.sleep(wait_time)
        except (ConnectionError, socket.error, socket.gaierror, TimeoutError, requests.exceptions.RequestException) as e:
             print(f"\n{RED}{BOLD}[NETWORK ERROR] {e}{RESET}")
             consecutive_connection_errors += 1
             print(f"{YELLOW}[WARN] Periksa koneksi internet. Mencoba lagi dlm {wait_time} detik... (Attempt: {consecutive_connection_errors}){RESET}")
             time.sleep(wait_time)
        except Exception as e:
            print(f"\n{RED}{BOLD}[UNEXPECTED ERROR] Loop Utama:{RESET}")
            traceback.print_exc()
            consecutive_connection_errors += 1
            print(f"{YELLOW}[WARN] Mencoba menghubungkan kembali dlm {wait_time} detik...{RESET}")
            time.sleep(wait_time)
        finally:
            if mail:
                try:
                    if mail.state != 'LOGOUT': mail.logout()
                    # print(f"{CYAN}[SYS] Logout IMAP.{RESET}") # Kurangi verbosity
                except Exception: pass
            mail = None # Pastikan mail direset

        if running and consecutive_connection_errors > 5: # Berhenti jika error terus menerus
            print(f"\n{RED}{BOLD}[FATAL] Terlalu banyak error koneksi berturut-turut. Program berhenti.{RESET}")
            running = False
        elif running:
            time.sleep(2) # Jeda singkat sebelum retry koneksi utama

    # --- End of Outer Loop ---
    clear_screen() # Bersihkan layar setelah listener berhenti
    print(f"{YELLOW}{BOLD}[INFO] Listener dihentikan.{RESET}")
    time.sleep(1)

# --- Fungsi Menu Pengaturan ---
def show_settings(settings):
    """Menampilkan dan mengedit pengaturan menggunakan menu interaktif."""
    while True:
        clear_screen()
        print_separator(char="=", color=CYAN)
        print_centered("PENGATURAN", color=CYAN)
        print_separator(char="=", color=CYAN)

        # Siapkan data untuk ditampilkan
        email_addr = settings['email_address'] or f"{RED}[Belum diatur]{RESET}"
        app_pass = f"{GREEN}[Sudah diatur]{RESET}" if settings['app_password'] else f"{RED}[Belum diatur]{RESET}"
        imap_srv = settings['imap_server']
        interval = f"{settings['check_interval_seconds']} detik"
        target_kw = settings['target_keyword']
        trigger_kw = settings['trigger_keyword']

        binance_lib_status = f"{GREEN}Tersedia{RESET}" if BINANCE_AVAILABLE else f"{RED}Tidak Tersedia (Install python-binance){RESET}"
        api_key = f"{GREEN}[Sudah diatur]{RESET}" if settings['binance_api_key'] else f"{RED}[Belum diatur]{RESET}"
        api_secret = f"{GREEN}[Sudah diatur]{RESET}" if settings['binance_api_secret'] else f"{RED}[Belum diatur]{RESET}"
        trading_pair = settings['trading_pair'] or f"{RED}[Belum diatur]{RESET}"
        buy_qty = f"{settings['buy_quote_quantity']} (e.g., USDT)"
        sell_qty = f"{settings['sell_base_quantity']} (e.g., BTC)"
        exec_status = f"{GREEN}Aktif{RESET}" if settings['execute_binance_orders'] else f"{RED}Nonaktif{RESET}"

        # Tampilkan dalam format yang lebih rapi
        print(f"\n{BOLD}{UNDERLINE}--- Email Settings ---{RESET}")
        print(f" {CYAN}1. Alamat Email{RESET}   : {email_addr}")
        print(f" {CYAN}2. App Password{RESET}   : {app_pass}")
        print(f" {CYAN}3. Server IMAP{RESET}    : {imap_srv}")
        print(f" {CYAN}4. Interval Cek{RESET}   : {interval}")
        print(f" {CYAN}5. Keyword Target{RESET} : {target_kw}")
        print(f" {CYAN}6. Keyword Trigger{RESET}: {trigger_kw}")

        print(f"\n{BOLD}{UNDERLINE}--- Binance Settings ---{RESET}")
        print(f" Library Status      : {binance_lib_status}")
        print(f" {CYAN}7. API Key{RESET}        : {api_key}")
        print(f" {CYAN}8. API Secret{RESET}     : {api_secret}")
        print(f" {CYAN}9. Trading Pair{RESET}   : {trading_pair}")
        print(f" {CYAN}10. Buy Quote Qty{RESET} : {buy_qty}")
        print(f" {CYAN}11. Sell Base Qty{RESET} : {sell_qty}")
        print(f" {CYAN}12. Eksekusi Order{RESET} : {exec_status}")
        print("-" * 30)

        menu_options = [
            "Edit Pengaturan Email",
            "Edit Pengaturan Binance",
            "Kembali ke Menu Utama"
        ]
        terminal_menu = TerminalMenu(
            menu_options,
            title="Pilih Aksi:",
            menu_cursor=f"{GREEN}> ",
            menu_cursor_style=("fg_green", "bold"),
            menu_highlight_style=("bg_green", "fg_black"),
            cycle_cursor=True,
            clear_screen=False # Biarkan layar yang sudah ada
        )
        selected_index = terminal_menu.show()

        if selected_index == 0: # Edit Email
            edit_email_settings(settings)
        elif selected_index == 1: # Edit Binance
            edit_binance_settings(settings)
        elif selected_index == 2 or selected_index is None: # Kembali atau Ctrl+C
            break # Keluar dari loop pengaturan
        else: # Pilihan tidak terduga
             print(f"{RED}{BOLD}[ERROR] Pilihan tidak valid.{RESET}")
             time.sleep(1)

def edit_email_settings(settings):
    """Fungsi untuk mengedit pengaturan email."""
    clear_screen()
    print_separator(char="-", color=MAGENTA)
    print_centered("EDIT PENGATURAN EMAIL", color=MAGENTA)
    print_separator(char="-", color=MAGENTA)
    print(f"{YELLOW}Tekan Enter untuk skip & gunakan nilai lama.{RESET}\n")

    try:
        # 1. Email
        current = settings['email_address']
        new_val = input(f" 1. Email [{current or 'Kosong'}]: ").strip()
        if new_val: settings['email_address'] = new_val

        # 2. App Password
        current_display = "[Sudah diatur]" if settings['app_password'] else "[Kosong]"
        new_val = getpass.getpass(f" 2. App Password (ketik baru jika ingin ganti) [{current_display}]: ").strip()
        if new_val: settings['app_password'] = new_val

        # 3. Server IMAP
        current = settings['imap_server']
        new_val = input(f" 3. Server IMAP [{current}]: ").strip()
        if new_val: settings['imap_server'] = new_val

        # 4. Interval Cek
        current = settings['check_interval_seconds']
        while True:
            new_val_str = input(f" 4. Interval (detik) [{current}], min 5: ").strip()
            if not new_val_str: break # Skip
            try:
                new_interval = int(new_val_str)
                if new_interval >= 5:
                    settings['check_interval_seconds'] = new_interval
                    break
                else: print(f"   {RED}[ERROR] Interval minimal 5 detik.{RESET}")
            except ValueError: print(f"   {RED}[ERROR] Masukkan angka bulat.{RESET}")

        # 5. Keyword Target
        current = settings['target_keyword']
        new_val = input(f" 5. Keyword Target [{current}]: ").strip()
        if new_val: settings['target_keyword'] = new_val

        # 6. Keyword Trigger
        current = settings['trigger_keyword']
        new_val = input(f" 6. Keyword Trigger [{current}]: ").strip()
        if new_val: settings['trigger_keyword'] = new_val

        save_settings(settings)

    except (KeyboardInterrupt, EOFError):
        print(f"\n{YELLOW}Edit dibatalkan.{RESET}")
        time.sleep(1)

def edit_binance_settings(settings):
    """Fungsi untuk mengedit pengaturan Binance."""
    clear_screen()
    print_separator(char="-", color=MAGENTA)
    print_centered("EDIT PENGATURAN BINANCE", color=MAGENTA)
    print_separator(char="-", color=MAGENTA)
    print(f"{YELLOW}Tekan Enter untuk skip & gunakan nilai lama.{RESET}\n")

    if not BINANCE_AVAILABLE:
         print(f"{YELLOW}{BOLD}   PERINGATAN: Library 'python-binance' tidak terinstall.{RESET}")
         print(f"{YELLOW}   Pengaturan ini mungkin tidak akan berfungsi sampai library diinstall.{RESET}\n")

    try:
        # 7. API Key
        current_display = "[Sudah diatur]" if settings['binance_api_key'] else "[Kosong]"
        new_val = input(f" 7. API Key [{current_display}]: ").strip()
        if new_val: settings['binance_api_key'] = new_val

        # 8. API Secret
        current_display = "[Sudah diatur]" if settings['binance_api_secret'] else "[Kosong]"
        # Pakai getpass untuk menyembunyikan secret
        new_val = getpass.getpass(f" 8. API Secret (ketik baru jika ingin ganti) [{current_display}]: ").strip()
        if new_val: settings['binance_api_secret'] = new_val

        # 9. Trading Pair
        current = settings['trading_pair']
        new_val = input(f" 9. Trading Pair (e.g., BTCUSDT) [{current or 'Kosong'}]: ").strip().upper()
        if new_val: settings['trading_pair'] = new_val

        # 10. Buy Quote Qty
        current = settings['buy_quote_quantity']
        while True:
            new_val_str = input(f"10. Buy Quote Qty (e.g., 11.0 USDT) [{current}], > 0: ").strip()
            if not new_val_str: break # Skip
            try:
                new_qty = float(new_val_str)
                if new_qty > 0:
                    settings['buy_quote_quantity'] = new_qty
                    break
                else: print(f"   {RED}[ERROR] Kuantitas Beli harus lebih besar dari 0.{RESET}")
            except ValueError: print(f"   {RED}[ERROR] Masukkan angka (e.g., 11.0 atau 11).{RESET}")

        # 11. Sell Base Qty
        current = settings['sell_base_quantity']
        while True:
            new_val_str = input(f"11. Sell Base Qty (e.g., 0.0005 BTC) [{current}], >= 0: ").strip()
            if not new_val_str: break # Skip
            try:
                new_qty = float(new_val_str)
                if new_qty >= 0: # Boleh 0 jika tidak ingin ada sell otomatis
                    settings['sell_base_quantity'] = new_qty
                    break
                else: print(f"   {RED}[ERROR] Kuantitas Jual harus 0 atau lebih besar.{RESET}")
            except ValueError: print(f"   {RED}[ERROR] Masukkan angka (e.g., 0.0005 atau 0).{RESET}")

        # 12. Eksekusi Order
        current_exec = settings['execute_binance_orders']
        exec_prompt = f"{GREEN}y (Aktif){RESET}" if current_exec else f"{RED}n (Nonaktif){RESET}"
        while True:
            new_val_str = input(f"12. Eksekusi Order Binance? (y/n) [{exec_prompt}]: ").lower().strip()
            if not new_val_str: break # Skip
            if new_val_str == 'y':
                settings['execute_binance_orders'] = True
                break
            elif new_val_str == 'n':
                settings['execute_binance_orders'] = False
                break
            else: print(f"   {RED}[ERROR] Masukkan 'y' atau 'n'.{RESET}")

        save_settings(settings)

    except (KeyboardInterrupt, EOFError):
        print(f"\n{YELLOW}Edit dibatalkan.{RESET}")
        time.sleep(1)

# --- Fungsi Menu Utama ---
def main_menu():
    """Menampilkan menu utama aplikasi menggunakan TUI."""
    settings = load_settings() # Load sekali di awal

    # Cek dependensi Binance jika dibutuhkan di awal
    if not BINANCE_AVAILABLE and any(s.startswith('binance_') for s in settings if settings[s]):
        print(f"\n{YELLOW}{BOLD}PERINGATAN: Library 'python-binance' tidak ditemukan,{RESET}")
        print(f"{YELLOW}tapi ada konfigurasi Binance di {CONFIG_FILE}. Fitur Binance tidak akan jalan.{RESET}")
        print(f"{YELLOW}Install dengan: {BOLD}pip install python-binance{RESET}")
        time.sleep(4)

    while True:
        settings = load_settings() # Reload settings setiap kali kembali ke menu utama
        clear_screen()
        print_separator(char="=", color=MAGENTA)
        print_centered("Exora AI - Email & Binance Listener", color=MAGENTA)
        print_separator(char="=", color=MAGENTA)

        # Siapkan Teks Status
        email_status = f"{GREEN}OK{RESET}" if settings['email_address'] and settings['app_password'] else f"{RED}Belum Lengkap{RESET}"
        binance_exec_mode = f"{GREEN}AKTIF{RESET}" if settings['execute_binance_orders'] else f"{YELLOW}NONAKTIF{RESET}"
        binance_config_ok = settings['binance_api_key'] and settings['binance_api_secret'] and settings['trading_pair']
        binance_status = f"{GREEN}OK{RESET}" if binance_config_ok else f"{RED}Belum Lengkap{RESET}"
        binance_lib_stat = f"{GREEN}(Lib OK){RESET}" if BINANCE_AVAILABLE else f"{RED}(Lib Missing!){RESET}"

        print(f"\n{BOLD}Status Konfigurasi:{RESET}")
        print(f" - Email       : {email_status}")
        if settings['execute_binance_orders']:
            print(f" - Binance     : {binance_status} {binance_lib_stat}")
        print(f" - Eksekusi Ord: {binance_exec_mode}\n")


        # Definisikan Opsi Menu
        menu_options = [
            f"Mulai Mendengarkan (Mode: {binance_exec_mode})",
            "Pengaturan",
            "Keluar"
        ]
        terminal_menu = TerminalMenu(
            menu_options,
            title="MENU UTAMA",
            menu_cursor=f"{CYAN}> ",
            menu_cursor_style=("fg_cyan", "bold"),
            menu_highlight_style=("bg_cyan", "fg_black"),
            cycle_cursor=True,
            clear_screen=False # Kita sudah clear manual
        )
        selected_index = terminal_menu.show()

        if selected_index == 0: # Mulai Mendengarkan
            # Validasi sebelum memulai
            valid_email = settings['email_address'] and settings['app_password']
            execute_binance = settings.get("execute_binance_orders")
            valid_binance_config = settings['binance_api_key'] and settings['binance_api_secret'] and settings['trading_pair']
            # Validasi qty hanya jika eksekusi aktif
            valid_binance_qty = (settings['buy_quote_quantity'] > 0 and settings['sell_base_quantity'] >= 0)

            if not valid_email:
                print(f"\n{RED}{BOLD}[ERROR] Pengaturan Email (Alamat/App Password) belum lengkap!{RESET}")
                print(f"{YELLOW}         Masuk ke menu 'Pengaturan' dulu.{RESET}")
                time.sleep(3)
            elif execute_binance and not BINANCE_AVAILABLE:
                 print(f"\n{RED}{BOLD}[ERROR] Eksekusi Binance aktif tapi library 'python-binance' tidak ada!{RESET}")
                 print(f"{YELLOW}         Install library atau nonaktifkan eksekusi di Pengaturan.{RESET}")
                 time.sleep(4)
            elif execute_binance and not valid_binance_config:
                 print(f"\n{RED}{BOLD}[ERROR] Pengaturan Binance (API/Secret/Pair) belum lengkap!{RESET}")
                 print(f"{YELLOW}         Masuk ke menu 'Pengaturan' dulu.{RESET}")
                 time.sleep(3)
            elif execute_binance and not valid_binance_qty:
                 print(f"\n{RED}{BOLD}[ERROR] Kuantitas Beli/Jual Binance tidak valid!{RESET}")
                 print(f"{YELLOW}         - Buy Quote Qty harus > 0")
                 print(f"{YELLOW}         - Sell Base Qty harus >= 0")
                 print(f"{YELLOW}         Periksa di menu 'Pengaturan'.{RESET}")
                 time.sleep(4)
            else:
                # Siap memulai
                start_listening(settings)
                # Setelah listener berhenti (misal via Ctrl+C), loop menu utama akan lanjut
        elif selected_index == 1: # Pengaturan
            show_settings(settings)
            # Settings mungkin berubah, akan di-reload saat loop menu utama berulang
        elif selected_index == 2 or selected_index is None: # Keluar atau Ctrl+C di menu
            clear_screen()
            print(f"\n{CYAN}{BOLD}Terima kasih! Sampai jumpa!{RESET}\n")
            sys.exit(0)
        else: # Pilihan tidak terduga
             print(f"\n{RED}{BOLD}[ERROR] Pilihan tidak valid.{RESET}")
             time.sleep(1)

# --- Entry Point ---
if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        # Signal handler sudah diatur, ini sbg fallback jika terjadi sebelum handler aktif
        clear_screen()
        print(f"\n{YELLOW}{BOLD}[WARN] Program dihentikan paksa.{RESET}")
        sys.exit(1)
    except Exception as e:
        # Tangkap error tak terduga di level tertinggi
        clear_screen()
        print(f"\n{BOLD}{RED}===== ERROR KRITIS ====={RESET}")
        traceback.print_exc()
        print(f"\n{RED}{BOLD}Terjadi error kritis yang tidak tertangani: {e}{RESET}")
        print("Program akan keluar.")
        sys.exit(1)
