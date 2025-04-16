# -*- coding: utf-8 -*-
import imaplib
import email
from email.header import decode_header
import time
import datetime # Untuk timestamp
import subprocess
import json
import os
import getpass # Tetap ada jika diperlukan di masa depan, tapi input password dibuat eksplisit
import sys
import signal # Untuk menangani Ctrl+C
import traceback # Untuk mencetak traceback error
import socket # Untuk error koneksi

# --- Coba import inquirer untuk menu interaktif ---
try:
    import inquirer
    # from inquirer.themes import GreenPassion # Contoh tema jika ingin eksplorasi
    INQUIRER_AVAILABLE = True
except ImportError:
    INQUIRER_AVAILABLE = False
    # Pesan peringatan akan ditampilkan saat pertama kali menu dipanggil

# --- Binance Integration ---
try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException, BinanceOrderException
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False
    # Pesan peringatan dipindahkan ke awal agar lebih terlihat
    # Definisikan exception dummy jika library tidak ada agar script tidak crash
    class BinanceAPIException(Exception): pass
    class BinanceOrderException(Exception): pass
    class Client: # Dummy class
        # Tambahkan konstanta dummy jika diperlukan di logika lain
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
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"

# --- Fungsi Penanganan Sinyal (Ctrl+C) ---
def signal_handler(sig, frame):
    global running
    # Tambah baris baru agar tidak menimpa pesan 'mendengarkan'
    print(f"\n{YELLOW}[WARN] Ctrl+C terdeteksi. Menghentikan program...{RESET}")
    running = False
    # Beri sedikit waktu untuk loop lain berhenti jika memungkinkan
    # time.sleep(0.5) # Mungkin tidak perlu, tergantung loop
    print(f"{RED}[EXIT] Keluar dari program.{RESET}")
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
                # Pastikan semua kunci default ada, tambahkan jika belum
                for key, default_value in DEFAULT_SETTINGS.items():
                    if key not in loaded_settings:
                        print(f"{YELLOW}[WARN] Kunci '{key}' tidak ada di config, ditambahkan dengan nilai default: {default_value}{RESET}")
                        settings[key] = default_value
                    else:
                        settings[key] = loaded_settings[key]

                # Validasi tambahan setelah load (pindahkan ke sini)
                if not isinstance(settings.get("check_interval_seconds"), int) or settings.get("check_interval_seconds", 10) < 5:
                    print(f"{YELLOW}[WARN] Interval cek di '{CONFIG_FILE}' tidak valid (<5 atau bukan angka), direset ke 10.{RESET}")
                    settings["check_interval_seconds"] = DEFAULT_SETTINGS["check_interval_seconds"] # Gunakan default

                if not isinstance(settings.get("buy_quote_quantity"), (int, float)) or settings.get("buy_quote_quantity") <= 0:
                     print(f"{YELLOW}[WARN] 'buy_quote_quantity' tidak valid (<=0 atau bukan angka), direset ke {DEFAULT_SETTINGS['buy_quote_quantity']}.{RESET}")
                     settings["buy_quote_quantity"] = DEFAULT_SETTINGS['buy_quote_quantity']

                if not isinstance(settings.get("sell_base_quantity"), (int, float)) or settings.get("sell_base_quantity") < 0: # Allow 0
                     print(f"{YELLOW}[WARN] 'sell_base_quantity' tidak valid (<0 atau bukan angka), direset ke {DEFAULT_SETTINGS['sell_base_quantity']}.{RESET}")
                     settings["sell_base_quantity"] = DEFAULT_SETTINGS['sell_base_quantity']

                if not isinstance(settings.get("execute_binance_orders"), bool):
                    print(f"{YELLOW}[WARN] 'execute_binance_orders' tidak valid (bukan true/false), direset ke False.{RESET}")
                    settings["execute_binance_orders"] = False

                # Jika ada perubahan karena validasi atau penambahan kunci, simpan kembali
                if settings != loaded_settings:
                     print(f"{YELLOW}[INFO] Memperbarui file konfigurasi karena ada perbaikan/penambahan kunci.{RESET}")
                     save_settings(settings)

        except json.JSONDecodeError:
            print(f"{RED}[ERROR] File konfigurasi '{CONFIG_FILE}' rusak. Menggunakan default & menyimpan ulang.{RESET}")
            settings = DEFAULT_SETTINGS.copy() # Pastikan settings adalah default yang bersih
            save_settings(settings) # Simpan default yang bersih
        except Exception as e:
            print(f"{RED}[ERROR] Gagal memuat konfigurasi: {e}{RESET}")
            settings = DEFAULT_SETTINGS.copy() # Gunakan default jika ada error lain
            # Tidak menyimpan ulang jika error tidak diketahui
    else:
        # Jika file tidak ada, simpan default awal
        print(f"{YELLOW}[INFO] File konfigurasi '{CONFIG_FILE}' tidak ditemukan. Membuat dengan nilai default.{RESET}")
        settings = DEFAULT_SETTINGS.copy()
        save_settings(settings)
    return settings


def save_settings(settings):
    """Menyimpan pengaturan ke file JSON."""
    try:
        # Lakukan validasi tipe data sekali lagi sebelum menyimpan untuk keamanan
        settings_to_save = DEFAULT_SETTINGS.copy()
        settings_to_save.update(settings) # Timpa dengan data yang ada

        settings_to_save['check_interval_seconds'] = int(settings_to_save.get('check_interval_seconds', DEFAULT_SETTINGS['check_interval_seconds']))
        settings_to_save['buy_quote_quantity'] = float(settings_to_save.get('buy_quote_quantity', DEFAULT_SETTINGS['buy_quote_quantity']))
        settings_to_save['sell_base_quantity'] = float(settings_to_save.get('sell_base_quantity', DEFAULT_SETTINGS['sell_base_quantity']))
        settings_to_save['execute_binance_orders'] = bool(settings_to_save.get('execute_binance_orders', DEFAULT_SETTINGS['execute_binance_orders']))
        # Pastikan string tetap string
        settings_to_save['email_address'] = str(settings_to_save.get('email_address', ''))
        settings_to_save['app_password'] = str(settings_to_save.get('app_password', ''))
        settings_to_save['imap_server'] = str(settings_to_save.get('imap_server', DEFAULT_SETTINGS['imap_server']))
        settings_to_save['target_keyword'] = str(settings_to_save.get('target_keyword', DEFAULT_SETTINGS['target_keyword']))
        settings_to_save['trigger_keyword'] = str(settings_to_save.get('trigger_keyword', DEFAULT_SETTINGS['trigger_keyword']))
        settings_to_save['binance_api_key'] = str(settings_to_save.get('binance_api_key', ''))
        settings_to_save['binance_api_secret'] = str(settings_to_save.get('binance_api_secret', ''))
        settings_to_save['trading_pair'] = str(settings_to_save.get('trading_pair', DEFAULT_SETTINGS['trading_pair'])).upper() # Simpan dalam uppercase

        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings_to_save, f, indent=4, sort_keys=True) # Urutkan kunci agar lebih rapi
        # Tidak perlu print info save di sini karena sudah ada di load/edit
        # print(f"{GREEN}[INFO] Pengaturan berhasil disimpan ke '{CONFIG_FILE}'{RESET}")
    except Exception as e:
        print(f"{RED}[ERROR] Gagal menyimpan konfigurasi: {e}{RESET}")

# --- Fungsi Utilitas ---
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def decode_mime_words(s):
    """Mendekode header email MIME encoded-words."""
    if not s:
        return ""
    try:
        decoded_parts = decode_header(s)
        result = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                # Gunakan 'replace' untuk menangani karakter yang tidak bisa di-decode
                result.append(part.decode(encoding or 'utf-8', errors='replace'))
            else:
                # Jika sudah string (misal, tidak terenkode), tambahkan langsung
                result.append(part)
        return "".join(result)
    except Exception as e:
        print(f"{YELLOW}[WARN] Gagal mendekode header: {e}. Header asli: {s}{RESET}")
        # Kembalikan string asli jika decode gagal total
        return str(s) if isinstance(s, str) else repr(s)


def get_text_from_email(msg):
    """Mengekstrak konten teks plain dari objek email.message.Message."""
    text_content = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            # Ambil text/plain yang bukan attachment
            if content_type == "text/plain" and "attachment" not in content_disposition.lower():
                try:
                    charset = part.get_content_charset() or 'utf-8' # Default ke utf-8 jika tidak ada
                    payload = part.get_payload(decode=True) # Decode dari base64/quoted-printable
                    if payload:
                         # Ganti error decode dengan karakter pengganti unicode
                        text_content += payload.decode(charset, errors='replace')
                except LookupError: # Jika charset tidak dikenal Python
                    print(f"{YELLOW}[WARN] Charset tidak dikenal: {part.get_content_charset()}. Mencoba decode dengan utf-8 (errors replace).{RESET}")
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                             text_content += payload.decode('utf-8', errors='replace')
                    except Exception as e_utf8:
                         print(f"{YELLOW}[WARN] Gagal decode paksa ke utf-8: {e_utf8}{RESET}")
                except Exception as e:
                    print(f"{YELLOW}[WARN] Tidak bisa mendekode bagian email (multipart): {e}{RESET}")
    else:
        # Jika email bukan multipart
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                if payload:
                    text_content = payload.decode(charset, errors='replace')
            except LookupError:
                 print(f"{YELLOW}[WARN] Charset tidak dikenal: {msg.get_content_charset()}. Mencoba decode dengan utf-8 (errors replace).{RESET}")
                 try:
                     payload = msg.get_payload(decode=True)
                     if payload:
                         text_content = payload.decode('utf-8', errors='replace')
                 except Exception as e_utf8:
                     print(f"{YELLOW}[WARN] Gagal decode paksa ke utf-8: {e_utf8}{RESET}")
            except Exception as e:
                 print(f"{YELLOW}[WARN] Tidak bisa mendekode body email (non-multipart): {e}{RESET}")

    # Bersihkan whitespace berlebih dan return lowercase
    return " ".join(text_content.split()).lower()


# --- Fungsi Beep ---
def trigger_beep(action):
    """Memicu suara beep sistem berdasarkan aksi (buy/sell)."""
    try:
        # Gunakan frekuensi dan durasi berbeda untuk buy/sell
        if action == "buy":
            print(f"{MAGENTA}[ACTION] Memicu BEEP untuk '{BOLD}BUY{RESET}{MAGENTA}'{RESET}")
            # Nada lebih tinggi, durasi pendek, berulang
            subprocess.run(["beep", "-f", "1000", "-l", "300", "-D", "100", "-r", "3"], check=True, capture_output=True, text=True)
        elif action == "sell":
            print(f"{MAGENTA}[ACTION] Memicu BEEP untuk '{BOLD}SELL{RESET}{MAGENTA}'{RESET}")
            # Nada lebih rendah, durasi lebih panjang
            subprocess.run(["beep", "-f", "600", "-l", "600", "-D", "200", "-r", "2"], check=True, capture_output=True, text=True)
        else:
             print(f"{YELLOW}[WARN] Aksi beep tidak dikenal '{action}'.{RESET}")
    except FileNotFoundError:
        # Berikan instruksi instalasi jika 'beep' tidak ada (umum di Linux)
        print(f"{YELLOW}[WARN] Perintah 'beep' tidak ditemukan. Beep dilewati.{RESET}")
        print(f"{YELLOW}         (Di Linux, coba: sudo apt install beep / sudo yum install beep){RESET}")
    except subprocess.CalledProcessError as e:
        print(f"{RED}[ERROR] Gagal menjalankan 'beep': {e}{RESET}")
        if e.stderr: print(f"{RED}         Stderr: {e.stderr.strip()}{RESET}")
    except Exception as e:
        print(f"{RED}[ERROR] Kesalahan tak terduga saat beep: {e}{RESET}")

# --- Fungsi Eksekusi Binance ---
def get_binance_client(settings):
    """Membuat instance Binance client jika library tersedia dan kredensial ada."""
    if not BINANCE_AVAILABLE:
        # Tidak perlu print error di sini karena sudah dicek di tempat pemanggilan
        return None
    api_key = settings.get('binance_api_key')
    api_secret = settings.get('binance_api_secret')
    if not api_key or not api_secret:
        print(f"{RED}[ERROR] API Key atau Secret Key Binance belum diatur di konfigurasi.{RESET}")
        return None
    try:
        client = Client(api_key, api_secret)
        # Test koneksi (ping) penting untuk memastikan API key valid
        client.ping()
        print(f"{GREEN}[BINANCE] Koneksi & Autentikasi ke Binance API berhasil.{RESET}")
        return client
    except BinanceAPIException as e:
        print(f"{RED}[BINANCE ERROR] Gagal terhubung/autentikasi ke Binance: {e}{RESET}")
        if e.code == -2014 or "invalid" in e.message.lower(): # Cek error API key tidak valid
            print(f"{RED}         -> API Key atau Secret Key kemungkinan TIDAK VALID.{RESET}")
        elif e.code == -2015:
            print(f"{RED}         -> API Key atau Secret Key TIDAK VALID (Invalid API-key format).{RESET}")
        return None
    except requests.exceptions.RequestException as e: # Tangani error koneksi jaringan saat membuat client
        print(f"{RED}[NETWORK ERROR] Gagal terhubung ke Binance saat membuat client: {e}{RESET}")
        return None
    except Exception as e:
        print(f"{RED}[ERROR] Gagal membuat Binance client (kesalahan tak terduga): {e}{RESET}")
        return None

def execute_binance_order(client, settings, side):
    """Mengeksekusi order MARKET BUY atau SELL di Binance."""
    if not client:
        print(f"{RED}[BINANCE] Eksekusi dibatalkan, client Binance tidak valid atau tidak tersedia.{RESET}")
        return False
    # Pengaturan execute_binance_orders sudah dicek sebelum memanggil fungsi ini

    pair = settings.get('trading_pair', '').upper()
    if not pair:
        print(f"{RED}[BINANCE ERROR] Trading pair belum diatur di konfigurasi.{RESET}")
        return False

    order_details = {}
    action_desc = ""
    is_buy = (side == Client.SIDE_BUY)
    is_sell = (side == Client.SIDE_SELL)

    try:
        if is_buy:
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
            # Ambil info base dan quote dari pair untuk deskripsi
            try:
                info = client.get_symbol_info(pair)
                quote_asset = info['quoteAsset']
                action_desc = f"MARKET BUY {pair} senilai {quote_qty} {quote_asset}"
            except Exception: # Jika gagal ambil info, gunakan deskripsi generik
                 action_desc = f"MARKET BUY {pair} dengan quote qty {quote_qty}"


        elif is_sell:
            base_qty = settings.get('sell_base_quantity', 0.0)
            if base_qty <= 0:
                 # Error hanya jika memang ingin SELL, tapi quantity 0
                 print(f"{RED}[BINANCE ERROR] Kuantitas Jual (sell_base_quantity) harus > 0 untuk eksekusi SELL.{RESET}")
                 return False
            order_details = {
                'symbol': pair,
                'side': Client.SIDE_SELL,
                'type': Client.ORDER_TYPE_MARKET,
                'quantity': base_qty # Jual sejumlah base asset
            }
            # Ambil info base dan quote dari pair untuk deskripsi
            try:
                info = client.get_symbol_info(pair)
                base_asset = info['baseAsset']
                action_desc = f"MARKET SELL {base_qty} {base_asset} ({pair})"
            except Exception:
                 action_desc = f"MARKET SELL {base_qty} (base) of {pair}"

        else:
            print(f"{RED}[BINANCE ERROR] Sisi order tidak valid: {side}{RESET}")
            return False

        print(f"{MAGENTA}[BINANCE] Mencoba eksekusi: {action_desc}...{RESET}")

        # --- *** EKSEKUSI ORDER *** ---
        order_result = client.create_order(**order_details)
        # --- *** --------------- *** ---

        print(f"{GREEN}[BINANCE SUCCESS] Order berhasil dieksekusi!{RESET}")
        print(f"  Order ID : {order_result.get('orderId')}")
        print(f"  Symbol   : {order_result.get('symbol')}")
        print(f"  Side     : {order_result.get('side')}")
        print(f"  Status   : {order_result.get('status')}")

        # Hitung dan tampilkan detail fill jika ada
        if order_result.get('fills') and len(order_result['fills']) > 0:
            total_base_qty = sum(float(f['qty']) for f in order_result['fills'])
            total_quote_qty = sum(float(f['commission']) if f['commissionAsset'] != order_result['symbol'] else (float(f['qty']) * float(f['price'])) for f in order_result['fills']) # Lebih kompleks jika komisi dibayar dgn BNB dll. Ini asumsi sederhana.

            # Cara perhitungan avg_price yg lebih aman dari ZeroDivisionError
            if total_base_qty > 0:
                 # Hitung nilai quote total dari (qty * price)
                 total_quote_value = sum(float(f['qty']) * float(f['price']) for f in order_result['fills'])
                 avg_price = total_quote_value / total_base_qty
            else:
                 avg_price = 0 # Atau NaN?

            # Tentukan presisi berdasarkan symbol info jika memungkinkan
            price_precision = 8 # Default
            qty_precision = 8 # Default
            try:
                 info = client.get_symbol_info(pair)
                 price_precision = info['quotePrecision'] # Presisi harga quote
                 qty_precision = info['baseAssetPrecision'] # Presisi kuantitas base
            except Exception:
                pass # Gunakan default jika gagal

            print(f"  Avg Price: {avg_price:.{price_precision}f}")
            print(f"  Filled Qty: {total_base_qty:.{qty_precision}f} {order_result.get('symbol', '').replace(info.get('quoteAsset',''), '') if info else ''}") # Tampilkan base asset jika bisa
            if is_buy:
                print(f"  Cost Est.: {total_quote_value:.{price_precision}f} {info.get('quoteAsset','QUOTE') if info else 'QUOTE'}")
        else:
            print(f"  (Detail fills tidak tersedia di response)")

        return True

    except BinanceAPIException as e:
        print(f"{RED}[BINANCE API ERROR] Gagal eksekusi order ({action_desc}): {e.status_code} - {e.message}{RESET}")
        # Berikan petunjuk berdasarkan kode error umum
        if e.code == -2010 or 'insufficient balance' in e.message.lower(): # Insufficient balance
            print(f"{RED}         -> Kemungkinan saldo tidak cukup untuk {side}.{RESET}")
        elif e.code == -1121: # Invalid symbol
            print(f"{RED}         -> Trading pair '{pair}' tidak valid atau tidak ditemukan di Binance.{RESET}")
        elif e.code == -1013 or 'min_notional' in e.message.lower(): # Min notional filter
             print(f"{RED}         -> Nilai order terlalu kecil (cek filter MIN_NOTIONAL untuk {pair}).{RESET}")
        elif e.code == -1111 or 'lot_size' in e.message.lower(): # Lot size filter
             print(f"{RED}         -> Kuantitas order tidak sesuai dengan aturan step size (cek filter LOT_SIZE untuk {pair}).{RESET}")
        elif e.code == -2015: # Invalid API Key permissions
            print(f"{RED}         -> API Key tidak memiliki izin untuk trading ('Enable Spot & Margin Trading' harus dicentang).{RESET}")
        return False
    except BinanceOrderException as e: # Error spesifik order (jarang untuk market order, tapi ada)
        print(f"{RED}[BINANCE ORDER ERROR] Gagal eksekusi order ({action_desc}): {e.status_code} - {e.message}{RESET}")
        return False
    except requests.exceptions.RequestException as e: # Tangani error koneksi jaringan saat eksekusi
        print(f"{RED}[NETWORK ERROR] Gagal mengirim order ke Binance: {e}{RESET}")
        return False
    except Exception as e:
        print(f"{RED}[ERROR] Kesalahan tak terduga saat eksekusi order Binance ({action_desc}):{RESET}")
        traceback.print_exc() # Cetak traceback untuk debug error tak terduga
        return False

# --- Fungsi Pemrosesan Email ---
def process_email(mail, email_id, settings, binance_client):
    """Mengambil, mem-parsing, memproses satu email, dan memicu aksi jika sesuai."""
    global running
    if not running: return

    target_keyword_lower = settings.get('target_keyword', '').lower()
    trigger_keyword_lower = settings.get('trigger_keyword', '').lower()
    email_id_str = email_id.decode('utf-8')

    # Validasi keyword dasar sebelum fetch email
    if not target_keyword_lower or not trigger_keyword_lower:
         print(f"{YELLOW}[WARN] Keyword Target atau Trigger belum diatur di config. Lewati pemrosesan email {email_id_str}.{RESET}")
         # Tetap tandai sudah dibaca agar tidak diproses ulang
         try:
             mail.store(email_id, '+FLAGS', '\\Seen')
         except Exception as e_seen:
             print(f"{RED}[ERROR] Gagal menandai email {email_id_str} sebagai 'Seen' setelah skip: {e_seen}{RESET}")
         return

    try:
        status, data = mail.fetch(email_id, "(RFC822)")
        if status != 'OK':
            print(f"{RED}[ERROR] Gagal mengambil email ID {email_id_str}: Status {status}{RESET}")
            # Mungkin coba lagi nanti? Untuk sekarang, return saja.
            return

        # Parsing email
        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        subject = decode_mime_words(msg["Subject"])
        sender = decode_mime_words(msg["From"])
        # Ambil tanggal dari header jika ada, jika tidak pakai waktu sekarang
        date_tuple = email.utils.parsedate_tz(msg['Date'])
        email_timestamp_str = "N/A"
        if date_tuple:
            local_date = datetime.datetime.fromtimestamp(email.utils.mktime_tz(date_tuple))
            email_timestamp_str = local_date.strftime("%Y-%m-%d %H:%M:%S %Z") # Tampilkan timezone jika ada
        else:
            email_timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " (Received)"


        print(f"\n{CYAN}--- Memproses Email ({email_timestamp_str}) ---{RESET}")
        print(f" ID    : {email_id_str}")
        print(f" Dari  : {sender}")
        print(f" Subjek: {subject}")

        body = get_text_from_email(msg) # Body sudah lowercase
        subject_lower = subject.lower() # Subject juga lowercase untuk pencarian
        full_content = subject_lower + " " + body # Gabungkan subject dan body lowercase

        # --- Pencarian Keyword ---
        target_found = target_keyword_lower in full_content
        trigger_found = trigger_keyword_lower in full_content

        if target_found:
            print(f"{GREEN}[INFO] Keyword target '{settings['target_keyword']}' ditemukan.{RESET}")
            try:
                # Cari index pertama target keyword
                target_index = full_content.index(target_keyword_lower)
                # Cari index trigger keyword SETELAH target keyword
                trigger_index = full_content.index(trigger_keyword_lower, target_index + len(target_keyword_lower))

                # Ambil kata setelah trigger keyword
                start_word_index = trigger_index + len(trigger_keyword_lower)
                text_after_trigger = full_content[start_word_index:].lstrip() # Ambil teks setelahnya dan hapus spasi awal
                words_after_trigger = text_after_trigger.split(maxsplit=1) # Pisahkan hanya kata pertama

                if words_after_trigger:
                    action_word = words_after_trigger[0].strip('.,!?:;()[]{}').lower() # Bersihkan tanda baca umum
                    print(f"{GREEN}[INFO] Keyword trigger '{settings['trigger_keyword']}' ditemukan setelah target. Kata berikutnya: '{BOLD}{action_word}{RESET}{GREEN}'{RESET}")

                    # --- Trigger Aksi (Beep dan/atau Binance) ---
                    action_matched = False
                    if action_word == "buy":
                        action_matched = True
                        trigger_beep("buy")
                        # Eksekusi Binance BUY jika diaktifkan dan client valid
                        if settings.get("execute_binance_orders") and binance_client:
                           execute_binance_order(binance_client, settings, Client.SIDE_BUY)
                        elif settings.get("execute_binance_orders"):
                            print(f"{YELLOW}[WARN] Eksekusi Binance aktif tapi client tidak valid/tersedia saat ini.{RESET}")

                    elif action_word == "sell":
                        action_matched = True
                        trigger_beep("sell")
                        # Eksekusi Binance SELL jika diaktifkan dan client valid
                        if settings.get("execute_binance_orders") and binance_client:
                            # Validasi tambahan: pastikan sell quantity > 0
                            if settings.get('sell_base_quantity', 0.0) > 0:
                                execute_binance_order(binance_client, settings, Client.SIDE_SELL)
                            else:
                                print(f"{YELLOW}[WARN] Aksi 'sell' terdeteksi, tapi 'sell_base_quantity' di setting adalah 0. Order tidak dieksekusi.{RESET}")
                        elif settings.get("execute_binance_orders"):
                           print(f"{YELLOW}[WARN] Eksekusi Binance aktif tapi client tidak valid/tersedia saat ini.{RESET}")

                    if not action_matched:
                        print(f"{YELLOW}[WARN] Kata setelah trigger ({action_word}) bukan 'buy' atau 'sell'. Tidak ada aksi market.{RESET}")

                else:
                    # Trigger ditemukan setelah target, tapi tidak ada kata setelahnya
                    print(f"{YELLOW}[WARN] Keyword trigger '{settings['trigger_keyword']}' ditemukan setelah target, tapi tidak ada kata sesudahnya.{RESET}")

            except ValueError:
                # Ini terjadi jika trigger_keyword tidak ditemukan SETELAH target_keyword
                print(f"{YELLOW}[WARN] Keyword trigger '{settings['trigger_keyword']}' tidak ditemukan {BOLD}setelah{RESET}{YELLOW} keyword target '{settings['target_keyword']}'.{RESET}")
            except Exception as e:
                 print(f"{RED}[ERROR] Gagal parsing kata setelah trigger: {e}{RESET}")
                 traceback.print_exc() # Bantu debug jika ada error aneh
        else:
            # Target keyword tidak ditemukan sama sekali
            print(f"{BLUE}[INFO] Keyword target '{settings['target_keyword']}' tidak ditemukan dalam email ini.{RESET}")

        # --- Tandai email sebagai sudah dibaca ('Seen') ---
        # Lakukan ini terlepas dari apakah keyword ditemukan atau tidak,
        # agar email yang sama tidak diproses berulang kali.
        try:
            print(f"{BLUE}[INFO] Menandai email {email_id_str} sebagai sudah dibaca.{RESET}")
            res, _ = mail.store(email_id, '+FLAGS', '\\Seen')
            if res != 'OK':
                 print(f"{YELLOW}[WARN] Gagal menandai email {email_id_str} sebagai 'Seen', status: {res}{RESET}")
        except Exception as e:
            print(f"{RED}[ERROR] Gagal menandai email {email_id_str} sebagai 'Seen': {e}{RESET}")

        print(f"{CYAN}-------------------------------------------{RESET}")

    except (email.errors.MessageParseError, email.errors.HeaderParseError) as e_parse:
        print(f"{RED}[ERROR] Gagal mem-parsing email ID {email_id_str}: {e_parse}{RESET}")
        # Mungkin tandai sebagai seen agar tidak coba parse lagi?
        try: mail.store(email_id, '+FLAGS', '\\Seen')
        except: pass
    except Exception as e:
        print(f"{RED}[ERROR] Kesalahan tak terduga saat memproses email ID {email_id_str}:{RESET}")
        traceback.print_exc()
        # Coba tandai seen juga di sini
        try: mail.store(email_id, '+FLAGS', '\\Seen')
        except: pass


# --- Fungsi Listening Utama ---
def start_listening(settings):
    """Memulai loop untuk memeriksa email baru dan memprosesnya."""
    global running
    running = True # Pastikan flag running di-set true saat memulai
    mail = None
    binance_client = None
    initial_connection_attempt = True # Flag untuk pesan error login sekali saja
    consecutive_connection_errors = 0 # Lacak error koneksi beruntun
    max_consecutive_errors = 5 # Maksimal error sebelum jeda lebih lama
    wait_time_base = 30 # Waktu tunggu dasar (detik)
    wait_time_max = 300 # Waktu tunggu maksimal

    # --- Setup Binance Client di Awal (jika diaktifkan) ---
    if settings.get("execute_binance_orders"):
        if not BINANCE_AVAILABLE:
             print(f"{RED}[FATAL] Eksekusi Binance diaktifkan tapi library python-binance tidak ada!{RESET}")
             print(f"{YELLOW}         Silakan install dengan 'pip install python-binance' atau nonaktifkan eksekusi.{RESET}")
             # Tidak perlu return, biarkan menu utama yang mencegah start
             # running = False
             # return # Seharusnya tidak dipanggil jika validasi di menu utama jalan
        else:
             print(f"{CYAN}[SYS] Eksekusi Binance aktif. Mencoba menginisialisasi koneksi Binance API...{RESET}")
             binance_client = get_binance_client(settings)
             if not binance_client:
                 print(f"{RED}[FATAL] Gagal menginisialisasi Binance Client.{RESET}")
                 print(f"{YELLOW}         Eksekusi order TIDAK akan berjalan. Periksa API Key/Secret, izin API, dan koneksi internet.{RESET}")
                 print(f"{YELLOW}         Anda bisa menonaktifkan 'Eksekusi Order' di Pengaturan jika hanya butuh notifikasi email/beep.{RESET}")
                 # Tetap lanjutkan untuk listener email jika user mau
             else:
                 print(f"{GREEN}[SYS] Binance Client siap.{RESET}")
    else:
        print(f"{YELLOW}[INFO] Eksekusi order Binance dinonaktifkan di pengaturan ('execute_binance_orders': false).{RESET}")

    # --- Loop Utama Email Listener ---
    while running:
        try:
            # Jika mail tidak None (misal dari loop sebelumnya), coba logout dulu
            if mail and mail.state != 'LOGOUT':
                try:
                    mail.logout()
                except Exception:
                    pass # Abaikan error saat logout paksa
                mail = None

            # --- Koneksi IMAP ---
            print(f"{CYAN}[SYS] Mencoba menghubungkan ke server IMAP ({settings['imap_server']})...{RESET}")
            mail = imaplib.IMAP4_SSL(settings['imap_server'])
            print(f"{GREEN}[SYS] Terhubung ke {settings['imap_server']}. Mencoba login...{RESET}")
            # --- Login Email ---
            login_status, login_message = mail.login(settings['email_address'], settings['app_password'])
            if login_status != 'OK':
                # Pesan login failed lebih spesifik
                print(f"{RED}[FATAL] Login Email GAGAL!{RESET}")
                try:
                     # Coba decode pesan error jika ada
                     error_detail = login_message[0].decode() if login_message else "Tidak ada detail"
                     print(f"{RED}         Server merespon: {error_detail}{RESET}")
                except Exception:
                     print(f"{RED}         Server merespon: {login_message}{RESET}") # Tampilkan raw jika decode gagal
                print(f"{YELLOW}         -> Periksa kembali Alamat Email dan App Password di Pengaturan.{RESET}")
                print(f"{YELLOW}         -> Pastikan IMAP diaktifkan di pengaturan akun Gmail/Email Anda.{RESET}")
                print(f"{YELLOW}         -> Jika menggunakan Gmail & 2FA, pastikan App Password sudah benar dibuat.{RESET}")
                running = False # Hentikan loop utama karena login gagal
                break # Keluar dari while running

            # Jika login berhasil
            print(f"{GREEN}[SYS] Login email berhasil sebagai {BOLD}{settings['email_address']}{RESET}")
            initial_connection_attempt = True # Reset flag error login jika berhasil
            consecutive_connection_errors = 0 # Reset counter error koneksi
            mail.select("inbox") # Pilih INBOX
            print(f"{GREEN}[INFO] Memulai mode mendengarkan di INBOX... (Interval: {settings['check_interval_seconds']} detik){RESET}")
            print(f"{YELLOW}(Tekan Ctrl+C untuk berhenti){RESET}")
            print("-" * 50)

            # --- Loop Mendengarkan Email ---
            last_check_time = time.time() # Tandai waktu cek terakhir
            while running:
                current_time = time.time()
                # Hanya cek jika sudah melewati interval
                if current_time - last_check_time >= settings['check_interval_seconds']:
                    last_check_time = current_time # Update waktu cek terakhir

                    # 1. Cek Koneksi IMAP (NOOP)
                    try:
                        noop_status, _ = mail.noop()
                        if noop_status != 'OK':
                            print(f"\n{YELLOW}[WARN] Koneksi IMAP NOOP gagal (Status: {noop_status}). Mencoba reconnect...{RESET}")
                            break # Keluar loop inner untuk reconnect
                    except (imaplib.IMAP4.abort, imaplib.IMAP4.readonly, OSError, socket.error) as e_noop:
                         print(f"\n{YELLOW}[WARN] Koneksi IMAP terputus saat NOOP ({type(e_noop).__name__}). Mencoba reconnect...{RESET}")
                         break # Keluar loop inner untuk reconnect

                    # 2. Cek Koneksi/Status Binance (jika aktif)
                    if binance_client:
                        try:
                             binance_client.ping()
                             # print(f"{BLUE}[DEBUG] Binance Ping OK{RESET}", end='\r') # Optional debug
                        except (BinanceAPIException, requests.exceptions.RequestException, Exception) as PingErr:
                             print(f"\n{YELLOW}[WARN] Ping ke Binance API gagal ({type(PingErr).__name__}).{RESET}")
                             print(f"{YELLOW}         Mencoba membuat ulang Binance client...{RESET}")
                             binance_client = get_binance_client(settings) # Coba buat ulang client
                             if not binance_client:
                                  print(f"{RED}         Gagal membuat ulang Binance client. Eksekusi order mungkin gagal.{RESET}")
                             else:
                                  print(f"{GREEN}         Binance client berhasil dibuat ulang.{RESET}")
                             time.sleep(5) # Beri jeda setelah error ping/reconnect

                    # 3. Cari Email Baru (UNSEEN)
                    try:
                        search_status, messages = mail.search(None, '(UNSEEN)')
                        if search_status != 'OK':
                             print(f"\n{RED}[ERROR] Gagal mencari email UNSEEN (Status: {search_status}). Mencoba reconnect...{RESET}")
                             break # Keluar loop inner untuk reconnect

                        email_ids = messages[0].split()
                        if email_ids:
                            print(f"\n{GREEN}[INFO] Menemukan {len(email_ids)} email baru! Memproses...{RESET}")
                            for email_id in email_ids:
                                if not running: break # Cek flag running di setiap iterasi
                                process_email(mail, email_id, settings, binance_client)
                            if not running: break # Cek lagi setelah loop
                            print("-" * 50)
                            print(f"{GREEN}[INFO] Selesai memproses. Kembali mendengarkan...{RESET}")
                        else:
                            # Tampilkan pesan tunggu yang lebih informatif
                            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                            status_binance = f"{GREEN}OK{RESET}" if binance_client else f"{YELLOW}N/A{RESET}" if not settings.get("execute_binance_orders") else f"{RED}ERR{RESET}"
                            print(f"{BLUE}[{timestamp}] No new mail. Listening... (IMAP: {GREEN}OK{RESET}, Binance: {status_binance}){RESET}   ", end='\r')

                    except (imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError, socket.error) as e_search:
                         print(f"\n{RED}[ERROR] Error saat mencari email ({type(e_search).__name__}). Mencoba reconnect...{RESET}")
                         break # Keluar loop inner
                    except Exception as e_inner:
                         print(f"\n{RED}[ERROR] Kesalahan tak terduga di loop listener:{RESET}")
                         traceback.print_exc()
                         print(f"{YELLOW}         Mencoba melanjutkan...{RESET}")
                         time.sleep(5) # Jeda singkat sebelum lanjut loop inner

                # Tunggu 1 detik sebelum cek waktu lagi (mengurangi penggunaan CPU)
                # Cek flag running di sini juga agar bisa berhenti lebih cepat
                if not running: break
                time.sleep(1)

            # --- Keluar dari Loop Mendengarkan (Inner) ---
            # Jika keluar karena `running` jadi False, tidak perlu coba reconnect
            if not running:
                 break # Keluar dari loop utama (outer) juga

            # Jika keluar karena error (break), coba tutup koneksi sebelum reconnect
            if mail and mail.state == 'SELECTED':
                try:
                    print(f"\n{CYAN}[SYS] Menutup koneksi IMAP sebelum reconnect...{RESET}")
                    mail.close()
                    mail.logout()
                except Exception:
                    pass # Abaikan error saat tutup paksa
                mail = None

        # --- Exception Handling untuk Koneksi/Login (Outer Loop) ---
        except (imaplib.IMAP4.error, imaplib.IMAP4.abort) as e:
            print(f"\n{RED}[ERROR] Kesalahan IMAP: {e}{RESET}")
            if "authentication failed" in str(e).lower() or "invalid credentials" in str(e).lower() or (hasattr(e, 'args') and e.args and "login failed" in str(e.args[0]).lower()):
                # Hanya tampilkan pesan fatal jika ini percobaan pertama setelah start/sukses login
                if initial_connection_attempt:
                    print(f"{RED}[FATAL] Login Email GAGAL! Periksa Alamat Email dan App Password.{RESET}")
                    running = False # Hentikan jika login gagal total
                    break
                else:
                    # Jika sudah pernah login, mungkin hanya masalah sementara
                    print(f"{YELLOW}[WARN] Autentikasi gagal saat reconnect. Mungkin masalah sementara atau password diganti?{RESET}")
            else:
                 print(f"{YELLOW}[WARN] Kesalahan IMAP lain terjadi.{RESET}")
            initial_connection_attempt = False # Tandai sudah bukan percobaan awal
            consecutive_connection_errors += 1

        except (ConnectionError, OSError, socket.error, socket.gaierror, TimeoutError) as e:
             print(f"\n{RED}[ERROR] Kesalahan Koneksi Jaringan: {e}{RESET}")
             print(f"{YELLOW}         Periksa koneksi internet Anda.{RESET}")
             initial_connection_attempt = False
             consecutive_connection_errors += 1

        except Exception as e:
            print(f"\n{RED}[ERROR] Kesalahan tak terduga di loop utama (koneksi/login):{RESET}")
            traceback.print_exc()
            initial_connection_attempt = False
            consecutive_connection_errors += 1

        finally:
            # Pastikan logout jika objek mail masih ada dan terkoneksi
            if mail and mail.state != 'LOGOUT':
                try:
                    if mail.state == 'SELECTED': mail.close()
                    mail.logout()
                    print(f"{CYAN}[SYS] Logout dari server IMAP.{RESET}")
                except Exception: pass
            mail = None # Set mail ke None setelah logout/error

        # --- Logika Reconnect dengan Jeda Bertingkat ---
        if running: # Hanya coba reconnect jika program masih diperintahkan jalan
             wait_time = min(wait_time_base * (2 ** min(consecutive_connection_errors, 4)), wait_time_max) # Exponential backoff
             print(f"{YELLOW}[WARN] Mencoba menghubungkan kembali dalam {wait_time} detik... ({consecutive_connection_errors}/{max_consecutive_errors} error beruntun){RESET}")
             # Tambahkan jeda sebelum loop berikutnya, sambil cek flag running
             for _ in range(wait_time):
                 if not running: break
                 time.sleep(1)
             if not running: break # Keluar jika dihentikan saat menunggu

    # --- Program Berakhir ---
    print(f"\n{YELLOW}[INFO] Mode mendengarkan dihentikan.{RESET}")
    # Pastikan logout sekali lagi jika loop berhenti tiba-tiba
    if mail and mail.state != 'LOGOUT':
        try: mail.logout()
        except: pass


# --- Fungsi Menu Pengaturan ---
def show_settings(settings):
    """Menampilkan dan mengedit pengaturan menggunakan input standar."""
    while True:
        clear_screen()
        print(f"{BOLD}{CYAN}--- Pengaturan Email & Binance Listener ---{RESET}")
        print("\n--- Email Settings ---")
        print(f" 1. {CYAN}Alamat Email{RESET}   : {settings.get('email_address') or '[Belum diatur]'}")
        # Tampilkan password sebagian tersensor untuk keamanan minimal
        pwd_display = settings.get('app_password')
        if pwd_display and len(pwd_display) > 4:
            pwd_display = pwd_display[:2] + '*' * (len(pwd_display) - 4) + pwd_display[-2:]
        elif pwd_display:
             pwd_display = '*' * len(pwd_display)
        else:
             pwd_display = '[Belum diatur]'
        print(f" 2. {CYAN}App Password{RESET}   : {pwd_display}")
        print(f" 3. {CYAN}Server IMAP{RESET}    : {settings.get('imap_server', DEFAULT_SETTINGS['imap_server'])}")
        print(f" 4. {CYAN}Interval Cek{RESET}   : {settings.get('check_interval_seconds', DEFAULT_SETTINGS['check_interval_seconds'])} detik")
        print(f" 5. {CYAN}Keyword Target{RESET} : {settings.get('target_keyword', DEFAULT_SETTINGS['target_keyword'])}")
        print(f" 6. {CYAN}Keyword Trigger{RESET}: {settings.get('trigger_keyword', DEFAULT_SETTINGS['trigger_keyword'])}")

        print("\n--- Binance Settings ---")
        binance_status = f"{GREEN}Tersedia{RESET}" if BINANCE_AVAILABLE else f"{RED}Tidak Tersedia (Install 'python-binance'){RESET}"
        print(f" Library Status      : {binance_status}")
        # Sensor API Key & Secret
        api_key_display = settings.get('binance_api_key')
        api_secret_display = settings.get('binance_api_secret')
        api_key_display = api_key_display[:5] + '...' + api_key_display[-5:] if api_key_display and len(api_key_display) > 10 else ('*' * len(api_key_display) if api_key_display else '[Belum diatur]')
        api_secret_display = api_secret_display[:5] + '...' + api_secret_display[-5:] if api_secret_display and len(api_secret_display) > 10 else ('*' * len(api_secret_display) if api_secret_display else '[Belum diatur]')

        print(f" 7. {CYAN}API Key{RESET}        : {api_key_display}")
        print(f" 8. {CYAN}API Secret{RESET}     : {api_secret_display}")
        print(f" 9. {CYAN}Trading Pair{RESET}   : {settings.get('trading_pair') or '[Belum diatur]'}")
        print(f"10. {CYAN}Buy Quote Qty{RESET}  : {settings.get('buy_quote_quantity', DEFAULT_SETTINGS['buy_quote_quantity'])} (Contoh: USDT)")
        print(f"11. {CYAN}Sell Base Qty{RESET}  : {settings.get('sell_base_quantity', DEFAULT_SETTINGS['sell_base_quantity'])} (Contoh: BTC)")
        exec_status = f"{GREEN}Aktif{RESET}" if settings.get('execute_binance_orders') else f"{RED}Nonaktif{RESET}"
        print(f"12. {CYAN}Eksekusi Order{RESET} : {exec_status}")
        print("-" * 30)

        # --- Opsi Menu Pengaturan dengan Inquirer ---
        choice_key = None # Variabel untuk menyimpan hasil pilihan ('e' atau 'k')
        settings_options = [
            (f"{YELLOW}E{RESET} - Edit Pengaturan", 'e'),
            (f"{YELLOW}K{RESET} - Kembali ke Menu Utama", 'k')
        ]

        if INQUIRER_AVAILABLE:
            question = [
                inquirer.List('action',
                              message="Pilih opsi",
                              choices=[opt[0] for opt in settings_options], # Tampilkan teksnya saja
                              carousel=True # Navigasi bisa berputar
                             )
            ]
            try:
                answer = inquirer.prompt(question)#, theme=GreenPassion()) # Bisa pakai tema
                if answer:
                    # Cari key ('e'/'k') berdasarkan teks yang dipilih
                    selected_text = answer['action']
                    for text, key in settings_options:
                        if text == selected_text:
                            choice_key = key
                            break
                else: # Jika user tekan Ctrl+C di prompt inquirer
                    signal_handler(None, None) # Panggil handler Ctrl+C
                    return # Keluar dari show_settings

            except Exception as e:
                print(f"\n{RED}[ERROR] Gagal menampilkan menu interaktif pengaturan: {e}{RESET}")
                print(f"{YELLOW}Menggunakan input teks standar.{RESET}")
                choice_key = input("Pilih opsi (E/K): ").lower().strip()
        else:
            # Fallback jika inquirer tidak ada
            choice_key = input("Pilih opsi (E/K): ").lower().strip()

        # --- Logika Berdasarkan Pilihan ---
        if choice_key == 'e':
            print(f"\n{BOLD}{MAGENTA}--- Edit Pengaturan ---{RESET}")
            print(f"{YELLOW}(Kosongkan input untuk menggunakan nilai saat ini){RESET}")
            original_settings = settings.copy() # Simpan state awal

            # --- Edit Email ---
            print(f"\n{CYAN}--- Email ---{RESET}")
            new_val = input(f" 1. Email [{settings.get('email_address')}]: ").strip()
            if new_val: settings['email_address'] = new_val

            # Minta password baru, jangan tampilkan yang lama
            new_pass = input(f" 2. App Password Baru (kosongkan jika tidak ingin ubah): ").strip()
            if new_pass: settings['app_password'] = new_pass

            new_val = input(f" 3. Server IMAP [{settings.get('imap_server', DEFAULT_SETTINGS['imap_server'])}]: ").strip()
            if new_val: settings['imap_server'] = new_val
            while True:
                current_interval = settings.get('check_interval_seconds', DEFAULT_SETTINGS['check_interval_seconds'])
                new_val_str = input(f" 4. Interval (detik) [{current_interval}], min 5: ").strip()
                if not new_val_str: break # Kosong = tidak ubah
                try:
                    new_interval = int(new_val_str)
                    if new_interval >= 5:
                        settings['check_interval_seconds'] = new_interval
                        break
                    else: print(f"   {RED}[ERROR] Interval minimal 5 detik.{RESET}")
                except ValueError: print(f"   {RED}[ERROR] Masukkan angka bulat.{RESET}")

            new_val = input(f" 5. Keyword Target [{settings.get('target_keyword', DEFAULT_SETTINGS['target_keyword'])}]: ").strip()
            if new_val: settings['target_keyword'] = new_val
            new_val = input(f" 6. Keyword Trigger [{settings.get('trigger_keyword', DEFAULT_SETTINGS['trigger_keyword'])}]: ").strip()
            if new_val: settings['trigger_keyword'] = new_val

            # --- Edit Binance ---
            print(f"\n{CYAN}--- Binance ---{RESET}")
            if not BINANCE_AVAILABLE:
                 print(f"{YELLOW}   (Library Binance tidak terinstall, pengaturan Binance mungkin tidak berpengaruh){RESET}")

            new_val = input(f" 7. API Key Baru (kosongkan jika tidak ubah): ").strip()
            if new_val: settings['binance_api_key'] = new_val
            new_val = input(f" 8. API Secret Baru (kosongkan jika tidak ubah): ").strip()
            if new_val: settings['binance_api_secret'] = new_val
            new_val = input(f" 9. Trading Pair (e.g., BTCUSDT) [{settings.get('trading_pair')}]: ").strip().upper() # Selalu uppercase
            if new_val: settings['trading_pair'] = new_val

            while True:
                 current_buy_qty = settings.get('buy_quote_quantity', DEFAULT_SETTINGS['buy_quote_quantity'])
                 new_val_str = input(f"10. Buy Quote Qty (e.g., 11.0 USDT) [{current_buy_qty}], harus > 0: ").strip()
                 if not new_val_str: break
                 try:
                     new_qty = float(new_val_str)
                     if new_qty > 0:
                         settings['buy_quote_quantity'] = new_qty
                         break
                     else: print(f"   {RED}[ERROR] Kuantitas Beli (Quote) harus lebih besar dari 0.{RESET}")
                 except ValueError: print(f"   {RED}[ERROR] Masukkan angka desimal (contoh: 11.0 atau 15.5).{RESET}")

            while True:
                 current_sell_qty = settings.get('sell_base_quantity', DEFAULT_SETTINGS['sell_base_quantity'])
                 new_val_str = input(f"11. Sell Base Qty (e.g., 0.0005 BTC) [{current_sell_qty}], harus >= 0: ").strip()
                 if not new_val_str: break
                 try:
                     new_qty = float(new_val_str)
                     if new_qty >= 0: # Boleh 0 jika tidak ingin eksekusi sell
                         settings['sell_base_quantity'] = new_qty
                         break
                     else: print(f"   {RED}[ERROR] Kuantitas Jual (Base) harus 0 atau lebih besar.{RESET}")
                 except ValueError: print(f"   {RED}[ERROR] Masukkan angka desimal (contoh: 0.0005 atau 0).{RESET}")

            while True:
                 current_exec_bool = settings.get('execute_binance_orders', False)
                 current_exec_display = f"{GREEN}Aktif{RESET}" if current_exec_bool else f"{RED}Nonaktif{RESET}"
                 prompt_text = f"12. Eksekusi Order Binance? (y/n) [{current_exec_display}]: "
                 new_val_str = input(prompt_text).lower().strip()
                 if not new_val_str: break # Tidak ubah
                 if new_val_str == 'y':
                     settings['execute_binance_orders'] = True
                     break
                 elif new_val_str == 'n':
                     settings['execute_binance_orders'] = False
                     break
                 else: print(f"   {RED}[ERROR] Masukkan 'y' (untuk aktif) atau 'n' (untuk nonaktif).{RESET}")

            # Simpan jika ada perubahan
            if settings != original_settings:
                save_settings(settings)
                print(f"\n{GREEN}[INFO] Pengaturan diperbarui dan disimpan.{RESET}")
            else:
                 print(f"\n{BLUE}[INFO] Tidak ada perubahan pengaturan.{RESET}")
            time.sleep(2) # Beri waktu user membaca pesan

        elif choice_key == 'k':
            break # Keluar dari loop pengaturan
        else:
            # Hanya tampilkan error jika choice_key bukan None (artinya ada input tapi salah)
            if choice_key is not None:
                 print(f"\n{RED}[ERROR] Pilihan tidak valid. Coba lagi.{RESET}")
                 time.sleep(1.5)
            # Jika choice_key adalah None (misal dari Ctrl+C di inquirer), tidak perlu pesan error

# --- Fungsi Menu Utama ---
def main_menu():
    """Menampilkan menu utama aplikasi menggunakan inquirer jika tersedia."""
    # Tampilkan peringatan library yang hilang di awal
    if not BINANCE_AVAILABLE:
        print(f"\n{YELLOW}!!! WARNING: Library 'python-binance' tidak ditemukan. !!!{RESET}")
        print(f"{YELLOW}!!!          Fitur eksekusi order Binance tidak akan berfungsi. !!!{RESET}")
        print(f"{YELLOW}!!!          Install dengan: pip install python-binance         !!!{RESET}\n")
        time.sleep(1) # Jeda sedikit
    if not INQUIRER_AVAILABLE:
        print(f"\n{YELLOW}!!! WARNING: Library 'inquirer' tidak ditemukan. Menu akan menggunakan input teks biasa. !!!{RESET}")
        print(f"{YELLOW}!!!          Untuk menu interaktif, install dengan: pip install inquirer               !!!{RESET}\n")
        time.sleep(1)

    settings = load_settings() # Muat pengaturan sekali di awal

    while True:
        # Muat ulang pengaturan setiap kali kembali ke menu utama, kalau-kalau diedit
        settings = load_settings()
        clear_screen()
        print(f"{BOLD}{MAGENTA}========================================{RESET}")
        print(f"{BOLD}{MAGENTA}   Exora AI - Email & Binance Listener  {RESET}")
        print(f"{BOLD}{MAGENTA}========================================{RESET}")

        # --- Tampilkan Status Konfigurasi ---
        print("\n--- Status Konfigurasi ---")
        email_status = f"{GREEN}OK{RESET}" if settings.get('email_address') else f"{RED}BELUM DIATUR{RESET}"
        pass_status = f"{GREEN}OK{RESET}" if settings.get('app_password') else f"{RED}BELUM DIATUR{RESET}"
        print(f" Email           : [{email_status}] | App Password: [{pass_status}]")

        api_status = f"{GREEN}OK{RESET}" if settings.get('binance_api_key') else f"{RED}BELUM DIATUR{RESET}"
        secret_status = f"{GREEN}OK{RESET}" if settings.get('binance_api_secret') else f"{RED}BELUM DIATUR{RESET}"
        pair_status = f"{GREEN}{settings.get('trading_pair')}{RESET}" if settings.get('trading_pair') else f"{RED}BELUM DIATUR{RESET}"
        exec_mode = settings.get('execute_binance_orders', False)
        exec_status = f"{GREEN}AKTIF{RESET}" if exec_mode else f"{YELLOW}NONAKTIF{RESET}"
        binance_lib_status = f"{GREEN}OK{RESET}" if BINANCE_AVAILABLE else f"{RED}TIDAK ADA{RESET}"
        print(f" Binance Library : [{binance_lib_status}]")
        print(f" Binance Akun    : [{api_status}] API Key | [{secret_status}] Secret | [{pair_status}] Pair")
        print(f" Binance Eksekusi: [{exec_status}] (Buy: {settings.get('buy_quote_quantity')}, Sell: {settings.get('sell_base_quantity')})")
        print("-" * 40)

        # --- Opsi Menu Utama dengan Inquirer ---
        choice_key = None # Variabel penyimpan hasil ('1', '2', '3')

        # Tentukan teks opsi pertama berdasarkan status eksekusi Binance
        listen_option_text = f"{GREEN}1.{RESET} Mulai Mendengarkan (Email"
        if settings.get("execute_binance_orders"):
            if BINANCE_AVAILABLE:
                listen_option_text += f" & {BOLD}Binance Order{RESET}{GREEN}"
            else:
                listen_option_text += f" & {RED}Binance Order [LIB HILANG]{RESET}{GREEN}"
        listen_option_text += ")"

        main_menu_options = [
            (listen_option_text, '1'),
            (f"{CYAN}2.{RESET} Pengaturan", '2'),
            (f"{YELLOW}3.{RESET} Keluar", '3')
        ]

        if INQUIRER_AVAILABLE:
            question = [
                inquirer.List('action',
                              message="Silakan pilih opsi",
                              choices=[opt[0] for opt in main_menu_options],
                              carousel=True
                             )
            ]
            try:
                answer = inquirer.prompt(question)#, theme=GreenPassion())
                if answer:
                     # Cari key ('1'/'2'/'3') berdasarkan teks yang dipilih
                    selected_text = answer['action']
                    for text, key in main_menu_options:
                        if text == selected_text:
                            choice_key = key
                            break
                else: # Ctrl+C di prompt inquirer
                    signal_handler(None, None)
                    # Seharusnya exit, tapi untuk jaga-jaga:
                    return # Keluar dari main_menu
            except Exception as e:
                 print(f"\n{RED}[ERROR] Gagal menampilkan menu interaktif utama: {e}{RESET}")
                 print(f"{YELLOW}Menggunakan input teks standar.{RESET}")
                 choice_key = input("Masukkan pilihan Anda (1/2/3): ").strip()
        else:
             # Fallback jika inquirer tidak ada
             choice_key = input("Masukkan pilihan Anda (1/2/3): ").strip()

        # --- Logika Berdasarkan Pilihan ---
        if choice_key == '1':
            # Validasi sebelum memulai listening
            can_start = True
            print("\n--- Memeriksa Kesiapan ---")
            if not settings.get('email_address') or not settings.get('app_password'):
                print(f"{RED}[ERROR] Pengaturan Email (Alamat/App Password) belum lengkap!{RESET}")
                can_start = False
            else:
                print(f"{GREEN}[OK] Pengaturan Email Lengkap.{RESET}")

            execute_binance = settings.get("execute_binance_orders")
            if execute_binance:
                print(f"{BLUE}[INFO] Mode Eksekusi Binance Aktif. Memeriksa konfigurasi Binance...{RESET}")
                if not BINANCE_AVAILABLE:
                     print(f"{RED}[ERROR] Library 'python-binance' tidak ditemukan! Tidak bisa eksekusi order.{RESET}")
                     print(f"{YELLOW}         Nonaktifkan 'Eksekusi Order' di pengaturan atau install library.{RESET}")
                     can_start = False
                else:
                    valid_binance_creds = settings.get('binance_api_key') and settings.get('binance_api_secret')
                    valid_binance_pair = settings.get('trading_pair')
                    # Validasi quantity hanya perlu jika ingin eksekusi
                    # Buy selalu perlu > 0 jika mau buy
                    valid_buy_qty = settings.get('buy_quote_quantity', 0.0) > 0
                    # Sell perlu > 0 HANYA jika ingin melakukan aksi sell
                    # Jika sell_base_quantity = 0, itu valid tapi tidak akan bisa sell
                    # valid_sell_qty = settings.get('sell_base_quantity', 0.0) > 0 # Ini tidak perlu untuk start

                    if not valid_binance_creds:
                         print(f"{RED}[ERROR] API Key atau Secret Key Binance belum diatur!{RESET}")
                         can_start = False
                    elif not valid_binance_pair:
                        print(f"{RED}[ERROR] Trading Pair Binance belum diatur!{RESET}")
                        can_start = False
                    elif not valid_buy_qty:
                         print(f"{RED}[ERROR] 'Buy Quote Qty' harus lebih besar dari 0!{RESET}")
                         can_start = False
                    # Tidak perlu cek sell qty > 0 untuk memulai
                    # else:
                    #      print(f"{GREEN}[OK] Pengaturan dasar Binance lengkap.{RESET}")
                    if can_start: # Jika lolos semua cek di atas
                         print(f"{GREEN}[OK] Pengaturan Binance (Key, Secret, Pair, Buy Qty) valid untuk memulai.{RESET}")
                         if settings.get('sell_base_quantity', 0.0) <= 0:
                             print(f"{YELLOW}[WARN] 'Sell Base Qty' adalah 0. Eksekusi 'sell' tidak akan berfungsi.{RESET}")

            else:
                 print(f"{BLUE}[INFO] Mode Eksekusi Binance Nonaktif. Hanya listener email & beep.{RESET}")


            if can_start:
                clear_screen()
                mode = f"Email Listener Only{' & Beep' if 'beep' in os.getenv('PATH', '').lower() or os.path.exists('/usr/bin/beep') else ''}" # Cek sederhana 'beep'
                if execute_binance and BINANCE_AVAILABLE:
                    mode = "Email & Binance Order Execution"
                elif execute_binance:
                    mode = "Email Listener (Eksekusi Binance Gagal - Library Hilang)"

                print(f"{BOLD}{GREEN}--- Memulai Mode: {mode} ---{RESET}")
                # Reset flag running sebelum memulai (jika user stop-start tanpa keluar)
                global running
                running = True
                start_listening(settings)
                # Setelah start_listening selesai (karena Ctrl+C atau error fatal)
                print(f"\n{YELLOW}[INFO] Kembali ke Menu Utama...{RESET}")
                time.sleep(2)
            else:
                print(f"\n{YELLOW}Gagal memulai. Silakan perbaiki pengaturan melalui Opsi 2.{RESET}")
                time.sleep(4)

        elif choice_key == '2':
            show_settings(settings)
            # Pengaturan akan di-load ulang di awal loop while
        elif choice_key == '3':
            print(f"\n{CYAN}Terima kasih telah menggunakan Exora AI Listener! Sampai jumpa!{RESET}")
            sys.exit(0)
        else:
             # Hanya tampilkan error jika choice_key bukan None (artinya input salah)
            if choice_key is not None:
                 print(f"\n{RED}[ERROR] Pilihan tidak valid. Masukkan 1, 2, atau 3.{RESET}")
                 time.sleep(1.5)
            # Jika choice_key None (dari Ctrl+C), tidak perlu error, loop akan lanjut / keluar

# --- Entry Point ---
if __name__ == "__main__":
    try:
        # Panggil main_menu untuk memulai aplikasi
        main_menu()
    except KeyboardInterrupt:
        # Ini seharusnya sudah ditangani oleh signal_handler, tapi sebagai fallback
        print(f"\n{YELLOW}[WARN] Program dihentikan paksa (KeyboardInterrupt di level atas).{RESET}")
        sys.exit(1)
    except Exception as e:
        # Tangkap error tak terduga yang mungkin terjadi di luar loop utama
        print(f"\n{BOLD}{RED}===== ERROR KRITIS TAK TERDUGA ====={RESET}")
        traceback.print_exc() # Tampilkan detail error
        print(f"\n{RED}Terjadi error kritis yang tidak tertangani: {e}{RESET}")
        print("Program akan keluar.")
        sys.exit(1)
