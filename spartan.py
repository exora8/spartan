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
import re # Untuk strip ANSI codes
import math # Untuk pulsing effect

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
        SIDE_BUY = 'BUY'; SIDE_SELL = 'SELL'; ORDER_TYPE_MARKET = 'MARKET'

# --- Konfigurasi & Variabel Global ---
CONFIG_FILE = "config.json"
DEFAULT_SETTINGS = {
    # ... (Default settings tetap sama)
    "email_address": "", "app_password": "", "imap_server": "imap.gmail.com",
    "check_interval_seconds": 10, "target_keyword": "Exora AI", "trigger_keyword": "order",
    "binance_api_key": "", "binance_api_secret": "", "trading_pair": "BTCUSDT",
    "buy_quote_quantity": 11.0, "sell_base_quantity": 0.0, "execute_binance_orders": False
}
running = True

# --- Kode Warna ANSI & Style ---
RESET = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"; ITALIC = "\033[3m"
UNDERLINE = "\033[4m"; BLINK = "\033[5m"; REVERSE = "\033[7m"; HIDDEN = "\033[8m"
# Warna Dasar
RED = "\033[31m"; GREEN = "\033[32m"; YELLOW = "\033[33m"; BLUE = "\033[34m"
MAGENTA = "\033[35m"; CYAN = "\033[36m"; WHITE = "\033[37m"
# Warna Cerah (Bright)
BRIGHT_RED = "\033[91m"; BRIGHT_GREEN = "\033[92m"; BRIGHT_YELLOW = "\033[93m"
BRIGHT_BLUE = "\033[94m"; BRIGHT_MAGENTA = "\033[95m"; BRIGHT_CYAN = "\033[96m"
BRIGHT_WHITE = "\033[97m"

# --- Karakter "Animasi" & Status ---
spinner_chars = ['🌑', '🌒', '🌓', '🌔', '🌕', '🌖', '🌗', '🌘'] # Moon phases
# spinner_chars = ['◢', '◣', '◤', '◥'] # Arrows
loading_bar_char = '■'
wipe_char = '█'
status_ok = f"{GREEN}✔{RESET}"
status_nok = f"{RED}✘{RESET}"
status_warn = f"{YELLOW}⚠{RESET}"
status_wait = f"{BLUE}⏳{RESET}"
status_info = f"{CYAN}ℹ{RESET}"
status_rocket = f"{MAGENTA}🚀{RESET}"

# --- ASCII Art (Coba yang lebih simpel & tahan banting) ---
# Pastikan tidak ada spasi ekstra di akhir baris art
MAIN_ART = [
    r"      _______________",
    r"     / ____ \__   __\",
    r"    / / __ \ \ | |",
    r"   / / /_/ / / | |",
    r"  / ____ / /  |_|",
    r" /_/   \_\/ ",
    r" ",
    r"   EXORA AI LISTENER",
    r" ",
]

SETTINGS_ART = [
    r"  _______ _______ ",
    r" |__   __|__   __|",
    r"    | |     | |   ",
    r"    | |     | |   ",
    r"    | |     | |   ",
    r"    |_|     |_|   ",
    r" ",
    r"    PENGATURAN",
    r" ",
]


# --- Fungsi Utilitas Tampilan ---
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def get_terminal_size():
    try: columns, rows = os.get_terminal_size(0)
    except Exception: # Fallback luas
        try:
            rows, columns = map(int, os.popen('stty size', 'r').read().split())
        except ValueError: rows, columns = 24, 80 # Default absolut
    return rows, columns

def len_no_ansi(text):
    """Menghitung panjang string tanpa karakter ANSI escape codes."""
    # Pola regex untuk ANSI escape codes
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return len(ansi_escape.sub('', text))

def print_centered(text, width, color=RESET):
    visible_len = len_no_ansi(text)
    padding = max(0, (width - visible_len) // 2)
    print(f"{' ' * padding}{color}{text}{RESET}")

def print_separator(char="─", length=80, color=DIM + WHITE + RESET):
    print(f"{color}{char * length}{RESET}")

def wipe_effect(rows, cols, char=wipe_char, delay=0.001, color=DIM):
    """Efek wipe cepat."""
    mid_row = rows // 2
    for r in range(mid_row):
        line = char * cols
        sys.stdout.write(f"\033[{r + 1};1H{color}{line}{RESET}")
        sys.stdout.write(f"\033[{rows - r};1H{color}{line}{RESET}")
        sys.stdout.flush()
        time.sleep(delay)
    # Clear sisa tengah jika ganjil
    if rows % 2 != 0:
         sys.stdout.write(f"\033[{mid_row + 1};1H{color}{line}{RESET}")
         sys.stdout.flush()
         time.sleep(delay)
    # Balik (optional, clear screen biasanya cukup)
    # for r in range(mid_row, -1, -1):
    #      line = " " * cols
    #      sys.stdout.write(f"\033[{r + 1};1H{line}")
    #      sys.stdout.write(f"\033[{rows - r};1H{line}")
    #      sys.stdout.flush()
    #      time.sleep(delay)

def draw_layout(left_lines, right_lines, title=""):
    """Menggambar layout, bisa 1 atau 2 kolom tergantung lebar terminal."""
    rows, cols = get_terminal_size()
    layout_width = cols - 4 # Lebar konten utama (margin 2 kiri, 2 kanan)
    min_two_col_width = 70 # Lebar minimum untuk layout 2 kolom

    # --- Vertical Padding ---
    # Hitung tinggi konten (pilih yg lebih tinggi antara kiri/kanan) + header/footer
    content_height = max(len(left_lines), len(right_lines))
    total_ui_height = content_height + 4 # Perkiraan: 1 title, 1 separator, 1 prompt, 1 blank
    v_padding = max(0, (rows - total_ui_height) // 2)
    print("\n" * v_padding)

    # --- Title ---
    if title:
        print_centered(f"{REVERSE}{BOLD}{WHITE} {title} {RESET}", layout_width)
        print_separator(char="=", length=layout_width, color=BRIGHT_CYAN)

    # --- Determine Layout (1 atau 2 Kolom) ---
    if cols >= min_two_col_width and right_lines:
        # --- Dua Kolom ---
        left_width = (layout_width * 2) // 3 - 2 # Kolom kiri lebih lebar
        right_width = layout_width - left_width - 4 # 4 spasi pemisah
        spacer = " " * 4
        max_lines = max(len(left_lines), len(right_lines))

        for i in range(max_lines):
            # Ambil teks, pastikan ada isinya jika indeks valid
            left_part = left_lines[i].rstrip() if i < len(left_lines) else ""
            right_part = right_lines[i].rstrip() if i < len(right_lines) else ""

            # Hitung panjang visual untuk padding kiri
            left_visible_len = len_no_ansi(left_part)
            left_padding = " " * max(0, left_width - left_visible_len)

            # Gabungkan dengan padding
            padded_left = f"{left_part}{left_padding}"

            # Pad kanan (opsional, biasanya art sudah pas)
            # right_visible_len = len_no_ansi(right_part)
            # right_padding = " " * max(0, right_width - right_visible_len)
            # padded_right = f"{right_part}{right_padding}"

            # Cetak dengan margin kiri
            print(f"  {padded_left}{spacer}{right_part}") # Margin 2 spasi

    else:
        # --- Satu Kolom ---
        # Cetak Art dulu jika ada (di tengah)
        if right_lines:
            art_width = max(len_no_ansi(line) for line in right_lines) if right_lines else 0
            art_padding = max(0, (layout_width - art_width) // 2)
            for line in right_lines:
                print(f"  {' ' * art_padding}{line}") # Margin 2 spasi
            print_separator(char="-", length=layout_width, color=DIM)

        # Cetak Konten Kiri
        for line in left_lines:
            print(f"  {line}") # Margin 2 spasi

    # --- Footer Separator ---
    print_separator(char="=", length=layout_width, color=BRIGHT_CYAN)

def startup_animation():
    rows, cols = get_terminal_size()
    clear_screen()
    brand_chars = list("🚀 Exora AI Listener 🚀")
    display_line = [" "] * len(brand_chars)

    print("\n" * (rows // 3)) # Posisi agak ke bawah

    # Animasi ketik judul
    temp_line = ""
    for i, char in enumerate(brand_chars):
        display_line[i] = char
        temp_line = "".join(display_line)
        print_centered(f"{BOLD}{MAGENTA}{temp_line}{RESET}", cols)
        time.sleep(0.05)
        if i < len(brand_chars) - 1:
            sys.stdout.write("\033[F") # Cursor up
            sys.stdout.flush()

    # Loading bar
    print("\n")
    bar_width = 30
    for i in range(bar_width + 1):
        percent = int((i / bar_width) * 100)
        bar = f"{GREEN}{loading_bar_char * i}{DIM}{loading_bar_char * (bar_width - i)}{RESET}"
        status_msg = f"Inisialisasi... {percent}%"
        print_centered(f"[{bar}] {status_msg}", cols)
        time.sleep(0.03)
        if i < bar_width:
            sys.stdout.write("\033[F") # Cursor up
            sys.stdout.flush()

    print_centered(f"{GREEN}{BOLD}✅ Sistem Siap!{RESET}", cols)
    time.sleep(0.8)
    wipe_effect(rows, cols, char=random.choice(['*', '#', '+', '.']), delay=0.001) # Wipe cepat


# --- Fungsi Penanganan Sinyal ---
# (Tetap sama)
def signal_handler(sig, frame):
    global running
    rows, cols = get_terminal_size()
    clear_screen()
    print("\n" * (rows // 2 - 1))
    print_centered(f"{BRIGHT_YELLOW}{BOLD}🛑 Ctrl+C! Menghentikan listener... 🛑{RESET}", cols)
    running = False
    time.sleep(1)
    clear_screen()
    print("\n" * (rows // 2 - 1))
    print_centered(f"{RED}{BOLD}👋 Sampai jumpa! 👋{RESET}", cols)
    print("\n" * (rows // 2))
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# --- Fungsi Konfigurasi ---
# (Load & Save Settings tetap sama, mungkin tambahkan print status)
def load_settings():
    settings = DEFAULT_SETTINGS.copy()
    # ... (logika load & validasi tetap sama seperti sebelumnya) ...
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_settings = json.load(f)
                for key in DEFAULT_SETTINGS:
                    if key in loaded_settings: settings[key] = loaded_settings[key]
                # Validasi
                settings["check_interval_seconds"] = max(5, int(settings.get("check_interval_seconds", 10)))
                settings["buy_quote_quantity"] = max(0.0, float(settings.get("buy_quote_quantity", 11.0)))
                settings["sell_base_quantity"] = max(0.0, float(settings.get("sell_base_quantity", 0.0)))
                settings["execute_binance_orders"] = bool(settings.get("execute_binance_orders", False))
                save_settings(settings, silent=True) # Save koreksi
        except Exception as e:
            print(f"{RED}[ERROR] Load config gagal: {e}{RESET}")
    else:
        save_settings(settings) # Buat baru
    return settings

def save_settings(settings, silent=False):
    try:
        settings_to_save = {key: settings[key] for key in DEFAULT_SETTINGS if key in settings}
        # ... (validasi tipe data sebelum save) ...
        settings_to_save['check_interval_seconds'] = int(settings_to_save.get('check_interval_seconds', 10))
        settings_to_save['buy_quote_quantity'] = float(settings_to_save.get('buy_quote_quantity', 11.0))
        settings_to_save['sell_base_quantity'] = float(settings_to_save.get('sell_base_quantity', 0.0))
        settings_to_save['execute_binance_orders'] = bool(settings_to_save.get('execute_binance_orders', False))
        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings_to_save, f, indent=4, sort_keys=True)
        if not silent:
            print(f"{status_ok} {GREEN}{BOLD}Pengaturan disimpan!{RESET}")
    except Exception as e:
        print(f"{status_nok} {RED}Gagal menyimpan konfigurasi: {e}{RESET}")


# --- Fungsi Utilitas Lain ---
# (decode_mime_words, get_text_from_email, trigger_beep tetap sama fungsinya)
def get_timestamp(): return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
    # ... (logika get text tetap sama) ...
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type(); cd = str(part.get("Content-Disposition"))
            if ctype == "text/plain" and "attachment" not in cd.lower():
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    text_content += payload.decode(charset, errors='replace') + "\n"
                except Exception: pass # Ignore decoding errors for parts
    else:
        ctype = msg.get_content_type()
        if ctype == "text/plain":
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                text_content = payload.decode(charset, errors='replace')
            except Exception: pass
    return text_content.lower()

def trigger_beep(action):
    # (Fungsi beep tetap sama, mungkin sederhanakan outputnya)
    try:
        action_upper = action.upper()
        action_color = GREEN if action == "buy" else RED if action == "sell" else MAGENTA
        print(f"{action_color}{BOLD}🔊 BEEP: {action_upper}!{RESET}")
        # ... (logika subprocess beep / fallback '\a' tetap sama) ...
        try:
            if action == "buy": subprocess.run(["beep", "-f", "1000", "-l", "200", "-r", "2"], check=True, capture_output=True, text=True, timeout=1)
            elif action == "sell": subprocess.run(["beep", "-f", "600", "-l", "400"], check=True, capture_output=True, text=True, timeout=1)
            else: print("\a", end='')
        except Exception: print("\a", end=''); sys.stdout.flush()
    except Exception: pass


# --- Fungsi Eksekusi Binance ---
# (get_binance_client & execute_binance_order tetap sama fungsinya)
# (Pastikan outputnya jelas dan pakai status icon)
def get_binance_client(settings):
    if not BINANCE_AVAILABLE: return None
    if not settings.get('binance_api_key') or not settings.get('binance_api_secret'):
        print(f"{status_nok} {RED}{BOLD}API Key/Secret Binance kosong!{RESET}")
        return None
    try:
        print(f"{status_wait} {CYAN}Menghubungkan ke Binance API...{RESET}", end='\r')
        client = Client(settings['binance_api_key'], settings['binance_api_secret'])
        client.ping()
        print(f"{status_ok} {GREEN}{BOLD}Koneksi Binance API Berhasil!                {RESET}")
        return client
    except BinanceAPIException as e:
        print(f"{status_nok} {RED}{BOLD}Koneksi/Auth Binance Gagal:{RESET} {e.status_code} - {e.message}")
        return None
    except Exception as e:
        print(f"{status_nok} {RED}{BOLD}Gagal membuat Binance client:{RESET} {e}")
        return None

def execute_binance_order(client, settings, side):
    if not client: print(f"{status_warn} {YELLOW}Eksekusi dibatalkan, client Binance tidak valid.{RESET}"); return False
    if not settings.get("execute_binance_orders", False): print(f"{status_info} {DIM}Eksekusi order dinonaktifkan.{RESET}"); return False
    pair = settings.get('trading_pair', '').upper();
    if not pair: print(f"{status_nok} {RED}{BOLD}Trading pair kosong!{RESET}"); return False

    order_details = {}; action_desc = ""; side_color = BRIGHT_GREEN if side == Client.SIDE_BUY else BRIGHT_RED
    side_icon = "🛒" if side == Client.SIDE_BUY else "💰"

    try:
        print(f"\n{side_color}--- {BOLD}PERSIAPAN ORDER {side} ({pair}){RESET} {side_color}---{RESET}")
        # ... (logika penentuan detail order BUY/SELL tetap sama) ...
        if side == Client.SIDE_BUY:
            quote_qty = settings.get('buy_quote_quantity', 0.0)
            if quote_qty <= 0: print(f"{status_nok} {RED}Buy Qty <= 0.{RESET}"); return False
            order_details = {'symbol': pair, 'side': side, 'type': Client.ORDER_TYPE_MARKET, 'quoteOrderQty': quote_qty}
            action_desc = f"{side_icon} {BOLD}MARKET BUY{RESET} senilai {quote_qty} (Quote) untuk {pair}"
        elif side == Client.SIDE_SELL:
            base_qty = settings.get('sell_base_quantity', 0.0)
            if base_qty <= 0: print(f"{status_warn} {YELLOW}Sell Qty <= 0. Order dilewati.{RESET}"); return False
            order_details = {'symbol': pair, 'side': side, 'type': Client.ORDER_TYPE_MARKET, 'quantity': base_qty}
            action_desc = f"{side_icon} {BOLD}MARKET SELL{RESET} sejumlah {base_qty} (Base) dari {pair}"
        else: print(f"{status_nok} {RED}Sisi order tidak valid: {side}{RESET}"); return False

        print(f"{CYAN}{status_wait} Mencoba eksekusi: {action_desc}...{RESET}")
        order_result = client.create_order(**order_details) # EKSEKUSI
        print(f"{side_color}{BOLD}✅ ORDER BERHASIL DI EKSEKUSI!{RESET}")
        # ... (Print detail order result tetap sama) ...
        print(f"{DIM}-------------------------------------------{RESET}")
        print(f"{DIM}  ID: {order_result.get('orderId')}, Status: {order_result.get('status')}{RESET}")
        if order_result.get('fills'):
             total_qty = sum(float(f['qty']) for f in order_result['fills'])
             total_quote = sum(float(f['cummulativeQuoteQty']) for f in order_result['fills'])
             avg_price = total_quote / total_qty if total_qty else 0
             print(f"{DIM}  Avg Price: {avg_price:.8f}, Filled: {total_qty:.8f} Base, Cost: {total_quote:.4f} Quote{RESET}")
        print(f"{DIM}-------------------------------------------{RESET}")
        return True
    except BinanceAPIException as e:
        print(f"{status_nok} {RED}{BOLD}BINANCE API ERROR:{RESET} {e.status_code} - {e.message}")
        # ... (pesan error spesifik) ...
        return False
    except BinanceOrderException as e:
        print(f"{status_nok} {RED}{BOLD}BINANCE ORDER ERROR:{RESET} {e.status_code} - {e.message}")
        return False
    except Exception as e:
        print(f"{status_nok} {RED}{BOLD}ERROR EKSEKUSI BINANCE:{RESET}"); traceback.print_exc()
        return False
    finally: print(f"{side_color}--- {BOLD}SELESAI PROSES ORDER {side}{RESET} {side_color}---{RESET}\n")


# --- Fungsi Pemrosesan Email ---
def process_email(mail, email_id, settings, binance_client):
    global running; if not running: return
    target_kw = settings['target_keyword'].lower(); trigger_kw = settings['trigger_keyword'].lower()
    email_id_str = email_id.decode('utf-8'); ts = get_timestamp()

    try:
        print(f"\n{MAGENTA}📧 {BOLD}Proses Email ID: {email_id_str} [{ts}]{RESET}{MAGENTA} ==={RESET}")
        status, data = mail.fetch(email_id, "(RFC822)");
        if status != 'OK': print(f"{status_nok} {RED}Gagal fetch: {status}{RESET}"); return
        msg = email.message_from_bytes(data[0][1])
        subject = decode_mime_words(msg["Subject"]); sender = decode_mime_words(msg["From"])
        print(f"   {CYAN}Dari  :{RESET} {sender}"); print(f"   {CYAN}Subjek:{RESET} {subject}")
        print(f"{MAGENTA}-------------------------------------------{RESET}")
        body = get_text_from_email(msg); full_content = subject.lower() + " " + body

        if target_kw in full_content:
            print(f"{GREEN}🎯 {BOLD}Keyword Target Ditemukan!{RESET} ('{settings['target_keyword']}')")
            target_idx = full_content.find(target_kw)
            trigger_idx = full_content.find(trigger_kw, target_idx + len(target_kw))
            if trigger_idx != -1:
                action_part = full_content[trigger_idx + len(trigger_kw):].lstrip()
                action_word = action_part.split(maxsplit=1)[0].strip('.,!?:;()[]{}').lower() if action_part else ""
                if action_word in ["buy", "sell"]:
                    action_color = BRIGHT_GREEN if action_word == "buy" else BRIGHT_RED
                    print(f"{action_color}📌 {BOLD}Keyword Trigger Ditemukan!{RESET} -> Aksi: {BOLD}{action_word.upper()}{RESET}")
                    trigger_beep(action_word)
                    if settings.get("execute_binance_orders"):
                        if binance_client:
                            execute_binance_order(binance_client, settings, getattr(Client, f"SIDE_{action_word.upper()}"))
                        else: print(f"{status_warn} {YELLOW}Binance client tidak siap.{RESET}")
                elif action_word: print(f"{status_warn} {YELLOW}Aksi '{action_word}' tidak dikenal.{RESET}")
                else: print(f"{status_warn} {YELLOW}Tidak ada kata setelah trigger.{RESET}")
            else: print(f"{status_warn} {YELLOW}Trigger '{trigger_kw}' tidak ditemukan setelah target.{RESET}")
        else: print(f"{BLUE}💨 Keyword target tidak ditemukan.{RESET}")
        try: mail.store(email_id, '+FLAGS', '\\Seen') # Mark as read
        except Exception as e: print(f"{status_nok} {RED}Gagal mark as read: {e}{RESET}")
        print(f"{MAGENTA}==========================================={RESET}")
    except Exception as e: print(f"{status_nok} {RED}ERROR proses email {email_id_str}:{RESET}"); traceback.print_exc(); print(f"{MAGENTA}==========================================={RESET}")


# --- Fungsi Listening Utama ---
def start_listening(settings):
    global running, spinner_chars
    running = True; mail = None; binance_client = None; wait_time = 30
    conn_attempts = 0; spinner_idx = 0; last_status_line = ""

    rows, cols = get_terminal_size()
    clear_screen()
    print("\n" * 2)
    title_bar = f" {status_rocket}{BOLD} LISTENER AKTIF: Email {'& Binance' if settings.get('execute_binance_orders') else ''} {status_rocket} "
    print_centered(f"{REVERSE}{WHITE}{title_bar}{RESET}", cols-4)
    print_separator(char="*", length=cols-4, color=MAGENTA)
    print("\n")

    if settings.get("execute_binance_orders"):
        if not BINANCE_AVAILABLE: print(f"{status_nok} {RED}{BOLD}FATAL: Library 'python-binance' tidak ada!{RESET}"); running = False; return
        print(f"{status_info} {CYAN}[SETUP] Inisialisasi Binance...{RESET}")
        binance_client = get_binance_client(settings)
        if not binance_client: print(f"{status_nok} {RED}{BOLD}Gagal konek Binance. Eksekusi dibatalkan.{RESET}"); settings['execute_binance_orders'] = False
    else: print(f"{status_info} {YELLOW}[INFO] Eksekusi Binance dinonaktifkan.{RESET}")

    print_separator(length=cols-4, color=CYAN)
    print(f"{status_info} {CYAN}[SETUP] Menyiapkan Listener Email ({settings['email_address']})...{RESET}")
    print_separator(length=cols-4, color=CYAN)
    time.sleep(1)
    print(f"\n{BOLD}{WHITE}Memulai pemantauan... (Ctrl+C untuk berhenti){RESET}")
    print("-" * (cols - 4))

    while running:
        try:
            # --- IMAP Connection ---
            if not mail or mail.state != 'SELECTED':
                conn_attempts += 1; status_line = f"{status_wait} {CYAN}[{conn_attempts}] Koneksi ke IMAP ({settings['imap_server']})...{RESET}"
                print(status_line.ljust(len(last_status_line)), end='\r'); last_status_line = status_line
                try:
                    mail = imaplib.IMAP4_SSL(settings['imap_server'], timeout=20) # Tambah timeout
                    status_line = f"{status_ok} {GREEN}IMAP Terhubung.              {RESET}"; print(status_line.ljust(len(last_status_line)), end='\r'); last_status_line = status_line
                    status_line = f"{status_wait} {CYAN}Login ({settings['email_address']})...{RESET}"; print(status_line.ljust(len(last_status_line)), end='\r'); last_status_line = status_line
                    mail.login(settings['email_address'], settings['app_password'])
                    status_line = f"{status_ok} {GREEN}Login Berhasil!             {RESET}"; print(status_line.ljust(len(last_status_line)), end='\r'); last_status_line = status_line; time.sleep(0.5)
                    mail.select("inbox")
                    status_line = f"{status_ok} {GREEN}INBOX Ready. Mendengarkan...{RESET}"; print(status_line.ljust(len(last_status_line))); last_status_line = status_line # Print newline
                    print("-" * (cols - 4)); conn_attempts = 0
                except (imaplib.IMAP4.error, socket.error, OSError) as imap_err:
                    status_line = f"{status_nok} {RED}{BOLD}IMAP Gagal:{RESET} {imap_err} "; print(status_line.ljust(len(last_status_line))); last_status_line = status_line
                    if "authentication failed" in str(imap_err).lower() or "invalid credentials" in str(imap_err).lower(): print(f"{RED}{BOLD}   -> CEK EMAIL/APP PASS!{RESET}"); running = False; return
                    else: print(f"{YELLOW}   -> Coba lagi dalam {wait_time} detik...{RESET}"); time.sleep(wait_time); continue

            # --- Inner Loop: Check Mail ---
            while running:
                try: status, _ = mail.noop(); # Keepalive
                     if status != 'OK': print(f"\n{status_warn} {YELLOW}IMAP NOOP fail ({status}). Reconnecting...{RESET}"); break
                except Exception: print(f"\n{status_warn} {YELLOW}IMAP Keepalive fail. Reconnecting...{RESET}"); break

                status, messages = mail.search(None, '(UNSEEN)');
                if status != 'OK': print(f"\n{status_nok} {RED}IMAP search fail ({status}). Reconnecting...{RESET}"); break
                email_ids = messages[0].split()
                if email_ids:
                    print(" " * len(last_status_line), end='\r') # Clear status line
                    print(f"\n{BRIGHT_GREEN}{BOLD}✨ Ditemukan {len(email_ids)} email baru! ✨{RESET}")
                    print("-" * (cols - 4))
                    for email_id in email_ids:
                        if not running: break
                        process_email(mail, email_id, settings, binance_client)
                    if not running: break
                    print("-" * (cols - 4)); print(f"{GREEN}✅ Selesai. Kembali mendengarkan...{RESET}"); print("-" * (cols - 4))
                    last_status_line = "" # Reset status line
                else:
                    # --- No New Mail: Show Spinner ---
                    wait_interval = settings['check_interval_seconds']
                    spinner = spinner_chars[spinner_idx % len(spinner_chars)]
                    spinner_idx += 1
                    status_line = f"{BLUE}{BOLD}{spinner}{RESET}{BLUE} Menunggu email ({wait_interval}s)... {RESET}"
                    print(status_line.ljust(len(last_status_line)), end='\r')
                    last_status_line = status_line
                    for _ in range(wait_interval): # Sleep per second for responsiveness
                        if not running: break
                        time.sleep(1)
                    if not running: break

            # --- Exited Inner Loop (Reconnect Needed) ---
            if mail and mail.state == 'SELECTED': try: mail.close() except Exception: pass

        # --- Outer Exception Handling ---
        except (ConnectionError, socket.gaierror) as net_err:
             status_line = f"\n{status_nok} {RED}{BOLD}Network Error:{RESET} {net_err}"; print(status_line.ljust(len(last_status_line))); last_status_line = status_line
             print(f"{YELLOW}   -> Cek internet. Coba lagi dalam {wait_time} detik...{RESET}"); time.sleep(wait_time)
        except Exception as e:
            status_line = f"\n{status_nok} {RED}{BOLD}ERROR Listener Utama:{RESET}"; print(status_line.ljust(len(last_status_line))); last_status_line = status_line
            traceback.print_exc()
            print(f"{YELLOW}   -> Coba recovery dalam {wait_time} detik...{RESET}"); time.sleep(wait_time)
        finally:
            if mail: try: mail.logout() except Exception: pass
            mail = None;
            if running: time.sleep(3) # Pause before outer loop retry

    print(f"\n{BRIGHT_YELLOW}{BOLD}🛑 Listener dihentikan.{RESET}")
    print("-"*(cols-4))


# --- Fungsi Menu Pengaturan ---
def show_settings(settings):
    while True:
        rows, cols = get_terminal_size()
        wipe_effect(rows, cols, char='⚙️', delay=0.002, color=CYAN) # Wipe setting
        clear_screen()

        left_content = []
        left_content.append(f"{BLUE}{BOLD}--- Email Settings ---{RESET}")
        # ... (Isi konten kiri seperti sebelumnya, pakai status icon jika perlu) ...
        email_disp = settings['email_address'] or f'{YELLOW}[Kosong]{RESET}'
        pwd_disp = '[Hidden]' if settings['app_password'] else f'{YELLOW}[Kosong]{RESET}'
        left_content.append(f" 1. {CYAN}Email{RESET}    : {email_disp}")
        left_content.append(f" 2. {CYAN}App Pass{RESET} : {pwd_disp}")
        left_content.append(f" 3. {CYAN}IMAP Srv{RESET} : {settings['imap_server']}")
        left_content.append(f" 4. {CYAN}Interval{RESET} : {settings['check_interval_seconds']}s {DIM}(min:5){RESET}")
        left_content.append(f" 5. {CYAN}Target KW{RESET}: {BOLD}{settings['target_keyword']}{RESET}")
        left_content.append(f" 6. {CYAN}Trigger KW{RESET}: {BOLD}{settings['trigger_keyword']}{RESET}")
        left_content.append("")
        left_content.append(f"{BLUE}{BOLD}--- Binance Settings ---{RESET}")
        lib_status = f"{GREEN}Ready{RESET}" if BINANCE_AVAILABLE else f"{RED}Missing!{RESET}"
        left_content.append(f" Library     : [{status_ok if BINANCE_AVAILABLE else status_nok}] {lib_status}")
        api_key_disp = '[Hidden]' if settings['binance_api_key'] else f'{YELLOW}[Kosong]{RESET}'
        api_sec_disp = '[Hidden]' if settings['binance_api_secret'] else f'{YELLOW}[Kosong]{RESET}'
        left_content.append(f" 7. {CYAN}API Key{RESET}   : {api_key_disp}")
        left_content.append(f" 8. {CYAN}API Secret{RESET}: {api_sec_disp}")
        pair_disp = settings['trading_pair'] or f'{YELLOW}[Kosong]{RESET}'
        left_content.append(f" 9. {CYAN}TradingPair{RESET}: {BOLD}{pair_disp}{RESET}")
        left_content.append(f"10. {CYAN}Buy Qty{RESET}  : {settings['buy_quote_quantity']} {DIM}(Quote>0){RESET}")
        left_content.append(f"11. {CYAN}Sell Qty{RESET} : {settings['sell_base_quantity']} {DIM}(Base>=0){RESET}")
        exec_status = f"{GREEN}{BOLD}AKTIF{RESET}" if settings['execute_binance_orders'] else f"{RED}NONAKTIF{RESET}"
        left_content.append(f"12. {CYAN}Eksekusi{RESET}  : [{status_ok if settings['execute_binance_orders'] else status_nok}] {exec_status}")
        left_content.append("")
        left_content.append(f" {GREEN}{BOLD}E{RESET} - Edit Pengaturan")
        left_content.append(f" {RED}{BOLD}K{RESET} - Kembali ke Menu")

        # --- Draw Layout ---
        draw_layout(left_content, SETTINGS_ART, title="PENGATURAN")

        # --- Input ---
        choice = input(f"  {BOLD}{WHITE}Pilihan Anda (E/K): {RESET}").lower().strip()

        if choice == 'e':
            print(f"\n  {BOLD}{MAGENTA}--- Edit Pengaturan ---{RESET} {DIM}(Kosongkan untuk skip){RESET}")
            # --- Proses Edit ---
            # (Logika input edit tetap sama, pakai getpass)
            # ... (copy paste logika edit dari versi sebelumnya) ...
            # Email Edits
            print(f"\n  {CYAN}--- Email ---{RESET}")
            new_val = input(f"  1. Email [{email_disp}]: ").strip();
            if new_val: settings['email_address'] = new_val
            try:
                new_pass = getpass.getpass(f"  2. App Password Baru [{pwd_disp}] (ketik u/ ubah): ").strip()
                if new_pass: settings['app_password'] = new_pass; print(f"    {GREEN}Password diperbarui.{RESET}")
            except Exception: new_pass = input(f"  2. App Password Baru (terlihat) [{pwd_disp}]: ").strip();
            if new_pass: settings['app_password'] = new_pass
            new_val = input(f"  3. Server IMAP [{settings['imap_server']}]: ").strip();
            if new_val: settings['imap_server'] = new_val
            while True:
                val = input(f"  4. Interval [{settings['check_interval_seconds']}s], min 5: ").strip();
                if not val: break;
                try: i = int(val); assert i>=5; settings['check_interval_seconds']=i; break;
                except: print(f"    {RED}Input angka >= 5.{RESET}")
            new_val=input(f"  5. Keyword Target [{settings['target_keyword']}]: ").strip();
            if new_val: settings['target_keyword'] = new_val
            new_val=input(f"  6. Keyword Trigger [{settings['trigger_keyword']}]: ").strip();
            if new_val: settings['trigger_keyword'] = new_val

            # Binance Edits
            print(f"\n  {CYAN}--- Binance ---{RESET}")
            new_val = input(f"  7. API Key [{api_key_disp}]: ").strip();
            if new_val: settings['binance_api_key'] = new_val
            try:
                new_secret = getpass.getpass(f"  8. API Secret Baru [{api_sec_disp}] (ketik u/ ubah): ").strip()
                if new_secret: settings['binance_api_secret'] = new_secret; print(f"    {GREEN}Secret Key diperbarui.{RESET}")
            except Exception: new_secret = input(f"  8. API Secret Baru (terlihat) [{api_sec_disp}]: ").strip();
            if new_secret: settings['binance_api_secret'] = new_secret
            new_val = input(f"  9. Trading Pair [{pair_disp}]: ").strip().upper();
            if new_val: settings['trading_pair'] = new_val
            while True:
                val=input(f" 10. Buy Quote Qty [{settings['buy_quote_quantity']}], > 0: ").strip();
                if not val: break;
                try: f=float(val); assert f>0; settings['buy_quote_quantity']=f; break;
                except: print(f"    {RED}Input angka > 0.{RESET}")
            while True:
                val=input(f" 11. Sell Base Qty [{settings['sell_base_quantity']}], >= 0: ").strip();
                if not val: break;
                try: f=float(val); assert f>=0; settings['sell_base_quantity']=f; break;
                except: print(f"    {RED}Input angka >= 0.{RESET}")
            while True:
                cur="Aktif" if settings['execute_binance_orders'] else "Nonaktif"
                val=input(f" 12. Eksekusi Order? (y/n) [{cur}]: ").lower().strip();
                if not val: break;
                if val=='y': settings['execute_binance_orders']=True; print(f"    {GREEN}Eksekusi Diaktifkan.{RESET}"); break;
                elif val=='n': settings['execute_binance_orders']=False; print(f"    {RED}Eksekusi Dinonaktifkan.{RESET}"); break;
                else: print(f"    {RED}Input 'y' atau 'n'.{RESET}")

            save_settings(settings)
            input(f"\n  {GREEN}{BOLD}✅ Pengaturan disimpan!{RESET} Tekan Enter...")

        elif choice == 'k':
            break
        else:
            print(f"  {RED}[ERROR] Pilihan tidak valid.{RESET}")
            time.sleep(1)

# --- Fungsi Menu Utama ---
def main_menu():
    global MAIN_ART
    settings = load_settings()
    startup_animation()
    pulse_state = 0

    while True:
        settings = load_settings() # Re-load setting
        rows, cols = get_terminal_size()
        # wipe_effect(rows, cols, char=random.choice(['░', '▒', '▓']), delay=0.001) # Fast wipe
        clear_screen()

        # --- Pulsing Title Effect ---
        t = time.time()
        # pulse_factor = (math.sin(t * 3) + 1) / 2 # Sin wave 0 to 1
        # title_color = BRIGHT_MAGENTA if pulse_factor > 0.5 else MAGENTA
        # title_style = BOLD if pulse_factor > 0.3 else BOLD+DIM
        pulse_state = 1 - pulse_state # Simple toggle
        title_color = BRIGHT_MAGENTA if pulse_state == 1 else MAGENTA
        title_style = BOLD

        # --- Konten Kolom Kiri ---
        left_content = []
        # left_content.append(f"{title_style}{title_color}╔══════════════════════════════╗{RESET}")
        # left_content.append(f"{title_style}{title_color}║   Exora AI Email Listener    ║{RESET}")
        # left_content.append(f"{title_style}{title_color}╚══════════════════════════════╝{RESET}")
        left_content.append("")
        left_content.append(f"{BOLD}{WHITE}Menu Utama:{RESET}")
        exec_label = f" {BOLD}& Binance{RESET}" if settings.get("execute_binance_orders") else ""
        left_content.append(f" {BRIGHT_GREEN}{BOLD}1.{RESET} Mulai Listener (Email{exec_label})")
        left_content.append(f" {BRIGHT_CYAN}{BOLD}2.{RESET} Buka Pengaturan")
        left_content.append(f" {BRIGHT_YELLOW}{BOLD}3.{RESET} Keluar Aplikasi")
        left_content.append("") # Spasi
        left_content.append(f"{BOLD}{WHITE}Status Cepat:{RESET}")
        email_ok = bool(settings['email_address']) and bool(settings['app_password'])
        email_status = status_ok if email_ok else status_nok
        left_content.append(f" Email Config : [{email_status}] {settings['email_address'] if email_ok else '(Belum Lengkap)'}")
        exec_on = settings.get("execute_binance_orders", False)
        exec_label = f"{GREEN}AKTIF{RESET}" if exec_on else f"{YELLOW}NONAKTIF{RESET}"
        lib_status = f"{GREEN}Ready{RESET}" if BINANCE_AVAILABLE else f"{RED}Missing!{RESET}"
        left_content.append(f" Binance Lib  : [{status_ok if BINANCE_AVAILABLE else status_nok}] {lib_status} | Eksekusi: [{status_ok if exec_on else status_warn}] {exec_label}")
        if exec_on and BINANCE_AVAILABLE:
            api_ok = bool(settings['binance_api_key']) and bool(settings['binance_api_secret'])
            pair_ok = bool(settings['trading_pair'])
            qty_ok = settings['buy_quote_quantity'] > 0 and settings['sell_base_quantity'] >= 0
            bin_cfg_ok = api_ok and pair_ok and qty_ok
            cfg_status = status_ok if bin_cfg_ok else status_warn
            left_content.append(f" Binance Cfg  : [{cfg_status}] {'Lengkap' if bin_cfg_ok else '(Perlu Dicek)'}")

        # --- Draw Layout ---
        # Update Main Art title color
        dynamic_art = MAIN_ART[:] # Salin list
        dynamic_art[0] = f"{title_style}{title_color}{dynamic_art[0]}{RESET}"
        dynamic_art[1] = f"{title_style}{title_color}{dynamic_art[1]}{RESET}"
        dynamic_art[2] = f"{title_style}{title_color}{dynamic_art[2]}{RESET}"
        dynamic_art[3] = f"{title_style}{title_color}{dynamic_art[3]}{RESET}"
        dynamic_art[4] = f"{title_style}{title_color}{dynamic_art[4]}{RESET}"
        dynamic_art[5] = f"{title_style}{title_color}{dynamic_art[5]}{RESET}"
        dynamic_art[7] = f"   {title_style}{title_color}{dynamic_art[7].strip()}{RESET}" # Judul dalam art

        draw_layout(left_content, dynamic_art) # Tidak pakai title bar lagi

        # --- Input ---
        choice = input(f"  {BOLD}{WHITE}Masukkan pilihan Anda (1/2/3): {RESET}").strip()

        if choice == '1':
            # --- Validasi Sebelum Mulai ---
            can_start = True
            if not email_ok:
                print(f"\n  {status_nok} {RED}Email/App Password belum diatur di Pengaturan!{RESET}"); can_start = False
            if exec_on:
                if not BINANCE_AVAILABLE:
                    print(f"\n  {status_nok} {RED}Eksekusi aktif tapi library Binance error! Install 'python-binance'.{RESET}"); can_start = False
                elif not bin_cfg_ok:
                     print(f"\n  {status_warn} {YELLOW}Eksekusi aktif tapi konfigurasi Binance belum lengkap/valid (API/Pair/Qty).{RESET}")
                     # Tetap bisa start, tapi eksekusi mungkin gagal

            if can_start:
                start_listening(settings)
                print(f"\n{YELLOW}[INFO] Kembali ke Menu Utama...{RESET}")
                input(f"{DIM}Tekan Enter untuk melanjutkan...{RESET}")
            else:
                input(f"\n{DIM}Tekan Enter untuk kembali ke menu...{RESET}")

        elif choice == '2':
            show_settings(settings)
        elif choice == '3':
            clear_screen(); print("\n" * (rows // 3)); print_centered(f"{BRIGHT_CYAN}{BOLD}👋 Terima kasih! Sampai jumpa! 👋{RESET}", cols); print("\n" * 5); sys.exit(0)
        else: print(f"\n  {RED}{BOLD}Pilihan tidak valid!{RESET}"); time.sleep(1.5)


# --- Entry Point ---
if __name__ == "__main__":
    try: main_menu()
    except KeyboardInterrupt: print(f"\n{YELLOW}{BOLD}Program dihentikan paksa.{RESET}"); sys.exit(1)
    except Exception as e:
        clear_screen(); print(f"\n{BOLD}{RED}💥 ERROR KRITIS 💥{RESET}\n"); traceback.print_exc()
        print(f"\n{RED}Error: {e}{RESET}\nProgram akan ditutup."); sys.exit(1)
