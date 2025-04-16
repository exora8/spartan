# -*- coding: utf-8 -*-
import imaplib
import email
from email.header import decode_header
import time
import datetime # Untuk timestamp
import subprocess
import json
import os
import getpass # Tetap import, meskipun tidak dipakai di edit settings
import sys
import signal # Untuk menangani Ctrl+C
import traceback # Untuk mencetak traceback error
import socket # Untuk error koneksi

# --- Inquirer Integration (untuk menu interaktif) ---
try:
    import inquirer
    from inquirer.themes import GreenPassion
    INQUIRER_AVAILABLE = True
except ImportError:
    INQUIRER_AVAILABLE = False
    print("\n!!! WARNING: Library 'inquirer' tidak ditemukan. !!!")
    print("!!!          Menu akan menggunakan input teks biasa.     !!!")
    print("!!!          Install dengan: pip install inquirer       !!!\n")
    time.sleep(3) # Beri waktu untuk membaca warning

# --- Binance Integration ---
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
    class Client: # Dummy class
        # Tambahkan konstanta dummy jika inquirer tidak ada tapi binance ada
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

# Variabel global untuk mengontrol loop utama
running = True

# --- Kode Warna ANSI ---
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m" # Efek dim/redup
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"

# --- Fungsi Penanganan Sinyal (Ctrl+C) ---
def signal_handler(sig, frame):
    global running
    print(f"\n{YELLOW}{BOLD}[WARN] Ctrl+C terdeteksi. Menghentikan program...{RESET}")
    running = False
    # Beri sedikit waktu agar loop utama bisa berhenti dengan bersih jika memungkinkan
    time.sleep(1.5)
    print(f"{RED}{BOLD}[EXIT] Keluar dari program.{RESET}")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# --- Fungsi Konfigurasi ---
# load_settings & save_settings tetap sama, tidak perlu diubah
def load_settings():
    """Memuat pengaturan dari file JSON, memastikan semua kunci ada."""
    settings = DEFAULT_SETTINGS.copy() # Mulai dengan default
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_settings = json.load(f)
                # Pastikan hanya kunci dari DEFAULT_SETTINGS yang dipertimbangkan
                valid_keys = set(DEFAULT_SETTINGS.keys())
                filtered_settings = {k: v for k, v in loaded_settings.items() if k in valid_keys}
                settings.update(filtered_settings) # Timpa default dengan yg dari file

                # Validasi tambahan setelah load
                if settings.get("check_interval_seconds", 10) < 5:
                    print(f"{YELLOW}[WARN] Interval cek di '{CONFIG_FILE}' < 5 detik, direset ke 10.{RESET}")
                    settings["check_interval_seconds"] = 10

                if not isinstance(settings.get("buy_quote_quantity"), (int, float)) or settings.get("buy_quote_quantity") <= 0:
                     print(f"{YELLOW}[WARN] 'buy_quote_quantity' tidak valid, direset ke {DEFAULT_SETTINGS['buy_quote_quantity']}.{RESET}")
                     settings["buy_quote_quantity"] = DEFAULT_SETTINGS['buy_quote_quantity']

                # Memperbolehkan 0 untuk sell_base_quantity
                if not isinstance(settings.get("sell_base_quantity"), (int, float)) or settings.get("sell_base_quantity") < 0:
                     print(f"{YELLOW}[WARN] 'sell_base_quantity' tidak valid, direset ke {DEFAULT_SETTINGS['sell_base_quantity']}.{RESET}")
                     settings["sell_base_quantity"] = DEFAULT_SETTINGS['sell_base_quantity']

                if not isinstance(settings.get("execute_binance_orders"), bool):
                    print(f"{YELLOW}[WARN] 'execute_binance_orders' tidak valid, direset ke False.{RESET}")
                    settings["execute_binance_orders"] = False

                # Save back any corrections made or defaults added
                save_settings(settings)

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
        settings['check_interval_seconds'] = int(settings.get('check_interval_seconds', DEFAULT_SETTINGS['check_interval_seconds']))
        settings['buy_quote_quantity'] = float(settings.get('buy_quote_quantity', DEFAULT_SETTINGS['buy_quote_quantity']))
        settings['sell_base_quantity'] = float(settings.get('sell_base_quantity', DEFAULT_SETTINGS['sell_base_quantity']))
        settings['execute_binance_orders'] = bool(settings.get('execute_binance_orders', DEFAULT_SETTINGS['execute_binance_orders']))

        # Filter hanya kunci yang ada di DEFAULT_SETTINGS untuk disimpan
        settings_to_save = {k: settings.get(k, DEFAULT_SETTINGS[k]) for k in DEFAULT_SETTINGS}

        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings_to_save, f, indent=4, sort_keys=True) # Urutkan kunci agar lebih rapi
        # Jangan print pesan sukses simpan saat load awal jika tidak ada perubahan
        # print(f"{GREEN}[INFO] Pengaturan berhasil disimpan ke '{CONFIG_FILE}'{RESET}")
    except Exception as e:
        print(f"{RED}[ERROR] Gagal menyimpan konfigurasi: {e}{RESET}")


# --- Fungsi Utilitas ---
# clear_screen, decode_mime_words, get_text_from_email tetap sama
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def decode_mime_words(s):
    if not s:
        return ""
    try:
        decoded_parts = decode_header(s)
        result = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                # Handle potential decoding errors gracefully
                result.append(part.decode(encoding or 'utf-8', errors='replace'))
            else:
                # Assume it's already a string (though decode_header usually returns bytes or str)
                result.append(str(part))
        return "".join(result)
    except Exception as e:
        print(f"{YELLOW}[WARN] Gagal mendekode header: {e}. Header asli: {s}{RESET}")
        # Return original string or a placeholder if decoding fails completely
        return str(s) if isinstance(s, str) else s.decode('utf-8', errors='replace') if isinstance(s, bytes) else "[Decoding Error]"


def get_text_from_email(msg):
    text_content = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            # Ambil text/plain tapi abaikan attachment
            if content_type == "text/plain" and "attachment" not in content_disposition.lower():
                try:
                    charset = part.get_content_charset() or 'utf-8' # Default ke utf-8
                    payload = part.get_payload(decode=True)
                    if payload:
                        text_content += payload.decode(charset, errors='replace') + "\n" # Tambah newline antar bagian
                except Exception as e:
                    print(f"{YELLOW}[WARN] Tidak bisa mendekode bagian email (charset: {part.get_content_charset()}): {e}{RESET}")
    else:
        # Jika bukan multipart, cek apakah body utamanya text/plain
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                if payload:
                    text_content = payload.decode(charset, errors='replace')
            except Exception as e:
                 print(f"{YELLOW}[WARN] Tidak bisa mendekode body email (charset: {msg.get_content_charset()}): {e}{RESET}")
    # Membersihkan spasi berlebih dan return lowercase
    return " ".join(text_content.split()).lower()

# --- Fungsi Beep ---
# trigger_beep tetap sama
def trigger_beep(action):
    try:
        if action == "buy":
            print(f"{MAGENTA}{BOLD}[ACTION] Memicu BEEP untuk 'BUY'{RESET}")
            # Menggunakan argumen yang lebih umum (frekuensi dan durasi)
            subprocess.run(["beep", "-f", "1000", "-l", "300"], check=True, capture_output=True, text=True)
            time.sleep(0.1)
            subprocess.run(["beep", "-f", "1200", "-l", "200"], check=True, capture_output=True, text=True)
        elif action == "sell":
            print(f"{MAGENTA}{BOLD}[ACTION] Memicu BEEP untuk 'SELL'{RESET}")
            subprocess.run(["beep", "-f", "700", "-l", "500"], check=True, capture_output=True, text=True)
        else:
             print(f"{YELLOW}[WARN] Aksi beep tidak dikenal '{action}'.{RESET}")
    except FileNotFoundError:
        print(f"{YELLOW}[WARN] Perintah 'beep' tidak ditemukan. Beep dilewati.{RESET}")
        print(f"{DIM}         (Untuk Linux, install 'beep': sudo apt install beep / sudo yum install beep){RESET}")
    except subprocess.CalledProcessError as e:
        print(f"{RED}[ERROR] Gagal menjalankan 'beep': {e}{RESET}")
        if e.stderr: print(f"{RED}         Stderr: {e.stderr.strip()}{RESET}")
    except Exception as e:
        print(f"{RED}[ERROR] Kesalahan tak terduga saat beep: {e}{RESET}")


# --- Fungsi Eksekusi Binance ---
# get_binance_client & execute_binance_order tetap sama
def get_binance_client(settings):
    """Membuat instance Binance client."""
    if not BINANCE_AVAILABLE:
        print(f"{RED}[ERROR] Library python-binance tidak terinstall. Tidak bisa membuat client.{RESET}")
        return None
    api_key = settings.get('binance_api_key')
    api_secret = settings.get('binance_api_secret')
    if not api_key or not api_secret:
        print(f"{RED}[ERROR] API Key atau Secret Key Binance belum diatur di konfigurasi.{RESET}")
        return None
    try:
        print(f"{CYAN}[BINANCE] Mencoba koneksi ke Binance API...{RESET}")
        client = Client(api_key, api_secret)
        # Test koneksi (opsional tapi bagus)
        client.ping()
        # Dapatkan info akun untuk konfirmasi (opsional)
        # account_info = client.get_account()
        # print(f"{GREEN}[BINANCE] Koneksi dan autentikasi ke Binance API berhasil.{RESET}")
        # print(f"{DIM}         (Account Type: {account_info.get('accountType')}){RESET}")
        print(f"{GREEN}[BINANCE] Koneksi dan autentikasi ke Binance API berhasil.{RESET}")
        return client
    except BinanceAPIException as e:
        print(f"{RED}{BOLD}[BINANCE ERROR] Gagal terhubung/autentikasi ke Binance: Status={e.status_code}, Pesan='{e.message}'{RESET}")
        if "timestamp" in e.message.lower():
             print(f"{YELLOW}         -> Periksa apakah waktu sistem Anda sinkron.{RESET}")
        if "signature" in e.message.lower() or "invalid key" in e.message.lower():
             print(f"{YELLOW}         -> Periksa kembali API Key dan Secret Key Anda.{RESET}")
        return None
    except requests.exceptions.RequestException as e: # Tangani error koneksi network
        print(f"{RED}[NETWORK ERROR] Gagal menghubungi Binance API: {e}{RESET}")
        print(f"{YELLOW}         -> Periksa koneksi internet Anda.{RESET}")
        return None
    except Exception as e:
        print(f"{RED}[ERROR] Gagal membuat Binance client: {e}{RESET}")
        traceback.print_exc()
        return None

def execute_binance_order(client, settings, side):
    """Mengeksekusi order MARKET BUY atau SELL di Binance."""
    if not client:
        print(f"{RED}[BINANCE] Eksekusi dibatalkan, client tidak valid.{RESET}")
        return False
    if not settings.get("execute_binance_orders", False):
        # Ini seharusnya tidak terjadi jika logic di main_menu benar, tapi sebagai safety net
        print(f"{YELLOW}[BINANCE] Eksekusi order dinonaktifkan ('execute_binance_orders': false). Order dilewati.{RESET}")
        return False # Dianggap tidak gagal, hanya dilewati

    pair = settings.get('trading_pair', '').upper()
    if not pair:
        print(f"{RED}[BINANCE ERROR] Trading pair belum diatur di konfigurasi.{RESET}")
        return False

    order_details = {}
    action_desc = ""

    try:
        if side == Client.SIDE_BUY:
            quote_qty = settings.get('buy_quote_quantity', 0.0)
            if quote_qty <= 0:
                 print(f"{RED}[BINANCE ERROR] Kuantitas Beli (buy_quote_quantity) harus > 0.{RESET}")
                 return False
            order_details = {
                'symbol': pair,
                'side': Client.SIDE_BUY,
                'type': Client.ORDER_TYPE_MARKET,
                'quoteOrderQty': quote_qty
            }
            action_desc = f"MARKET BUY {quote_qty} (quote) of {pair}"

        elif side == Client.SIDE_SELL:
            base_qty = settings.get('sell_base_quantity', 0.0)
            if base_qty <= 0:
                 # Jika base_qty 0, ini seharusnya tidak dipanggil berdasarkan logic awal,
                 # tapi bisa jadi user ingin trigger beep tanpa eksekusi.
                 # Jika eksekusi diaktifkan tapi qty 0, beri warning.
                 print(f"{YELLOW}[BINANCE WARN] Kuantitas Jual (sell_base_quantity) adalah 0. Order SELL tidak dieksekusi.{RESET}")
                 return False # Tidak dianggap error fatal, tapi order tidak jalan
                 # Jika ingin ini jadi error:
                 # print(f"{RED}[BINANCE ERROR] Kuantitas Jual (sell_base_quantity) harus > 0 untuk eksekusi SELL.{RESET}")
                 # return False
            order_details = {
                'symbol': pair,
                'side': Client.SIDE_SELL,
                'type': Client.ORDER_TYPE_MARKET,
                'quantity': base_qty # Jual sejumlah base asset
            }
            action_desc = f"MARKET SELL {base_qty} (base) of {pair}"
        else:
            print(f"{RED}[BINANCE ERROR] Sisi order tidak valid: {side}{RESET}")
            return False

        print(f"{MAGENTA}{BOLD}[BINANCE] Mencoba eksekusi: {action_desc}...{RESET}")

        # Simulasi jika perlu (DEBUG)
        # print(f"{YELLOW}[DEBUG] Simulasi order: {order_details}{RESET}")
        # time.sleep(1)
        # return True # Hapus ini untuk eksekusi sungguhan

        order_result = client.create_order(**order_details)

        print(f"{GREEN}{BOLD}[BINANCE SUCCESS] Order berhasil dieksekusi!{RESET}")
        print(f"  {DIM}Order ID : {order_result.get('orderId')}{RESET}")
        print(f"  {DIM}Symbol   : {order_result.get('symbol')}{RESET}")
        print(f"  {DIM}Side     : {order_result.get('side')}{RESET}")
        print(f"  {DIM}Status   : {order_result.get('status')}{RESET}")

        # Info fill (harga rata-rata dan kuantitas terisi)
        if order_result.get('fills') and len(order_result.get('fills')) > 0:
            total_qty = sum(float(f['qty']) for f in order_result['fills'])
            total_quote_qty = sum(float(f['cummulativeQuoteQty']) for f in order_result['fills']) # Gunakan cummulativeQuoteQty
            avg_price = total_quote_qty / total_qty if total_qty else 0
            print(f"  {DIM}Avg Price: {avg_price:.8f}{RESET}") # Sesuaikan presisi jika perlu
            print(f"  {DIM}Filled Qty: {total_qty:.8f} (Base) / {total_quote_qty:.4f} (Quote){RESET}")
        elif order_result.get('cummulativeQuoteQty'): # Kadang fills kosong tapi ada cummulative
             print(f"  {DIM}Total Cost/Proceeds: {float(order_result['cummulativeQuoteQty']):.4f} (Quote){RESET}")
        return True

    except BinanceAPIException as e:
        print(f"{RED}{BOLD}[BINANCE API ERROR] Gagal eksekusi order: Status={e.status_code}, Kode={e.code}, Pesan='{e.message}'{RESET}")
        # Contoh error spesifik:
        if e.code == -2010: # Insufficient balance
            print(f"{RED}         -> Kemungkinan saldo tidak cukup.{RESET}")
        elif e.code == -1121: # Invalid symbol
            print(f"{RED}         -> Trading pair '{pair}' tidak valid.{RESET}")
        elif e.code == -1013 or 'MIN_NOTIONAL' in str(e.message): # Min notional / Lot size
             print(f"{RED}         -> Order size terlalu kecil (cek minimum order/MIN_NOTIONAL di info pair).{RESET}")
        elif e.code == -1111: # LOT_SIZE
             print(f"{RED}         -> Kuantitas order tidak sesuai aturan LOT_SIZE (kelipatan step size).{RESET}")
        return False
    except BinanceOrderException as e:
        # Ini biasanya untuk error spesifik order yang tidak tercover APIException
        print(f"{RED}{BOLD}[BINANCE ORDER ERROR] Gagal eksekusi order: Status={e.status_code}, Kode={e.code}, Pesan='{e.message}'{RESET}")
        return False
    except requests.exceptions.RequestException as e: # Tangani error koneksi network saat order
        print(f"{RED}[NETWORK ERROR] Gagal mengirim order ke Binance: {e}{RESET}")
        return False
    except Exception as e:
        print(f"{RED}[ERROR] Kesalahan tak terduga saat eksekusi order Binance:{RESET}")
        traceback.print_exc()
        return False

# --- Fungsi Pemrosesan Email ---
# process_email tetap sama
def process_email(mail, email_id, settings, binance_client): # Tambah binance_client
    """Mengambil, mem-parsing, dan memproses satu email, lalu eksekusi order jika sesuai."""
    global running
    if not running: return

    target_keyword_lower = settings['target_keyword'].lower()
    trigger_keyword_lower = settings['trigger_keyword'].lower()
    email_id_str = email_id.decode('utf-8')

    try:
        # print(f"{DIM}[DEBUG] Fetching email ID {email_id_str}...{RESET}")
        status, data = mail.fetch(email_id, "(RFC822)")
        if status != 'OK':
            print(f"{RED}[ERROR] Gagal mengambil email ID {email_id_str}: {status}{RESET}")
            # Coba lanjut ke email berikutnya jika ada error fetch
            return

        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        subject = decode_mime_words(msg["Subject"])
        sender = decode_mime_words(msg["From"])
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print(f"\n{CYAN}--- Email Ditemukan ({timestamp}) ---{RESET}")
        print(f" ID    : {email_id_str}")
        print(f" Dari  : {sender}")
        print(f" Subjek: {subject}")

        # Dapatkan body text setelah informasi dasar ditampilkan
        body = get_text_from_email(msg)
        # Gabungkan subjek dan body untuk pencarian keyword yang lebih fleksibel
        full_content = (subject.lower() + " " + body)

        # print(f"{DIM}[DEBUG] Full content (lower): {full_content[:200]}...{RESET}") # Tampilkan sebagian konten untuk debug

        if target_keyword_lower in full_content:
            print(f"{GREEN}[PASS] Keyword target '{settings['target_keyword']}' ditemukan.{RESET}")
            try:
                # Cari trigger SETELAH target
                target_index = full_content.find(target_keyword_lower)
                trigger_index = full_content.find(trigger_keyword_lower, target_index + len(target_keyword_lower))

                if trigger_index != -1:
                    start_word_index = trigger_index + len(trigger_keyword_lower)
                    text_after_trigger = full_content[start_word_index:].lstrip() # Ambil teks setelah trigger, hapus spasi awal
                    words_after_trigger = text_after_trigger.split(maxsplit=1) # Split jadi kata pertama dan sisanya

                    if words_after_trigger:
                        # Ambil kata pertama setelah trigger, bersihkan dari tanda baca umum
                        action_word = words_after_trigger[0].strip('.,!?:;()[]{}').lower()
                        print(f"{GREEN}[PASS] Keyword trigger '{settings['trigger_keyword']}' ditemukan. Kata aksi: '{BOLD}{action_word}{RESET}{GREEN}'{RESET}")

                        # --- Trigger Aksi (Beep dan/atau Binance) ---
                        order_attempted = False # Tandai apakah eksekusi order dicoba
                        execute_binance = settings.get("execute_binance_orders", False)

                        if action_word == "buy":
                            trigger_beep("buy")
                            if execute_binance:
                                if binance_client:
                                    execute_binance_order(binance_client, settings, Client.SIDE_BUY)
                                    order_attempted = True
                                else:
                                    print(f"{YELLOW}[WARN] Eksekusi Binance aktif tapi client tidak valid/tersedia saat ini.{RESET}")
                            # Jika eksekusi nonaktif, tidak ada pesan warning khusus diperlukan di sini

                        elif action_word == "sell":
                             # Hanya eksekusi jika sell_base_quantity > 0
                            can_sell = settings.get('sell_base_quantity', 0.0) > 0
                            trigger_beep("sell") # Beep tetap jalan
                            if execute_binance:
                                if can_sell:
                                    if binance_client:
                                        execute_binance_order(binance_client, settings, Client.SIDE_SELL)
                                        order_attempted = True
                                    else:
                                        print(f"{YELLOW}[WARN] Eksekusi Binance aktif tapi client tidak valid/tersedia saat ini.{RESET}")
                                elif settings.get('sell_base_quantity') <= 0: # Beri info jika qty 0
                                    print(f"{YELLOW}[INFO] Aksi 'sell' terdeteksi, tapi 'sell_base_quantity' = 0. Order Binance tidak dieksekusi.{RESET}")
                            # Jika eksekusi nonaktif, tidak ada pesan warning khusus

                        else:
                            print(f"{YELLOW}[INFO] Kata setelah '{settings['trigger_keyword']}' ('{action_word}') bukan 'buy' atau 'sell'. Tidak ada aksi market.{RESET}")

                        # Pesan tambahan jika eksekusi diaktifkan tapi tidak terjadi karena error client
                        if execute_binance and action_word in ["buy", "sell"] and not order_attempted and not (action_word == "sell" and settings.get('sell_base_quantity', 0.0) <= 0):
                             print(f"{YELLOW}[BINANCE] Eksekusi tidak dilakukan (lihat pesan error client di atas).{RESET}")

                    else:
                        print(f"{YELLOW}[WARN] Keyword trigger '{settings['trigger_keyword']}' ditemukan, tapi tidak ada kata setelahnya.{RESET}")
                else:
                     print(f"{YELLOW}[WARN] Keyword target ditemukan, tapi keyword trigger '{settings['trigger_keyword']}' tidak ditemukan {BOLD}setelahnya{RESET}{YELLOW}.{RESET}")

            except Exception as e:
                 print(f"{RED}[ERROR] Gagal parsing kata setelah trigger: {e}{RESET}")
                 traceback.print_exc() # Tampilkan traceback untuk debug internal error
        else:
            print(f"{BLUE}[INFO] Keyword target '{settings['target_keyword']}' tidak ditemukan dalam email ini.{RESET}")

        # Tandai email sebagai sudah dibaca ('Seen') setelah diproses
        try:
            # print(f"{DIM}[DEBUG] Marking email {email_id_str} as Seen...{RESET}")
            mail.store(email_id, '+FLAGS', '\\Seen')
        except Exception as e:
            print(f"{RED}[ERROR] Gagal menandai email {email_id_str} sebagai 'Seen': {e}{RESET}")
        print(f"{CYAN}-------------------------------------------{RESET}")

    except Exception as e:
        print(f"{RED}{BOLD}[ERROR] Gagal memproses email ID {email_id_str}:{RESET}")
        traceback.print_exc()

# --- Fungsi Listening Utama ---
# start_listening tidak perlu banyak diubah, hanya pesan log awal
def start_listening(settings):
    """Memulai loop untuk memeriksa email baru dan menyiapkan client Binance."""
    global running
    running = True # Pastikan running=True saat memulai
    mail = None
    binance_client = None # Inisialisasi client Binance
    last_check_time = time.time() # Untuk interval cek yang lebih akurat
    consecutive_errors = 0 # Lacak error beruntun
    max_consecutive_errors = 5 # Batas sebelum jeda lebih lama
    long_wait_time = 60 # Jeda lama setelah banyak error
    initial_wait_time = 2 # Jeda singkat awal
    wait_time = initial_wait_time # Waktu tunggu reconnect awal

    # --- Setup Binance Client di Awal (jika diaktifkan) ---
    execute_binance = settings.get("execute_binance_orders", False)
    if execute_binance:
        if not BINANCE_AVAILABLE:
             print(f"{RED}{BOLD}[FATAL] Eksekusi Binance diaktifkan tapi library python-binance tidak ada!{RESET}")
             print(f"{YELLOW}         Nonaktifkan eksekusi di Pengaturan atau install library: pip install python-binance{RESET}")
             running = False # Hentikan sebelum loop utama
             return # Keluar dari fungsi start_listening

        print(f"\n{CYAN}--- Inisialisasi Binance Client ---{RESET}")
        binance_client = get_binance_client(settings)
        if not binance_client:
            print(f"{RED}{BOLD}[FATAL] Gagal menginisialisasi Binance Client.{RESET}")
            print(f"{YELLOW}         Periksa API Key/Secret, koneksi internet, dan sinkronisasi waktu sistem.{RESET}")
            print(f"{YELLOW}         Eksekusi order Binance tidak akan berfungsi.{RESET}")
            # Pertimbangkan: Haruskah program berhenti total? Atau biarkan jalan untuk email saja?
            # Opsi 1: Berhenti total
            # running = False
            # return
            # Opsi 2: Lanjut tanpa Binance (seperti sekarang)
            print(f"{YELLOW}         Program akan lanjut untuk notifikasi email saja.{RESET}")
        else:
            print(f"{GREEN}{BOLD}[SYS] Binance Client siap.{RESET}")
        print("-" * 40)
    else:
        print(f"\n{YELLOW}[INFO] Eksekusi order Binance dinonaktifkan ('execute_binance_orders': false).{RESET}")
        print(f"{DIM}        (Hanya notifikasi email dan beep yang akan aktif){RESET}")
        print("-" * 40)

    # --- Loop Utama Email Listener ---
    while running:
        try:
            # Coba koneksi IMAP
            if not mail or mail.state != 'SELECTED':
                print(f"\n{CYAN}[SYS] Mencoba menghubungkan ke IMAP {settings['imap_server']}...{RESET}")
                # Timeout koneksi ditambahkan
                mail = imaplib.IMAP4_SSL(settings['imap_server'], timeout=30)
                print(f"{GREEN}[SYS] Terhubung. Mencoba login {settings['email_address']}...{RESET}")
                # Tambahkan penanganan error login spesifik
                try:
                    rv, desc = mail.login(settings['email_address'], settings['app_password'])
                    if rv != 'OK':
                        # Tangani login gagal secara eksplisit
                        raise imaplib.IMAP4.error(f"Login failed: {desc}")
                except (imaplib.IMAP4.error, OSError) as login_err: # OSError bisa terjadi jika koneksi drop saat login
                     print(f"{RED}{BOLD}[FATAL] Login Email GAGAL!{RESET}")
                     print(f"{RED}         Pesan: {login_err}{RESET}")
                     print(f"{YELLOW}         Periksa Alamat Email, App Password, dan izin akses IMAP di akun email Anda.{RESET}")
                     running = False # Hentikan loop utama jika login gagal
                     # Jangan logout jika login gagal, cukup bersihkan var mail
                     mail = None
                     continue # Coba lagi di iterasi berikutnya atau keluar jika running=False

                print(f"{GREEN}{BOLD}[SYS] Login email berhasil!{RESET}")
                mail.select("inbox")
                print(f"{GREEN}[INFO] Memulai mode mendengarkan di INBOX... (Ctrl+C untuk berhenti){RESET}")
                print("-" * 50)
                consecutive_errors = 0 # Reset error counter on successful connect/login
                wait_time = initial_wait_time # Reset wait time

            # Loop inner untuk cek email & noop
            while running:
                current_time = time.time()
                # Cek interval
                if current_time - last_check_time < settings['check_interval_seconds']:
                    # Tidur sebentar agar tidak busy-wait
                    time.sleep(0.5)
                    continue

                # Cek koneksi IMAP dengan NOOP
                try:
                    # print(f"{DIM}[DEBUG] Sending NOOP...{RESET}", end='\r')
                    status, _ = mail.noop()
                    # print(" " * 30, end='\r') # Clear debug message
                    if status != 'OK':
                        print(f"\n{YELLOW}[WARN] Koneksi IMAP NOOP gagal (Status: {status}). Mencoba reconnect...{RESET}")
                        try: mail.close() # Coba tutup dulu
                        except Exception: pass
                        mail = None # Paksa reconnect di loop luar
                        break # Keluar loop inner
                except (imaplib.IMAP4.abort, imaplib.IMAP4.readonly, BrokenPipeError, OSError) as noop_err:
                     print(f"\n{YELLOW}[WARN] Koneksi IMAP terputus ({type(noop_err).__name__}). Mencoba reconnect...{RESET}")
                     try: mail.logout() # Coba logout jika state memungkinkan
                     except Exception: pass
                     mail = None
                     break # Keluar loop inner

                # Cek koneksi Binance jika client ada (opsional, tapi bagus)
                # Lakukan ini lebih jarang dari cek email untuk efisiensi
                # Misalnya, setiap 5 kali interval email atau minimal 60 detik sekali
                if binance_client and current_time - getattr(binance_client, '_last_ping_time', 0) > max(60, settings['check_interval_seconds'] * 5):
                     try:
                         # print(f"{DIM}[DEBUG] Pinging Binance API...{RESET}", end='\r')
                         binance_client.ping()
                         setattr(binance_client, '_last_ping_time', current_time) # Update waktu ping terakhir
                         # print(" " * 30, end='\r') # Clear debug message
                     except Exception as ping_err:
                         print(f"\n{YELLOW}[WARN] Ping ke Binance API gagal ({ping_err}). Mencoba membuat ulang client...{RESET}")
                         # Coba buat ulang client sekali
                         binance_client = get_binance_client(settings) # Reuse fungsi get_client
                         if not binance_client:
                              print(f"{RED}       Gagal membuat ulang Binance client. Eksekusi mungkin gagal.{RESET}")
                              # Reset waktu ping agar segera dicoba lagi nanti
                              setattr(binance_client, '_last_ping_time', 0) if binance_client else None
                         else:
                             print(f"{GREEN}       Binance client berhasil dibuat ulang.{RESET}")
                             setattr(binance_client, '_last_ping_time', current_time)
                         # Beri jeda sedikit setelah error ping/reconnect
                         time.sleep(5)

                # Cek email baru (UNSEEN)
                # print(f"{DIM}[DEBUG] Searching UNSEEN emails...{RESET}", end='\r')
                status, messages = mail.search(None, '(UNSEEN)')
                # print(" " * 35, end='\r') # Clear debug message
                if status != 'OK':
                     print(f"\n{RED}[ERROR] Gagal mencari email UNSEEN: {status}{RESET}")
                     # Mungkin sesi tidak valid, coba reconnect
                     try: mail.close()
                     except Exception: pass
                     mail = None
                     break # Keluar loop inner

                email_ids = messages[0].split()
                if email_ids:
                    num_emails = len(email_ids)
                    print(f"\n{GREEN}{BOLD}[!] Menemukan {num_emails} email baru! Memproses...{RESET}")
                    # Proses satu per satu
                    for i, email_id in enumerate(email_ids):
                        if not running: break # Cek flag running di setiap iterasi
                        print(f"{DIM}--- Memproses email {i+1}/{num_emails} ---{RESET}")
                        process_email(mail, email_id, settings, binance_client) # Kirim client Binance
                    if not running: break # Cek lagi setelah loop proses email
                    print("-" * 50)
                    print(f"{GREEN}[INFO] Selesai memproses {num_emails} email. Kembali mendengarkan...{RESET}")
                else:
                    # Tidak ada email baru, tampilkan pesan tunggu yang update
                    wait_interval = settings['check_interval_seconds']
                    # Menampilkan '.' yang bergerak sederhana
                    dots = "." * (int(time.time()) % 4)
                    print(f"{BLUE}[INFO] Tidak ada email baru. Cek lagi dalam ~{wait_interval}s {dots}{RESET}     ", end='\r')

                last_check_time = current_time # Update waktu cek terakhir
                # time.sleep(1) # Loop utama punya mekanisme interval sendiri

            # Jika keluar dari loop inner karena error, atau normal stop
            if mail and mail.state == 'SELECTED':
                try:
                    # print(f"{DIM}[DEBUG] Closing mailbox...{RESET}")
                    mail.close()
                except Exception as close_err:
                    # print(f"{YELLOW}[WARN] Error saat menutup mailbox: {close_err}{RESET}")
                    pass # Tetap coba logout

        except (imaplib.IMAP4.error, imaplib.IMAP4.abort, BrokenPipeError, OSError) as e:
            # Tangani error IMAP atau koneksi dasar
            print(f"\n{RED}{BOLD}[ERROR] Kesalahan IMAP/Koneksi: {e}{RESET}")
            consecutive_errors += 1
            if "login failed" in str(e).lower() or "authentication failed" in str(e).lower() or "invalid credentials" in str(e).lower():
                print(f"{RED}{BOLD}[FATAL] Login Email GAGAL! Periksa Alamat Email dan App Password.{RESET}")
                running = False # Hentikan loop utama
            elif consecutive_errors >= max_consecutive_errors:
                 print(f"{YELLOW}[WARN] Terlalu banyak error beruntun ({consecutive_errors}). Menunggu {long_wait_time} detik sebelum mencoba lagi...{RESET}")
                 time.sleep(long_wait_time)
                 wait_time = initial_wait_time # Reset wait time setelah jeda panjang
                 consecutive_errors = 0 # Reset error counter
            else:
                 print(f"{YELLOW}[WARN] Mencoba menghubungkan kembali dalam {wait_time} detik... (Error ke-{consecutive_errors}){RESET}")
                 time.sleep(wait_time)
                 # Tingkatkan waktu tunggu secara bertahap
                 wait_time = min(wait_time * 2, 30) # Maks 30 detik exponential backoff

        except (socket.error, socket.gaierror) as e:
             # Tangani error DNS atau koneksi network spesifik
             print(f"\n{RED}{BOLD}[NETWORK ERROR] Kesalahan Koneksi Jaringan: {e}{RESET}")
             consecutive_errors += 1
             if consecutive_errors >= max_consecutive_errors:
                 print(f"{YELLOW}[WARN] Terlalu banyak error jaringan beruntun ({consecutive_errors}). Menunggu {long_wait_time} detik...{RESET}")
                 time.sleep(long_wait_time)
                 wait_time = initial_wait_time
                 consecutive_errors = 0
             else:
                 print(f"{YELLOW}[WARN] Periksa koneksi internet Anda. Mencoba lagi dalam {wait_time} detik... (Error ke-{consecutive_errors}){RESET}")
                 time.sleep(wait_time)
                 wait_time = min(wait_time * 2, 45) # Backoff hingga 45 detik

        except Exception as e:
            # Tangani error tak terduga lainnya
            print(f"\n{RED}{BOLD}[ERROR] Kesalahan tak terduga di loop utama:{RESET}")
            traceback.print_exc()
            consecutive_errors += 1
            print(f"{YELLOW}[WARN] Mencoba melanjutkan setelah error. Tunggu {wait_time} detik... (Error ke-{consecutive_errors}){RESET}")
            time.sleep(wait_time)
            wait_time = min(wait_time * 2, 60) # Backoff hingga 60 detik
            if consecutive_errors >= max_consecutive_errors + 2: # Jeda sangat lama jika terus error
                 print(f"{RED}[FATAL] Terlalu banyak error tak terduga beruntun. Berhenti.{RESET}")
                 running = False

        finally:
            # Pastikan logout dari IMAP jika koneksi pernah dibuat & state valid
            if mail and mail.state != 'LOGOUT':
                try:
                    # print(f"{DIM}[DEBUG] Logging out from IMAP...{RESET}")
                    mail.logout()
                    # print(f"{CYAN}[SYS] Logout dari server IMAP.{RESET}")
                except Exception as logout_err:
                    # print(f"{YELLOW}[WARN] Error saat logout: {logout_err}{RESET}")
                    pass # Abaikan error logout, mungkin koneksi sudah mati
            mail = None # Set mail ke None agar reconnect dicoba di iterasi berikutnya
        if running: time.sleep(0.5) # Jeda singkat antar upaya koneksi utama

    print(f"\n{YELLOW}{BOLD}[INFO] Mode mendengarkan dihentikan.{RESET}")


# --- Fungsi Menu Pengaturan (MODIFIED) ---
def show_settings(settings):
    """Menampilkan dan mengedit pengaturan, termasuk Binance."""
    while True:
        clear_screen()
        print(f"{BOLD}{CYAN}--- Pengaturan Email & Binance Listener ---{RESET}")

        # --- Tampilkan Pengaturan Email ---
        print(f"\n{MAGENTA}--- Email Settings ---{RESET}")
        print(f" 1. {CYAN}Alamat Email{RESET}   : {settings['email_address'] or f'{DIM}[Belum diatur]{RESET}'}")
        # Tampilkan password sebagian tersamar jika ada isinya
        app_pass_display = f"*{'*' * (len(settings['app_password']) - 2)}*" if len(settings['app_password']) > 2 else ('***' if settings['app_password'] else f'{DIM}[Belum diatur]{RESET}')
        print(f" 2. {CYAN}App Password{RESET}   : {app_pass_display}")
        print(f" 3. {CYAN}Server IMAP{RESET}    : {settings['imap_server']}")
        print(f" 4. {CYAN}Interval Cek{RESET}   : {settings['check_interval_seconds']} detik")
        print(f" 5. {CYAN}Keyword Target{RESET} : '{settings['target_keyword']}'")
        print(f" 6. {CYAN}Keyword Trigger{RESET}: '{settings['trigger_keyword']}'")

        # --- Tampilkan Pengaturan Binance ---
        print(f"\n{MAGENTA}--- Binance Settings ---{RESET}")
        binance_status = f"{GREEN}Tersedia{RESET}" if BINANCE_AVAILABLE else f"{RED}Tidak Tersedia (Install 'python-binance'){RESET}"
        print(f" Library Status      : {binance_status}")
        api_key_display = f"{settings['binance_api_key'][:4]}...{settings['binance_api_key'][-4:]}" if len(settings['binance_api_key']) > 8 else ('OK' if settings['binance_api_key'] else f'{DIM}[Belum diatur]{RESET}')
        api_secret_display = f"{settings['binance_api_secret'][:4]}...{settings['binance_api_secret'][-4:]}" if len(settings['binance_api_secret']) > 8 else ('OK' if settings['binance_api_secret'] else f'{DIM}[Belum diatur]{RESET}')
        print(f" 7. {CYAN}API Key{RESET}        : {api_key_display}")
        print(f" 8. {CYAN}API Secret{RESET}     : {api_secret_display}")
        print(f" 9. {CYAN}Trading Pair{RESET}   : {settings['trading_pair'] or f'{DIM}[Belum diatur]{RESET}'}")
        print(f"10. {CYAN}Buy Quote Qty{RESET}  : {settings['buy_quote_quantity']} (e.g., USDT)")
        print(f"11. {CYAN}Sell Base Qty{RESET}  : {settings['sell_base_quantity']} (e.g., BTC) {DIM}(0 = nonaktif){RESET}")
        exec_status = f"{GREEN}{BOLD}Aktif{RESET}" if settings['execute_binance_orders'] else f"{RED}Nonaktif{RESET}"
        print(f"12. {CYAN}Eksekusi Order{RESET} : {exec_status}")
        print("-" * 40)

        # --- Opsi Menu Pengaturan ---
        if INQUIRER_AVAILABLE:
            questions = [
                inquirer.List('action',
                              message=f"{YELLOW}Pilih aksi{RESET}",
                              choices=[
                                  ('Edit Pengaturan', 'edit'),
                                  ('Kembali ke Menu Utama', 'back')
                              ],
                              carousel=True # Agar bisa loop dari bawah ke atas
                             )
            ]
            try:
                 answers = inquirer.prompt(questions, theme=GreenPassion())
                 choice = answers['action'] if answers else 'back' # Default kembali jika user Ctrl+C
            except Exception as e:
                 print(f"{RED}Error pada menu interaktif: {e}{RESET}")
                 choice = 'back' # Fallback jika inquirer error
            except KeyboardInterrupt:
                 print(f"\n{YELLOW}Edit dibatalkan.{RESET}")
                 choice = 'back'
                 time.sleep(1)

        else: # Fallback ke input teks
            print("\nOpsi:")
            print(f" {YELLOW}E{RESET} - Edit Pengaturan")
            print(f" {YELLOW}K{RESET} - Kembali ke Menu Utama")
            print("-" * 30)
            choice_input = input("Pilih opsi (E/K): ").lower().strip()
            if choice_input == 'e':
                choice = 'edit'
            elif choice_input == 'k':
                choice = 'back'
            else:
                print(f"{RED}[ERROR] Pilihan tidak valid.{RESET}")
                time.sleep(1.5)
                continue # Ulangi loop tampilan

        # --- Proses Pilihan ---
        if choice == 'edit':
            print(f"\n{BOLD}{MAGENTA}--- Edit Pengaturan ---{RESET}")
            print(f"{DIM}(Kosongkan input untuk mempertahankan nilai saat ini){RESET}")

            # --- Edit Email ---
            print(f"\n{CYAN}--- Email ---{RESET}")
            new_val = input(f" 1. Email [{settings['email_address']}]: ").strip()
            if new_val: settings['email_address'] = new_val

            # Gunakan getpass untuk input password demi keamanan, tapi beri tahu user
            print(f" 2. App Password (input akan tersembunyi): ", end='', flush=True)
            try:
                # Coba getpass, fallback ke input biasa jika gagal (misal di IDE tertentu)
                 new_pass = getpass.getpass("")
            except (ImportError, EOFError, OSError):
                 print(f"{YELLOW}(getpass gagal, input terlihat){RESET}")
                 new_pass = input(f" App Password [{app_pass_display}]: ").strip()
            if new_pass: settings['app_password'] = new_pass
            else: print(f"{DIM}   (Password tidak diubah){RESET}") # Konfirmasi jika kosong

            new_val = input(f" 3. Server IMAP [{settings['imap_server']}]: ").strip()
            if new_val: settings['imap_server'] = new_val

            while True:
                new_val_str = input(f" 4. Interval (detik) [{settings['check_interval_seconds']}], min 5: ").strip()
                if not new_val_str: break # Biarkan jika kosong
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
                 print(f"{YELLOW}   (Library Binance tidak terinstall, pengaturan ini mungkin tidak berpengaruh){RESET}")

            new_val = input(f" 7. API Key [{api_key_display}]: ").strip()
            if new_val: settings['binance_api_key'] = new_val

            # Input secret juga disembunyikan jika memungkinkan
            print(f" 8. API Secret (input akan tersembunyi): ", end='', flush=True)
            try:
                 new_secret = getpass.getpass("")
            except (ImportError, EOFError, OSError):
                 print(f"{YELLOW}(getpass gagal, input terlihat){RESET}")
                 new_secret = input(f" API Secret [{api_secret_display}]: ").strip()
            if new_secret: settings['binance_api_secret'] = new_secret
            else: print(f"{DIM}   (Secret tidak diubah){RESET}") # Konfirmasi jika kosong

            new_val = input(f" 9. Trading Pair (e.g., BTCUSDT) [{settings['trading_pair']}]: ").strip().upper() # Langsung upper
            if new_val: settings['trading_pair'] = new_val

            while True:
                 new_val_str = input(f"10. Buy Quote Qty (e.g., 11.0 USDT) [{settings['buy_quote_quantity']}], > 0: ").strip()
                 if not new_val_str: break
                 try:
                     new_qty = float(new_val_str)
                     if new_qty > 0:
                         settings['buy_quote_quantity'] = new_qty
                         break
                     else: print(f"   {RED}[ERROR] Kuantitas Beli harus lebih besar dari 0.{RESET}")
                 except ValueError: print(f"   {RED}[ERROR] Masukkan angka desimal (e.g., 11.0 atau 15).{RESET}")

            while True:
                 new_val_str = input(f"11. Sell Base Qty (e.g., 0.0005 BTC) [{settings['sell_base_quantity']}], >= 0: ").strip()
                 if not new_val_str: break
                 try:
                     new_qty = float(new_val_str)
                     if new_qty >= 0: # Membolehkan 0
                         settings['sell_base_quantity'] = new_qty
                         break
                     else: print(f"   {RED}[ERROR] Kuantitas Jual harus 0 atau lebih besar.{RESET}")
                 except ValueError: print(f"   {RED}[ERROR] Masukkan angka desimal (e.g., 0.0005 atau 0).{RESET}")

            while True:
                 current_exec = settings['execute_binance_orders']
                 exec_prompt = f"{GREEN}Aktif{RESET}" if current_exec else f"{RED}Nonaktif{RESET}"
                 # Menggunakan y/n untuk toggle
                 new_val_str = input(f"12. Eksekusi Order Binance? ({exec_prompt}) [y/n]: ").lower().strip()
                 if not new_val_str: break # Biarkan jika kosong
                 if new_val_str == 'y':
                     if BINANCE_AVAILABLE:
                         settings['execute_binance_orders'] = True
                         break
                     else:
                         print(f"   {RED}[ERROR] Tidak bisa mengaktifkan, library 'python-binance' tidak tersedia.{RESET}")
                         settings['execute_binance_orders'] = False # Pastikan tetap nonaktif
                         break # Keluar loop ini, user harus install dulu
                 elif new_val_str == 'n':
                     settings['execute_binance_orders'] = False
                     break
                 else: print(f"   {RED}[ERROR] Masukkan 'y' untuk aktif atau 'n' untuk nonaktif.{RESET}")


            save_settings(settings)
            print(f"\n{GREEN}{BOLD}[INFO] Pengaturan berhasil disimpan ke '{CONFIG_FILE}'.{RESET}")
            input(f"{DIM}Tekan Enter untuk kembali ke menu pengaturan...{RESET}") # Jeda agar user lihat pesan sukses

        elif choice == 'back':
            break # Keluar dari loop pengaturan

# --- Fungsi Menu Utama (MODIFIED) ---
def main_menu():
    """Menampilkan menu utama aplikasi dengan pilihan interaktif."""
    settings = load_settings() # Muat pengaturan sekali di awal

    while True:
        # Muat ulang pengaturan setiap kali kembali ke menu utama, jika diperlukan
        # settings = load_settings()
        clear_screen()
        print(f"{BOLD}{MAGENTA}============================================{RESET}")
        print(f" {BOLD}{MAGENTA}    Exora AI - Email & Binance Listener   {RESET}")
        print(f"{BOLD}{MAGENTA}============================================{RESET}")

        # Tampilkan Status Konfigurasi
        print(f"\n{CYAN}--- Status Konfigurasi ---{RESET}")
        email_status = f"{GREEN}OK{RESET}" if settings.get('email_address') else f"{RED}Kosong{RESET}"
        pass_status = f"{GREEN}OK{RESET}" if settings.get('app_password') else f"{RED}Kosong{RESET}"
        print(f" Email        : [{email_status}] Email | [{pass_status}] App Password")

        if BINANCE_AVAILABLE:
            api_status = f"{GREEN}OK{RESET}" if settings.get('binance_api_key') else f"{RED}Kosong{RESET}"
            secret_status = f"{GREEN}OK{RESET}" if settings.get('binance_api_secret') else f"{RED}Kosong{RESET}"
            pair_status = f"{GREEN}{settings.get('trading_pair')}{RESET}" if settings.get('trading_pair') else f"{RED}Kosong{RESET}"
            buy_qty_ok = settings.get('buy_quote_quantity', 0) > 0
            # Sell qty boleh 0, tapi beri tanda jika 0 dan eksekusi aktif
            sell_qty_ok = settings.get('sell_base_quantity', 0) >= 0
            sell_qty_display = f"{GREEN}OK ({settings['sell_base_quantity']})" if sell_qty_ok else f"{RED}Invalid (<0)"
            if settings['execute_binance_orders'] and settings.get('sell_base_quantity') == 0:
                 sell_qty_display = f"{YELLOW}OK (0 - Sell nonaktif)"


            buy_qty_display = f"{GREEN}OK ({settings['buy_quote_quantity']})" if buy_qty_ok else f"{RED}Invalid (<=0)"

            exec_mode = f"{GREEN}AKTIF{RESET}" if settings.get('execute_binance_orders') else f"{YELLOW}NONAKTIF{RESET}"
            print(f" Binance Lib  : {GREEN}Terinstall{RESET}")
            print(f" Binance Akun : [{api_status}] API | [{secret_status}] Secret | [{pair_status}] Pair")
            print(f" Binance Qty  : [{buy_qty_display}] Buy | [{sell_qty_display}] Sell")
            print(f" Eksekusi     : [{exec_mode}]")
        else:
            print(f" Binance Lib  : {RED}Tidak Terinstall{RESET} {DIM}(pip install python-binance){RESET}")
            print(f" {DIM}(Pengaturan dan eksekusi Binance tidak tersedia){RESET}")
        print("-" * 44)

        # --- Pilihan Menu Utama ---
        menu_title = f"{YELLOW}Menu Utama {DIM}(Gunakan ↑ / ↓ dan Enter){RESET}" if INQUIRER_AVAILABLE else f"{YELLOW}Menu Utama (Ketik Pilihan):{RESET}"

        if INQUIRER_AVAILABLE:
            # Definisikan pilihan untuk inquirer
            choices = [
                (f" {GREEN}1. Mulai Mendengarkan{RESET}" + (f" {DIM}(Email & {BOLD}Binance{RESET}{DIM}){RESET}" if settings.get("execute_binance_orders") and BINANCE_AVAILABLE else f" {DIM}(Email Only){RESET}"), 'start'),
                (f" {CYAN}2. Pengaturan{RESET}", 'settings'),
                (f" {RED}3. Keluar{RESET}", 'exit')
            ]

            questions = [
                inquirer.List('main_choice',
                              message=menu_title,
                              choices=choices,
                              carousel=True)
            ]
            try:
                answers = inquirer.prompt(questions, theme=GreenPassion())
                choice_key = answers['main_choice'] if answers else 'exit' # Default exit jika user Ctrl+C
            except Exception as e:
                print(f"{RED}Error pada menu interaktif: {e}{RESET}")
                choice_key = 'exit' # Fallback jika inquirer error
            except KeyboardInterrupt:
                 print(f"\n{YELLOW}Keluar dari menu...{RESET}")
                 choice_key = 'exit'
                 time.sleep(1)


        else: # Fallback ke input teks
            print(f"\n{menu_title}")
            print(f" {GREEN}1.{RESET} Mulai Mendengarkan" + (f" (Email & {BOLD}Binance{RESET})" if settings.get("execute_binance_orders") and BINANCE_AVAILABLE else " (Email Only)"))
            print(f" {CYAN}2.{RESET} Pengaturan")
            print(f" {RED}3.{RESET} Keluar")
            print("-" * 44)
            choice_input = input("Masukkan pilihan Anda (1/2/3): ").strip()
            if choice_input == '1': choice_key = 'start'
            elif choice_input == '2': choice_key = 'settings'
            elif choice_input == '3': choice_key = 'exit'
            else: choice_key = 'invalid'

        # --- Proses Pilihan ---
        if choice_key == 'start':
            print("-" * 44) # Separator sebelum validasi/start
            # Validasi sebelum memulai
            valid_email = settings.get('email_address') and settings.get('app_password')
            execute_binance = settings.get("execute_binance_orders", False)

            # Validasi Binance hanya jika eksekusi diaktifkan DAN library tersedia
            valid_binance_config = False
            can_sell = False
            if execute_binance and BINANCE_AVAILABLE:
                 valid_binance_config = (
                     settings.get('binance_api_key') and
                     settings.get('binance_api_secret') and
                     settings.get('trading_pair') and
                     settings.get('buy_quote_quantity', 0) > 0 and
                     settings.get('sell_base_quantity', 0) >= 0 # Boleh 0, tapi cek terpisah
                 )
                 can_sell = settings.get('sell_base_quantity', 0) > 0

            # --- Cek Kondisi Error ---
            error_messages = []
            if not valid_email:
                error_messages.append(f"{RED}[X] Pengaturan Email (Alamat/App Password) belum lengkap!{RESET}")

            if execute_binance and not BINANCE_AVAILABLE:
                 error_messages.append(f"{RED}[X] Eksekusi Binance aktif tapi library 'python-binance' tidak ditemukan!{RESET}")
                 error_messages.append(f"{DIM}    Install: pip install python-binance atau nonaktifkan eksekusi.{RESET}")

            if execute_binance and BINANCE_AVAILABLE and not valid_binance_config:
                 error_messages.append(f"{RED}[X] Eksekusi Binance aktif tapi konfigurasinya belum lengkap/valid!{RESET}")
                 details = []
                 if not settings.get('binance_api_key'): details.append("API Key kosong")
                 if not settings.get('binance_api_secret'): details.append("API Secret kosong")
                 if not settings.get('trading_pair'): details.append("Trading Pair kosong")
                 if settings.get('buy_quote_quantity', 0) <= 0: details.append("Buy Quote Qty <= 0")
                 if settings.get('sell_base_quantity', 0) < 0: details.append("Sell Base Qty < 0") # Error jika negatif
                 if details: error_messages.append(f"{DIM}    Detail: {', '.join(details)}.{RESET}")

            # --- Tampilkan Error atau Mulai ---
            if error_messages:
                print(f"\n{BOLD}{YELLOW}--- Tidak Bisa Memulai ---{RESET}")
                for msg in error_messages:
                    print(msg)
                print(f"\n{YELLOW}Silakan perbaiki melalui menu '{CYAN}Pengaturan{YELLOW}'.{RESET}")
                input(f"{DIM}Tekan Enter untuk kembali ke menu...{RESET}")
            else:
                # Siap memulai
                clear_screen()
                mode = "Email & Binance Order" if execute_binance and BINANCE_AVAILABLE else "Email Listener Only"
                print(f"{BOLD}{GREEN}--- Memulai Mode: {mode} ---{RESET}")
                start_listening(settings)
                print(f"\n{YELLOW}[INFO] Kembali ke Menu Utama...{RESET}")
                time.sleep(2) # Jeda sebelum menampilkan menu lagi

        elif choice_key == 'settings':
            show_settings(settings)
            settings = load_settings() # Load ulang jika ada perubahan

        elif choice_key == 'exit':
            print(f"\n{CYAN}Terima kasih telah menggunakan Exora AI Listener! Sampai jumpa!{RESET}")
            sys.exit(0)

        elif choice_key == 'invalid': # Hanya untuk mode input teks
            print(f"\n{RED}[ERROR] Pilihan tidak valid. Masukkan 1, 2, atau 3.{RESET}")
            time.sleep(1.5)
        # else: # Tidak perlu else, inquirer menangani pilihan yang valid saja

# --- Entry Point ---
if __name__ == "__main__":
    # Cek versi Python jika perlu (misal, f-string butuh 3.6+)
    if sys.version_info < (3, 6):
        print(f"{RED}Error: Script ini membutuhkan Python 3.6 atau lebih tinggi.{RESET}")
        sys.exit(1)

    try:
        main_menu()
    except KeyboardInterrupt:
        # Seharusnya sudah ditangani oleh signal handler atau inquirer,
        # tapi sebagai fallback akhir.
        print(f"\n{YELLOW}{BOLD}[WARN] Program dihentikan paksa dari luar menu.{RESET}")
        sys.exit(1)
    except Exception as e:
        # Tangani error kritis yang tidak terduga di luar loop utama
        clear_screen() # Bersihkan layar sebelum menampilkan error fatal
        print(f"\n{BOLD}{RED}====================== ERROR KRITIS ======================{RESET}")
        print(f"{RED}Terjadi kesalahan fatal yang tidak tertangani di level atas:{RESET}")
        traceback.print_exc() # Tampilkan traceback lengkap
        print(f"\n{RED}Pesan Error: {e}{RESET}")
        print(f"{RED}Program tidak dapat melanjutkan dan akan keluar.{RESET}")
        print(f"{YELLOW}Mohon laporkan error ini jika terjadi berulang.{RESET}")
        print(f"{BOLD}{RED}========================================================={RESET}")
        input(f"{DIM}Tekan Enter untuk keluar...{RESET}") # Agar user sempat baca
        sys.exit(1)
