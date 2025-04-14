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
import shutil # Untuk get_terminal_size() yang lebih modern

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
MIN_TERMINAL_WIDTH = 70 # Lebar minimal terminal agar layout 2 kolom tidak rusak

# --- Kode Warna ANSI & Style ---
# (Kode Warna ANSI tetap sama)
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


# --- Karakter "Animasi" ---
# (Karakter animasi tetap sama)
spinner_chars = ['▹▹▹▹▹', '▸▹▹▹▹', '▹▸▹▹▹', '▹▹▸▹▹', '▹▹▹▸▹', '▹▹▹▹▸']
loading_bar_char = '█'
wipe_char = '▓'
status_ok = f"{GREEN}✔{RESET}"
status_nok = f"{RED}✘{RESET}"
status_warn = f"{YELLOW}⚠{RESET}"
status_wait = f"{BLUE}⏳{RESET}"

# --- ASCII Art (Sedikit disempurnakan) ---
ROCKET_ART = [
    "      .",
    "     / \\",
    "    / _ \\",
    "   |.o '.|",
    "   |'._.'|",
    "   |     |",
    " ,'|  .  |.",
    "/  |     |  \\",
    "|   `-----'   |",
    " \\  '. V .'  /",
    "  '._____.'",
    "     || ||",
    "     || ||",
    "     || ||",
    "    / | | \\",
    "   /  | |  \\",
    "  `-. H H .-`",
    "   _//^\\\\_",
    "  | /   \\ |",
    "  \\| | | |/",
    "   '-----'",
]

SETTINGS_ART = [ # Art untuk menu settings
    "       .--.",
    "      |o_o |",
    "      |:_/ |",
    "     //   \\ \\",
    "    (|     | )",
    "   /'\\_   _/`\\",
    "   \\___)=(___/",
    "",
    "   CONFIGURATOR",
    "     MODULE",
]


# --- Fungsi Utilitas Tampilan ---
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def get_terminal_size(default_cols=80, default_rows=24):
    """Mendapatkan ukuran terminal (kolom, baris)."""
    try:
        # Metode paling modern dan direkomendasikan
        cols, rows = shutil.get_terminal_size()
        return cols, rows
    except (AttributeError, ValueError, OSError):
        try:
            # Metode fallback menggunakan os (mungkin tidak selalu ada)
            cols, rows = os.get_terminal_size(0)
            return cols, rows
        except (AttributeError, ValueError, OSError):
            try:
                # Fallback untuk Unix-like systems via stty
                rows, cols = map(int, os.popen('stty size', 'r').read().split())
                return cols, rows
            except ValueError:
                # Default jika semua gagal
                return default_cols, default_rows

def print_centered(text, width, color=RESET):
    """Mencetak teks di tengah dengan padding."""
    # Hati-hati: Fungsi ini belum menghitung panjang ANSI codes.
    # Untuk teks sederhana tanpa banyak warna di tengah, ini cukup.
    text_len_no_ansi = len(re.sub(r'\x1b\[[0-9;]*m', '', text)) # Simple ANSI strip
    padding = max(0, (width - text_len_no_ansi)) // 2
    print(f"{color}{' ' * padding}{text}{RESET}")

def print_separator(char="─", length=80, color=DIM + WHITE + RESET):
    """Mencetak garis pemisah."""
    print(f"{color}{char * length}{RESET}")

def wipe_effect(rows, cols, char=wipe_char, delay=0.005, color=DIM):
    """Efek wipe sederhana (tetap sama)."""
    for r in range(rows // 2):
        line = char * cols
        sys.stdout.write(f"\033[{r + 1};1H{color}{line}{RESET}")
        sys.stdout.write(f"\033[{rows - r};1H{color}{line}{RESET}")
        sys.stdout.flush()
        time.sleep(delay)

def pad_lines(lines, target_height):
    """Menambahkan baris kosong di akhir list hingga mencapai target_height."""
    padding_needed = max(0, target_height - len(lines))
    return lines + [""] * padding_needed

# Modifikasi: Terima width kalkulasi dari luar
def draw_two_column_layout(left_lines, right_lines, total_width, left_col_width, padding=4):
    """ Mencetak dua kolom bersebelahan dengan tinggi sama. """
    # Pastikan kedua list punya tinggi yang sama
    max_height = max(len(left_lines), len(right_lines))
    left_padded_lines = pad_lines(left_lines, max_height)
    right_padded_lines = pad_lines(right_lines, max_height)

    right_col_width = total_width - left_col_width - padding
    spacer = " " * padding

    for i in range(max_height):
        left_part = left_padded_lines[i].rstrip()
        right_part = right_padded_lines[i].rstrip()

        # Perhitungan padding kiri mungkin perlu disesuaikan jika ada ANSI
        # Untuk simplicity, kita anggap ANSI tidak signifikan mengubah panjang visual
        left_aligned = left_part.ljust(left_col_width)
        # ASCII art biasanya tidak perlu ljust, tapi jaga-jaga:
        right_aligned = right_part.ljust(right_col_width)

        print(f"{left_aligned}{spacer}{right_aligned}")

def startup_animation():
    # (Startup animation tetap sama)
    clear_screen()
    rows, cols = get_terminal_size()
    brand = "🚀 Exora AI Listener 🚀"
    stages = ["[■□□□□□]", "[■■□□□□]", "[■■■□□□]", "[■■■■□□]", "[■■■■■□]", "[■■■■■■]"]
    messages = [
        "Menginisialisasi sistem...",
        "Memuat modul...",
        "Mengecek dependensi...",
        "Menghubungkan ke Matrix...",
        "Kalibrasi sensor...",
        "Siap meluncur!"
    ]

    print("\n" * (rows // 3))
    print_centered(brand, cols, BOLD + MAGENTA)
    print("\n")
    import re # Perlu re untuk print_centered jika ada ANSI
    for i, stage in enumerate(stages):
        progress = f"{BLUE}{stage}{RESET} {messages[i]}"
        print_centered(progress + " " * 20, cols)
        time.sleep(random.uniform(0.2, 0.5))
        if i < len(stages) - 1:
             sys.stdout.write("\033[F")
             sys.stdout.flush()

    print_centered(f"{GREEN}{BOLD}✅ Sistem Siap!{RESET}", cols)
    time.sleep(1)
    wipe_effect(rows, cols)

# --- Fungsi Penanganan Sinyal (Ctrl+C) ---
# (Tetap sama)
def signal_handler(sig, frame):
    global running
    print(f"\n{BRIGHT_YELLOW}{BOLD}🛑 Ctrl+C terdeteksi! Menghentikan semua proses...{RESET}")
    running = False
    time.sleep(0.5)
    print(f"\n{RED}{BOLD}👋 Sampai jumpa!{RESET}")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# --- Fungsi Konfigurasi ---
# (Load & Save Settings tetap sama)
def load_settings():
    settings = DEFAULT_SETTINGS.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_settings = json.load(f)
                for key in DEFAULT_SETTINGS:
                    if key in loaded_settings:
                        settings[key] = loaded_settings[key]
                # Validasi
                settings["check_interval_seconds"] = max(5, int(settings.get("check_interval_seconds", 10)))
                settings["buy_quote_quantity"] = max(0.0, float(settings.get("buy_quote_quantity", 11.0)))
                settings["sell_base_quantity"] = max(0.0, float(settings.get("sell_base_quantity", 0.0)))
                settings["execute_binance_orders"] = bool(settings.get("execute_binance_orders", False))
                save_settings(settings, silent=True)
        except json.JSONDecodeError:
            print(f"{RED}[ERROR] File '{CONFIG_FILE}' rusak. Pakai default & simpan ulang.{RESET}")
            save_settings(settings)
        except Exception as e:
            print(f"{RED}[ERROR] Gagal load config: {e}{RESET}")
            print(f"{YELLOW}[WARN] Pakai default sementara.{RESET}")
    else:
        print(f"{YELLOW}[INFO] File '{CONFIG_FILE}' tidak ada. Dibuat dengan default.{RESET}")
        save_settings(settings)
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
            print(f"{GREEN}{BOLD}💾 Pengaturan disimpan ke '{CONFIG_FILE}'{RESET}")
    except Exception as e:
        print(f"{RED}[ERROR] Gagal menyimpan config: {e}{RESET}")


# --- Fungsi Utilitas Lain ---
# (decode_mime_words, get_text_from_email, trigger_beep, get_binance_client, execute_binance_order, process_email)
# (Fungsi-fungsi ini secara logika tetap sama, hanya tampilan outputnya saja yg sudah diubah sebelumnya)
# ... (Kode fungsi-fungsi ini disalin dari versi sebelumnya) ...
def get_timestamp(): return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def decode_mime_words(s):
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
                except Exception as e: print(f"{YELLOW}[WARN] Decode error (multipart): {e}{RESET}")
    else:
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                text_content = payload.decode(charset, errors='replace')
            except Exception as e: print(f"{YELLOW}[WARN] Decode error (single): {e}{RESET}")
    return text_content.lower()

def trigger_beep(action):
    try:
        action_upper = action.upper(); action_color = GREEN if action == "buy" else RED if action == "sell" else MAGENTA
        print(f"{action_color}{BOLD}🔊 BEEP {action_upper}! 🔊{RESET}")
        try:
            if action == "buy": subprocess.run(["beep", "-f", "1000", "-l", "500", "-D", "100", "-r", "3"], check=True, capture_output=True, text=True, timeout=3)
            elif action == "sell": subprocess.run(["beep", "-f", "700", "-l", "700", "-D", "100", "-r", "2"], check=True, capture_output=True, text=True, timeout=3)
            else: print("\a", end='')
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError): print("\a", end=''); sys.stdout.flush()
    except Exception as e: print(f"{RED}[ERROR] Beep error: {e}{RESET}")

def get_binance_client(settings):
    if not BINANCE_AVAILABLE: return None
    if not settings.get('binance_api_key') or not settings.get('binance_api_secret'): print(f"{status_nok} {RED}{BOLD}API Key/Secret Binance kosong!{RESET}"); return None
    try:
        print(f"{status_wait} {CYAN}Menghubungkan ke Binance API...{RESET}", end='\r'); client = Client(settings['binance_api_key'], settings['binance_api_secret']); client.ping()
        print(f"{status_ok} {GREEN}{BOLD}Koneksi Binance API Berhasil!                {RESET}"); return client
    except BinanceAPIException as e: print(f"{status_nok} {RED}{BOLD}Koneksi/Auth Binance Gagal:{RESET} {e.status_code} - {e.message}"); return None
    except Exception as e: print(f"{status_nok} {RED}{BOLD}Gagal membuat Binance client:{RESET} {e}"); return None

def execute_binance_order(client, settings, side):
    if not client: print(f"{status_warn} {YELLOW}Eksekusi dibatalkan, client Binance tidak valid.{RESET}"); return False
    if not settings.get("execute_binance_orders", False): print(f"{status_warn} {YELLOW}Eksekusi order dinonaktifkan. Order dilewati.{RESET}"); return False
    pair = settings.get('trading_pair', '').upper();
    if not pair: print(f"{status_nok} {RED}{BOLD}Trading pair belum diatur!{RESET}"); return False
    order_details = {}; action_desc = ""; side_color = BRIGHT_GREEN if side == Client.SIDE_BUY else BRIGHT_RED; side_icon = "🛒" if side == Client.SIDE_BUY else "💰"
    try:
        print(f"\n{side_color}--- {BOLD}PERSIAPAN ORDER {side} ({pair}){RESET} {side_color}---{RESET}")
        if side == Client.SIDE_BUY:
            quote_qty = settings.get('buy_quote_quantity', 0.0);
            if quote_qty <= 0: print(f"{status_nok} {RED}Qty Beli harus > 0.{RESET}"); return False
            order_details = {'symbol': pair, 'side': Client.SIDE_BUY, 'type': Client.ORDER_TYPE_MARKET, 'quoteOrderQty': quote_qty}; quote_asset = pair[-4:].replace("BTC","") if pair.endswith("BTC") else pair[-3:]; action_desc = f"{side_icon} {BOLD}MARKET BUY{RESET} {quote_qty} {quote_asset} untuk {pair}"
        elif side == Client.SIDE_SELL:
            base_qty = settings.get('sell_base_quantity', 0.0);
            if base_qty <= 0: print(f"{status_warn if base_qty == 0 else status_nok} {YELLOW if base_qty==0 else RED}Qty Jual {settings['sell_base_quantity']}. Order SELL {'dilewati' if base_qty==0 else 'harus > 0'}.{RESET}"); return False
            order_details = {'symbol': pair, 'side': Client.SIDE_SELL, 'type': Client.ORDER_TYPE_MARKET, 'quantity': base_qty}; base_asset=pair[:-len(quote_asset)] if 'quote_asset' in locals() else pair[:-3]; action_desc = f"{side_icon} {BOLD}MARKET SELL{RESET} {base_qty} {base_asset} dari {pair}"
        else: print(f"{status_nok} {RED}Sisi order tidak valid: {side}{RESET}"); return False
        print(f"{CYAN}{status_wait} Mencoba eksekusi: {action_desc}...{RESET}"); order_result = client.create_order(**order_details)
        print(f"{side_color}{BOLD}✅ ORDER BERHASIL DI EKSEKUSI!{RESET}"); print(f"{DIM}-------------------------------------------")
        print(f"{DIM}  Order ID : {order_result.get('orderId')}"); print(f"{DIM}  Symbol   : {order_result.get('symbol')}"); print(f"{DIM}  Side     : {order_result.get('side')}"); print(f"{DIM}  Status   : {order_result.get('status')}")
        if order_result.get('fills'):
            total_qty = sum(float(f['qty']) for f in order_result['fills']); total_quote_qty = sum(float(f['cummulativeQuoteQty']) for f in order_result['fills']); avg_price = total_quote_qty / total_qty if total_qty else 0
            print(f"{DIM}  Avg Price: {avg_price:.8f}"); print(f"{DIM}  Filled Qty: {total_qty:.8f} (Base)"); print(f"{DIM}  Total Cost: {total_quote_qty:.4f} (Quote)")
        print(f"-------------------------------------------{RESET}"); return True
    except BinanceAPIException as e: print(f"{status_nok} {RED}{BOLD}BINANCE API ERROR:{RESET} {e.status_code} - {e.message}"); return False # simplified error details
    except BinanceOrderException as e: print(f"{status_nok} {RED}{BOLD}BINANCE ORDER ERROR:{RESET} {e.status_code} - {e.message}"); return False
    except Exception as e: print(f"{status_nok} {RED}{BOLD}ERROR EKSEKUSI BINANCE:{RESET}"); traceback.print_exc(); return False
    finally: print(f"{side_color}--- {BOLD}SELESAI PROSES ORDER {side} ({pair}){RESET} {side_color}---{RESET}\n")

def process_email(mail, email_id, settings, binance_client):
    global running; if not running: return
    target_keyword_lower = settings['target_keyword'].lower(); trigger_keyword_lower = settings['trigger_keyword'].lower(); email_id_str = email_id.decode('utf-8'); ts = get_timestamp()
    try:
        print(f"\n{MAGENTA}📧 {BOLD}Memproses Email ID: {email_id_str} [{ts}]{RESET}{MAGENTA} ==={RESET}"); print(f"{DIM}   Mengambil data...{RESET}", end='\r'); status, data = mail.fetch(email_id, "(RFC822)")
        if status != 'OK': print(f"{status_nok} {RED}Gagal fetch ID {email_id_str}: {status}   {RESET}"); return
        print(f"{GREEN}   Data diterima.                 {RESET}"); raw_email = data[0][1]; msg = email.message_from_bytes(raw_email); subject = decode_mime_words(msg["Subject"]); sender = decode_mime_words(msg["From"])
        print(f"   {CYAN}Dari  :{RESET} {sender}"); print(f"   {CYAN}Subjek:{RESET} {subject}"); print(f"{MAGENTA}-------------------------------------------{RESET}")
        body = get_text_from_email(msg); full_content = (subject.lower() + " " + body)
        if target_keyword_lower in full_content:
            print(f"{GREEN}🎯 {BOLD}Target Ditemukan!{RESET} ('{settings['target_keyword']}')");
            try:
                target_index = full_content.find(target_keyword_lower); trigger_index = full_content.find(trigger_keyword_lower, target_index + len(target_keyword_lower))
                if trigger_index != -1:
                    start_word_index = trigger_index + len(trigger_keyword_lower); text_after_trigger = full_content[start_word_index:].lstrip(); words_after_trigger = text_after_trigger.split(maxsplit=1)
                    if words_after_trigger:
                        action_word = words_after_trigger[0].strip('.,!?:;()[]{}').lower(); action_color = BRIGHT_GREEN if action_word == "buy" else BRIGHT_RED if action_word == "sell" else BRIGHT_YELLOW
                        print(f"{action_color}📌 {BOLD}Trigger Ditemukan!{RESET} ('{settings['trigger_keyword']}') -> Aksi: {BOLD}{action_word.upper()}{RESET}")
                        if action_word in ["buy", "sell"]:
                            trigger_beep(action_word)
                            if settings.get("execute_binance_orders"):
                                if binance_client: execute_binance_order(binance_client, settings, getattr(Client, f"SIDE_{action_word.upper()}"))
                                else: print(f"{status_warn} {YELLOW}Eksekusi aktif tapi client Binance tidak siap.{RESET}")
                            else: print(f"{DIM}   (Eksekusi Binance dinonaktifkan){RESET}")
                        else: print(f"{status_warn} {YELLOW}Aksi '{action_word}' tidak dikenal.{RESET}")
                    else: print(f"{status_warn} {YELLOW}Tidak ada kata setelah trigger '{settings['trigger_keyword']}'.{RESET}")
                else: print(f"{status_warn} {YELLOW}Trigger '{settings['trigger_keyword']}' tidak ditemukan SETELAH target '{settings['target_keyword']}'.{RESET}")
            except Exception as e: print(f"{status_nok} {RED}Gagal parsing setelah trigger: {e}{RESET}")
        else: print(f"{BLUE}💨 Keyword target '{settings['target_keyword']}' tidak ditemukan.{RESET}")
        try: mail.store(email_id, '+FLAGS', '\\Seen')
        except Exception as e: print(f"{status_nok} {RED}Gagal tandai 'Seen' ID {email_id_str}: {e}{RESET}")
        print(f"{MAGENTA}==========================================={RESET}")
    except Exception as e: print(f"{status_nok} {RED}{BOLD}Gagal total proses ID {email_id_str}:{RESET}"); traceback.print_exc(); print(f"{MAGENTA}==========================================={RESET}")

# --- Fungsi Listening Utama ---
def start_listening(settings):
    # (Fungsi listener utama secara logika tetap sama, hanya bagian setup tampilan awal dan pesan tunggu yg diupdate)
    global running, spinner_chars
    running = True; mail = None; binance_client = None; wait_time = 30; connection_attempts = 0; spinner_index = 0
    rows, cols = get_terminal_size()

    clear_screen()
    vertical_padding = max(1, (rows - 15) // 3) # Hitung padding atas dinamis
    print("\n" * vertical_padding)
    print_separator(char="*", length=cols-4, color=MAGENTA)
    mode = "Email & Binance Order" if settings.get("execute_binance_orders") else "Email Listener Only"
    print_centered(f"🚀 {BOLD}MODE AKTIF: {mode}{RESET} 🚀", cols-4, MAGENTA)
    print_separator(char="*", length=cols-4, color=MAGENTA)
    print("\n")

    # Setup Binance (tetap sama)
    if settings.get("execute_binance_orders"):
        if not BINANCE_AVAILABLE: print(f"{status_nok} {RED}{BOLD}FATAL: Library 'python-binance' tidak ada!{RESET}"); running = False; return
        print(f"{CYAN}🔗 {BOLD}[SETUP] Menginisialisasi Koneksi Binance...{RESET}")
        binance_client = get_binance_client(settings)
        if not binance_client:
            print(f"{status_nok} {RED}{BOLD}FATAL: Gagal konek Binance. Eksekusi order dibatalkan.{RESET}")
            settings['execute_binance_orders'] = False; print(f"{YELLOW}Eksekusi Binance dinonaktifkan untuk sesi ini.{RESET}"); time.sleep(3)
        else: print(f"{status_ok} {GREEN}{BOLD}[SETUP] Binance Client Siap!{RESET}")
    else: print(f"{YELLOW}ℹ️ {BOLD}[INFO] Eksekusi order Binance dinonaktifkan.{RESET}")

    print_separator(length=cols-4, color=CYAN)
    print(f"{CYAN}📧 {BOLD}[SETUP] Menyiapkan Listener Email...{RESET}")
    print(f"{DIM}   Akun  : {settings['email_address']}{RESET}")
    print(f"{DIM}   Server: {settings['imap_server']}{RESET}")
    print_separator(length=cols-4, color=CYAN)
    time.sleep(1)
    print(f"\n{BOLD}{WHITE}Memulai pemantauan... (Ctrl+C untuk berhenti){RESET}")
    print("-" * (cols - 4))

    # Loop Utama Listener (logika sama, update pesan tunggu)
    while running:
        try:
            # Koneksi IMAP (logika sama)
            if not mail or mail.state != 'SELECTED':
                connection_attempts += 1; print(f"{status_wait} {CYAN}[{connection_attempts}] Conn IMAP ({settings['imap_server']})...{RESET}", end='\r')
                try:
                    mail = imaplib.IMAP4_SSL(settings['imap_server']); print(f"{status_ok} {GREEN}IMAP Conn OK.               {RESET}")
                    print(f"{status_wait} {CYAN}Login {settings['email_address']}...{RESET}", end='\r'); mail.login(settings['email_address'], settings['app_password'])
                    print(f"{status_ok} {GREEN}Login OK! ({settings['email_address']}){RESET}     "); mail.select("inbox"); print(f"{status_ok} {GREEN}INBOX Ready. Listening...{RESET}"); print("-" * (cols-4)); connection_attempts = 0
                except (imaplib.IMAP4.error, imaplib.IMAP4.abort, socket.error, OSError) as imap_err:
                    print(f"{status_nok} {RED}{BOLD}IMAP Error:{RESET} {imap_err} ");
                    if "authentication failed" in str(imap_err).lower(): print(f"{RED}{BOLD}   -> CEK EMAIL/APP PASS! IMAP Aktif?{RESET}"); running = False; return
                    else: print(f"{YELLOW}   -> Retry dalam {wait_time}d...{RESET}"); time.sleep(wait_time); continue

            # Loop Cek Email (logika sama, update pesan tunggu)
            while running:
                try: # IMAP health check
                    status, _ = mail.noop();
                    if status != 'OK': print(f"\n{status_warn} {YELLOW}IMAP NOOP fail ({status}). Reconnecting...{RESET}"); break
                except (imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError) as NopErr: print(f"\n{status_warn} {YELLOW}IMAP disconnected ({type(NopErr).__name__}). Reconnecting...{RESET}"); break

                # Cek Email Baru (logika sama)
                status, messages = mail.search(None, '(UNSEEN)');
                if status != 'OK': print(f"\n{status_nok} {RED}Gagal search: {status}. Reconnecting...{RESET}"); break
                email_ids = messages[0].split()
                if email_ids:
                    print(" " * (cols - 4), end='\r'); print(f"\n{BRIGHT_GREEN}{BOLD}✨ Ditemukan {len(email_ids)} email baru! Memproses... ✨{RESET}"); print("-" * (cols - 4))
                    for email_id in email_ids:
                        if not running: break
                        process_email(mail, email_id, settings, binance_client)
                    if not running: break
                    print("-" * (cols - 4)); print(f"{GREEN}✅ Selesai. Kembali mendengarkan...{RESET}"); print("-" * (cols - 4))
                else:
                    # Pesan tunggu dengan spinner adaptif
                    wait_interval = settings['check_interval_seconds']; spinner = spinner_chars[spinner_index % len(spinner_chars)]; spinner_index += 1
                    wait_message = f"{BLUE}{BOLD}{spinner}{RESET}{BLUE} Menunggu ({wait_interval}s)... {RESET}"
                    # Clear line before printing
                    print(" " * (cols - 4), end='\r')
                    print(wait_message, end='\r')
                    for i in range(wait_interval):
                         if not running: break
                         time.sleep(1)
                    if not running: break

            if mail and mail.state == 'SELECTED':
                try: mail.close()
                except Exception: pass
        # Exception Handling Luar (logika sama)
        except (ConnectionError, OSError, socket.error, socket.gaierror) as net_err: print(f"\n{status_nok} {RED}{BOLD}Network Error:{RESET} {net_err}"); print(f"{YELLOW}   -> Cek internet. Retry dalam {wait_time}d...{RESET}"); time.sleep(wait_time)
        except Exception as e: print(f"\n{status_nok} {RED}{BOLD}UNEXPECTED ERROR:{RESET}"); traceback.print_exc(); print(f"{YELLOW}   -> Recovery dalam {wait_time}d...{RESET}"); time.sleep(wait_time)
        finally:
            if mail:
                try:
                    if mail.state != 'LOGOUT': mail.logout()
                except Exception: pass
            mail = None
            if running: time.sleep(3)
    print(f"\n{BRIGHT_YELLOW}{BOLD}🛑 Listener dihentikan.{RESET}"); print("-"*(cols-4))


# --- Fungsi Menu Pengaturan ---
def show_settings(settings):
    # (Fungsi show_settings secara logika tetap sama, hanya update layout)
    global SETTINGS_ART
    while True:
        rows, cols = get_terminal_size()
        if cols < MIN_TERMINAL_WIDTH:
             clear_screen(); print(f"\n{YELLOW}Terminal terlalu sempit ({cols} cols). Minimal {MIN_TERMINAL_WIDTH} agar optimal.{RESET}"); input("Tekan Enter..."); return

        layout_width = cols - 4
        left_col_width = layout_width // 2 - 3

        wipe_effect(rows, cols, char='.')
        clear_screen()
        vertical_padding = max(1, (rows - len(SETTINGS_ART) - 10) // 2) # Padding atas
        print("\n" * vertical_padding)

        # Konten Kiri (Settings)
        left_content = []
        left_content.append(f"{BOLD}{BRIGHT_CYAN}⚙️=== Pengaturan Listener ===⚙️{RESET}")
        # ... (isi left_content sama seperti versi sebelumnya) ...
        left_content.append("-" * left_col_width)
        left_content.append(f"{BLUE}{BOLD}--- Email Settings ---{RESET}")
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
        lib_status = f"{GREEN}✅ Ready{RESET}" if BINANCE_AVAILABLE else f"{RED}❌ Missing!{RESET}"
        left_content.append(f" Library     : {lib_status}")
        api_key_disp = '[Hidden]' if settings['binance_api_key'] else f"{YELLOW}[Kosong]{RESET}"
        api_sec_disp = '[Hidden]' if settings['binance_api_secret'] else f"{YELLOW}[Kosong]{RESET}"
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


        # Cetak Layout
        import re # Dibutuhkan untuk print_centered jika ada ANSI
        print_centered(f"{REVERSE}{WHITE}{BOLD} PENGATURAN {RESET}", layout_width)
        draw_two_column_layout(left_content, SETTINGS_ART, total_width=layout_width, left_col_width=left_col_width, padding=4)
        print_separator(char="=", length=layout_width, color=BRIGHT_CYAN)

        choice = input(f"{BOLD}{WHITE}Pilihan Anda (E/K): {RESET}").lower().strip()

        if choice == 'e':
             # --- Proses Edit (logika sama persis) ---
            print(f"\n{BOLD}{MAGENTA}--- Edit Pengaturan ---{RESET} {DIM}(Kosongkan untuk skip){RESET}")
            # Email
            print(f"\n{CYAN}--- Email ---{RESET}")
            new_val = input(f" 1. Email [{settings['email_address']}]: ").strip();
            if new_val: settings['email_address'] = new_val
            try: new_pass = getpass.getpass(f" 2. App Pass Baru [{pwd_disp}] (ketik u/ ubah): ").strip();
            except Exception: new_pass = input(f" 2. App Pass Baru (terlihat) [{pwd_disp}]: ").strip()
            if new_pass: settings['app_password'] = new_pass; print(f"   {GREEN}Password diperbarui.{RESET}")
            new_val = input(f" 3. Server IMAP [{settings['imap_server']}]: ").strip();
            if new_val: settings['imap_server'] = new_val
            while True:
                new_val_str = input(f" 4. Interval [{settings['check_interval_seconds']}s], min 5: ").strip();
                if not new_val_str: break
                try: new_interval = int(new_val_str);
                except ValueError: print(f"   {RED}Masukkan angka.{RESET}"); continue
                if new_interval >= 5: settings['check_interval_seconds'] = new_interval; break
                else: print(f"   {RED}Minimal 5 detik.{RESET}")
            new_val = input(f" 5. Target KW [{settings['target_keyword']}]: ").strip();
            if new_val: settings['target_keyword'] = new_val
            new_val = input(f" 6. Trigger KW [{settings['trigger_keyword']}]: ").strip();
            if new_val: settings['trigger_keyword'] = new_val
            # Binance
            print(f"\n{CYAN}--- Binance ---{RESET}");
            if not BINANCE_AVAILABLE: print(f"{YELLOW}   (Library Binance tidak ada){RESET}")
            new_val = input(f" 7. API Key [{api_key_disp}]: ").strip();
            if new_val: settings['binance_api_key'] = new_val
            try: new_secret = getpass.getpass(f" 8. API Secret Baru [{api_sec_disp}] (ketik u/ ubah): ").strip();
            except Exception: new_secret = input(f" 8. API Secret Baru (terlihat) [{api_sec_disp}]: ").strip()
            if new_secret: settings['binance_api_secret'] = new_secret; print(f"   {GREEN}Secret Key diperbarui.{RESET}")
            new_val = input(f" 9. Trading Pair [{settings['trading_pair']}]: ").strip().upper();
            if new_val: settings['trading_pair'] = new_val
            while True:
                new_val_str = input(f"10. Buy Quote Qty [{settings['buy_quote_quantity']}], > 0: ").strip();
                if not new_val_str: break
                try: new_qty = float(new_val_str);
                except ValueError: print(f"   {RED}Masukkan angka.{RESET}"); continue
                if new_qty > 0: settings['buy_quote_quantity'] = new_qty; break
                else: print(f"   {RED}Harus > 0.{RESET}")
            while True:
                new_val_str = input(f"11. Sell Base Qty [{settings['sell_base_quantity']}], >= 0: ").strip();
                if not new_val_str: break
                try: new_qty = float(new_val_str);
                except ValueError: print(f"   {RED}Masukkan angka.{RESET}"); continue
                if new_qty >= 0: settings['sell_base_quantity'] = new_qty; break
                else: print(f"   {RED}Harus >= 0.{RESET}")
            while True:
                 exec_prompt = f"{GREEN}Aktif{RESET}" if settings['execute_binance_orders'] else f"{RED}Nonaktif{RESET}"; new_val_str = input(f"12. Eksekusi Order? (y/n) [{exec_prompt}]: ").lower().strip();
                 if not new_val_str: break
                 if new_val_str == 'y': settings['execute_binance_orders'] = True; print(f"   {GREEN}Eksekusi Diaktifkan.{RESET}"); break
                 elif new_val_str == 'n': settings['execute_binance_orders'] = False; print(f"   {RED}Eksekusi Dinonaktifkan.{RESET}"); break
                 else: print(f"   {RED}Masukkan 'y' atau 'n'.{RESET}")

            save_settings(settings)
            input(f"\n{GREEN}{BOLD}✅ Pengaturan disimpan!{RESET} Tekan Enter...")

        elif choice == 'k': break
        else: print(f"{RED}[ERROR] Pilihan tidak valid.{RESET}"); time.sleep(1)

# --- Fungsi Menu Utama ---
def main_menu():
    global ROCKET_ART
    settings = load_settings()
    startup_animation()

    while True:
        settings = load_settings()
        rows, cols = get_terminal_size()

        # Cek lebar terminal
        if cols < MIN_TERMINAL_WIDTH:
            clear_screen()
            print(f"\n{BRIGHT_YELLOW}{BOLD}PERINGATAN:{RESET}")
            print(f"{YELLOW}Lebar terminal Anda terlalu sempit ({cols} kolom).")
            print(f"Layout mungkin tidak tampil optimal. Rekomendasi minimal: {MIN_TERMINAL_WIDTH} kolom.")
            print("\nSilakan perbesar window terminal Anda.")
            print("\nOpsi:")
            print(" 1. Coba tampilkan menu (mungkin berantakan)")
            print(" 2. Keluar")
            choice = input("Pilihan (1/2): ").strip()
            if choice == '2':
                 clear_screen(); print(f"\n{CYAN}Keluar...{RESET}"); sys.exit(0)
            # Jika pilih 1, lanjut tapi layout mungkin rusak

        # Hitung layout dinamis
        layout_width = cols - 4
        left_col_width = layout_width // 2 - 3
        vertical_padding = max(1, (rows - len(ROCKET_ART) - 10) // 2) # Padding atas dinamis

        wipe_effect(rows, cols, char=random.choice(['*', '#', '+', '.']), delay=0.003)
        clear_screen()
        print("\n" * vertical_padding) # Terapkan padding atas

        # --- Konten Kiri (Menu Utama) ---
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
        left_content.append(f"{BOLD}{WHITE}Status Cepat:{RESET}")
        email_ok = bool(settings['email_address']) and bool(settings['app_password'])
        email_status = status_ok if email_ok else status_nok
        left_content.append(f" Email Config : [{email_status}]")
        exec_on = settings.get("execute_binance_orders", False); exec_status_label = f"{GREEN}AKTIF{RESET}" if exec_on else f"{YELLOW}NONAKTIF{RESET}"
        lib_status = status_ok if BINANCE_AVAILABLE else status_nok + f" {RED}Missing!{RESET}"
        left_content.append(f" Binance Lib  : [{lib_status}] | Eksekusi: [{exec_status_label}]")
        if exec_on and BINANCE_AVAILABLE:
            api_ok = bool(settings['binance_api_key']) and bool(settings['binance_api_secret']); pair_ok = bool(settings['trading_pair']); qty_ok = settings['buy_quote_quantity'] > 0 and settings['sell_base_quantity'] >= 0
            bin_status = status_ok if api_ok and pair_ok and qty_ok else status_warn
            left_content.append(f" Binance Cfg  : [{bin_status}] (API/Pair/Qty)")
        elif exec_on and not BINANCE_AVAILABLE: left_content.append(f" Binance Cfg  : [{status_nok}] {RED}(Library Error){RESET}")
        left_content.append("-" * left_col_width)

        # Cetak Layout
        import re # Untuk print_centered
        # print_centered(f"{REVERSE}{WHITE}{BOLD} MENU UTAMA {RESET}", layout_width) # Optional Title
        draw_two_column_layout(left_content, ROCKET_ART, total_width=layout_width, left_col_width=left_col_width, padding=4)
        print_separator(char="=", length=layout_width, color=BRIGHT_MAGENTA)

        choice = input(f"{BOLD}{WHITE}Masukkan pilihan Anda (1/2/3): {RESET}").strip()

        if choice == '1':
            # Validasi sebelum mulai (logika sama)
            valid = True; error_msgs = []
            if not email_ok: error_msgs.append("Email/App Password belum diatur!"); valid = False
            if exec_on and not BINANCE_AVAILABLE: error_msgs.append("Eksekusi aktif tapi library Binance error!"); valid = False
            if exec_on and BINANCE_AVAILABLE and not (api_ok and pair_ok and qty_ok): error_msgs.append("Eksekusi aktif tapi config Binance (API/Pair/Qty) belum lengkap/valid.") # No longer sets valid=False here

            if not valid:
                 print(f"\n{RED}{BOLD} Gagal memulai:{RESET}")
                 for msg in error_msgs: print(f"{RED} - {msg}{RESET}")
                 print(f"\n{YELLOW}Silakan perbaiki di menu 'Pengaturan'.{RESET}")
                 input(f"{DIM}Tekan Enter untuk kembali...{RESET}")
            else:
                 if error_msgs: # Show warnings if any, but proceed
                      print(f"\n{YELLOW}{BOLD}Peringatan:{RESET}")
                      for msg in error_msgs: print(f"{YELLOW} - {msg}{RESET}")
                      input(f"{DIM}Tekan Enter untuk melanjutkan listener...{RESET}")
                 start_listening(settings)
                 print(f"\n{YELLOW}[INFO] Kembali ke Menu Utama...{RESET}")
                 input(f"{DIM}Tekan Enter untuk melanjutkan...{RESET}")

        elif choice == '2':
            show_settings(settings)
        elif choice == '3':
            clear_screen(); print("\n" * (rows // 3)); print_centered(f"{BRIGHT_CYAN}{BOLD}👋 Terima kasih! Sampai jumpa! 👋{RESET}", cols); print("\n" * 5); sys.exit(0)
        else:
            print(f"\n{RED}{BOLD} Pilihan tidak valid! Masukkan 1, 2, atau 3.{RESET}"); time.sleep(1.5)


# --- Entry Point ---
if __name__ == "__main__":
    # (Entry point tetap sama)
    import re # Impor re di scope global jika belum
    try:
        main_menu()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}{BOLD}Program dihentikan paksa.{RESET}")
        sys.exit(1)
    except Exception as e:
        clear_screen()
        print(f"\n{BOLD}{RED}╔════════════════════════════╗{RESET}")
        print(f"{BOLD}{RED}║      💥 ERROR KRITIS 💥     ║{RESET}")
        print(f"{BOLD}{RED}╚════════════════════════════╝{RESET}")
        print(f"\n{RED}Terjadi error yang tidak dapat dipulihkan:{RESET}")
        traceback.print_exc()
        print(f"\n{RED}Pesan Error: {e}{RESET}")
        print("\nProgram akan ditutup.")
        sys.exit(1)
