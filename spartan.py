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
import requests # Untuk handle error koneksi Binance

# --- Integrasi Library Tampilan ---
try:
    import inquirer
    from inquirer.themes import GreenPassion
    INQUIRER_AVAILABLE = True
except ImportError:
    INQUIRER_AVAILABLE = False

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.table import Table
    from rich.progress import SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn, Progress # Untuk status lebih keren
    from rich.live import Live # Untuk update status dinamis
    from rich import print as rprint # Gunakan print dari rich
    from rich.prompt import Prompt, Confirm # Alternatif input rich
    RICH_AVAILABLE = True
    console = Console() # Inisialisasi console Rich
except ImportError:
    RICH_AVAILABLE = False
    # Fallback print jika rich tidak ada
    def rprint(*args, **kwargs): print(*args)
    # Dummy classes/functions jika rich tidak ada
    class Console:
        def print(self, *args, **kwargs): print(*args)
        def rule(self, *args, **kwargs): print("-" * 40)
        def status(self, *args, **kwargs): return DummyStatus()
        def print_exception(self, *args, **kwargs): traceback.print_exc()
    class DummyStatus:
        def start(self): pass
        def stop(self): pass
        def update(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
    class Panel:
        def __init__(self, content, *args, **kwargs): self.content = content
        # Define how Panel should behave when printed without Rich
        def __str__(self): return f"--- Panel ---\n{self.content}\n-------------"
    class Text(str): pass # Simple fallback
    console = Console() # Gunakan dummy console

try:
    import pyfiglet
    FIGLET_AVAILABLE = True
except ImportError:
    FIGLET_AVAILABLE = False

try:
    import emoji
    EMOJI_AVAILABLE = True
    # Definisikan beberapa emoji
    ICON_EMAIL = emoji.emojize(":e-mail:")
    ICON_PASSWORD = emoji.emojize(":key:")
    ICON_SERVER = emoji.emojize(":satellite_antenna:")
    ICON_CLOCK = emoji.emojize(":alarm_clock:")
    ICON_TARGET = emoji.emojize(":dart:")
    ICON_TRIGGER = emoji.emojize(":bell:")
    ICON_BINANCE = emoji.emojize(":chart_increasing:")
    ICON_API = emoji.emojize(":locked_with_key:")
    ICON_PAIR = emoji.emojize(":currency_exchange:")
    ICON_QTY = emoji.emojize(":money_bag:")
    ICON_EXECUTE = emoji.emojize(":robot:")
    ICON_OK = emoji.emojize(":check_mark_button:")
    ICON_ERROR = emoji.emojize(":cross_mark:")
    ICON_WARN = emoji.emojize(":warning:")
    ICON_INFO = emoji.emojize(":information:")
    ICON_START = emoji.emojize(":rocket:")
    ICON_SETTINGS = emoji.emojize(":gear:")
    ICON_EXIT = emoji.emojize(":door:")
    ICON_LISTEN = emoji.emojize(":ear:")
    ICON_NETWORK = emoji.emojize(":globe_with_meridians:")
    ICON_PROCESS = emoji.emojize(":magnifying_glass_tilted_left:")
    ICON_MARK = emoji.emojize(":envelope_with_arrow:")
    ICON_BEEP = emoji.emojize(":speaker_high_volume:")

except ImportError:
    EMOJI_AVAILABLE = False
    # Fallback jika emoji tidak ada
    ICON_EMAIL, ICON_PASSWORD, ICON_SERVER, ICON_CLOCK, ICON_TARGET, ICON_TRIGGER = "📧", "🔑", "📡", "⏰", "🎯", "🔔"
    ICON_BINANCE, ICON_API, ICON_PAIR, ICON_QTY, ICON_EXECUTE = "📈", "🔐", "💱", "💰", "🤖"
    ICON_OK, ICON_ERROR, ICON_WARN, ICON_INFO = "✅", "❌", "⚠️", "ℹ️"
    ICON_START, ICON_SETTINGS, ICON_EXIT, ICON_LISTEN, ICON_NETWORK, ICON_PROCESS, ICON_MARK, ICON_BEEP = "🚀", "⚙️", "🚪", "👂", "🌐", "🔍", "📩", "🔊"


# --- Peringatan Library Opsional ---
if not INQUIRER_AVAILABLE:
    rprint(f"[bold yellow]{ICON_WARN} WARNING: Library 'inquirer' tidak ditemukan.[/bold yellow]")
    rprint("[yellow]          Menu akan menggunakan input teks biasa.[/yellow]")
    rprint("[yellow]          Install dengan: [cyan]pip install inquirer[/cyan][/yellow]\n")
    time.sleep(2)
if not RICH_AVAILABLE:
    rprint(f"{ICON_WARN} WARNING: Library 'rich' tidak ditemukan.")
    rprint("          Tampilan akan menjadi standar (kurang menarik).")
    rprint("          Install dengan: pip install rich\n")
    time.sleep(2)
if not FIGLET_AVAILABLE:
    rprint(f"{ICON_WARN} WARNING: Library 'pyfiglet' tidak ditemukan.")
    rprint("          Judul utama tidak akan ditampilkan dalam format ASCII art.")
    rprint("          Install dengan: pip install pyfiglet\n")
    time.sleep(2)
if not EMOJI_AVAILABLE:
    rprint(f"{ICON_WARN} WARNING: Library 'emoji' tidak ditemukan.")
    rprint("          Ikon emoji tidak akan ditampilkan.")
    rprint("          Install dengan: pip install emoji\n")
    time.sleep(2)

# --- Binance Integration (Kode sama, hanya print diganti rprint jika perlu) ---
try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException, BinanceOrderException
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False
    rprint(f"\n[bold red]!!! {ICON_ERROR} WARNING: Library 'python-binance' tidak ditemukan. !!![/bold red]")
    rprint("[yellow]!!!          Fitur eksekusi order Binance tidak akan berfungsi. !!![/yellow]")
    rprint(f"[yellow]!!!          Install dengan: [cyan]pip install python-binance[/cyan]         !!![/yellow]\n")
    class BinanceAPIException(Exception): pass
    class BinanceOrderException(Exception): pass
    class Client:
        SIDE_BUY = 'BUY'
        SIDE_SELL = 'SELL'
        ORDER_TYPE_MARKET = 'MARKET'

# --- Konfigurasi & Variabel Global ---
CONFIG_FILE = "config.json"
DEFAULT_SETTINGS = {
    "email_address": "", "app_password": "", "imap_server": "imap.gmail.com",
    "check_interval_seconds": 10, "target_keyword": "Exora AI", "trigger_keyword": "order",
    "binance_api_key": "", "binance_api_secret": "", "trading_pair": "BTCUSDT",
    "buy_quote_quantity": 11.0, "sell_base_quantity": 0.0, "execute_binance_orders": False
}
running = True

# --- Kode Warna ANSI (Kurang relevan jika pakai Rich, tapi bisa sebagai fallback) ---
RESET = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"
RED = "\033[91m"; GREEN = "\033[92m"; YELLOW = "\033[93m"
BLUE = "\033[94m"; MAGENTA = "\033[95m"; CYAN = "\033[96m"

# --- Fungsi Penanganan Sinyal (Ctrl+C) ---
def signal_handler(sig, frame):
    global running
    running = False # Set flag untuk menghentikan loop
    console.print(f"\n[bold yellow]{ICON_WARN} Ctrl+C terdeteksi. Menghentikan proses...[/bold yellow]",)
    # Tambahkan sedikit jeda agar loop utama bisa merespon flag 'running'
    time.sleep(1.5)
    console.print(f"[bold red]{ICON_EXIT} Keluar dari program.[/bold red]")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# --- Fungsi Konfigurasi (load/save - logic sama, print diganti rprint) ---
def load_settings():
    settings = DEFAULT_SETTINGS.copy()
    config_exists = os.path.exists(CONFIG_FILE)
    if config_exists:
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_settings = json.load(f)
            valid_keys = set(DEFAULT_SETTINGS.keys())
            filtered_settings = {k: v for k, v in loaded_settings.items() if k in valid_keys}
            settings.update(filtered_settings)

            # Validasi (pesan menggunakan rprint)
            corrections_made = False
            if settings.get("check_interval_seconds", 10) < 5:
                rprint(f"[yellow]{ICON_WARN} Interval cek di '{CONFIG_FILE}' < 5 detik, direset ke 10.[/yellow]")
                settings["check_interval_seconds"] = 10
                corrections_made = True
            # ... (validasi lain tetap sama, gunakan rprint untuk warning) ...
            if not isinstance(settings.get("buy_quote_quantity"), (int, float)) or settings.get("buy_quote_quantity") <= 0:
                 rprint(f"[yellow]{ICON_WARN} 'buy_quote_quantity' tidak valid, direset ke {DEFAULT_SETTINGS['buy_quote_quantity']}.[/yellow]")
                 settings["buy_quote_quantity"] = DEFAULT_SETTINGS['buy_quote_quantity']
                 corrections_made = True
            if not isinstance(settings.get("sell_base_quantity"), (int, float)) or settings.get("sell_base_quantity") < 0: # Allow 0
                 rprint(f"[yellow]{ICON_WARN} 'sell_base_quantity' tidak valid, direset ke {DEFAULT_SETTINGS['sell_base_quantity']}.[/yellow]")
                 settings["sell_base_quantity"] = DEFAULT_SETTINGS['sell_base_quantity']
                 corrections_made = True
            if not isinstance(settings.get("execute_binance_orders"), bool):
                rprint(f"[yellow]{ICON_WARN} 'execute_binance_orders' tidak valid, direset ke False.[/yellow]")
                settings["execute_binance_orders"] = False
                corrections_made = True

            # Save back jika ada koreksi atau jika ada kunci default baru
            if corrections_made or len(settings) != len(filtered_settings):
                 save_settings(settings, silent_success=True) # Jangan print sukses saat load awal

        except json.JSONDecodeError:
            rprint(f"[bold red]{ICON_ERROR} File konfigurasi '{CONFIG_FILE}' rusak. Menggunakan default & menyimpan ulang.[/bold red]")
            save_settings(settings)
        except Exception as e:
            rprint(f"[bold red]{ICON_ERROR} Gagal memuat konfigurasi: {e}[/bold red]")
            console.print_exception(show_locals=False) # Tampilkan traceback dgn Rich
    else:
        rprint(f"[yellow]{ICON_INFO} File konfigurasi '{CONFIG_FILE}' tidak ditemukan. Membuat dengan nilai default.[/yellow]")
        save_settings(settings)
    return settings

def save_settings(settings, silent_success=False):
    """Menyimpan pengaturan ke file JSON."""
    try:
        # Pastikan tipe data benar sebelum menyimpan (logic sama)
        settings['check_interval_seconds'] = int(settings.get('check_interval_seconds', DEFAULT_SETTINGS['check_interval_seconds']))
        settings['buy_quote_quantity'] = float(settings.get('buy_quote_quantity', DEFAULT_SETTINGS['buy_quote_quantity']))
        settings['sell_base_quantity'] = float(settings.get('sell_base_quantity', DEFAULT_SETTINGS['sell_base_quantity']))
        settings['execute_binance_orders'] = bool(settings.get('execute_binance_orders', DEFAULT_SETTINGS['execute_binance_orders']))

        settings_to_save = {k: settings.get(k, DEFAULT_SETTINGS[k]) for k in DEFAULT_SETTINGS}
        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings_to_save, f, indent=4, sort_keys=True)
        if not silent_success:
            rprint(Panel(f"[bold green]{ICON_OK} Pengaturan berhasil disimpan ke '{CONFIG_FILE}'[/bold green]",
                         title="Simpan Sukses", border_style="green"))
    except Exception as e:
        rprint(f"[bold red]{ICON_ERROR} Gagal menyimpan konfigurasi: {e}[/bold red]")
        console.print_exception(show_locals=False)

# --- Fungsi Utilitas ---
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

# decode_mime_words & get_text_from_email (logic sama, print diganti rprint)
def decode_mime_words(s):
    if not s: return ""
    try:
        decoded_parts = decode_header(s)
        result = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(encoding or 'utf-8', errors='replace'))
            else:
                result.append(str(part))
        return "".join(result)
    except Exception as e:
        rprint(f"[yellow]{ICON_WARN} Gagal mendekode header: {e}. Header asli: {s}[/yellow]")
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
                    rprint(f"[yellow]{ICON_WARN} Tidak bisa mendekode bagian email (charset: {part.get_content_charset()}): {e}[/yellow]")
    else:
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                if payload: text_content = payload.decode(charset, errors='replace')
            except Exception as e:
                 rprint(f"[yellow]{ICON_WARN} Tidak bisa mendekode body email (charset: {msg.get_content_charset()}): {e}[/yellow]")
    return " ".join(text_content.split()).lower()

# --- Fungsi Beep (print diganti rprint) ---
def trigger_beep(action):
    try:
        if action == "buy":
            rprint(f"[bold magenta]{ICON_BEEP} BEEP untuk [white]BUY[/white]![/bold magenta]")
            subprocess.run(["beep", "-f", "1000", "-l", "300"], check=True, capture_output=True, text=True)
            time.sleep(0.1)
            subprocess.run(["beep", "-f", "1200", "-l", "200"], check=True, capture_output=True, text=True)
        elif action == "sell":
            rprint(f"[bold magenta]{ICON_BEEP} BEEP untuk [white]SELL[/white]![/bold magenta]")
            subprocess.run(["beep", "-f", "700", "-l", "500"], check=True, capture_output=True, text=True)
        else:
             rprint(f"[yellow]{ICON_WARN} Aksi beep tidak dikenal '{action}'.[/yellow]")
    except FileNotFoundError:
        rprint(f"[yellow]{ICON_WARN} Perintah 'beep' tidak ditemukan. Beep dilewati.[/yellow]")
        rprint(f"[dim]         (Untuk Linux, install 'beep': sudo apt install beep / sudo yum install beep)[/dim]")
    except subprocess.CalledProcessError as e:
        rprint(f"[red]{ICON_ERROR} Gagal menjalankan 'beep': {e}[/red]")
        if e.stderr: rprint(f"[red]         Stderr: {e.stderr.strip()}[/red]")
    except Exception as e:
        rprint(f"[red]{ICON_ERROR} Kesalahan tak terduga saat beep: {e}[/red]")

# --- Fungsi Eksekusi Binance (print diganti rprint, gunakan panel/style) ---
def get_binance_client(settings):
    if not BINANCE_AVAILABLE:
        rprint(f"[red]{ICON_ERROR} Library python-binance tidak terinstall.[/red]")
        return None
    api_key = settings.get('binance_api_key')
    api_secret = settings.get('binance_api_secret')
    if not api_key or not api_secret:
        rprint(f"[red]{ICON_ERROR} API Key atau Secret Key Binance belum diatur.[/red]")
        return None
    try:
        rprint(f"[cyan]{ICON_NETWORK} Menghubungkan ke Binance API...[/cyan]")
        # Set timeouts untuk koneksi dan baca
        client = Client(api_key, api_secret, requests_params={'timeout': 15})
        client.ping()
        # account_info = client.get_account(recvWindow=10000) # Perpanjang recvWindow jika perlu
        rprint(f"[bold green]{ICON_OK} Koneksi & Autentikasi Binance API Berhasil.[/bold green]")
        # rprint(f"[dim]         (Tipe Akun: {account_info.get('accountType')})[/dim]")
        return client
    except (BinanceAPIException, BinanceOrderException) as e:
        rprint(f"[bold red]{ICON_ERROR} Gagal koneksi/autentikasi Binance: Status={e.status_code}, Kode={e.code}, Pesan='{e.message}'[/bold red]")
        if "timestamp" in str(e.message).lower():
             rprint(f"[yellow]         -> Periksa apakah waktu sistem Anda sinkron.{ICON_CLOCK}[/yellow]")
        if "signature" in str(e.message).lower() or "invalid key" in str(e.message).lower():
             rprint(f"[yellow]         -> Periksa kembali API Key dan Secret Key Anda.{ICON_API}[/yellow]")
        return None
    except requests.exceptions.Timeout:
        rprint(f"[bold red]{ICON_ERROR} Koneksi ke Binance API timeout.[/bold red]")
        rprint(f"[yellow]         -> Periksa koneksi internet atau coba tingkatkan timeout.{ICON_NETWORK}[/yellow]")
        return None
    except requests.exceptions.RequestException as e:
        rprint(f"[bold red]{ICON_ERROR} Gagal menghubungi Binance API: {e}{ICON_NETWORK}[/bold red]")
        return None
    except Exception as e:
        rprint(f"[bold red]{ICON_ERROR} Gagal membuat Binance client:{e}[/bold red]")
        console.print_exception(show_locals=False)
        return None

def execute_binance_order(client, settings, side):
    if not client:
        rprint(f"[red]{ICON_ERROR} Eksekusi Binance dibatalkan, client tidak valid.[/red]")
        return False
    if not settings.get("execute_binance_orders", False):
        rprint(f"[yellow]{ICON_WARN} Eksekusi order dinonaktifkan. Order dilewati.[/yellow]")
        return False # Safety net

    pair = settings.get('trading_pair', '').upper()
    if not pair:
        rprint(f"[red]{ICON_ERROR} Trading pair belum diatur.{ICON_PAIR}[/red]")
        return False

    order_details = {}
    action_desc = ""
    side_color = "green" if side == Client.SIDE_BUY else "red"
    side_icon = ICON_BINANCE

    try:
        if side == Client.SIDE_BUY:
            quote_qty = settings.get('buy_quote_quantity', 0.0)
            if quote_qty <= 0:
                 rprint(f"[red]{ICON_ERROR} Kuantitas Beli (buy_quote_quantity) harus > 0.{ICON_QTY}[/red]")
                 return False
            order_details = {'symbol': pair, 'side': Client.SIDE_BUY, 'type': Client.ORDER_TYPE_MARKET, 'quoteOrderQty': quote_qty}
            action_desc = f"MARKET BUY {quote_qty} (quote) {pair}"
        elif side == Client.SIDE_SELL:
            base_qty = settings.get('sell_base_quantity', 0.0)
            if base_qty <= 0:
                 rprint(f"[yellow]{ICON_INFO} Kuantitas Jual (sell_base_quantity) = 0. Order SELL tidak dieksekusi.{ICON_QTY}[/yellow]")
                 return False
            order_details = {'symbol': pair, 'side': Client.SIDE_SELL, 'type': Client.ORDER_TYPE_MARKET, 'quantity': base_qty}
            action_desc = f"MARKET SELL {base_qty} (base) {pair}"
        else:
            rprint(f"[red]{ICON_ERROR} Sisi order tidak valid: {side}[/red]")
            return False

        rprint(Panel(f"Mencoba eksekusi: [bold {side_color}]{action_desc}[/bold {side_color}]...",
                     title=f"{side_icon} Eksekusi Binance", border_style="magenta"))

        # Simulasi jika perlu (DEBUG)
        # rprint(f"[yellow][DEBUG] Simulasi order: {order_details}[/yellow]")
        # time.sleep(1)
        # return True

        order_result = client.create_order(**order_details)

        # Tampilkan hasil dengan tabel Rich
        result_table = Table(title=f"{ICON_OK} Order Berhasil Dieksekusi!", show_header=False, box=None, padding=(0, 1))
        result_table.add_column(style="dim cyan")
        result_table.add_column()
        result_table.add_row("Order ID", str(order_result.get('orderId')))
        result_table.add_row("Symbol", order_result.get('symbol'))
        result_table.add_row("Side", order_result.get('side'))
        result_table.add_row("Status", order_result.get('status'))

        if order_result.get('fills') and len(order_result.get('fills')) > 0:
            total_qty = sum(float(f['qty']) for f in order_result['fills'])
            total_quote_qty = sum(float(f['cummulativeQuoteQty']) for f in order_result['fills'])
            avg_price = total_quote_qty / total_qty if total_qty else 0
            result_table.add_row("Avg Price", f"{avg_price:.8f}")
            result_table.add_row("Filled Qty", f"{total_qty:.8f} (Base) / {total_quote_qty:.4f} (Quote)")
        elif order_result.get('cummulativeQuoteQty'):
             result_table.add_row("Total Cost/Proceeds", f"{float(order_result['cummulativeQuoteQty']):.4f} (Quote)")

        rprint(Panel(result_table, border_style="green"))
        return True

    except (BinanceAPIException, BinanceOrderException) as e:
        error_panel_content = Text()
        error_panel_content.append(f"Gagal eksekusi order: Status={e.status_code}, Kode={e.code}\n", style="bold red")
        error_panel_content.append(f"Pesan: '{e.message}'", style="red")
        if e.code == -2010: error_panel_content.append(f"\n[yellow]   -> Kemungkinan saldo tidak cukup.{ICON_QTY}[/yellow]")
        elif e.code == -1121: error_panel_content.append(f"\n[yellow]   -> Trading pair '{pair}' tidak valid.{ICON_PAIR}[/yellow]")
        elif e.code == -1013 or 'MIN_NOTIONAL' in str(e.message): error_panel_content.append(f"\n[yellow]   -> Order size terlalu kecil (cek MIN_NOTIONAL).{ICON_QTY}[/yellow]")
        elif e.code == -1111: error_panel_content.append(f"\n[yellow]   -> Kuantitas order tidak sesuai LOT_SIZE.{ICON_QTY}[/yellow]")
        rprint(Panel(error_panel_content, title=f"{ICON_ERROR} Binance API/Order Error", border_style="red"))
        return False
    except requests.exceptions.RequestException as e:
        rprint(Panel(f"Gagal mengirim order ke Binance: {e}\nPeriksa koneksi internet.", title=f"{ICON_ERROR} Network Error", border_style="red"))
        return False
    except Exception as e:
        rprint(Panel(f"Kesalahan tak terduga saat eksekusi order Binance:\n{e}", title=f"{ICON_ERROR} Error", border_style="red"))
        console.print_exception(show_locals=False)
        return False

# --- Fungsi Pemrosesan Email (print diganti rprint, gunakan panel/style) ---
def process_email(mail, email_id, settings, binance_client):
    global running
    if not running: return

    target_keyword_lower = settings['target_keyword'].lower()
    trigger_keyword_lower = settings['trigger_keyword'].lower()
    email_id_str = email_id.decode('utf-8')

    try:
        # rprint(f"[dim]Fetching email ID {email_id_str}...[/dim]")
        status, data = mail.fetch(email_id, "(RFC822)")
        if status != 'OK':
            rprint(f"[red]{ICON_ERROR} Gagal mengambil email ID {email_id_str}: {status}[/red]")
            return

        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        subject = decode_mime_words(msg["Subject"])
        sender = decode_mime_words(msg["From"])
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Tampilkan detail email dalam panel
        email_details = Table(show_header=False, box=None, padding=(0,1))
        email_details.add_column(style="dim cyan")
        email_details.add_column(style="white")
        email_details.add_row("ID", email_id_str)
        email_details.add_row("Dari", sender)
        email_details.add_row("Subjek", subject)

        rprint(Panel(email_details, title=f"{ICON_EMAIL} Email Ditemukan ({timestamp})", border_style="cyan", expand=False))

        body = get_text_from_email(msg)
        full_content = (subject.lower() + " " + body)
        # rprint(f"[dim]Content: {full_content[:150]}...[/dim]") # Debug

        if target_keyword_lower in full_content:
            rprint(f"[green]{ICON_TARGET} Keyword target '{settings['target_keyword']}' ditemukan.[/green]")
            try:
                target_index = full_content.find(target_keyword_lower)
                trigger_index = full_content.find(trigger_keyword_lower, target_index + len(target_keyword_lower))

                if trigger_index != -1:
                    start_word_index = trigger_index + len(trigger_keyword_lower)
                    text_after_trigger = full_content[start_word_index:].lstrip()
                    words_after_trigger = text_after_trigger.split(maxsplit=1)

                    if words_after_trigger:
                        action_word = words_after_trigger[0].strip('.,!?:;()[]{}').lower()
                        rprint(f"[green]{ICON_TRIGGER} Keyword trigger '{settings['trigger_keyword']}' ditemukan. Kata aksi: [bold white]'{action_word}'[/bold white][/green]")

                        # --- Trigger Aksi ---
                        order_attempted = False
                        execute_binance = settings.get("execute_binance_orders", False)
                        action_color = "white"
                        action_icon = ""

                        if action_word == "buy":
                            trigger_beep("buy")
                            action_color = "green"
                            action_icon = ICON_BINANCE
                            if execute_binance:
                                if binance_client:
                                    order_attempted = execute_binance_order(binance_client, settings, Client.SIDE_BUY)
                                else:
                                    rprint(f"[yellow]{ICON_WARN} Eksekusi Binance aktif tapi client tidak valid/tersedia.{ICON_NETWORK}[/yellow]")
                        elif action_word == "sell":
                            trigger_beep("sell")
                            action_color = "red"
                            action_icon = ICON_BINANCE
                            can_sell = settings.get('sell_base_quantity', 0.0) > 0
                            if execute_binance:
                                if can_sell:
                                    if binance_client:
                                        order_attempted = execute_binance_order(binance_client, settings, Client.SIDE_SELL)
                                    else:
                                        rprint(f"[yellow]{ICON_WARN} Eksekusi Binance aktif tapi client tidak valid/tersedia.{ICON_NETWORK}[/yellow]")
                                elif settings.get('sell_base_quantity') <= 0:
                                    rprint(f"[yellow]{ICON_INFO} Aksi 'sell' terdeteksi, tapi 'sell_base_quantity' = 0. Order tidak dieksekusi.[/yellow]")
                        else:
                            rprint(f"[blue]{ICON_INFO} Kata aksi '{action_word}' bukan 'buy'/'sell'. Tidak ada aksi market.[/blue]")

                        # Pesan jika eksekusi aktif tapi gagal karena client
                        if execute_binance and action_word in ["buy", "sell"] and not order_attempted and not (action_word == "sell" and settings.get('sell_base_quantity', 0.0) <= 0) and binance_client is None:
                             rprint(f"[yellow]{ICON_WARN} Eksekusi tidak dilakukan (Client Binance tidak tersedia).[/yellow]")

                    else:
                        rprint(f"[yellow]{ICON_WARN} Trigger '{settings['trigger_keyword']}' ditemukan, tapi tidak ada kata setelahnya.[/yellow]")
                else:
                     rprint(f"[yellow]{ICON_WARN} Target ditemukan, tapi trigger '{settings['trigger_keyword']}' tidak ditemukan [bold]setelahnya[/bold].[/yellow]")

            except Exception as e:
                 rprint(f"[red]{ICON_ERROR} Gagal parsing kata setelah trigger: {e}[/red]")
                 console.print_exception(show_locals=False)
        else:
            rprint(f"[blue]{ICON_INFO} Keyword target '{settings['target_keyword']}' tidak ditemukan.[/blue]")

        # Tandai email sebagai sudah dibaca
        try:
            # rprint(f"[dim]Menandai email {email_id_str} sebagai Seen...[/dim]")
            mail.store(email_id, '+FLAGS', '\\Seen')
            rprint(f"[dim cyan]{ICON_MARK} Email {email_id_str} ditandai sudah dibaca.[/dim cyan]")
        except Exception as e:
            rprint(f"[red]{ICON_ERROR} Gagal menandai email {email_id_str} sebagai 'Seen': {e}[/red]")
        # console.rule(style="dim cyan") # Garis pemisah antar email

    except Exception as e:
        rprint(Panel(f"Gagal memproses email ID {email_id_str}:\n{e}", title=f"{ICON_ERROR} Error Proses Email", border_style="red"))
        console.print_exception(show_locals=False)

# --- Fungsi Listening Utama (Gunakan Rich Status/Live) ---
def start_listening(settings):
    global running
    running = True
    mail = None
    binance_client = None
    last_check_time = 0
    consecutive_errors = 0
    max_consecutive_errors = 5
    long_wait_time = 60
    initial_wait_time = 5 # Naikkan sedikit wait time awal
    wait_time = initial_wait_time
    last_ping_time = 0 # Waktu ping terakhir ke binance
    ping_interval = max(60, settings['check_interval_seconds'] * 5) # Interval ping binance

    # --- Setup Binance Client ---
    execute_binance = settings.get("execute_binance_orders", False)
    if execute_binance:
        if not BINANCE_AVAILABLE:
             rprint(Panel(f"[bold red]{ICON_ERROR} Eksekusi Binance aktif tapi library [cyan]python-binance[/cyan] tidak ada![/bold red]\n"
                           "[yellow]Nonaktifkan eksekusi di Pengaturan atau install library.[/yellow]",
                           title="Error Kritis", border_style="red", expand=False))
             running = False; return
        console.rule("[bold cyan]Inisialisasi Binance Client[/bold cyan]", style="cyan")
        binance_client = get_binance_client(settings)
        if not binance_client:
            rprint(Panel(f"[bold red]{ICON_ERROR} Gagal menginisialisasi Binance Client.[/bold red]\n"
                           "[yellow]Periksa API Key/Secret, koneksi, dan waktu sistem.[/yellow]\n"
                           "[yellow]Eksekusi order [bold]tidak[/bold] akan berfungsi. Program lanjut untuk email saja.[/yellow]",
                           title="Error Koneksi Binance", border_style="red", expand=False))
        else:
            rprint(f"[bold green]{ICON_OK} Binance Client Siap.[/bold green]")
        console.rule(style="cyan")
    else:
        rprint(Panel(f"[yellow]{ICON_INFO} Eksekusi order Binance [bold]Nonaktif[/bold]. Hanya notifikasi email & beep.[/yellow]",
                     title="Mode Operasi", border_style="yellow", expand=False))

    # --- Loop Utama dengan Rich Live/Status ---
    status_text = Text(f"{ICON_LISTEN} Menunggu email...", style="blue")
    spinner = SpinnerColumn(spinner_name="dots", style="blue")
    status_columns = [spinner, TextColumn("[blue]{task.description}")]

    with Live(Panel(status_text, title="Status", border_style="blue"), console=console, refresh_per_second=4, transient=True) as live:
        while running:
            try:
                # --- Koneksi IMAP ---
                if not mail or mail.state != 'SELECTED':
                    live.update(Panel(Text(f"{ICON_NETWORK} Menghubungkan ke IMAP {settings['imap_server']}...", style="cyan"), title="Status", border_style="cyan"), refresh=True)
                    time.sleep(0.5) # Jeda singkat sebelum konek
                    try:
                        mail = imaplib.IMAP4_SSL(settings['imap_server'], timeout=30)
                        live.update(Panel(Text(f"{ICON_EMAIL} Login sebagai {settings['email_address']}...", style="cyan"), title="Status", border_style="cyan"), refresh=True)
                        rv, desc = mail.login(settings['email_address'], settings['app_password'])
                        if rv != 'OK': raise imaplib.IMAP4.error(f"Login failed: {desc}")
                        mail.select("inbox")
                        live.console.print(f"[bold green]{ICON_OK} Login & Koneksi IMAP Berhasil.[/bold green]")
                        live.console.print(Panel(f"[bold green]{ICON_LISTEN} Mode Mendengarkan Aktif[/bold green]\n[dim]Tekan Ctrl+C untuk berhenti[/dim]",
                                               title="Listener Ready", border_style="green", expand=False))
                        live.update(Panel(status_text, title="Status", border_style="blue"), refresh=True) # Kembali ke status tunggu
                        consecutive_errors = 0
                        wait_time = initial_wait_time
                        last_check_time = time.time() # Mulai cek segera setelah konek
                    except (imaplib.IMAP4.error, OSError, socket.error, socket.gaierror, TimeoutError) as login_err:
                         live.console.print(f"[bold red]{ICON_ERROR} GAGAL KONEKSI/LOGIN EMAIL![/bold red]")
                         live.console.print(f"[red]   Pesan: {login_err}[/red]")
                         live.console.print(f"[yellow]   Periksa Email, App Password, Server IMAP, Izin Akses, dan Koneksi Internet.{ICON_NETWORK}[/yellow]")
                         if "authentication failed" in str(login_err).lower():
                             running = False # Berhenti jika otentikasi gagal
                         else: # Jika error koneksi
                             consecutive_errors += 1
                             sleep_time = wait_time if consecutive_errors < max_consecutive_errors else long_wait_time
                             live.update(Panel(Text(f"{ICON_ERROR} Gagal konek. Mencoba lagi dalam {sleep_time}d...", style="red"), title="Status", border_style="red"), refresh=True)
                             time.sleep(sleep_time)
                             wait_time = min(wait_time * 2, 30) if consecutive_errors < max_consecutive_errors else wait_time
                         mail = None # Pastikan reconnect dicoba
                         continue # Lanjut ke iterasi berikutnya

                # --- Loop Inner (Cek Email & Koneksi) ---
                current_time = time.time()
                if current_time - last_check_time >= settings['check_interval_seconds']:
                    live.update(Panel(Text(f"{ICON_LISTEN} Memeriksa email baru...", style="blue"), title="Status", border_style="blue"), refresh=True)
                    # NOOP Check
                    try:
                        # rprint("[dim]NOOP Check...[/dim]", end='\r')
                        status, _ = mail.noop()
                        if status != 'OK': raise imaplib.IMAP4.abort("NOOP failed")
                        # rprint(" " * 20, end='\r')
                    except (imaplib.IMAP4.abort, imaplib.IMAP4.readonly, BrokenPipeError, OSError) as noop_err:
                         live.console.print(f"\n[yellow]{ICON_WARN} Koneksi IMAP terputus ({type(noop_err).__name__}). Reconnecting...[/yellow]")
                         try: mail.logout()
                         except Exception: pass
                         mail = None
                         time.sleep(initial_wait_time) # Jeda sebelum reconnect
                         continue # Kembali ke loop luar untuk reconnect

                    # Ping Binance Check (lebih jarang)
                    if binance_client and current_time - last_ping_time > ping_interval:
                        live.update(Panel(Text(f"{ICON_NETWORK} Ping Binance API...", style="cyan"), title="Status", border_style="cyan"), refresh=True)
                        try:
                             binance_client.ping()
                             last_ping_time = current_time
                             live.update(Panel(status_text, title="Status", border_style="blue"), refresh=True) # Kembali ke status tunggu
                        except Exception as ping_err:
                             live.console.print(f"\n[yellow]{ICON_WARN} Ping Binance API gagal ({ping_err}). Mencoba re-init client...{ICON_NETWORK}[/yellow]")
                             binance_client = get_binance_client(settings) # Coba buat ulang
                             if binance_client:
                                 live.console.print(f"[green]{ICON_OK} Binance client berhasil di-init ulang.[/green]")
                                 last_ping_time = current_time
                             else:
                                 live.console.print(f"[red]{ICON_ERROR} Gagal re-init Binance client.[/red]")
                                 last_ping_time = 0 # Coba lagi nanti
                             time.sleep(5)
                             live.update(Panel(status_text, title="Status", border_style="blue"), refresh=True) # Kembali ke status tunggu

                    # Cek Email UNSEEN
                    status, messages = mail.search(None, '(UNSEEN)')
                    if status != 'OK':
                         live.console.print(f"\n[red]{ICON_ERROR} Gagal mencari email UNSEEN: {status}. Reconnecting...[/red]")
                         try: mail.close()
                         except Exception: pass
                         mail = None
                         time.sleep(initial_wait_time)
                         continue

                    email_ids = messages[0].split()
                    if email_ids:
                        num_emails = len(email_ids)
                        live.console.print(f"\n[bold green]{ICON_PROCESS} Menemukan {num_emails} email baru! Memproses...[/bold green]")
                        console.rule(style="dim green")
                        for i, email_id in enumerate(email_ids):
                            if not running: break
                            live.console.print(f"[dim]--- Memproses email {i+1}/{num_emails} ---[/dim]")
                            process_email(mail, email_id, settings, binance_client)
                            console.rule(style="dim green") # Pemisah antar email
                        if not running: break
                        live.console.print(f"[bold green]{ICON_OK} Selesai memproses. Kembali mendengarkan...[/bold green]")
                    else:
                        # Tidak ada email baru, update status tunggu
                        dots = "." * (int(time.time()*2) % 4)
                        status_text = Text(f"{ICON_LISTEN} Menunggu email {dots}", style="blue")
                        live.update(Panel(status_text, title="Status", border_style="blue"), refresh=True)


                    last_check_time = current_time # Update waktu cek terakhir
                else:
                    # Jika belum waktunya cek, tidur sebentar
                    time.sleep(0.5)


            except (imaplib.IMAP4.error, imaplib.IMAP4.abort, BrokenPipeError, OSError) as e:
                live.console.print(f"\n[bold red]{ICON_ERROR} Kesalahan IMAP/Koneksi: {e}[/bold red]")
                consecutive_errors += 1
                sleep_time = wait_time if consecutive_errors < max_consecutive_errors else long_wait_time
                live.update(Panel(Text(f"{ICON_ERROR} Error ({consecutive_errors}). Reconnecting dalam {sleep_time}d...", style="red"), title="Status", border_style="red"), refresh=True)
                time.sleep(sleep_time)
                wait_time = min(wait_time * 2, 30) if consecutive_errors < max_consecutive_errors else wait_time
                mail = None # Force reconnect
            except (socket.error, socket.gaierror) as e:
                live.console.print(f"\n[bold red]{ICON_ERROR} Kesalahan Jaringan: {e}[/bold red]")
                consecutive_errors += 1
                sleep_time = wait_time if consecutive_errors < max_consecutive_errors else long_wait_time
                live.update(Panel(Text(f"{ICON_ERROR} Error Jaringan ({consecutive_errors}). Retry dalam {sleep_time}d...", style="red"), title="Status", border_style="red"), refresh=True)
                time.sleep(sleep_time)
                wait_time = min(wait_time * 2, 45) if consecutive_errors < max_consecutive_errors else wait_time
                mail = None # Force reconnect
            except Exception as e:
                live.console.print(f"\n[bold red]{ICON_ERROR} Kesalahan Tak Terduga di Loop Utama:[/bold red]")
                console.print_exception(show_locals=False)
                consecutive_errors += 1
                sleep_time = wait_time if consecutive_errors < max_consecutive_errors + 2 else long_wait_time * 2
                live.update(Panel(Text(f"{ICON_ERROR} Error Tak Terduga ({consecutive_errors}). Retry dalam {sleep_time}d...", style="red"), title="Status", border_style="red"), refresh=True)
                time.sleep(sleep_time)
                wait_time = min(wait_time * 2, 60) if consecutive_errors < max_consecutive_errors + 2 else wait_time
                if consecutive_errors >= max_consecutive_errors + 3:
                     live.console.print(f"[bold red]{ICON_ERROR} Terlalu banyak error beruntun. Berhenti.[/bold red]")
                     running = False
                mail = None # Coba reconnect setelah error tak terduga

            finally:
                # Pastikan logout jika mail object ada & state valid
                if mail and mail.state != 'LOGOUT':
                    try: mail.logout()
                    except Exception: pass
                # Set mail ke None jika terjadi error yang butuh reconnect
                if mail and not running: # Jika berhenti normal, pastikan mail = None
                    mail = None

            if running: time.sleep(0.1) # Jeda singkat antar iterasi loop utama

    # Keluar dari loop
    rprint(f"\n[bold yellow]{ICON_INFO} Mode mendengarkan dihentikan.[/bold yellow]")


# --- Fungsi Menu Pengaturan (MODIFIED with Rich) ---
def show_settings(settings):
    while True:
        clear_screen()
        console.rule(f"[bold cyan]{ICON_SETTINGS} Pengaturan Email & Binance Listener[/bold cyan]", style="cyan")

        # --- Tampilkan Pengaturan dengan Tabel Rich ---
        settings_table = Table(title="Konfigurasi Saat Ini", show_header=True, header_style="bold magenta",
                               box=None, padding=(0, 1, 0, 0)) # Atas, Kanan, Bawah, Kiri
        settings_table.add_column("Kategori", style="dim cyan", width=10)
        settings_table.add_column("Item", style="cyan", width=18)
        settings_table.add_column("Nilai", style="white")

        # Email Settings
        settings_table.add_row("Email", f"{ICON_EMAIL} Alamat Email", settings['email_address'] or "[italic red]Kosong[/italic red]")
        app_pass_display = f"*{'*' * (len(settings['app_password']) - 1)}" if len(settings['app_password']) > 1 else ('***' if settings['app_password'] else "[italic red]Kosong[/italic red]")
        settings_table.add_row("", f"{ICON_PASSWORD} App Password", app_pass_display)
        settings_table.add_row("", f"{ICON_SERVER} Server IMAP", settings['imap_server'])
        settings_table.add_row("", f"{ICON_CLOCK} Interval Cek", f"{settings['check_interval_seconds']} detik")
        settings_table.add_row("", f"{ICON_TARGET} Keyword Target", f"'{settings['target_keyword']}'")
        settings_table.add_row("", f"{ICON_TRIGGER} Keyword Trigger", f"'{settings['trigger_keyword']}'")

        settings_table.add_section() # Pemisah

        # Binance Settings
        lib_status = f"[green]Terinstall {ICON_OK}[/green]" if BINANCE_AVAILABLE else f"[red]Tidak Tersedia {ICON_ERROR}[/red]"
        settings_table.add_row("Binance", "Library Status", lib_status)
        if BINANCE_AVAILABLE:
            api_key_display = f"{settings['binance_api_key'][:4]}...{settings['binance_api_key'][-4:]}" if len(settings['binance_api_key']) > 8 else ('[green]OK[/green]' if settings['binance_api_key'] else '[italic red]Kosong[/italic red]')
            api_secret_display = f"{settings['binance_api_secret'][:4]}...{settings['binance_api_secret'][-4:]}" if len(settings['binance_api_secret']) > 8 else ('[green]OK[/green]' if settings['binance_api_secret'] else '[italic red]Kosong[/italic red]')
            settings_table.add_row("", f"{ICON_API} API Key", api_key_display)
            settings_table.add_row("", f"{ICON_API} API Secret", api_secret_display)
            settings_table.add_row("", f"{ICON_PAIR} Trading Pair", settings['trading_pair'] or "[italic red]Kosong[/italic red]")
            settings_table.add_row("", f"{ICON_QTY} Buy Quote Qty", f"{settings['buy_quote_quantity']} (USDT/dll)")
            sell_qty_disp = f"{settings['sell_base_quantity']} (BTC/dll)" + (" [dim](Sell Nonaktif)[/dim]" if settings['sell_base_quantity'] == 0 else "")
            settings_table.add_row("", f"{ICON_QTY} Sell Base Qty", sell_qty_disp)
            exec_status = f"[bold green]Aktif {ICON_OK}[/bold green]" if settings['execute_binance_orders'] else f"[bold red]Nonaktif {ICON_ERROR}[/bold red]"
            settings_table.add_row("", f"{ICON_EXECUTE} Eksekusi Order", exec_status)
        else:
             settings_table.add_row("", "[dim](Pengaturan Binance tidak relevan)[/dim]", "")

        rprint(Panel(settings_table, border_style="blue", expand=False))
        console.rule(style="blue")

        # --- Opsi Menu Pengaturan ---
        if INQUIRER_AVAILABLE:
            questions = [inquirer.List('action', message=f"{ICON_SETTINGS} Pilih aksi",
                                       choices=[('Edit Pengaturan', 'edit'), ('Kembali ke Menu Utama', 'back')], carousel=True)]
            try: answers = inquirer.prompt(questions, theme=GreenPassion()); choice = answers['action'] if answers else 'back'
            except KeyboardInterrupt: rprint(f"\n[yellow]{ICON_WARN} Edit dibatalkan.[/yellow]"); choice = 'back'; time.sleep(1)
            except Exception as e: rprint(f"[red]{ICON_ERROR} Error menu: {e}[/red]"); choice = 'back'
        else: # Fallback input teks
            choice_input = Prompt.ask("[bold yellow]Pilih opsi (E=Edit, K=Kembali)[/bold yellow]", choices=['e', 'k'], default='k').lower()
            if choice_input == 'e': choice = 'edit'
            else: choice = 'back'

        # --- Proses Pilihan ---
        if choice == 'edit':
            console.rule("[bold magenta]Edit Pengaturan[/bold magenta]", style="magenta")
            rprint("[dim](Tekan Enter untuk mempertahankan nilai saat ini)[/dim]")

            # --- Edit Email ---
            rprint(f"\n[bold cyan]--- {ICON_EMAIL} Email ---[/bold cyan]")
            settings['email_address'] = Prompt.ask(" 1. Alamat Email", default=settings['email_address'])
            new_pass = Prompt.ask(" 2. App Password [dim](input tersembunyi)[/dim]", password=True, default="")
            if new_pass: settings['app_password'] = new_pass
            else: rprint("[dim]   (Password tidak diubah)[/dim]")
            settings['imap_server'] = Prompt.ask(" 3. Server IMAP", default=settings['imap_server'])
            while True:
                try:
                    new_interval = int(Prompt.ask(f" 4. Interval Cek (detik, min 5)", default=str(settings['check_interval_seconds'])))
                    if new_interval >= 5: settings['check_interval_seconds'] = new_interval; break
                    else: rprint(f"   [red]{ICON_ERROR} Interval minimal 5 detik.[/red]")
                except ValueError: rprint(f"   [red]{ICON_ERROR} Masukkan angka bulat.[/red]")
            settings['target_keyword'] = Prompt.ask(" 5. Keyword Target", default=settings['target_keyword'])
            settings['trigger_keyword'] = Prompt.ask(" 6. Keyword Trigger", default=settings['trigger_keyword'])

            # --- Edit Binance ---
            rprint(f"\n[bold cyan]--- {ICON_BINANCE} Binance ---[/bold cyan]")
            if not BINANCE_AVAILABLE: rprint(f"[yellow]{ICON_WARN} Library Binance tidak terinstall.[/yellow]")
            settings['binance_api_key'] = Prompt.ask(" 7. API Key", default=settings['binance_api_key'])
            new_secret = Prompt.ask(" 8. API Secret [dim](input tersembunyi)[/dim]", password=True, default="")
            if new_secret: settings['binance_api_secret'] = new_secret
            else: rprint("[dim]   (Secret tidak diubah)[/dim]")
            settings['trading_pair'] = Prompt.ask(" 9. Trading Pair (e.g., BTCUSDT)", default=settings['trading_pair']).upper()
            while True:
                 try:
                     new_qty = float(Prompt.ask(f"10. Buy Quote Qty (e.g., 11.0)", default=str(settings['buy_quote_quantity'])))
                     if new_qty > 0: settings['buy_quote_quantity'] = new_qty; break
                     else: rprint(f"   [red]{ICON_ERROR} Kuantitas Beli harus > 0.[/red]")
                 except ValueError: rprint(f"   [red]{ICON_ERROR} Masukkan angka desimal.[/red]")
            while True:
                 try:
                     new_qty = float(Prompt.ask(f"11. Sell Base Qty (e.g., 0.0005, 0=nonaktif)", default=str(settings['sell_base_quantity'])))
                     if new_qty >= 0: settings['sell_base_quantity'] = new_qty; break
                     else: rprint(f"   [red]{ICON_ERROR} Kuantitas Jual harus >= 0.[/red]")
                 except ValueError: rprint(f"   [red]{ICON_ERROR} Masukkan angka desimal.[/red]")

            if BINANCE_AVAILABLE:
                current_exec_text = "Aktif" if settings['execute_binance_orders'] else "Nonaktif"
                exec_confirm = Confirm.ask(f"12. Eksekusi Order Binance? ({current_exec_text})", default=settings['execute_binance_orders'])
                settings['execute_binance_orders'] = exec_confirm
            else:
                settings['execute_binance_orders'] = False # Pastikan False jika lib tidak ada

            save_settings(settings) # Simpan perubahan
            Prompt.ask(f"\n[dim]Tekan Enter untuk kembali...[/dim]", default="")

        elif choice == 'back':
            break # Keluar loop pengaturan

# --- Fungsi Menu Utama (MODIFIED with Rich & Figlet) ---
def main_menu():
    settings = load_settings()

    while True:
        clear_screen()

        # --- Judul ASCII Art ---
        if FIGLET_AVAILABLE:
            figlet_title = pyfiglet.figlet_format("Exora AI Listener", font="slant")
            rprint(f"[bold magenta]{figlet_title}[/bold magenta]")
        else:
            console.rule("[bold magenta] Exora AI - Email & Binance Listener [/bold magenta]", style="magenta")

        # --- Panel Status ---
        status_table = Table(show_header=False, box=None, padding=(0, 1))
        status_table.add_column(style="dim cyan", width=18)
        status_table.add_column(style="white")

        email_ok = settings.get('email_address')
        pass_ok = settings.get('app_password')
        status_table.add_row(f"{ICON_EMAIL} Email Status", f"[{'green' if email_ok else 'red'}]{'OK' if email_ok else 'Kosong'}[/{'green' if email_ok else 'red'}] Email | [{'green' if pass_ok else 'red'}]{'OK' if pass_ok else 'Kosong'}[/{'green' if pass_ok else 'red'}] App Pass")

        if BINANCE_AVAILABLE:
            api_ok = settings.get('binance_api_key')
            secret_ok = settings.get('binance_api_secret')
            pair_ok = settings.get('trading_pair')
            buy_qty_ok = settings.get('buy_quote_quantity', 0) > 0
            sell_qty_val = settings.get('sell_base_quantity', 0)
            sell_qty_ok = sell_qty_val >= 0
            exec_active = settings.get('execute_binance_orders')

            status_table.add_row(f"{ICON_BINANCE} Binance Status", f"Lib: [green]OK[/green] | API: [{'green' if api_ok else 'red'}]{'OK' if api_ok else 'X'}[/{'green' if api_ok else 'red'}] | Secret: [{'green' if secret_ok else 'red'}]{'OK' if secret_ok else 'X'}[/{'green' if secret_ok else 'red'}] | Pair: [{'green' if pair_ok else 'red'}]{settings.get('trading_pair','X')}[/{'green' if pair_ok else 'red'}]")
            sell_qty_style = "green" if sell_qty_ok else "red"
            sell_qty_text = f"{sell_qty_val}" if sell_qty_ok else "Invalid"
            if exec_active and sell_qty_val == 0: sell_qty_style="yellow"; sell_qty_text+=" (Sell Off)"
            status_table.add_row(f"{ICON_QTY} Binance Qty", f"Buy: [{'green' if buy_qty_ok else 'red'}]{settings.get('buy_quote_quantity', 'X')}[/{'green' if buy_qty_ok else 'red'}] | Sell: [{sell_qty_style}]{sell_qty_text}[/{sell_qty_style}]")
            status_table.add_row(f"{ICON_EXECUTE} Eksekusi", f"[{'green' if exec_active else 'yellow'}]{'AKTIF' if exec_active else 'NONAKTIF'}[/{'green' if exec_active else 'yellow'}]")
        else:
            status_table.add_row(f"{ICON_BINANCE} Binance Status", f"[red]Library Tidak Terinstall {ICON_ERROR}[/red]")

        rprint(Panel(status_table, title="Status Konfigurasi", border_style="blue", expand=False))
        console.rule(style="blue")

        # --- Pilihan Menu Utama ---
        menu_title = f"{ICON_SETTINGS} Menu Utama [dim](Gunakan ↑ / ↓ dan Enter)[/dim]" if INQUIRER_AVAILABLE else f"{ICON_SETTINGS} Menu Utama [dim](Ketik Pilihan)[/dim]"

        if INQUIRER_AVAILABLE:
            start_text = f" {ICON_START} Mulai Mendengarkan" + (f" [dim](Email & [bold]Binance[/bold]){ICON_BINANCE}[/dim]" if settings.get("execute_binance_orders") and BINANCE_AVAILABLE else f" [dim](Email Only){ICON_EMAIL}[/dim]")
            choices = [(start_text, 'start'), (f" {ICON_SETTINGS} Pengaturan", 'settings'), (f" {ICON_EXIT} Keluar", 'exit')]
            questions = [inquirer.List('main_choice', message=menu_title, choices=choices, carousel=True)]
            try: answers = inquirer.prompt(questions, theme=GreenPassion()); choice_key = answers['main_choice'] if answers else 'exit'
            except KeyboardInterrupt: rprint(f"\n[yellow]{ICON_WARN} Keluar dari menu...[/yellow]"); choice_key = 'exit'; time.sleep(1)
            except Exception as e: rprint(f"[red]{ICON_ERROR} Error menu: {e}[/red]"); choice_key = 'exit'
        else: # Fallback input teks
            rprint(menu_title)
            rprint(f" 1. {ICON_START} Mulai Mendengarkan" + (" (Email & Binance)" if settings.get("execute_binance_orders") and BINANCE_AVAILABLE else " (Email Only)"))
            rprint(f" 2. {ICON_SETTINGS} Pengaturan")
            rprint(f" 3. {ICON_EXIT} Keluar")
            choice_input = Prompt.ask("[bold yellow]Masukkan pilihan Anda (1/2/3)[/bold yellow]", choices=['1', '2', '3'], default='3')
            if choice_input == '1': choice_key = 'start'
            elif choice_input == '2': choice_key = 'settings'
            else: choice_key = 'exit'

        # --- Proses Pilihan ---
        if choice_key == 'start':
            console.rule(style="blue")
            # Validasi (logika sama, pesan pakai Rich)
            valid_email = settings.get('email_address') and settings.get('app_password')
            execute_binance = settings.get("execute_binance_orders", False)
            valid_binance_config = False
            if execute_binance and BINANCE_AVAILABLE:
                 valid_binance_config = (settings.get('binance_api_key') and settings.get('binance_api_secret') and
                                         settings.get('trading_pair') and settings.get('buy_quote_quantity', 0) > 0 and
                                         settings.get('sell_base_quantity', 0) >= 0)

            error_messages = []
            if not valid_email: error_messages.append(f"[red]{ICON_ERROR} Pengaturan Email belum lengkap![/red]")
            if execute_binance and not BINANCE_AVAILABLE: error_messages.append(f"[red]{ICON_ERROR} Eksekusi aktif tapi library 'python-binance' tidak ada![/red]")
            if execute_binance and BINANCE_AVAILABLE and not valid_binance_config:
                 error_messages.append(f"[red]{ICON_ERROR} Konfigurasi Binance belum lengkap/valid untuk eksekusi![/red]")
                 # Tambahkan detail error jika perlu

            if error_messages:
                error_content = "\n".join(error_messages)
                error_content += f"\n\n[yellow]Silakan perbaiki melalui menu '{ICON_SETTINGS} Pengaturan'.[/yellow]"
                rprint(Panel(error_content, title=f"{ICON_WARN} Tidak Bisa Memulai", border_style="red", expand=False))
                Prompt.ask(f"[dim]Tekan Enter untuk kembali...[/dim]", default="")
            else:
                clear_screen()
                mode = "Email & Binance Order" if execute_binance and BINANCE_AVAILABLE else "Email Listener Only"
                icon_mode = ICON_BINANCE if execute_binance and BINANCE_AVAILABLE else ICON_EMAIL
                rprint(Panel(f"[bold green]Mode: {mode} {icon_mode}[/bold green]", title=f"{ICON_START} Memulai Listener", border_style="green", expand=False))
                start_listening(settings)
                rprint(f"\n[yellow]{ICON_INFO} Kembali ke Menu Utama...[/yellow]")
                time.sleep(2)

        elif choice_key == 'settings':
            show_settings(settings)
            settings = load_settings() # Load ulang jika ada perubahan

        elif choice_key == 'exit':
            rprint(f"\n[bold cyan]Terima kasih! Sampai jumpa! {ICON_EXIT}[/bold cyan]")
            sys.exit(0)

# --- Entry Point ---
if __name__ == "__main__":
    if sys.version_info < (3, 7): # Rich mungkin perlu 3.7+ untuk fitur lengkap
        rprint(f"[bold red]Error: Script ini optimal dengan Python 3.7 atau lebih tinggi.[/bold red]")
        # sys.exit(1) # Bisa di-uncomment jika mau strict

    try:
        main_menu()
    except KeyboardInterrupt:
        console.print(f"\n[bold yellow]{ICON_WARN} Program dihentikan paksa dari luar menu.[/bold yellow]")
        sys.exit(1)
    except Exception as e:
        clear_screen()
        console.rule("[bold red] ERROR KRITIS [/bold red]", style="red")
        console.print(f"[bold red]Terjadi kesalahan fatal yang tidak tertangani:[/bold red]")
        console.print_exception(show_locals=True) # Tampilkan traceback & locals dgn Rich
        console.print(f"\n[red]Pesan Error: {e}[/red]")
        console.rule(style="red")
        Prompt.ask(f"[dim]Tekan Enter untuk keluar...[/dim]", default="")
        sys.exit(1)
