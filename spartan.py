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
# (Kode Binance Integration tetap sama - TIDAK DIUBAH)
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

# --- Kode Warna ANSI & Style (TETAP SAMA) ---
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"
BLINK = "\033[5m" # Hindari
REVERSE = "\033[7m"
HIDDEN = "\033[8m"
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
spinner_chars = ['🛡️ ', ' 🗡️ ', ' 🏹', '🛡️ '] # Spartan theme spinner
# spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'] # Braille spinner
# spinner_chars = ['-', '\\', '|', '/'] # Classic spinner
loading_bar_char = '█'
wipe_chars = ['▓', '▒', '░', '*','+','#'] # Variasi wipe
status_ok = f"{GREEN}✔{RESET}"
status_nok = f"{RED}✘{RESET}"
status_warn = f"{YELLOW}⚠{RESET}"
status_wait = f"{BLUE}⏳{RESET}"
status_conn = f"{CYAN}🔗{RESET}"
status_email = f"{MAGENTA}📧{RESET}"
status_money = f"{GREEN}💰{RESET}"
status_target = f"{YELLOW}🎯{RESET}"
status_action = f"{BRIGHT_BLUE}⚡{RESET}"

# --- ASCII Art (TEMA SPARTA) ---
# Cari "spartan helmet ascii art" atau sejenisnya
# Pastikan lebarnya tidak terlalu besar untuk layout 2 kolom
SPARTAN_FACE_ART = [
    f"          {DIM}█████████████{RESET}",
    f"      {DIM}███████████████████{RESET}",
    f"     {DIM}████{RESET} {BOLD}{WHITE}██      ██{RESET} {DIM}████{RESET}",
    f"    {DIM}███{RESET}   {BOLD}{WHITE}██{RED}████{RESET}{BOLD}{WHITE}██{RESET}   {DIM}███{RESET}",
    f"   {DIM}███{RESET}    {BOLD}{WHITE}██████{RESET}    {DIM}███{RESET}",
    f"  {DIM}███{RESET}    {BOLD}{WHITE}(____){RESET}     {DIM}███{RESET}",
    f" {DIM}███{RESET}      {RED}\\/{RESET}{BOLD}{WHITE}/{RESET}       {DIM}███{RESET}",
    f" {DIM}██{RESET}       {RED}\\{RESET}{BOLD}{WHITE}//{RESET}        {DIM}██{RESET}",
    f" {DIM}██{RESET}       {RED}| |{RESET}        {DIM}██{RESET}",
    f" {DIM}██{RESET}      {RED}/ /\\{RESET}        {DIM}██{RESET}",
    f"  {DIM}███{RESET}    {RED}/_/--\\_{RESET}    {DIM}███{RESET}",
    f"   {DIM}████{RESET} {RED}(____){RESET}    {DIM}████{RESET}",
    f"     {DIM}██████████████{RESET}",
    f"       {DIM}███████████{RESET}",
    f"       {BOLD}{YELLOW}THIS IS SPARTA!{RESET}" # Tambahan
]

SPARTAN_SHIELD_ART = [ # Art untuk halaman setting
    f"    {DIM}_______",
    f"   {DIM}/ _____ \\",
    f"  {DIM}| |     | |",
    f"  {DIM}| |{RESET}  Λ  {DIM}| |", # Lambda symbol
    f"  {DIM}| |_____| |",
    f"   {DIM}\\_______/",
    f"     {DIM} V",
]

# --- Fungsi Utilitas Tampilan (DIMODIFIKASI & DITAMBAH) ---
def clear_screen():
    """Membersihkan layar terminal."""
    os.system('cls' if os.name == 'nt' else 'clear')

def get_terminal_size():
    """Mendapatkan ukuran terminal (baris, kolom). Fallback ke default."""
    try:
        columns, rows = os.get_terminal_size(0)
    except (OSError, AttributeError, NameError, ValueError):
        try:
            rows, columns = map(int, os.popen('stty size', 'r').read().split())
        except ValueError:
            rows, columns = 24, 80 # Default aman
    return rows, columns

def print_centered(text, width, color=RESET, fill_char=" "):
    """Mencetak teks di tengah dengan padding."""
    # Hati-hati: ANSI codes kacaukan perhitungan panjang standar len()
    # Solusi sederhana: hitung panjang teks tanpa ANSI (belum diimplementasikan di sini)
    # Untuk sekarang, asumsi ANSI hanya di awal/akhir atau tidak signifikan
    text_len = len(text) - text.count('\033') * 5 # Estimasi kasar panjang ANSI
    if text_len < 0: text_len = len(text) # Fallback jika estimasi aneh
    padding = (width - text_len) // 2
    padding = max(0, padding) # Pastikan tidak negatif
    print(f"{color}{fill_char * padding}{text}{fill_char * padding}{RESET}")

def print_separator(char="─", width=80, color=DIM + WHITE + RESET, animated=False, delay=0.005):
    """Mencetak garis pemisah, bisa animasi."""
    line = char * width
    if animated and width > 0:
        for i in range(width):
             sys.stdout.write(f"\r{color}{char * (i+1)}{RESET}")
             sys.stdout.flush()
             time.sleep(delay)
        print() # Pindah baris setelah selesai
    else:
        print(f"{color}{line}{RESET}")

def wipe_effect(rows, cols, char=None, delay=0.005, color=DIM):
    """Efek wipe dari atas/bawah ke tengah atau sebaliknya."""
    if char is None:
        char = random.choice(wipe_chars) # Pilih karakter wipe acak jika tidak dispesifik
    direction = random.choice(['in', 'out']) # Wipe masuk atau keluar

    if direction == 'in':
        for r in range(rows // 2):
            line = char * cols
            sys.stdout.write(f"\033[{r + 1};1H{color}{line}{RESET}") # Baris atas
            sys.stdout.write(f"\033[{rows - r};1H{color}{line}{RESET}") # Baris bawah
            sys.stdout.flush()
            time.sleep(delay)
    else: # Wipe out (dari tengah ke luar)
        mid_row = rows // 2
        for r in range(mid_row, 0, -1):
            line = " " * cols # Karakter spasi untuk menghapus
            sys.stdout.write(f"\033[{mid_row - r + 1};1H{line}{RESET}") # Baris atas tengah -> luar
            sys.stdout.write(f"\033[{mid_row + r};1H{line}{RESET}")     # Baris bawah tengah -> luar
            sys.stdout.flush()
            time.sleep(delay)
        # Pastikan tengah bersih (jika rows ganjil)
        sys.stdout.write(f"\033[{mid_row + 1};1H{' ' * cols}{RESET}")
        sys.stdout.flush()


def draw_two_column_layout(left_lines, right_lines, total_width=90, left_width=45, padding=4, color=RESET):
    """
    Mencetak dua kolom bersebelahan.
    Hati-hati dengan ANSI codes dalam perhitungan lebar.
    """
    right_width = total_width - left_width - padding
    max_lines = max(len(left_lines), len(right_lines))
    spacer = " " * padding

    # Fungsi helper SANGAT SEDERHANA untuk strip ANSI (tanpa regex)
    def simple_strip_ansi(line):
        in_escape = False
        result = ""
        for char in line:
            if char == '\033':
                in_escape = True
            elif in_escape and char == 'm':
                in_escape = False
            elif not in_escape:
                result += char
        return result

    for i in range(max_lines):
        left_part = left_lines[i].rstrip() if i < len(left_lines) else ""
        right_part = right_lines[i].rstrip() if i < len(right_lines) else ""

        # Hitung panjang visual (tanpa ANSI) untuk padding
        left_len_visual = len(simple_strip_ansi(left_part))

        # Pad left part agar lebarnya konsisten secara visual
        padding_needed = max(0, left_width - left_len_visual)
        left_padded = left_part + (" " * padding_needed)

        # Gabungkan dan cetak (asumsi right_part adalah ASCII art, tidak perlu padding kanan)
        print(f"{color}{left_padded}{spacer}{right_part}{RESET}")

def startup_animation():
    """Animasi startup baru yang lebih meriah."""
    clear_screen()
    rows, cols = get_terminal_size()
    brand = f"🛡️ {BOLD}{YELLOW}Exora AI Listener{RESET} 🛡️ {DIM}(Spartan Edition){RESET}"
    stages = [
        "Mempersiapkan Perisai...",
        "Menajamkan Tombak...",
        "Mengecek Formasi Phalanx...",
        "Menghubungi Oracle Delphi...", # Fun
        "Mengumpulkan Hoplite...",
        "SIAP TEMPUR!"
    ]
    bar_width = min(40, cols - 20) # Lebar progress bar

    # Gambar Spartan di tengah atas (jika cukup ruang)
    if rows > len(SPARTAN_FACE_ART) + 15: # Cek jika cukup baris
        art_start_row = 3
        art_padding = (cols - len(simple_strip_ansi(SPARTAN_FACE_ART[0]))) // 2
        for i, line in enumerate(SPARTAN_FACE_ART):
            sys.stdout.write(f"\033[{art_start_row + i};{art_padding}H{line}{RESET}")

    # Posisi progress bar di bawah
    progress_row = rows // 2 + 3
    title_row = progress_row - 2

    sys.stdout.write(f"\033[{title_row};1H") # Pindah ke baris judul
    print_centered(brand, cols, BOLD + YELLOW)
    sys.stdout.write(f"\033[{progress_row};1H") # Pindah ke baris progress

    for i, stage in enumerate(stages):
        percent = int(((i + 1) / len(stages)) * 100)
        filled_width = int(bar_width * (percent / 100))
        bar = loading_bar_char * filled_width + DIM + '-' * (bar_width - filled_width) + RESET
        progress_text = f"{YELLOW}{BOLD}[{bar}{YELLOW}{BOLD}] {percent}%{RESET} {CYAN}- {stage}{RESET}"

        # Hapus baris sebelumnya (progress & status)
        sys.stdout.write(f"\033[{progress_row};1H" + " " * (cols-1))
        sys.stdout.write(f"\033[{progress_row + 1};1H" + " " * (cols-1))
        sys.stdout.write(f"\033[{progress_row};1H") # Kembali ke baris progress

        print_centered(progress_text, cols) # Cetak progress bar & persen
        # print_centered(f"{CYAN}{stage}{RESET}" + " " * 10, cols) # Cetak status message

        sys.stdout.flush()
        time.sleep(random.uniform(0.3, 0.8)) # Delay acak

    sys.stdout.write(f"\033[{progress_row + 2};1H") # Baris setelah progress
    print_centered(f"{GREEN}{BOLD}✅ Sistem Siap! FOR SPARTA!{RESET}", cols)
    time.sleep(1.5)
    wipe_effect(rows, cols, char='*', delay=0.004, color=YELLOW) # Efek wipe sebelum ke menu

# --- Fungsi Penanganan Sinyal (Ctrl+C) ---
# (Tetap sama - TIDAK DIUBAH)
def signal_handler(sig, frame):
    global running
    rows, cols = get_terminal_size()
    print(f"\n{BRIGHT_YELLOW}{BOLD}🛑 PERINTAH BERHENTI DITERIMA! Mundur teratur...{RESET}")
    running = False
    # Animasi keluar sederhana
    farewell = f"👋 {RED}{BOLD}AHOO! AHOO! Sampai jumpa!{RESET} 👋"
    print("\n" * (rows // 3))
    print_centered(farewell, cols, RED)
    print("\n")
    print_separator(char="*", width=cols-4, color=RED, animated=True, delay=0.01)
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# --- Fungsi Konfigurasi ---
# (Load & Save Settings tetap sama fungsinya, hanya visual feedback ditambah)
def load_settings():
    """Memuat pengaturan dari file JSON dengan visual feedback."""
    # print(f"{DIM}💾 Memuat {CONFIG_FILE}...{RESET}", end='\r') # Kurang efektif jika cepat
    settings = DEFAULT_SETTINGS.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_settings = json.load(f)
                for key in DEFAULT_SETTINGS:
                    if key in loaded_settings:
                        settings[key] = loaded_settings[key]
                # Validasi (sama seperti sebelumnya)
                settings["check_interval_seconds"] = max(5, int(settings.get("check_interval_seconds", 10)))
                settings["buy_quote_quantity"] = max(0.0, float(settings.get("buy_quote_quantity", 11.0)))
                settings["sell_base_quantity"] = max(0.0, float(settings.get("sell_base_quantity", 0.0)))
                settings["execute_binance_orders"] = bool(settings.get("execute_binance_orders", False))
                # Diam-diam simpan jika ada koreksi
                save_settings(settings, silent=True, initial_load=True)
            # print(f"{status_ok} {GREEN}Pengaturan dimuat dari {CONFIG_FILE}.{RESET}")
        except json.JSONDecodeError:
            print(f"{status_nok} {RED}[ERROR] File konfigurasi '{CONFIG_FILE}' rusak! Menggunakan default & menyimpan ulang.{RESET}")
            save_settings(settings) # Simpan default yang baru
        except Exception as e:
            print(f"{status_nok} {RED}[ERROR] Gagal memuat konfigurasi: {e}{RESET}")
            print(f"{status_warn} {YELLOW}[WARN] Menggunakan pengaturan default sementara.{RESET}")
            # Tidak save jika error loading selain JSONDecode
    else:
        print(f"{status_warn} {YELLOW}[INFO] File '{CONFIG_FILE}' tidak ditemukan. Membuat dengan nilai default.{RESET}")
        save_settings(settings) # Simpan default untuk pertama kali
    # Pemeriksaan Binance Library setelah load settings
    if not BINANCE_AVAILABLE:
        print(f"{status_warn} {YELLOW}{BOLD}Library 'python-binance' tidak ditemukan.{RESET} {DIM}Fitur Binance tidak akan berfungsi.{RESET}")
    return settings

def save_settings(settings, silent=False, initial_load=False):
    """Menyimpan pengaturan ke file JSON dengan visual feedback."""
    if not silent and not initial_load:
         print(f"{DIM}💾 Menyimpan pengaturan ke {CONFIG_FILE}...{RESET}", end='\r')
    try:
        settings_to_save = {key: settings[key] for key in DEFAULT_SETTINGS if key in settings}
        # Validasi tipe data sebelum save (sama)
        settings_to_save['check_interval_seconds'] = int(settings_to_save.get('check_interval_seconds', 10))
        settings_to_save['buy_quote_quantity'] = float(settings_to_save.get('buy_quote_quantity', 11.0))
        settings_to_save['sell_base_quantity'] = float(settings_to_save.get('sell_base_quantity', 0.0))
        settings_to_save['execute_binance_orders'] = bool(settings_to_save.get('execute_binance_orders', False))

        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings_to_save, f, indent=4, sort_keys=True)
        if not silent:
            print(f"{status_ok} {GREEN}{BOLD}Pengaturan berhasil disimpan ke '{CONFIG_FILE}'.{RESET}{' '*10}")
    except Exception as e:
        print(f"{status_nok} {RED}[ERROR] Gagal menyimpan konfigurasi: {e}{RESET}{' '*10}")

# --- Fungsi Utilitas Lain ---
# (decode_mime_words, get_text_from_email tetap sama fungsinya)
# (trigger_beep sedikit dimodifikasi visualnya)
def get_timestamp():
    """Format timestamp standar."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def decode_mime_words(s):
    # (Tetap sama - KRUSIAL)
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
    # (Tetap sama - KRUSIAL)
    text_content = ""
    # Tambahkan feedback kecil
    # print(f"{DIM}   Menganalisa bagian email...{RESET}", end='\r')
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
                    print(f"{status_warn} {YELLOW}Tidak bisa mendekode bagian email (text/plain): {e}{RESET}")
    else:
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                text_content = payload.decode(charset, errors='replace')
            except Exception as e:
                 print(f"{status_warn} {YELLOW}Tidak bisa mendekode body email (non-multipart): {e}{RESET}")
    # print(f"{DIM}   Analisa email selesai.      {RESET}")
    return text_content.lower() # Langsung lowercase

def trigger_beep(action):
    """Memainkan suara beep sesuai aksi dengan visual Spartan."""
    try:
        action_upper = action.upper()
        action_color = GREEN if action == "buy" else RED if action == "sell" else MAGENTA
        icon = "📈" if action == "buy" else "📉" if action == "sell" else "🔔"
        print(f"{action_color}{BOLD}{icon} BEEP! SERUAN {action_upper}! {icon}{RESET}")
        # Coba 'beep' atau fallback ke '\a'
        try:
            cmd = []
            if action == "buy":
                # Nada naik (misal: 3 nada pendek naik)
                cmd = ["beep", "-f", "800", "-l", "100", "-n", "-f", "1000", "-l", "100", "-n", "-f", "1200", "-l", "200"]
            elif action == "sell":
                # Nada turun (misal: 2 nada panjang turun)
                 cmd = ["beep", "-f", "1000", "-l", "300", "-n", "-f", "700", "-l", "400"]
            else:
                cmd = ["beep", "-f", "500", "-l", "150"] # Default beep pendek

            # Jalankan subprocess jika cmd ada
            if cmd:
                 subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=2)
            else:
                 print("\a", end='') # Bell standar jika action tidak dikenali

        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
            # Fallback jika 'beep' gagal atau tidak ada
            print("\a", end='') # Bell standar sistem
            sys.stdout.flush() # Pastikan bunyi
    except Exception as e:
        print(f"{status_nok} {RED}[ERROR] Kesalahan tak terduga saat beep: {e}{RESET}")

# --- Fungsi Eksekusi Binance ---
# (get_binance_client & execute_binance_order tetap sama fungsinya, visual diperkuat)
def get_binance_client(settings):
    """Mendapatkan client Binance dengan visual feedback koneksi."""
    if not BINANCE_AVAILABLE:
        print(f"{status_nok} {RED}{BOLD}Library Binance tidak tersedia.{RESET}")
        return None
    if not settings.get('binance_api_key') or not settings.get('binance_api_secret'):
        print(f"{status_nok} {RED}{BOLD}API Key/Secret Binance kosong! Tidak bisa konek.{RESET}")
        return None

    spinner = itertools.cycle(spinner_chars)
    print(f"{status_conn} {CYAN}Menghubungi Markas Komando Binance...", end='', flush=True)
    client = None
    try:
        # Animasi kecil saat konek
        for _ in range(random.randint(5, 10)): # Simulasi waktu koneksi
            print(f"\r{status_conn} {CYAN}Menghubungi Markas Komando Binance... {next(spinner)}{RESET}", end='', flush=True)
            time.sleep(0.15)

        client = Client(settings['binance_api_key'], settings['binance_api_secret'])
        # Test ping
        print(f"\r{status_conn} {CYAN}Mengirim Sinyal Ping ke Binance... {next(spinner)}{RESET}", end='', flush=True)
        ping_start = time.time()
        client.ping()
        ping_ms = (time.time() - ping_start) * 1000
        print(f"\r{status_ok} {GREEN}{BOLD}Ping Binance Berhasil! ({ping_ms:.0f} ms){RESET}{' '*20}")

        # Test koneksi akun (opsional, bisa lambat)
        print(f"{status_wait} {CYAN}Memverifikasi Kredensial Akun... {next(spinner)}{RESET}", end='\r', flush=True)
        acc_info = client.get_account()
        print(f"\r{status_ok} {GREEN}{BOLD}Koneksi & Autentikasi Binance SUKSES!{RESET}{' '*20}")
        # print(f"{DIM}   -> Status Akun: {acc_info.get('accountType', 'N/A')}, Bisa Trading: {acc_info.get('canTrade', '?')}{RESET}")
        return client
    except BinanceAPIException as e:
        print(f"\r{status_nok} {RED}{BOLD}Koneksi/Auth Binance GAGAL:{RESET} {e.status_code} - {e.message}{' '*10}")
        return None
    except Exception as e:
        print(f"\r{status_nok} {RED}{BOLD}Gagal membuat Binance client:{RESET} {e}{' '*20}")
        return None

def execute_binance_order(client, settings, side):
    """Eksekusi order Binance dengan visual feedback lebih detail."""
    if not client:
        print(f"{status_warn} {YELLOW}Eksekusi dibatalkan, client Binance tidak valid.{RESET}")
        return False
    if not settings.get("execute_binance_orders", False):
        # Seharusnya tidak sampai sini jika cek di awal, tapi sebagai safety
        print(f"{status_warn} {YELLOW}Eksekusi order dinonaktifkan (SAFETY CHECK). Order dilewati.{RESET}")
        return False

    pair = settings.get('trading_pair', '').upper()
    if not pair:
        print(f"{status_nok} {RED}{BOLD}Trading pair belum diatur di konfigurasi!{RESET}")
        return False

    order_details = {}
    action_desc = ""
    side_color = BRIGHT_GREEN if side == Client.SIDE_BUY else BRIGHT_RED
    side_icon = "🛒" if side == Client.SIDE_BUY else "💰" # atau 🛡️ 🗡️ ?
    side_name = "BELI" if side == Client.SIDE_BUY else "JUAL"

    print(f"\n{side_color}⚔️ {BOLD}--- PERSIAPAN STRATEGI {side_name} ({pair}) ---{RESET} ⚔️")

    try:
        if side == Client.SIDE_BUY:
            quote_qty = settings.get('buy_quote_quantity', 0.0)
            if quote_qty <= 0:
                 print(f"{status_nok} {RED}Kuantitas Beli (buy_quote_quantity) harus > 0.{RESET}")
                 return False
            order_details = {'symbol': pair, 'side': Client.SIDE_BUY, 'type': Client.ORDER_TYPE_MARKET, 'quoteOrderQty': quote_qty}
            quote_asset = pair[3:] if len(pair) > 3 else "QUOTE" # Estimasi Quote Asset
            action_desc = f"{side_icon} {BOLD}MARKET {side_name}{RESET} {quote_qty} {quote_asset} untuk {pair}"

        elif side == Client.SIDE_SELL:
            base_qty = settings.get('sell_base_quantity', 0.0)
            if base_qty <= 0:
                 if settings.get('sell_base_quantity') == 0.0: # Angka 0.0 sengaja di setting
                    print(f"{status_warn} {YELLOW}Kuantitas Jual (sell_base_quantity) adalah 0. Order {side_name} dilewati.{RESET}")
                 else: # Angka negatif atau tidak valid
                    print(f"{status_nok} {RED}Kuantitas Jual (sell_base_quantity) harus >= 0.{RESET}")
                 return False # Jangan eksekusi jika <= 0
            order_details = {'symbol': pair, 'side': Client.SIDE_SELL, 'type': Client.ORDER_TYPE_MARKET, 'quantity': base_qty}
            base_asset = pair[:3] if len(pair) > 3 else "BASE" # Estimasi Base Asset
            action_desc = f"{side_icon} {BOLD}MARKET {side_name}{RESET} {base_qty} {base_asset} dari {pair}"
        else:
            print(f"{status_nok} {RED}Sisi order tidak valid: {side}{RESET}")
            return False

        print(f"{status_action} {CYAN}Mengirim Perintah Serangan: {action_desc}...{RESET}")
        # Simulasi delay kecil
        time.sleep(random.uniform(0.5, 1.0))

        # ---- INI BAGIAN PENTING EKSEKUSI ----
        order_start_time = time.time()
        order_result = client.create_order(**order_details)
        order_exec_time = time.time() - order_start_time
        # ------------------------------------

        print(f"{side_color}{BOLD}✅ SERANGAN {side_name} BERHASIL DIEKSEKUSI!{RESET} (Waktu: {order_exec_time:.2f} detik)")
        print(f"{DIM}┌──────────────────────────────────────────┐")
        print(f"{DIM}│ {BOLD}Laporan Pertempuran (Order ID: {order_result.get('orderId')}){RESET}{DIM} │")
        print(f"{DIM}├──────────────────────────────────────────┤")
        print(f"{DIM}│ Symbol   : {order_result.get('symbol', 'N/A'):<15} Status: {order_result.get('status', 'N/A'):<12} │")
        print(f"{DIM}│ Side     : {order_result.get('side', 'N/A'):<15} Type  : {order_result.get('type', 'N/A'):<12} │")
        if order_result.get('fills'):
            total_qty = sum(float(f['qty']) for f in order_result['fills'])
            total_quote_qty = sum(float(f['commission']) if f['commissionAsset'] == pair[3:] else float(f['cummulativeQuoteQty']) for f in order_result['fills']) # Coba pakai cummulativeQuoteQty
            avg_price = total_quote_qty / total_qty if total_qty else 0.0
            commission = sum(float(f['commission']) for f in order_result['fills'])
            commission_asset = order_result['fills'][0]['commissionAsset'] if order_result['fills'] else '?'

            print(f"{DIM}├─────────── HASIL PERTEMPURAN ──────────┤")
            print(f"{DIM}│ Avg Price: {avg_price:<25.8f} │") # Format rata kiri
            print(f"{DIM}│ Filled Qty: {total_qty:<24.8f} │") # Base Asset
            print(f"{DIM}│ Total Cost: {total_quote_qty:<24.4f} │") # Quote Asset
            print(f"{DIM}│ Komisi   : {commission:<18.8f} {commission_asset:<6} │")
        else:
             print(f"{DIM}│ {YELLOW}(Tidak ada detail 'fills' diterima){RESET}{DIM}        │")
        print(f"{DIM}└──────────────────────────────────────────┘{RESET}")
        return True

    except BinanceAPIException as e:
        print(f"\r{status_nok} {RED}{BOLD}BINANCE API ERROR:{RESET} {e.status_code} - {e.message}{' '*10}")
        if e.code == -2010: print(f"{RED}{BOLD}      -> Dana Perang (Saldo) TIDAK CUKUP?{RESET}")
        elif e.code == -1121: print(f"{RED}{BOLD}      -> Medan Perang ('{pair}') TIDAK VALID?{RESET}")
        elif e.code == -1013 or 'MIN_NOTIONAL' in str(e.message).upper(): print(f"{RED}{BOLD}      -> Jumlah Pasukan TERLALU KECIL (cek MIN_NOTIONAL)?{RESET}")
        elif e.code == -1111 or 'LOT_SIZE' in str(e.message).upper(): print(f"{RED}{BOLD}      -> Jumlah Pasukan tidak sesuai LOT_SIZE?{RESET}")
        return False
    except BinanceOrderException as e:
        print(f"\r{status_nok} {RED}{BOLD}BINANCE ORDER ERROR:{RESET} {e.status_code} - {e.message}{' '*10}")
        return False
    except Exception as e:
        print(f"\r{status_nok} {RED}{BOLD}ERROR EKSEKUSI BINANCE:{RESET}")
        traceback.print_exc()
        return False
    finally:
         print(f"{side_color}⚔️ {BOLD}--- AKHIR STRATEGI {side_name} ({pair}) ---{RESET} ⚔️\n")


# --- Fungsi Pemrosesan Email ---
def process_email(mail, email_id, settings, binance_client):
    """Memproses satu email dengan visual feedback."""
    global running
    if not running: return

    target_keyword_lower = settings['target_keyword'].lower()
    trigger_keyword_lower = settings['trigger_keyword'].lower()
    email_id_str = email_id.decode('utf-8')
    ts = get_timestamp()
    rows, cols = get_terminal_size() # Dapatkan ukuran terminal
    separator = f"{MAGENTA}{'=' * (cols // 2)}{RESET}"

    try:
        print(f"\n{separator}")
        print_centered(f"{status_email} {BOLD}Memproses Pesan Masuk ID: {email_id_str} [{ts}]{RESET}", cols, MAGENTA)
        print(f"{separator}")

        # --- Step 1: Fetch Email ---
        print(f"{status_wait} {DIM}Mengunduh data pesan...{RESET}", end='\r')
        status, data = mail.fetch(email_id, "(RFC822)")
        if status != 'OK':
            print(f"{status_nok} {RED}Gagal mengunduh pesan ID {email_id_str}: {status}   {RESET}")
            return
        print(f"{status_ok} {GREEN}Data pesan diterima.          {RESET}")

        # --- Step 2: Parse Email ---
        print(f"{status_wait} {DIM}Membongkar enkripsi pesan...{RESET}", end='\r')
        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        subject = decode_mime_words(msg["Subject"])
        sender = decode_mime_words(msg["From"])
        print(f"{status_ok} {GREEN}Enkripsi pesan terbongkar.     {RESET}")
        print(f"   {CYAN}Pengirim : {RESET}{sender}")
        print(f"   {CYAN}Judul    : {RESET}{subject}")
        print(f"{MAGENTA}-------------------------------------------{RESET}")

        # --- Step 3: Extract & Check Keywords ---
        print(f"{status_wait} {DIM}Memindai isi pesan untuk intelijen...{RESET}", end='\r')
        body = get_text_from_email(msg)
        full_content = (subject.lower() + " " + body)
        print(f"{status_ok} {GREEN}Pemindaian isi pesan selesai.         {RESET}")

        if target_keyword_lower in full_content:
            print(f"{status_target} {GREEN}{BOLD}Intelijen Target Ditemukan!{RESET} ('{settings['target_keyword']}')")
            try:
                target_index = full_content.find(target_keyword_lower)
                # Cari trigger SETELAH target
                trigger_index = full_content.find(trigger_keyword_lower, target_index + len(target_keyword_lower))

                if trigger_index != -1:
                    start_word_index = trigger_index + len(trigger_keyword_lower)
                    text_after_trigger = full_content[start_word_index:].lstrip()
                    words_after_trigger = text_after_trigger.split(maxsplit=1) # Ambil kata pertama setelah trigger

                    if words_after_trigger:
                        action_word = words_after_trigger[0].strip('.,!?:;()[]{}<>').lower() # Bersihkan karakter aneh
                        action_color = BRIGHT_GREEN if action_word == "buy" else BRIGHT_RED if action_word == "sell" else BRIGHT_YELLOW
                        print(f"{status_action} {action_color}{BOLD}Perintah Aksi Diterima!{RESET} ('{settings['trigger_keyword']}' -> '{action_word.upper()}')")

                        # --- Step 4: Trigger Action ---
                        if action_word == "buy" or action_word == "sell":
                            trigger_beep(action_word) # Bunyikan alarm perang!
                            if settings.get("execute_binance_orders"):
                                if binance_client:
                                    execute_binance_order(binance_client, settings, getattr(Client, f"SIDE_{action_word.upper()}"))
                                else:
                                    print(f"{status_warn} {YELLOW}Mode Eksekusi aktif tapi koneksi Binance belum siap/gagal.{RESET}")
                            elif action_word in ["buy", "sell"]:
                                 print(f"{DIM}   (Mode Latihan: Eksekusi Binance dinonaktifkan){RESET}")
                        else:
                            print(f"{status_warn} {YELLOW}Aksi '{action_word}' tidak dikenali (harus 'buy'/'sell'). Tidak ada serangan pasar.{RESET}")
                    else:
                        print(f"{status_warn} {YELLOW}Intelijen trigger '{settings['trigger_keyword']}' ada, tapi tidak ada perintah aksi setelahnya.{RESET}")
                else:
                     print(f"{status_warn} {YELLOW}Intelijen target '{settings['target_keyword']}' ada, tapi perintah trigger '{settings['trigger_keyword']}' tidak ditemukan SETELAHNYA.{RESET}")
            except Exception as e:
                 print(f"{status_nok} {RED}Gagal memproses perintah aksi setelah trigger: {e}{RESET}")
                 traceback.print_exc(limit=1) # Tampilkan traceback singkat
        else:
            print(f"{BLUE}💨 Pesan diabaikan. Tidak ada intelijen target '{settings['target_keyword']}'.{RESET}")

        # --- Step 5: Mark as Seen ---
        try:
            # print(f"{DIM}   Menandai pesan {email_id_str} sebagai 'Sudah Dibaca'...{RESET}", end='\r')
            mail.store(email_id, '+FLAGS', '\\Seen')
            # print(f"{DIM}   Pesan {email_id_str} ditandai 'Sudah Dibaca'.         {RESET}")
        except Exception as e:
            print(f"{status_nok} {RED}Gagal menandai pesan {email_id_str} sebagai 'Sudah Dibaca': {e}{RESET}")

        print(f"{separator}") # Penutup proses email

    except Exception as e:
        print(f"\r{status_nok} {RED}{BOLD}GAGAL TOTAL MEMPROSES PESAN ID {email_id_str}:{RESET} {' '*20}")
        traceback.print_exc()
        print(f"{separator}") # Penutup error


# --- Fungsi Listening Utama (DIMODIFIKASI VISUALNYA) ---
def start_listening(settings):
    """Memulai listener utama dengan tampilan lebih dinamis."""
    global running, spinner_chars
    running = True
    mail = None
    binance_client = None
    wait_time = 30 # Waktu tunggu reconnect (detik)
    connection_attempts = 0
    spinner_index = 0
    last_email_check_time = time.time()
    status_line = ""

    rows, cols = get_terminal_size()
    clear_screen()
    print("\n" * 1) # Sedikit margin atas
    print_separator(char="═", width=cols-2, color=YELLOW)
    mode = f"{BOLD}Email & Serangan Binance{RESET}" if settings.get("execute_binance_orders") else f"{BOLD}Pengintaian Email Saja{RESET}"
    print_centered(f"🛡️ {YELLOW}{BOLD}MODE OPERASI AKTIF: {mode} {YELLOW}🛡️", cols-2, YELLOW)
    print_separator(char="═", width=cols-2, color=YELLOW)
    print("\n")

    # --- Setup Binance (jika aktif) ---
    if settings.get("execute_binance_orders"):
        if not BINANCE_AVAILABLE:
             print(f"{status_nok} {RED}{BOLD}FATAL: Library 'python-binance' HILANG! Mode Serangan tidak mungkin.{RESET}")
             print(f"{YELLOW}   -> Nonaktifkan eksekusi di Pengaturan atau install library: pip install python-binance{RESET}")
             running = False; return # Stop jika library vital tidak ada & mode aktif
        print(f"{status_conn} {BOLD}{CYAN}[PERSIAPAN] Menginisialisasi Koneksi ke Markas Binance...{RESET}")
        binance_client = get_binance_client(settings)
        if not binance_client:
            print(f"{status_nok} {RED}{BOLD}PERINGATAN: Gagal terhubung ke Binance!{RESET}")
            print(f"{YELLOW}   -> Eksekusi order otomatis dinonaktifkan untuk sesi ini.{RESET}")
            print(f"{YELLOW}   -> Periksa API Key/Secret & koneksi internet, lalu restart.{RESET}")
            settings['execute_binance_orders'] = False # Nonaktifkan paksa untuk sesi ini
            time.sleep(4) # Beri waktu baca
        else:
            print(f"{status_ok} {GREEN}{BOLD}[PERSIAPAN] Koneksi Binance Siap Tempur!{RESET}")
    else:
        print(f"{status_warn} {YELLOW}{BOLD}[INFO] Mode Serangan Binance dinonaktifkan.{RESET}")

    print_separator(width=cols-2, color=CYAN)
    print(f"{status_email} {BOLD}{CYAN}[PERSIAPAN] Menyiapkan Pos Pengintaian Email...{RESET}")
    print(f"{DIM}   Akun Target  : {settings['email_address']}{RESET}")
    print(f"{DIM}   Server Intel : {settings['imap_server']}{RESET}")
    print_separator(width=cols-2, color=CYAN)
    time.sleep(1)
    print(f"\n{BOLD}{WHITE}MEMULAI MISI PENGINTAIAN... (Tekan Ctrl+C untuk mundur){RESET}")
    print("-" * (cols - 2))

    # --- Loop Utama Listener ---
    while running:
        try:
            # --- Koneksi IMAP ---
            if not mail or mail.state != 'SELECTED':
                connection_attempts += 1
                # Animasi koneksi
                spinner = itertools.cycle(spinner_chars)
                status_line = f"{status_conn} {CYAN}[Upaya {connection_attempts}] Menyambung ke server intel ({settings['imap_server']})... {next(spinner)}{RESET}"
                print(status_line.ljust(cols-1), end='\r')
                try:
                    mail = imaplib.IMAP4_SSL(settings['imap_server'])
                    status_line = f"{status_ok} {GREEN}Terhubung ke Server Intel.                 {RESET}"; print(status_line.ljust(cols-1))
                    status_line = f"{status_wait} {CYAN}Login sebagai {settings['email_address']}... {next(spinner)}{RESET}"; print(status_line.ljust(cols-1), end='\r')
                    mail.login(settings['email_address'], settings['app_password'])
                    status_line = f"{status_ok} {GREEN}Login Intelijen Berhasil! ({settings['email_address']}){RESET}     "; print(status_line.ljust(cols-1))
                    mail.select("inbox")
                    status_line = f"{status_ok} {GREEN}Masuk ke INBOX. Siap Mengintai...{RESET}"; print(status_line.ljust(cols-1))
                    print("-" * (cols-2))
                    connection_attempts = 0 # Reset jika berhasil
                    last_email_check_time = time.time() # Reset timer check
                except (imaplib.IMAP4.error, imaplib.IMAP4.abort, socket.error, OSError) as imap_err:
                    status_line = f"{status_nok} {RED}{BOLD}Gagal koneksi/login IMAP:{RESET} {imap_err} "
                    print(status_line.ljust(cols-1))
                    if "authentication failed" in str(imap_err).lower() or "invalid credentials" in str(imap_err).lower():
                         print(f"{RED}{BOLD}   -> KESALAHAN KREDENSIAL! Periksa Email & App Password!{RESET}")
                         print(f"{RED}{BOLD}   -> Pastikan Akses IMAP di akun email sudah diaktifkan.{RESET}")
                         running = False; return # Stop jika otentikasi gagal
                    else:
                         print(f"{YELLOW}   -> Mencoba lagi dalam {wait_time} detik...{RESET}")
                         for i in range(wait_time, 0, -1):
                              print(f"\r{YELLOW}   -> Mencoba lagi dalam {i} detik...{RESET}        ", end="")
                              time.sleep(1)
                              if not running: break
                         print("\r" + " " * (cols-1) + "\r", end="") # Hapus countdown
                         continue # Coba lagi dari awal loop while

            # --- Loop Cek Email (Inner) ---
            while running:
                # Check IMAP health (NOOP command)
                try:
                    if time.time() - last_email_check_time > 60: # Cek NOOP tiap 60 detik
                         status, _ = mail.noop()
                         if status != 'OK':
                             status_line = f"\n{status_warn} {YELLOW}Koneksi IMAP NOOP gagal ({status}). Menyambung ulang...{RESET}"
                             print(status_line.ljust(cols-1))
                             break # Keluar loop inner, akan reconnect di loop luar
                         last_email_check_time = time.time() # Reset timer jika NOOP ok
                except (imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError) as NopErr:
                     status_line = f"\n{status_warn} {YELLOW}Koneksi IMAP terputus ({type(NopErr).__name__}). Menyambung ulang...{RESET}"
                     print(status_line.ljust(cols-1))
                     break # Keluar loop inner

                # Check Binance health (optional, jika client ada)
                # if binance_client and time.time() - last_binance_check > 300: # Cek tiap 5 menit
                #     try: binance_client.ping()
                #     except Exception: reconnect_binance() ...

                # --- Cek Email Baru (UNSEEN) ---
                status, messages = mail.search(None, '(UNSEEN)')
                if status != 'OK':
                     status_line = f"\n{status_nok} {RED}Gagal mencari pesan baru: {status}. Menyambung ulang...{RESET}"
                     print(status_line.ljust(cols-1))
                     break # Keluar loop inner

                email_ids = messages[0].split()
                if email_ids:
                    print("\r" + " " * (cols - 1) + "\r", end='') # Hapus pesan tunggu/spinner
                    print(f"\n{BRIGHT_GREEN}{BOLD}✨ Ditemukan {len(email_ids)} Pesan Intelijen Baru! Memproses... ✨{RESET}")
                    print("-" * (cols - 2))
                    for email_id in email_ids:
                        if not running: break
                        process_email(mail, email_id, settings, binance_client)
                    if not running: break
                    print("-" * (cols - 2))
                    print(f"{status_ok} {GREEN}Selesai memproses {len(email_ids)} pesan. Kembali mengintai...{RESET}")
                    print("-" * (cols - 2))
                    last_email_check_time = time.time() # Reset timer check setelah proses
                else:
                    # --- Tidak ada email baru, tampilkan status tunggu + animasi ---
                    wait_interval = settings['check_interval_seconds']
                    spinner = spinner_chars[spinner_index % len(spinner_chars)]
                    spinner_index += 1
                    # Hitung mundur
                    for i in range(wait_interval, 0, -1):
                         if not running: break
                         wait_message = f"{BLUE}{BOLD}{spinner}{RESET}{BLUE} Mengintai... Tidak ada pergerakan. Cek lagi dalam {i} detik {RESET}"
                         # Pastikan pesan tidak melebihi lebar kolom
                         print(wait_message.ljust(cols - 1), end='\r')
                         time.sleep(1)
                         # Update spinner jika perlu
                         spinner = spinner_chars[spinner_index % len(spinner_chars)]
                         spinner_index += 1

                    if not running: break
                    print(" " * (cols - 1), end='\r') # Hapus pesan tunggu setelah selesai
                    last_email_check_time = time.time() # Reset timer check setelah tunggu

            # --- Keluar dari loop inner (karena break atau not running) ---
            if mail and mail.state == 'SELECTED':
                try: mail.close()
                except Exception: pass
            if mail and mail.state == 'AUTH': # Jika sudah login tapi belum select
                try: mail.logout()
                except Exception: pass
            mail = None # Set None agar reconnect di loop luar

        # --- Exception Handling Luar ---
        except (ConnectionError, OSError, socket.error, socket.gaierror, imaplib.IMAP4.error, imaplib.IMAP4.abort) as net_err:
             status_line = f"\n{status_nok} {RED}{BOLD}Kesalahan Koneksi Jaringan/IMAP:{RESET} {net_err}"
             print(status_line.ljust(cols-1))
             print(f"{YELLOW}   -> Periksa internet/server IMAP. Mencoba lagi dalam {wait_time} detik...{RESET}")
             for i in range(wait_time, 0, -1):
                  print(f"\r{YELLOW}   -> Mencoba lagi dalam {i} detik...{RESET}        ", end="")
                  time.sleep(1)
                  if not running: break
             print("\r" + " " * (cols-1) + "\r", end="") # Hapus countdown
        except Exception as e:
            status_line = f"\n{status_nok} {RED}{BOLD}ERROR TAK TERDUGA DI LOOP UTAMA:{RESET}"
            print(status_line.ljust(cols-1))
            traceback.print_exc()
            print(f"{YELLOW}   -> Mencoba recovery dalam {wait_time} detik...{RESET}")
            time.sleep(wait_time)
        finally:
            # Pastikan logout jika mail masih ada state nya
            if mail:
                try:
                    if mail.state != 'LOGOUT': mail.logout()
                except Exception: pass
            mail = None # Pastikan None untuk trigger reconnect
            if running: time.sleep(3) # Jeda singkat sebelum retry koneksi utama (jika loop luar berlanjut)

    # --- Listener Berhenti ---
    rows, cols = get_terminal_size()
    print(f"\n{BRIGHT_YELLOW}{BOLD}🛑 MISI PENGINTAIAN DIHENTIKAN.{RESET}")
    print("-"*(cols-2))


# --- Fungsi Menu Pengaturan (DIMODIFIKASI VISUALNYA) ---
def show_settings(settings):
    """Menampilkan dan mengedit pengaturan dengan layout 2 kolom."""
    global SPARTAN_SHIELD_ART # Gunakan art perisai
    original_settings = settings.copy() # Simpan state awal

    while True:
        rows, cols = get_terminal_size()
        layout_width = min(cols - 4, 110) # Batasi lebar layout maks 110
        # Bagi lebar, beri lebih banyak untuk setting
        left_col_width = int(layout_width * 0.6) - 3
        padding = 4

        # Efek sebelum clear
        wipe_effect(rows, cols, char=random.choice(['.',':','-']), delay=0.002, color=DIM)
        clear_screen()
        print("\n" * 1) # Margin atas

        # --- Konten Kolom Kiri (Pengaturan) ---
        left_content = []
        left_content.append(f"{BOLD}{BRIGHT_CYAN}╔══════════════════════════╗{RESET}")
        left_content.append(f"{BOLD}{BRIGHT_CYAN}║   🛡️ ATUR STRATEGI 🛡️   ║{RESET}")
        left_content.append(f"{BOLD}{BRIGHT_CYAN}╚══════════════════════════╝{RESET}")
        left_content.append("-" * left_col_width)
        left_content.append(f"{BLUE}{BOLD}--- Intelijen Email ---{RESET}")
        email_disp = settings['email_address'] or f'{YELLOW}[Belum Diatur]{RESET}'
        pwd_disp = '********' if settings['app_password'] else f'{YELLOW}[Belum Diatur]{RESET}'
        left_content.append(f" 1. {CYAN}Akun Email{RESET}   : {email_disp}")
        left_content.append(f" 2. {CYAN}App Password{RESET} : {pwd_disp}")
        left_content.append(f" 3. {CYAN}Server IMAP{RESET}  : {settings['imap_server']}")
        left_content.append(f" 4. {CYAN}Interval Cek{RESET} : {settings['check_interval_seconds']} detik {DIM}(min:5){RESET}")
        left_content.append(f" 5. {CYAN}Keyword Target{RESET}: {BOLD}{settings['target_keyword']}{RESET}")
        left_content.append(f" 6. {CYAN}Keyword Trigger{RESET}: {BOLD}{settings['trigger_keyword']}{RESET}")
        left_content.append("")
        left_content.append(f"{BLUE}{BOLD}--- Markas Binance ---{RESET}")
        lib_status = f"{GREEN}✅ Siap{RESET}" if BINANCE_AVAILABLE else f"{RED}❌ Library Hilang!{RESET}"
        left_content.append(f" Library Binance : {lib_status}")
        api_key_disp = settings['binance_api_key'][:5] + '...' + settings['binance_api_key'][-5:] if len(settings['binance_api_key']) > 10 else (f"{YELLOW}[Belum Diatur]{RESET}" if not settings['binance_api_key'] else settings['binance_api_key'])
        api_sec_disp = '********' if settings['binance_api_secret'] else f'{YELLOW}[Belum Diatur]{RESET}'
        left_content.append(f" 7. {CYAN}API Key{RESET}      : {api_key_disp}")
        left_content.append(f" 8. {CYAN}API Secret{RESET}   : {api_sec_disp}")
        pair_disp = settings['trading_pair'] or f'{YELLOW}[Belum Diatur]{RESET}'
        left_content.append(f" 9. {CYAN}Pasangan Tempur{RESET}: {BOLD}{pair_disp}{RESET}")
        left_content.append(f"10. {CYAN}Dana Beli{RESET}    : {settings['buy_quote_quantity']} {DIM}(Quote > 0){RESET}")
        left_content.append(f"11. {CYAN}Pasukan Jual{RESET} : {settings['sell_base_quantity']} {DIM}(Base >= 0){RESET}")
        exec_status = f"{GREEN}{BOLD}✅ AKTIF{RESET}" if settings['execute_binance_orders'] else f"{RED}❌ NONAKTIF{RESET}"
        left_content.append(f"12. {CYAN}Eksekusi Otomatis : {exec_status}")
        left_content.append("-" * left_col_width)
        left_content.append(f" {GREEN}{BOLD}E{RESET} - Edit Pengaturan")
        left_content.append(f" {YELLOW}{BOLD}S{RESET} - Simpan & Kembali")
        left_content.append(f" {RED}{BOLD}K{RESET} - Kembali (Tanpa Simpan)")
        left_content.append("-" * left_col_width)

        # --- Kolom Kanan (ASCII Art Perisai) ---
        right_content = [""] * 4 + SPARTAN_SHIELD_ART # Beri padding atas biar sejajar
        # Pad right_content biar sama tinggi dengan left_content
        while len(right_content) < len(left_content):
            right_content.append("")

        # --- Cetak Layout ---
        print_centered(f"{REVERSE}{WHITE}{BOLD} PENGATURAN STRATEGI {RESET}", layout_width)
        draw_two_column_layout(left_content, right_content, total_width=layout_width, left_width=left_col_width, padding=padding, color=WHITE)
        print_separator(char="=", width=layout_width, color=BRIGHT_CYAN)

        choice = input(f"{BOLD}{WHITE}Pilih Aksi (E/S/K): {RESET}").lower().strip()

        if choice == 'e':
            print(f"\n{BOLD}{MAGENTA}--- Mode Edit Strategi ---{RESET} {DIM}(Tekan Enter untuk skip item){RESET}")
            temp_settings = settings.copy() # Edit di temporary dict

            # --- Proses Edit ---
            # (Logika input edit tetap sama, visual diperjelas)
            print(f"\n{CYAN}{BOLD}--- Intelijen Email ---{RESET}")
            new_val = input(f" 1. Email [{temp_settings['email_address']}]: ").strip()
            if new_val: temp_settings['email_address'] = new_val
            try:
                current_pass_display = '[Rahasia]' if temp_settings['app_password'] else '[Kosong]'
                new_pass = getpass.getpass(f" 2. App Password Baru [{current_pass_display}] (ketik untuk ubah): ").strip()
                if new_pass: temp_settings['app_password'] = new_pass; print(f"   {GREEN}{status_ok} Password intelijen diperbarui.{RESET}")
            except Exception: # Fallback jika getpass error
                 print(f"{YELLOW}Tidak bisa menyembunyikan input password di terminal ini.{RESET}")
                 new_pass = input(f" 2. App Password Baru (terlihat) [{current_pass_display}]: ").strip()
                 if new_pass: temp_settings['app_password'] = new_pass

            new_val = input(f" 3. Server IMAP [{temp_settings['imap_server']}]: ").strip();
            if new_val: temp_settings['imap_server'] = new_val
            while True:
                new_val_str = input(f" 4. Interval Cek [{temp_settings['check_interval_seconds']}s], min 5: ").strip()
                if not new_val_str: break
                try:
                    new_interval = int(new_val_str)
                    if new_interval >= 5: temp_settings['check_interval_seconds'] = new_interval; break
                    else: print(f"   {RED}{status_nok} Minimal 5 detik, Komandan!{RESET}")
                except ValueError: print(f"   {RED}{status_nok} Masukkan angka saja.{RESET}")
            new_val = input(f" 5. Keyword Target [{temp_settings['target_keyword']}]: ").strip();
            if new_val: temp_settings['target_keyword'] = new_val
            new_val = input(f" 6. Keyword Trigger [{temp_settings['trigger_keyword']}]: ").strip();
            if new_val: temp_settings['trigger_keyword'] = new_val

            print(f"\n{CYAN}{BOLD}--- Markas Binance ---{RESET}")
            if not BINANCE_AVAILABLE: print(f"{YELLOW}   (Perhatian: Library Binance tidak terdeteksi){RESET}")
            new_val = input(f" 7. API Key [{api_key_disp}]: ").strip();
            if new_val: temp_settings['binance_api_key'] = new_val
            try:
                current_secret_display = '[Rahasia]' if temp_settings['binance_api_secret'] else '[Kosong]'
                new_secret = getpass.getpass(f" 8. API Secret Baru [{current_secret_display}] (ketik untuk ubah): ").strip()
                if new_secret: temp_settings['binance_api_secret'] = new_secret; print(f"   {GREEN}{status_ok} Kunci rahasia markas diperbarui.{RESET}")
            except Exception:
                 print(f"{YELLOW}Tidak bisa menyembunyikan input secret di terminal ini.{RESET}")
                 new_secret = input(f" 8. API Secret Baru (terlihat) [{current_secret_display}]: ").strip()
                 if new_secret: temp_settings['binance_api_secret'] = new_secret

            new_val = input(f" 9. Pasangan Tempur [{temp_settings['trading_pair']}]: ").strip().upper();
            if new_val: temp_settings['trading_pair'] = new_val
            while True:
                 new_val_str = input(f"10. Dana Beli (Quote) [{temp_settings['buy_quote_quantity']}], harus > 0: ").strip()
                 if not new_val_str: break
                 try:
                     new_qty = float(new_val_str)
                     if new_qty > 0: temp_settings['buy_quote_quantity'] = new_qty; break
                     else: print(f"   {RED}{status_nok} Dana beli harus lebih dari 0!{RESET}")
                 except ValueError: print(f"   {RED}{status_nok} Masukkan angka saja.{RESET}")
            while True:
                 new_val_str = input(f"11. Pasukan Jual (Base) [{temp_settings['sell_base_quantity']}], harus >= 0: ").strip()
                 if not new_val_str: break
                 try:
                     new_qty = float(new_val_str)
                     if new_qty >= 0: temp_settings['sell_base_quantity'] = new_qty; break
                     else: print(f"   {RED}{status_nok} Jumlah pasukan jual tidak boleh negatif!{RESET}")
                 except ValueError: print(f"   {RED}{status_nok} Masukkan angka saja.{RESET}")
            while True:
                 current_exec_status = "Aktif" if temp_settings['execute_binance_orders'] else "Nonaktif"
                 current_exec_color = GREEN if temp_settings['execute_binance_orders'] else RED
                 exec_prompt = f"{current_exec_color}{current_exec_status}{RESET}"
                 new_val_str = input(f"12. Eksekusi Otomatis? (y/n) [{exec_prompt}]: ").lower().strip()
                 if not new_val_str: break
                 if new_val_str == 'y': temp_settings['execute_binance_orders'] = True; print(f"   {GREEN}{status_ok} Mode Serangan Otomatis {BOLD}DIAKTIFKAN{RESET}."); break
                 elif new_val_str == 'n': temp_settings['execute_binance_orders'] = False; print(f"   {RED}{status_nok} Mode Serangan Otomatis {BOLD}DINONAKTIFKAN{RESET}."); break
                 else: print(f"   {RED}{status_nok} Pilihan hanya 'y' (Ya) atau 'n' (Tidak).{RESET}")

            settings = temp_settings.copy() # Update setting utama dengan perubahan
            print(f"\n{YELLOW}[INFO] Pengaturan telah diubah. Pilih 'S' untuk menyimpan atau 'K' untuk batal.{RESET}")
            input(f"{DIM}Tekan Enter untuk kembali ke menu pengaturan...{RESET}")


        elif choice == 's':
            save_settings(settings)
            print(f"\n{GREEN}{BOLD}✅ Strategi disimpan! Kembali ke Menu Utama...{RESET}")
            time.sleep(1.5)
            break # Keluar dari loop pengaturan

        elif choice == 'k':
            print(f"\n{YELLOW}{BOLD}⚠️ Perubahan dibatalkan. Kembali ke Menu Utama...{RESET}")
            settings = original_settings.copy() # Kembalikan ke state awal sebelum edit
            time.sleep(1.5)
            break # Keluar dari loop pengaturan
        else:
            print(f"\n{RED}{BOLD} Pilihan tidak valid! Pilih E, S, atau K.{RESET}")
            time.sleep(1.5)

# --- Fungsi Menu Utama (DIMODIFIKASI VISUALNYA) ---
def main_menu():
    """Menampilkan menu utama dengan layout Spartan."""
    global SPARTAN_FACE_ART
    settings = load_settings() # Load awal sekali saja di sini
    startup_animation() # Panggil animasi startup sekali

    while True:
        settings = load_settings() # Re-load setting setiap kembali ke menu
        rows, cols = get_terminal_size()
        layout_width = min(cols - 4, 100) # Batasi lebar layout
        left_col_width = layout_width // 2 - 3 # Lebar kolom kiri
        padding = 4

        # Wipe acak sebelum clear
        wipe_effect(rows, cols, char=random.choice(wipe_chars), delay=0.003, color=random.choice([RED,YELLOW,DIM]))
        clear_screen()
        print("\n" * 1) # Margin atas

        # --- Konten Kolom Kiri (Menu) ---
        left_content = []
        left_content.append(f"{BOLD}{BRIGHT_MAGENTA}╔══════════════════════════════╗{RESET}")
        left_content.append(f"{BOLD}{BRIGHT_MAGENTA}║   {YELLOW}EXORA AI - SPARTAN OPS{RESET}{BOLD}{BRIGHT_MAGENTA}   ║{RESET}")
        left_content.append(f"{BOLD}{BRIGHT_MAGENTA}╚══════════════════════════════╝{RESET}")
        left_content.append("")
        left_content.append(f"{BOLD}{WHITE}Pilih Misi:{RESET}")

        exec_mode_label = f" {BOLD}& Serangan Binance{RESET}" if settings.get("execute_binance_orders") else ""
        start_option_color = BRIGHT_GREEN if settings.get('email_address') and settings.get('app_password') else YELLOW # Warna opsi start berdasarkan kesiapan email
        left_content.append(f" {start_option_color}{BOLD}1.{RESET} Mulai Pengintaian (Email{exec_mode_label})")
        left_content.append(f" {BRIGHT_CYAN}{BOLD}2.{RESET} Atur Strategi (Pengaturan)")
        left_content.append(f" {BRIGHT_RED}{BOLD}3.{RESET} Mundur Teratur (Keluar)")
        left_content.append("-" * left_col_width)

        # Status Cepat (Lebih detail)
        left_content.append(f"{BOLD}{WHITE}Status Kesiapan:{RESET}")
        # Email
        email_ok = bool(settings['email_address']) and bool(settings['app_password'])
        email_status_icon = status_ok if email_ok else status_nok
        email_status_text = f"{GREEN}Siap{RESET}" if email_ok else f"{RED}Perlu Diatur!{RESET}"
        left_content.append(f" Intel Email  : [{email_status_icon}] {email_status_text}")

        # Binance Library & Eksekusi
        exec_on = settings.get("execute_binance_orders", False)
        exec_status_label = f"{GREEN}AKTIF{RESET}" if exec_on else f"{YELLOW}NONAKTIF{RESET}"
        lib_status_icon = status_ok if BINANCE_AVAILABLE else status_nok
        lib_status_text = f"{GREEN}Terdeteksi{RESET}" if BINANCE_AVAILABLE else f"{RED}Hilang!{RESET}"
        left_content.append(f" Binance Lib  : [{lib_status_icon}] {lib_status_text} | Eksekusi: [{exec_status_label}]")

        # Binance Config (jika eksekusi aktif & library ada)
        if exec_on and BINANCE_AVAILABLE:
            api_ok = bool(settings['binance_api_key']) and bool(settings['binance_api_secret'])
            pair_ok = bool(settings['trading_pair'])
            buy_qty_ok = settings['buy_quote_quantity'] > 0
            sell_qty_ok = settings['sell_base_quantity'] >= 0 # Boleh 0 untuk sell
            bin_config_ok = api_ok and pair_ok and buy_qty_ok and sell_qty_ok
            bin_status_icon = status_ok if bin_config_ok else status_warn
            bin_status_text = f"{GREEN}Lengkap{RESET}" if bin_config_ok else f"{YELLOW}Belum Lengkap!{RESET}"
            details = []
            if not api_ok: details.append("API")
            if not pair_ok: details.append("Pair")
            if not buy_qty_ok: details.append("BuyQty")
            if not sell_qty_ok: details.append("SellQty") # Jarang masalah jika 0
            detail_str = f" ({', '.join(details)})" if details else ""
            left_content.append(f" Binance Cfg  : [{bin_status_icon}] {bin_status_text}{detail_str}")
        elif exec_on and not BINANCE_AVAILABLE:
             left_content.append(f" Binance Cfg  : [{status_nok}] {RED}(Lib Error){RESET}")
        # Jika tidak eksekusi, tidak perlu tampilkan status config binance
        # else:
        #      left_content.append(f" Binance Cfg  : [{DIM}N/A (Eksekusi Nonaktif){RESET}]")


        left_content.append("-" * left_col_width)
        # Pad left content biar tingginya sama dengan SPARTAN_FACE_ART
        while len(left_content) < len(SPARTAN_FACE_ART):
             left_content.append(" ") # Tambah spasi kosong

        # --- Cetak Layout ---
        print_centered(f"{REVERSE}{WHITE}{BOLD} MARKAS UTAMA {RESET}", layout_width)
        draw_two_column_layout(left_content, SPARTAN_FACE_ART, total_width=layout_width, left_width=left_col_width, padding=padding, color=WHITE)
        print_separator(char="=", width=layout_width, color=BRIGHT_MAGENTA)

        choice = input(f"{BOLD}{WHITE}Masukkan nomor misi (1/2/3): {RESET}").strip()

        if choice == '1':
            # Validasi Kesiapan Sebelum Mulai
            ready_to_start = True
            print() # Baris baru sebelum pesan status
            if not email_ok:
                 print(f"{status_nok} {RED}{BOLD}Strategi Intelijen Email belum lengkap!{RESET} (Periksa Email/Password di Pengaturan).")
                 ready_to_start = False
            if exec_on and not BINANCE_AVAILABLE:
                 print(f"{status_nok} {RED}{BOLD}Mode Serangan aktif tapi library Binance hilang!{RESET} Tidak bisa memulai.")
                 ready_to_start = False
            if exec_on and BINANCE_AVAILABLE and not bin_config_ok:
                 print(f"{status_warn} {YELLOW}{BOLD}Mode Serangan aktif tapi konfigurasi Binance belum lengkap/valid.{RESET}")
                 print(f"{YELLOW}   -> Bot akan berjalan, tapi {BOLD}TIDAK AKAN{RESET}{YELLOW} bisa eksekusi order.")
                 # ready_to_start = False # Tetap bisa jalan, tapi beri warning keras
                 input(f"{DIM}Tekan Enter untuk lanjut HANYA dengan pengintaian email...{RESET}")

            if ready_to_start:
                start_listening(settings)
                # Kembali ke menu setelah listener berhenti (misal via Ctrl+C)
                print(f"\n{YELLOW}[INFO] Kembali ke Markas Utama...{RESET}")
                input(f"{DIM}Tekan Enter untuk melanjutkan...{RESET}")
            else:
                print(f"\n{YELLOW}Silakan perbaiki di menu 'Atur Strategi' (Pengaturan).{RESET}")
                input(f"{DIM}Tekan Enter untuk kembali ke Markas Utama...{RESET}")

        elif choice == '2':
            show_settings(settings)
            # Settings disimpan di dalam show_settings jika user memilih 'S'
        elif choice == '3':
            clear_screen()
            rows, cols = get_terminal_size()
            farewell_art = [ # Simple farewell art
                f"{RED} __   __",
                f"{RED}/  `-'  \\",
                f"{RED}\\  {BOLD}BYE{RESET}{RED}  /",
                f"{RED} \\.__./ ",
                f"{RED}  / /\\ \\",
                f"{RED} / /  \\ \\",
                f"{RED}`-'    `-'{RESET}"
            ]
            farewell_msg = f"{BRIGHT_CYAN}{BOLD}AHOO! AHOO! Sampai jumpa, Komandan!{RESET}"
            print("\n" * (max(5, rows // 3 - len(farewell_art)//2))) # Posisikan agak di tengah
            for line in farewell_art: print_centered(line, cols)
            print("\n")
            print_centered(farewell_msg, cols)
            print("\n\n")
            print_separator(char="*", width=cols-4, color=RED, animated=True, delay=0.01)
            sys.exit(0)
        else:
            print(f"\n{RED}{BOLD} Misi tidak dikenal! Pilih 1, 2, atau 3.{RESET}")
            time.sleep(1.5)

# --- Entry Point (TIDAK DIUBAH) ---
if __name__ == "__main__":
    try:
        # Pastikan file config ada saat pertama kali jalan
        if not os.path.exists(CONFIG_FILE):
             print(f"Membuat file konfigurasi default: {CONFIG_FILE}")
             save_settings(DEFAULT_SETTINGS.copy(), silent=True) # Buat file config jika belum ada
        main_menu()
    except KeyboardInterrupt:
        # Signal handler sudah menangani ini, tapi sebagai fallback
        print(f"\n{YELLOW}{BOLD}Program dihentikan paksa dari luar.{RESET}")
        sys.exit(1)
    except Exception as e:
        # Tangkap error tak terduga di level tertinggi
        clear_screen()
        print(f"\n{BOLD}{BG_RED}{WHITE}╔═══════════════════════════════════════╗{RESET}")
        print(f"{BOLD}{BG_RED}{WHITE}║      🚨🚨🚨 ERROR KRITIS 🚨🚨🚨       ║{RESET}")
        print(f"{BOLD}{BG_RED}{WHITE}╚═══════════════════════════════════════╝{RESET}")
        print(f"\n{RED}{BOLD}Terjadi kesalahan fatal yang tidak dapat dipulihkan:{RESET}")
        print("-" * 60)
        traceback.print_exc() # Tampilkan traceback lengkap
        print("-" * 60)
        print(f"{RED}Pesan Error: {e}{RESET}")
        print("\n{YELLOW}Program terpaksa berhenti. Periksa log error di atas.{RESET}")
        input("\nTekan Enter untuk keluar...") # Tahan biar user bisa baca error
        sys.exit(1)
