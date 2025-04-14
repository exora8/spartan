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
import itertools # Untuk spinner cycle (Standard Library)

# --- Binance Integration ---
# (Bagian Binance tetap sama)
try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException, BinanceOrderException
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False
    print("\n!!! WARNING: Library 'python-binance' tidak ditemukan. !!!")
    print("!!!          Fitur eksekusi order Binance tidak akan berfungsi. !!!")
    print("!!!          Install dengan: pip install python-binance         !!!\n")
    # Definisikan exception dummy jika library tidak ada agar script tidak crash
    class BinanceAPIException(Exception): pass
    class BinanceOrderException(Exception): pass
    class Client: pass # Dummy class

# --- Konfigurasi & Variabel Global ---
# (Bagian Konfigurasi tetap sama)
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
running = True # Variabel global untuk mengontrol loop utama

# --- Kode Warna ANSI ---
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m" # Sedikit redup
UNDERLINE = "\033[4m"
BLINK = "\033[5m" # Mungkin tidak didukung semua terminal
REVERSE = "\033[7m"
HIDDEN = "\033[8m" # Jarang dipakai

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
WHITE = "\033[97m"

# --- Helper Animasi ---
SPINNER_CHARS = itertools.cycle(['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']) # Braille spinner
# SPINNER_CHARS = itertools.cycle(['|', '/', '-', '\\']) # Spinner klasik
LOADING_BAR = ['▏', '▎', '▍', '▌', '▋', '▊', '▉']

def clear_line():
    """Membersihkan baris saat ini di terminal."""
    sys.stdout.write("\r" + " " * 80 + "\r") # Pastikan cukup lebar
    sys.stdout.flush()

def spinning_message(message="Memproses", duration=0.1, color=CYAN):
    """Menampilkan pesan dengan spinner berputar."""
    spinner = next(SPINNER_CHARS)
    sys.stdout.write(f"\r{color}{BOLD}[{spinner}]{RESET} {color}{message}...{RESET} ")
    sys.stdout.flush()
    time.sleep(duration)

def animate_wait(seconds, message="Menunggu", color=BLUE):
    """Animasi countdown dengan spinner."""
    for i in range(seconds, 0, -1):
        if not running: break
        spinner = next(SPINNER_CHARS)
        sys.stdout.write(f"\r{color}{BOLD}[{spinner}]{RESET} {color}{message} {BOLD}{i}{RESET}{color} detik...{RESET}  ")
        sys.stdout.flush()
        time.sleep(1)
    clear_line()

def pulse_message(message, color=GREEN, duration=0.6, pulses=3):
    """Membuat pesan berkedip (pulse) dengan bold."""
    original_message = f"{color}{message}{RESET}"
    bold_message = f"{BOLD}{color}{message}{RESET}"
    for _ in range(pulses):
        if not running: break
        sys.stdout.write(f"\r{bold_message}")
        sys.stdout.flush()
        time.sleep(duration / (pulses * 2))
        sys.stdout.write(f"\r{original_message}")
        sys.stdout.flush()
        time.sleep(duration / (pulses * 2))
    # Pastikan akhirannya adalah pesan asli dan di baris baru
    clear_line()
    print(original_message)

def typing_effect(text, delay=0.03, color=WHITE):
    """Efek mengetik."""
    for char in text:
        sys.stdout.write(f"{color}{char}{RESET}")
        sys.stdout.flush()
        time.sleep(delay)
    print() # Newline di akhir

def draw_box(title, color=MAGENTA, width=40):
    """Menggambar box di sekitar judul."""
    padding = (width - len(title) - 2) // 2
    print(f"{BOLD}{color}{'═' * width}{RESET}")
    print(f"{BOLD}{color}║{' ' * padding}{title}{' ' * (width - len(title) - 2 - padding)}║{RESET}")
    print(f"{BOLD}{color}{'═' * width}{RESET}")

# --- Fungsi Penanganan Sinyal (Ctrl+C) ---
def signal_handler(sig, frame):
    global running
    clear_line()
    print(f"\n{YELLOW}{BOLD}[WARN] Ctrl+C terdeteksi. Menghentikan program...{RESET}")
    running = False
    time.sleep(1.0) # Beri waktu sedikit
    clear_screen()
    print(f"{RED}{BOLD}[EXIT] Keluar dari program.{RESET}")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# --- Fungsi Konfigurasi ---
# (Fungsi load_settings dan save_settings tetap sama, hanya pesan output bisa diberi warna)
def load_settings():
    """Memuat pengaturan dari file JSON, memastikan semua kunci ada."""
    settings = DEFAULT_SETTINGS.copy() # Mulai dengan default
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_settings = json.load(f)
                settings.update(loaded_settings) # Timpa default dengan yg dari file

                # Validasi tambahan setelah load (pesan diberi warna)
                if settings.get("check_interval_seconds", 10) < 5:
                    print(f"{YELLOW}[WARN] Interval cek di '{CONFIG_FILE}' < 5 detik, direset ke 10.{RESET}")
                    settings["check_interval_seconds"] = 10
                if not isinstance(settings.get("buy_quote_quantity"), (int, float)) or settings.get("buy_quote_quantity") <= 0:
                     print(f"{YELLOW}[WARN] 'buy_quote_quantity' tidak valid, direset ke {DEFAULT_SETTINGS['buy_quote_quantity']}.{RESET}")
                     settings["buy_quote_quantity"] = DEFAULT_SETTINGS['buy_quote_quantity']
                if not isinstance(settings.get("sell_base_quantity"), (int, float)) or settings.get("sell_base_quantity") < 0: # Allow 0
                     print(f"{YELLOW}[WARN] 'sell_base_quantity' tidak valid, direset ke {DEFAULT_SETTINGS['sell_base_quantity']}.{RESET}")
                     settings["sell_base_quantity"] = DEFAULT_SETTINGS['sell_base_quantity']
                if not isinstance(settings.get("execute_binance_orders"), bool):
                    print(f"{YELLOW}[WARN] 'execute_binance_orders' tidak valid, direset ke False.{RESET}")
                    settings["execute_binance_orders"] = False
                # Save back any corrections made if necessary
                # save_settings(settings) # Uncomment if you want auto-save on validation fix

        except json.JSONDecodeError:
            print(f"{RED}[ERROR] File konfigurasi '{CONFIG_FILE}' rusak. Menggunakan default & menyimpan ulang.{RESET}")
            save_settings(settings) # Simpan default yang bersih
        except Exception as e:
            print(f"{RED}[ERROR] Gagal memuat konfigurasi: {e}{RESET}")
            # Tidak menyimpan ulang jika error tidak diketahui
    else:
        # Jika file tidak ada, simpan default awal
        print(f"{YELLOW}[INFO] File konfigurasi '{CONFIG_FILE}' tidak ditemukan. Membuat dengan nilai default.{RESET}")
        save_settings(settings)
    return settings

def save_settings(settings):
    """Menyimpan pengaturan ke file JSON."""
    try:
        # Pastikan tipe data benar sebelum menyimpan
        settings['check_interval_seconds'] = int(settings.get('check_interval_seconds', 10))
        settings['buy_quote_quantity'] = float(settings.get('buy_quote_quantity', 11.0))
        settings['sell_base_quantity'] = float(settings.get('sell_base_quantity', 0.0))
        settings['execute_binance_orders'] = bool(settings.get('execute_binance_orders', False))

        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings, f, indent=4, sort_keys=True) # Urutkan kunci agar lebih rapi
        # Pesan sukses dengan pulse kecil
        pulse_message(f"Pengaturan berhasil disimpan ke '{CONFIG_FILE}'", GREEN, duration=0.4, pulses=2)
    except Exception as e:
        print(f"{RED}[ERROR] Gagal menyimpan konfigurasi: {e}{RESET}")


# --- Fungsi Utilitas ---
# (Fungsi decode_mime_words dan get_text_from_email tetap sama, hanya pesan error diberi warna)
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def decode_mime_words(s):
    if not s: return ""
    try:
        decoded_parts = decode_header(s)
        result = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(encoding or 'utf-8', errors='replace'))
            else:
                result.append(part)
        return "".join(result)
    except Exception as e:
        print(f"{YELLOW}[WARN] Gagal decode header: {e}{RESET}")
        return str(s) # Kembalikan string asli jika gagal total

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


# --- Fungsi Beep ---
# (Fungsi trigger_beep tetap sama, hanya pesan diberi warna/bold)
def trigger_beep(action):
    action_upper = action.upper()
    action_display = f"{BOLD}{action_upper}{RESET}" if action_upper in ["BUY", "SELL"] else action
    try:
        if action == "buy":
            print(f"{MAGENTA}{BOLD}[⚡ ACTION ⚡]{RESET} {MAGENTA}Memicu BEEP untuk {GREEN}{action_display}{RESET}{MAGENTA}!{RESET}")
            subprocess.run(["beep", "-f", "1000", "-l", "500", "-D", "500", "-r", "5"], check=True, capture_output=True, text=True)
        elif action == "sell":
            print(f"{MAGENTA}{BOLD}[⚡ ACTION ⚡]{RESET} {MAGENTA}Memicu BEEP untuk {RED}{action_display}{RESET}{MAGENTA}!{RESET}")
            subprocess.run(["beep", "-f", "700", "-l", "1000", "-D", "500", "-r", "2"], check=True, capture_output=True, text=True)
        else:
             print(f"{YELLOW}[WARN] Aksi beep tidak dikenal '{action}'.{RESET}")
    except FileNotFoundError:
        print(f"{YELLOW}[WARN] Perintah 'beep' tidak ditemukan. Beep dilewati.{RESET}")
    except subprocess.CalledProcessError as e:
        print(f"{RED}[ERROR] Gagal menjalankan 'beep': {e}{RESET}")
        if e.stderr: print(f"{DIM}{RED}         Stderr: {e.stderr.strip()}{RESET}")
    except Exception as e:
        print(f"{RED}[ERROR] Kesalahan tak terduga saat beep: {e}{RESET}")

# --- Fungsi Eksekusi Binance ---
# (Fungsi get_binance_client dan execute_binance_order dimodifikasi dengan animasi/warna)
def get_binance_client(settings):
    """Membuat instance Binance client dengan animasi."""
    if not BINANCE_AVAILABLE:
        print(f"{RED}{BOLD}[ERROR] Library python-binance tidak terinstall. Tidak bisa membuat client.{RESET}")
        return None
    if not settings.get('binance_api_key') or not settings.get('binance_api_secret'):
        print(f"{RED}{BOLD}[ERROR] API Key atau Secret Key Binance belum diatur!{RESET}")
        return None

    client = None
    connecting_msg = "Menghubungkan ke Binance API"
    start_time = time.time()
    while time.time() - start_time < 10 and not client and running: # Timeout 10 detik
        try:
            spinning_message(connecting_msg, 0.15, color=CYAN)
            client_instance = Client(settings['binance_api_key'], settings['binance_api_secret'])
            # Test koneksi
            client_instance.ping()
            clear_line()
            pulse_message("Koneksi ke Binance API Berhasil!", GREEN, duration=0.5, pulses=2)
            client = client_instance # Berhasil
        except BinanceAPIException as e:
            clear_line()
            print(f"{RED}{BOLD}[BINANCE ERROR] Gagal terhubung/autentikasi: {e}{RESET}")
            return None # Gagal, keluar
        except Exception as e:
            clear_line()
            print(f"{RED}[ERROR] Gagal membuat Binance client: {e}{RESET}")
            return None # Gagal, keluar
        if not running: return None # Jika user Ctrl+C saat proses

    if not client:
        clear_line()
        print(f"{RED}[ERROR] Gagal terhubung ke Binance setelah beberapa saat.{RESET}")
    return client


def execute_binance_order(client, settings, side):
    """Mengeksekusi order MARKET BUY atau SELL di Binance dengan animasi."""
    if not client:
        print(f"{RED}[BINANCE] Eksekusi dibatalkan, client tidak valid.{RESET}")
        return False
    if not settings.get("execute_binance_orders", False):
        print(f"{YELLOW}[BINANCE] Eksekusi order dinonaktifkan ('execute_binance_orders': false). Order dilewati.{RESET}")
        return False

    pair = settings.get('trading_pair', '').upper()
    if not pair:
        print(f"{RED}[BINANCE ERROR] Trading pair belum diatur!{RESET}")
        return False

    order_details = {}
    action_desc = ""
    action_color = RESET

    try:
        if side == Client.SIDE_BUY:
            quote_qty = settings.get('buy_quote_quantity', 0.0)
            if quote_qty <= 0:
                 print(f"{RED}[BINANCE ERROR] Kuantitas Beli (buy_quote_quantity) harus > 0.{RESET}")
                 return False
            order_details = { 'symbol': pair, 'side': Client.SIDE_BUY, 'type': Client.ORDER_TYPE_MARKET, 'quoteOrderQty': quote_qty }
            action_desc = f"MARKET BUY {quote_qty} (quote) of {pair}"
            action_color = GREEN

        elif side == Client.SIDE_SELL:
            base_qty = settings.get('sell_base_quantity', 0.0)
            if base_qty <= 0:
                 print(f"{RED}[BINANCE ERROR] Kuantitas Jual (sell_base_quantity) harus > 0.{RESET}")
                 return False
            order_details = { 'symbol': pair, 'side': Client.SIDE_SELL, 'type': Client.ORDER_TYPE_MARKET, 'quantity': base_qty }
            action_desc = f"MARKET SELL {base_qty} (base) of {pair}"
            action_color = RED
        else:
            print(f"{RED}[BINANCE ERROR] Sisi order tidak valid: {side}{RESET}")
            return False

        print(f"{MAGENTA}{BOLD}[BINANCE ACTION]{RESET} {action_color}Mencoba eksekusi: {BOLD}{action_desc}{RESET}{action_color}...{RESET}")

        # Animasi saat mengirim order
        executing_msg = "Mengirim order ke Binance"
        order_result = None
        start_time = time.time()
        while time.time() - start_time < 15 and not order_result and running: # Timeout 15 detik
             try:
                 spinning_message(executing_msg, 0.1, color=MAGENTA)
                 # --- EKSEKUSI ORDER SEBENARNYA ---
                 order_result = client.create_order(**order_details)
                 # ----------------------------------
             except (BinanceAPIException, BinanceOrderException) as e:
                 clear_line()
                 print(f"{RED}{BOLD}[BINANCE EXECUTION FAILED]{RESET}")
                 print(f"{RED}  Error Code: {e.status_code} - Pesan: {e.message}{RESET}")
                 # Pesan bantuan spesifik
                 if isinstance(e, BinanceAPIException):
                     if e.code == -2010: print(f"{YELLOW}    -> Kemungkinan saldo tidak cukup.{RESET}")
                     elif e.code == -1121: print(f"{YELLOW}    -> Trading pair '{pair}' tidak valid.{RESET}")
                     elif e.code == -1013 or 'MIN_NOTIONAL' in e.message: print(f"{YELLOW}    -> Order size terlalu kecil (cek MIN_NOTIONAL/LOT_SIZE).{RESET}")
                 return False # Gagal, keluar
             except Exception as e:
                 clear_line()
                 print(f"{RED}{BOLD}[ERROR]{RESET} Kesalahan tak terduga saat eksekusi order Binance:")
                 traceback.print_exc()
                 return False # Gagal, keluar
             if not running: return False # User Ctrl+C saat proses

        clear_line()

        if order_result:
            pulse_message("🚀 Order Berhasil Dieksekusi! 🚀", GREEN, duration=0.6, pulses=3)
            print(f"{GREEN}  Order ID : {BOLD}{order_result.get('orderId')}{RESET}")
            print(f"{GREEN}  Symbol   : {BOLD}{order_result.get('symbol')}{RESET}")
            print(f"{GREEN}  Side     : {BOLD}{order_result.get('side')}{RESET}")
            print(f"{GREEN}  Status   : {BOLD}{order_result.get('status')}{RESET}")
            if order_result.get('fills'):
                total_qty = sum(float(f['qty']) for f in order_result['fills'])
                total_quote_qty = sum(float(f['qty']) * float(f['price']) for f in order_result['fills'])
                avg_price = total_quote_qty / total_qty if total_qty else 0
                print(f"{GREEN}  Avg Price: {BOLD}{avg_price:.8f}{RESET}")
                print(f"{GREEN}  Filled Qty: {BOLD}{total_qty:.8f}{RESET}")
            return True
        else:
            # Timeout atau diinterupsi
            print(f"{RED}[ERROR] Gagal mengeksekusi order (Timeout atau dibatalkan).{RESET}")
            return False

    except Exception as e: # Catchall di luar loop eksekusi
        print(f"{RED}[ERROR] Kesalahan tak terduga di fungsi execute_binance_order: {e}{RESET}")
        traceback.print_exc()
        return False

# --- Fungsi Pemrosesan Email ---
def process_email(mail, email_id, settings, binance_client):
    """Mengambil, mem-parsing, dan memproses satu email, lalu eksekusi order jika sesuai."""
    global running
    if not running: return

    target_keyword_lower = settings['target_keyword'].lower()
    trigger_keyword_lower = settings['trigger_keyword'].lower()
    email_id_str = email_id.decode('utf-8')
    processing_start_time = time.time()

    try:
        # Animasi saat fetch email
        fetch_msg = f"Mengambil email ID {email_id_str}"
        status, data = None, None
        fetch_tries = 0
        while fetch_tries < 3 and not status and running: # Coba fetch maks 3 kali
            spinning_message(fetch_msg, 0.1, color=CYAN)
            try:
                status, data = mail.fetch(email_id, "(RFC822)")
                if status != 'OK':
                     clear_line()
                     print(f"{YELLOW}[WARN] Fetch email ID {email_id_str} gagal ({status}), mencoba lagi...{RESET}")
                     status = None # Agar loop berlanjut
                     time.sleep(0.5)
            except Exception as fetch_err:
                 clear_line()
                 print(f"{RED}[ERROR] Error saat fetch email {email_id_str}: {fetch_err}{RESET}")
                 status = 'ERROR' # Tandai error agar tidak loop lagi
            fetch_tries += 1
            if not running: return # Jika diinterupsi saat fetch

        clear_line()
        if status != 'OK':
            print(f"{RED}[ERROR] Gagal total mengambil email ID {email_id_str} setelah beberapa percobaan.{RESET}")
            return

        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        subject = decode_mime_words(msg["Subject"])
        sender = decode_mime_words(msg["From"])
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print(f"\n{CYAN}--- 📨 Email Diterima ({timestamp}) ---{RESET}")
        print(f" {DIM}ID    : {email_id_str}{RESET}")
        print(f" {DIM}Dari  : {sender}{RESET}")
        print(f" {BOLD}Subjek: {subject}{RESET}")

        # Animasi parsing body (cepat saja)
        parse_msg = "Memparsing isi email"
        for _ in range(3): spinning_message(parse_msg, 0.05, color=DIM); time.sleep(0.05)
        clear_line()

        body = get_text_from_email(msg)
        full_content = (subject.lower() + " " + body)

        if target_keyword_lower in full_content:
            pulse_message(f"Keyword target '{settings['target_keyword']}' ditemukan!", GREEN, duration=0.5, pulses=2)
            try:
                target_index = full_content.index(target_keyword_lower)
                trigger_index = full_content.index(trigger_keyword_lower, target_index + len(target_keyword_lower))
                start_word_index = trigger_index + len(trigger_keyword_lower)
                text_after_trigger = full_content[start_word_index:].lstrip()
                words_after_trigger = text_after_trigger.split(maxsplit=1)

                if words_after_trigger:
                    action_word = words_after_trigger[0].strip('.,!?:;()[]{}').lower()
                    action_color = GREEN if action_word == "buy" else RED if action_word == "sell" else YELLOW
                    print(f"{GREEN}[INFO] Keyword trigger '{settings['trigger_keyword']}' ditemukan. Kata berikutnya: '{BOLD}{action_color}{action_word.upper()}{RESET}{GREEN}'{RESET}")

                    # --- Trigger Aksi (Beep dan/atau Binance) ---
                    if action_word == "buy":
                        trigger_beep("buy")
                        if binance_client and settings.get("execute_binance_orders"):
                           execute_binance_order(binance_client, settings, Client.SIDE_BUY)
                        elif settings.get("execute_binance_orders"):
                            print(f"{YELLOW}[WARN] Eksekusi Binance aktif tapi client tidak valid/tersedia.{RESET}")

                    elif action_word == "sell":
                        trigger_beep("sell")
                        if binance_client and settings.get("execute_binance_orders"):
                           execute_binance_order(binance_client, settings, Client.SIDE_SELL)
                        elif settings.get("execute_binance_orders"):
                           print(f"{YELLOW}[WARN] Eksekusi Binance aktif tapi client tidak valid/tersedia.{RESET}")
                    else:
                        print(f"{YELLOW}[WARN] Kata '{action_word}' bukan 'buy'/'sell'. Tidak ada aksi market.{RESET}")

                else:
                    print(f"{YELLOW}[WARN] Tidak ada kata setelah '{settings['trigger_keyword']}'.{RESET}")

            except ValueError:
                print(f"{YELLOW}[WARN] Keyword trigger '{settings['trigger_keyword']}' tidak ditemukan {BOLD}setelah{RESET}{YELLOW} '{settings['target_keyword']}'.{RESET}")
            except Exception as e:
                 print(f"{RED}[ERROR] Gagal parsing kata setelah trigger: {e}{RESET}")
        else:
            print(f"{BLUE}[INFO] Keyword target '{settings['target_keyword']}' tidak ditemukan.{RESET}")

        # Tandai email sebagai sudah dibaca ('Seen') - dengan animasi kecil
        mark_msg = f"Menandai email {email_id_str} sebagai 'Seen'"
        marked = False
        start_time = time.time()
        while time.time() - start_time < 5 and not marked and running: # Timeout 5 detik
            try:
                spinning_message(mark_msg, 0.1, color=DIM)
                status, _ = mail.store(email_id, '+FLAGS', '\\Seen')
                if status == 'OK':
                    marked = True
                else:
                    time.sleep(0.2) # Jeda jika gagal sementara
            except Exception as e:
                 clear_line()
                 print(f"{RED}[ERROR] Gagal menandai email {email_id_str} sebagai 'Seen': {e}{RESET}")
                 break # Keluar loop jika error
            if not running: break # Jika diinterupsi

        clear_line()
        if marked:
            print(f"{DIM}[INFO] Email {email_id_str} ditandai 'Seen'.{RESET}")
        elif running: # Hanya print error jika tidak diinterupsi
             print(f"{YELLOW}[WARN] Gagal menandai email {email_id_str} 'Seen' (mungkin sudah ditandai?).{RESET}")

        processing_time = time.time() - processing_start_time
        print(f"{CYAN}--- Selesai Proses Email (took {processing_time:.2f}s) ---{RESET}")

    except Exception as e:
        clear_line() # Bersihkan sisa animasi jika ada error
        print(f"{RED}{BOLD}[ERROR]{RESET} Gagal memproses email ID {email_id_str}:{RESET}")
        traceback.print_exc()

# --- Fungsi Listening Utama ---
def start_listening(settings):
    """Memulai loop untuk memeriksa email baru dengan animasi & menyiapkan client Binance."""
    global running
    running = True
    mail = None
    binance_client = None
    wait_time = 30 # Waktu tunggu sebelum retry koneksi error
    consecutive_noop_failures = 0
    MAX_NOOP_FAILURES = 3 # Batas maks error NOOP sebelum reconnect paksa

    # --- Setup Binance Client di Awal (jika diaktifkan) ---
    if settings.get("execute_binance_orders"):
        if not BINANCE_AVAILABLE:
             print(f"{RED}{BOLD}[FATAL] Eksekusi Binance diaktifkan tapi library python-binance tidak ada! Nonaktifkan atau install.{RESET}")
             running = False
             time.sleep(3)
             return
        print(f"{CYAN}[SYS] Menginisialisasi koneksi Binance API...{RESET}")
        binance_client = get_binance_client(settings)
        if not binance_client:
            print(f"{RED}{BOLD}[FATAL] Gagal inisialisasi Binance Client. Periksa API Key/Secret/Koneksi.{RESET}")
            print(f"{YELLOW}         Eksekusi order tidak akan berjalan. Menonaktifkan di Pengaturan akan mengabaikan ini.{RESET}")
            # Tidak menghentikan program, hanya notifikasi email mungkin masih diinginkan
            # running = False # Bisa di-uncomment jika ingin stop total jika Binance gagal
            # return
        else:
            print(f"{GREEN}[SYS] Binance Client Siap Digunakan.{RESET}")
    else:
        print(f"{YELLOW}[INFO] Eksekusi order Binance dinonaktifkan.{RESET}")

    print("-" * 50)
    time.sleep(1) # Jeda sebelum mulai loop

    # --- Loop Utama Email Listener ---
    while running:
        try:
            # --- Koneksi IMAP dengan Animasi ---
            imap_server = settings['imap_server']
            email_addr = settings['email_address']
            app_pass = settings['app_password']

            if not mail or mail.state == 'LOGOUT': # Hanya konek jika belum atau sudah logout
                connect_msg = f"Menghubungkan ke {imap_server}"
                connecting = True
                start_time = time.time()
                mail = None # Reset mail object
                while connecting and (time.time() - start_time < 20) and running: # Timeout 20 detik
                    spinning_message(connect_msg, 0.15, color=CYAN)
                    try:
                        mail = imaplib.IMAP4_SSL(imap_server)
                        clear_line()
                        pulse_message(f"Terhubung ke {imap_server}", GREEN, duration=0.4, pulses=2)
                        connecting = False # Berhasil connect
                    except (socket.gaierror, OSError, socket.error, imaplib.IMAP4.error) as e:
                        clear_line()
                        print(f"{YELLOW}[WARN] Gagal konek ({e}), mencoba lagi...{RESET}")
                        time.sleep(2) # Jeda sebelum coba lagi
                    except Exception as e:
                        clear_line()
                        print(f"{RED}[ERROR] Gagal konek IMAP: {e}{RESET}")
                        connecting = False # Hentikan percobaan koneksi
                        raise # Lemparkan error ke blok catch utama
                    if not running: connecting = False # Hentikan jika Ctrl+C

                if not mail and running: # Jika timeout atau gagal total
                    clear_line()
                    print(f"{RED}[ERROR] Gagal terhubung ke {imap_server} setelah beberapa saat.{RESET}")
                    raise ConnectionError("IMAP Connection Timeout") # Trigger blok catch bawah

                if not running: break # Keluar loop utama jika diinterupsi

                # --- Login dengan Animasi ---
                login_msg = f"Login sebagai {email_addr}"
                logging_in = True
                start_time = time.time()
                login_success = False
                while logging_in and (time.time() - start_time < 15) and running: # Timeout 15 detik
                     spinning_message(login_msg, 0.15, color=CYAN)
                     try:
                         status, _ = mail.login(email_addr, app_pass)
                         if status == 'OK':
                             clear_line()
                             pulse_message(f"Login berhasil sebagai {BOLD}{email_addr}{RESET}", GREEN, duration=0.5, pulses=2)
                             logging_in = False
                             login_success = True
                         else:
                             # Seharusnya imaplib raise exception jika gagal, tapi just in case
                             clear_line()
                             print(f"{RED}[ERROR] Login gagal (Status: {status}). Periksa kredensial.{RESET}")
                             logging_in = False
                             raise imaplib.IMAP4.error("Authentication failed") # Trigger catch
                     except imaplib.IMAP4.error as e:
                         clear_line()
                         err_str = str(e).lower()
                         if "authentication failed" in err_str or "invalid credentials" in err_str or "username and password not accepted" in err_str:
                              print(f"{RED}{BOLD}[FATAL] Login Email GAGAL! Periksa Alamat Email dan App Password.{RESET}")
                         else:
                              print(f"{RED}[ERROR] Kesalahan IMAP saat login: {e}{RESET}")
                         logging_in = False # Hentikan percobaan login
                         raise # Lemparkan error ke blok catch utama
                     except Exception as e:
                         clear_line()
                         print(f"{RED}[ERROR] Kesalahan tak terduga saat login: {e}{RESET}")
                         logging_in = False
                         raise
                     if not running: logging_in = False

                if not login_success and running:
                    clear_line()
                    print(f"{RED}[ERROR] Gagal login setelah beberapa saat.{RESET}")
                    raise ConnectionError("IMAP Login Timeout/Failure")

                if not running: break

                # --- Pilih Inbox ---
                try:
                    mail.select("inbox")
                    print(f"{GREEN}[INFO] Memulai mode mendengarkan di INBOX... (Tekan Ctrl+C untuk berhenti){RESET}")
                    print(f"{DIM}{'-' * 50}{RESET}")
                    consecutive_noop_failures = 0 # Reset counter error NOOP
                except Exception as e:
                     print(f"{RED}[ERROR] Gagal memilih INBOX: {e}{RESET}")
                     raise # Lemparkan error

            # --- Loop Cek Email ---
            while running:
                try:
                    # Cek koneksi IMAP dengan NOOP
                    status, _ = mail.noop()
                    if status != 'OK':
                        consecutive_noop_failures += 1
                        print(f"{YELLOW}[WARN] Koneksi IMAP NOOP gagal ({status}). Percobaan {consecutive_noop_failures}/{MAX_NOOP_FAILURES}.{RESET}")
                        if consecutive_noop_failures >= MAX_NOOP_FAILURES:
                            print(f"{YELLOW}[WARN] Terlalu banyak NOOP gagal. Mencoba reconnect...{RESET}")
                            break # Keluar loop cek email untuk reconnect paksa
                        time.sleep(2) # Jeda singkat sebelum coba lagi
                    else:
                        consecutive_noop_failures = 0 # Reset jika berhasil

                except (imaplib.IMAP4.abort, imaplib.IMAP4.readonly, OSError, socket.error) as NopErr:
                     print(f"{YELLOW}[WARN] Koneksi IMAP terputus ({NopErr}). Mencoba reconnect...{RESET}")
                     consecutive_noop_failures = 0 # Reset counter
                     break # Keluar loop cek email untuk reconnect paksa
                except Exception as NopErr:
                     print(f"{RED}[ERROR] Error tak terduga saat NOOP: {NopErr}{RESET}")
                     traceback.print_exc()
                     consecutive_noop_failures = 0 # Reset counter
                     break # Keluar loop cek email untuk reconnect paksa

                # Cek koneksi Binance jika client ada (opsional)
                if binance_client and settings.get("execute_binance_orders"):
                    try:
                         binance_client.ping()
                    except Exception as PingErr:
                         print(f"{YELLOW}[WARN] Ping ke Binance API gagal ({PingErr}). Mencoba membuat ulang client...{RESET}")
                         # Coba buat ulang client
                         binance_client = get_binance_client(settings)
                         if not binance_client:
                              print(f"{RED}       Gagal membuat ulang Binance client. Eksekusi mungkin gagal.{RESET}")
                         time.sleep(5) # Beri jeda setelah error ping

                # --- Cek Email Baru (UNSEEN) ---
                search_status, messages = 'ERROR', [b'']
                try:
                    search_status, messages = mail.search(None, '(UNSEEN)')
                except Exception as search_err:
                     print(f"{RED}[ERROR] Gagal mencari email UNSEEN: {search_err}{RESET}")
                     break # Coba reconnect jika search gagal

                if search_status == 'OK':
                    email_ids = messages[0].split()
                    if email_ids:
                        clear_line() # Hapus pesan tunggu jika ada
                        pulse_message(f"🎉 Menemukan {len(email_ids)} email baru! 🎉", CYAN, duration=0.6, pulses=3)
                        for email_id in email_ids:
                            if not running: break
                            process_email(mail, email_id, settings, binance_client)
                        if not running: break
                        print(f"{DIM}{'-' * 50}{RESET}")
                        print(f"{GREEN}[INFO] Selesai memproses. Kembali mendengarkan...{RESET}")
                    else:
                        # Animasi Menunggu
                        wait_interval = settings['check_interval_seconds']
                        wait_msg = f"Tidak ada email baru. Cek lagi dalam"
                        for i in range(wait_interval, 0, -1):
                             if not running: break
                             spinner = next(SPINNER_CHARS)
                             sys.stdout.write(f"\r{BLUE}{BOLD}[{spinner}]{RESET} {BLUE}{wait_msg} {BOLD}{i}{RESET}{BLUE} detik...{RESET}    ")
                             sys.stdout.flush()
                             time.sleep(1)
                        if not running: break
                        clear_line() # Hapus pesan tunggu setelah selesai
                else:
                     print(f"{RED}[ERROR] Gagal mencari email (Status: {search_status}). Mencoba reconnect...{RESET}")
                     break # Keluar loop cek email untuk reconnect

            # Tutup koneksi IMAP jika keluar loop inner (karena error/reconnect)
            if mail and mail.state == 'SELECTED':
                try:
                    clear_line()
                    print(f"{DIM}[SYS] Menutup koneksi inbox...{RESET}")
                    mail.close()
                except Exception: pass
            if mail and mail.state != 'LOGOUT':
                 try:
                     mail.logout()
                     print(f"{DIM}[SYS] Logout dari server IMAP.{RESET}")
                 except Exception: pass
            mail = None # Set None agar koneksi dibuat ulang di iterasi berikutnya


        # --- Exception Handling untuk Loop Utama ---
        except (imaplib.IMAP4.error, imaplib.IMAP4.abort) as e:
            clear_line()
            err_str = str(e).lower()
            if "authentication failed" in err_str or "invalid credentials" in err_str or "username and password not accepted" in err_str:
                print(f"{RED}{BOLD}[FATAL] Login Email GAGAL! Periksa Alamat Email dan App Password.{RESET}")
                running = False # Hentikan loop utama
                return # Keluar dari fungsi start_listening
            else:
                print(f"{RED}[ERROR] Kesalahan IMAP: {e}{RESET}")
            print(f"{YELLOW}[WARN] Mencoba menghubungkan kembali dalam {wait_time} detik...{RESET}")
            animate_wait(wait_time, "Menunggu sebelum retry", YELLOW)
        except (ConnectionError, OSError, socket.error, socket.gaierror) as e:
             clear_line()
             print(f"{RED}[ERROR] Kesalahan Koneksi: {e}{RESET}")
             print(f"{YELLOW}[WARN] Periksa koneksi internet. Mencoba lagi dalam {wait_time} detik...{RESET}")
             animate_wait(wait_time, "Menunggu sebelum retry", YELLOW)
        except Exception as e:
            clear_line()
            print(f"{RED}{BOLD}[ERROR]{RESET} Kesalahan tak terduga di loop utama:")
            traceback.print_exc()
            print(f"{YELLOW}[WARN] Mencoba menghubungkan kembali dalam {wait_time} detik...{RESET}")
            animate_wait(wait_time, "Menunggu sebelum retry", YELLOW)
        finally:
            # Pastikan logout jika masih terkoneksi dan loop berhenti karena error lain
            if mail and mail.state != 'LOGOUT':
                try:
                    mail.logout()
                    print(f"{DIM}[SYS] Logout darurat dari server IMAP.{RESET}")
                except Exception: pass
            mail = None # Set None untuk memastikan re-koneksi
        if running: time.sleep(2) # Jeda sebelum retry koneksi utama jika masih running

    clear_line()
    print(f"\n{YELLOW}{BOLD}[INFO] Mode mendengarkan dihentikan.{RESET}")


# --- Fungsi Menu Pengaturan ---
def show_settings(settings):
    """Menampilkan dan mengedit pengaturan dengan tampilan lebih menarik."""
    while True:
        clear_screen()
        draw_box("Pengaturan Email & Binance Listener", CYAN, 55)
        print(f"\n{BOLD}{BLUE}--- Pengaturan Email ---{RESET}")
        print(f" 1. {CYAN}Alamat Email{RESET}   : {settings['email_address'] or f'{YELLOW}[Belum diatur]{RESET}'}")
        print(f" 2. {CYAN}App Password{RESET}   : {'*' * len(settings['app_password']) if settings['app_password'] else f'{YELLOW}[Belum diatur]{RESET}'}") # Tampilkan bintang
        print(f" 3. {CYAN}Server IMAP{RESET}    : {settings['imap_server']}")
        print(f" 4. {CYAN}Interval Cek{RESET}   : {settings['check_interval_seconds']} detik {DIM}(min 5){RESET}")
        print(f" 5. {CYAN}Keyword Target{RESET} : {settings['target_keyword']}")
        print(f" 6. {CYAN}Keyword Trigger{RESET}: {settings['trigger_keyword']}")

        print(f"\n{BOLD}{BLUE}--- Pengaturan Binance ---{RESET}")
        binance_status = f"{GREEN}Tersedia{RESET}" if BINANCE_AVAILABLE else f"{RED}Tidak Tersedia (Install 'python-binance'){RESET}"
        print(f" Library Status      : {binance_status}")
        print(f" 7. {CYAN}API Key{RESET}        : {settings['binance_api_key'][:5] + '...' if settings['binance_api_key'] else f'{YELLOW}[Belum diatur]{RESET}'}") # Tampilkan sebagian
        print(f" 8. {CYAN}API Secret{RESET}     : {settings['binance_api_secret'][:5] + '...' if settings['binance_api_secret'] else f'{YELLOW}[Belum diatur]{RESET}'}") # Tampilkan sebagian
        print(f" 9. {CYAN}Trading Pair{RESET}   : {settings['trading_pair'] or f'{YELLOW}[Belum diatur]{RESET}'}")
        print(f"10. {CYAN}Buy Quote Qty{RESET}  : {settings['buy_quote_quantity']} {DIM}(e.g., USDT){RESET}")
        print(f"11. {CYAN}Sell Base Qty{RESET}  : {settings['sell_base_quantity']} {DIM}(e.g., BTC){RESET}")
        exec_status = f"{BOLD}{GREEN} ✅ AKTIF{RESET}" if settings['execute_binance_orders'] else f"{BOLD}{RED} ❌ NONAKTIF{RESET}"
        print(f"12. {CYAN}Eksekusi Order{RESET} : {exec_status}")
        print(f"{DIM}{'-' * 55}{RESET}")

        print("\nOpsi:")
        print(f" [{BOLD}{YELLOW}E{RESET}] - Edit Pengaturan")
        print(f" [{BOLD}{YELLOW}K{RESET}] - Kembali ke Menu Utama")
        print(f"{DIM}{'-' * 55}{RESET}")

        choice = input(f"{BOLD}Pilih opsi (E/K): {RESET}").lower().strip()

        if choice == 'e':
            print(f"\n{BOLD}{MAGENTA}--- Edit Pengaturan ---{RESET} {DIM}(Kosongkan untuk tidak mengubah){RESET}")
            # --- Edit Email ---
            print(f"\n{UNDERLINE}{CYAN}Email:{RESET}")
            new_val = input(f" 1. Email [{settings['email_address']}]: ").strip()
            if new_val: settings['email_address'] = new_val
            # Gunakan getpass untuk password demi keamanan
            prompt_pass = f" 2. App Password [{'*' * len(settings['app_password']) if settings['app_password'] else 'Kosong'}]: "
            try:
                new_pass = getpass.getpass(prompt_pass).strip()
                if new_pass: settings['app_password'] = new_pass
            except (EOFError, KeyboardInterrupt): # Handle jika getpass tidak didukung / diinterupsi
                 print("\nInput password dibatalkan.")
                 new_val = input(f" 2. App Password (terlihat) [{'*' * len(settings['app_password']) if settings['app_password'] else 'Kosong'}]: ").strip()
                 if new_val: settings['app_password'] = new_val

            new_val = input(f" 3. Server IMAP [{settings['imap_server']}]: ").strip()
            if new_val: settings['imap_server'] = new_val
            while True:
                new_val_str = input(f" 4. Interval (detik) [{settings['check_interval_seconds']}], min 5: ").strip()
                if not new_val_str: break
                try:
                    new_interval = int(new_val_str)
                    if new_interval >= 5: settings['check_interval_seconds'] = new_interval; break
                    else: print(f"   {RED}[ERROR] Interval minimal 5 detik.{RESET}")
                except ValueError: print(f"   {RED}[ERROR] Masukkan angka.{RESET}")
            new_val = input(f" 5. Keyword Target [{settings['target_keyword']}]: ").strip()
            if new_val: settings['target_keyword'] = new_val
            new_val = input(f" 6. Keyword Trigger [{settings['trigger_keyword']}]: ").strip()
            if new_val: settings['trigger_keyword'] = new_val

             # --- Edit Binance ---
            print(f"\n{UNDERLINE}{CYAN}Binance:{RESET}")
            if not BINANCE_AVAILABLE:
                 print(f"{YELLOW}   (Library Binance tidak terinstall, pengaturan ini mungkin tidak berpengaruh){RESET}")

            new_val = input(f" 7. API Key [{settings['binance_api_key'][:5]+'...' if settings['binance_api_key'] else 'Kosong'}]: ").strip()
            if new_val: settings['binance_api_key'] = new_val
            prompt_secret = f" 8. API Secret [{settings['binance_api_secret'][:5]+'...' if settings['binance_api_secret'] else 'Kosong'}]: "
            try:
                 new_secret = getpass.getpass(prompt_secret).strip()
                 if new_secret: settings['binance_api_secret'] = new_secret
            except (EOFError, KeyboardInterrupt):
                 print("\nInput secret dibatalkan.")
                 new_val = input(f" 8. API Secret (terlihat) [{settings['binance_api_secret'][:5]+'...' if settings['binance_api_secret'] else 'Kosong'}]: ").strip()
                 if new_val: settings['binance_api_secret'] = new_val

            new_val = input(f" 9. Trading Pair (e.g., BTCUSDT) [{settings['trading_pair']}]: ").strip().upper()
            if new_val: settings['trading_pair'] = new_val
            while True:
                 new_val_str = input(f"10. Buy Quote Qty (e.g., 11.0 USDT) [{settings['buy_quote_quantity']}], > 0: ").strip()
                 if not new_val_str: break
                 try:
                     new_qty = float(new_val_str)
                     if new_qty > 0: settings['buy_quote_quantity'] = new_qty; break
                     else: print(f"   {RED}[ERROR] Kuantitas Beli harus > 0.{RESET}")
                 except ValueError: print(f"   {RED}[ERROR] Masukkan angka desimal (e.g., 11.0).{RESET}")
            while True:
                 new_val_str = input(f"11. Sell Base Qty (e.g., 0.0005 BTC) [{settings['sell_base_quantity']}], >= 0: ").strip()
                 if not new_val_str: break
                 try:
                     new_qty = float(new_val_str)
                     if new_qty >= 0: settings['sell_base_quantity'] = new_qty; break
                     else: print(f"   {RED}[ERROR] Kuantitas Jual harus >= 0.{RESET}")
                 except ValueError: print(f"   {RED}[ERROR] Masukkan angka desimal (e.g., 0.0005).{RESET}")
            while True:
                 current_exec = settings['execute_binance_orders']
                 exec_prompt = f"{GREEN}Aktif{RESET}" if current_exec else f"{RED}Nonaktif{RESET}"
                 new_val_str = input(f"12. Eksekusi Order Binance? (y/n) [{exec_prompt}]: ").lower().strip()
                 if not new_val_str: break
                 if new_val_str == 'y': settings['execute_binance_orders'] = True; break
                 elif new_val_str == 'n': settings['execute_binance_orders'] = False; break
                 else: print(f"   {RED}[ERROR] Masukkan 'y' atau 'n'.{RESET}")

            save_settings(settings)
            print(f"\n{GREEN}{BOLD}Pengaturan diperbarui dan disimpan!{RESET}")
            time.sleep(2)

        elif choice == 'k':
            break # Keluar dari loop pengaturan
        else:
            print(f"{RED}{BOLD}Pilihan tidak valid!{RESET} Tekan Enter untuk lanjut...")
            input() # Tunggu user menekan Enter

# --- Fungsi Menu Utama ---
def main_menu():
    """Menampilkan menu utama aplikasi dengan tampilan lebih menarik."""
    settings = load_settings()
    first_run = True

    while True:
        clear_screen()
        title = "Exora AI - Email & Binance Listener"
        if first_run:
             draw_box(title, MAGENTA, 55)
             typing_effect("Selamat datang! Pilih opsi di bawah:", 0.04, CYAN)
             first_run = False
        else:
            draw_box(title, MAGENTA, 55)
            print("\nSilakan pilih opsi:\n")

        # Opsi Menu
        exec_binance = settings.get("execute_binance_orders")
        binance_mode = f" & {BOLD}Binance{RESET}" if exec_binance else ""
        print(f" [{BOLD}{GREEN}1{RESET}] Mulai Mendengarkan (Email{binance_mode})")
        print(f" [{BOLD}{CYAN}2{RESET}] Pengaturan")
        print(f" [{BOLD}{YELLOW}3{RESET}] Keluar")
        print(f"{DIM}{'-' * 55}{RESET}")

        # Tampilkan status konfigurasi penting
        email_ok = settings['email_address']
        pass_ok = settings['app_password']
        api_ok = settings['binance_api_key']
        secret_ok = settings['binance_api_secret']
        pair_ok = settings['trading_pair']
        buy_qty_ok = settings.get('buy_quote_quantity', 0) > 0
        sell_qty_ok = settings.get('sell_base_quantity', -1) >= 0 # Boleh 0

        email_status = f"{GREEN}OK{RESET}" if email_ok else f"{RED}X{RESET}"
        pass_status = f"{GREEN}OK{RESET}" if pass_ok else f"{RED}X{RESET}"
        api_status = f"{GREEN}OK{RESET}" if api_ok else f"{RED}X{RESET}"
        secret_status = f"{GREEN}OK{RESET}" if secret_ok else f"{RED}X{RESET}"
        pair_status = f"{GREEN}{settings['trading_pair']}{RESET}" if pair_ok else f"{RED}X{RESET}"
        qty_status = f"{GREEN}OK{RESET}" if buy_qty_ok and sell_qty_ok else f"{RED}X{RESET}"
        exec_mode = f"{BOLD}{GREEN}AKTIF{RESET}" if exec_binance else f"{BOLD}{YELLOW}NONAKTIF{RESET}"

        print(f" {BOLD}Status Email :{RESET} [{email_status}] Email | [{pass_status}] App Pass")
        print(f" {BOLD}Status Binance:{RESET} [{api_status}] API | [{secret_status}] Secret | [{pair_status}] Pair | [{qty_status}] Qty | Eksekusi [{exec_mode}]")
        print(f"{DIM}{'-' * 55}{RESET}")

        choice = input(f"{BOLD}Masukkan pilihan Anda (1/2/3): {RESET}").strip()

        if choice == '1':
            # Validasi sebelum memulai
            can_start = True
            error_messages = []
            if not email_ok or not pass_ok:
                error_messages.append("Pengaturan Email (Alamat/App Password) belum lengkap!")
                can_start = False

            if exec_binance:
                if not BINANCE_AVAILABLE:
                    error_messages.append("Eksekusi Binance aktif tapi library 'python-binance' tidak ditemukan!")
                    can_start = False
                if not api_ok or not secret_ok or not pair_ok:
                     error_messages.append("Pengaturan Binance (API/Secret/Pair) belum lengkap!")
                     can_start = False
                # Kuantitas hanya dicek jika eksekusi aktif
                if not buy_qty_ok:
                     error_messages.append("Kuantitas Beli (buy_quote_quantity) harus > 0.")
                     can_start = False
                # Hanya warning jika sell qty = 0, karena mungkin hanya ingin buy
                if settings['sell_base_quantity'] == 0 :
                    print(f"{YELLOW}[WARN] Kuantitas Jual (sell_base_quantity) adalah 0. Aksi SELL tidak akan tereksekusi.{RESET}")
                    time.sleep(1.5) # Tampilkan warning sebentar
                elif settings['sell_base_quantity'] < 0: # Error jika < 0
                    error_messages.append("Kuantitas Jual (sell_base_quantity) tidak valid (< 0).")
                    can_start = False


            if can_start:
                clear_screen()
                mode = "Email & Binance Order" if exec_binance else "Email Listener Only"
                draw_box(f"Memulai Mode: {mode}", GREEN, 55)
                start_listening(settings)
                print(f"\n{YELLOW}{BOLD}[INFO] Kembali ke Menu Utama...{RESET}")
                time.sleep(2)
            else:
                print(f"\n{RED}{BOLD}--- TIDAK BISA MEMULAI ---{RESET}")
                for msg in error_messages:
                    print(f"{RED} - {msg}{RESET}")
                print(f"{YELLOW}Silakan masuk ke menu [{BOLD}2{RESET}] Pengaturan untuk memperbaiki.{RESET}")
                input("\nTekan Enter untuk kembali ke menu...") # Tunggu user

        elif choice == '2':
            show_settings(settings)
            settings = load_settings() # Load ulang jika ada perubahan
        elif choice == '3':
            clear_screen()
            draw_box("Sampai Jumpa!", CYAN, 30)
            typing_effect("Terima kasih telah menggunakan Exora AI Listener!", 0.05, CYAN)
            sys.exit(0)
        else:
            print(f"\n{RED}{BOLD}Pilihan tidak valid!{RESET} Masukkan 1, 2, atau 3.")
            time.sleep(1.5)

# --- Entry Point ---
if __name__ == "__main__":
    try:
        clear_screen()
        main_menu()
    except KeyboardInterrupt:
        # Signal handler sudah menangani ini, tapi sebagai fallback
        clear_line()
        print(f"\n{YELLOW}{BOLD}[WARN] Program dihentikan paksa.{RESET}")
        sys.exit(1)
    except Exception as e:
        clear_screen()
        print(f"\n{BOLD}{RED}===== 💥 ERROR KRITIS TAK TERDUGA 💥 ====={RESET}")
        traceback.print_exc()
        print(f"\n{RED}Terjadi error fatal yang tidak tertangani: {e}{RESET}")
        print("Program akan keluar.")
        input("Tekan Enter untuk keluar...") # Biar user sempat baca
        sys.exit(1)
