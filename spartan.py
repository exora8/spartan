# -*- coding: utf-8 -*-
import imaplib
import email
from email.header import decode_header
import time
import datetime
import subprocess
import json
import os
import getpass
import sys
import signal
import traceback
import socket
import itertools
import logging # Import logging standar

# --- Rich Integration ---
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.layout import Layout
    from rich.live import Live
    from rich.logging import RichHandler
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
    from rich.prompt import Prompt, Confirm, IntPrompt, FloatPrompt
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("\n!!! FATAL: Library 'rich' tidak ditemukan. Tampilan keren tidak akan berfungsi. !!!")
    print("!!!          Install dengan: pip install rich                                   !!!\n")
    # Definisikan class/fungsi dummy jika rich tidak ada agar tidak crash total saat import
    class DummyRich:
        def __getattr__(self, name):
            print(f"!!! RICH ERROR: Mencoba akses '{name}' tapi 'rich' tidak terinstall.")
            return lambda *args, **kwargs: None
    Console = Panel = Text = Layout = Live = RichHandler = Table = Progress = SpinnerColumn = BarColumn = TextColumn = Prompt = Confirm = IntPrompt = FloatPrompt = DummyRich
    # Tetap keluar jika rich tidak ada, karena UI jadi andalan
    sys.exit("Error: Library 'rich' dibutuhkan.")

# --- Binance Integration ---
# (Bagian Binance tetap sama, pastikan BINANCE_AVAILABLE dicek)
try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException, BinanceOrderException
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False
    # Definisikan exception dummy jika library tidak ada agar script tidak crash
    class BinanceAPIException(Exception): pass
    class BinanceOrderException(Exception): pass
    class Client: pass # Dummy class
# --- Konfigurasi & Variabel Global ---
# (Bagian Konfigurasi tetap sama)
CONFIG_FILE = "config.json"
DEFAULT_SETTINGS = {
    # ... (default settings sama) ...
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

# --- Rich Setup ---
console = Console()
logging.basicConfig(
    level="INFO",
    format="%(message)s", # Biarkan RichHandler yg format
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True, markup=True)] # Gunakan RichHandler
)
log = logging.getLogger("rich") # Dapatkan logger

# --- Helper & Util (Disederhanakan/Diganti rich) ---
def clear_screen():
    # Handled oleh Console atau Live
    console.clear()

def get_timestamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Fungsi animasi lama (spinning_message, animate_wait, pulse_message, typing_effect, draw_box)
# akan digantikan oleh fitur Rich seperti console.status, Panel, Progress, dll.

# --- Fungsi Penanganan Sinyal (Ctrl+C) ---
def signal_handler(sig, frame):
    global running
    running = False
    # Hentikan Live display jika ada sebelum print pesan keluar
    # (Perlu cara untuk mengakses variabel 'live' dari sini, misal global atau class)
    log.warning("[bold yellow]Ctrl+C terdeteksi. Menghentikan program...[/]")
    # Beri jeda sedikit agar pesan terlihat jika live aktif
    time.sleep(0.5)
    # Mungkin perlu clear screen lagi setelah live berhenti
    console.clear()
    log.info("[bold red]🚪 Keluar dari program.[/]")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# --- Fungsi Konfigurasi (Contoh Modifikasi Pesan) ---
def load_settings():
    settings = DEFAULT_SETTINGS.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_settings = json.load(f)
                settings.update(loaded_settings)

            # Validasi dengan log.warning
            if settings.get("check_interval_seconds", 10) < 5:
                log.warning(f"Interval cek di '{CONFIG_FILE}' < 5 detik, direset ke 10.")
                settings["check_interval_seconds"] = 10
            # ... (validasi lain pakai log.warning) ...
            if not isinstance(settings.get("execute_binance_orders"), bool):
                log.warning("'execute_binance_orders' tidak valid, direset ke False.")
                settings["execute_binance_orders"] = False

        except json.JSONDecodeError:
            log.error(f"File konfigurasi '{CONFIG_FILE}' rusak. Menggunakan default & menyimpan ulang.")
            save_settings(settings)
        except Exception as e:
            log.error(f"Gagal memuat konfigurasi: {e}", exc_info=True)
    else:
        log.info(f"File konfigurasi '{CONFIG_FILE}' tidak ditemukan. Membuat dengan nilai default.")
        save_settings(settings)
    return settings

def save_settings(settings):
    try:
        # ... (validasi tipe data sama) ...
        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings, f, indent=4, sort_keys=True)
        # Pesan sukses dengan log.info dan markup
        log.info(f"[bold green]💾 Pengaturan berhasil disimpan ke '[cyan]{CONFIG_FILE}[/]'[/]")
    except Exception as e:
        log.error(f"Gagal menyimpan konfigurasi: {e}", exc_info=True)

# --- Fungsi Utilitas (Contoh Modifikasi Pesan Error) ---
def decode_mime_words(s):
    # ... (logika sama) ...
    # Ganti print dengan log.warning
    # except Exception as e:
    #     log.warning(f"Gagal decode header: {e}")
    #     return str(s)
    # (Kode asli decode_mime_words sudah cukup baik)
    if not s: return ""
    try:
        decoded_parts = decode_header(s)
        result = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(encoding or 'utf-8', errors='replace'))
            else:
                result.append(part)
        return "".join(result)
    except Exception as e:
        log.warning(f"Gagal decode header: {e}")
        return str(s) # Kembalikan string asli jika gagal total


def get_text_from_email(msg):
    # ... (logika sama) ...
    # Ganti print dengan log.warning
    # except Exception as e:
    #      log.warning(f"Tidak bisa mendekode bagian email: {e}")
    # (Kode asli get_text_from_email sudah cukup baik)
    text_content = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    text_content += payload.decode(charset, errors='replace')
                except Exception as e:
                    log.warning(f"Tidak bisa mendekode bagian email: {e}")
    else:
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                text_content = payload.decode(charset, errors='replace')
            except Exception as e:
                 log.warning(f"Tidak bisa mendekode body email: {e}")
    return text_content.lower()


# --- Fungsi Beep (Contoh Modifikasi Pesan) ---
def trigger_beep(action):
    action_upper = action.upper()
    action_display = f"[bold green]{action_upper}[/]" if action_upper == "BUY" else f"[bold red]{action_upper}[/]" if action_upper == "SELL" else action
    try:
        if action_upper in ["BUY", "SELL"]:
            log.info(f"[bold magenta]⚡ ACTION ⚡[/] Memicu BEEP untuk {action_display}!")
            # ... (subprocess.run sama)
            if action == "buy":
                subprocess.run(["beep", "-f", "1000", "-l", "500", "-D", "500", "-r", "5"], check=True, capture_output=True, text=True)
            elif action == "sell":
                subprocess.run(["beep", "-f", "700", "-l", "1000", "-D", "500", "-r", "2"], check=True, capture_output=True, text=True)
        else:
             log.warning(f"Aksi beep tidak dikenal '{action}'.")
    except FileNotFoundError:
        log.warning("Perintah 'beep' tidak ditemukan. Beep dilewati.")
    except subprocess.CalledProcessError as e:
        log.error(f"Gagal menjalankan 'beep': {e}")
        if e.stderr: log.error(f"         Stderr: {e.stderr.strip()}")
    except Exception as e:
        log.error(f"Kesalahan tak terduga saat beep: {e}", exc_info=True)

# --- Fungsi Eksekusi Binance (Contoh Modifikasi dengan `console.status`) ---
def get_binance_client(settings):
    if not BINANCE_AVAILABLE:
        log.error("[bold red]Library python-binance tidak terinstall. Tidak bisa membuat client.[/]")
        return None
    if not settings.get('binance_api_key') or not settings.get('binance_api_secret'):
        log.error("[bold red]API Key atau Secret Key Binance belum diatur![/]")
        return None

    client = None
    connect_msg = "[cyan]Menghubungkan ke Binance API...[/]"
    try:
        # Gunakan console.status untuk animasi
        with console.status(connect_msg, spinner="dots") as status:
            # (Tidak perlu loop timeout manual di sini, biarkan Client handle timeout)
            status.update("[cyan]Menginisialisasi Binance Client...[/]")
            client_instance = Client(settings['binance_api_key'], settings['binance_api_secret'])

            status.update("[cyan]Melakukan ping ke Binance API...[/]")
            client_instance.ping() # Test koneksi

            # Jika sampai sini berarti berhasil
            client = client_instance

        # Pesan sukses setelah status selesai
        log.info("[bold green]🔗 Koneksi ke Binance API Berhasil![/]")
        return client

    except BinanceAPIException as e:
        log.error(f"[bold red][BINANCE ERROR][/] Gagal terhubung/autentikasi: {e}")
        return None
    except Exception as e:
        log.error(f"Gagal membuat Binance client: {e}", exc_info=True)
        return None

def execute_binance_order(client, settings, side):
    if not client:
        log.warning("[BINANCE] Eksekusi dibatalkan, client tidak valid.")
        return False
    if not settings.get("execute_binance_orders", False):
        log.info("[BINANCE] Eksekusi order dinonaktifkan ('execute_binance_orders': false). Order dilewati.")
        return False

    pair = settings.get('trading_pair', '').upper()
    if not pair:
        log.error("[BINANCE ERROR] Trading pair belum diatur!")
        return False

    order_details = {}
    action_desc = ""
    action_color = "white" # Default color for rich markup

    try:
        if side == Client.SIDE_BUY:
            quote_qty = settings.get('buy_quote_quantity', 0.0)
            if quote_qty <= 0:
                 log.error("[BINANCE ERROR] Kuantitas Beli (buy_quote_quantity) harus > 0.")
                 return False
            order_details = { 'symbol': pair, 'side': Client.SIDE_BUY, 'type': Client.ORDER_TYPE_MARKET, 'quoteOrderQty': quote_qty }
            action_desc = f"MARKET BUY {quote_qty} (quote) of {pair}"
            action_color = "green"

        elif side == Client.SIDE_SELL:
            base_qty = settings.get('sell_base_quantity', 0.0)
            if base_qty <= 0:
                 log.error("[BINANCE ERROR] Kuantitas Jual (sell_base_quantity) harus > 0.")
                 return False
            order_details = { 'symbol': pair, 'side': Client.SIDE_SELL, 'type': Client.ORDER_TYPE_MARKET, 'quantity': base_qty }
            action_desc = f"MARKET SELL {base_qty} (base) of {pair}"
            action_color = "red"
        else:
            log.error(f"[BINANCE ERROR] Sisi order tidak valid: {side}")
            return False

        log.info(f"[bold magenta][BINANCE ACTION][/] Mencoba eksekusi: [bold {action_color}]{action_desc}[/]")

        order_result = None
        # Animasi saat mengirim order dengan console.status
        executing_msg = f"[magenta]Mengirim order {action_desc} ke Binance...[/]"
        try:
            with console.status(executing_msg, spinner="arrow3") as status:
                # --- EKSEKUSI ORDER SEBENARNYA ---
                order_result = client.create_order(**order_details)
                # ----------------------------------
                # (Tidak perlu loop timeout manual, biarkan client handle)
                # Jeda singkat agar status terlihat
                time.sleep(0.5)

            # Jika sampai sini, order terkirim (belum tentu sukses diisi)
            log.info(f"[bold {action_color}]🚀 Order [{order_result.get('side')}] untuk {order_result.get('symbol')} berhasil dikirim (ID: {order_result.get('orderId')})![/]")
            log.info(f"  Status   : [bold]{order_result.get('status')}[/]")
            if order_result.get('fills') and order_result['fills']:
                total_qty = sum(float(f['qty']) for f in order_result['fills'])
                total_quote_qty = sum(float(f['qty']) * float(f['price']) for f in order_result['fills'])
                avg_price = total_quote_qty / total_qty if total_qty else 0
                log.info(f"  Avg Price: [bold cyan]{avg_price:.8f}[/]")
                log.info(f"  Filled Qty: [bold cyan]{total_qty:.8f}[/]")
            elif order_result.get('status') == 'FILLED':
                 # Jika status FILLED tapi fills kosong (jarang terjadi, tapi mungkin untuk market order kecil)
                 log.info(f"  Executed Qty: [bold cyan]{order_result.get('executedQty')}[/]")

            return True

        except (BinanceAPIException, BinanceOrderException) as e:
            log.error(f"[bold red][BINANCE EXECUTION FAILED][/]")
            log.error(f"  Error Code: {e.code} - Pesan: {e.message}")
            # Pesan bantuan spesifik
            if isinstance(e, BinanceAPIException):
                if e.code == -2010: log.warning("    -> Kemungkinan saldo tidak cukup.")
                elif e.code == -1121: log.warning(f"    -> Trading pair '{pair}' tidak valid.")
                elif e.code == -1013 or ('MIN_NOTIONAL' in str(e.message).upper()): log.warning("    -> Order size terlalu kecil (cek MIN_NOTIONAL/LOT_SIZE).")
            return False
        except Exception as e:
            log.error("Kesalahan tak terduga saat eksekusi order Binance:", exc_info=True)
            return False

    except Exception as e:
        log.error(f"Kesalahan tak terduga di fungsi execute_binance_order: {e}", exc_info=True)
        return False


# --- Fungsi Pemrosesan Email (Contoh Modifikasi Logging) ---
def process_email(mail, email_id, settings, binance_client):
    global running
    if not running: return

    target_keyword_lower = settings['target_keyword'].lower()
    trigger_keyword_lower = settings['trigger_keyword'].lower()
    email_id_str = email_id.decode('utf-8')

    log.info(f"--- 📨 Memproses Email ID: [cyan]{email_id_str}[/] ---")

    try:
        # Animasi fetch dengan status
        status_msg = f"[cyan]Mengambil email ID {email_id_str}...[/]"
        status, data = None, None
        fetch_tries = 0
        MAX_FETCH_TRIES = 3

        with console.status(status_msg, spinner="moon") as status_ctx:
            while fetch_tries < MAX_FETCH_TRIES and status != 'OK' and running:
                try:
                    status, data = mail.fetch(email_id, "(RFC822)")
                    if status != 'OK':
                        fetch_tries += 1
                        status_ctx.update(f"[yellow]Fetch email ID {email_id_str} gagal ({status}), coba lagi ({fetch_tries}/{MAX_FETCH_TRIES})...[/]")
                        time.sleep(0.5)
                    # Jika OK, loop akan berhenti
                except Exception as fetch_err:
                     log.error(f"Error saat fetch email {email_id_str}: {fetch_err}")
                     status = 'ERROR' # Tandai error agar tidak loop lagi
                     break # Keluar loop fetch
                if not running: return

        if status != 'OK':
            log.error(f"Gagal total mengambil email ID {email_id_str} setelah {fetch_tries} percobaan.")
            return

        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        subject = decode_mime_words(msg["Subject"])
        sender = decode_mime_words(msg["From"])

        log.info(f"  [dim]Dari  :[/dim] {sender}")
        log.info(f"  [bold]Subjek:[/bold] {subject}")

        body = get_text_from_email(msg)
        full_content = (subject.lower() + " " + body)

        if target_keyword_lower in full_content:
            log.info(f"[bold green]✅ Keyword target '[cyan]{settings['target_keyword']}[/]' ditemukan![/]")
            try:
                target_index = full_content.index(target_keyword_lower)
                trigger_index = full_content.index(trigger_keyword_lower, target_index + len(target_keyword_lower))
                start_word_index = trigger_index + len(trigger_keyword_lower)
                text_after_trigger = full_content[start_word_index:].lstrip()
                words_after_trigger = text_after_trigger.split(maxsplit=1)

                if words_after_trigger:
                    action_word = words_after_trigger[0].strip('.,!?:;()[]{}').lower()
                    action_color = "green" if action_word == "buy" else "red" if action_word == "sell" else "yellow"
                    log.info(f"  Keyword trigger '[cyan]{settings['trigger_keyword']}[/]' ditemukan. Kata berikutnya: '[bold {action_color}]{action_word.upper()}[/]'")

                    # --- Trigger Aksi (Beep dan/atau Binance) ---
                    if action_word in ["buy", "sell"]:
                        trigger_beep(action_word)
                        if binance_client and settings.get("execute_binance_orders"):
                            side = Client.SIDE_BUY if action_word == "buy" else Client.SIDE_SELL
                            execute_binance_order(binance_client, settings, side)
                        elif settings.get("execute_binance_orders"):
                            log.warning("Eksekusi Binance aktif tapi client tidak valid/tersedia.")
                    else:
                        log.warning(f"Kata '{action_word}' bukan 'buy'/'sell'. Tidak ada aksi market.")

                else:
                    log.warning(f"Tidak ada kata setelah '{settings['trigger_keyword']}'.")

            except ValueError:
                log.warning(f"Keyword trigger '[cyan]{settings['trigger_keyword']}[/]' tidak ditemukan [bold]setelah[/] '[cyan]{settings['target_keyword']}[/]'.")
            except Exception as e:
                 log.error(f"Gagal parsing kata setelah trigger: {e}", exc_info=True)
        else:
            log.info(f"[blue]ℹ️ Keyword target '[cyan]{settings['target_keyword']}[/]' tidak ditemukan.[/]")

        # Tandai email sebagai 'Seen' dengan status
        mark_msg = f"[dim]Menandai email {email_id_str} sebagai 'Seen'...[/]"
        marked = False
        try:
            with console.status(mark_msg, spinner="point") as status_ctx:
                # (Tidak perlu loop timeout, biarkan store handle)
                status, _ = mail.store(email_id, '+FLAGS', '\\Seen')
                if status == 'OK':
                    marked = True
                time.sleep(0.2) # Jeda singkat

            if marked:
                log.info(f"  [dim]Email {email_id_str} ditandai 'Seen'.[/]")
            else:
                log.warning(f"Gagal menandai email {email_id_str} 'Seen' (Status: {status}). Mungkin sudah ditandai?")
        except Exception as e:
            log.error(f"Gagal menandai email {email_id_str} sebagai 'Seen': {e}")

    except Exception as e:
        log.error(f"Gagal memproses email ID {email_id_str}:", exc_info=True)
    finally:
        log.info(f"--- Selesai proses email [cyan]{email_id_str}[/] ---")


# --- Layout Definition ---
def make_layout() -> Layout:
    """Definisikan layout TUI."""
    layout = Layout(name="root")

    layout.split(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1),
        Layout(name="footer", size=5), # Lebih besar untuk status
    )
    layout["main"].split_row(
        Layout(name="side", size=30, visible=False), # Bisa untuk info tambahan nanti
        Layout(name="body", ratio=1),
    )
    layout["footer"].split_row(
        Layout(name="status", ratio=1),
        Layout(name="clock", size=20)
    )
    return layout

# --- Panel/Widget Generators ---
def make_header() -> Panel:
    """Buat panel header."""
    title = "[bold magenta]📧 Exora AI - Email & Binance Listener 🤖[/]"
    return Panel(Text(title, justify="center"), border_style="magenta")

def make_status_bar(settings, imap_status, binance_status, listener_state) -> Panel:
    """Buat panel status bar."""
    cfg = settings # Alias pendek
    email_ok = cfg['email_address'] and cfg['app_password']
    b_exec = cfg['execute_binance_orders']
    b_creds_ok = cfg['binance_api_key'] and cfg['binance_api_secret']
    b_pair_ok = cfg['trading_pair']
    b_qty_ok = cfg['buy_quote_quantity'] > 0 and cfg['sell_base_quantity'] >= 0

    email_sym = "[green]✓[/]" if email_ok else "[red]✗[/]"
    imap_sym, imap_col = {"Connected": ("✓", "green"), "Connecting": ("~", "yellow"), "Disconnected": ("✗", "red"), "Error": ("!", "red"), "Idle": ("-","dim")}.get(imap_status, ("?", "yellow"))
    imap_disp = f"IMAP: [{imap_col}]{imap_sym} {imap_status}[/]"

    if b_exec:
        b_avail_sym = "[green]✓[/]" if BINANCE_AVAILABLE else "[red]✗ Lib[/]"
        b_cred_sym = "[green]✓[/]" if b_creds_ok else "[red]✗ Creds[/]"
        b_pair_sym = f"[green]{cfg['trading_pair']}[/]" if b_pair_ok else "[red]✗ Pair[/]"
        b_qty_sym = "[green]✓ Qty[/]" if b_qty_ok else "[red]✗ Qty[/]"
        bin_sym, bin_col = {"Ready": ("✓", "green"), "Connecting": ("~", "yellow"), "Error": ("!", "red"), "Disabled": ("-", "dim"), "N/A": ("-", "dim")}.get(binance_status, ("?", "yellow"))
        binance_disp = f"Binance: [{bin_col}]{bin_sym} {binance_status}[/] ({b_avail_sym}{b_cred_sym}|{b_pair_sym}|{b_qty_sym})"
    else:
        binance_disp = "Binance: [dim]- Disabled[/]"

    state_sym, state_col = {"Listening": ("👂", "blue"), "Checking": ("🔎", "cyan"), "Processing": ("⚙️", "yellow"), "Waiting": ("⏳", "dim"), "Error": ("🔥", "red")}.get(listener_state, ("?", "magenta"))
    state_disp = f"State: [{state_col}]{state_sym} {listener_state}[/]"

    status_text = f"{email_sym} {imap_disp} | {binance_disp} | {state_disp}"
    return Panel(status_text, border_style="blue", title="[blue]Status[/]")

def make_clock() -> Panel:
    """Buat panel jam."""
    now = datetime.datetime.now()
    time_str = now.strftime("%H:%M:%S")
    date_str = now.strftime("%Y-%m-%d")
    clock_text = Text(f"{date_str}\n{time_str}", justify="center")
    return Panel(clock_text, border_style="green", title="[green]Time[/]")

# --- Fungsi Listening Utama (dengan `Live` dan `Layout`) ---
def start_listening(settings):
    global running
    running = True
    mail = None
    binance_client = None
    wait_time = 30
    consecutive_noop_failures = 0
    MAX_NOOP_FAILURES = 3

    # Status variables for the layout
    imap_status = "Disconnected"
    binance_status = "N/A"
    listener_state = "Initializing"

    # --- Setup Binance Client di Awal (jika diaktifkan) ---
    if settings.get("execute_binance_orders"):
        if not BINANCE_AVAILABLE:
            log.critical("[bold red]Eksekusi Binance diaktifkan tapi library python-binance tidak ada! Nonaktifkan atau install.[/]")
            running = False
            time.sleep(3)
            return # Keluar jika library krusial tidak ada

        listener_state = "Binance Connect"
        binance_status = "Connecting"
        # Harus diupdate di Live jika sudah jalan, tapi ini sebelum Live
        console.print(Panel("[cyan]Menginisialisasi koneksi Binance API...[/]", border_style="cyan"))
        binance_client = get_binance_client(settings)
        if not binance_client:
            binance_status = "Error"
            log.error("[bold red]Gagal inisialisasi Binance Client. Periksa API Key/Secret/Koneksi.[/]")
            log.warning("[yellow]Eksekusi order tidak akan berjalan. Menonaktifkan di Pengaturan akan mengabaikan ini.[/]")
            # Tidak menghentikan program
        else:
            binance_status = "Ready"
            log.info("[bold green]✅ Binance Client Siap Digunakan.[/]")
    else:
        binance_status = "Disabled"
        log.info("[yellow]ℹ️ Eksekusi order Binance dinonaktifkan.[/]")

    layout = make_layout()
    layout["header"].update(make_header())

    # --- Loop Utama dengan Live Update ---
    try:
        with Live(layout, refresh_per_second=4, screen=False, vertical_overflow="visible") as live: # screen=False agar log bisa scroll
            while running:
                try:
                    # Update status bar & clock setiap iterasi
                    layout["footer"]["status"].update(make_status_bar(settings, imap_status, binance_status, listener_state))
                    layout["footer"]["clock"].update(make_clock())
                    live.refresh() # Pastikan refresh

                    # --- Koneksi IMAP ---
                    imap_server = settings['imap_server']
                    email_addr = settings['email_address']
                    app_pass = settings['app_password']

                    if not mail or mail.state == 'LOGOUT':
                        imap_status = "Connecting"
                        listener_state = "IMAP Connect"
                        layout["footer"]["status"].update(make_status_bar(settings, imap_status, binance_status, listener_state))
                        live.refresh()
                        log.info(f"🔌 Menghubungkan ke {imap_server}...")
                        try:
                            mail = imaplib.IMAP4_SSL(imap_server, timeout=20) # Tambah timeout
                            imap_status = "Logging In"
                            listener_state = "IMAP Login"
                            layout["footer"]["status"].update(make_status_bar(settings, imap_status, binance_status, listener_state))
                            live.refresh()
                            log.info(f"🔑 Login sebagai {email_addr}...")
                            status, _ = mail.login(email_addr, app_pass)
                            if status == 'OK':
                                imap_status = "Connected"
                                listener_state = "Selecting Inbox"
                                layout["footer"]["status"].update(make_status_bar(settings, imap_status, binance_status, listener_state))
                                live.refresh()
                                log.info(f"[bold green]🔓 Login berhasil sebagai [cyan]{email_addr}[/][/]")
                                mail.select("inbox")
                                log.info("[bold green]📬 Memulai mode mendengarkan di INBOX...[/]")
                                listener_state = "Listening"
                                consecutive_noop_failures = 0
                            else:
                                raise imaplib.IMAP4.error(f"Login failed (Status: {status})")

                        except (socket.gaierror, OSError, socket.error, imaplib.IMAP4.error, TimeoutError) as e:
                            imap_status = "Error"
                            listener_state = "Error"
                            log.error(f"Gagal koneksi/login IMAP: {e}", exc_info=True)
                            if mail: mail.shutdown() # Coba tutup jika objek ada
                            mail = None
                            log.warning(f"Mencoba lagi dalam {wait_time} detik...")
                            # Animate wait directly might be tricky with Live, just sleep
                            for i in range(wait_time):
                                if not running: break
                                time.sleep(1)
                                layout["footer"]["clock"].update(make_clock()) # Update jam saat tunggu
                                live.refresh()
                            continue # Lanjut ke iterasi berikutnya untuk coba lagi
                        except Exception as e:
                            imap_status = "Error"
                            listener_state = "Error"
                            log.exception("Kesalahan tak terduga saat setup IMAP:")
                            if mail: mail.shutdown()
                            mail = None
                            raise # Lemparkan error fatal

                    # --- Loop Cek Email (Jika terkoneksi) ---
                    listener_state = "Checking"
                    layout["footer"]["status"].update(make_status_bar(settings, imap_status, binance_status, listener_state))
                    live.refresh()

                    # Cek koneksi IMAP dengan NOOP
                    try:
                        status, _ = mail.noop()
                        if status != 'OK':
                            consecutive_noop_failures += 1
                            log.warning(f"Koneksi IMAP NOOP gagal ({status}). Coba {consecutive_noop_failures}/{MAX_NOOP_FAILURES}.")
                            if consecutive_noop_failures >= MAX_NOOP_FAILURES:
                                log.warning("Terlalu banyak NOOP gagal. Reconnect paksa...")
                                raise imaplib.IMAP4.abort("Max NOOP failures reached") # Trigger reconnect
                        else:
                            consecutive_noop_failures = 0 # Reset jika berhasil
                    except (imaplib.IMAP4.abort, imaplib.IMAP4.readonly, OSError, socket.error, TimeoutError) as NopErr:
                         log.warning(f"Koneksi IMAP terputus ({NopErr}). Mencoba reconnect...")
                         raise imaplib.IMAP4.abort("Connection lost during NOOP") # Trigger reconnect

                    # (Cek koneksi Binance bisa ditambahkan di sini jika perlu periodic ping)
                    # ...

                    # --- Cek Email Baru (UNSEEN) ---
                    search_status, messages = 'ERROR', [b'']
                    try:
                        search_status, messages = mail.search(None, '(UNSEEN)')
                    except Exception as search_err:
                        log.error(f"Gagal mencari email UNSEEN: {search_err}")
                        raise imaplib.IMAP4.abort("Search command failed") # Trigger reconnect

                    if search_status == 'OK':
                        email_ids = messages[0].split()
                        if email_ids:
                            listener_state = "Processing"
                            log.info(f"[bold cyan]🎉 Menemukan {len(email_ids)} email baru! Memproses...[/]")
                            layout["footer"]["status"].update(make_status_bar(settings, imap_status, binance_status, listener_state))
                            live.refresh()
                            for email_id in email_ids:
                                if not running: break
                                process_email(mail, email_id, settings, binance_client)
                                time.sleep(0.1) # Jeda antar proses email
                            if not running: break
                            log.info("[bold green]✅ Selesai memproses batch email.[/]")
                            listener_state = "Listening" # Kembali listening
                        else:
                            # Tidak ada email baru, tunggu
                            listener_state = "Waiting"
                            wait_interval = settings['check_interval_seconds']
                            for i in range(wait_interval, 0, -1):
                                if not running: break
                                layout["footer"]["status"].update(make_status_bar(settings, imap_status, binance_status, f"Waiting ({i}s)"))
                                layout["footer"]["clock"].update(make_clock())
                                live.refresh()
                                time.sleep(1)
                            if not running: break
                            listener_state = "Listening" # Selesai tunggu
                    else:
                        log.error(f"Gagal mencari email (Status: {search_status}). Mencoba reconnect...")
                        raise imaplib.IMAP4.abort("Search command returned non-OK status") # Trigger reconnect

                # --- Exception Handling untuk Loop Dalam (utk trigger reconnect) ---
                except (imaplib.IMAP4.error, imaplib.IMAP4.abort, TimeoutError) as e:
                    imap_status = "Error"
                    listener_state = "Error"
                    log.error(f"Kesalahan IMAP: {e}. Mencoba reconnect...")
                    layout["footer"]["status"].update(make_status_bar(settings, imap_status, binance_status, listener_state))
                    live.refresh()
                    if mail:
                        try: mail.shutdown() # Coba tutup koneksi lama
                        except: pass
                    mail = None
                    imap_status = "Disconnected"
                    time.sleep(5) # Jeda sebelum coba konek lagi di iterasi berikutnya
                except Exception as e:
                    listener_state = "Error"
                    imap_status = "Error" # Asumsikan error IMAP jika tidak diketahui
                    log.exception("Kesalahan tak terduga di loop listener:")
                    layout["footer"]["status"].update(make_status_bar(settings, imap_status, binance_status, listener_state))
                    live.refresh()
                    if mail:
                        try: mail.shutdown()
                        except: pass
                    mail = None
                    imap_status = "Disconnected"
                    log.warning(f"Mencoba lagi dalam {wait_time} detik...")
                    for i in range(wait_time):
                        if not running: break
                        time.sleep(1)
                        layout["footer"]["clock"].update(make_clock())
                        live.refresh()

    # --- Keluar dari Live context (karena running=False atau error luar)
    finally:
        listener_state = "Stopped"
        imap_status = "Disconnected"
        log.info("[bold yellow]⏹️ Mode mendengarkan dihentikan.[/]")
        # Logout jika masih terkoneksi
        if mail and mail.state != 'LOGOUT':
            log.info("🚪 Logout dari server IMAP...")
            try: mail.logout()
            except Exception: pass
        mail = None
        # Update status terakhir sebelum Live hilang (mungkin tidak terlihat)
        layout["footer"]["status"].update(make_status_bar(settings, imap_status, binance_status, listener_state))
        # console.print(layout) # Cetak layout terakhir?


# --- Fungsi Menu Pengaturan (dengan `rich.prompt` dan `Table`) ---
def show_settings(settings):
    while True:
        console.clear()
        console.print(Panel("[bold cyan]⚙️ Pengaturan Email & Binance Listener ⚙️[/]", expand=False, border_style="cyan"))

        # Tampilkan pengaturan dalam tabel
        table = Table(title="Pengaturan Saat Ini", show_header=True, header_style="bold blue", border_style="dim")
        table.add_column("#", style="dim", width=3)
        table.add_column("Pengaturan", style="cyan", min_width=20)
        table.add_column("Nilai", style="white", min_width=30)

        # Email Settings
        table.add_row("1", "Alamat Email", settings['email_address'] or "[yellow]Belum diatur[/]")
        table.add_row("2", "App Password", ('*' * len(settings['app_password']) if settings['app_password'] else "[yellow]Belum diatur[/]"))
        table.add_row("3", "Server IMAP", settings['imap_server'])
        table.add_row("4", "Interval Cek (s)", str(settings['check_interval_seconds']), style="magenta" if settings['check_interval_seconds'] < 10 else "white")
        table.add_row("5", "Keyword Target", f"'{settings['target_keyword']}'")
        table.add_row("6", "Keyword Trigger", f"'{settings['trigger_keyword']}'")

        # Binance Settings
        table.add_section()
        bin_lib_status = "[green]Tersedia[/]" if BINANCE_AVAILABLE else "[red]Tidak Tersedia (Install 'python-binance')[/]"
        table.add_row("-", "[dim]Library Binance[/]", bin_lib_status)
        table.add_row("7", "API Key", (settings['binance_api_key'][:5] + '...' if settings['binance_api_key'] else "[yellow]Belum diatur[/]"))
        table.add_row("8", "API Secret", (settings['binance_api_secret'][:5] + '...' if settings['binance_api_secret'] else "[yellow]Belum diatur[/]"))
        table.add_row("9", "Trading Pair", settings['trading_pair'] or "[yellow]Belum diatur[/]")
        table.add_row("10", "Buy Quote Qty", f"{settings['buy_quote_quantity']:.2f}", style="green")
        table.add_row("11", "Sell Base Qty", f"{settings['sell_base_quantity']:.8f}", style="red" if settings['sell_base_quantity'] > 0 else "yellow")
        exec_status = "[bold green]✅ AKTIF[/]" if settings['execute_binance_orders'] else "[bold red]❌ NONAKTIF[/]"
        table.add_row("12", "Eksekusi Order", exec_status)

        console.print(table)
        console.print("\nOpsi:")
        console.print(Panel("[bold yellow]E[/] - Edit Pengaturan | [bold yellow]K[/] - Kembali ke Menu Utama", expand=False))

        choice = Prompt.ask("[bold]Pilih opsi[/]", choices=["e", "k"], default="k").lower()

        if choice == 'e':
            console.print(Panel("[bold magenta]--- Edit Pengaturan ---[/] [dim](Tekan Enter untuk skip)[/]", border_style="magenta"))

            # Gunakan Prompt dari Rich untuk input yang lebih baik
            settings['email_address'] = Prompt.ask(" 1. Email", default=settings['email_address'])
            # Password masih pakai getpass demi keamanan, tapi dalam Prompt
            new_pass = Prompt.ask(" 2. App Password", password=True, default="") # Default kosong agar tidak tampilkan bintang jika tidak diubah
            if new_pass: settings['app_password'] = new_pass

            settings['imap_server'] = Prompt.ask(" 3. Server IMAP", default=settings['imap_server'])
            settings['check_interval_seconds'] = IntPrompt.ask(" 4. Interval (detik, min 5)", default=settings['check_interval_seconds'], choices=None, show_default=True)
            if settings['check_interval_seconds'] < 5: settings['check_interval_seconds'] = 5 ; log.warning("Interval diatur ke minimum 5 detik.")

            settings['target_keyword'] = Prompt.ask(" 5. Keyword Target", default=settings['target_keyword'])
            settings['trigger_keyword'] = Prompt.ask(" 6. Keyword Trigger", default=settings['trigger_keyword'])

            console.print("\n[bold blue]--- Binance ---[/]")
            if not BINANCE_AVAILABLE:
                log.warning("Library Binance tidak terinstall, pengaturan ini mungkin tidak berpengaruh.")

            new_api_key = Prompt.ask(" 7. API Key", default=settings['binance_api_key'][:5] + '...' if settings['binance_api_key'] else "")
            # Jika input tidak kosong dan bukan placeholder, update
            if new_api_key and new_api_key != (settings['binance_api_key'][:5] + '...'): settings['binance_api_key'] = new_api_key

            new_api_secret = Prompt.ask(" 8. API Secret", password=True, default="")
            if new_api_secret: settings['binance_api_secret'] = new_api_secret

            settings['trading_pair'] = Prompt.ask(" 9. Trading Pair (e.g., BTCUSDT)", default=settings['trading_pair']).upper()

            settings['buy_quote_quantity'] = FloatPrompt.ask("10. Buy Quote Qty (e.g., 11.0)", default=settings['buy_quote_quantity'])
            if settings['buy_quote_quantity'] <= 0: settings['buy_quote_quantity'] = DEFAULT_SETTINGS['buy_quote_quantity']; log.warning("Buy Qty harus > 0, direset ke default.")

            settings['sell_base_quantity'] = FloatPrompt.ask("11. Sell Base Qty (e.g., 0.0005)", default=settings['sell_base_quantity'])
            if settings['sell_base_quantity'] < 0: settings['sell_base_quantity'] = DEFAULT_SETTINGS['sell_base_quantity']; log.warning("Sell Qty harus >= 0, direset ke default.")

            settings['execute_binance_orders'] = Confirm.ask("12. Eksekusi Order Binance?", default=settings['execute_binance_orders'])

            save_settings(settings)
            log.info("[bold green]Pengaturan diperbarui dan disimpan![/]")
            time.sleep(2)

        elif choice == 'k':
            break

# --- Fungsi Menu Utama (dengan `rich` dan validasi) ---
def main_menu():
    settings = load_settings()
    first_run = True

    while True:
        console.clear()
        console.print(make_header()) # Tampilkan header konsisten

        if first_run:
            console.print(Text("Selamat datang! Pilih opsi di bawah:", justify="center", style="cyan"))
            first_run = False
        else:
            console.print(Text("Menu Utama:", justify="center", style="bold blue"))

        # Opsi Menu dalam Panel
        menu_options = [
            "[bold green]1[/] - Mulai Mendengarkan",
            "[bold cyan]2[/] - Pengaturan",
            "[bold yellow]3[/] - Keluar"
        ]
        console.print(Panel("\n".join(menu_options), title="Opsi", border_style="green", expand=False))

        # Tampilkan status ringkas
        # (Status detail sudah ada di status bar saat listener jalan)
        email_ok = settings['email_address'] and settings['app_password']
        b_exec = settings['execute_binance_orders']
        b_creds_ok = settings['binance_api_key'] and settings['binance_api_secret']
        b_pair_ok = settings['trading_pair']
        b_ok = b_creds_ok and b_pair_ok

        status_text = Text()
        status_text.append("Status: ", style="bold")
        status_text.append("Email [", style="dim")
        status_text.append("✓" if email_ok else "✗", style="green" if email_ok else "red")
        status_text.append("] ", style="dim")
        if b_exec:
            status_text.append("Binance [", style="dim")
            status_text.append("✓" if b_ok else "✗", style="green" if b_ok else "red")
            status_text.append("] ", style="dim")
            status_text.append("Exec [bold green]ON[/]", style="dim")
        else:
            status_text.append("Binance Exec [bold yellow]OFF[/]", style="dim")

        console.print(Panel(status_text, border_style="dim", expand=False))

        choice = Prompt.ask("[bold]Masukkan pilihan Anda[/]", choices=["1", "2", "3"], default="3")

        if choice == '1':
            # Validasi sebelum memulai (pakai log)
            can_start = True
            if not email_ok:
                log.error("Pengaturan Email (Alamat/App Password) belum lengkap!")
                can_start = False
            if b_exec:
                if not BINANCE_AVAILABLE:
                    log.error("Eksekusi Binance aktif tapi library 'python-binance' tidak ditemukan!")
                    can_start = False
                if not b_ok:
                    log.error("Pengaturan Binance (API/Secret/Pair) belum lengkap untuk eksekusi!")
                    can_start = False
                if settings['buy_quote_quantity'] <= 0:
                    log.error("Kuantitas Beli (buy_quote_quantity) harus > 0.")
                    can_start = False
                if settings['sell_base_quantity'] < 0:
                    log.error("Kuantitas Jual (sell_base_quantity) tidak valid (< 0).")
                    can_start = False
                elif settings['sell_base_quantity'] == 0 :
                    log.warning("Kuantitas Jual (sell_base_quantity) adalah 0. Aksi SELL tidak akan tereksekusi.")
                    # time.sleep(1.5) # Tidak perlu sleep di menu

            if can_start:
                console.clear()
                mode = "Email & Binance Order" if b_exec else "Email Listener Only"
                console.print(Panel(f"🚀 Memulai Mode: [bold]{mode}[/]", border_style="green"))
                start_listening(settings) # Fungsi ini sekarang handle Live display
                log.info("Kembali ke Menu Utama...") # Pesan setelah listener berhenti
                time.sleep(2)
            else:
                log.error("[bold red]--- TIDAK BISA MEMULAI ---[/]")
                log.warning(f"Silakan masuk ke menu '[bold cyan]2[/] Pengaturan' untuk memperbaiki.")
                Prompt.ask("\nTekan Enter untuk kembali ke menu...", default="") # Tunggu user

        elif choice == '2':
            show_settings(settings)
            settings = load_settings() # Load ulang jika ada perubahan
        elif choice == '3':
            console.clear()
            console.print(Panel("[bold cyan]👋 Sampai Jumpa! 👋[/]", border_style="cyan"))
            console.print(Text("Terima kasih telah menggunakan Exora AI Listener!", style="cyan"))
            sys.exit(0)


# --- Entry Point ---
if __name__ == "__main__":
    try:
        # console.clear() # Clear di awal main_menu
        main_menu()
    except KeyboardInterrupt:
        # Signal handler sudah menangani ini, tapi sebagai fallback
        # Pastikan console tidak dalam mode aneh
        console.show_cursor(True)
        console.print("\n[bold yellow]Program dihentikan paksa (Fallback).[/]")
        sys.exit(1)
    except Exception as e:
        console.clear()
        console.print(Panel("[bold red]💥 ERROR KRITIS TAK TERDUGA 💥[/]", border_style="red"))
        log.exception("Terjadi error fatal yang tidak tertangani:") # Log traceback dengan Rich
        console.print("\n[red]Program akan keluar.[/]")
        Prompt.ask("Tekan Enter untuk keluar...", default="")
        sys.exit(1)
