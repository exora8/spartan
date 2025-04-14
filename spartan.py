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
import itertools # Untuk spinner

# --- Binance Integration ---
try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException, BinanceOrderException
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False
    print("\n" + "\033[93m" + "[WARN] Library 'python-binance' tidak ditemukan." + "\033[0m") # YELLOW
    print("\033[93m" + "[WARN] Fitur eksekusi order Binance tidak akan berfungsi." + "\033[0m")
    print("\033[93m" + "[WARN] Install dengan: pip install python-binance" + "\033[0m" + "\n")
    # Definisikan exception dummy jika library tidak ada agar script tidak crash
    class BinanceAPIException(Exception): pass
    class BinanceOrderException(Exception): pass
    class Client: # Dummy class
        SIDE_BUY = 'BUY' # Tambahkan konstanta dummy
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

# Variabel global untuk mengontrol loop utama
running = True

# --- Kode Warna ANSI ---
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m" # Efek redup
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
WHITE = "\033[97m"

# --- Karakter Spinner ---
spinner = itertools.cycle(['-', '\\', '|', '/'])
# spinner = itertools.cycle([' K', ' Ke', ' Ker', ' Kerj', ' Kerja', 'Kerja.', 'Kerja..', 'Kerja...']) # Alternatif spinner teks

# --- Fungsi Penanganan Sinyal (Ctrl+C) ---
def signal_handler(sig, frame):
    global running
    print(f"\n{YELLOW}{BOLD}[WARN] Ctrl+C terdeteksi. Menghentikan program...{RESET}")
    running = False
    # Kasih sedikit waktu untuk loop utama berhenti secara alami jika memungkinkan
    time.sleep(0.5)
    print(f"{RED}{BOLD}[EXIT] Keluar dari program.{RESET}")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# --- Fungsi Konfigurasi ---
def load_settings():
    """Memuat pengaturan dari file JSON, memastikan semua kunci ada."""
    settings = DEFAULT_SETTINGS.copy() # Mulai dengan default
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_settings = json.load(f)
                # Hanya update kunci yang ada di default, hindari kunci tak dikenal
                for key in DEFAULT_SETTINGS:
                    if key in loaded_settings:
                        settings[key] = loaded_settings[key]

                # Validasi tambahan setelah load
                if not isinstance(settings.get("check_interval_seconds"), int) or settings.get("check_interval_seconds") < 5:
                    print(f"{YELLOW}[WARN] Interval cek di '{CONFIG_FILE}' < 5 detik atau tipe salah, direset ke 10.{RESET}")
                    settings["check_interval_seconds"] = 10

                if not isinstance(settings.get("buy_quote_quantity"), (int, float)) or settings.get("buy_quote_quantity") <= 0:
                     print(f"{YELLOW}[WARN] 'buy_quote_quantity' tidak valid (harus angka > 0), direset ke {DEFAULT_SETTINGS['buy_quote_quantity']}.{RESET}")
                     settings["buy_quote_quantity"] = DEFAULT_SETTINGS['buy_quote_quantity']

                if not isinstance(settings.get("sell_base_quantity"), (int, float)) or settings.get("sell_base_quantity") < 0: # Allow 0
                     print(f"{YELLOW}[WARN] 'sell_base_quantity' tidak valid (harus angka >= 0), direset ke {DEFAULT_SETTINGS['sell_base_quantity']}.{RESET}")
                     settings["sell_base_quantity"] = DEFAULT_SETTINGS['sell_base_quantity']

                if not isinstance(settings.get("execute_binance_orders"), bool):
                    print(f"{YELLOW}[WARN] 'execute_binance_orders' tidak valid (harus true/false), direset ke False.{RESET}")
                    settings["execute_binance_orders"] = False

                # Save back any corrections made & remove unknown keys
                save_settings(settings)

        except json.JSONDecodeError:
            print(f"{RED}[ERROR] File konfigurasi '{CONFIG_FILE}' rusak. Menggunakan default & menyimpan ulang.{RESET}")
            save_settings(settings) # Simpan default yang bersih
        except Exception as e:
            print(f"{RED}[ERROR] Gagal memuat konfigurasi: {e}{RESET}")
            print(f"{YELLOW}[WARN] Menggunakan pengaturan default sementara.{RESET}")
            # Tidak menyimpan ulang jika error tidak diketahui
    else:
        # Jika file tidak ada, simpan default awal
        print(f"{YELLOW}[INFO] File konfigurasi '{CONFIG_FILE}' tidak ditemukan. Membuat dengan nilai default.{RESET}")
        save_settings(settings)
    return settings

def save_settings(settings):
    """Menyimpan pengaturan ke file JSON."""
    try:
        # Filter hanya key yang ada di default sebelum menyimpan
        settings_to_save = {key: settings[key] for key in DEFAULT_SETTINGS if key in settings}

        # Pastikan tipe data benar sebelum menyimpan
        settings_to_save['check_interval_seconds'] = int(settings_to_save.get('check_interval_seconds', 10))
        settings_to_save['buy_quote_quantity'] = float(settings_to_save.get('buy_quote_quantity', 11.0))
        settings_to_save['sell_base_quantity'] = float(settings_to_save.get('sell_base_quantity', 0.0))
        settings_to_save['execute_binance_orders'] = bool(settings_to_save.get('execute_binance_orders', False))

        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings_to_save, f, indent=4, sort_keys=True) # Urutkan kunci agar lebih rapi
        # print(f"{GREEN}[INFO] Pengaturan berhasil disimpan ke '{CONFIG_FILE}'{RESET}") # Komentari agar tidak terlalu verbose saat auto-save
    except Exception as e:
        print(f"{RED}[ERROR] Gagal menyimpan konfigurasi: {e}{RESET}")

# --- Fungsi Utilitas ---
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_separator(char="=", length=50, color=CYAN):
    print(f"{color}{char * length}{RESET}")

def get_timestamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def decode_mime_words(s):
    # Fungsi ini krusial dan biarkan seperti adanya
    if not s:
        return ""
    decoded_parts = decode_header(s)
    result = []
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            # Handle potential errors during decoding gracefully
            try:
                result.append(part.decode(encoding or 'utf-8', errors='replace'))
            except (LookupError, ValueError): # Handle unknown encoding or other decode errors
                result.append(part.decode('utf-8', errors='replace')) # Fallback to utf-8 replace
        else:
            result.append(part)
    return "".join(result)

def get_text_from_email(msg):
    # Fungsi ini krusial dan biarkan seperti adanya
    text_content = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            # Get text/plain parts that are not explicitly attachments
            if content_type == "text/plain" and "attachment" not in content_disposition.lower():
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    text_content += payload.decode(charset, errors='replace') + "\n" # Tambah newline antar bagian
                except Exception as e:
                    print(f"{YELLOW}[WARN] Tidak bisa mendekode bagian email (text/plain): {e}{RESET}")
            # Tambahan: Coba ekstrak text/html jika text/plain tidak ada (opsional, bisa noisy)
            # elif content_type == "text/html" and "attachment" not in content_disposition.lower() and not text_content:
            #     try:
            #         charset = part.get_content_charset() or 'utf-8'
            #         payload = part.get_payload(decode=True)
            #         # Simple HTML tag stripping (bisa diganti library yg lebih canggih jika perlu)
            #         import re
            #         html_content = payload.decode(charset, errors='replace')
            #         text_content += re.sub('<[^<]+?>', '', html_content) + "\n"
            #         print(f"{DIM}[DEBUG] Mengekstrak dari text/html karena text/plain kosong/error.{RESET}")
            #     except Exception as e:
            #         print(f"{YELLOW}[WARN] Tidak bisa mendekode bagian email (text/html): {e}{RESET}")

    else: # Not multipart
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                text_content = payload.decode(charset, errors='replace')
            except Exception as e:
                 print(f"{YELLOW}[WARN] Tidak bisa mendekode body email (non-multipart): {e}{RESET}")
        # else: # Handle non-plain text single part if needed
        #     print(f"{DIM}[DEBUG] Email non-multipart bukan text/plain ({content_type}).{RESET}")

    return text_content.lower() # Pastikan selalu lower case

# --- Fungsi Beep ---
def trigger_beep(action):
    try:
        if action == "buy":
            print(f"{MAGENTA}{BOLD}⚡ BEEP BUY! ⚡{RESET}")
            # Coba 'tput bel' sebagai alternatif cross-platform sederhana jika 'beep' tidak ada
            try:
                subprocess.run(["beep", "-f", "1000", "-l", "500", "-D", "500", "-r", "5"], check=True, capture_output=True, text=True, timeout=5)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                print("\a", end='') # Fallback ke system bell standar
                # os.system('tput bel') # Alternatif lain
        elif action == "sell":
            print(f"{MAGENTA}{BOLD}⚡ BEEP SELL! ⚡{RESET}")
            try:
                subprocess.run(["beep", "-f", "700", "-l", "1000", "-D", "500", "-r", "2"], check=True, capture_output=True, text=True, timeout=5)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                 print("\a", end='') # Fallback
                 # os.system('tput bel')
        else:
             print(f"{YELLOW}[WARN] Aksi beep tidak dikenal '{action}'.{RESET}")
    except subprocess.CalledProcessError as e:
        print(f"{RED}[ERROR] Gagal menjalankan 'beep': {e}{RESET}")
        if e.stderr: print(f"{RED}         Stderr: {e.stderr.strip()}{RESET}")
    except Exception as e:
        print(f"{RED}[ERROR] Kesalahan tak terduga saat beep: {e}{RESET}")

# --- Fungsi Eksekusi Binance ---
def get_binance_client(settings):
    """Membuat instance Binance client."""
    if not BINANCE_AVAILABLE:
        # Pesan sudah ditampilkan di awal, tidak perlu diulang
        return None
    if not settings.get('binance_api_key') or not settings.get('binance_api_secret'):
        print(f"{RED}{BOLD}[BINANCE ERROR] API Key atau Secret Key Binance belum diatur!{RESET}")
        return None
    try:
        print(f"{DIM}[BINANCE] Menghubungkan ke Binance API...{RESET}", end='\r')
        client = Client(settings['binance_api_key'], settings['binance_api_secret'])
        client.ping() # Test koneksi
        print(f"{GREEN}{BOLD}✅ [BINANCE] Koneksi API Berhasil!                 {RESET}")
        # Get server time (optional, good check)
        # server_time = client.get_server_time()
        # print(f"{DIM}[BINANCE] Server Time: {datetime.datetime.fromtimestamp(server_time['serverTime']/1000)}{RESET}")
        return client
    except BinanceAPIException as e:
        print(f"{RED}{BOLD}❌ [BINANCE ERROR] Gagal koneksi/autentikasi: {e.status_code} - {e.message}{RESET}")
        return None
    except Exception as e:
        print(f"{RED}{BOLD}❌ [BINANCE ERROR] Gagal membuat client: {e}{RESET}")
        return None

def execute_binance_order(client, settings, side):
    """Mengeksekusi order MARKET BUY atau SELL di Binance."""
    if not client:
        print(f"{RED}[BINANCE] Eksekusi dibatalkan, client tidak valid.{RESET}")
        return False
    if not settings.get("execute_binance_orders", False):
        print(f"{YELLOW}[BINANCE] Eksekusi order dinonaktifkan di pengaturan. Order dilewati.{RESET}")
        return False # Dianggap tidak gagal, hanya dilewati

    pair = settings.get('trading_pair', '').upper()
    if not pair:
        print(f"{RED}{BOLD}[BINANCE ERROR] Trading pair belum diatur!{RESET}")
        return False

    order_details = {}
    action_desc = ""
    side_color = GREEN if side == Client.SIDE_BUY else RED

    try:
        if side == Client.SIDE_BUY:
            quote_qty = settings.get('buy_quote_quantity', 0.0)
            if quote_qty <= 0:
                 print(f"{RED}{BOLD}[BINANCE ERROR] Kuantitas Beli (buy_quote_quantity) harus > 0.{RESET}")
                 return False
            order_details = {
                'symbol': pair,
                'side': Client.SIDE_BUY,
                'type': Client.ORDER_TYPE_MARKET,
                'quoteOrderQty': quote_qty
            }
            action_desc = f"{side_color}{BOLD}MARKET BUY{RESET} {quote_qty} USDT senilai {pair}" # Asumsi quote USDT

        elif side == Client.SIDE_SELL:
            base_qty = settings.get('sell_base_quantity', 0.0)
            if base_qty <= 0:
                 # Kasih warning jika 0, karena setting defaultnya 0
                 if settings.get('sell_base_quantity') == 0:
                    print(f"{YELLOW}[BINANCE WARN] Kuantitas Jual (sell_base_quantity) masih 0. Order SELL dilewati.{RESET}")
                 else:
                    print(f"{RED}{BOLD}[BINANCE ERROR] Kuantitas Jual (sell_base_quantity) harus > 0.{RESET}")
                 return False
            order_details = {
                'symbol': pair,
                'side': Client.SIDE_SELL,
                'type': Client.ORDER_TYPE_MARKET,
                'quantity': base_qty # Jual sejumlah base asset
            }
            action_desc = f"{side_color}{BOLD}MARKET SELL{RESET} {base_qty} {pair.replace('USDT', '')}" # Asumsi pair xxxUSDT

        else:
            print(f"{RED}{BOLD}[BINANCE ERROR] Sisi order tidak valid: {side}{RESET}")
            return False

        print(f"{CYAN}🛒 [BINANCE] Mencoba eksekusi: {action_desc}...{RESET}")
        order_result = client.create_order(**order_details)

        print(f"{GREEN}{BOLD}✅ [BINANCE SUCCESS] Order Berhasil Dieksekusi!{RESET}")
        print(f"{DIM}-------------------------------------------{RESET}")
        print(f"{DIM}  Order ID : {order_result.get('orderId')}{RESET}")
        print(f"{DIM}  Symbol   : {order_result.get('symbol')}{RESET}")
        print(f"{DIM}  Side     : {order_result.get('side')}{RESET}")
        print(f"{DIM}  Status   : {order_result.get('status')}{RESET}")
        # Info fill (harga rata-rata dan kuantitas terisi)
        if order_result.get('fills'):
            total_qty = sum(float(f['qty']) for f in order_result['fills'])
            total_quote_qty = sum(float(f['cummulativeQuoteQty']) for f in order_result['fills']) # Pakai cummulativeQuoteQty
            avg_price = total_quote_qty / total_qty if total_qty else 0
            print(f"{DIM}  Avg Price: {avg_price:.8f}{RESET}") # Sesuaikan presisi jika perlu
            print(f"{DIM}  Filled Qty: {total_qty:.8f} (Base){RESET}")
            print(f"{DIM}  Total Cost: {total_quote_qty:.4f} (Quote){RESET}")
        print(f"{DIM}-------------------------------------------{RESET}")
        return True

    except BinanceAPIException as e:
        print(f"{RED}{BOLD}❌ [BINANCE API ERROR] Gagal eksekusi order: {e.status_code} - {e.message}{RESET}")
        if e.code == -2010: print(f"{RED}         -> Kemungkinan SALDO TIDAK CUKUP.{RESET}")
        elif e.code == -1121: print(f"{RED}         -> Trading pair '{pair}' TIDAK VALID.{RESET}")
        elif e.code == -1013 or 'MIN_NOTIONAL' in str(e.message): print(f"{RED}         -> Order size TERLALU KECIL (cek MIN_NOTIONAL).{RESET}")
        elif e.code == -1111 or 'LOT_SIZE' in str(e.message): print(f"{RED}         -> Kuantitas tidak sesuai LOT_SIZE filter.{RESET}")
        return False
    except BinanceOrderException as e:
        print(f"{RED}{BOLD}❌ [BINANCE ORDER ERROR] Gagal eksekusi order: {e.status_code} - {e.message}{RESET}")
        return False
    except Exception as e:
        print(f"{RED}{BOLD}❌ [ERROR] Kesalahan tak terduga saat eksekusi order Binance:{RESET}")
        traceback.print_exc()
        return False

# --- Fungsi Pemrosesan Email ---
def process_email(mail, email_id, settings, binance_client): # Tambah binance_client
    """Mengambil, mem-parsing, dan memproses satu email, lalu eksekusi order jika sesuai."""
    global running
    if not running: return

    target_keyword_lower = settings['target_keyword'].lower()
    trigger_keyword_lower = settings['trigger_keyword'].lower()
    email_id_str = email_id.decode('utf-8')
    ts = get_timestamp()

    try:
        # print(f"{DIM}[DEBUG] Fetching email ID {email_id_str}...{RESET}")
        status, data = mail.fetch(email_id, "(RFC822)")
        if status != 'OK':
            print(f"{RED}[ERROR][{ts}] Gagal mengambil email ID {email_id_str}: {status}{RESET}")
            return

        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        subject = decode_mime_words(msg["Subject"])
        sender = decode_mime_words(msg["From"])


        print(f"\n{MAGENTA}📧 === Email Baru Diterima [{ts}] ==={RESET}")
        print(f"   {CYAN}ID    :{RESET} {email_id_str}")
        print(f"   {CYAN}Dari  :{RESET} {sender}")
        print(f"   {CYAN}Subjek:{RESET} {subject}")
        print(f"{MAGENTA}-------------------------------------------{RESET}")

        body = get_text_from_email(msg)
        # Gabungkan subjek dan body untuk pencarian keyword
        # Perhatikan: Jika keyword ada di signature email yang sama terus, bisa jadi false positive
        # Pertimbangkan hanya cari di body jika subjek terlalu umum: full_content = body
        full_content = (subject.lower() + " " + body)

        # Optional: Tampilkan snippet body untuk debugging
        # print(f"{DIM}--- Body Snippet ---{RESET}")
        # print(DIM + body[:200].replace('\n', ' ') + ('...' if len(body) > 200 else '') + RESET)
        # print(f"{DIM}--------------------{RESET}")


        if target_keyword_lower in full_content:
            print(f"{GREEN}🎯 [MATCH] Keyword target '{settings['target_keyword']}' DITEMUKAN!{RESET}")
            try:
                # Cari trigger SETELAH target
                target_index = full_content.find(target_keyword_lower)
                trigger_index = full_content.find(trigger_keyword_lower, target_index + len(target_keyword_lower))

                if trigger_index != -1:
                    start_word_index = trigger_index + len(trigger_keyword_lower)
                    # Ambil teks setelah trigger, bersihkan spasi di awal
                    text_after_trigger = full_content[start_word_index:].lstrip()
                    # Pisahkan kata pertama setelah trigger
                    words_after_trigger = text_after_trigger.split(maxsplit=1)

                    if words_after_trigger:
                        # Ambil kata pertama, bersihkan tanda baca umum, jadikan lowercase
                        action_word = words_after_trigger[0].strip('.,!?:;()[]{}').lower()
                        print(f"{GREEN}📌 [TRIGGER] Keyword trigger '{settings['trigger_keyword']}' ditemukan. Kata berikutnya: '{BOLD}{WHITE}{action_word.upper()}{RESET}{GREEN}'{RESET}")

                        # --- Trigger Aksi (Beep dan/atau Binance) ---
                        order_executed_attempted = False # Tandai apakah order sudah dicoba
                        if action_word == "buy":
                            trigger_beep("buy")
                            if settings.get("execute_binance_orders"):
                                if binance_client:
                                    execute_binance_order(binance_client, settings, Client.SIDE_BUY)
                                else:
                                    print(f"{YELLOW}[WARN] Eksekusi Binance aktif tapi client tidak siap.{RESET}")
                                order_executed_attempted = True

                        elif action_word == "sell":
                            trigger_beep("sell")
                            if settings.get("execute_binance_orders"):
                                if binance_client:
                                    execute_binance_order(binance_client, settings, Client.SIDE_SELL)
                                else:
                                     print(f"{YELLOW}[WARN] Eksekusi Binance aktif tapi client tidak siap.{RESET}")
                                order_executed_attempted = True
                        else:
                            print(f"{YELLOW}[WARN] Kata setelah '{settings['trigger_keyword']}' ({action_word}) bukan 'buy' atau 'sell'. Tidak ada aksi market.{RESET}")

                        # Info tambahan jika eksekusi diaktifkan tapi tidak terjadi
                        if settings.get("execute_binance_orders") and not order_executed_attempted and action_word in ["buy", "sell"]:
                            print(f"{YELLOW}[BINANCE] Eksekusi tidak dilakukan (client tidak siap atau aksi tidak valid).{RESET}")

                    else:
                        print(f"{YELLOW}[WARN] Tidak ada kata yang terbaca setelah '{settings['trigger_keyword']}'.{RESET}")
                else:
                     print(f"{YELLOW}[WARN] Keyword trigger '{settings['trigger_keyword']}' tidak ditemukan {BOLD}setelah{RESET}{YELLOW} keyword target '{settings['target_keyword']}'.{RESET}")

            except Exception as e:
                 print(f"{RED}[ERROR] Gagal parsing kata setelah trigger: {e}{RESET}")
                 # traceback.print_exc() # Uncomment for detailed debug
        else:
            print(f"{BLUE}💨 [SKIP] Keyword target '{settings['target_keyword']}' tidak ditemukan dalam email ini.{RESET}")

        # Tandai email sebagai sudah dibaca ('Seen')
        try:
            # print(f"{DIM}[SYS] Menandai email {email_id_str} sebagai 'Seen'...{RESET}")
            mail.store(email_id, '+FLAGS', '\\Seen')
        except Exception as e:
            print(f"{RED}[ERROR] Gagal menandai email {email_id_str} sebagai 'Seen': {e}{RESET}")
        print(f"{MAGENTA}==========================================={RESET}") # Penutup log email

    except Exception as e:
        print(f"{RED}{BOLD}[ERROR][{ts}] Gagal total memproses email ID {email_id_str}:{RESET}")
        traceback.print_exc()
        print(f"{MAGENTA}==========================================={RESET}")

# --- Fungsi Listening Utama ---
def start_listening(settings):
    """Memulai loop untuk memeriksa email baru dan menyiapkan client Binance."""
    global running, spinner
    running = True
    mail = None
    binance_client = None # Inisialisasi client Binance
    wait_time = 30 # Waktu tunggu sebelum reconnect error
    connection_attempts = 0

    # --- Setup Binance Client di Awal (jika diaktifkan) ---
    clear_screen()
    print_separator(char="*", color=MAGENTA)
    mode = "Email & Binance Order" if settings.get("execute_binance_orders") else "Email Listener Only"
    print(f"{MAGENTA}{BOLD}🚀 Memulai Mode: {mode} 🚀{RESET}")
    print_separator(char="*", color=MAGENTA)

    if settings.get("execute_binance_orders"):
        if not BINANCE_AVAILABLE:
             print(f"\n{RED}{BOLD}[FATAL] Eksekusi Binance diaktifkan tapi library python-binance tidak ada!{RESET}")
             print(f"{YELLOW}Nonaktifkan 'Eksekusi Order' di Pengaturan atau install library (`pip install python-binance`).{RESET}")
             running = False
             return
        print(f"\n{CYAN}🔗 [SETUP] Menginisialisasi koneksi Binance API...{RESET}")
        binance_client = get_binance_client(settings)
        if not binance_client:
            print(f"{RED}{BOLD}[FATAL] Gagal menginisialisasi Binance Client.{RESET}")
            print(f"{YELLOW}         Periksa API Key/Secret, koneksi internet, dan izin API di Binance.")
            print(f"{YELLOW}         Eksekusi order TIDAK AKAN berjalan. Lanjutkan dengan listener email saja? (y/n){RESET}")
            choice = input("> ").lower()
            if choice != 'y':
                running = False
                return
            else:
                print(f"{YELLOW}[WARN] Melanjutkan tanpa eksekusi Binance.{RESET}")
                settings['execute_binance_orders'] = False # Nonaktifkan sementara untuk sesi ini
        else:
            print(f"{GREEN}{BOLD}👍 [SETUP] Binance Client Siap!{RESET}")
    else:
        print(f"\n{YELLOW}ℹ️ [INFO] Eksekusi order Binance dinonaktifkan di pengaturan.{RESET}")
        if BINANCE_AVAILABLE:
             print(f"{DIM}   (Anda bisa mengaktifkannya di menu Pengaturan){RESET}")

    print_separator(color=CYAN)
    print(f"{CYAN}📧 [SETUP] Menyiapkan Listener Email...{RESET}")
    print(f"{DIM}   Akun : {settings['email_address']}{RESET}")
    print(f"{DIM}   Server: {settings['imap_server']}{RESET}")
    print_separator(color=CYAN)
    time.sleep(1) # Jeda sedikit

    # --- Loop Utama Email Listener ---
    while running:
        try:
            # --- Koneksi IMAP ---
            if not mail or mail.state != 'SELECTED':
                connection_attempts += 1
                print(f"{CYAN}📡 [{connection_attempts}] Menghubungkan ke IMAP ({settings['imap_server']})...{RESET}", end='\r')
                mail = imaplib.IMAP4_SSL(settings['imap_server'])
                print(f"{GREEN}✅ Terhubung ke {settings['imap_server']}             {RESET}")
                print(f"{CYAN}🔑 Login sebagai {settings['email_address']}...{RESET}", end='\r')
                mail.login(settings['email_address'], settings['app_password'])
                print(f"{GREEN}🔓 Login Email Berhasil! {BOLD}({settings['email_address']}){RESET}")
                mail.select("inbox")
                print(f"{GREEN}📥 Masuk ke INBOX. Siap mendengarkan...{RESET}")
                print(f"{DIM}(Tekan Ctrl+C untuk berhenti){RESET}")
                print_separator(char="-", length=50, color=BLUE)
                connection_attempts = 0 # Reset counter on success

            # --- Loop Cek Email ---
            while running:
                # Check IMAP connection health
                try:
                    status, _ = mail.noop()
                    if status != 'OK':
                        print(f"\n{YELLOW}[WARN] Koneksi IMAP NOOP gagal ({status}). Mencoba reconnect...{RESET}")
                        break # Break inner loop to reconnect
                except (imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError) as NopErr:
                     print(f"\n{YELLOW}[WARN] Koneksi IMAP terputus ({type(NopErr).__name__}). Mencoba reconnect...{RESET}")
                     break # Break inner loop to reconnect

                # Check Binance connection health (if applicable)
                if binance_client and settings.get("execute_binance_orders"):
                    try:
                         # Ping is cheap and checks auth + connectivity
                         binance_client.ping()
                         # print(f"{DIM}Binance ping OK{RESET}", end='\r') # Terlalu berisik
                    except Exception as PingErr:
                         print(f"\n{YELLOW}{BOLD}[BINANCE WARN] Ping ke Binance API gagal ({type(PingErr).__name__}).{RESET}")
                         print(f"{YELLOW}               Mencoba membuat ulang client...{RESET}")
                         # Coba buat ulang client sekali
                         binance_client = get_binance_client(settings)
                         if not binance_client:
                              print(f"{RED}{BOLD}       Gagal membuat ulang Binance client! Eksekusi order mungkin gagal.{RESET}")
                              # Potentially disable execution temporarily?
                              # settings['execute_binance_orders'] = False
                         else:
                              print(f"{GREEN}{BOLD}       Client Binance berhasil dibuat ulang.{RESET}")
                         time.sleep(5) # Beri jeda setelah error ping


                # --- Cek Email Baru (UNSEEN) ---
                status, messages = mail.search(None, '(UNSEEN)')
                if status != 'OK':
                     print(f"\n{RED}[ERROR] Gagal mencari email: {status}{RESET}")
                     break # Coba reconnect

                email_ids = messages[0].split()
                if email_ids:
                    # Hapus pesan tunggu/spinner sebelum print email baru
                    print(" " * 70, end='\r')
                    print(f"\n{GREEN}{BOLD}✨ Ditemukan {len(email_ids)} email baru! Memproses... ✨{RESET}")
                    for email_id in email_ids:
                        if not running: break
                        process_email(mail, email_id, settings, binance_client)
                    if not running: break
                    print_separator(char="-", length=50, color=BLUE)
                    print(f"{GREEN}✅ Selesai memproses. Kembali mendengarkan...{RESET}")
                else:
                    # --- Tidak ada email baru, tampilkan spinner ---
                    wait_interval = settings['check_interval_seconds']
                    wait_message = f"{BLUE}🕒 Tidak ada email baru. Menunggu {wait_interval} detik {next(spinner)}{RESET}"
                    print(wait_message, end='\r')
                    # Tidur per detik agar responsif terhadap Ctrl+C
                    for _ in range(wait_interval):
                         if not running: break
                         time.sleep(1)
                         wait_message = f"{BLUE}🕒 Tidak ada email baru. Menunggu {wait_interval - (_ + 1)} detik {next(spinner)}{RESET} " # Tambah spasi di akhir
                         print(wait_message, end='\r')
                    if not running: break
                    # Hapus pesan tunggu setelah selesai
                    print(" " * len(wait_message) * 2, end='\r') # Hapus baris spinner

            # --- Keluar dari loop inner (karena error / stop) ---
            if mail and mail.state == 'SELECTED':
                try:
                    # print(f"{DIM}Closing mailbox...{RESET}")
                    mail.close()
                except Exception as e:
                    # print(f"{YELLOW}[WARN] Error closing mailbox: {e}{RESET}")
                    pass # Abaikan error saat close

        # --- Exception Handling untuk Koneksi / Login ---
        except (imaplib.IMAP4.error, imaplib.IMAP4.abort) as e:
            print(f"\n{RED}{BOLD}[ERROR] Kesalahan IMAP: {e}{RESET}")
            # Periksa error spesifik login
            if "authentication failed" in str(e).lower() \
               or "invalid credentials" in str(e).lower() \
               or "username and password not accepted" in str(e).lower() \
               or "[AUTHENTICATIONFAILED]" in str(e).upper():
                print(f"{RED}{BOLD}[FATAL] Login Email GAGAL! Periksa alamat email dan App Password di Pengaturan.{RESET}")
                print(f"{YELLOW}         Pastikan juga akses IMAP diaktifkan di akun Gmail/Email Anda.{RESET}")
                running = False # Hentikan loop utama
                return # Keluar dari fungsi start_listening
            print(f"{YELLOW}[WARN] Akan mencoba menghubungkan kembali dalam {wait_time} detik...{RESET}")
            time.sleep(wait_time)
        except (ConnectionError, OSError, socket.error, socket.gaierror) as e:
             print(f"\n{RED}{BOLD}[ERROR] Kesalahan Koneksi Jaringan: {e}{RESET}")
             print(f"{YELLOW}[WARN] Periksa koneksi internet Anda. Mencoba lagi dalam {wait_time} detik...{RESET}")
             time.sleep(wait_time)
        except Exception as e:
            print(f"\n{RED}{BOLD}[ERROR] Kesalahan tak terduga di loop utama:{RESET}")
            traceback.print_exc()
            print(f"{YELLOW}[WARN] Terjadi error. Mencoba recovery dalam {wait_time} detik...{RESET}")
            time.sleep(wait_time)
        finally:
            # --- Cleanup sebelum retry atau exit ---
            if mail:
                try:
                    if mail.state != 'LOGOUT':
                        # print(f"{DIM}Logging out from IMAP...{RESET}")
                        mail.logout()
                except Exception:
                    pass # Abaikan error saat logout
            mail = None # Set None agar koneksi ulang terjadi di iterasi berikutnya
            if running:
                # Beri jeda singkat sebelum mencoba koneksi ulang
                time.sleep(3)

    print(f"\n{YELLOW}{BOLD}🛑 Listener dihentikan.{RESET}")

# --- Fungsi Menu Pengaturan ---
def show_settings(settings):
    """Menampilkan dan mengedit pengaturan, termasuk Binance."""
    while True:
        clear_screen()
        print(f"{BOLD}{CYAN}⚙️=== Pengaturan Email & Binance Listener ===⚙️{RESET}")

        print(f"\n{BLUE}--- Email Settings ---{RESET}")
        print(f" 1. {CYAN}Alamat Email{RESET}   : {settings['email_address'] or f'{YELLOW}[Belum diatur]{RESET}'}")
        # Tampilkan beberapa karakter password untuk indikasi, sisanya bintang
        pwd_display = settings['app_password'][:2] + '*' * (len(settings['app_password']) - 2) if len(settings['app_password']) > 1 else settings['app_password']
        print(f" 2. {CYAN}App Password{RESET}   : {pwd_display or f'{YELLOW}[Belum diatur]{RESET}'}")
        print(f" 3. {CYAN}Server IMAP{RESET}    : {settings['imap_server']}")
        print(f" 4. {CYAN}Interval Cek{RESET}   : {settings['check_interval_seconds']} detik {DIM}(min: 5){RESET}")
        print(f" 5. {CYAN}Keyword Target{RESET} : {BOLD}{settings['target_keyword']}{RESET}")
        print(f" 6. {CYAN}Keyword Trigger{RESET}: {BOLD}{settings['trigger_keyword']}{RESET}")

        print(f"\n{BLUE}--- Binance Settings ---{RESET}")
        binance_status = f"{GREEN}✅ Tersedia{RESET}" if BINANCE_AVAILABLE else f"{RED}❌ Tidak Tersedia (Install 'python-binance'){RESET}"
        print(f" Library Status      : {binance_status}")
        # Tampilkan sebagian kecil key/secret untuk indikasi
        api_key_disp = settings['binance_api_key'][:4] + '...' + settings['binance_api_key'][-4:] if len(settings['binance_api_key']) > 8 else settings['binance_api_key']
        api_sec_disp = settings['binance_api_secret'][:4] + '...' + settings['binance_api_secret'][-4:] if len(settings['binance_api_secret']) > 8 else settings['binance_api_secret']
        print(f" 7. {CYAN}API Key{RESET}        : {api_key_disp or f'{YELLOW}[Belum diatur]{RESET}'}")
        print(f" 8. {CYAN}API Secret{RESET}     : {api_sec_disp or f'{YELLOW}[Belum diatur]{RESET}'}")
        print(f" 9. {CYAN}Trading Pair{RESET}   : {BOLD}{settings['trading_pair'] or f'{YELLOW}[Belum diatur]{RESET}'}{RESET}")
        print(f"10. {CYAN}Buy Quote Qty{RESET}  : {settings['buy_quote_quantity']} {DIM}(Mis: USDT, harus > 0){RESET}")
        print(f"11. {CYAN}Sell Base Qty{RESET}  : {settings['sell_base_quantity']} {DIM}(Mis: BTC, harus >= 0){RESET}")
        exec_status = f"{GREEN}{BOLD}✅ AKTIF{RESET}" if settings['execute_binance_orders'] else f"{RED}❌ NONAKTIF{RESET}"
        print(f"12. {CYAN}Eksekusi Order{RESET} : {exec_status}")
        print_separator(char="-", length=40, color=CYAN)

        print(f"\n{YELLOW}Pilih Aksi:{RESET}")
        print(f" {GREEN}E{RESET} - Edit Pengaturan")
        print(f" {RED}K{RESET} - Kembali ke Menu Utama")
        print_separator(char="-", length=40, color=CYAN)

        choice = input("Pilihan Anda (E/K): ").lower().strip()

        if choice == 'e':
            print(f"\n{BOLD}{MAGENTA}--- Edit Pengaturan ---{RESET}")
            print(f"{DIM}(Kosongkan input jika tidak ingin mengubah nilai){RESET}")

            # --- Edit Email ---
            print(f"\n{CYAN}--- Email ---{RESET}")
            new_val = input(f" 1. Email [{settings['email_address']}]: ").strip()
            if new_val: settings['email_address'] = new_val

            # Gunakan getpass untuk menyembunyikan input password
            try:
                current_pass_display = settings['app_password'][:2] + '...' if settings['app_password'] else '[Kosong]'
                new_pass = getpass.getpass(f" 2. App Password Baru [{current_pass_display}] (ketik untuk ubah): ").strip()
                if new_pass:
                    settings['app_password'] = new_pass
                    print(f"   {GREEN}Password diperbarui.{RESET}")
            except Exception as e:
                print(f"\n{YELLOW}[WARN] Tidak bisa menggunakan getpass (mungkin di IDE tertentu). Input password akan terlihat.{RESET}")
                new_pass = input(f" 2. App Password Baru [{current_pass_display}] (ketik untuk ubah): ").strip()
                if new_pass: settings['app_password'] = new_pass

            new_val = input(f" 3. Server IMAP [{settings['imap_server']}]: ").strip()
            if new_val: settings['imap_server'] = new_val
            while True:
                new_val_str = input(f" 4. Interval (detik) [{settings['check_interval_seconds']}], min 5: ").strip()
                if not new_val_str: break
                try:
                    new_interval = int(new_val_str)
                    if new_interval >= 5:
                        settings['check_interval_seconds'] = new_interval
                        break
                    else: print(f"   {RED}[ERROR] Interval minimal 5 detik.{RESET}")
                except ValueError: print(f"   {RED}[ERROR] Masukkan angka bulat.{RESET}")
            new_val = input(f" 5. Keyword Target [{settings['target_keyword']}]: ").strip()
            if new_val: settings['target_keyword'] = new_val
            new_val = input(f" 6. Keyword Trigger [{settings['trigger_keyword']}]: ").strip()
            if new_val: settings['trigger_keyword'] = new_val

             # --- Edit Binance ---
            print(f"\n{CYAN}--- Binance ---{RESET}")
            if not BINANCE_AVAILABLE:
                 print(f"{YELLOW}   (Library Binance tidak terinstall, pengaturan API mungkin tidak akan berfungsi){RESET}")

            new_val = input(f" 7. API Key [{api_key_disp}]: ").strip()
            if new_val: settings['binance_api_key'] = new_val
            # Gunakan getpass juga untuk secret key
            try:
                current_secret_display = settings['binance_api_secret'][:4] + '...' if settings['binance_api_secret'] else '[Kosong]'
                new_secret = getpass.getpass(f" 8. API Secret Baru [{current_secret_display}] (ketik untuk ubah): ").strip()
                if new_secret:
                    settings['binance_api_secret'] = new_secret
                    print(f"   {GREEN}Secret Key diperbarui.{RESET}")
            except Exception as e:
                 print(f"\n{YELLOW}[WARN] Tidak bisa menggunakan getpass. Input Secret Key akan terlihat.{RESET}")
                 new_secret = input(f" 8. API Secret Baru [{current_secret_display}] (ketik untuk ubah): ").strip()
                 if new_secret: settings['binance_api_secret'] = new_secret

            new_val = input(f" 9. Trading Pair (e.g., BTCUSDT) [{settings['trading_pair']}]: ").strip().upper()
            if new_val: settings['trading_pair'] = new_val
            while True:
                 new_val_str = input(f"10. Buy Quote Qty (mis: 11.0 USDT) [{settings['buy_quote_quantity']}], harus > 0: ").strip()
                 if not new_val_str: break
                 try:
                     new_qty = float(new_val_str)
                     if new_qty > 0:
                         settings['buy_quote_quantity'] = new_qty
                         break
                     else: print(f"   {RED}[ERROR] Kuantitas Beli harus lebih besar dari 0.{RESET}")
                 except ValueError: print(f"   {RED}[ERROR] Masukkan angka (e.g., 11.0 atau 15).{RESET}")
            while True:
                 new_val_str = input(f"11. Sell Base Qty (mis: 0.0005 BTC) [{settings['sell_base_quantity']}], harus >= 0: ").strip()
                 if not new_val_str: break
                 try:
                     new_qty = float(new_val_str)
                     if new_qty >= 0: # Allow 0
                         settings['sell_base_quantity'] = new_qty
                         break
                     else: print(f"   {RED}[ERROR] Kuantitas Jual harus 0 atau lebih besar.{RESET}")
                 except ValueError: print(f"   {RED}[ERROR] Masukkan angka (e.g., 0.0005 atau 0).{RESET}")
            while True:
                 current_exec = settings['execute_binance_orders']
                 exec_prompt = f"{GREEN}Aktif{RESET}" if current_exec else f"{RED}Nonaktif{RESET}"
                 new_val_str = input(f"12. Eksekusi Order Binance? (y/n) [{exec_prompt}]: ").lower().strip()
                 if not new_val_str: break
                 if new_val_str == 'y':
                     settings['execute_binance_orders'] = True
                     print(f"   {GREEN}Eksekusi Binance Diaktifkan.{RESET}")
                     break
                 elif new_val_str == 'n':
                     settings['execute_binance_orders'] = False
                     print(f"   {RED}Eksekusi Binance Dinonaktifkan.{RESET}")
                     break
                 else: print(f"   {RED}[ERROR] Masukkan 'y' atau 'n'.{RESET}")


            save_settings(settings)
            print(f"\n{GREEN}{BOLD}💾 Pengaturan berhasil disimpan ke '{CONFIG_FILE}'{RESET}")
            input(f"{DIM}Tekan Enter untuk kembali ke menu pengaturan...{RESET}")

        elif choice == 'k':
            break # Keluar dari loop pengaturan
        else:
            print(f"{RED}[ERROR] Pilihan tidak valid. Masukkan 'E' atau 'K'.{RESET}")
            time.sleep(1.5)

# --- Fungsi Menu Utama ---
def main_menu():
    """Menampilkan menu utama aplikasi."""
    settings = load_settings() # Load sekali di awal

    while True:
        settings = load_settings() # Re-load setiap kali menu ditampilkan, antisipasi edit manual file
        clear_screen()
        print(f"{BOLD}{MAGENTA}╔═════════════════════════════════════════════════════════════╗{RESET}")
        print(f"{BOLD}{MAGENTA}║       🚀 Exora AI - Email & Binance Listener 🚀           ║{RESET}")
        print(f"{BOLD}{MAGENTA}╚═════════════════════════════════════════════════════════════╝{RESET}")
        print(f"\n{WHITE}{BOLD}Selamat datang! Pilih aksi:{RESET}\n")

        # Opsi Menu
        exec_mode_label = f" & {BOLD}Binance{RESET}" if settings.get("execute_binance_orders") else ""
        print(f" {GREEN}{BOLD}1.{RESET} Mulai Mendengarkan (Email{exec_mode_label})")
        print(f" {CYAN}{BOLD}2.{RESET} Pengaturan")
        print(f" {YELLOW}{BOLD}3.{RESET} Keluar")
        print_separator(char="-", length=61, color=MAGENTA)

        # Tampilkan status konfigurasi penting
        email_ok = bool(settings['email_address'])
        pass_ok = bool(settings['app_password'])
        api_ok = bool(settings['binance_api_key'])
        secret_ok = bool(settings['binance_api_secret'])
        pair_ok = bool(settings['trading_pair'])
        buy_qty_ok = settings['buy_quote_quantity'] > 0
        # Sell qty 0 dianggap OK karena mungkin hanya mau BUY
        sell_qty_ok = settings['sell_base_quantity'] >= 0
        exec_on = settings.get("execute_binance_orders", False)

        email_status = f"{GREEN}✔{RESET}" if email_ok else f"{RED}❌{RESET}"
        pass_status = f"{GREEN}✔{RESET}" if pass_ok else f"{RED}❌{RESET}"
        api_status = f"{GREEN}✔{RESET}" if api_ok else f"{RED}❌{RESET}"
        secret_status = f"{GREEN}✔{RESET}" if secret_ok else f"{RED}❌{RESET}"
        pair_status = f"{GREEN}✔{RESET}" if pair_ok else f"{RED}❌{RESET}"
        buy_status = f"{GREEN}✔{RESET}" if buy_qty_ok else f"{RED}❌{RESET}"
        sell_status = f"{GREEN}✔{RESET}" if sell_qty_ok else f"{RED}❌{RESET}" # Sell 0 is ok
        exec_status_label = f"{GREEN}AKTIF{RESET}" if exec_on else f"{YELLOW}NONAKTIF{RESET}"
        lib_status = f"{GREEN}OK{RESET}" if BINANCE_AVAILABLE else f"{RED}Missing!{RESET}"

        print(f"{BOLD}Status Cepat:{RESET}")
        print(f" Email      : [{email_status}] Email [{pass_status}] Passwd")
        print(f" Binance Lib: [{lib_status}] | Eksekusi: [{exec_status_label}]")
        if exec_on:
            print(f" Binance API: [{api_status}] Key [{secret_status}] Secret [{pair_status}] Pair [{buy_status}] BuyQty [{sell_status}] SellQty")
        print_separator(char="-", length=61, color=MAGENTA)

        choice = input("Masukkan pilihan Anda (1/2/3): ").strip()

        if choice == '1':
            # --- Validasi Sebelum Memulai ---
            error_messages = []
            # Validasi Email Wajib
            if not email_ok or not pass_ok:
                error_messages.append("Pengaturan Email (Alamat/App Password) belum lengkap!")

            # Validasi Binance jika Eksekusi Aktif
            if exec_on:
                if not BINANCE_AVAILABLE:
                    error_messages.append("Eksekusi Binance aktif tapi library 'python-binance' TIDAK DITEMUKAN!")
                    error_messages.append("   -> Install: pip install python-binance")
                if not api_ok or not secret_ok:
                    error_messages.append("Eksekusi Binance aktif tapi API Key/Secret belum diatur!")
                if not pair_ok:
                    error_messages.append("Eksekusi Binance aktif tapi Trading Pair belum diatur!")
                if not buy_qty_ok:
                     error_messages.append("Kuantitas Beli (buy_quote_quantity) harus lebih besar dari 0!")
                # Hanya warning jika sell qty 0 dan eksekusi aktif
                if sell_qty_ok and settings['sell_base_quantity'] == 0:
                     print(f"\n{YELLOW}{BOLD}[PERHATIAN] Kuantitas Jual (sell_base_quantity) adalah 0.{RESET}")
                     print(f"{YELLOW}           Order 'SELL' tidak akan dieksekusi jika terpicu.{RESET}")
                     time.sleep(2) # Beri waktu user membaca warning
                elif not sell_qty_ok: # Jika < 0 (tidak valid)
                     error_messages.append("Kuantitas Jual (sell_base_quantity) tidak valid (harus >= 0)!")


            # Tampilkan semua error jika ada
            if error_messages:
                print(f"\n{RED}{BOLD}🚨 Gagal Memulai Listener! 🚨{RESET}")
                for msg in error_messages:
                    print(f"{RED} - {msg}{RESET}")
                print(f"\n{YELLOW}Silakan perbaiki melalui menu 'Pengaturan' (pilihan 2).{RESET}")
                input(f"{DIM}Tekan Enter untuk kembali ke menu...{RESET}")
            else:
                # Siap memulai
                start_listening(settings) # Panggil fungsi listener utama
                # Setelah listener berhenti (Ctrl+C atau error fatal), kembali ke menu
                print(f"\n{YELLOW}[INFO] Kembali ke Menu Utama...{RESET}")
                input(f"{DIM}Tekan Enter untuk melanjutkan...{RESET}")

        elif choice == '2':
            show_settings(settings)
            # settings = load_settings() # Load ulang setting setelah dari menu edit (sudah dihandle di awal loop)
        elif choice == '3':
            clear_screen()
            print(f"\n{CYAN}{BOLD}👋 Terima kasih telah menggunakan Exora AI Listener! Sampai jumpa! 👋{RESET}\n")
            sys.exit(0)
        else:
            print(f"\n{RED}[ERROR] Pilihan tidak valid. Masukkan 1, 2, atau 3.{RESET}")
            time.sleep(1.5)

# --- Entry Point ---
if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        # Signal handler sudah menangani ini, tapi sebagai fallback
        print(f"\n{YELLOW}[WARN] Program dihentikan paksa dari luar signal handler.{RESET}")
        sys.exit(1)
    except Exception as e:
        # Tangkap error tak terduga di level tertinggi
        clear_screen()
        print(f"\n{BOLD}{RED}╔════════════════════════════╗{RESET}")
        print(f"{BOLD}{RED}║      💥 ERROR KRITIS 💥     ║{RESET}")
        print(f"{BOLD}{RED}╚════════════════════════════╝{RESET}")
        print(f"\n{RED}Terjadi error yang tidak dapat dipulihkan di luar loop utama:{RESET}")
        traceback.print_exc() # Tampilkan detail error
        print(f"\n{RED}Pesan Error: {e}{RESET}")
        print("\nProgram akan ditutup.")
        sys.exit(1)
