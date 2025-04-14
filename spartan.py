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
# (Kode Binance Integration tetap sama)
try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException, BinanceOrderException
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False
    # Pesan warning sudah ada di load_settings
    class BinanceAPIException(Exception): pass
    class BinanceOrderException(Exception): pass
    class Client:
        SIDE_BUY = 'BUY'
        SIDE_SELL = 'SELL'
        ORDER_TYPE_MARKET = 'MARKET'

# --- Konfigurasi & Variabel Global ---
CONFIG_FILE = "config.json"
DEFAULT_SETTINGS = {
    # ... (Default settings tetap sama)
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
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m" # Mungkin tidak support di semua terminal
UNDERLINE = "\033[4m"
BLINK = "\033[5m" # Hindari jika bisa, sering mengganggu
REVERSE = "\033[7m" # Tukar foreground/background
HIDDEN = "\033[8m" # Teks tersembunyi
# Warna Dasar
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"
# Warna Cerah (Bright)
BRIGHT_RED = "\033[91m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_YELLOW = "\033[93m"
BRIGHT_BLUE = "\033[94m"
BRIGHT_MAGENTA = "\033[95m"
BRIGHT_CYAN = "\033[96m"
BRIGHT_WHITE = "\033[97m"
# Warna Background (Contoh)
BG_RED = "\033[41m"
BG_GREEN = "\033[42m"
BG_BLUE = "\033[44m"

# --- Karakter "Animasi" ---
spinner_chars = ['▹▹▹▹▹', '▸▹▹▹▹', '▹▸▹▹▹', '▹▹▸▹▹', '▹▹▹▸▹', '▹▹▹▹▸']
# spinner_chars = ['🌍', '🌎', '🌏'] # Emoji spinner (butuh font support)
# spinner_chars = ['[■□□□]', '[□■□□]', '[□□■□]', '[□□□■]'] # Blok loading
loading_bar_char = '█'
wipe_char = '▓' # Karakter untuk efek wipe
status_ok = f"{GREEN}✔{RESET}"
status_nok = f"{RED}✘{RESET}"
status_warn = f"{YELLOW}⚠{RESET}"
status_wait = f"{BLUE}⏳{RESET}"

# --- ASCII Art (Contoh) ---
# Ganti dengan ASCII art favoritmu, usahakan tingginya mirip menu
# Cari di Google: "text ascii art generator"
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
    os.system('cls' if os.name == 'nt' else 'clear')

def get_terminal_size():
    try:
        # Cara standar (mungkin butuh library 'shutil' di Python 3.3+)
        columns, rows = os.get_terminal_size(0)
    except (OSError, AttributeError, NameError):
        try:
            # Fallback untuk beberapa environment
            rows, columns = os.popen('stty size', 'r').read().split()
            rows, columns = int(rows), int(columns)
        except ValueError:
            # Default jika semua gagal
            rows, columns = 24, 80
    return rows, columns

def print_centered(text, width, color=RESET):
    padding = (width - len(text)) // 2
    print(f"{color}{' ' * padding}{text}{RESET}")

def print_separator(char="─", length=80, color=DIM + WHITE + RESET):
    print(f"{color}{char * length}{RESET}")

def wipe_effect(rows, cols, char=wipe_char, delay=0.005, color=DIM):
    """Efek wipe sederhana."""
    for r in range(rows // 2):
        line = char * cols
        # Wipe dari atas dan bawah ke tengah
        sys.stdout.write(f"\033[{r + 1};1H{color}{line}{RESET}") # Cetak di baris r+1
        sys.stdout.write(f"\033[{rows - r};1H{color}{line}{RESET}") # Cetak di baris rows-r
        sys.stdout.flush()
        time.sleep(delay)
    # Jeda singkat di tengah
    # time.sleep(0.1)
    # Hapus wipe (atau akan ditimpa clear_screen setelahnya)
    # for r in range(rows // 2):
    #     line = " " * cols
    #     sys.stdout.write(f"\033[{rows//2 - r};1H{line}")
    #     sys.stdout.write(f"\033[{rows//2 + 1 + r};1H{line}")
    #     sys.stdout.flush()
    #     time.sleep(delay)

def draw_two_column_layout(left_lines, right_lines, total_width=90, left_width=45, padding=4):
    """ Mencetak dua kolom bersebelahan """
    right_width = total_width - left_width - padding
    max_lines = max(len(left_lines), len(right_lines))
    spacer = " " * padding

    for i in range(max_lines):
        left_part = left_lines[i].rstrip() if i < len(left_lines) else ""
        right_part = right_lines[i].rstrip() if i < len(right_lines) else ""

        # Pad left part agar lebarnya konsisten
        left_padded = left_part.ljust(left_width)
        # Pad right part (meskipun ASCII art biasanya tidak perlu)
        right_padded = right_part.ljust(right_width)

        # Gabungkan dan cetak
        # Hati-hati: ANSI codes bisa mengacaukan perhitungan panjang ljust.
        # Jika ada ANSI di left_part, perlu cara hitung panjang yg lebih canggih.
        # Untuk sekarang, asumsi ANSI hanya di awal/akhir atau tidak signifikan.
        print(f"{left_padded}{spacer}{right_padded}")

def startup_animation():
    """Animasi sederhana saat program dimulai."""
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

    print("\n" * (rows // 3)) # Posisi agak ke bawah
    print_centered(brand, cols, BOLD + MAGENTA)
    print("\n")

    for i, stage in enumerate(stages):
        progress = f"{BLUE}{stage}{RESET} {messages[i]}"
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
# (Tetap sama)
def signal_handler(sig, frame):
    global running
    print(f"\n{BRIGHT_YELLOW}{BOLD}🛑 Ctrl+C terdeteksi! Menghentikan semua proses...{RESET}")
    running = False
    time.sleep(0.5)
    # Mungkin perlu cleanup tambahan di sini jika ada proses background
    print(f"\n{RED}{BOLD}👋 Sampai jumpa!{RESET}")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# --- Fungsi Konfigurasi ---
# (Load & Save Settings tetap sama, mungkin tambahkan print status)
def load_settings():
    """Memuat pengaturan dari file JSON."""
    # print(f"{DIM}💾 Memuat pengaturan dari {CONFIG_FILE}...{RESET}") # Optional
    settings = DEFAULT_SETTINGS.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_settings = json.load(f)
                # ... (validasi tetap sama) ...
                # Hanya update kunci yang ada di default
                for key in DEFAULT_SETTINGS:
                    if key in loaded_settings:
                        settings[key] = loaded_settings[key]

                # Validasi (keep simple for now)
                settings["check_interval_seconds"] = max(5, int(settings.get("check_interval_seconds", 10)))
                settings["buy_quote_quantity"] = max(0.0, float(settings.get("buy_quote_quantity", 11.0)))
                settings["sell_base_quantity"] = max(0.0, float(settings.get("sell_base_quantity", 0.0)))
                settings["execute_binance_orders"] = bool(settings.get("execute_binance_orders", False))

                # Save back corrections silently
                save_settings(settings, silent=True)
        except json.JSONDecodeError:
            print(f"{RED}[ERROR] File konfigurasi '{CONFIG_FILE}' rusak. Menggunakan default & menyimpan ulang.{RESET}")
            save_settings(settings)
        except Exception as e:
            print(f"{RED}[ERROR] Gagal memuat konfigurasi: {e}{RESET}")
            print(f"{YELLOW}[WARN] Menggunakan pengaturan default sementara.{RESET}")
    else:
        print(f"{YELLOW}[INFO] File '{CONFIG_FILE}' tidak ditemukan. Membuat dengan nilai default.{RESET}")
        save_settings(settings)
    # print(f"{GREEN}👍 Pengaturan dimuat.{RESET}") # Optional
    return settings

def save_settings(settings, silent=False):
    """Menyimpan pengaturan ke file JSON."""
    try:
        settings_to_save = {key: settings[key] for key in DEFAULT_SETTINGS if key in settings}
        # ... (validasi tipe data sebelum save tetap sama) ...
        settings_to_save['check_interval_seconds'] = int(settings_to_save.get('check_interval_seconds', 10))
        settings_to_save['buy_quote_quantity'] = float(settings_to_save.get('buy_quote_quantity', 11.0))
        settings_to_save['sell_base_quantity'] = float(settings_to_save.get('sell_base_quantity', 0.0))
        settings_to_save['execute_binance_orders'] = bool(settings_to_save.get('execute_binance_orders', False))

        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings_to_save, f, indent=4, sort_keys=True)
        if not silent:
            print(f"{GREEN}{BOLD}💾 Pengaturan berhasil disimpan ke '{CONFIG_FILE}'{RESET}")
    except Exception as e:
        print(f"{RED}[ERROR] Gagal menyimpan konfigurasi: {e}{RESET}")


# --- Fungsi Utilitas Lain ---
# (decode_mime_words, get_text_from_email, trigger_beep tetap sama fungsinya)
# (Mungkin tambahkan sedikit visual feedback di dalamnya)
def get_timestamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def decode_mime_words(s):
    # Fungsi ini krusial dan biarkan seperti adanya
    if not s: return ""
    decoded_parts = decode_header(s)
    result = []
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            try: result.append(part.decode(encoding or 'utf-8', errors='replace'))
            except (LookupError, ValueError): result.append(part.decode('utf-8', errors='replace'))
        else: result.append(part)
    return "".join(result)

def get_text_from_email(msg):
    # Fungsi ini krusial dan biarkan seperti adanya
    text_content = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            if content_type == "text/plain" and "attachment" not in content_disposition.lower():
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    text_content += payload.decode(charset, errors='replace') + "\n"
                except Exception as e:
                    print(f"{YELLOW}[WARN] Tidak bisa mendekode bagian email (text/plain): {e}{RESET}")
    else:
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                text_content = payload.decode(charset, errors='replace')
            except Exception as e:
                 print(f"{YELLOW}[WARN] Tidak bisa mendekode body email (non-multipart): {e}{RESET}")
    return text_content.lower()

def trigger_beep(action):
    try:
        action_upper = action.upper()
        action_color = GREEN if action == "buy" else RED if action == "sell" else MAGENTA
        print(f"{action_color}{BOLD}🔊 BEEP {action_upper}! 🔊{RESET}")
        # Coba 'tput bel' sebagai alternatif cross-platform sederhana jika 'beep' tidak ada
        try:
            if action == "buy":
                subprocess.run(["beep", "-f", "1000", "-l", "500", "-D", "100", "-r", "3"], check=True, capture_output=True, text=True, timeout=3)
            elif action == "sell":
                subprocess.run(["beep", "-f", "700", "-l", "700", "-D", "100", "-r", "2"], check=True, capture_output=True, text=True, timeout=3)
            else:
                 print("\a", end='') # Bell standar untuk aksi lain
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
            print("\a", end='') # Fallback ke system bell standar
            sys.stdout.flush() # Pastikan bell bunyi
    except Exception as e:
        print(f"{RED}[ERROR] Kesalahan tak terduga saat beep: {e}{RESET}")


# --- Fungsi Eksekusi Binance ---
# (get_binance_client & execute_binance_order tetap sama fungsinya)
# (Tambahkan visualisasi koneksi/eksekusi)
def get_binance_client(settings):
    if not BINANCE_AVAILABLE: return None
    if not settings.get('binance_api_key') or not settings.get('binance_api_secret'):
        print(f"{status_nok} {RED}{BOLD}API Key/Secret Binance kosong!{RESET}")
        return None
    try:
        print(f"{status_wait} {CYAN}Menghubungkan ke Binance API...{RESET}", end='\r')
        client = Client(settings['binance_api_key'], settings['binance_api_secret'])
        client.ping()
        acc_info = client.get_account() # Dapatkan info akun singkat
        balances = [b for b in acc_info.get('balances', []) if float(b['free']) > 0]
        print(f"{status_ok} {GREEN}{BOLD}Koneksi Binance API Berhasil!                {RESET}")
        # print(f"{DIM}   -> Akun: {acc_info.get('email', 'N/A')}{RESET}") # Email mungkin tidak tersedia
        # print(f"{DIM}   -> Saldo Aktif: {len(balances)} koin{RESET}")
        return client
    except BinanceAPIException as e:
        print(f"{status_nok} {RED}{BOLD}Koneksi/Auth Binance Gagal:{RESET} {e.status_code} - {e.message}")
        return None
    except Exception as e:
        print(f"{status_nok} {RED}{BOLD}Gagal membuat Binance client:{RESET} {e}")
        return None

def execute_binance_order(client, settings, side):
    if not client:
        print(f"{status_warn} {YELLOW}Eksekusi dibatalkan, client Binance tidak valid.{RESET}")
        return False
    if not settings.get("execute_binance_orders", False):
        print(f"{status_warn} {YELLOW}Eksekusi order dinonaktifkan. Order dilewati.{RESET}")
        return False

    pair = settings.get('trading_pair', '').upper()
    if not pair:
        print(f"{status_nok} {RED}{BOLD}Trading pair belum diatur!{RESET}")
        return False

    order_details = {}
    action_desc = ""
    side_color = BRIGHT_GREEN if side == Client.SIDE_BUY else BRIGHT_RED
    side_icon = "🛒" if side == Client.SIDE_BUY else "💰"

    try:
        print(f"\n{side_color}--- {BOLD}PERSIAPAN ORDER {side} ({pair}){RESET} {side_color}---{RESET}")
        if side == Client.SIDE_BUY:
            quote_qty = settings.get('buy_quote_quantity', 0.0)
            if quote_qty <= 0:
                 print(f"{status_nok} {RED}Kuantitas Beli (buy_quote_quantity) harus > 0.{RESET}")
                 return False
            order_details = {'symbol': pair, 'side': Client.SIDE_BUY, 'type': Client.ORDER_TYPE_MARKET, 'quoteOrderQty': quote_qty}
            quote_asset = "USDT" # Asumsi USDT, bisa dibuat lebih dinamis
            if pair.endswith("USDT"): quote_asset = "USDT"
            elif pair.endswith("BUSD"): quote_asset = "BUSD"
            elif pair.endswith("BTC"): quote_asset = "BTC"
            # etc.
            action_desc = f"{side_icon} {BOLD}MARKET BUY{RESET} {quote_qty} {quote_asset} untuk {pair}"

        elif side == Client.SIDE_SELL:
            base_qty = settings.get('sell_base_quantity', 0.0)
            if base_qty <= 0:
                 if settings.get('sell_base_quantity') == 0: print(f"{status_warn} {YELLOW}Kuantitas Jual 0. Order SELL dilewati.{RESET}")
                 else: print(f"{status_nok} {RED}Kuantitas Jual (sell_base_quantity) harus > 0.{RESET}")
                 return False
            order_details = {'symbol': pair, 'side': Client.SIDE_SELL, 'type': Client.ORDER_TYPE_MARKET, 'quantity': base_qty}
            base_asset = pair.replace("USDT", "").replace("BUSD","").replace("BTC","") # Guesstimate
            action_desc = f"{side_icon} {BOLD}MARKET SELL{RESET} {base_qty} {base_asset} dari {pair}"
        else:
            print(f"{status_nok} {RED}Sisi order tidak valid: {side}{RESET}")
            return False

        print(f"{CYAN}{status_wait} Mencoba eksekusi: {action_desc}...{RESET}")
        # ---- INI BAGIAN PENTING EKSEKUSI ----
        order_result = client.create_order(**order_details)
        # ------------------------------------

        print(f"{side_color}{BOLD}✅ ORDER BERHASIL DI EKSEKUSI!{RESET}")
        print(f"{DIM}-------------------------------------------")
        print(f"{DIM}  Order ID : {order_result.get('orderId')}")
        print(f"{DIM}  Symbol   : {order_result.get('symbol')}")
        print(f"{DIM}  Side     : {order_result.get('side')}")
        print(f"{DIM}  Status   : {order_result.get('status')}")
        if order_result.get('fills'):
            # ... (perhitungan avg price, filled qty, total cost tetap sama) ...
            total_qty = sum(float(f['qty']) for f in order_result['fills'])
            total_quote_qty = sum(float(f['cummulativeQuoteQty']) for f in order_result['fills']) # Pakai cummulativeQuoteQty
            avg_price = total_quote_qty / total_qty if total_qty else 0
            print(f"{DIM}  Avg Price: {avg_price:.8f}")
            print(f"{DIM}  Filled Qty: {total_qty:.8f} (Base)")
            print(f"{DIM}  Total Cost: {total_quote_qty:.4f} (Quote)")
        print(f"-------------------------------------------{RESET}")
        return True

    except BinanceAPIException as e:
        print(f"{status_nok} {RED}{BOLD}BINANCE API ERROR:{RESET} {e.status_code} - {e.message}")
        # ... (pesan error spesifik tetap sama) ...
        if e.code == -2010: print(f"{RED}      -> SALDO TIDAK CUKUP?{RESET}")
        elif e.code == -1121: print(f"{RED}      -> Trading pair '{pair}' TIDAK VALID?{RESET}")
        elif e.code == -1013 or 'MIN_NOTIONAL' in str(e.message): print(f"{RED}      -> Order size TERLALU KECIL (cek MIN_NOTIONAL)?{RESET}")
        elif e.code == -1111 or 'LOT_SIZE' in str(e.message): print(f"{RED}      -> Kuantitas tidak sesuai LOT_SIZE filter?{RESET}")
        return False
    except BinanceOrderException as e:
        print(f"{status_nok} {RED}{BOLD}BINANCE ORDER ERROR:{RESET} {e.status_code} - {e.message}")
        return False
    except Exception as e:
        print(f"{status_nok} {RED}{BOLD}ERROR EKSEKUSI BINANCE:{RESET}")
        traceback.print_exc()
        return False
    finally:
         print(f"{side_color}--- {BOLD}SELESAI PROSES ORDER {side} ({pair}){RESET} {side_color}---{RESET}\n")


# --- Fungsi Pemrosesan Email ---
def process_email(mail, email_id, settings, binance_client):
    global running
    if not running: return

    target_keyword_lower = settings['target_keyword'].lower()
    trigger_keyword_lower = settings['trigger_keyword'].lower()
    email_id_str = email_id.decode('utf-8')
    ts = get_timestamp()

    try:
        print(f"\n{MAGENTA}📧 {BOLD}Memproses Email ID: {email_id_str} [{ts}]{RESET}{MAGENTA} ==={RESET}")
        print(f"{DIM}   Mengambil data email...{RESET}", end='\r')
        status, data = mail.fetch(email_id, "(RFC822)")
        if status != 'OK':
            print(f"{status_nok} {RED}Gagal mengambil email ID {email_id_str}: {status}   {RESET}")
            return
        print(f"{GREEN}   Data email diterima.                 {RESET}") # Clear prev line

        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        subject = decode_mime_words(msg["Subject"])
        sender = decode_mime_words(msg["From"])

        print(f"   {CYAN}Dari  :{RESET} {sender}")
        print(f"   {CYAN}Subjek:{RESET} {subject}")
        print(f"{MAGENTA}-------------------------------------------{RESET}")

        body = get_text_from_email(msg)
        full_content = (subject.lower() + " " + body)

        if target_keyword_lower in full_content:
            print(f"{GREEN}🎯 {BOLD}Keyword Target Ditemukan!{RESET} ('{settings['target_keyword']}')")
            try:
                target_index = full_content.find(target_keyword_lower)
                trigger_index = full_content.find(trigger_keyword_lower, target_index + len(target_keyword_lower))

                if trigger_index != -1:
                    start_word_index = trigger_index + len(trigger_keyword_lower)
                    text_after_trigger = full_content[start_word_index:].lstrip()
                    words_after_trigger = text_after_trigger.split(maxsplit=1)

                    if words_after_trigger:
                        action_word = words_after_trigger[0].strip('.,!?:;()[]{}').lower()
                        action_color = BRIGHT_GREEN if action_word == "buy" else BRIGHT_RED if action_word == "sell" else BRIGHT_YELLOW
                        print(f"{action_color}📌 {BOLD}Keyword Trigger Ditemukan!{RESET} ('{settings['trigger_keyword']}') -> Aksi: {BOLD}{action_word.upper()}{RESET}")

                        # --- Trigger Aksi ---
                        if action_word == "buy" or action_word == "sell":
                            trigger_beep(action_word)
                            if settings.get("execute_binance_orders"):
                                if binance_client:
                                    execute_binance_order(binance_client, settings, getattr(Client, f"SIDE_{action_word.upper()}"))
                                else:
                                    print(f"{status_warn} {YELLOW}Eksekusi Binance aktif tapi client tidak siap.{RESET}")
                            elif action_word in ["buy", "sell"]:
                                 print(f"{DIM}   (Eksekusi Binance dinonaktifkan){RESET}")
                        else:
                            print(f"{status_warn} {YELLOW}Aksi '{action_word}' tidak dikenal (bukan 'buy'/'sell'). Tidak ada aksi market.{RESET}")
                    else:
                        print(f"{status_warn} {YELLOW}Tidak ada kata setelah keyword trigger '{settings['trigger_keyword']}'.{RESET}")
                else:
                     print(f"{status_warn} {YELLOW}Keyword trigger '{settings['trigger_keyword']}' tidak ditemukan SETELAH target '{settings['target_keyword']}'.{RESET}")
            except Exception as e:
                 print(f"{status_nok} {RED}Gagal parsing setelah trigger: {e}{RESET}")
        else:
            print(f"{BLUE}💨 Keyword target '{settings['target_keyword']}' tidak ditemukan.{RESET}")

        # Tandai email sebagai 'Seen'
        try:
            # print(f"{DIM}   Menandai email {email_id_str} sebagai 'Seen'...{RESET}")
            mail.store(email_id, '+FLAGS', '\\Seen')
        except Exception as e:
            print(f"{status_nok} {RED}Gagal menandai email {email_id_str} sebagai 'Seen': {e}{RESET}")
        print(f"{MAGENTA}==========================================={RESET}")

    except Exception as e:
        print(f"{status_nok} {RED}{BOLD}Gagal total memproses email ID {email_id_str}:{RESET}")
        traceback.print_exc()
        print(f"{MAGENTA}==========================================={RESET}")


# --- Fungsi Listening Utama ---
def start_listening(settings):
    global running, spinner_chars
    running = True
    mail = None
    binance_client = None
    wait_time = 30
    connection_attempts = 0
    spinner_index = 0

    rows, cols = get_terminal_size()
    clear_screen()
    print("\n" * 2) # Sedikit margin atas
    print_separator(char="*", length=cols-4, color=MAGENTA)
    mode = "Email & Binance Order" if settings.get("execute_binance_orders") else "Email Listener Only"
    print_centered(f"🚀 {BOLD}MODE AKTIF: {mode}{RESET} 🚀", cols-4, MAGENTA)
    print_separator(char="*", length=cols-4, color=MAGENTA)
    print("\n")

    # --- Setup Binance ---
    if settings.get("execute_binance_orders"):
        if not BINANCE_AVAILABLE:
             print(f"{status_nok} {RED}{BOLD}FATAL: Library 'python-binance' tidak ada!{RESET}")
             running = False; return
        print(f"{CYAN}🔗 {BOLD}[SETUP] Menginisialisasi Koneksi Binance...{RESET}")
        binance_client = get_binance_client(settings)
        if not binance_client:
            print(f"{status_nok} {RED}{BOLD}FATAL: Gagal konek Binance. Eksekusi order dibatalkan.{RESET}")
            # Beri opsi lanjut tanpa binance atau keluar
            # running = False; return # Opsi: langsung stop
            print(f"{YELLOW}Nonaktifkan eksekusi Binance di pengaturan jika ingin lanjut tanpa order.{RESET}")
            settings['execute_binance_orders'] = False # Nonaktifkan paksa untuk sesi ini
            print(f"{YELLOW}Eksekusi Binance dinonaktifkan untuk sesi ini.{RESET}")
            time.sleep(3)
        else:
            print(f"{status_ok} {GREEN}{BOLD}[SETUP] Binance Client Siap!{RESET}")
    else:
        print(f"{YELLOW}ℹ️ {BOLD}[INFO] Eksekusi order Binance dinonaktifkan.{RESET}")

    print_separator(length=cols-4, color=CYAN)
    print(f"{CYAN}📧 {BOLD}[SETUP] Menyiapkan Listener Email...{RESET}")
    print(f"{DIM}   Akun  : {settings['email_address']}{RESET}")
    print(f"{DIM}   Server: {settings['imap_server']}{RESET}")
    print_separator(length=cols-4, color=CYAN)
    time.sleep(1)
    print(f"\n{BOLD}{WHITE}Memulai pemantauan... (Ctrl+C untuk berhenti){RESET}")
    print("-" * (cols - 4))

    # --- Loop Utama Listener ---
    while running:
        try:
            # --- Koneksi IMAP ---
            if not mail or mail.state != 'SELECTED':
                connection_attempts += 1
                print(f"{status_wait} {CYAN}[{connection_attempts}] Menghubungkan ke IMAP ({settings['imap_server']})...{RESET}", end='\r')
                try:
                    mail = imaplib.IMAP4_SSL(settings['imap_server'])
                    print(f"{status_ok} {GREEN}Terhubung ke IMAP Server.               {RESET}")
                    print(f"{status_wait} {CYAN}Login sebagai {settings['email_address']}...{RESET}", end='\r')
                    mail.login(settings['email_address'], settings['app_password'])
                    print(f"{status_ok} {GREEN}Login Email Berhasil! ({settings['email_address']}){RESET}     ")
                    mail.select("inbox")
                    print(f"{status_ok} {GREEN}Masuk ke INBOX. Siap mendengarkan...{RESET}")
                    print("-" * (cols-4))
                    connection_attempts = 0
                except (imaplib.IMAP4.error, imaplib.IMAP4.abort, socket.error, OSError) as imap_err:
                    print(f"{status_nok} {RED}{BOLD}Gagal koneksi/login IMAP:{RESET} {imap_err} ")
                    if "authentication failed" in str(imap_err).lower() or "invalid credentials" in str(imap_err).lower():
                         print(f"{RED}{BOLD}   -> PERIKSA EMAIL & APP PASSWORD! Akses IMAP sudah aktif?{RESET}")
                         running = False; return
                    else:
                         print(f"{YELLOW}   -> Mencoba lagi dalam {wait_time} detik...{RESET}")
                         time.sleep(wait_time)
                         continue # Coba lagi dari awal loop while

            # --- Loop Cek Email (Inner) ---
            while running:
                # Check IMAP health
                try:
                    status, _ = mail.noop()
                    if status != 'OK':
                        print(f"\n{status_warn} {YELLOW}Koneksi IMAP NOOP gagal ({status}). Reconnecting...{RESET}")
                        break
                except (imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError) as NopErr:
                     print(f"\n{status_warn} {YELLOW}Koneksi IMAP terputus ({type(NopErr).__name__}). Reconnecting...{RESET}")
                     break

                # Check Binance health (optional, bisa dilewati jika jarang error)
                # ... (bisa ditambahkan jika perlu) ...

                # --- Cek Email Baru (UNSEEN) ---
                status, messages = mail.search(None, '(UNSEEN)')
                if status != 'OK':
                     print(f"\n{status_nok} {RED}Gagal mencari email: {status}. Reconnecting...{RESET}")
                     break

                email_ids = messages[0].split()
                if email_ids:
                    print(" " * (cols - 4), end='\r') # Hapus pesan tunggu
                    print(f"\n{BRIGHT_GREEN}{BOLD}✨ Ditemukan {len(email_ids)} email baru! Memproses... ✨{RESET}")
                    print("-" * (cols - 4))
                    for email_id in email_ids:
                        if not running: break
                        process_email(mail, email_id, settings, binance_client)
                    if not running: break
                    print("-" * (cols - 4))
                    print(f"{GREEN}✅ Selesai memproses. Kembali mendengarkan...{RESET}")
                    print("-" * (cols - 4))
                else:
                    # --- Tidak ada email baru, tampilkan spinner ---
                    wait_interval = settings['check_interval_seconds']
                    spinner = spinner_chars[spinner_index % len(spinner_chars)]
                    spinner_index += 1
                    wait_message = f"{BLUE}{BOLD}{spinner}{RESET}{BLUE} Menunggu email baru ({wait_interval}s)... {RESET}"
                    # Pastikan pesan tidak melebihi lebar kolom
                    print(wait_message.ljust(cols - 4), end='\r')

                    # Tidur per detik agar responsif Ctrl+C
                    for i in range(wait_interval):
                         if not running: break
                         time.sleep(1)
                         # Update spinner atau timer jika mau
                         # spinner = spinner_chars[spinner_index % len(spinner_chars)]
                         # spinner_index += 1
                         # wait_message = f"{BLUE}{BOLD}{spinner}{RESET}{BLUE} Menunggu ({wait_interval - (i+1)}s)... {RESET}"
                         # print(wait_message.ljust(cols - 4), end='\r')

                    if not running: break
                    # Hapus pesan tunggu setelah selesai (opsional, karena akan ditimpa di iterasi berikutnya)
                    # print(" " * (cols - 4), end='\r')

            # --- Keluar dari loop inner ---
            if mail and mail.state == 'SELECTED':
                try: mail.close()
                except Exception: pass

        # --- Exception Handling Luar ---
        except (ConnectionError, OSError, socket.error, socket.gaierror) as net_err:
             print(f"\n{status_nok} {RED}{BOLD}Kesalahan Koneksi Jaringan:{RESET} {net_err}")
             print(f"{YELLOW}   -> Periksa internet. Mencoba lagi dalam {wait_time} detik...{RESET}")
             time.sleep(wait_time)
        except Exception as e:
            print(f"\n{status_nok} {RED}{BOLD}ERROR TAK TERDUGA DI LOOP UTAMA:{RESET}")
            traceback.print_exc()
            print(f"{YELLOW}   -> Mencoba recovery dalam {wait_time} detik...{RESET}")
            time.sleep(wait_time)
        finally:
            if mail:
                try:
                    if mail.state != 'LOGOUT': mail.logout()
                except Exception: pass
            mail = None
            if running: time.sleep(3) # Jeda sebelum retry koneksi utama

    print(f"\n{BRIGHT_YELLOW}{BOLD}🛑 Listener dihentikan.{RESET}")
    print("-"*(cols-4))


# --- Fungsi Menu Pengaturan ---
def show_settings(settings):
    rows, cols = get_terminal_size()
    layout_width = min(cols - 4, 100) # Batasi lebar layout maks 100
    left_col_width = layout_width // 2 - 3 # Lebar kolom kiri

    while True:
        wipe_effect(rows, cols, char='.') # Efek wipe titik
        clear_screen()
        print("\n" * 2) # Margin atas

        # --- Konten Kolom Kiri ---
        left_content = []
        left_content.append(f"{BOLD}{BRIGHT_CYAN}⚙️=== Pengaturan Listener ===⚙️{RESET}")
        left_content.append("-" * left_col_width)
        left_content.append(f"{BLUE}{BOLD}--- Email Settings ---{RESET}")
        email_disp = settings['email_address'] or f'{YELLOW}[Kosong]{RESET}'
        pwd_disp = settings['app_password'][:2] + '*' * (len(settings['app_password']) - 2) if len(settings['app_password']) > 1 else (f"{YELLOW}[Kosong]{RESET}" if not settings['app_password'] else settings['app_password'])
        left_content.append(f" 1. {CYAN}Email{RESET}    : {email_disp}")
        left_content.append(f" 2. {CYAN}App Pass{RESET} : {pwd_disp}")
        left_content.append(f" 3. {CYAN}IMAP Srv{RESET} : {settings['imap_server']}")
        left_content.append(f" 4. {CYAN}Interval{RESET} : {settings['check_interval_seconds']}s {DIM}(min:5){RESET}")
        left_content.append(f" 5. {CYAN}Target KW{RESET}: {BOLD}{settings['target_keyword']}{RESET}")
        left_content.append(f" 6. {CYAN}Trigger KW{RESET}: {BOLD}{settings['trigger_keyword']}{RESET}")
        left_content.append("")
        left_content.append(f"{BLUE}{BOLD}--- Binance Settings ---{RESET}")
        lib_status = f"{GREEN}✅ Ready{RESET}" if BINANCE_AVAILABLE else f"{RED}❌ Missing!{RESET}"
        left_content.append(f" Library     : {lib_status}")
        api_key_disp = settings['binance_api_key'][:4] + '...' + settings['binance_api_key'][-4:] if len(settings['binance_api_key']) > 8 else (f"{YELLOW}[Kosong]{RESET}" if not settings['binance_api_key'] else settings['binance_api_key'])
        api_sec_disp = settings['binance_api_secret'][:4] + '...' + settings['binance_api_secret'][-4:] if len(settings['binance_api_secret']) > 8 else (f"{YELLOW}[Kosong]{RESET}" if not settings['binance_api_secret'] else settings['binance_api_secret'])
        left_content.append(f" 7. {CYAN}API Key{RESET}   : {api_key_disp}")
        left_content.append(f" 8. {CYAN}API Secret{RESET}: {api_sec_disp}")
        pair_disp = settings['trading_pair'] or f'{YELLOW}[Kosong]{RESET}'
        left_content.append(f" 9. {CYAN}TradingPair{RESET}: {BOLD}{pair_disp}{RESET}")
        left_content.append(f"10. {CYAN}Buy Qty{RESET}  : {settings['buy_quote_quantity']} {DIM}(Quote>0){RESET}")
        left_content.append(f"11. {CYAN}Sell Qty{RESET} : {settings['sell_base_quantity']} {DIM}(Base>=0){RESET}")
        exec_status = f"{GREEN}{BOLD}✅ AKTIF{RESET}" if settings['execute_binance_orders'] else f"{RED}❌ NONAKTIF{RESET}"
        left_content.append(f"12. {CYAN}Eksekusi{RESET}  : {exec_status}")
        left_content.append("-" * left_col_width)
        left_content.append(f" {GREEN}{BOLD}E{RESET} - Edit Pengaturan")
        left_content.append(f" {RED}{BOLD}K{RESET} - Kembali ke Menu")
        left_content.append("-" * left_col_width)

        # --- Gambar ASCII Art ---
        # (Pastikan jumlah baris art sesuai atau lebih sedikit dari left_content)
        settings_art = [ # Contoh art lain
            "   .--.",
            "  |o_o |",
            "  |:_/ |",
            " //   \\ \\",
            "(|     | )",
            "/'\\_   _/`\\",
            "\\___)=(___/"
        ] + [""] * (len(left_content) - 7) # Pad art biar sama tinggi

        # --- Cetak Layout ---
        print_centered(f"{REVERSE}{WHITE}{BOLD} PENGATURAN {RESET}", layout_width)
        draw_two_column_layout(left_content, settings_art, total_width=layout_width, left_width=left_col_width, padding=4)
        print_separator(char="=", length=layout_width, color=BRIGHT_CYAN)

        choice = input(f"{BOLD}{WHITE}Pilihan Anda (E/K): {RESET}").lower().strip()

        if choice == 'e':
            print(f"\n{BOLD}{MAGENTA}--- Edit Pengaturan ---{RESET} {DIM}(Kosongkan untuk skip){RESET}")
            # --- Proses Edit ---
            # (Logika input edit tetap sama, mungkin tambahkan validasi lebih ketat)

            # Email
            print(f"\n{CYAN}--- Email ---{RESET}")
            new_val = input(f" 1. Email [{settings['email_address']}]: ").strip()
            if new_val: settings['email_address'] = new_val
            try:
                current_pass_display = '[Hidden]' if settings['app_password'] else '[Kosong]'
                new_pass = getpass.getpass(f" 2. App Password Baru [{current_pass_display}] (ketik u/ ubah): ").strip()
                if new_pass: settings['app_password'] = new_pass; print(f"   {GREEN}Password diperbarui.{RESET}")
            except Exception:
                 new_pass = input(f" 2. App Password Baru (terlihat) [{current_pass_display}]: ").strip()
                 if new_pass: settings['app_password'] = new_pass

            new_val = input(f" 3. Server IMAP [{settings['imap_server']}]: ").strip();
            if new_val: settings['imap_server'] = new_val
            while True:
                new_val_str = input(f" 4. Interval [{settings['check_interval_seconds']}s], min 5: ").strip()
                if not new_val_str: break
                try:
                    new_interval = int(new_val_str)
                    if new_interval >= 5: settings['check_interval_seconds'] = new_interval; break
                    else: print(f"   {RED}Minimal 5 detik.{RESET}")
                except ValueError: print(f"   {RED}Masukkan angka.{RESET}")
            new_val = input(f" 5. Keyword Target [{settings['target_keyword']}]: ").strip();
            if new_val: settings['target_keyword'] = new_val
            new_val = input(f" 6. Keyword Trigger [{settings['trigger_keyword']}]: ").strip();
            if new_val: settings['trigger_keyword'] = new_val

            # Binance
            print(f"\n{CYAN}--- Binance ---{RESET}")
            if not BINANCE_AVAILABLE: print(f"{YELLOW}   (Library Binance tidak ada){RESET}")
            new_val = input(f" 7. API Key [{api_key_disp}]: ").strip();
            if new_val: settings['binance_api_key'] = new_val
            try:
                current_secret_display = '[Hidden]' if settings['binance_api_secret'] else '[Kosong]'
                new_secret = getpass.getpass(f" 8. API Secret Baru [{current_secret_display}] (ketik u/ ubah): ").strip()
                if new_secret: settings['binance_api_secret'] = new_secret; print(f"   {GREEN}Secret Key diperbarui.{RESET}")
            except Exception:
                 new_secret = input(f" 8. API Secret Baru (terlihat) [{current_secret_display}]: ").strip()
                 if new_secret: settings['binance_api_secret'] = new_secret

            new_val = input(f" 9. Trading Pair [{settings['trading_pair']}]: ").strip().upper();
            if new_val: settings['trading_pair'] = new_val
            while True:
                 new_val_str = input(f"10. Buy Quote Qty [{settings['buy_quote_quantity']}], > 0: ").strip()
                 if not new_val_str: break
                 try:
                     new_qty = float(new_val_str)
                     if new_qty > 0: settings['buy_quote_quantity'] = new_qty; break
                     else: print(f"   {RED}Harus > 0.{RESET}")
                 except ValueError: print(f"   {RED}Masukkan angka.{RESET}")
            while True:
                 new_val_str = input(f"11. Sell Base Qty [{settings['sell_base_quantity']}], >= 0: ").strip()
                 if not new_val_str: break
                 try:
                     new_qty = float(new_val_str)
                     if new_qty >= 0: settings['sell_base_quantity'] = new_qty; break
                     else: print(f"   {RED}Harus >= 0.{RESET}")
                 except ValueError: print(f"   {RED}Masukkan angka.{RESET}")
            while True:
                 exec_prompt = f"{GREEN}Aktif{RESET}" if settings['execute_binance_orders'] else f"{RED}Nonaktif{RESET}"
                 new_val_str = input(f"12. Eksekusi Order? (y/n) [{exec_prompt}]: ").lower().strip()
                 if not new_val_str: break
                 if new_val_str == 'y': settings['execute_binance_orders'] = True; print(f"   {GREEN}Eksekusi Diaktifkan.{RESET}"); break
                 elif new_val_str == 'n': settings['execute_binance_orders'] = False; print(f"   {RED}Eksekusi Dinonaktifkan.{RESET}"); break
                 else: print(f"   {RED}Masukkan 'y' atau 'n'.{RESET}")

            save_settings(settings)
            input(f"\n{GREEN}{BOLD}✅ Pengaturan disimpan!{RESET} Tekan Enter...")

        elif choice == 'k':
            break
        else:
            print(f"{RED}[ERROR] Pilihan tidak valid.{RESET}")
            time.sleep(1)

# --- Fungsi Menu Utama ---
def main_menu():
    global ROCKET_ART
    settings = load_settings() # Load awal
    startup_animation() # Panggil animasi startup sekali

    while True:
        settings = load_settings() # Re-load setting
        rows, cols = get_terminal_size()
        layout_width = min(cols - 4, 100) # Batasi lebar layout
        left_col_width = layout_width // 2 - 3

        wipe_effect(rows, cols, char=random.choice(['*', '#', '+', '.']), delay=0.003) # Wipe acak
        clear_screen()
        print("\n" * 2) # Margin atas

        # --- Konten Kolom Kiri (Menu Utama) ---
        left_content = []
        left_content.append(f"{BOLD}{BRIGHT_MAGENTA}╔══════════════════════════════╗{RESET}")
        left_content.append(f"{BOLD}{BRIGHT_MAGENTA}║   Exora AI Email Listener    ║{RESET}")
        left_content.append(f"{BOLD}{BRIGHT_MAGENTA}╚══════════════════════════════╝{RESET}")
        left_content.append("")
        left_content.append(f"{BOLD}{WHITE}Menu Utama:{RESET}")

        exec_mode_label = f" {BOLD}& Binance{RESET}" if settings.get("execute_binance_orders") else ""
        left_content.append(f" {BRIGHT_GREEN}{BOLD}1.{RESET} Mulai Listener (Email{exec_mode_label})")
        left_content.append(f" {BRIGHT_CYAN}{BOLD}2.{RESET} Buka Pengaturan")
        left_content.append(f" {BRIGHT_YELLOW}{BOLD}3.{RESET} Keluar Aplikasi")
        left_content.append("-" * left_col_width)

        # Status Cepat
        left_content.append(f"{BOLD}{WHITE}Status Cepat:{RESET}")
        email_ok = bool(settings['email_address']) and bool(settings['app_password'])
        email_status = status_ok if email_ok else status_nok
        left_content.append(f" Email Config : [{email_status}]")

        exec_on = settings.get("execute_binance_orders", False)
        exec_status_label = f"{GREEN}AKTIF{RESET}" if exec_on else f"{YELLOW}NONAKTIF{RESET}"
        lib_status = status_ok if BINANCE_AVAILABLE else status_nok + f" {RED}Missing!{RESET}"
        left_content.append(f" Binance Lib  : [{lib_status}] | Eksekusi: [{exec_status_label}]")

        if exec_on and BINANCE_AVAILABLE:
            api_ok = bool(settings['binance_api_key']) and bool(settings['binance_api_secret'])
            pair_ok = bool(settings['trading_pair'])
            qty_ok = settings['buy_quote_quantity'] > 0 and settings['sell_base_quantity'] >= 0
            bin_status = status_ok if api_ok and pair_ok and qty_ok else status_warn
            left_content.append(f" Binance Cfg  : [{bin_status}] (API/Pair/Qty)")
        elif exec_on and not BINANCE_AVAILABLE:
             left_content.append(f" Binance Cfg  : [{status_nok}] {RED}(Library Error){RESET}")


        left_content.append("-" * left_col_width)
        # Pad left content biar tingginya sama dengan ROCKET_ART
        while len(left_content) < len(ROCKET_ART):
             left_content.append("")

        # --- Cetak Layout ---
        # print_centered(f"{REVERSE}{WHITE}{BOLD} MENU UTAMA {RESET}", layout_width) # Optional Title Bar
        draw_two_column_layout(left_content, ROCKET_ART, total_width=layout_width, left_width=left_col_width, padding=4)
        print_separator(char="=", length=layout_width, color=BRIGHT_MAGENTA)

        choice = input(f"{BOLD}{WHITE}Masukkan pilihan Anda (1/2/3): {RESET}").strip()

        if choice == '1':
            # Validasi sebelum mulai (disederhanakan)
            valid = True
            if not email_ok:
                 print(f"\n{status_nok} {RED}Email/App Password belum diatur!{RESET}"); valid = False
            if exec_on and not BINANCE_AVAILABLE:
                 print(f"\n{status_nok} {RED}Eksekusi aktif tapi library Binance error!{RESET}"); valid = False
            if exec_on and BINANCE_AVAILABLE and not (api_ok and pair_ok and qty_ok):
                 print(f"\n{status_warn} {YELLOW}Eksekusi aktif tapi konfigurasi Binance belum lengkap/valid (API/Pair/Qty).{RESET}")
                 # Tidak set valid = False, mungkin user mau lanjut tanpa eksekusi?

            if valid:
                start_listening(settings)
                # Kembali ke menu setelah listener berhenti
                print(f"\n{YELLOW}[INFO] Kembali ke Menu Utama...{RESET}")
                input(f"{DIM}Tekan Enter untuk melanjutkan...{RESET}")
            else:
                print(f"\n{YELLOW}Silakan perbaiki di menu 'Pengaturan'.{RESET}")
                input(f"{DIM}Tekan Enter untuk kembali...{RESET}")

        elif choice == '2':
            show_settings(settings)
        elif choice == '3':
            clear_screen()
            print("\n" * (rows // 3))
            print_centered(f"{BRIGHT_CYAN}{BOLD}👋 Terima kasih! Sampai jumpa! 👋{RESET}", cols)
            print("\n" * 5)
            sys.exit(0)
        else:
            print(f"\n{RED}{BOLD} Pilihan tidak valid! Masukkan 1, 2, atau 3.{RESET}")
            time.sleep(1.5)


# --- Entry Point ---
if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        # Seharusnya sudah ditangani signal handler
        print(f"\n{YELLOW}{BOLD}Program dihentikan paksa.{RESET}")
        sys.exit(1)
    except Exception as e:
        # Tangkap error tak terduga di level tertinggi
        clear_screen()
        print(f"\n{BOLD}{RED}╔════════════════════════════╗{RESET}")
        print(f"{BOLD}{RED}║      💥 ERROR KRITIS 💥     ║{RESET}")
        print(f"{BOLD}{RED}╚════════════════════════════╝{RESET}")
        print(f"\n{RED}Terjadi error yang tidak dapat dipulihkan:{RESET}")
        traceback.print_exc()
        print(f"\n{RED}Pesan Error: {e}{RESET}")
        print("\nProgram akan ditutup.")
        # input("Tekan Enter untuk keluar...") # Optional: biar user bisa baca error
        sys.exit(1)
