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
import random # Untuk variasi kecil

# --- Binance Integration ---
# (Kode Binance Integration tetap sama - Tidak diubah)
try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException, BinanceOrderException
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False
    class BinanceAPIException(Exception): pass
    class BinanceOrderException(Exception): pass
    class Client:
        SIDE_BUY = 'BUY'
        SIDE_SELL = 'SELL'
        ORDER_TYPE_MARKET = 'MARKET'

# --- Konfigurasi & Variabel Global ---
CONFIG_FILE = "config.json"
DEFAULT_SETTINGS = {
    "email_address": "",
    "app_password": "",
    "imap_server": "imap.gmail.com",
    "check_interval_seconds": 10,
    "target_keyword": "Exora AI",
    "trigger_keyword": "order",
    "binance_api_key": "",
    "binance_api_secret": "",
    "trading_pair": "BTCUSDT",
    "buy_quote_quantity": 11.0,
    "sell_base_quantity": 0.0,
    "execute_binance_orders": False
}
running = True

# --- Kode Warna ANSI & Style ---
# (Tetap sama - Tidak diubah)
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m" # Mungkin tidak support di semua terminal
UNDERLINE = "\033[4m"
BLINK = "\033[5m" # Hindari jika bisa, sering mengganggu
REVERSE = "\033[7m" # Tukar foreground/background
HIDDEN = "\033[8m" # Teks tersembunyi
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"
BRIGHT_RED = "\033[91m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_YELLOW = "\033[93m"
BRIGHT_BLUE = "\033[94m"
BRIGHT_MAGENTA = "\033[95m"
BRIGHT_CYAN = "\033[96m"
BRIGHT_WHITE = "\033[97m"
BG_RED = "\033[41m"
BG_GREEN = "\033[42m"
BG_BLUE = "\033[44m"

# --- Karakter "Animasi" ---
# (Tetap sama - Tidak diubah)
spinner_chars = ['▹▹▹▹▹', '▸▹▹▹▹', '▹▸▹▹▹', '▹▹▸▹▹', '▹▹▹▸▹', '▹▹▹▹▸']
loading_bar_char = '█'
wipe_char = '▓' # Karakter untuk efek wipe
status_ok = f"{GREEN}✔{RESET}"
status_nok = f"{RED}✘{RESET}"
status_warn = f"{YELLOW}⚠{RESET}"
status_wait = f"{BLUE}⏳{RESET}"

# --- ASCII Art ---
# (Tetap sama - Tidak diubah)
ROCKET_ART = [
    "        .",
    "       / \\",
    "      / _ \\",
    "     |.o '.|",
    "     |'._.'|",
    "     |     |",
    "   ,'|  .  |.",
    "  /  |     |  \\",
    " |   `-----'   |",
    "  \\ '._____.' /",
    "   '.________.'",
    "      |     |",
    "      |     |",
    "      |     |",
    "     /| | | |\\",
    "    / | | | | \\",
    "   `-._____.-'",
    "      '---'"
]

# --- Fungsi Utilitas Tampilan ---
def clear_screen():
    """Membersihkan layar terminal."""
    os.system('cls' if os.name == 'nt' else 'clear')

def get_terminal_size():
    """Mendapatkan ukuran terminal (baris, kolom). Fallback ke default jika gagal."""
    try:
        # Cara standar (mungkin butuh library 'shutil' di Python 3.3+)
        columns, rows = os.get_terminal_size(0)
    except (OSError, AttributeError, NameError, TypeError): # Tambah TypeError just in case
        try:
            # Fallback untuk beberapa environment Unix-like
            rows, columns = map(int, os.popen('stty size', 'r').read().split())
        except ValueError:
            # Default jika semua gagal
            rows, columns = 24, 80 # Default standar
    return rows, columns

def print_centered(text, width, color=RESET):
    """Mencetak teks di tengah lebar yang diberikan."""
    # Hitung panjang teks tanpa ANSI codes untuk centering yang benar
    plain_text = ''.join(c for c in text if 31 < ord(c) < 127) # Perkiraan kasar, bisa kurang akurat
    # Kalkulasi padding berdasarkan perkiraan panjang teks asli (termasuk warna)
    # Ini mungkin tidak sempurna jika warna ada di tengah teks, tapi cukup baik untuk header
    padding = max(0, (width - len(plain_text))) // 2
    print(f"{' ' * padding}{color}{text}{RESET}") # Terapkan warna pada seluruh teks

def print_separator(char="─", length=None, color=DIM + WHITE + RESET):
    """Mencetak garis pemisah dengan panjang adaptif atau tetap."""
    if length is None:
        _, cols = get_terminal_size()
        length = cols - 4 # Default ke lebar terminal - margin
    print(f"{color}{char * length}{RESET}")

def wipe_effect(rows, cols, char=wipe_char, delay=0.005, color=DIM):
    """Efek wipe sederhana yang mengisi layar dari atas/bawah ke tengah."""
    for r in range(rows // 2 + 1): # +1 agar tengahnya juga terisi
        line = char * cols
        # Pastikan tidak menulis di luar batas baris
        if r + 1 <= rows:
            sys.stdout.write(f"\033[{r + 1};1H{color}{line}{RESET}") # Cetak di baris r+1
        if rows - r >= 1 and rows - r != r + 1: # Jangan timpa baris yang sama
            sys.stdout.write(f"\033[{rows - r};1H{color}{line}{RESET}") # Cetak di baris rows-r
        sys.stdout.flush()
        time.sleep(delay)
    # Tidak perlu menghapus wipe jika clear_screen akan dipanggil setelahnya

def draw_two_column_layout(left_lines, right_lines, total_width, left_width, padding=4):
    """
    Mencetak dua kolom bersebelahan dengan lebar adaptif.
    Memastikan total_width tidak melebihi lebar terminal aktual.
    """
    _rows, term_cols = get_terminal_size()
    # Pastikan total_width tidak melebihi lebar terminal yang tersedia
    total_width = min(total_width, term_cols)
    # Pastikan left_width tidak terlalu besar
    left_width = min(left_width, total_width - padding - 1) # Sisakan minimal 1 untuk kanan
    right_width = max(1, total_width - left_width - padding) # Minimal lebar 1

    max_lines = max(len(left_lines), len(right_lines))
    spacer = " " * padding

    # Fungsi helper untuk menghitung panjang visible string (tanpa ANSI)
    def visible_len(s):
        return len(re.sub(r'\033\[[0-9;]*m', '', s))

    # Impor re hanya jika dibutuhkan (lazy import)
    import re

    for i in range(max_lines):
        left_part = left_lines[i].rstrip() if i < len(left_lines) else ""
        right_part = right_lines[i].rstrip() if i < len(right_lines) else ""

        # Hitung panjang visible kiri untuk padding yang benar
        left_visible_len = visible_len(left_part)
        # Tambahkan padding spasi agar mencapai left_width
        left_padding = " " * max(0, left_width - left_visible_len)
        left_padded = f"{left_part}{left_padding}"

        # Ambil bagian kanan sesuai right_width (ASCII art biasanya tidak perlu wrap)
        right_padded = right_part[:right_width] # Potong jika terlalu panjang

        # Gabungkan dan cetak, pastikan tidak melebihi total_width
        line = f"{left_padded}{spacer}{right_padded}"
        print(line[:total_width]) # Potong jika gabungan melebihi total_width


def startup_animation():
    """Animasi sederhana saat program dimulai, adaptif."""
    clear_screen()
    rows, cols = get_terminal_size()
    brand = "🚀 Exora AI Listener 🚀"
    stages = ["[■□□□□□]", "[■■□□□□]", "[■■■□□□]", "[■■■■□□]", "[■■■■■□]", "[■■■■■■]"]
    messages = [
        "Menginisialisasi sistem...",
        "Memuat modul...",
        "Mengecek dependensi...",
        "Menghubungkan ke Matrix...", # Haha, just for fun
        "Kalibrasi sensor...",
        "Siap meluncur!"
    ]

    print("\n" * max(1, rows // 3)) # Posisi agak ke bawah, minimal 1 baris
    print_centered(brand, cols, BOLD + MAGENTA)
    print("\n")

    for i, stage in enumerate(stages):
        progress = f"{BLUE}{stage}{RESET} {messages[i]}"
        # Center progress message, leave padding for overwrite
        print_centered(progress + " " * 20, cols) # Extra padding to clear previous line
        time.sleep(random.uniform(0.2, 0.5))
        # Pindah cursor ke atas 1 baris untuk menimpa message sebelumnya
        if i < len(stages) - 1:
             sys.stdout.write("\033[F") # Pindah cursor ke atas
             sys.stdout.flush()

    print_centered(f"{GREEN}{BOLD}✅ Sistem Siap!{RESET}", cols)
    time.sleep(1)
    wipe_effect(rows, cols) # Efek wipe sebelum ke menu

# --- Fungsi Penanganan Sinyal (Ctrl+C) ---
# (Tetap sama - Tidak diubah)
def signal_handler(sig, frame):
    global running
    print(f"\n{BRIGHT_YELLOW}{BOLD}🛑 Ctrl+C terdeteksi! Menghentikan semua proses...{RESET}")
    running = False
    # Beri sedikit waktu untuk loop utama berhenti secara alami
    time.sleep(0.5)
    # Mungkin perlu cleanup tambahan di sini jika ada proses background
    print(f"\n{RED}{BOLD}👋 Sampai jumpa!{RESET}")
    # Pastikan layar bersih sebelum keluar jika diinginkan
    # clear_screen()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# --- Fungsi Konfigurasi ---
# (Fungsi load_settings & save_settings tetap sama - Tidak ada perubahan logika inti)
def load_settings():
    """Memuat pengaturan dari file JSON."""
    settings = DEFAULT_SETTINGS.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_settings = json.load(f)
                # Hanya update kunci yang ada di default
                for key in DEFAULT_SETTINGS:
                    if key in loaded_settings:
                        # Lakukan validasi tipe dasar saat memuat
                        default_type = type(DEFAULT_SETTINGS[key])
                        try:
                            if default_type == bool:
                                settings[key] = bool(loaded_settings[key])
                            elif default_type == int:
                                settings[key] = int(loaded_settings[key])
                            elif default_type == float:
                                settings[key] = float(loaded_settings[key])
                            else: # String atau tipe lain yang tidak perlu konversi ketat
                                settings[key] = loaded_settings[key]
                        except (ValueError, TypeError):
                            print(f"{YELLOW}[WARN] Nilai '{loaded_settings[key]}' untuk '{key}' tidak valid, gunakan default: '{DEFAULT_SETTINGS[key]}'.{RESET}")
                            settings[key] = DEFAULT_SETTINGS[key] # Fallback ke default jika tipe salah

                # Validasi spesifik setelah memuat
                settings["check_interval_seconds"] = max(5, settings.get("check_interval_seconds", 10))
                settings["buy_quote_quantity"] = max(0.0, settings.get("buy_quote_quantity", 11.0))
                settings["sell_base_quantity"] = max(0.0, settings.get("sell_base_quantity", 0.0))

                # Save back corrections silently to ensure config file consistency
                save_settings(settings, silent=True)

        except json.JSONDecodeError:
            print(f"{RED}[ERROR] File konfigurasi '{CONFIG_FILE}' rusak. Menggunakan default & menyimpan ulang.{RESET}")
            save_settings(settings) # Simpan default
        except Exception as e:
            print(f"{RED}[ERROR] Gagal memuat konfigurasi: {e}{RESET}")
            print(f"{YELLOW}[WARN] Menggunakan pengaturan default sementara.{RESET}")
    else:
        # print(f"{YELLOW}[INFO] File '{CONFIG_FILE}' tidak ditemukan. Membuat dengan nilai default.{RESET}") # Pesan ini bisa muncul saat pertama kali run
        save_settings(settings) # Buat file config baru dengan default
    if not BINANCE_AVAILABLE:
        # Pesan warning jika Binance tidak tersedia, setelah memuat setting
         if settings.get('execute_binance_orders'):
              print(f"{status_warn} {YELLOW}Eksekusi Binance aktif, tapi library 'python-binance' tidak ditemukan!{RESET}")
              print(f"{DIM}   -> Fitur Binance tidak akan berjalan. Install dengan 'pip install python-binance'.{RESET}")
    return settings

def save_settings(settings, silent=False):
    """Menyimpan pengaturan ke file JSON."""
    try:
        settings_to_save = {}
        # Pastikan hanya key dari DEFAULT_SETTINGS yang disimpan
        # dan validasi tipe sebelum menyimpan
        for key, default_value in DEFAULT_SETTINGS.items():
            value = settings.get(key, default_value) # Ambil nilai dari settings atau default
            default_type = type(default_value)
            try:
                if default_type == bool:
                    settings_to_save[key] = bool(value)
                elif default_type == int:
                    settings_to_save[key] = int(value)
                elif default_type == float:
                    settings_to_save[key] = float(value)
                else: # String atau lainnya
                    settings_to_save[key] = str(value) if isinstance(value, (int, float, bool)) else value
            except (ValueError, TypeError):
                 if not silent:
                     print(f"{YELLOW}[WARN] Gagal konversi nilai untuk '{key}' saat menyimpan. Menggunakan default: '{default_value}'.{RESET}")
                 settings_to_save[key] = default_value

        # Pastikan nilai numerik valid
        settings_to_save['check_interval_seconds'] = max(5, settings_to_save.get('check_interval_seconds', 10))
        settings_to_save['buy_quote_quantity'] = max(0.0, settings_to_save.get('buy_quote_quantity', 11.0))
        settings_to_save['sell_base_quantity'] = max(0.0, settings_to_save.get('sell_base_quantity', 0.0))

        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings_to_save, f, indent=4, sort_keys=True)
        if not silent:
            # Dapatkan ukuran terminal untuk separator
            _, cols = get_terminal_size()
            print(f"{GREEN}{BOLD}💾 Pengaturan berhasil disimpan ke '{CONFIG_FILE}'{RESET}")
            print_separator(length=min(cols-4, 60), color=GREEN) # Separator pendek
    except Exception as e:
        print(f"{RED}[ERROR] Gagal menyimpan konfigurasi: {e}{RESET}")


# --- Fungsi Utilitas Lain ---
# (Fungsi get_timestamp, decode_mime_words, get_text_from_email, trigger_beep tetap sama - Tidak ada perubahan logika inti)
# (Tambahkan sedikit visual feedback di dalamnya)
def get_timestamp():
    """Mendapatkan timestamp format YYYY-MM-DD HH:MM:SS."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def decode_mime_words(s):
    """Decode header email (Subject, From, To). Crucial, keep as is."""
    if not s: return ""
    try:
        decoded_parts = decode_header(s)
        result = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                try:
                    result.append(part.decode(encoding or 'utf-8', errors='replace'))
                except (LookupError, ValueError, TypeError): # Tangkap lebih banyak error potensial
                    result.append(part.decode('utf-8', errors='replace')) # Fallback UTF-8
            elif isinstance(part, str):
                 result.append(part)
            else:
                 # Handle unexpected types if necessary, e.g., convert to string
                 result.append(str(part))
        return "".join(result)
    except Exception as e:
        print(f"{YELLOW}[WARN] Error saat decode header: {e}. Header asli: {s}{RESET}")
        return s # Kembalikan string asli jika decode gagal total

def get_text_from_email(msg):
    """Ekstrak konten teks dari objek email. Crucial, keep as is."""
    text_content = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            # Hanya ambil text/plain yang bukan attachment
            if content_type == "text/plain" and "attachment" not in content_disposition.lower():
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    # Ganti None payload dengan byte kosong
                    if payload is None: payload = b''
                    text_content += payload.decode(charset, errors='replace') + "\n"
                except (LookupError, ValueError, TypeError, AttributeError) as e:
                    print(f"{YELLOW}[WARN] Tidak bisa decode part email (text/plain): {e}{RESET}")
                    # Coba decode dengan fallback jika error
                    try:
                        text_content += payload.decode('utf-8', errors='replace') + "\n"
                    except: pass # Abaikan jika fallback juga gagal
    else:
        # Handle non-multipart emails
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                if payload is None: payload = b''
                text_content = payload.decode(charset, errors='replace')
            except (LookupError, ValueError, TypeError, AttributeError) as e:
                 print(f"{YELLOW}[WARN] Tidak bisa decode body email (non-multipart): {e}{RESET}")
                 try:
                    text_content = payload.decode('utf-8', errors='replace')
                 except: pass # Abaikan jika fallback gagal
    return text_content.lower() # Kembalikan dalam lowercase

def trigger_beep(action):
    """Memainkan suara beep berdasarkan aksi (buy/sell)."""
    # Dapatkan ukuran terminal untuk pesan yang rapi
    _rows, cols = get_terminal_size()
    try:
        action_upper = action.upper()
        action_color = GREEN if action == "buy" else RED if action == "sell" else MAGENTA
        # Cetak pesan BEEP dengan padding agar jelas
        print(f"\n{action_color}{BOLD}🔊 BEEP {action_upper}! 🔊{' ' * (cols // 2)}{RESET}\n")
        # Coba 'tput bel' sebagai alternatif cross-platform sederhana jika 'beep' tidak ada
        try:
            cmd = None
            if action == "buy":
                # Contoh command 'beep' (Linux), sesuaikan jika perlu
                cmd = ["beep", "-f", "1000", "-l", "500", "-D", "100", "-r", "3"]
            elif action == "sell":
                cmd = ["beep", "-f", "700", "-l", "700", "-D", "100", "-r", "2"]

            if cmd:
                # Jalankan di background agar tidak blocking, timeout pendek
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                # Jangan tunggu (check=True akan menunggu)
                # subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=2)
            else:
                 print("\a", end='') # Bell standar untuk aksi lain atau jika cmd tidak diset
                 sys.stdout.flush()

        except FileNotFoundError:
            # Jika command 'beep' tidak ditemukan
            # print(f"{DIM}   (Command 'beep' tidak ditemukan, pakai bell standar){RESET}")
            print("\a", end='') # Fallback ke system bell standar
            sys.stdout.flush() # Pastikan bell bunyi
        except Exception as beep_err:
             # Tangkap error lain dari subprocess
             print(f"{YELLOW}[WARN] Error saat menjalankan command beep: {beep_err}{RESET}")
             print("\a", end='') # Fallback bell
             sys.stdout.flush()

    except Exception as e:
        print(f"{RED}[ERROR] Kesalahan tak terduga saat beep: {e}{RESET}")


# --- Fungsi Eksekusi Binance ---
# (Fungsi get_binance_client & execute_binance_order tetap sama - Tidak ada perubahan logika inti)
# (Tambahkan visualisasi koneksi/eksekusi yang lebih jelas)
def get_binance_client(settings):
    """Membuat dan memverifikasi koneksi Binance Client."""
    _rows, cols = get_terminal_size() # Untuk formatting pesan
    connecting_msg = f"{status_wait} {CYAN}Menghubungkan ke Binance API...{RESET}"
    print(connecting_msg.ljust(cols - 4), end='\r') # Overwriteable message

    if not BINANCE_AVAILABLE:
        print(f"{status_nok} {RED}{BOLD}Library 'python-binance' tidak ada!{RESET}".ljust(cols - 4))
        return None
    if not settings.get('binance_api_key') or not settings.get('binance_api_secret'):
        print(f"{status_nok} {RED}{BOLD}API Key/Secret Binance kosong di pengaturan!{RESET}".ljust(cols - 4))
        return None

    try:
        client = Client(settings['binance_api_key'], settings['binance_api_secret'])
        # Test koneksi dengan ping atau get_account
        client.ping() # Ping lebih ringan
        # Optional: Dapatkan info akun untuk konfirmasi
        # acc_info = client.get_account()
        print(f"{status_ok} {GREEN}{BOLD}Koneksi Binance API Berhasil!                {RESET}".ljust(cols - 4))
        # Optional: Tampilkan info akun singkat
        # print(f"{DIM}   -> Akun Terhubung (cek saldo jika perlu){RESET}")
        return client
    except (BinanceAPIException, BinanceOrderException) as e:
        error_msg = f"{status_nok} {RED}{BOLD}Koneksi/Auth Binance Gagal:{RESET} {e.status_code} - {e.message}"
        print(error_msg.ljust(cols - 4))
        if "Invalid API-key" in str(e.message):
             print(f"{RED}   -> Periksa API Key/Secret & IP Whitelist (jika ada).{RESET}")
        return None
    except requests.exceptions.RequestException as req_err: # Tangkap error koneksi jaringan
        error_msg = f"{status_nok} {RED}{BOLD}Gagal Menghubungi Binance:{RESET} {req_err}"
        print(error_msg.ljust(cols - 4))
        print(f"{YELLOW}   -> Periksa koneksi internet Anda.{RESET}")
        return None
    except Exception as e:
        error_msg = f"{status_nok} {RED}{BOLD}Gagal membuat Binance client:{RESET} {type(e).__name__} - {e}"
        print(error_msg.ljust(cols - 4))
        # traceback.print_exc() # Uncomment for detailed debugging
        return None


def execute_binance_order(client, settings, side):
    """Mengeksekusi order MARKET BUY/SELL di Binance."""
    _rows, cols = get_terminal_size() # Untuk formatting
    if not client:
        print(f"{status_warn} {YELLOW}Eksekusi dibatalkan, client Binance tidak valid.{RESET}")
        return False
    if not settings.get("execute_binance_orders", False):
        # Pesan ini seharusnya tidak muncul jika logika pemanggilan sudah benar
        # print(f"{status_warn} {YELLOW}Eksekusi order dinonaktifkan (seharusnya tidak sampai sini).{RESET}")
        return False # Seharusnya tidak dipanggil jika execute_binance_orders False

    pair = settings.get('trading_pair', '').upper()
    if not pair:
        print(f"{status_nok} {RED}{BOLD}Trading pair belum diatur di pengaturan!{RESET}")
        return False

    order_details = {}
    action_desc = ""
    side_color = BRIGHT_GREEN if side == Client.SIDE_BUY else BRIGHT_RED
    side_icon = "🛒" if side == Client.SIDE_BUY else "💰"
    border_char = "═" # Karakter border

    try:
        # Header Aksi
        header = f"{side_color}{BOLD}{border_char*3} PERSIAPAN ORDER {side} ({pair}) {border_char*3}{RESET}"
        print(f"\n{header}")

        if side == Client.SIDE_BUY:
            quote_qty = settings.get('buy_quote_quantity', 0.0)
            if quote_qty <= 0:
                 print(f"{status_nok} {RED}Kuantitas Beli (buy_quote_quantity) harus > 0.{RESET}")
                 print(f"{side_color}{border_char * len(header)}{RESET}") # Footer
                 return False
            order_details = {'symbol': pair, 'side': Client.SIDE_BUY, 'type': Client.ORDER_TYPE_MARKET, 'quoteOrderQty': quote_qty}
            # Coba tebak quote asset (umumnya di akhir pair)
            quote_asset = "Quote"
            if pair.endswith("USDT"): quote_asset = "USDT"
            elif pair.endswith("BUSD"): quote_asset = "BUSD"
            elif pair.endswith("BTC"): quote_asset = "BTC"
            elif pair.endswith("ETH"): quote_asset = "ETH"
            elif pair.endswith("TRY"): quote_asset = "TRY"
            elif pair.endswith("EUR"): quote_asset = "EUR"
            # etc.
            action_desc = f"{side_icon} {BOLD}MARKET BUY{RESET} {quote_qty:.8f} {quote_asset} worth of {pair}" # Tampilkan presisi

        elif side == Client.SIDE_SELL:
            base_qty = settings.get('sell_base_quantity', 0.0)
            if base_qty <= 0:
                 # Hanya warn jika 0, error jika negatif (meskipun load_settings harusnya mencegah negatif)
                 if base_qty == 0: print(f"{status_warn} {YELLOW}Kuantitas Jual (sell_base_quantity) adalah 0. Tidak ada order SELL.{RESET}")
                 else: print(f"{status_nok} {RED}Kuantitas Jual (sell_base_quantity) harus >= 0.{RESET}")
                 print(f"{side_color}{border_char * len(header)}{RESET}") # Footer
                 return False
            order_details = {'symbol': pair, 'side': Client.SIDE_SELL, 'type': Client.ORDER_TYPE_MARKET, 'quantity': base_qty}
            # Coba tebak base asset
            base_asset = "Base"
            known_quotes = ["USDT", "BUSD", "BTC", "ETH", "TRY", "EUR"]
            for quote in known_quotes:
                if pair.endswith(quote):
                    base_asset = pair[:-len(quote)]
                    break
            action_desc = f"{side_icon} {BOLD}MARKET SELL{RESET} {base_qty:.8f} {base_asset} from {pair}" # Tampilkan presisi
        else:
            print(f"{status_nok} {RED}Sisi order tidak valid: {side}{RESET}")
            print(f"{side_color}{border_char * len(header)}{RESET}") # Footer
            return False

        # Konfirmasi sebelum eksekusi (jika perlu)
        # confirm = input(f"Eksekusi: {action_desc}? (y/n): ").lower()
        # if confirm != 'y':
        #     print(f"{YELLOW}Eksekusi dibatalkan oleh user.{RESET}")
        #     return False

        executing_msg = f"{CYAN}{status_wait} Mencoba eksekusi: {action_desc}...{RESET}"
        print(executing_msg.ljust(cols - 4), end='\r')

        # ---- INI BAGIAN PENTING EKSEKUSI ----
        # Gunakan test order jika ingin simulasi tanpa eksekusi nyata
        # order_result = client.create_test_order(**order_details)
        # print(f"{YELLOW}{BOLD}--- TEST ORDER MODE ---{RESET}")
        order_result = client.create_order(**order_details)
        # ------------------------------------

        # Hapus pesan "Mencoba eksekusi..."
        print(" " * (cols - 4), end='\r')

        # --- Tampilkan Hasil Order ---
        print(f"{side_color}{BOLD}✅ ORDER BERHASIL DI EKSEKUSI!{RESET}")
        print(f"{DIM}{'-'*40}{RESET}") # Separator internal
        print(f"{DIM}  Order ID : {order_result.get('orderId')}{RESET}")
        print(f"{DIM}  Symbol   : {order_result.get('symbol')}{RESET}")
        print(f"{DIM}  Side     : {order_result.get('side')}{RESET}")
        print(f"{DIM}  Status   : {order_result.get('status')}{RESET}")

        # Hitung detail dari 'fills' jika ada (untuk market order biasanya ada)
        if order_result.get('fills') and len(order_result['fills']) > 0:
            total_qty = sum(float(f['qty']) for f in order_result['fills'])
            total_quote_qty = sum(float(f['quoteQty']) for f in order_result['fills']) # Pakai quoteQty per fill
            avg_price = total_quote_qty / total_qty if total_qty else 0
            commission_total = sum(float(f['commission']) for f in order_result['fills'])
            commission_asset = order_result['fills'][0]['commissionAsset'] if order_result['fills'] else 'N/A'

            print(f"{DIM}  Avg Price: {avg_price:.8f}{RESET}")
            print(f"{DIM}  Filled Qty: {total_qty:.8f} (Base){RESET}")
            print(f"{DIM}  Total Val: {total_quote_qty:.4f} (Quote){RESET}")
            print(f"{DIM}  Commission: {commission_total:.8f} {commission_asset}{RESET}")
        else:
            # Jika tidak ada 'fills', coba tampilkan dari data utama (mungkin kurang akurat untuk market)
            print(f"{DIM}  Price    : {order_result.get('price', 'N/A')}{RESET}") # Biasanya 0 untuk market order
            print(f"{DIM}  Orig Qty : {order_result.get('origQty', 'N/A')}{RESET}")
            print(f"{DIM}  Exec Qty : {order_result.get('executedQty', 'N/A')}{RESET}")
            print(f"{DIM}  Quote Qty: {order_result.get('cummulativeQuoteQty', 'N/A')}{RESET}")

        print(f"{DIM}{'-'*40}{RESET}")
        return True

    except (BinanceAPIException, BinanceOrderException) as e:
        print(" " * (cols - 4), end='\r') # Hapus pesan "Mencoba eksekusi..."
        print(f"{status_nok} {RED}{BOLD}BINANCE API/ORDER ERROR:{RESET} Status {e.status_code}, Code {e.code}, Msg: {e.message}")
        # Pesan bantuan spesifik
        if e.code == -2010 or "insufficient balance" in str(e.message).lower():
             print(f"{RED}      -> SALDO TIDAK CUKUP? Periksa saldo {quote_asset if side == Client.SIDE_BUY else base_asset}.{RESET}")
        elif e.code == -1121: print(f"{RED}      -> Trading pair '{pair}' TIDAK VALID?{RESET}")
        elif e.code == -1013 or 'MIN_NOTIONAL' in str(e.message): print(f"{RED}      -> Order size TERLALU KECIL? Cek filter MIN_NOTIONAL untuk {pair}.{RESET}")
        elif e.code == -1111 or 'LOT_SIZE' in str(e.message): print(f"{RED}      -> Kuantitas tidak sesuai step size (LOT_SIZE)? Cek filter LOT_SIZE.{RESET}")
        elif e.code == -1021 or 'timestamp' in str(e.message).lower(): print(f"{RED}      -> Timestamp error? Sinkronkan jam sistem Anda.{RESET}")
        return False
    except requests.exceptions.RequestException as req_err: # Tangkap error koneksi jaringan saat order
        print(" " * (cols - 4), end='\r')
        print(f"{status_nok} {RED}{BOLD}Koneksi Error Saat Order:{RESET} {req_err}")
        print(f"{YELLOW}   -> Periksa internet. Order mungkin gagal atau tidak terkirim.{RESET}")
        return False
    except Exception as e:
        print(" " * (cols - 4), end='\r') # Hapus pesan "Mencoba eksekusi..."
        print(f"{status_nok} {RED}{BOLD}ERROR EKSEKUSI BINANCE (Non-API):{RESET}")
        traceback.print_exc() # Cetak detail error non-Binance
        return False
    finally:
        # Footer Aksi, pastikan header ada sebelum mencoba ambil panjangnya
        try: header_len = len(re.sub(r'\033\[[0-9;]*m', '', header)) # Panjang tanpa ANSI
        except NameError: header_len = 40 # Fallback length
        import re # Impor lagi jika belum
        print(f"{side_color}{border_char * header_len}{RESET}\n")


# --- Fungsi Pemrosesan Email ---
# (Fungsi process_email tetap sama - Tidak ada perubahan logika inti)
# (Pastikan output konsisten dan jelas)
def process_email(mail, email_id, settings, binance_client):
    """Memproses satu email: cek keyword, trigger aksi jika cocok."""
    global running
    if not running: return # Hentikan jika sinyal stop diterima

    target_keyword_lower = settings['target_keyword'].lower()
    trigger_keyword_lower = settings['trigger_keyword'].lower()
    email_id_str = email_id.decode('utf-8')
    ts = get_timestamp()
    _rows, cols = get_terminal_size() # Untuk formatting

    # --- Header Proses Email ---
    header = f"{MAGENTA}📧 {BOLD}Memproses Email ID: {email_id_str} [{ts}]{RESET}{MAGENTA} {'=' * max(5, cols - 60)}{RESET}"
    print(f"\n{header}")
    fetching_msg = f"{DIM}   Mengambil data email...{RESET}"
    print(fetching_msg.ljust(cols - 4), end='\r')

    try:
        # Fetch email content
        status, data = mail.fetch(email_id, "(RFC822)")
        if status != 'OK':
            print(f"{status_nok} {RED}Gagal fetch email ID {email_id_str}: {status}{RESET}".ljust(cols - 4))
            print(f"{MAGENTA}{'=' * len(header)}{RESET}") # Footer
            return
        print(f"{GREEN}   Data email diterima.                 {RESET}".ljust(cols - 4)) # Clear prev line

        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)

        # Decode sender and subject
        subject = decode_mime_words(msg["Subject"])
        sender = decode_mime_words(msg["From"])
        # Batasi panjang tampilan jika terlalu panjang
        max_subj_len = max(20, cols - 20)
        subject_display = (subject[:max_subj_len] + '...') if len(subject) > max_subj_len else subject
        sender_display = sender # Biasanya tidak terlalu panjang

        print(f"   {CYAN}Dari  :{RESET} {sender_display}")
        print(f"   {CYAN}Subjek:{RESET} {subject_display}")
        print(f"{MAGENTA}{'-' * 40}{RESET}") # Separator internal

        # Get email body text
        body = get_text_from_email(msg)
        # Gabungkan subjek dan body untuk pencarian keyword
        full_content = (subject.lower() + " " + body)

        # --- Keyword Matching ---
        if target_keyword_lower in full_content:
            print(f"{GREEN}🎯 {BOLD}Keyword Target Ditemukan!{RESET} ('{settings['target_keyword']}')")
            try:
                # Cari trigger SETELAH target
                target_index = full_content.find(target_keyword_lower)
                # Cari trigger setelah target + panjang target
                trigger_index = full_content.find(trigger_keyword_lower, target_index + len(target_keyword_lower))

                if trigger_index != -1:
                    # Ambil kata setelah trigger
                    start_word_index = trigger_index + len(trigger_keyword_lower)
                    text_after_trigger = full_content[start_word_index:].lstrip() # Hapus spasi awal
                    words_after_trigger = text_after_trigger.split(maxsplit=1) # Ambil kata pertama

                    if words_after_trigger:
                        action_word = words_after_trigger[0].strip('.,!?:;()[]{}').lower() # Bersihkan & lowercase
                        action_color = BRIGHT_GREEN if action_word == "buy" else BRIGHT_RED if action_word == "sell" else BRIGHT_YELLOW

                        print(f"{action_color}📌 {BOLD}Keyword Trigger Ditemukan!{RESET} ('{settings['trigger_keyword']}') -> Aksi: {BOLD}{action_word.upper()}{RESET}")

                        # --- Trigger Aksi (Beep & Binance) ---
                        if action_word in ["buy", "sell"]:
                            # 1. Trigger Beep
                            trigger_beep(action_word)

                            # 2. Cek apakah eksekusi Binance aktif
                            if settings.get("execute_binance_orders"):
                                if binance_client:
                                    # Eksekusi order Binance
                                    execute_binance_order(binance_client, settings, getattr(Client, f"SIDE_{action_word.upper()}"))
                                else:
                                    print(f"{status_warn} {YELLOW}Eksekusi Binance aktif tapi client tidak siap/gagal konek.{RESET}")
                            elif action_word in ["buy", "sell"]:
                                 # Jika eksekusi nonaktif tapi aksi valid
                                 print(f"{DIM}   (Eksekusi order Binance dinonaktifkan di pengaturan){RESET}")
                        else:
                            # Jika kata setelah trigger bukan 'buy' atau 'sell'
                            print(f"{status_warn} {YELLOW}Aksi '{action_word}' tidak dikenal (bukan 'buy'/'sell'). Tidak ada aksi market.{RESET}")
                    else:
                        # Jika ada trigger tapi tidak ada kata setelahnya
                        print(f"{status_warn} {YELLOW}Tidak ada kata setelah keyword trigger '{settings['trigger_keyword']}'.{RESET}")
                else:
                     # Jika target ada tapi trigger tidak ada SETELAHNYA
                     print(f"{status_warn} {YELLOW}Keyword trigger '{settings['trigger_keyword']}' tidak ditemukan SETELAH target '{settings['target_keyword']}'.{RESET}")

            except Exception as e:
                 print(f"{status_nok} {RED}Error saat parsing setelah trigger: {e}{RESET}")
                 # traceback.print_exc() # Debugging
        else:
            # Jika keyword target tidak ditemukan sama sekali
            print(f"{BLUE}💨 Keyword target '{settings['target_keyword']}' tidak ditemukan.{RESET}")

        # --- Tandai Email sebagai 'Seen' ---
        # Lakukan ini di akhir, terlepas dari hasil keyword matching
        try:
            # print(f"{DIM}   Menandai email {email_id_str} sebagai 'Seen'...{RESET}")
            mail.store(email_id, '+FLAGS', '\\Seen')
        except Exception as e:
            # Error ini biasanya tidak kritis, hanya warning
            print(f"{status_warn} {YELLOW}Gagal menandai email {email_id_str} sebagai 'Seen': {e}{RESET}")

    except Exception as e:
        # Tangkap error besar saat proses email
        print(f"{status_nok} {RED}{BOLD}Gagal total memproses email ID {email_id_str}:{RESET}")
        traceback.print_exc() # Tampilkan error detail
    finally:
        # --- Footer Proses Email ---
        import re
        try: header_len = len(re.sub(r'\033\[[0-9;]*m', '', header)) # Panjang tanpa ANSI
        except NameError: header_len = cols - 4 # Fallback
        print(f"{MAGENTA}{'=' * header_len}{RESET}")


# --- Fungsi Listening Utama ---
def start_listening(settings):
    """Loop utama untuk memeriksa email dan memprosesnya."""
    global running, spinner_chars
    running = True # Pastikan status running benar di awal
    mail = None
    binance_client = None
    connection_attempts = 0
    spinner_index = 0
    # Dapatkan ukuran terminal sekali di awal, bisa diupdate jika berubah drastis
    rows, cols = get_terminal_size()
    # Jeda antar retry koneksi (detik)
    retry_wait_time = min(30, max(10, settings.get('check_interval_seconds', 10) * 2)) # Misal 2x interval, min 10s max 30s

    clear_screen()
    print("\n" * 2) # Sedikit margin atas
    print_separator(char="*", length=cols-4, color=MAGENTA)
    mode = f"{BOLD}Email"
    if settings.get("execute_binance_orders"):
        mode += f" & Binance Order{RESET}{MAGENTA}" if BINANCE_AVAILABLE else f" {RESET}({RED}Binance Lib Error!{RESET}{MAGENTA})"
    else:
        mode += f" Listener Only{RESET}{MAGENTA}"
    print_centered(f"🚀 MODE AKTIF: {mode} 🚀", cols-4, MAGENTA)
    print_separator(char="*", length=cols-4, color=MAGENTA)
    print("\n")

    # --- Setup Binance (jika diaktifkan) ---
    if settings.get("execute_binance_orders"):
        if not BINANCE_AVAILABLE:
             # Fatal jika eksekusi aktif tapi library tidak ada
             print(f"{status_nok} {RED}{BOLD}FATAL: Library 'python-binance' tidak ada! Tidak bisa eksekusi order.{RESET}")
             print(f"{YELLOW}   -> Nonaktifkan 'Eksekusi Order' di Pengaturan atau install library ('pip install python-binance').{RESET}")
             running = False # Set running ke False agar loop utama tidak jalan
             input(f"\n{DIM}Tekan Enter untuk kembali ke menu...{RESET}")
             return # Keluar dari fungsi listening
        # Jika library ada, coba konek
        print(f"{CYAN}🔗 {BOLD}[SETUP] Menginisialisasi Koneksi Binance...{RESET}")
        binance_client = get_binance_client(settings)
        if not binance_client:
            print(f"{status_warn} {YELLOW}{BOLD}PERINGATAN: Gagal konek Binance saat startup.{RESET}")
            # Opsi:
            # 1. Stop total -> print(...) ; running = False; return
            # 2. Lanjut tanpa eksekusi (beri warning)
            print(f"{YELLOW}   -> Listener akan jalan, tapi order Binance TIDAK AKAN dieksekusi.{RESET}")
            print(f"{YELLOW}   -> Periksa API Key/Secret, koneksi, atau nonaktifkan eksekusi di Pengaturan.{RESET}")
            # Tidak set binance_client=None, biarkan proses email mencoba lagi nanti jika perlu
            # Atau paksa nonaktifkan hanya untuk sesi ini:
            # settings['execute_binance_orders'] = False
            # print(f"{DIM}   Eksekusi Binance dinonaktifkan sementara untuk sesi ini.{RESET}")
            time.sleep(3) # Jeda agar user baca
        else:
            print(f"{status_ok} {GREEN}{BOLD}[SETUP] Binance Client Siap!{RESET}")
    else:
        print(f"{YELLOW}ℹ️ {BOLD}[INFO] Eksekusi order Binance dinonaktifkan (sesuai pengaturan).{RESET}")

    # Cek jika `running` diubah jadi False oleh setup Binance
    if not running:
        return

    print_separator(length=cols-4, color=CYAN)
    print(f"{CYAN}📧 {BOLD}[SETUP] Menyiapkan Listener Email...{RESET}")
    email_disp = settings.get('email_address', '[Belum diatur]')
    imap_disp = settings.get('imap_server', '[Belum diatur]')
    print(f"{DIM}   Akun  : {email_disp}{RESET}")
    print(f"{DIM}   Server: {imap_disp}{RESET}")
    print_separator(length=cols-4, color=CYAN)
    time.sleep(1)
    print(f"\n{BOLD}{WHITE}Memulai pemantauan email... (Ctrl+C untuk berhenti){RESET}")
    print("-" * (cols - 4))

    # --- Loop Utama Listener ---
    last_noop_time = time.time()
    noop_interval = 5 * 60 # Kirim NOOP setiap 5 menit untuk jaga koneksi

    while running:
        try:
            # --- Koneksi IMAP ---
            if not mail or mail.state != 'SELECTED':
                connection_attempts += 1
                # Jika sudah gagal beberapa kali, tunggu lebih lama
                current_wait = retry_wait_time * min(connection_attempts, 5) # Max 5x wait time
                connecting_msg = f"{status_wait} {CYAN}[{connection_attempts}] Menghubungkan ke IMAP ({settings['imap_server']})... (Retry dalam {current_wait}s jika gagal){RESET}"
                print(connecting_msg.ljust(cols - 4), end='\r')

                try:
                    # Coba buat koneksi baru
                    mail = imaplib.IMAP4_SSL(settings['imap_server'])
                    conn_ok_msg = f"{status_ok} {GREEN}Terhubung ke IMAP Server.               {RESET}"
                    print(conn_ok_msg.ljust(cols - 4)) # Timpa pesan connecting

                    login_msg = f"{status_wait} {CYAN}Login sebagai {settings['email_address']}...{RESET}"
                    print(login_msg.ljust(cols - 4), end='\r')
                    mail.login(settings['email_address'], settings['app_password'])
                    login_ok_msg = f"{status_ok} {GREEN}Login Email Berhasil! ({settings['email_address']}){RESET}"
                    print(login_ok_msg.ljust(cols - 4)) # Timpa pesan login

                    mail.select("inbox")
                    inbox_ok_msg = f"{status_ok} {GREEN}Masuk ke INBOX. Siap mendengarkan...{RESET}"
                    print(inbox_ok_msg.ljust(cols - 4))
                    print("-" * (cols-4)) # Separator setelah sukses konek
                    connection_attempts = 0 # Reset counter setelah sukses
                    last_noop_time = time.time() # Reset timer NOOP

                except (imaplib.IMAP4.error, imaplib.IMAP4.abort, socket.gaierror, socket.error, OSError) as imap_err:
                    print(" " * (cols-4), end='\r') # Hapus pesan connecting/login
                    print(f"{status_nok} {RED}{BOLD}Gagal koneksi/login IMAP:{RESET} {imap_err} ")
                    # Cek error spesifik
                    err_str = str(imap_err).lower()
                    if "authentication failed" in err_str or \
                       "invalid credentials" in err_str or \
                       "username and password not accepted" in err_str or \
                       "authorization failed" in err_str:
                         print(f"{RED}{BOLD}   -> PERIKSA EMAIL & APP PASSWORD!{RESET}")
                         print(f"{YELLOW}   -> Pastikan Akses IMAP di akun Google/Email sudah diaktifkan.{RESET}")
                         print(f"{YELLOW}   -> Jika pakai Gmail, pastikan pakai App Password, bukan password utama.{RESET}")
                         running = False # Stop jika otentikasi gagal
                         input(f"\n{DIM}Tekan Enter untuk kembali ke menu...{RESET}")
                         return # Keluar dari listening
                    elif "temporary system problem" in err_str or "try again later" in err_str:
                         print(f"{YELLOW}   -> Masalah sementara di server email. Mencoba lagi dalam {current_wait} detik...{RESET}")
                    elif isinstance(imap_err, (socket.gaierror, socket.error)):
                         print(f"{YELLOW}   -> Masalah jaringan atau server IMAP tidak ditemukan/responsif.{RESET}")
                         print(f"{YELLOW}   -> Periksa koneksi internet dan nama IMAP server. Mencoba lagi dalam {current_wait} detik...{RESET}")
                    else:
                         print(f"{YELLOW}   -> Mencoba lagi dalam {current_wait} detik...{RESET}")

                    # Tunggu sebelum retry
                    # Gunakan loop kecil agar bisa diinterupsi Ctrl+C
                    for _ in range(current_wait):
                        if not running: break
                        time.sleep(1)
                    if not running: break # Keluar loop utama jika Ctrl+C ditekan saat wait
                    continue # Coba lagi dari awal loop while (koneksi ulang)
                except Exception as general_err:
                     print(" " * (cols-4), end='\r') # Hapus pesan connecting/login
                     print(f"{status_nok} {RED}{BOLD}Error tak terduga saat setup IMAP:{RESET} {general_err}")
                     traceback.print_exc()
                     print(f"{YELLOW}   -> Mencoba lagi dalam {current_wait} detik...{RESET}")
                     for _ in range(current_wait):
                         if not running: break
                         time.sleep(1)
                     if not running: break
                     continue

            # --- Jika Koneksi IMAP OK ---
            # Jaga koneksi tetap hidup dengan NOOP
            now = time.time()
            if now - last_noop_time > noop_interval:
                 try:
                     status, _ = mail.noop()
                     if status == 'OK':
                         last_noop_time = now
                         # print(f"{DIM}[{get_timestamp()}] NOOP OK{RESET}", end='\r') # Debug message
                     else:
                         print(f"\n{status_warn} {YELLOW}IMAP NOOP gagal ({status}). Koneksi mungkin bermasalah. Mencoba reconnect...{RESET}")
                         mail.logout() # Coba logout sebelum reconnect
                         mail = None
                         continue # Paksa reconnect di iterasi berikutnya
                 except (imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError) as NopErr:
                      print(f"\n{status_warn} {YELLOW}Koneksi IMAP terputus saat NOOP ({type(NopErr).__name__}). Reconnecting...{RESET}")
                      try: mail.logout()
                      except: pass
                      mail = None
                      continue # Paksa reconnect

            # --- Cek Email Baru (UNSEEN) ---
            try:
                # Cari email yang belum dibaca
                status, messages = mail.search(None, '(UNSEEN)')
                if status != 'OK':
                     print(f"\n{status_nok} {RED}Gagal mencari email (UNSEEN): {status}. Reconnecting...{RESET}")
                     try: mail.logout()
                     except: pass
                     mail = None
                     continue # Paksa reconnect

                email_ids = messages[0].split() # List of email IDs in bytes

                if email_ids:
                    # Hapus pesan tunggu jika ada email baru
                    print(" " * (cols - 4), end='\r')
                    print(f"\n{BRIGHT_GREEN}{BOLD}✨ Ditemukan {len(email_ids)} email baru! Memproses... ✨{RESET}")
                    print("-" * (cols - 4))

                    # Proses setiap email baru
                    for email_id in email_ids:
                        if not running: break # Berhenti jika Ctrl+C ditekan saat memproses
                        process_email(mail, email_id, settings, binance_client)
                        # Beri jeda singkat antar pemrosesan email (opsional)
                        # time.sleep(0.5)

                    if not running: break # Keluar loop utama jika dihentikan

                    # Setelah selesai memproses batch email baru
                    print("-" * (cols - 4))
                    print(f"{GREEN}✅ Selesai memproses {len(email_ids)} email. Kembali mendengarkan...{RESET}")
                    print("-" * (cols - 4))
                    spinner_index = 0 # Reset spinner setelah ada aktivitas

                else:
                    # --- Tidak ada email baru, tampilkan status tunggu ---
                    wait_interval = settings['check_interval_seconds']
                    spinner = spinner_chars[spinner_index % len(spinner_chars)]
                    # Update pesan tunggu setiap detik
                    # Pesan dibuat dinamis di loop sleep di bawah
                    # wait_message = f"{BLUE}{BOLD}{spinner}{RESET}{BLUE} Menunggu email ({wait_interval}s)... {RESET}"
                    # print(wait_message.ljust(cols - 4), end='\r')

                    # Tidur selama interval, cek running setiap detik
                    for i in range(wait_interval):
                        if not running: break
                        # Update spinner dan timer
                        current_spinner = spinner_chars[(spinner_index + i) % len(spinner_chars)]
                        remaining_time = wait_interval - i
                        wait_message = f"{BLUE}{BOLD}{current_spinner}{RESET}{BLUE} Menunggu email baru ({remaining_time}s)... {DIM}(Interval: {wait_interval}s){RESET}"
                        # Pastikan pesan tidak melebihi lebar kolom dan hapus sisa baris
                        print(wait_message.ljust(cols - 4), end='\r')
                        time.sleep(1)

                    if not running: break # Keluar jika dihentikan saat tidur
                    spinner_index += wait_interval # Majukan spinner sejumlah detik tunggu

                    # Hapus pesan tunggu setelah selesai (opsional, karena akan ditimpa)
                    # print(" " * (cols - 4), end='\r')

            except (imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError) as search_err:
                 print(f"\n{status_warn} {YELLOW}Koneksi IMAP terputus saat mencari/menunggu email ({type(search_err).__name__}). Reconnecting...{RESET}")
                 try: mail.logout()
                 except: pass
                 mail = None
                 continue # Paksa reconnect

        # --- Exception Handling Luar (Loop Utama) ---
        except (ConnectionError, socket.error, socket.gaierror, OSError) as net_err:
             print(f"\n{status_nok} {RED}{BOLD}Kesalahan Koneksi Jaringan Umum:{RESET} {net_err}")
             print(f"{YELLOW}   -> Periksa internet. Mencoba lagi dalam {retry_wait_time} detik...{RESET}")
             if mail:
                 try: mail.logout()
                 except: pass
             mail = None
             connection_attempts += 1 # Hitung sebagai percobaan gagal
             for _ in range(retry_wait_time):
                 if not running: break
                 time.sleep(1)
        except Exception as e:
            print(f"\n{status_nok} {RED}{BOLD}ERROR TAK TERDUGA DI LOOP UTAMA LISTENER:{RESET}")
            traceback.print_exc()
            print(f"{YELLOW}   -> Mencoba recovery dalam {retry_wait_time} detik...{RESET}")
            if mail:
                 try: mail.logout()
                 except: pass
            mail = None
            connection_attempts += 1 # Hitung sebagai percobaan gagal
            for _ in range(retry_wait_time):
                 if not running: break
                 time.sleep(1)
        finally:
            # Jika loop utama selesai (karena `running = False`)
            if not running:
                if mail:
                    print(f"{DIM}Menutup koneksi IMAP...{RESET}")
                    try:
                        if mail.state == 'SELECTED': mail.close()
                        mail.logout()
                        print(f"{GREEN}Koneksi IMAP ditutup.{RESET}")
                    except Exception as logout_err:
                        print(f"{YELLOW}Error saat menutup koneksi IMAP: {logout_err}{RESET}")
                mail = None # Pastikan mail None setelah loop berhenti

    # Pesan saat listener benar-benar berhenti
    print(f"\n{BRIGHT_YELLOW}{BOLD}🛑 Listener dihentikan.{RESET}")
    print("-"*(cols-4))


# --- Fungsi Menu Pengaturan ---
def show_settings(settings):
    """Menampilkan dan memungkinkan edit pengaturan."""
    rows, cols = get_terminal_size()
    # Batasi lebar layout agar tidak terlalu lebar di layar besar, tapi responsif di layar kecil
    layout_width = min(cols - 4, 100) # Maks 100 char, min lebar terminal - margin
    # Lebar kolom kiri sekitar 45-50% dari layout_width
    left_col_width = min(max(45, layout_width // 2 - 3), layout_width - 20) # Sisakan min 20 untuk kanan
    padding = 4 # Jarak antar kolom

    while True:
        # Efek visual sebelum clear (opsional)
        # wipe_effect(rows, cols, char=random.choice(['.',':',' ']), delay=0.001)
        clear_screen()
        print("\n" * 1) # Margin atas sedikit

        # --- Konten Kolom Kiri (Pengaturan) ---
        left_content = []
        left_content.append(f"{BOLD}{BRIGHT_CYAN}⚙️=== Pengaturan Listener ===⚙️{RESET}")
        left_content.append("-" * left_col_width) # Separator sesuai lebar kolom

        # Email Settings
        left_content.append(f"{BLUE}{BOLD}--- Email Settings ---{RESET}")
        email_disp = settings.get('email_address') or f'{YELLOW}[Kosong]{RESET}'
        # Tampilkan password sebagai asterik atau [Kosong]
        pwd_len = len(settings.get('app_password', ''))
        pwd_disp = f'**{settings["app_password"][-2:]}' if pwd_len > 4 else '*' * pwd_len if pwd_len > 0 else f'{YELLOW}[Kosong]{RESET}'

        left_content.append(f" 1. {CYAN}Email{RESET}    : {email_disp}")
        left_content.append(f" 2. {CYAN}App Pass{RESET} : {pwd_disp}")
        left_content.append(f" 3. {CYAN}IMAP Srv{RESET} : {settings.get('imap_server', 'imap.gmail.com')}")
        left_content.append(f" 4. {CYAN}Interval{RESET} : {settings.get('check_interval_seconds', 10)}s {DIM}(min:5){RESET}")
        left_content.append(f" 5. {CYAN}Target KW{RESET}: {BOLD}{settings.get('target_keyword', '[Kosong]')}{RESET}")
        left_content.append(f" 6. {CYAN}Trigger KW{RESET}: {BOLD}{settings.get('trigger_keyword', '[Kosong]')}{RESET}")
        left_content.append("") # Spasi

        # Binance Settings
        left_content.append(f"{BLUE}{BOLD}--- Binance Settings ---{RESET}")
        # Status library Binance
        lib_status = f"{GREEN}✅ Terinstall{RESET}" if BINANCE_AVAILABLE else f"{RED}❌ Hilang!{RESET}"
        left_content.append(f" Library     : {lib_status}")

        # Tampilkan API key/secret sebagian
        api_key = settings.get('binance_api_key', '')
        api_sec = settings.get('binance_api_secret', '')
        api_key_disp = f'{api_key[:4]}...{api_key[-4:]}' if len(api_key) > 8 else (f"{YELLOW}[Kosong]{RESET}" if not api_key else api_key)
        api_sec_disp = f'{api_sec[:4]}...{api_sec[-4:]}' if len(api_sec) > 8 else (f"{YELLOW}[Kosong]{RESET}" if not api_sec else api_sec)

        left_content.append(f" 7. {CYAN}API Key{RESET}   : {api_key_disp}")
        left_content.append(f" 8. {CYAN}API Secret{RESET}: {api_sec_disp}")
        pair_disp = settings.get('trading_pair') or f'{YELLOW}[Kosong]{RESET}'
        left_content.append(f" 9. {CYAN}TradingPair{RESET}: {BOLD}{pair_disp.upper()}{RESET}")
        # Format float dengan presisi
        buy_qty_disp = f"{settings.get('buy_quote_quantity', 0.0):.4f}"
        sell_qty_disp = f"{settings.get('sell_base_quantity', 0.0):.8f}"
        left_content.append(f"10. {CYAN}Buy Qty{RESET}  : {buy_qty_disp} {DIM}(Quote>0){RESET}")
        left_content.append(f"11. {CYAN}Sell Qty{RESET} : {sell_qty_disp} {DIM}(Base>=0){RESET}")
        # Status eksekusi
        exec_on = settings.get('execute_binance_orders', False)
        exec_status = f"{GREEN}{BOLD}✅ AKTIF{RESET}" if exec_on else f"{RED}❌ NONAKTIF{RESET}"
        exec_color = GREEN if exec_on else RED
        left_content.append(f"12. {exec_color}Eksekusi{RESET}  : {exec_status}")
        left_content.append("-" * left_col_width) # Separator bawah

        # Opsi Menu
        left_content.append(f" {GREEN}{BOLD}S{RESET} - Simpan & Kembali")
        left_content.append(f" {YELLOW}{BOLD}E{RESET} - Edit Pengaturan")
        left_content.append(f" {RED}{BOLD}K{RESET} - Kembali (Tanpa Simpan)")
        left_content.append("-" * left_col_width)

        # --- Gambar ASCII Art Sederhana ---
        # (Ganti dengan art lain jika mau, pastikan lebarnya tidak terlalu besar)
        settings_art = [
            f"{BLUE}   .--.    {RESET}",
            f"{BLUE}  |o_o |   {RESET}",
            f"{BLUE}  |:_/ |   {RESET}{YELLOW} Settings{RESET}",
            f"{BLUE} //   \\ \\  {RESET}",
            f"{BLUE}(|     | ) {RESET}",
            f"{BLUE}/'\\_   _/`\\{RESET}",
            f"{BLUE}\\___)=(___/{RESET}"
        ]
        # Pad art dengan baris kosong agar tingginya cocok dengan konten kiri
        while len(settings_art) < len(left_content):
            settings_art.append("")
        # Potong art jika terlalu tinggi (jika konten kiri lebih sedikit)
        settings_art = settings_art[:len(left_content)]

        # --- Cetak Layout ---
        print_centered(f"{REVERSE}{WHITE}{BOLD} PENGATURAN APLIKASI {RESET}", layout_width)
        draw_two_column_layout(left_content, settings_art, total_width=layout_width, left_width=left_col_width, padding=padding)
        print_separator(char="=", length=layout_width, color=BRIGHT_CYAN)

        # --- Input Pilihan ---
        choice = input(f"{BOLD}{WHITE}Pilihan Anda (S/E/K): {RESET}").lower().strip()

        if choice == 'e':
            print(f"\n{BOLD}{MAGENTA}--- Edit Pengaturan ---{RESET} {DIM}(Kosongkan input untuk skip item){RESET}")
            # Buat salinan sementara untuk diedit
            temp_settings = settings.copy()
            edited = False

            # --- Proses Edit Interaktif ---
            try:
                # Email
                print(f"\n{CYAN}--- Email ---{RESET}")
                new_val = input(f" 1. Email [{temp_settings['email_address']}]: ").strip()
                if new_val: temp_settings['email_address'] = new_val; edited = True

                current_pass_display = '[Hidden]' if temp_settings['app_password'] else '[Kosong]'
                new_pass = getpass.getpass(f" 2. App Password Baru [{current_pass_display}] (ketik u/ ubah): ").strip()
                if new_pass: temp_settings['app_password'] = new_pass; print(f"   {GREEN}Password diperbarui (jika diketik).{RESET}"); edited = True

                new_val = input(f" 3. Server IMAP [{temp_settings['imap_server']}]: ").strip()
                if new_val: temp_settings['imap_server'] = new_val; edited = True

                while True:
                    new_val_str = input(f" 4. Interval Cek (detik) [{temp_settings['check_interval_seconds']}s], min 5: ").strip()
                    if not new_val_str: break
                    try:
                        new_interval = int(new_val_str)
                        if new_interval >= 5:
                            temp_settings['check_interval_seconds'] = new_interval; edited = True; break
                        else: print(f"   {RED}Interval minimal 5 detik.{RESET}")
                    except ValueError: print(f"   {RED}Input tidak valid, masukkan angka bulat.{RESET}")

                new_val = input(f" 5. Keyword Target [{temp_settings['target_keyword']}]: ").strip()
                if new_val: temp_settings['target_keyword'] = new_val; edited = True

                new_val = input(f" 6. Keyword Trigger [{temp_settings['trigger_keyword']}]: ").strip()
                if new_val: temp_settings['trigger_keyword'] = new_val; edited = True

                # Binance
                print(f"\n{CYAN}--- Binance ---{RESET}")
                if not BINANCE_AVAILABLE: print(f"{YELLOW}   (Peringatan: Library Binance tidak terinstall){RESET}")

                # Format display API Key/Secret saat edit
                api_key_edit_disp = f'[Sekarang: {api_key_disp}]'
                api_sec_edit_disp = f'[Sekarang: {api_sec_disp}]'
                new_val = input(f" 7. API Key Baru {api_key_edit_disp}: ").strip()
                if new_val: temp_settings['binance_api_key'] = new_val; edited = True

                new_secret = getpass.getpass(f" 8. API Secret Baru {api_sec_edit_disp} (ketik u/ ubah): ").strip()
                if new_secret: temp_settings['binance_api_secret'] = new_secret; print(f"   {GREEN}Secret Key diperbarui (jika diketik).{RESET}"); edited = True

                new_val = input(f" 9. Trading Pair [{temp_settings['trading_pair']}] (misal: BTCUSDT): ").strip().upper()
                if new_val: temp_settings['trading_pair'] = new_val; edited = True

                while True:
                     new_val_str = input(f"10. Buy Quote Qty [{temp_settings['buy_quote_quantity']}], harus > 0: ").strip()
                     if not new_val_str: break
                     try:
                         new_qty = float(new_val_str)
                         if new_qty > 0:
                             temp_settings['buy_quote_quantity'] = new_qty; edited = True; break
                         else: print(f"   {RED}Kuantitas beli (quote) harus lebih besar dari 0.{RESET}")
                     except ValueError: print(f"   {RED}Input tidak valid, masukkan angka (misal: 11.5).{RESET}")

                while True:
                     new_val_str = input(f"11. Sell Base Qty [{temp_settings['sell_base_quantity']}], harus >= 0: ").strip()
                     if not new_val_str: break
                     try:
                         new_qty = float(new_val_str)
                         if new_qty >= 0:
                             temp_settings['sell_base_quantity'] = new_qty; edited = True; break
                         else: print(f"   {RED}Kuantitas jual (base) harus 0 atau lebih.{RESET}")
                     except ValueError: print(f"   {RED}Input tidak valid, masukkan angka (misal: 0.005).{RESET}")

                while True:
                     exec_prompt = f"{GREEN}Aktif{RESET}" if temp_settings['execute_binance_orders'] else f"{RED}Nonaktif{RESET}"
                     new_val_str = input(f"12. Aktifkan Eksekusi Order? (y/n) [Sekarang: {exec_prompt}]: ").lower().strip()
                     if not new_val_str: break
                     if new_val_str == 'y':
                         if not BINANCE_AVAILABLE:
                             print(f"   {RED}Tidak bisa mengaktifkan, library Binance hilang!{RESET}")
                         elif not temp_settings.get('binance_api_key') or not temp_settings.get('binance_api_secret'):
                             print(f"   {RED}Tidak bisa mengaktifkan, API Key/Secret Binance kosong!{RESET}")
                         else:
                              temp_settings['execute_binance_orders'] = True; print(f"   {GREEN}Eksekusi Order Diaktifkan.{RESET}"); edited = True; break
                     elif new_val_str == 'n':
                         temp_settings['execute_binance_orders'] = False; print(f"   {RED}Eksekusi Order Dinonaktifkan.{RESET}"); edited = True; break
                     else: print(f"   {RED}Input tidak valid, masukkan 'y' atau 'n'.{RESET}")

                # Setelah selesai edit, update settings utama jika ada perubahan
                if edited:
                    settings.update(temp_settings)
                    print(f"\n{YELLOW}Perubahan dicatat. Tekan 'S' untuk menyimpan atau 'K' untuk batal.{RESET}")
                else:
                    print(f"\n{DIM}Tidak ada perubahan.{RESET}")

                input(f"{DIM}Tekan Enter untuk kembali ke menu pengaturan...{RESET}")


            except Exception as edit_err:
                 print(f"\n{RED}{BOLD}Terjadi Error saat proses edit:{RESET} {edit_err}")
                 input(f"{DIM}Tekan Enter untuk kembali...{RESET}")

        elif choice == 's':
            save_settings(settings) # Simpan pengaturan yang mungkin sudah diubah
            input(f"\n{GREEN}{BOLD}✅ Pengaturan disimpan!{RESET} Tekan Enter untuk kembali ke Menu Utama...")
            break # Keluar dari loop show_settings

        elif choice == 'k':
            print(f"\n{YELLOW}Kembali ke Menu Utama (perubahan tidak disimpan jika belum tekan 'S')...{RESET}")
            time.sleep(1)
            break # Keluar dari loop show_settings
        else:
            print(f"\n{RED}{BOLD} Pilihan tidak valid! Masukkan S, E, atau K.{RESET}")
            time.sleep(1.5)

# --- Fungsi Menu Utama ---
def main_menu():
    """Menampilkan menu utama aplikasi."""
    # Load settings sekali di awal
    current_settings = load_settings()
    # Panggil animasi startup hanya sekali saat aplikasi pertama kali jalan
    startup_animation()

    while True:
        # Re-load settings setiap kali kembali ke menu utama, kalau-kalau file diedit manual
        # atau untuk memastikan setting terbaru dari show_settings() tercermin
        current_settings = load_settings()
        rows, cols = get_terminal_size()
        # Layout width adaptif
        layout_width = min(cols - 4, 100) # Maks 100, min lebar terminal - margin
        # Lebar kolom kiri (menu)
        left_col_width = min(max(40, layout_width // 2 - 4), layout_width - 25) # Sesuaikan agar pas
        padding = 4 # Jarak antar kolom

        # Efek visual sebelum clear (opsional)
        wipe_effect(rows, cols, char=random.choice(['*', '#', '+', '.']), delay=0.002)
        clear_screen()
        print("\n" * 1) # Margin atas sedikit

        # --- Konten Kolom Kiri (Menu Utama) ---
        left_content = []
        # Judul Aplikasi dengan border
        title = "Exora AI Email Listener"
        title_len = len(title)
        border_len = (left_col_width - title_len - 2) // 2 # -2 untuk spasi
        border = "═" * max(0, border_len)
        left_content.append(f"{BOLD}{BRIGHT_MAGENTA}╔{border} {title} {border}╗{RESET}")
        # Kosongkan baris bawah judul agar pas
        left_content.append(f"{BOLD}{BRIGHT_MAGENTA}╚{'═' * (left_col_width - 2)}╝{RESET}")
        left_content.append("")
        left_content.append(f"{BOLD}{WHITE}Menu Utama:{RESET}")

        # Opsi Menu
        exec_mode_label = ""
        if current_settings.get("execute_binance_orders"):
            exec_mode_label = f" {BOLD}& Binance{RESET}" if BINANCE_AVAILABLE else f" {RESET}({RED}Lib Error!{RESET}{BRIGHT_GREEN})"

        left_content.append(f" {BRIGHT_GREEN}{BOLD}1.{RESET} Mulai Listener (Email{exec_mode_label})")
        left_content.append(f" {BRIGHT_CYAN}{BOLD}2.{RESET} Buka Pengaturan")
        left_content.append(f" {BRIGHT_YELLOW}{BOLD}3.{RESET} Keluar Aplikasi")
        left_content.append("-" * left_col_width) # Separator

        # Status Cepat (lebih detail)
        left_content.append(f"{BOLD}{WHITE}Status Cepat:{RESET}")
        # Email Config Status
        email_ok = bool(current_settings.get('email_address')) and bool(current_settings.get('app_password'))
        email_status = status_ok if email_ok else status_nok + f" {YELLOW}(Perlu diisi){RESET}"
        left_content.append(f" Email Config : [{email_status}]")

        # Binance Status
        exec_on = current_settings.get("execute_binance_orders", False)
        exec_status_label = f"{GREEN}AKTIF{RESET}" if exec_on else f"{YELLOW}NONAKTIF{RESET}"
        lib_status = status_ok if BINANCE_AVAILABLE else status_nok + f" {RED}Missing!{RESET}"
        left_content.append(f" Binance Lib  : [{lib_status}] | Eksekusi: [{exec_status_label}]")

        # Binance Config Status (hanya jika eksekusi aktif & library ada)
        if exec_on and BINANCE_AVAILABLE:
            api_ok = bool(current_settings.get('binance_api_key')) and bool(current_settings.get('binance_api_secret'))
            pair_ok = bool(current_settings.get('trading_pair'))
            # Qty OK jika buy > 0 ATAU sell > 0 (salah satu cukup untuk potensi aksi)
            qty_buy_ok = current_settings.get('buy_quote_quantity', 0.0) > 0
            qty_sell_ok = current_settings.get('sell_base_quantity', 0.0) > 0
            qty_ok = qty_buy_ok or qty_sell_ok # Cukup salah satu > 0

            bin_cfg_status = status_nok
            reason = []
            if not api_ok: reason.append("API Key/Secret")
            if not pair_ok: reason.append("Trading Pair")
            if not qty_ok: reason.append("Buy/Sell Qty > 0")

            if api_ok and pair_ok and qty_ok:
                 bin_cfg_status = status_ok
            elif api_ok and pair_ok: # API & Pair OK, tapi Qty 0
                 bin_cfg_status = status_warn + f" {YELLOW}(Qty 0){RESET}"
            else: # API atau Pair kosong
                 bin_cfg_status = status_nok + f" {RED}({', '.join(reason)}?){RESET}"

            left_content.append(f" Binance Cfg  : [{bin_cfg_status}]")
        elif exec_on and not BINANCE_AVAILABLE:
             left_content.append(f" Binance Cfg  : [{status_nok}] {RED}(Library Error){RESET}")
        else:
            # Tidak perlu tampilkan detail config jika eksekusi nonaktif
            left_content.append(f" Binance Cfg  : [{DIM}N/A (Nonaktif){RESET}]")


        left_content.append("-" * left_col_width) # Separator bawah

        # --- ASCII Art (Kolom Kanan) ---
        # Gunakan ROCKET_ART yang sudah ada
        # Pad konten kiri dengan baris kosong agar tingginya sama dengan ROCKET_ART
        while len(left_content) < len(ROCKET_ART):
             left_content.append("")
        # Atau potong ROCKET_ART jika konten kiri lebih pendek (jarang terjadi)
        rocket_art_display = ROCKET_ART[:len(left_content)]


        # --- Cetak Layout ---
        # Optional Title Bar
        # print_centered(f"{REVERSE}{WHITE}{BOLD} MENU UTAMA {RESET}", layout_width)
        draw_two_column_layout(left_content, rocket_art_display, total_width=layout_width, left_width=left_col_width, padding=padding)
        print_separator(char="=", length=layout_width, color=BRIGHT_MAGENTA)

        # --- Input Pilihan ---
        choice = input(f"{BOLD}{WHITE}Masukkan pilihan Anda (1/2/3): {RESET}").strip()

        if choice == '1':
            # --- Validasi Sebelum Mulai Listener ---
            can_start = True
            print() # Baris baru sebelum pesan validasi
            if not email_ok:
                 print(f"{status_nok} {RED}Email atau App Password belum diatur di Pengaturan!{RESET}")
                 can_start = False

            # Validasi Binance hanya jika eksekusi diaktifkan
            if current_settings.get("execute_binance_orders"):
                if not BINANCE_AVAILABLE:
                     print(f"{status_nok} {RED}Eksekusi Binance aktif, tapi library 'python-binance' tidak ditemukan!{RESET}")
                     print(f"{DIM}   -> Install dengan 'pip install python-binance' atau nonaktifkan eksekusi.{RESET}")
                     can_start = False
                elif not api_ok:
                     print(f"{status_nok} {RED}Eksekusi Binance aktif, tapi API Key/Secret belum diatur!{RESET}")
                     can_start = False
                elif not pair_ok:
                     print(f"{status_nok} {RED}Eksekusi Binance aktif, tapi Trading Pair belum diatur!{RESET}")
                     can_start = False
                elif not qty_ok:
                     print(f"{status_warn} {YELLOW}Eksekusi Binance aktif, tapi Buy Quote Qty DAN Sell Base Qty keduanya 0 atau kurang.{RESET}")
                     print(f"{DIM}   -> Listener akan jalan, tapi tidak akan bisa eksekusi order.{RESET}")
                     # Tidak set can_start = False, user mungkin tetap ingin jalan

            if can_start:
                start_listening(current_settings)
                # Setelah listener berhenti (Ctrl+C atau error), kembali ke menu utama
                print(f"\n{YELLOW}[INFO] Kembali ke Menu Utama...{RESET}")
                input(f"{DIM}Tekan Enter untuk melanjutkan...{RESET}")
            else:
                print(f"\n{YELLOW}Silakan perbaiki konfigurasi di menu 'Pengaturan' (Pilihan 2).{RESET}")
                input(f"{DIM}Tekan Enter untuk kembali ke menu...{RESET}")

        elif choice == '2':
            show_settings(current_settings)
            # Settings di-reload di awal loop while, jadi perubahan akan tercermin
        elif choice == '3':
            clear_screen()
            # Pesan keluar yang lebih menarik
            print("\n" * max(3, rows // 3)) # Posisi agak ke bawah
            farewell_msg = f"{BRIGHT_CYAN}{BOLD}👋 Terima kasih telah menggunakan Exora AI Listener! Sampai jumpa! 👋{RESET}"
            print_centered(farewell_msg, cols)
            # Animasi roket kecil saat keluar? (Opsional)
            print_centered("       .", cols)
            print_centered("      / \\", cols)
            print_centered("     /__\\", cols)
            print("\n\n")
            time.sleep(0.5)
            sys.exit(0)
        else:
            print(f"\n{RED}{BOLD} Pilihan tidak valid! Masukkan 1, 2, atau 3.{RESET}")
            time.sleep(1.5) # Jeda agar user bisa baca pesan error


# --- Entry Point ---
if __name__ == "__main__":
    # Import 'requests' hanya jika diperlukan oleh Binance (opsional, bisa di atas)
    try:
        import requests
    except ImportError:
        # Jika requests tidak ada dan Binance dipakai, get_binance_client akan gagal nanti
        pass

    try:
        main_menu()
    except KeyboardInterrupt:
        # Signal handler seharusnya sudah menangani ini, tapi sebagai fallback
        print(f"\n{YELLOW}{BOLD}Program dihentikan paksa (KeyboardInterrupt tidak tertangkap handler).{RESET}")
        sys.exit(1)
    except Exception as e:
        # Tangkap error tak terduga di level tertinggi untuk graceful exit
        # Pastikan layar bersih sebelum menampilkan error kritis
        clear_screen()
        print(f"\n{BOLD}{RED}╔═══════════════════════════════════════╗{RESET}")
        print(f"{BOLD}{RED}║        💥 ERROR KRITIS TERDETEKSI 💥       ║{RESET}")
        print(f"{BOLD}{RED}╚═══════════════════════════════════════╝{RESET}")
        print(f"\n{RED}Terjadi error yang tidak dapat dipulihkan di luar loop utama:{RESET}")
        # Tampilkan traceback untuk debugging
        print(f"{YELLOW}{'-'*60}{RESET}")
        traceback.print_exc()
        print(f"{YELLOW}{'-'*60}{RESET}")
        print(f"\n{RED}{BOLD}Pesan Error:{RESET} {type(e).__name__}: {e}")
        print("\n{RED}Program akan ditutup.{RESET}")
        # Beri waktu user membaca error sebelum exit (opsional)
        # input("\nTekan Enter untuk keluar...")
        sys.exit(1)
