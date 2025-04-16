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
import re # Untuk fallback print jika rich tidak ada

# --- Rich & PyFiglet Integration (untuk tampilan keren) ---
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.theme import Theme
    from rich.spinner import Spinner
    from rich.live import Live # Opsional, bisa pakai console.status
    from rich.progress import track # Opsional untuk progress bar
    RICH_AVAILABLE = True
    # Tema custom biar konsisten
    custom_theme = Theme({
        "info": "dim cyan",
        "warning": "yellow",
        "error": "bold red",
        "success": "bold green",
        "highlight": "bold magenta",
        "label": "cyan",
        "value": "default",
        "dim": "dim",
        "title": "bold magenta",
        "header": "bold blue",
        "input": "bold yellow", # Untuk prompt input
        "danger": "bold red on white", # Untuk pesan fatal
    })
    console = Console(theme=custom_theme)
except ImportError:
    RICH_AVAILABLE = False
    # Fallback Console sederhana jika rich tidak ada
    class FallbackConsole:
        def print(self, *args, **kwargs):
            new_args = [re.sub(r'\[/?.*?\]', '', str(arg)) for arg in args]
            print(*new_args)
        def rule(self, *args, **kwargs):
            print("-" * 40)
        # Tambahkan dummy method lain jika diperlukan
        def status(self, *args, **kwargs):
            # Dummy status context manager
            class DummyStatus:
                def __enter__(self): pass
                def __exit__(self, exc_type, exc_val, exc_tb): pass
            return DummyStatus()

    console = FallbackConsole()
    print("\n!!! WARNING: Library 'rich' tidak ditemukan. Tampilan CLI akan standar. !!!")
    print("!!!          Install dengan: pip install rich                            !!!\n")
    time.sleep(3)

try:
    import pyfiglet
    PYFIGLET_AVAILABLE = True
except ImportError:
    PYFIGLET_AVAILABLE = False
    # Tidak perlu warning jika rich juga tidak ada
    if RICH_AVAILABLE:
        console.print("[warning]!!! WARNING: Library 'pyfiglet' tidak ditemukan. Judul akan standar. !!![/]")
        console.print("[warning]!!!          Install dengan: pip install pyfiglet                    !!![/]")
        time.sleep(2)


# --- Inquirer Integration (menu interaktif) ---
# (Tetap sama seperti sebelumnya)
try:
    import inquirer
    # Coba gunakan tema rich jika ada, atau fallback ke GreenPassion/default
    if RICH_AVAILABLE:
        # Tema inquirer mungkin tidak langsung kompatibel dengan rich, gunakan default/GreenPassion
        from inquirer.themes import GreenPassion as DefaultTheme
    else:
        from inquirer.themes import GreenPassion as DefaultTheme
    INQUIRER_AVAILABLE = True
except ImportError:
    INQUIRER_AVAILABLE = False
    # Warning sudah diberikan jika rich tidak ada, cukup untuk inquirer saja
    if RICH_AVAILABLE: # Hanya tampilkan jika rich ada tapi inquirer tidak
        console.print("[warning]!!! WARNING: Library 'inquirer' tidak ditemukan. Menu akan teks biasa. !!![/]")
        console.print("[warning]!!!          Install dengan: pip install inquirer                      !!![/]")
        time.sleep(3)
    # Jika rich juga tidak ada, warning sudah muncul di awal
    # Definisikan tema dummy jika inquirer tidak ada
    class DefaultTheme: pass


# --- Binance Integration ---
# (Tetap sama seperti sebelumnya)
try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException, BinanceOrderException
    import requests # Ditambahkan untuk menangani RequestException secara eksplisit
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False
    console.print("\n[warning]!!! WARNING: Library 'python-binance' tidak ditemukan. !!![/]")
    console.print("[warning]!!!          Fitur eksekusi order Binance tidak akan berfungsi. !!![/]")
    console.print("[warning]!!!          Install dengan: [code]pip install python-binance[/]       !!![/]\n")
    time.sleep(2)
    # Definisikan exception dummy jika library tidak ada agar script tidak crash
    class BinanceAPIException(Exception): pass
    class BinanceOrderException(Exception): pass
    class Client: # Dummy class
        SIDE_BUY = 'BUY'
        SIDE_SELL = 'SELL'
        ORDER_TYPE_MARKET = 'MARKET'
    class requests: # Dummy class
        class exceptions:
             class RequestException(Exception): pass


# --- Konfigurasi & Variabel Global ---
CONFIG_FILE = "config.json"
DEFAULT_SETTINGS = {
    # Email Settings
    "email_address": "",
    "app_password": "",
    "imap_server": "imap.gmail.com",
    "check_interval_seconds": 10,
    "target_keyword": "Exora AI",
    "trigger_keyword": "order",
    # Binance Settings
    "binance_api_key": "",
    "binance_api_secret": "",
    "trading_pair": "BTCUSDT",
    "buy_quote_quantity": 11.0,
    "sell_base_quantity": 0.0,
    "execute_binance_orders": False
}
running = True # Kontrol loop utama

# Hapus konstanta warna ANSI lama, gunakan markup rich
# RESET = "\033[0m" ... etc.

# --- Fungsi Penanganan Sinyal (Ctrl+C) ---
def signal_handler(sig, frame):
    global running
    console.print(f"\n[warning][bold]Ctrl+C terdeteksi. Menghentikan program...[/bold][/]")
    running = False
    time.sleep(1.5)
    console.print(f"[error][bold]Keluar dari program.[/bold][/]")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# --- Fungsi Konfigurasi ---
# load_settings & save_settings tetap sama, hanya ganti print ke console.print
def load_settings():
    """Memuat pengaturan dari file JSON, memastikan semua kunci ada."""
    settings = DEFAULT_SETTINGS.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_settings = json.load(f)
                valid_keys = set(DEFAULT_SETTINGS.keys())
                filtered_settings = {k: v for k, v in loaded_settings.items() if k in valid_keys}
                settings.update(filtered_settings)

                # Validasi (gunakan console.print untuk warning)
                if settings.get("check_interval_seconds", 10) < 5:
                    console.print(f"[warning]Interval cek di '{CONFIG_FILE}' < 5 detik, direset ke 10.[/]")
                    settings["check_interval_seconds"] = 10
                if not isinstance(settings.get("buy_quote_quantity"), (int, float)) or settings.get("buy_quote_quantity") <= 0:
                    console.print(f"[warning]'buy_quote_quantity' tidak valid, direset ke {DEFAULT_SETTINGS['buy_quote_quantity']}.[/]")
                    settings["buy_quote_quantity"] = DEFAULT_SETTINGS['buy_quote_quantity']
                if not isinstance(settings.get("sell_base_quantity"), (int, float)) or settings.get("sell_base_quantity") < 0:
                    console.print(f"[warning]'sell_base_quantity' tidak valid, direset ke {DEFAULT_SETTINGS['sell_base_quantity']}.[/]")
                    settings["sell_base_quantity"] = DEFAULT_SETTINGS['sell_base_quantity']
                if not isinstance(settings.get("execute_binance_orders"), bool):
                    console.print(f"[warning]'execute_binance_orders' tidak valid, direset ke False.[/]")
                    settings["execute_binance_orders"] = False

                # Periksa jika ada kunci default baru yang belum ada di file
                missing_keys = valid_keys - set(filtered_settings.keys())
                if missing_keys:
                     console.print(f"[info]Menambahkan kunci default baru ke '{CONFIG_FILE}': {', '.join(missing_keys)}[/]")
                     # Tidak perlu save di sini, save akan terjadi jika ada koreksi atau file baru

                # Hanya simpan jika ada perubahan atau file baru dibuat
                current_saved_settings = {}
                try: # Muat lagi untuk perbandingan bersih
                   with open(CONFIG_FILE, 'r') as f_check:
                       current_saved_settings = json.load(f_check)
                except: pass # Abaikan jika file belum ada/rusak

                settings_to_save_check = {k: settings.get(k, DEFAULT_SETTINGS[k]) for k in DEFAULT_SETTINGS}
                if settings_to_save_check != current_saved_settings:
                     save_settings(settings) # Simpan jika ada perbedaan

        except json.JSONDecodeError:
            console.print(f"[error]File konfigurasi '{CONFIG_FILE}' rusak. Menggunakan default & menyimpan ulang.[/]")
            save_settings(settings)
        except Exception as e:
            console.print(f"[error]Gagal memuat konfigurasi: {e}[/]")
            traceback.print_exc() # Tampilkan traceback untuk debug
    else:
        console.print(f"[info]File konfigurasi '{CONFIG_FILE}' tidak ditemukan. Membuat dengan nilai default.[/]")
        save_settings(settings)
    return settings

def save_settings(settings):
    """Menyimpan pengaturan ke file JSON."""
    try:
        settings['check_interval_seconds'] = int(settings.get('check_interval_seconds', DEFAULT_SETTINGS['check_interval_seconds']))
        settings['buy_quote_quantity'] = float(settings.get('buy_quote_quantity', DEFAULT_SETTINGS['buy_quote_quantity']))
        settings['sell_base_quantity'] = float(settings.get('sell_base_quantity', DEFAULT_SETTINGS['sell_base_quantity']))
        settings['execute_binance_orders'] = bool(settings.get('execute_binance_orders', DEFAULT_SETTINGS['execute_binance_orders']))
        settings_to_save = {k: settings.get(k, DEFAULT_SETTINGS[k]) for k in DEFAULT_SETTINGS}

        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings_to_save, f, indent=4, sort_keys=True)
        # Pesan sukses disimpan hanya saat diedit manual, bukan saat load awal
        # console.print(f"[success]Pengaturan berhasil disimpan ke '{CONFIG_FILE}'[/]")
    except Exception as e:
        console.print(f"[error]Gagal menyimpan konfigurasi: {e}[/]")

# --- Fungsi Utilitas ---
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

# decode_mime_words & get_text_from_email tetap sama, hanya ganti print
def decode_mime_words(s):
    if not s: return ""
    try:
        decoded_parts = decode_header(s)
        result = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(encoding or 'utf-8', errors='replace'))
            else: result.append(str(part))
        return "".join(result)
    except Exception as e:
        console.print(f"[warning]Gagal mendekode header: {e}. Header asli: {s}[/]")
        return str(s) if isinstance(s, str) else s.decode('utf-8', errors='replace') if isinstance(s, bytes) else "[Decoding Error]"

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
                    if payload: text_content += payload.decode(charset, errors='replace') + "\n"
                except Exception as e:
                    console.print(f"[warning]Tidak bisa mendekode bagian email (charset: {part.get_content_charset()}): {e}[/]")
    else:
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                if payload: text_content = payload.decode(charset, errors='replace')
            except Exception as e:
                 console.print(f"[warning]Tidak bisa mendekode body email (charset: {msg.get_content_charset()}): {e}[/]")
    return " ".join(text_content.split()).lower()

# --- Fungsi Beep ---
# trigger_beep tetap sama, ganti print
def trigger_beep(action):
    cmd = None
    if action == "buy":
        console.print(f"[highlight][bold]BEEP AKSI: BUY![/bold][/]")
        # Coba frekuensi & durasi yang sedikit berbeda
        cmd = ["beep", "-f", "1200", "-l", "150", "-n", "-f", "1500", "-l", "250"]
    elif action == "sell":
        console.print(f"[highlight][bold]BEEP AKSI: SELL![/bold][/]")
        cmd = ["beep", "-f", "600", "-l", "400"]
    else:
         console.print(f"[warning]Aksi beep tidak dikenal '{action}'.[/]")
         return

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        console.print(f"[warning]Perintah 'beep' tidak ditemukan. Beep dilewati.[/]")
        console.print(f"[dim]         (Untuk Linux, install 'beep': sudo apt install beep / sudo yum install beep)[/]")
    except subprocess.CalledProcessError as e:
        console.print(f"[error]Gagal menjalankan 'beep': {e}[/]")
        if e.stderr: console.print(f"[error]         Stderr: {e.stderr.strip()}[/]")
    except Exception as e:
        console.print(f"[error]Kesalahan tak terduga saat beep: {e}[/]")


# --- Fungsi Eksekusi Binance ---
# get_binance_client & execute_binance_order tetap sama, ganti print
def get_binance_client(settings):
    if not BINANCE_AVAILABLE:
        console.print("[error]Library python-binance tidak terinstall.[/]")
        return None
    api_key = settings.get('binance_api_key')
    api_secret = settings.get('binance_api_secret')
    if not api_key or not api_secret:
        console.print("[error]API Key atau Secret Key Binance belum diatur.[/]")
        return None
    try:
        console.print("[info]Mencoba koneksi ke Binance API...[/]")
        client = Client(api_key, api_secret)
        client.ping()
        console.print("[success]Koneksi dan autentikasi ke Binance API berhasil.[/]")
        return client
    except BinanceAPIException as e:
        console.print(f"[error][bold]BINANCE API ERROR: Status={e.status_code}, Pesan='{e.message}'[/bold][/]")
        if "timestamp" in e.message.lower(): console.print(f"[warning]   -> Periksa apakah waktu sistem Anda sinkron.[/]")
        if "signature" in e.message.lower() or "invalid key" in e.message.lower(): console.print(f"[warning]   -> Periksa kembali API Key dan Secret Key Anda.[/]")
        return None
    except requests.exceptions.RequestException as e:
        console.print(f"[error][bold]NETWORK ERROR: Gagal menghubungi Binance API: {e}[/bold][/]")
        console.print(f"[warning]   -> Periksa koneksi internet Anda.[/]")
        return None
    except Exception as e:
        console.print(f"[error][bold]ERROR: Gagal membuat Binance client: {e}[/bold][/]")
        traceback.print_exc()
        return None

def execute_binance_order(client, settings, side):
    if not client:
        console.print("[error]Eksekusi Binance dibatalkan, client tidak valid.[/]")
        return False
    # Safety check (seharusnya sudah dicek sebelumnya)
    if not settings.get("execute_binance_orders", False): return False

    pair = settings.get('trading_pair', '').upper()
    if not pair:
        console.print("[error]Trading pair belum diatur.[/]")
        return False

    order_details = {}
    action_desc = ""

    try:
        if side == Client.SIDE_BUY:
            quote_qty = settings.get('buy_quote_quantity', 0.0)
            if quote_qty <= 0:
                console.print("[error]Kuantitas Beli (buy_quote_quantity) harus > 0.[/]")
                return False
            order_details = {'symbol': pair, 'side': Client.SIDE_BUY, 'type': Client.ORDER_TYPE_MARKET, 'quoteOrderQty': quote_qty}
            action_desc = f"MARKET BUY {quote_qty} (quote) of {pair}"
        elif side == Client.SIDE_SELL:
            base_qty = settings.get('sell_base_quantity', 0.0)
            if base_qty <= 0:
                console.print("[warning]Kuantitas Jual (sell_base_quantity) adalah 0. Order SELL tidak dieksekusi.[/]")
                return False # Bukan error, tapi tidak ada aksi
            order_details = {'symbol': pair, 'side': Client.SIDE_SELL, 'type': Client.ORDER_TYPE_MARKET, 'quantity': base_qty}
            action_desc = f"MARKET SELL {base_qty} (base) of {pair}"
        else:
            console.print(f"[error]Sisi order tidak valid: {side}[/]")
            return False

        console.print(f"[highlight]=> Mencoba eksekusi: [bold]{action_desc}[/bold]...[/]")
        order_result = client.create_order(**order_details)

        console.print(Panel(f"""\
[bold green]✓ Order Berhasil Dieksekusi![/bold green]
  [dim]Order ID  :[/dim] [default]{order_result.get('orderId')}[/default]
  [dim]Symbol    :[/dim] [default]{order_result.get('symbol')}[/default]
  [dim]Side      :[/dim] [default]{order_result.get('side')}[/default]
  [dim]Status    :[/dim] [success]{order_result.get('status')}[/success]""",
                        title="[bold]Hasil Order Binance[/]", border_style="green", expand=False))

        if order_result.get('fills') and len(order_result.get('fills')) > 0:
            total_qty = sum(float(f['qty']) for f in order_result['fills'])
            total_quote_qty = sum(float(f['cummulativeQuoteQty']) for f in order_result['fills'])
            avg_price = total_quote_qty / total_qty if total_qty else 0
            console.print(f"  [dim]Avg Price :[/dim] [default]{avg_price:.8f}[/default]")
            console.print(f"  [dim]Filled Qty:[/dim] [default]{total_qty:.8f} (Base) / {total_quote_qty:.4f} (Quote)[/default]")
        elif order_result.get('cummulativeQuoteQty'):
             console.print(f"  [dim]Total Cost/Proceeds:[/dim] [default]{float(order_result['cummulativeQuoteQty']):.4f} (Quote)[/default]")
        return True

    except BinanceAPIException as e:
        console.print(f"[error][bold]BINANCE API ERROR: Gagal eksekusi order. Status={e.status_code}, Kode={e.code}, Pesan='{e.message}'[/bold][/]")
        if e.code == -2010: console.print(f"[error]   -> Kemungkinan saldo tidak cukup.[/]")
        elif e.code == -1121: console.print(f"[error]   -> Trading pair '{pair}' tidak valid.[/]")
        elif e.code == -1013 or 'MIN_NOTIONAL' in str(e.message): console.print(f"[error]   -> Order size terlalu kecil (cek MIN_NOTIONAL).[/]")
        elif e.code == -1111: console.print(f"[error]   -> Kuantitas order tidak sesuai LOT_SIZE.[/]")
        return False
    except BinanceOrderException as e:
        console.print(f"[error][bold]BINANCE ORDER ERROR: Gagal eksekusi order. Status={e.status_code}, Kode={e.code}, Pesan='{e.message}'[/bold][/]")
        return False
    except requests.exceptions.RequestException as e:
        console.print(f"[error][bold]NETWORK ERROR: Gagal mengirim order ke Binance: {e}[/bold][/]")
        return False
    except Exception as e:
        console.print(f"[error][bold]ERROR: Kesalahan tak terduga saat eksekusi order Binance:[/bold][/]")
        traceback.print_exc()
        return False


# --- Fungsi Pemrosesan Email ---
# process_email tetap sama, ganti print
def process_email(mail, email_id, settings, binance_client):
    global running
    if not running: return

    target_keyword_lower = settings['target_keyword'].lower()
    trigger_keyword_lower = settings['trigger_keyword'].lower()
    email_id_str = email_id.decode('utf-8')

    try:
        status, data = mail.fetch(email_id, "(RFC822)")
        if status != 'OK':
            console.print(f"[error]Gagal mengambil email ID {email_id_str}: {status}[/]")
            return

        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        subject = decode_mime_words(msg["Subject"])
        sender = decode_mime_words(msg["From"])
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Tampilkan info email dalam Panel
        email_info = f"""\
[label]ID    :[/label] [value]{email_id_str}[/value]
[label]Dari  :[/label] [value]{sender}[/value]
[label]Subjek:[/label] [value]{subject}[/value]"""
        console.print(Panel(email_info, title=f"[header]Email Diterima ({timestamp})[/]", border_style="cyan", expand=False))

        body = get_text_from_email(msg)
        full_content = (subject.lower() + " " + body)

        if target_keyword_lower in full_content:
            console.print(f"[success]Keyword target '{settings['target_keyword']}' ditemukan.[/]")
            try:
                target_index = full_content.find(target_keyword_lower)
                trigger_index = full_content.find(trigger_keyword_lower, target_index + len(target_keyword_lower))

                if trigger_index != -1:
                    start_word_index = trigger_index + len(trigger_keyword_lower)
                    text_after_trigger = full_content[start_word_index:].lstrip()
                    words_after_trigger = text_after_trigger.split(maxsplit=1)

                    if words_after_trigger:
                        action_word = words_after_trigger[0].strip('.,!?:;()[]{}').lower()
                        console.print(f"[success]Keyword trigger '{settings['trigger_keyword']}' ditemukan. Kata aksi: '[bold]{action_word}[/bold]'[/]")

                        # Trigger Aksi
                        execute_binance = settings.get("execute_binance_orders", False)
                        order_attempted = False

                        if action_word == "buy":
                            trigger_beep("buy")
                            if execute_binance and BINANCE_AVAILABLE:
                                if binance_client:
                                    execute_binance_order(binance_client, settings, Client.SIDE_BUY)
                                    order_attempted = True
                                else: console.print("[warning]Eksekusi Binance aktif tapi client tidak valid/tersedia.[/]")

                        elif action_word == "sell":
                            can_sell = settings.get('sell_base_quantity', 0.0) > 0
                            trigger_beep("sell")
                            if execute_binance and BINANCE_AVAILABLE:
                                if can_sell:
                                    if binance_client:
                                        execute_binance_order(binance_client, settings, Client.SIDE_SELL)
                                        order_attempted = True
                                    else: console.print("[warning]Eksekusi Binance aktif tapi client tidak valid/tersedia.[/]")
                                elif settings.get('sell_base_quantity') == 0:
                                    console.print("[info]Aksi 'sell' terdeteksi, tapi 'sell_base_quantity' = 0. Order Binance tidak dieksekusi.[/]")

                        else:
                            console.print(f"[info]Kata setelah '{settings['trigger_keyword']}' ('{action_word}') bukan 'buy' atau 'sell'. Tidak ada aksi market.[/]")

                        if execute_binance and BINANCE_AVAILABLE and action_word in ["buy", "sell"] and not order_attempted and not (action_word == "sell" and not can_sell):
                             console.print(f"[warning]Eksekusi tidak dilakukan (lihat pesan error client di atas).[/]")

                    else: console.print(f"[warning]Keyword trigger '{settings['trigger_keyword']}' ditemukan, tapi tidak ada kata setelahnya.[/]")
                else: console.print(f"[warning]Keyword target ditemukan, tapi trigger '{settings['trigger_keyword']}' tidak ditemukan [bold]setelahnya[/bold].[/]")

            except Exception as e:
                 console.print(f"[error]Gagal parsing kata setelah trigger: {e}[/]")
                 traceback.print_exc()
        else:
            console.print(f"[info]Keyword target '{settings['target_keyword']}' tidak ditemukan dalam email ini.[/]")

        # Tandai sebagai 'Seen'
        try:
            # console.print(f"[dim]Menandai email {email_id_str} sebagai 'Seen'...[/]", end='\r')
            mail.store(email_id, '+FLAGS', '\\Seen')
            # console.print(" " * 50, end='\r') # Hapus pesan
        except Exception as e:
            console.print(f"[error]Gagal menandai email {email_id_str} sebagai 'Seen': {e}[/]")
        console.rule(style="dim cyan") # Garis pemisah antar email

    except Exception as e:
        console.print(f"[error][bold]Gagal memproses email ID {email_id_str}:[/bold][/]")
        traceback.print_exc()


# --- Fungsi Listening Utama (MODIFIED for rich status) ---
def start_listening(settings):
    global running
    running = True
    mail = None
    binance_client = None
    last_check_time = time.time()
    consecutive_errors = 0
    max_consecutive_errors = 5
    long_wait_time = 60
    initial_wait_time = 2
    wait_time = initial_wait_time

    # Setup Binance Client
    execute_binance = settings.get("execute_binance_orders", False)
    if execute_binance:
        if not BINANCE_AVAILABLE:
             console.print("[danger]FATAL: Eksekusi Binance aktif tapi library python-binance tidak ada![/]")
             console.print("[warning]Install: [code]pip install python-binance[/] atau nonaktifkan di Pengaturan.[/]")
             running = False; return
        console.rule("[header]Inisialisasi Binance Client[/]", style="blue")
        binance_client = get_binance_client(settings)
        if not binance_client:
            console.print("[danger]FATAL: Gagal menginisialisasi Binance Client.[/]")
            console.print("[warning]Periksa API Key/Secret, koneksi, dan waktu sistem.[/]")
            console.print("[warning]Eksekusi order Binance [bold]TIDAK[/bold] akan berfungsi.[/]")
            # Lanjut untuk email saja
            console.print("[info]Program akan lanjut untuk notifikasi email saja.[/]")
        else: console.print("[success]Binance Client siap.[/]")
        console.rule(style="blue")
    else:
        console.print("\n[info]Eksekusi order Binance [bold yellow]dinonaktifkan[/].[/]")
        console.print("[dim](Hanya notifikasi email dan beep yang akan aktif)[/]")
        console.rule(style="dim")

    # Loop Utama
    while running:
        try:
            if not mail or mail.state != 'SELECTED':
                console.print(f"\n[info]Menghubungkan ke IMAP [bold]{settings['imap_server']}[/bold]...[/]")
                try:
                    mail = imaplib.IMAP4_SSL(settings['imap_server'], timeout=30)
                    console.print(f"[info]Login sebagai [bold]{settings['email_address']}[/bold]...[/]")
                    rv, desc = mail.login(settings['email_address'], settings['app_password'])
                    if rv != 'OK': raise imaplib.IMAP4.error(f"Login failed: {desc}")
                    console.print("[success][bold]Login email berhasil![/bold][/]")
                    mail.select("inbox")
                    console.print("[success]Memulai mode mendengarkan di INBOX...[/] [dim](Ctrl+C untuk berhenti)[/]")
                    console.rule(style="green")
                    consecutive_errors = 0
                    wait_time = initial_wait_time
                except (imaplib.IMAP4.error, OSError, socket.error) as login_err:
                     console.print(f"[danger]FATAL: Login Email GAGAL![/]")
                     console.print(f"[error]Pesan: {login_err}[/]")
                     console.print(f"[warning]Periksa Email, App Password, dan izin IMAP di akun Anda.[/]")
                     running = False; mail = None; continue

            # Loop Cek Email & Koneksi
            while running:
                current_time = time.time()
                wait_interval = settings['check_interval_seconds']

                # --- Gunakan console.status untuk indikator tunggu ---
                status_msg = f"[info]Memeriksa email baru & koneksi ({datetime.datetime.now():%H:%M:%S})...[/]"
                with console.status(status_msg, spinner="dots"):
                    # Cek Interval (jangan cek terlalu cepat)
                    while time.time() - last_check_time < wait_interval:
                        if not running: break
                        time.sleep(0.2) # Tidur singkat
                    if not running: break

                    # Cek Koneksi IMAP NOOP
                    try:
                        status, _ = mail.noop()
                        if status != 'OK':
                            console.print(f"\n[warning]Koneksi IMAP NOOP gagal (Status: {status}). Reconnect...[/]")
                            try: mail.close()
                            except: pass
                            mail = None; break
                    except (imaplib.IMAP4.abort, imaplib.IMAP4.readonly, BrokenPipeError, OSError) as noop_err:
                         console.print(f"\n[warning]Koneksi IMAP terputus ({type(noop_err).__name__}). Reconnect...[/]")
                         try: mail.logout()
                         except: pass
                         mail = None; break

                    # Cek Koneksi Binance (lebih jarang)
                    if binance_client and current_time - getattr(binance_client, '_last_ping_time', 0) > max(60, wait_interval * 5):
                         try:
                             # console.print("[dim]Pinging Binance...[/]", end='\r')
                             binance_client.ping()
                             setattr(binance_client, '_last_ping_time', current_time)
                             # console.print(" " * 20, end='\r')
                         except Exception as ping_err:
                             console.print(f"\n[warning]Ping ke Binance API gagal ({ping_err}). Coba buat ulang client...[/]")
                             binance_client = get_binance_client(settings)
                             if binance_client:
                                 console.print("[success]   Binance client berhasil dibuat ulang.[/]")
                                 setattr(binance_client, '_last_ping_time', current_time)
                             else:
                                 console.print("[error]   Gagal membuat ulang Binance client.[/]")
                                 setattr(binance_client, '_last_ping_time', 0) if binance_client else None # Reset timer jika gagal
                             time.sleep(3) # Jeda setelah error ping

                    # Cek Email UNSEEN
                    status, messages = mail.search(None, '(UNSEEN)')
                    if status != 'OK':
                         console.print(f"\n[error]Gagal mencari email UNSEEN: {status}. Reconnect...[/]")
                         try: mail.close()
                         except: pass
                         mail = None; break

                # --- Keluar dari console.status ---
                last_check_time = time.time() # Update waktu cek terakhir

                email_ids = messages[0].split()
                if email_ids:
                    num_emails = len(email_ids)
                    console.print(f"\n[success][bold] Ditemukan {num_emails} email baru! Memproses...[/bold][/]")
                    console.rule(style="cyan")
                    # Gunakan track jika > 1 email untuk progress bar
                    email_iterable = track(email_ids, description="[cyan]Memproses email...[/]", console=console) if RICH_AVAILABLE and num_emails > 1 else email_ids
                    for email_id in email_iterable:
                        if not running: break
                        process_email(mail, email_id, settings, binance_client)
                    if not running: break
                    console.print(f"[success]Selesai memproses {num_emails} email.[/]")
                    console.rule(style="green")
                    console.print("[info]Kembali mendengarkan...[/]") # Pesan setelah selesai proses
                # else: # Tidak perlu else, status sudah muncul saat menunggu
                #     pass

            # Keluar loop inner
            if mail and mail.state == 'SELECTED':
                try: mail.close()
                except Exception: pass

        except (imaplib.IMAP4.error, imaplib.IMAP4.abort, BrokenPipeError, OSError) as e:
            console.print(f"\n[error][bold]Kesalahan IMAP/Koneksi: {e}[/bold][/]")
            consecutive_errors += 1
            # Penanganan error login sudah di dalam loop koneksi
            if "login failed" not in str(e).lower() and "authentication failed" not in str(e).lower() and "invalid credentials" not in str(e).lower():
                if consecutive_errors >= max_consecutive_errors:
                     console.print(f"[warning]Terlalu banyak error ({consecutive_errors}). Menunggu {long_wait_time} detik...[/]")
                     time.sleep(long_wait_time); wait_time = initial_wait_time; consecutive_errors = 0
                else:
                     console.print(f"[warning]Mencoba reconnect dalam {wait_time} detik... (Error ke-{consecutive_errors})[/]")
                     time.sleep(wait_time); wait_time = min(wait_time * 2, 30)
            else: # Error login fatal, sudah ditangani sebelumnya
                 pass # running sudah False

        except (socket.error, socket.gaierror) as e:
             console.print(f"\n[error][bold]NETWORK ERROR: Kesalahan Jaringan: {e}[/bold][/]")
             consecutive_errors += 1
             if consecutive_errors >= max_consecutive_errors:
                 console.print(f"[warning]Terlalu banyak error jaringan ({consecutive_errors}). Menunggu {long_wait_time} detik...[/]")
                 time.sleep(long_wait_time); wait_time = initial_wait_time; consecutive_errors = 0
             else:
                 console.print(f"[warning]Periksa koneksi internet. Mencoba lagi dalam {wait_time} detik... (Error ke-{consecutive_errors})[/]")
                 time.sleep(wait_time); wait_time = min(wait_time * 2, 45)

        except Exception as e:
            console.print(f"\n[danger]ERROR KRITIS di loop utama:[/]")
            traceback.print_exc()
            consecutive_errors += 1
            console.print(f"[warning]Mencoba melanjutkan. Tunggu {wait_time} detik... (Error ke-{consecutive_errors})[/]")
            time.sleep(wait_time); wait_time = min(wait_time * 2, 60)
            if consecutive_errors >= max_consecutive_errors + 2:
                 console.print(f"[danger]Terlalu banyak error tak terduga. Berhenti.[/]")
                 running = False

        finally:
            if mail and mail.state != 'LOGOUT':
                try: mail.logout()
                except Exception: pass
            mail = None
        if running: time.sleep(0.5) # Jeda antar upaya koneksi

    console.print(f"\n[warning][bold]Mode mendengarkan dihentikan.[/bold][/]")


# --- Fungsi Menu Pengaturan (MODIFIED for rich Table) ---
def show_settings(settings):
    while True:
        clear_screen()
        console.print(Panel("[bold cyan]Pengaturan Email & Binance Listener[/]", style="cyan", expand=False, title_align="left"))

        # --- Gunakan Tabel Rich untuk Menampilkan Pengaturan ---
        table = Table(show_header=True, header_style="bold blue", border_style="dim", expand=False)
        table.add_column("No.", style="dim", width=3, justify="right")
        table.add_column("Kategori", style="info", width=8)
        table.add_column("Pengaturan", style="label", min_width=18)
        table.add_column("Nilai Saat Ini", style="value", min_width=30)

        # Email Settings
        table.add_row("1", "Email", "Alamat Email", settings['email_address'] or "[dim i]Belum diatur[/]")
        app_pass_display = f"*{'*' * (len(settings['app_password']) - 1)}" if len(settings['app_password']) > 1 else ('***' if settings['app_password'] else "[dim i]Belum diatur[/]")
        table.add_row("2", "Email", "App Password", app_pass_display)
        table.add_row("3", "Email", "Server IMAP", settings['imap_server'])
        table.add_row("4", "Email", "Interval Cek", f"{settings['check_interval_seconds']} detik")
        table.add_row("5", "Email", "Keyword Target", f"'{settings['target_keyword']}'")
        table.add_row("6", "Email", "Keyword Trigger", f"'{settings['trigger_keyword']}'")

        table.add_section() # Pemisah

        # Binance Settings
        binance_lib_status = "[success]Terinstall[/]" if BINANCE_AVAILABLE else "[error]Tidak Tersedia[/]"
        table.add_row("-", "Binance", "Library Status", binance_lib_status)
        api_key_display = f"{settings['binance_api_key'][:4]}...{settings['binance_api_key'][-4:]}" if len(settings['binance_api_key']) > 8 else ('[success]OK[/]' if settings['binance_api_key'] else "[dim i]Belum diatur[/]")
        api_secret_display = f"{settings['binance_api_secret'][:4]}...{settings['binance_api_secret'][-4:]}" if len(settings['binance_api_secret']) > 8 else ('[success]OK[/]' if settings['binance_api_secret'] else "[dim i]Belum diatur[/]")
        table.add_row("7", "Binance", "API Key", api_key_display)
        table.add_row("8", "Binance", "API Secret", api_secret_display)
        table.add_row("9", "Binance", "Trading Pair", settings['trading_pair'] or "[dim i]Belum diatur[/]")
        table.add_row("10", "Binance", "Buy Quote Qty", f"{settings['buy_quote_quantity']} [dim](USDT)[/]")
        sell_qty_style = "value" if settings['sell_base_quantity'] > 0 else "dim"
        table.add_row("11", "Binance", f"[{sell_qty_style}]Sell Base Qty[/]", f"[{sell_qty_style}]{settings['sell_base_quantity']}[/] [dim](BTC/ETH dll)[/]")
        exec_status = "[success][bold]Aktif[/bold][/]" if settings['execute_binance_orders'] else "[warning]Nonaktif[/]"
        table.add_row("12", "Binance", "Eksekusi Order", exec_status)

        console.print(table)
        console.rule(style="dim")

        # --- Opsi Menu Pengaturan (Inquirer atau Teks) ---
        if INQUIRER_AVAILABLE:
            questions = [
                inquirer.List('action',
                              message="[input]Pilih aksi[/]",
                              choices=[
                                  ('✏️ Edit Pengaturan', 'edit'),
                                  ('↩️ Kembali ke Menu Utama', 'back')
                              ],
                              carousel=True)
            ]
            try:
                 # Gunakan tema default atau GreenPassion jika rich tidak ada
                 theme_to_use = DefaultTheme()
                 answers = inquirer.prompt(questions, theme=theme_to_use)
                 choice = answers['action'] if answers else 'back'
            except Exception as e:
                 console.print(f"[error]Error pada menu interaktif: {e}[/]")
                 choice = 'back'
            except KeyboardInterrupt:
                 console.print(f"\n[warning]Edit dibatalkan.[/]")
                 choice = 'back'; time.sleep(1)
        else: # Fallback Teks
            console.print("\n[header]Opsi:[/]")
            console.print(" [input]E[/] - Edit Pengaturan")
            console.print(" [input]K[/] - Kembali ke Menu Utama")
            console.rule(style="dim")
            choice_input = input("Pilih opsi (E/K): ").lower().strip()
            if choice_input == 'e': choice = 'edit'
            elif choice_input == 'k': choice = 'back'
            else:
                console.print("[error]Pilihan tidak valid.[/]"); time.sleep(1.5); continue

        # --- Proses Pilihan ---
        if choice == 'edit':
            console.rule("[header]Edit Pengaturan[/]", style="blue")
            console.print("[dim](Kosongkan input untuk mempertahankan nilai saat ini)[/]")

            # --- Edit Email ---
            console.print("\n[header]--- Email ---[/]")
            new_val = console.input(f"[label] 1. Email [[i]{settings['email_address']}][/]]: ").strip()
            if new_val: settings['email_address'] = new_val
            console.print(f"[label] 2. App Password ([italic]input tersembunyi[/italic]): [/]", end="")
            try: new_pass = getpass.getpass("")
            except: new_pass = console.input(f"[warning](getpass gagal) App Password [{app_pass_display}]: [/]").strip()
            if new_pass: settings['app_password'] = new_pass
            else: console.print("[dim]   (Password tidak diubah)[/]")
            new_val = console.input(f"[label] 3. Server IMAP [[i]{settings['imap_server']}][/]]: ").strip()
            if new_val: settings['imap_server'] = new_val
            while True:
                new_val_str = console.input(f"[label] 4. Interval (detik) [[i]{settings['check_interval_seconds']}][/]], min 5: ").strip()
                if not new_val_str: break
                try:
                    new_interval = int(new_val_str)
                    if new_interval >= 5: settings['check_interval_seconds'] = new_interval; break
                    else: console.print(f"[error]   Interval minimal 5 detik.[/]")
                except ValueError: console.print(f"[error]   Masukkan angka bulat.[/]")
            new_val = console.input(f"[label] 5. Keyword Target [[i]{settings['target_keyword']}][/]]: ").strip()
            if new_val: settings['target_keyword'] = new_val
            new_val = console.input(f"[label] 6. Keyword Trigger [[i]{settings['trigger_keyword']}][/]]: ").strip()
            if new_val: settings['trigger_keyword'] = new_val

             # --- Edit Binance ---
            console.print("\n[header]--- Binance ---[/]")
            if not BINANCE_AVAILABLE: console.print(f"[warning]   (Library Binance tidak terinstall)[/]")
            new_val = console.input(f"[label] 7. API Key [[i]{api_key_display}][/]]: ").strip()
            if new_val: settings['binance_api_key'] = new_val
            console.print(f"[label] 8. API Secret ([italic]input tersembunyi[/italic]): [/]", end="")
            try: new_secret = getpass.getpass("")
            except: new_secret = console.input(f"[warning](getpass gagal) Secret [{api_secret_display}]: [/]").strip()
            if new_secret: settings['binance_api_secret'] = new_secret
            else: console.print("[dim]   (Secret tidak diubah)[/]")
            new_val = console.input(f"[label] 9. Trading Pair (e.g., BTCUSDT) [[i]{settings['trading_pair']}][/]]: ").strip().upper()
            if new_val: settings['trading_pair'] = new_val
            while True:
                 new_val_str = console.input(f"[label]10. Buy Quote Qty (e.g., 11.0) [[i]{settings['buy_quote_quantity']}][/]], > 0: ").strip()
                 if not new_val_str: break
                 try:
                     new_qty = float(new_val_str)
                     if new_qty > 0: settings['buy_quote_quantity'] = new_qty; break
                     else: console.print(f"[error]   Kuantitas Beli harus > 0.[/]")
                 except ValueError: console.print(f"[error]   Masukkan angka desimal (e.g., 11.0).[/]")
            while True:
                 new_val_str = console.input(f"[label]11. Sell Base Qty (e.g., 0.0005) [[i]{settings['sell_base_quantity']}][/]], >= 0: ").strip()
                 if not new_val_str: break
                 try:
                     new_qty = float(new_val_str)
                     if new_qty >= 0: settings['sell_base_quantity'] = new_qty; break
                     else: console.print(f"[error]   Kuantitas Jual harus >= 0.[/]")
                 except ValueError: console.print(f"[error]   Masukkan angka desimal (e.g., 0.0005).[/]")
            while True:
                 current_exec_display = "[success]Aktif[/]" if settings['execute_binance_orders'] else "[warning]Nonaktif[/]"
                 new_val_str = console.input(f"[label]12. Eksekusi Order? ({current_exec_display}) [y/n]: [/]").lower().strip()
                 if not new_val_str: break
                 if new_val_str == 'y':
                     if BINANCE_AVAILABLE: settings['execute_binance_orders'] = True; break
                     else: console.print(f"[error]   Tidak bisa aktif, library 'python-binance' tidak ada.[/]"); break
                 elif new_val_str == 'n': settings['execute_binance_orders'] = False; break
                 else: console.print(f"[error]   Masukkan 'y' atau 'n'.[/]")

            save_settings(settings)
            console.print(f"\n[success][bold]Pengaturan berhasil disimpan ke '{CONFIG_FILE}'.[/bold][/]")
            console.input(f"[dim]Tekan Enter untuk kembali...[/]")

        elif choice == 'back':
            break # Keluar loop pengaturan

# --- Fungsi Menu Utama (MODIFIED for rich & pyfiglet) ---
def main_menu():
    settings = load_settings()

    while True:
        clear_screen()
        # Judul Keren
        if PYFIGLET_AVAILABLE:
            try: # Font bisa tidak ada
                 ascii_art = pyfiglet.figlet_format("Exora AI", font="standard") # Coba 'slant', 'standard', 'smslant'
                 console.print(f"[title]{ascii_art}[/]", justify="center")
                 console.print("[bold blue] Email & Binance Listener [/]", justify="center")
            except:
                 console.print(Panel("[bold title] Exora AI - Email & Binance Listener [/]", style="magenta", expand=False), justify="center")
        else:
            console.print(Panel("[bold title] Exora AI - Email & Binance Listener [/]", style="magenta", expand=False), justify="center")

        console.rule("[dim]Status & Menu[/]", style="dim")

        # Status Konfigurasi dalam Panel
        status_lines = []
        email_status = "[success]OK[/]" if settings.get('email_address') else "[error]Kosong[/]"
        pass_status = "[success]OK[/]" if settings.get('app_password') else "[error]Kosong[/]"
        status_lines.append(f"[label]Email        :[/label] [{email_status}] Email | [{pass_status}] App Password")

        if BINANCE_AVAILABLE:
            api_status = "[success]OK[/]" if settings.get('binance_api_key') else "[error]Kosong[/]"
            secret_status = "[success]OK[/]" if settings.get('binance_api_secret') else "[error]Kosong[/]"
            pair_status = f"[success]{settings.get('trading_pair')}[/]" if settings.get('trading_pair') else "[error]Kosong[/]"
            buy_qty_ok = settings.get('buy_quote_quantity', 0) > 0
            sell_qty_ok = settings.get('sell_base_quantity', 0) >= 0
            buy_qty_display = f"[success]OK ({settings['buy_quote_quantity']})[/]" if buy_qty_ok else "[error]Invalid (<=0)[/]"
            sell_qty_display = f"[success]OK ({settings['sell_base_quantity']})[/]" if sell_qty_ok else "[error]Invalid (<0)[/]"
            if settings.get('sell_base_quantity') == 0 and settings['execute_binance_orders']:
                sell_qty_display = f"[warning]OK (0 - Sell Nonaktif)[/]"

            exec_mode = "[success][bold]AKTIF[/][/]" if settings.get('execute_binance_orders') else "[warning]NONAKTIF[/]"
            status_lines.append(f"[label]Binance Lib  :[/label] [success]Terinstall[/]")
            status_lines.append(f"[label]Binance Akun :[/label] [{api_status}] API | [{secret_status}] Secret | [{pair_status}] Pair")
            status_lines.append(f"[label]Binance Qty  :[/label] [{buy_qty_display}] Buy | [{sell_qty_display}] Sell")
            status_lines.append(f"[label]Eksekusi     :[/label] [{exec_mode}]")
        else:
            status_lines.append(f"[label]Binance Lib  :[/label] [error]Tidak Terinstall[/] [dim](pip install python-binance)[/]")

        console.print(Panel("\n".join(status_lines), title="[header]Status Konfigurasi[/]", border_style="blue", expand=False))
        console.rule(style="dim")

        # Pilihan Menu Utama (Inquirer atau Teks)
        menu_title = "[input]Menu Utama[/] [dim](Gunakan ↑ / ↓ dan Enter)[/]" if INQUIRER_AVAILABLE else "[input]Menu Utama (Ketik Pilihan):[/]"

        if INQUIRER_AVAILABLE:
            binance_mode = "[dim](Email & [bold]Binance[/][/])" if settings.get("execute_binance_orders") and BINANCE_AVAILABLE else "[dim](Email Only)[/]"
            choices = [
                (f" ▶️ Mulai Mendengarkan {binance_mode}", 'start'),
                (f" ⚙️ Pengaturan", 'settings'),
                (f" 🚪 Keluar", 'exit')
            ]
            questions = [inquirer.List('main_choice', message=menu_title, choices=choices, carousel=True)]
            try:
                 theme_to_use = DefaultTheme()
                 answers = inquirer.prompt(questions, theme=theme_to_use)
                 choice_key = answers['main_choice'] if answers else 'exit'
            except Exception as e: console.print(f"[error]Error menu: {e}[/]"); choice_key = 'exit'
            except KeyboardInterrupt: console.print(f"\n[warning]Keluar dari menu...[/]"); choice_key = 'exit'; time.sleep(1)
        else: # Fallback Teks
            console.print(f"\n{menu_title}")
            binance_mode_txt = "(Email & [bold]Binance[/])" if settings.get("execute_binance_orders") and BINANCE_AVAILABLE else "(Email Only)"
            console.print(f" [success]1.[/] Mulai Mendengarkan {binance_mode_txt}")
            console.print(f" [info]2.[/] Pengaturan")
            console.print(f" [error]3.[/] Keluar")
            console.rule(style="dim")
            choice_input = console.input("[input]Masukkan pilihan Anda (1/2/3): [/]").strip()
            if choice_input == '1': choice_key = 'start'
            elif choice_input == '2': choice_key = 'settings'
            elif choice_input == '3': choice_key = 'exit'
            else: choice_key = 'invalid'

        # Proses Pilihan
        if choice_key == 'start':
            console.rule(style="dim")
            valid_email = settings.get('email_address') and settings.get('app_password')
            execute_binance = settings.get("execute_binance_orders", False)
            valid_binance_config = False
            if execute_binance and BINANCE_AVAILABLE:
                 valid_binance_config = (settings.get('binance_api_key') and settings.get('binance_api_secret') and
                                     settings.get('trading_pair') and settings.get('buy_quote_quantity', 0) > 0 and
                                     settings.get('sell_base_quantity', 0) >= 0)

            error_messages = []
            if not valid_email: error_messages.append("[error][X] Pengaturan Email (Alamat/App Password) belum lengkap![/]")
            if execute_binance and not BINANCE_AVAILABLE:
                error_messages.append("[error][X] Eksekusi Binance aktif tapi library 'python-binance' tidak ada![/]")
                error_messages.append("[dim]    Install: [code]pip install python-binance[/] atau nonaktifkan.[/]")
            if execute_binance and BINANCE_AVAILABLE and not valid_binance_config:
                 error_messages.append("[error][X] Eksekusi Binance aktif tapi konfigurasinya belum lengkap/valid![/]")
                 details = []
                 if not settings.get('binance_api_key'): details.append("API Key")
                 if not settings.get('binance_api_secret'): details.append("API Secret")
                 if not settings.get('trading_pair'): details.append("Trading Pair")
                 if settings.get('buy_quote_quantity', 0) <= 0: details.append("Buy Qty <= 0")
                 if settings.get('sell_base_quantity', 0) < 0: details.append("Sell Qty < 0")
                 if details: error_messages.append(f"[dim]    Periksa: {', '.join(details)}.[/]")

            if error_messages:
                console.print(Panel("\n".join(error_messages), title="[warning]Tidak Bisa Memulai[/]", border_style="yellow", expand=False))
                console.print(f"\n[warning]Silakan perbaiki melalui menu '[info]Pengaturan[/]'.[/]")
                console.input(f"[dim]Tekan Enter untuk kembali...[/]")
            else:
                clear_screen()
                mode = "Email & Binance Order" if execute_binance and BINANCE_AVAILABLE else "Email Listener Only"
                console.print(Panel(f"[bold success]--- Memulai Mode: {mode} ---[/]", style="green", expand=False))
                start_listening(settings)
                console.print(f"\n[info]Kembali ke Menu Utama...[/]")
                time.sleep(2)

        elif choice_key == 'settings':
            show_settings(settings)
            settings = load_settings() # Load ulang jika ada perubahan

        elif choice_key == 'exit':
            console.print(f"\n[highlight]Terima kasih telah menggunakan Exora AI Listener! Sampai jumpa![/]")
            sys.exit(0)

        elif choice_key == 'invalid':
            console.print(f"\n[error]Pilihan tidak valid. Masukkan 1, 2, atau 3.[/]")
            time.sleep(1.5)

# --- Entry Point ---
if __name__ == "__main__":
    if sys.version_info < (3, 6):
        console.print("[danger]Error: Script ini membutuhkan Python 3.6 atau lebih tinggi.[/]")
        sys.exit(1)
    try:
        main_menu()
    except KeyboardInterrupt:
        console.print(f"\n[warning][bold]Program dihentikan paksa dari luar menu.[/bold][/]")
        sys.exit(1)
    except Exception as e:
        clear_screen()
        console.print(Panel("[bold danger] ERROR KRITIS [/]", expand=False, style="bold red on white"))
        console.print("[error]Terjadi kesalahan fatal yang tidak tertangani:[/]")
        console.print_exception(show_locals=False) # Tampilkan traceback dengan rich
        console.print(f"\n[error]Pesan Error: {e}[/]")
        console.print("[danger]Program tidak dapat melanjutkan dan akan keluar.[/]")
        console.input(f"[dim]Tekan Enter untuk keluar...[/]")
        sys.exit(1)
