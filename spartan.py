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
# (Definisi warna tetap sama, kita akan gunakan secara strategis)
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"
BLINK = "\033[5m"
REVERSE = "\033[7m"
HIDDEN = "\033[8m"
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

# --- Karakter "Animasi" & Status ---
# MODIF: Spinner gaya Spartan (lebih sederhana)
spinner_chars = ['|', '/', '-', '\\']
# spinner_chars = ['🛡️ ', '⚔️ '] # Emoji (butuh font & terminal support)
loading_bar_char = '█'
wipe_char = '░' # Karakter wipe lebih halus
status_ok = f"{BRIGHT_GREEN}✔{RESET}"
status_nok = f"{BRIGHT_RED}✘{RESET}"
status_warn = f"{BRIGHT_YELLOW}⚠{RESET}"
status_wait = f"{BRIGHT_BLUE}⏳{RESET}"
status_info = f"{BRIGHT_CYAN}ℹ{RESET}" # BARU: Status info

# --- ASCII Art (Contoh Spartan) ---
# MODIF: Mengganti ROCKET_ART dengan sesuatu yang lebih 'Spartan'
# Cari di Google: "spartan helmet ascii art", "shield ascii art"
SPARTAN_HELMET_ART = [
    "    .--.                  ",
    "   /    \\                 ",
    "  |      |                ",
    "  \\ ---- / .-=-.          ",
    "  /`    ' /   /           ",
    " /       |   /            ",
    " \\      )   /             ",
    "  '.   (   /              ",
    "    `--.| /               ",
    "       //`--.             ",
    "      ||  `'/             ",
    "      ||    '.            ",
    "      ||      \\           ",
    "     /__\\      \\          ",
    "    '.--.       |         ",
    "     \\__/       |         ",
    "      ||        ;         ",
    "      ||       /          ",
    "      ||      /           ",
    "      \\ \\    /            ",
    "       `.`--'             ",
    "         `--'             "
]

SETTINGS_GEAR_ART = [ # BARU: Art sederhana untuk halaman settings
    "      .--.",
    "     /.-. \\",
    "     \\'-' /",
    "      '--'",
    "      /..\\",
    "     // L \\\\",
    "    '/ | \\'",
    "   ///=|= \\\\\\",
    "  '/ || || \\'",
    " // / || \\ \\\\",
    "'.'/######\\'.'",
    "`. /------\\ .'",
    " / /        \\ \\",
    "(_/          \\_)",
]

# --- Fungsi Utilitas Tampilan ---
def clear_screen():
    """Membersihkan layar terminal."""
    os.system('cls' if os.name == 'nt' else 'clear')

def get_terminal_size():
    """Mendapatkan ukuran terminal (kolom, baris)."""
    try:
        columns, rows = os.get_terminal_size(0)
    except (OSError, AttributeError, TypeError, NameError): # MODIF: Tangkap TypeError juga
        try:
            rows, columns = os.popen('stty size', 'r').read().split()
            rows, columns = int(rows), int(columns)
        except ValueError:
            rows, columns = 24, 80 # Default fallback
    return rows, columns

def print_centered(text, width, color=RESET, char=" "):
    """Mencetak teks di tengah dengan padding karakter."""
    # MODIF: Handle ANSI codes in length calculation (simple version)
    def visible_len(s):
        import re
        return len(re.sub(r'\033\[[0-9;]*m', '', s))

    text_len = visible_len(text)
    if text_len >= width:
        print(f"{color}{text}{RESET}") # Hindari padding negatif
        return

    padding_total = width - text_len
    padding_left = padding_total // 2
    padding_right = padding_total - padding_left
    print(f"{color}{char * padding_left}{text}{char * padding_right}{RESET}")

def print_separator(char="─", length=80, color=DIM + WHITE + RESET):
    """Mencetak garis pemisah."""
    # MODIF: Pastikan panjang tidak negatif
    print(f"{color}{char * max(0, length)}{RESET}")

def wipe_effect(rows, cols, char=wipe_char, delay=0.003, color=DIM):
    """Efek wipe sederhana yang lebih cepat."""
    # MODIF: Wipe dari atas dan bawah, sedikit lebih cepat
    mid_row = rows // 2
    for r in range(mid_row):
        line = char * cols
        sys.stdout.write(f"\033[{r + 1};1H{color}{line}{RESET}") # Dari atas
        if rows - r > mid_row: # Hindari overwrite baris tengah jika ganjil
             sys.stdout.write(f"\033[{rows - r};1H{color}{line}{RESET}") # Dari bawah
        sys.stdout.flush()
        time.sleep(delay)
    # Wipe bagian tengah (jika ganjil)
    if rows % 2 != 0:
        sys.stdout.write(f"\033[{mid_row + 1};1H{color}{char * cols}{RESET}")
        sys.stdout.flush()
        time.sleep(delay)

    # Hapus wipe (langsung timpa dengan clear_screen setelahnya)
    # Tidak perlu menghapus secara manual karena akan di-clear

def draw_two_column_layout(left_lines, right_lines, total_width, left_width, padding=4):
    """ Mencetak dua kolom bersebelahan, lebih robust terhadap ANSI."""
    # MODIF: Simple ANSI stripping for length calculation
    def visible_len(s):
        import re
        return len(re.sub(r'\033\[[0-9;]*m', '', s))

    right_width = total_width - left_width - padding
    max_lines = max(len(left_lines), len(right_lines))
    spacer = " " * padding

    for i in range(max_lines):
        left_part = left_lines[i].rstrip() if i < len(left_lines) else ""
        right_part = right_lines[i].rstrip() if i < len(right_lines) else ""

        # Pad left part based on visible length
        visible_left_len = visible_len(left_part)
        left_padding = " " * max(0, left_width - visible_left_len)
        left_padded = left_part + left_padding

        # Right part usually doesn't need strict padding for ASCII art
        right_padded = right_part #.ljust(right_width) # Usually not needed

        print(f"{left_padded}{spacer}{right_padded}")


def startup_animation():
    """Animasi startup ala Spartan."""
    clear_screen()
    rows, cols = get_terminal_size()
    # MODIF: Tampilan lebih minimalis
    brand = f"🛡️ {BOLD}{WHITE}Exora AI Listener - System Check{RESET} 🛡️"
    stages = ['/', '-', '\\', '|', '/', '-', '\\', '|'] # Spinner
    messages = [
        "Initializing Core Systems...",
        "Loading Modules...",
        "Verifying Dependencies...",
        "Establishing Secure Link...", # Tema spartan
        "Calibrating Sensors...",
        "Checking Network...",
        "Final Preparations...",
        "SYSTEM READY."
    ]

    print("\n" * (rows // 3)) # Posisi agak ke bawah
    print_centered(brand, cols, BOLD + WHITE)
    print("\n")

    # Progress bar sederhana
    bar_width = min(40, cols - 20) # Lebar bar
    for i, msg in enumerate(messages):
        progress_percent = int(((i + 1) / len(messages)) * 100)
        filled_width = int(bar_width * (i + 1) // len(messages))
        bar = f"{BRIGHT_GREEN}{loading_bar_char * filled_width}{DIM}{loading_bar_char * (bar_width - filled_width)}{RESET}"
        status_line = f"{BLUE}{stages[i % len(stages)]}{RESET} {msg.ljust(30)} [{bar}] {progress_percent}%"
        print_centered(status_line + " " * 10, cols) # Padding extra u/ clear

        time.sleep(random.uniform(0.15, 0.3))
        if i < len(messages) - 1:
             sys.stdout.write("\033[F") # Pindah cursor ke atas
             sys.stdout.flush()

    print_centered(f"{status_ok} {BOLD}{BRIGHT_GREEN}Initialization Complete!{RESET}", cols)
    time.sleep(0.8)
    # wipe_effect(rows, cols, char=random.choice(['.', ' ']), delay=0.001) # Efek wipe cepat/halus
    clear_screen() # Langsung clear saja

# --- Fungsi Penanganan Sinyal (Ctrl+C) ---
# (Tetap sama, hanya pesan output sedikit disesuaikan)
def signal_handler(sig, frame):
    global running
    print(f"\n{BRIGHT_YELLOW}{BOLD}🛑 INTERRUPT DETECTED!{RESET} {YELLOW}Shutting down gracefully...{RESET}")
    running = False
    # Beri waktu sedikit untuk loop utama berhenti
    time.sleep(0.5)
    print(f"\n{RED}{BOLD}⚔️ Commander out. Farewell! ⚔️{RESET}")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# --- Fungsi Konfigurasi ---
# (Load & Save Settings tetap sama, tambahkan feedback visual minimal)
def load_settings():
    settings = DEFAULT_SETTINGS.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_settings = json.load(f)
                for key in DEFAULT_SETTINGS:
                    if key in loaded_settings:
                        settings[key] = loaded_settings[key]
                # Validasi (sama)
                settings["check_interval_seconds"] = max(5, int(settings.get("check_interval_seconds", 10)))
                settings["buy_quote_quantity"] = max(0.0, float(settings.get("buy_quote_quantity", 11.0)))
                settings["sell_base_quantity"] = max(0.0, float(settings.get("sell_base_quantity", 0.0)))
                settings["execute_binance_orders"] = bool(settings.get("execute_binance_orders", False))
                # Simpan ulang jika ada koreksi/default baru, tanpa notif
                current_settings_json = json.dumps({k:settings[k] for k in DEFAULT_SETTINGS}, sort_keys=True)
                loaded_settings_json = json.dumps({k:loaded_settings[k] for k in DEFAULT_SETTINGS if k in loaded_settings}, sort_keys=True)
                if current_settings_json != loaded_settings_json:
                     save_settings(settings, silent=True)
        except json.JSONDecodeError:
            print(f"{status_nok} {RED}Config file '{CONFIG_FILE}' corrupted. Using defaults & saving.{RESET}")
            save_settings(settings) # Save default on error
        except Exception as e:
            print(f"{status_nok} {RED}Failed to load config: {e}{RESET}")
            print(f"{status_warn} {YELLOW}Using temporary default settings.{RESET}")
    else:
        # print(f"{status_info} {BLUE}Config file '{CONFIG_FILE}' not found. Creating with defaults.{RESET}") # BARU: Info
        save_settings(settings) # Create default if not exist
    return settings

def save_settings(settings, silent=False):
    try:
        settings_to_save = {key: settings[key] for key in DEFAULT_SETTINGS if key in settings}
        settings_to_save['check_interval_seconds'] = int(settings_to_save.get('check_interval_seconds', 10))
        settings_to_save['buy_quote_quantity'] = float(settings_to_save.get('buy_quote_quantity', 11.0))
        settings_to_save['sell_base_quantity'] = float(settings_to_save.get('sell_base_quantity', 0.0))
        settings_to_save['execute_binance_orders'] = bool(settings_to_save.get('execute_binance_orders', False))
        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings_to_save, f, indent=4, sort_keys=True)
        if not silent:
            print(f"{status_ok} {GREEN}Settings saved to '{CONFIG_FILE}'{RESET}")
    except Exception as e:
        print(f"{status_nok} {RED}Failed to save config: {e}{RESET}")


# --- Fungsi Utilitas Lain ---
# (decode_mime_words, get_text_from_email tetap sama fungsinya)
def get_timestamp():
    return datetime.datetime.now().strftime("%H:%M:%S") # MODIF: Format lebih pendek

def decode_mime_words(s):
    # Fungsi ini krusial dan biarkan seperti adanya
    if not s: return ""
    try:
        decoded_parts = decode_header(s)
        result = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                try: result.append(part.decode(encoding or 'utf-8', errors='replace'))
                except (LookupError, ValueError): result.append(part.decode('utf-8', errors='replace'))
            else: result.append(part)
        return "".join(result)
    except Exception: # Tangkap error decode header yang aneh
        return str(s) if isinstance(s, str) else repr(s) # Fallback


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
                except Exception:
                    # print(f"{status_warn} {YELLOW}Cannot decode email part (text/plain){RESET}") # Optional: less verbose
                    pass
    else:
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                text_content = payload.decode(charset, errors='replace')
            except Exception:
                 # print(f"{status_warn} {YELLOW}Cannot decode email body (non-multipart){RESET}") # Optional: less verbose
                 pass
    return text_content.lower()

def trigger_beep(action):
    # MODIF: Output lebih ringkas
    action_color = BRIGHT_GREEN if action == "buy" else BRIGHT_RED if action == "sell" else BRIGHT_MAGENTA
    print(f"{action_color}{BOLD}🔊 ACTION TRIGGERED: {action.upper()}!{RESET}")
    try:
        # Coba 'tput bel' dulu sbg alternatif cross-platform paling dasar
        subprocess.run(["tput", "bel"], check=False, capture_output=True, timeout=1)
    except FileNotFoundError:
        print("\a", end='') # Fallback ke system bell standar
        sys.stdout.flush()
    except Exception: # Tangkap error lain dari tput
         print("\a", end='') # Fallback ke system bell standar
         sys.stdout.flush()

# --- Fungsi Eksekusi Binance ---
# (get_binance_client & execute_binance_order tetap sama fungsinya)
# (Tambahkan visualisasi koneksi/eksekusi yg lebih bersih)
def get_binance_client(settings):
    if not BINANCE_AVAILABLE: return None
    if not settings.get('binance_api_key') or not settings.get('binance_api_secret'):
        print(f"{status_nok} {RED}{BOLD}Binance API Key/Secret Missing!{RESET}")
        return None
    try:
        print(f"{status_wait} {CYAN}Connecting to Binance API...{RESET}", end='\r')
        client = Client(settings['binance_api_key'], settings['binance_api_secret'])
        # MODIF: Gunakan get_account() untuk test koneksi & dapatkan info singkat
        acc_info = client.get_account()
        can_trade = acc_info.get('canTrade', False)
        status_trade = f"{GREEN}Enabled{RESET}" if can_trade else f"{RED}Disabled{RESET}"
        # Hapus pesan tunggu
        sys.stdout.write("\r" + " " * 50 + "\r")
        sys.stdout.flush()
        print(f"{status_ok} {BRIGHT_GREEN}{BOLD}Binance API Connected!{RESET} (Trading: {status_trade})")
        if not can_trade:
             print(f"{status_warn} {YELLOW}Account trading is disabled on Binance side.{RESET}")
        return client
    except BinanceAPIException as e:
        sys.stdout.write("\r" + " " * 50 + "\r") # Hapus pesan tunggu
        print(f"{status_nok} {RED}{BOLD}Binance Connect/Auth Failed:{RESET} {e.status_code} - {e.message}")
        return None
    except Exception as e:
        sys.stdout.write("\r" + " " * 50 + "\r") # Hapus pesan tunggu
        print(f"{status_nok} {RED}{BOLD}Failed to create Binance client:{RESET} {e}")
        return None

def execute_binance_order(client, settings, side):
    if not client:
        print(f"{status_warn} {YELLOW}Execution cancelled, Binance client not valid.{RESET}")
        return False
    if not settings.get("execute_binance_orders", False):
        # Pesan ini seharusnya tidak muncul krn dicek di start_listening, tapi sbg safeguard
        print(f"{status_warn} {YELLOW}Order execution disabled. Skipping.{RESET}")
        return False

    pair = settings.get('trading_pair', '').upper()
    if not pair:
        print(f"{status_nok} {RED}{BOLD}Trading pair not set!{RESET}")
        return False

    order_details = {}
    action_desc = ""
    side_color = BRIGHT_GREEN if side == Client.SIDE_BUY else BRIGHT_RED
    side_icon = "🛒" if side == Client.SIDE_BUY else "💰"
    rows, cols = get_terminal_size() # MODIF: Untuk separator

    try:
        print(print_separator(char="-", length=cols // 2, color=side_color)) # MODIF: Separator
        print(f"{side_color}{BOLD}{side_icon} Attempting {side} Order ({pair}){RESET}{side_color} {side_icon}{RESET}")

        if side == Client.SIDE_BUY:
            quote_qty = settings.get('buy_quote_quantity', 0.0)
            if quote_qty <= 0:
                 print(f"{status_nok} {RED}Buy Quantity (Quote) must be > 0.{RESET}")
                 return False
            order_details = {'symbol': pair, 'side': Client.SIDE_BUY, 'type': Client.ORDER_TYPE_MARKET, 'quoteOrderQty': quote_qty}
            action_desc = f"MARKET BUY ~{quote_qty} Quote Asset for {pair}"

        elif side == Client.SIDE_SELL:
            base_qty = settings.get('sell_base_quantity', 0.0)
            if base_qty <= 0:
                 print(f"{status_nok} {RED}Sell Quantity (Base) must be > 0.{RESET}")
                 return False
            order_details = {'symbol': pair, 'side': Client.SIDE_SELL, 'type': Client.ORDER_TYPE_MARKET, 'quantity': base_qty}
            action_desc = f"MARKET SELL {base_qty} Base Asset from {pair}"
        else:
            print(f"{status_nok} {RED}Invalid order side: {side}{RESET}")
            return False

        print(f"{CYAN}{status_wait} Executing: {BOLD}{action_desc}{RESET}{CYAN}...{RESET}")
        # ---- EXECUTION ----
        order_result = client.create_order(**order_details)
        # -------------------

        print(f"{side_color}{BOLD}✅ ORDER EXECUTED SUCCESSFULLY!{RESET}")
        print(f"{DIM}---------------- Detail ----------------{RESET}")
        print(f"{DIM}  ID    : {order_result.get('orderId')}{RESET}")
        print(f"{DIM}  Symbol: {order_result.get('symbol')}{RESET}")
        print(f"{DIM}  Side  : {order_result.get('side')}{RESET}")
        print(f"{DIM}  Status: {order_result.get('status')}{RESET}")
        if order_result.get('fills'):
            total_qty = sum(float(f['qty']) for f in order_result['fills'])
            total_quote_qty = sum(float(f['commission']) if f['commissionAsset'] == 'BNB' else float(f['cummulativeQuoteQty']) for f in order_result['fills']) # MODIF: Use cummulativeQuoteQty
            avg_price = total_quote_qty / total_qty if total_qty else 0
            print(f"{DIM}  Filled: {total_qty:.8f} (Base){RESET}")
            print(f"{DIM}  Avg Pr: {avg_price:.8f} (Quote/Base){RESET}")
            print(f"{DIM}  Cost  : {total_quote_qty:.4f} (Quote){RESET}")
        print(f"{DIM}--------------------------------------{RESET}")
        return True

    except BinanceAPIException as e:
        print(f"{status_nok} {RED}{BOLD}BINANCE API ERROR:{RESET} {e.status_code} - {e.message}")
        if e.code == -2010: print(f"{RED}      -> Insufficient balance?{RESET}")
        elif e.code == -1121: print(f"{RED}      -> Invalid trading pair '{pair}'?{RESET}")
        elif e.code == -1013 or 'MIN_NOTIONAL' in str(e.message): print(f"{RED}      -> Order size too small (check MIN_NOTIONAL)?{RESET}")
        elif e.code == -1111 or 'LOT_SIZE' in str(e.message): print(f"{RED}      -> Quantity doesn't match LOT_SIZE filter?{RESET}")
        return False
    except BinanceOrderException as e:
        print(f"{status_nok} {RED}{BOLD}BINANCE ORDER ERROR:{RESET} {e.status_code} - {e.message}")
        return False
    except Exception as e:
        print(f"{status_nok} {RED}{BOLD}ERROR DURING BINANCE EXECUTION:{RESET}")
        traceback.print_exc()
        return False
    finally:
         print(print_separator(char="-", length=cols // 2, color=side_color)) # MODIF: Separator
         print("") # Add newline after order process


# --- Fungsi Pemrosesan Email ---
def process_email(mail, email_id, settings, binance_client):
    global running
    if not running: return

    target_keyword_lower = settings['target_keyword'].lower()
    trigger_keyword_lower = settings['trigger_keyword'].lower()
    email_id_str = email_id.decode('utf-8')
    ts = get_timestamp()
    rows, cols = get_terminal_size() # MODIF: Untuk separator

    try:
        # MODIF: Output lebih ringkas dan terstruktur
        print(print_separator(char="=", length=cols // 2, color=MAGENTA))
        print(f"{MAGENTA}📧 {BOLD}Processing Email ID: {email_id_str}{RESET} [{ts}]")
        print(f"{DIM}   Fetching email data...{RESET}", end='\r')
        status, data = mail.fetch(email_id, "(RFC822)")
        sys.stdout.write("\r" + " " * 40 + "\r") # Hapus pesan fetch
        if status != 'OK':
            print(f"{status_nok} {RED}Failed to fetch email ID {email_id_str}: {status}{RESET}")
            return

        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        subject = decode_mime_words(msg["Subject"])
        sender = decode_mime_words(msg["From"])

        print(f"   {CYAN}From  :{RESET} {sender[:min(len(sender), cols - 15)]}") # Limit sender length
        print(f"   {CYAN}Subj  :{RESET} {subject[:min(len(subject), cols - 15)]}") # Limit subject length

        body = get_text_from_email(msg)
        # Handle potential None from get_text_from_email
        full_content = (subject.lower() if subject else "") + " " + (body if body else "")

        if target_keyword_lower in full_content:
            print(f"   {status_ok} {GREEN}Target Keyword Found ('{settings['target_keyword']}')")
            try:
                target_index = full_content.find(target_keyword_lower)
                # Cari trigger *setelah* target
                trigger_index = full_content.find(trigger_keyword_lower, target_index + len(target_keyword_lower))

                if trigger_index != -1:
                    start_word_index = trigger_index + len(trigger_keyword_lower)
                    text_after_trigger = full_content[start_word_index:].lstrip()
                    words_after_trigger = text_after_trigger.split(maxsplit=1)

                    if words_after_trigger:
                        action_word = words_after_trigger[0].strip('.,!?:;()[]{}').lower()
                        action_color = BRIGHT_GREEN if action_word == "buy" else BRIGHT_RED if action_word == "sell" else BRIGHT_YELLOW
                        print(f"   {action_color}🎯 {BOLD}Trigger Found!{RESET} ('{settings['trigger_keyword']}') -> Action: {BOLD}{action_word.upper()}{RESET}")

                        # --- Trigger Aksi ---
                        if action_word == "buy" or action_word == "sell":
                            trigger_beep(action_word)
                            if settings.get("execute_binance_orders"):
                                if binance_client:
                                    # Eksekusi order dipindahkan ke luar try-except parsing ini
                                    # agar error parsing tidak menghentikan eksekusi jika logic benar
                                    execute_binance_order(binance_client, settings, getattr(Client, f"SIDE_{action_word.upper()}"))
                                else:
                                    print(f"   {status_warn} {YELLOW}Binance client not ready. Cannot execute.{RESET}")
                            # MODIF: Pesan dinonaktifkan hanya jika aksi valid
                            elif action_word in ["buy", "sell"]:
                                 print(f"   {DIM}(Binance execution is disabled){RESET}")
                        else:
                            print(f"   {status_warn} {YELLOW}Action '{action_word}' unknown (not 'buy'/'sell'). No market action.{RESET}")
                    else:
                        print(f"   {status_warn} {YELLOW}No words found after trigger keyword '{settings['trigger_keyword']}'.{RESET}")
                else:
                     print(f"   {status_info} {BLUE}Trigger '{settings['trigger_keyword']}' not found AFTER target '{settings['target_keyword']}'.{RESET}") # MODIF: Jadi info
            except Exception as e:
                 print(f"   {status_nok} {RED}Error parsing after trigger: {e}{RESET}")
        else:
            print(f"   {status_info} {BLUE}Target keyword '{settings['target_keyword']}' not found.{RESET}")

        # Tandai email sebagai 'Seen' (silent on success)
        try:
            mail.store(email_id, '+FLAGS', '\\Seen')
        except Exception as e:
            print(f"{status_nok} {RED}Failed to mark email {email_id_str} as 'Seen': {e}{RESET}")

        # print(print_separator(char="=", length=cols // 2, color=MAGENTA)) # Footer tidak perlu

    except Exception as e:
        print(f"{status_nok} {RED}{BOLD}Failed processing email ID {email_id_str}:{RESET}")
        traceback.print_exc()
        print(print_separator(char="=", length=cols // 2, color=RED))


# --- Fungsi Listening Utama ---
def start_listening(settings):
    global running, spinner_chars, spinner_index
    running = True
    mail = None
    binance_client = None
    wait_time = 30 # Detik retry koneksi
    connection_attempts = 0
    spinner_index = 0
    last_email_check_time = time.time() # MODIF: Untuk timer display

    rows, cols = get_terminal_size()
    clear_screen()
    print("\n" * 1) # Sedikit margin atas

    # --- Header Listener ---
    # MODIF: Header lebih Spartan
    print(print_separator(char="═", length=cols - 2, color=BRIGHT_WHITE))
    mode = "⚔️ LISTENING MODE ⚔️"
    exec_status = f"{GREEN}BINANCE ACTIVE{RESET}" if settings.get("execute_binance_orders") else f"{YELLOW}EMAIL ONLY{RESET}"
    title = f"{BOLD}{WHITE}{mode}{RESET} [{exec_status}]"
    print_centered(title, cols - 2, char=" ", color=WHITE) # Center with space padding
    print(print_separator(char="═", length=cols - 2, color=BRIGHT_WHITE))
    print("") # Spasi

    # --- Setup Binance ---
    if settings.get("execute_binance_orders"):
        if not BINANCE_AVAILABLE:
             print(f"{status_nok} {RED}{BOLD}FATAL: 'python-binance' library is missing!{RESET}")
             running = False; return
        print(f"{BOLD}{CYAN}--- Binance Setup ---{RESET}")
        binance_client = get_binance_client(settings)
        if not binance_client:
            print(f"{status_nok} {RED}{BOLD}FATAL: Failed to connect Binance.{RESET}")
            # Beri opsi lanjut tanpa binance atau keluar
            print(f"{YELLOW}Disabling Binance execution for this session.{RESET}")
            settings['execute_binance_orders'] = False # Nonaktifkan paksa
            time.sleep(3)
        else:
            print(f"{status_ok} {GREEN}Binance Client Ready!")
        print(print_separator(char="-", length=cols // 2, color=CYAN)) # Separator
    else:
        print(f"{status_info} {YELLOW}Binance execution is disabled in settings.{RESET}")
        print(print_separator(char="-", length=cols // 2, color=YELLOW)) # Separator

    # --- Setup Email ---
    print(f"{BOLD}{BLUE}--- Email Listener Setup ---{RESET}")
    email_display = settings['email_address'] or f"{RED}Not Set!{RESET}"
    print(f"{status_info} {BLUE}Account : {email_display}{RESET}")
    print(f"{status_info} {BLUE}Server  : {settings['imap_server']}{RESET}")
    print(f"{status_info} {BLUE}Interval: {settings['check_interval_seconds']}s{RESET}")
    print(print_separator(char="-", length=cols // 2, color=BLUE)) # Separator
    time.sleep(1)

    print(f"{BOLD}{WHITE}Starting Watch... (Press Ctrl+C to Stop){RESET}")
    print(print_separator(char="─", length=cols-2, color=DIM))

    # --- Loop Utama Listener ---
    while running:
        try:
            # --- Koneksi IMAP ---
            if not mail or mail.state != 'SELECTED':
                connection_attempts += 1
                status_line = f"{status_wait} {CYAN}[{connection_attempts}] Connecting to IMAP ({settings['imap_server']})... ".ljust(cols - 2)
                print(status_line, end='\r')
                try:
                    mail = imaplib.IMAP4_SSL(settings['imap_server'])
                    sys.stdout.write("\r" + " " * (cols - 2) + "\r") # Clear line
                    print(f"{status_ok} {GREEN}IMAP Server Connected. Logging in...{RESET}", end='\r')
                    mail.login(settings['email_address'], settings['app_password'])
                    sys.stdout.write("\r" + " " * (cols - 2) + "\r") # Clear line
                    print(f"{status_ok} {GREEN}Email Login OK ({settings['email_address']}). Selecting INBOX...{RESET}", end='\r')
                    mail.select("inbox")
                    sys.stdout.write("\r" + " " * (cols - 2) + "\r") # Clear line
                    print(f"{status_ok} {GREEN}Entered INBOX. Listening active...{RESET}")
                    print(print_separator(char="─", length=cols-2, color=DIM)) # Separator setelah konek
                    connection_attempts = 0 # Reset counter on success
                    last_email_check_time = time.time() # Reset timer
                except (imaplib.IMAP4.error, imaplib.IMAP4.abort, socket.error, OSError) as imap_err:
                    sys.stdout.write("\r" + " " * (cols - 2) + "\r") # Clear line
                    print(f"{status_nok} {RED}{BOLD}IMAP Connect/Login Failed:{RESET} {imap_err} ")
                    if "authentication failed" in str(imap_err).lower() or "invalid credentials" in str(imap_err).lower():
                         print(f"{RED}{BOLD}   -> CHECK EMAIL & APP PASSWORD! Is IMAP enabled?{RESET}")
                         running = False; return # Stop if auth failed
                    else:
                         print(f"{YELLOW}   -> Retrying in {wait_time} seconds...{RESET}")
                         for _ in range(wait_time): # Sleep with interrupt check
                             if not running: break
                             time.sleep(1)
                         continue # Retry connection loop

            # --- Loop Cek Email (Inner) ---
            while running:
                # Check IMAP health silently
                try:
                    status, _ = mail.noop()
                    if status != 'OK':
                        print(f"\n{status_warn} {YELLOW}IMAP NOOP failed ({status}). Reconnecting...{RESET}")
                        break # Break inner loop to reconnect
                except (imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError, socket.error):
                     # MODIF: Handle socket error too
                     print(f"\n{status_warn} {YELLOW}IMAP Connection lost. Reconnecting...{RESET}")
                     break # Break inner loop to reconnect

                # --- Cek Email Baru (UNSEEN) ---
                status, messages = mail.search(None, '(UNSEEN)')
                if status != 'OK':
                     print(f"\n{status_nok} {RED}Failed to search emails: {status}. Reconnecting...{RESET}")
                     break # Break inner loop to reconnect

                email_ids = messages[0].split()
                if email_ids:
                    # Clear the waiting message line before processing
                    sys.stdout.write("\r" + " " * (cols - 2) + "\r")
                    sys.stdout.flush()

                    print(f"\n{BRIGHT_GREEN}{BOLD}🔥 Found {len(email_ids)} New Email(s)! Processing... 🔥{RESET}")
                    # print(print_separator(char="-", length=cols-2, color=GREEN)) # Optional separator

                    for email_id in email_ids:
                        if not running: break
                        process_email(mail, email_id, settings, binance_client)
                    if not running: break

                    print(print_separator(char="─", length=cols-2, color=DIM)) # Separator after processing batch
                    print(f"{status_ok} {GREEN}Finished processing batch. Resuming watch...{RESET}")
                    last_email_check_time = time.time() # Reset timer after processing

                else:
                    # --- Tidak ada email baru, tampilkan status tunggu ---
                    wait_interval = settings['check_interval_seconds']
                    spinner = spinner_chars[spinner_index % len(spinner_chars)]
                    spinner_index += 1
                    elapsed_time = int(time.time() - last_email_check_time)
                    wait_message = f"{DIM}{spinner}{RESET} {WHITE}Watching... No new signals. Next check in {wait_interval - elapsed_time}s".ljust(cols - 2)
                    # Pastikan tidak melebihi lebar kolom
                    print(wait_message[:cols-2], end='\r')

                    # Tidur per detik agar responsif Ctrl+C & update timer
                    sleep_needed = True
                    for i in range(wait_interval):
                         if not running:
                             sleep_needed = False; break
                         # Update timer display every second
                         elapsed_time = int(time.time() - last_email_check_time)
                         remaining = max(0, wait_interval - elapsed_time)
                         # Jangan update spinner terlalu cepat, cukup timer saja
                         wait_message = f"{DIM}{spinner}{RESET} {WHITE}Watching... No new signals. Next check in {remaining}s".ljust(cols - 2)
                         print(wait_message[:cols-2], end='\r')
                         if remaining <= 0: # Jika waktu sudah habis
                            sleep_needed = False; break
                         time.sleep(1) # Sleep 1 detik

                    if not running: break
                    last_email_check_time = time.time() # Reset timer for next cycle

            # --- Keluar dari loop inner (Reconnect needed) ---
            if mail and mail.state == 'SELECTED':
                try: mail.close()
                except Exception: pass
            if mail and mail.state == 'AUTH':
                try: mail.logout() # Logout jika masih auth state
                except Exception: pass
            mail = None # Force reconnect

        # --- Exception Handling Luar (Network/Major Errors) ---
        except (ConnectionError, OSError, socket.error, socket.gaierror) as net_err:
             sys.stdout.write("\r" + " " * (cols - 2) + "\r") # Clear line
             print(f"\n{status_nok} {RED}{BOLD}Network Connection Error:{RESET} {net_err}")
             print(f"{YELLOW}   -> Check internet. Retrying in {wait_time} seconds...{RESET}")
             for _ in range(wait_time): # Sleep with interrupt check
                 if not running: break
                 time.sleep(1)
        except Exception as e:
            sys.stdout.write("\r" + " " * (cols - 2) + "\r") # Clear line
            print(f"\n{status_nok} {RED}{BOLD}UNEXPECTED ERROR IN MAIN LOOP:{RESET}")
            traceback.print_exc()
            print(f"{YELLOW}   -> Attempting recovery in {wait_time} seconds...{RESET}")
            for _ in range(wait_time): # Sleep with interrupt check
                 if not running: break
                 time.sleep(1)
        finally:
            # Ensure mail object is cleared for reconnect attempt
            if mail:
                try:
                    if mail.state != 'LOGOUT': mail.logout()
                except Exception: pass
            mail = None
            if running: time.sleep(1) # Small delay before main loop retry

    # --- Listener Stopped ---
    sys.stdout.write("\r" + " " * (cols - 2) + "\r") # Clear last status line
    print(f"\n{BRIGHT_YELLOW}{BOLD}🛑 Listener has been stopped.{RESET}")
    print(print_separator(char="═", length=cols - 2, color=YELLOW))


# --- Fungsi Menu Pengaturan ---
def show_settings(settings):
    global SETTINGS_GEAR_ART # BARU: Gunakan art baru
    rows, cols = get_terminal_size()
    # MODIF: Lebar layout lebih dinamis, min 60, max 110
    layout_width = max(60, min(cols - 4, 110))
    left_col_width = layout_width * 2 // 3 - 4 # Lebar kolom kiri 2/3
    right_col_width = layout_width - left_col_width - 4

    while True:
        # wipe_effect(rows, cols, char='.', delay=0.001) # Optional wipe
        clear_screen()
        print("\n" * 1) # Margin atas

        # --- Header Pengaturan ---
        print(print_separator(char="*", length=layout_width, color=BRIGHT_CYAN))
        print_centered(f"⚙️ {BOLD}SYSTEM CONFIGURATION{RESET} ⚙️", layout_width, color=BRIGHT_CYAN, char=" ")
        print(print_separator(char="*", length=layout_width, color=BRIGHT_CYAN))

        # --- Konten Kolom Kiri ---
        left_content = []
        # left_content.append(f"{BOLD}{WHITE}--- Parameters ---{RESET}")
        # left_content.append("-" * left_col_width)
        left_content.append(f"{BOLD}{BLUE}EMAIL CONFIGURATION:{RESET}")
        email_disp = settings['email_address'] or f'{YELLOW}[Not Set]{RESET}'
        # MODIF: Password display
        pwd_disp = f"{DIM}[Hidden]{RESET}" if settings['app_password'] else f'{YELLOW}[Not Set]{RESET}'
        left_content.append(f" {CYAN}1.{RESET} Address : {email_disp}")
        left_content.append(f" {CYAN}2.{RESET} App Pass: {pwd_disp}")
        left_content.append(f" {CYAN}3.{RESET} IMAP Srv: {settings['imap_server']}")
        left_content.append(f" {CYAN}4.{RESET} Interval: {settings['check_interval_seconds']}s {DIM}(min:5){RESET}")
        left_content.append(f" {CYAN}5.{RESET} TargetKW: {BOLD}{settings['target_keyword']}{RESET}")
        left_content.append(f" {CYAN}6.{RESET} TriggerKW: {BOLD}{settings['trigger_keyword']}{RESET}")
        left_content.append("")
        left_content.append(f"{BOLD}{MAGENTA}BINANCE CONFIGURATION:{RESET}")
        lib_status = f"{GREEN}Loaded{RESET}" if BINANCE_AVAILABLE else f"{RED}MISSING!{RESET}"
        left_content.append(f"    Library : {lib_status}")
        api_key_disp = settings['binance_api_key'][:4] + '...' + settings['binance_api_key'][-4:] if len(settings['binance_api_key']) > 8 else (f"{YELLOW}[Not Set]{RESET}" if not settings['binance_api_key'] else f"{DIM}[Set]{RESET}")
        api_sec_disp = f"{DIM}[Hidden]{RESET}" if settings['binance_api_secret'] else f'{YELLOW}[Not Set]{RESET}'
        left_content.append(f" {MAGENTA}7.{RESET} API Key : {api_key_disp}")
        left_content.append(f" {MAGENTA}8.{RESET} API Sec : {api_sec_disp}")
        pair_disp = settings['trading_pair'] or f'{YELLOW}[Not Set]{RESET}'
        left_content.append(f" {MAGENTA}9.{RESET} Pair    : {BOLD}{pair_disp}{RESET}")
        left_content.append(f"{MAGENTA}10.{RESET} Buy Qty : {settings['buy_quote_quantity']} {DIM}(Quote>0){RESET}")
        left_content.append(f"{MAGENTA}11.{RESET} Sell Qty: {settings['sell_base_quantity']} {DIM}(Base>=0){RESET}")
        exec_status = f"{BRIGHT_GREEN}{BOLD}ACTIVE{RESET}" if settings['execute_binance_orders'] else f"{RED}INACTIVE{RESET}"
        left_content.append(f"{MAGENTA}12.{RESET} Execute : {exec_status}")
        left_content.append("-" * left_col_width)
        left_content.append(f" {WHITE}{BOLD}E{RESET} - Edit Settings")
        left_content.append(f" {WHITE}{BOLD}K{RESET} - Back to Main Menu")
        left_content.append("-" * left_col_width)

        # --- Konten Kolom Kanan (ASCII Art) ---
        # Pad art biar tingginya mirip left_content
        right_content = SETTINGS_GEAR_ART[:] # Salin list
        while len(right_content) < len(left_content):
            right_content.append(" " * right_col_width) # Pad dengan spasi

        # --- Cetak Layout ---
        draw_two_column_layout(left_content, right_content, total_width=layout_width, left_width=left_col_width, padding=4)
        print_separator(char="*", length=layout_width, color=BRIGHT_CYAN) # Footer

        choice = input(f"{BOLD}{WHITE}Select Option (E/K): {RESET}").lower().strip()

        if choice == 'e':
            print(f"\n{BOLD}{MAGENTA}--- Edit Settings ---{RESET} {DIM}(Leave blank to skip){RESET}")
            # --- Proses Edit (Sama, tapi prompt lebih jelas) ---

            print(f"\n{BOLD}{BLUE}--- Email ---{RESET}")
            new_val = input(f" 1. Email Address [{settings['email_address']}]: ").strip()
            if new_val: settings['email_address'] = new_val
            try:
                current_pass_display = '[Set]' if settings['app_password'] else '[Empty]'
                new_pass = getpass.getpass(f" 2. New App Password [{current_pass_display}] (Type to change): ").strip()
                if new_pass:
                     settings['app_password'] = new_pass
                     print(f"   {GREEN}App Password Updated.{RESET}")
                else:
                    print(f"   {DIM}Password not changed.{RESET}") # Beri feedback jika tidak diubah
            except Exception: # Fallback jika getpass error
                 new_pass = input(f" 2. New App Password (visible) [{current_pass_display}]: ").strip()
                 if new_pass: settings['app_password'] = new_pass

            new_val = input(f" 3. IMAP Server [{settings['imap_server']}]: ").strip()
            if new_val: settings['imap_server'] = new_val
            while True:
                new_val_str = input(f" 4. Check Interval (sec) [{settings['check_interval_seconds']}], min 5: ").strip()
                if not new_val_str: break
                try:
                    new_interval = int(new_val_str)
                    if new_interval >= 5: settings['check_interval_seconds'] = new_interval; break
                    else: print(f"   {RED}Minimum interval is 5 seconds.{RESET}")
                except ValueError: print(f"   {RED}Invalid number. Please enter digits only.{RESET}")
            new_val = input(f" 5. Target Keyword [{settings['target_keyword']}]: ").strip()
            if new_val: settings['target_keyword'] = new_val
            new_val = input(f" 6. Trigger Keyword [{settings['trigger_keyword']}]: ").strip()
            if new_val: settings['trigger_keyword'] = new_val

            print(f"\n{BOLD}{MAGENTA}--- Binance ---{RESET}")
            if not BINANCE_AVAILABLE: print(f"{YELLOW}   (Note: Binance library is not installed/found){RESET}")
            current_key_display = '[Set]' if settings['binance_api_key'] else '[Empty]'
            new_val = input(f" 7. API Key [{current_key_display}]: ").strip()
            if new_val: settings['binance_api_key'] = new_val
            try:
                current_secret_display = '[Set]' if settings['binance_api_secret'] else '[Empty]'
                new_secret = getpass.getpass(f" 8. New API Secret [{current_secret_display}] (Type to change): ").strip()
                if new_secret:
                    settings['binance_api_secret'] = new_secret
                    print(f"   {GREEN}API Secret Updated.{RESET}")
                else:
                    print(f"   {DIM}Secret not changed.{RESET}")
            except Exception:
                 new_secret = input(f" 8. New API Secret (visible) [{current_secret_display}]: ").strip()
                 if new_secret: settings['binance_api_secret'] = new_secret

            new_val = input(f" 9. Trading Pair (e.g., BTCUSDT) [{settings['trading_pair']}]: ").strip().upper()
            if new_val: settings['trading_pair'] = new_val
            while True:
                 new_val_str = input(f"10. Buy Quote Quantity [{settings['buy_quote_quantity']}], must be > 0: ").strip()
                 if not new_val_str: break
                 try:
                     new_qty = float(new_val_str)
                     if new_qty > 0: settings['buy_quote_quantity'] = new_qty; break
                     else: print(f"   {RED}Quantity must be greater than 0.{RESET}")
                 except ValueError: print(f"   {RED}Invalid number.{RESET}")
            while True:
                 new_val_str = input(f"11. Sell Base Quantity [{settings['sell_base_quantity']}], must be >= 0: ").strip()
                 if not new_val_str: break
                 try:
                     new_qty = float(new_val_str)
                     if new_qty >= 0: settings['sell_base_quantity'] = new_qty; break
                     else: print(f"   {RED}Quantity must be 0 or greater.{RESET}")
                 except ValueError: print(f"   {RED}Invalid number.{RESET}")
            while True:
                 exec_prompt = f"{GREEN}Y{RESET}" if settings['execute_binance_orders'] else f"{RED}N{RESET}"
                 new_val_str = input(f"12. Enable Binance Execution? (Y/N) [{exec_prompt}]: ").lower().strip()
                 if not new_val_str: break
                 if new_val_str == 'y':
                     settings['execute_binance_orders'] = True; print(f"   {GREEN}Binance Execution ENABLED.{RESET}"); break
                 elif new_val_str == 'n':
                     settings['execute_binance_orders'] = False; print(f"   {RED}Binance Execution DISABLED.{RESET}"); break
                 else: print(f"   {RED}Invalid input. Please enter 'Y' or 'N'.{RESET}")

            save_settings(settings)
            input(f"\n{status_ok} {GREEN}{BOLD}Settings Saved!{RESET} Press Enter to return...")

        elif choice == 'k':
            break
        else:
            print(f"{RED}{BOLD}Invalid Option.{RESET} Please choose 'E' or 'K'.")
            time.sleep(1.5)

# --- Fungsi Menu Utama ---
def main_menu():
    global SPARTAN_HELMET_ART # MODIF: Gunakan art Spartan
    settings = load_settings() # Load awal
    startup_animation() # Panggil animasi startup sekali

    while True:
        settings = load_settings() # Re-load settings setiap kembali ke menu
        rows, cols = get_terminal_size()
        # MODIF: Lebar layout lebih dinamis
        layout_width = max(70, min(cols - 4, 100))
        left_col_width = layout_width * 2 // 5 # Lebar kolom kiri 2/5
        right_col_width = layout_width - left_col_width - 4

        # wipe_effect(rows, cols, char=random.choice(['.', ' ']), delay=0.002) # Optional wipe
        clear_screen()
        print("\n" * 1) # Margin atas

        # --- Header Menu Utama ---
        # MODIF: Header ala Spartan
        print(print_separator(char="*", length=layout_width, color=BRIGHT_MAGENTA))
        print_centered(f"🛡️ {BOLD}{WHITE} EXORA AI LISTENER - COMMAND CENTER {RESET} 🛡️", layout_width, color=BRIGHT_WHITE, char=" ")
        print(print_separator(char="*", length=layout_width, color=BRIGHT_MAGENTA))

        # --- Konten Kolom Kiri (Menu Utama) ---
        left_content = []
        # left_content.append(f"{BOLD}{WHITE} Main Menu {RESET}")
        # left_content.append("-" * left_col_width)
        left_content.append(f"{BOLD}{WHITE}SELECT ACTION:{RESET}")
        exec_mode_label = f" {BOLD}& Binance{RESET}" if settings.get("execute_binance_orders") else ""
        left_content.append(f" {BRIGHT_GREEN}1.{RESET} {BOLD}Start Watch{RESET} (Email{exec_mode_label})")
        left_content.append(f" {BRIGHT_CYAN}2.{RESET} {BOLD}Configure{RESET} System")
        left_content.append(f" {RED}3.{RESET} {BOLD}Exit{RESET} Program")
        left_content.append("-" * left_col_width)

        # Status Cepat
        left_content.append(f"{BOLD}{WHITE}QUICK STATUS:{RESET}")
        email_ok = bool(settings['email_address']) and bool(settings['app_password'])
        email_status = status_ok if email_ok else status_nok + f" {RED}Incomplete{RESET}"
        left_content.append(f" Email Setup : {email_status}")

        exec_on = settings.get("execute_binance_orders", False)
        exec_status_label = f"{GREEN}ACTIVE{RESET}" if exec_on else f"{YELLOW}INACTIVE{RESET}"
        lib_status = status_ok if BINANCE_AVAILABLE else status_nok + f" {RED}Missing!{RESET}"
        left_content.append(f" Binance Lib : {lib_status} | Exec: {exec_status_label}")

        if exec_on:
            if BINANCE_AVAILABLE:
                api_ok = bool(settings['binance_api_key']) and bool(settings['binance_api_secret'])
                pair_ok = bool(settings['trading_pair'])
                # MODIF: Cek qty sedikit berbeda (Buy > 0, Sell >= 0)
                buy_qty_ok = settings['buy_quote_quantity'] > 0
                sell_qty_ok = settings['sell_base_quantity'] >= 0
                qty_ok = buy_qty_ok # Perlu buy qty > 0 minimal
                bin_status = status_ok if api_ok and pair_ok and qty_ok else status_warn + f" {YELLOW}Check{RESET}"
                details = []
                if not api_ok: details.append("API")
                if not pair_ok: details.append("Pair")
                if not qty_ok: details.append("Qty")
                detail_str = f" ({'/'.join(details)})" if details else ""
                left_content.append(f" Binance Cfg : {bin_status}{detail_str}")
            else:
                 left_content.append(f" Binance Cfg : {status_nok} {RED}(Lib Error){RESET}")
        left_content.append("-" * left_col_width)

        # Pad left content biar tingginya sama dengan ASCII Art
        # MODIF: Gunakan art spartan
        target_art = SPARTAN_HELMET_ART
        while len(left_content) < len(target_art):
             left_content.append("")
        # Pangkas art jika terlalu tinggi
        target_art_display = target_art[:len(left_content)]


        # --- Cetak Layout ---
        draw_two_column_layout(left_content, target_art_display, total_width=layout_width, left_width=left_col_width, padding=4)
        print_separator(char="*", length=layout_width, color=BRIGHT_MAGENTA) # Footer

        choice = input(f"{BOLD}{WHITE}Enter your command (1/2/3): {RESET}").strip()

        if choice == '1':
            # Validasi sebelum mulai
            valid_start = True
            print("") # Newline before messages
            if not email_ok:
                 print(f"{status_nok} {RED}Email Address or App Password is not set!{RESET}"); valid_start = False
            if exec_on:
                if not BINANCE_AVAILABLE:
                    print(f"{status_nok} {RED}Binance execution enabled, but library is missing!{RESET}"); valid_start = False
                elif not (api_ok and pair_ok and qty_ok):
                    print(f"{status_warn} {YELLOW}Binance execution enabled, but config is incomplete/invalid (API/Pair/Qty).{RESET}")
                    # Tetap bisa start, tapi user diwarning
                    # valid_start = False # Uncomment jika mau stop jika config binance tak lengkap

            if valid_start:
                start_listening(settings)
                # Kembali ke menu setelah listener berhenti
                print(f"\n{status_info} {YELLOW}Returned to Command Center.{RESET}")
                input(f"{DIM}Press Enter to continue...{RESET}")
            else:
                print(f"\n{YELLOW}Please correct the issues in {BOLD}'Configure System'{RESET} first.")
                input(f"{DIM}Press Enter to return to menu...{RESET}")

        elif choice == '2':
            show_settings(settings)
        elif choice == '3':
            clear_screen()
            print("\n" * (rows // 3))
            print_centered(f"{BRIGHT_CYAN}{BOLD}⚔️ Dismissed! Until next time. ⚔️{RESET}", cols)
            print("\n" * 5)
            sys.exit(0)
        else:
            print(f"\n{RED}{BOLD} Invalid Command! {RESET}Please enter 1, 2, or 3.")
            time.sleep(1.5)


# --- Entry Point ---
if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        # Signal handler sudah menangani ini, tapi sebagai fallback
        print(f"\n{YELLOW}{BOLD}Program force-stopped.{RESET}")
        sys.exit(1)
    except Exception as e:
        # Tangkap error tak terduga di level tertinggi
        clear_screen()
        print(f"\n{BOLD}{BG_RED}{WHITE}╔═══════════════════════════════════════╗{RESET}")
        print(f"{BOLD}{BG_RED}{WHITE}║        *** CRITICAL SYSTEM ERROR ***        ║{RESET}")
        print(f"{BOLD}{BG_RED}{WHITE}╚═══════════════════════════════════════╝{RESET}")
        print(f"\n{BRIGHT_RED}An unrecoverable error occurred:{RESET}")
        traceback.print_exc() # Cetak traceback lengkap
        # print(f"\n{RED}Error Message: {e}{RESET}") # Pesan error singkat
        print(f"\n{RED}The program must terminate.{RESET}")
        # input("Press Enter to exit...") # Biarkan user baca error
        sys.exit(1)
