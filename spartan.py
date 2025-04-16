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
import requests # Untuk menangani error koneksi Binance

# --- Rich Integration (untuk UI keren) ---
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.rule import Rule
    from rich.columns import Columns
    from rich.spinner import Spinner
    from rich.prompt import Prompt, Confirm, IntPrompt, FloatPrompt
    from rich.table import Table
    from rich import print as rprint # Gunakan print dari rich
    RICH_AVAILABLE = True
    console = Console() # Inisialisasi console global
except ImportError:
    RICH_AVAILABLE = False
    print("\n!!! WARNING: Library 'rich' tidak ditemukan. !!!")
    print("!!!          Tampilan CLI akan standar.          !!!")
    print("!!!          Install dengan: pip install rich    !!!\n")
    # Definisikan fungsi print pengganti jika rich tidak ada
    def rprint(*args, **kwargs): print(*args, **kwargs)
    # Definisikan class dummy jika rich tidak ada
    class Panel: def __init__(self, content, **kwargs): self.content = content; self.kwargs = kwargs
    class Text: def __init__(self, text, **kwargs): self.text = text; self.kwargs = kwargs
    class Rule: def __init__(self, *args, **kwargs): pass
    class Spinner: def __init__(self, *args, **kwargs): pass
    class Columns: def __init__(self, *args, **kwargs): pass
    class Prompt: pass
    class Confirm: pass
    class IntPrompt: pass
    class FloatPrompt: pass
    console = None # Tandai console tidak ada
    time.sleep(3)

# --- Inquirer Integration (untuk menu interaktif) ---
try:
    import inquirer
    # Tema bisa disesuaikan atau dihapus jika tidak perlu
    # from inquirer.themes import GreenPassion
    INQUIRER_AVAILABLE = True
except ImportError:
    INQUIRER_AVAILABLE = False
    rprint("[yellow]!!! WARNING: Library 'inquirer' tidak ditemukan. !!![/]")
    rprint("[yellow]!!!          Menu akan menggunakan input teks biasa.     !!![/]")
    rprint("[yellow]!!!          Install dengan: pip install inquirer       !!![/]\n")
    time.sleep(3) # Beri waktu untuk membaca warning

# --- Binance Integration ---
try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException, BinanceOrderException
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False
    rprint("\n[bold yellow]!!! WARNING: Library 'python-binance' tidak ditemukan. !!![/]")
    rprint("[yellow]!!!          Fitur eksekusi order Binance tidak akan berfungsi. !!![/]")
    rprint("[yellow]!!!          Install dengan: pip install python-binance         !!![/]\n")
    class BinanceAPIException(Exception): pass
    class BinanceOrderException(Exception): pass
    class Client:
        SIDE_BUY = 'BUY'
        SIDE_SELL = 'SELL'
        ORDER_TYPE_MARKET = 'MARKET'

# --- Konfigurasi & Variabel Global ---
# (Konfigurasi & Variabel Global Tetap Sama)
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
running = True

# Hapus Kode Warna ANSI Lama, kita pakai markup Rich
# RESET = "\033[0m"
# BOLD = "\033[1m"
# ... dan seterusnya

# --- Fungsi Penanganan Sinyal (Ctrl+C) ---
def signal_handler(sig, frame):
    global running
    rprint(f"\n[bold yellow][WARN] Ctrl+C terdeteksi. Menghentikan program...[/]")
    running = False
    time.sleep(1.5)
    rprint(f"[bold red][EXIT] Keluar dari program.[/]")
    # Pastikan terminal kembali normal jika menggunakan fitur rich
    if RICH_AVAILABLE and console:
        console.show_cursor(True)
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# --- Fungsi Konfigurasi (Load & Save) ---
# (Tidak perlu diubah secara fungsional, tapi pesan error/info pakai rprint)
def load_settings():
    settings = DEFAULT_SETTINGS.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_settings = json.load(f)
                valid_keys = set(DEFAULT_SETTINGS.keys())
                filtered_settings = {k: v for k, v in loaded_settings.items() if k in valid_keys}
                settings.update(filtered_settings)

                # Validasi (pesan pakai rprint)
                if settings.get("check_interval_seconds", 10) < 5:
                    rprint(f"[yellow][WARN] Interval cek di '{CONFIG_FILE}' < 5 detik, direset ke 10.[/]")
                    settings["check_interval_seconds"] = 10
                if not isinstance(settings.get("buy_quote_quantity"), (int, float)) or settings.get("buy_quote_quantity") <= 0:
                    rprint(f"[yellow][WARN] 'buy_quote_quantity' tidak valid, direset ke {DEFAULT_SETTINGS['buy_quote_quantity']}.[/]")
                    settings["buy_quote_quantity"] = DEFAULT_SETTINGS['buy_quote_quantity']
                if not isinstance(settings.get("sell_base_quantity"), (int, float)) or settings.get("sell_base_quantity") < 0:
                    rprint(f"[yellow][WARN] 'sell_base_quantity' tidak valid, direset ke {DEFAULT_SETTINGS['sell_base_quantity']}.[/]")
                    settings["sell_base_quantity"] = DEFAULT_SETTINGS['sell_base_quantity']
                if not isinstance(settings.get("execute_binance_orders"), bool):
                    rprint(f"[yellow][WARN] 'execute_binance_orders' tidak valid, direset ke False.[/]")
                    settings["execute_binance_orders"] = False

                # Simpan hanya jika ada koreksi atau file baru saja dibuat
                if settings != loaded_settings:
                     save_settings(settings, silent=True) # silent agar tidak print saat load awal

        except json.JSONDecodeError:
            rprint(f"[bold red][ERROR] File konfigurasi '{CONFIG_FILE}' rusak. Menggunakan default & menyimpan ulang.[/]")
            save_settings(settings)
        except Exception as e:
            rprint(f"[bold red][ERROR] Gagal memuat konfigurasi: {e}[/]")
    else:
        rprint(f"[yellow][INFO] File konfigurasi '{CONFIG_FILE}' tidak ditemukan. Membuat dengan nilai default.[/]")
        save_settings(settings)
    return settings

def save_settings(settings, silent=False):
    """Menyimpan pengaturan ke file JSON."""
    try:
        # Pastikan tipe data benar
        settings['check_interval_seconds'] = int(settings.get('check_interval_seconds', DEFAULT_SETTINGS['check_interval_seconds']))
        settings['buy_quote_quantity'] = float(settings.get('buy_quote_quantity', DEFAULT_SETTINGS['buy_quote_quantity']))
        settings['sell_base_quantity'] = float(settings.get('sell_base_quantity', DEFAULT_SETTINGS['sell_base_quantity']))
        settings['execute_binance_orders'] = bool(settings.get('execute_binance_orders', DEFAULT_SETTINGS['execute_binance_orders']))

        settings_to_save = {k: settings.get(k, DEFAULT_SETTINGS[k]) for k in DEFAULT_SETTINGS}

        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings_to_save, f, indent=4, sort_keys=True)
        if not silent:
            rprint(f"[green][INFO] Pengaturan berhasil disimpan ke '{CONFIG_FILE}'[/]")
    except Exception as e:
        rprint(f"[bold red][ERROR] Gagal menyimpan konfigurasi: {e}[/]")

# --- Fungsi Utilitas ---
# (clear_screen pakai console.clear, decode/get_email pakai rprint untuk error)
def clear_screen():
    if RICH_AVAILABLE and console:
        console.clear()
    else:
        os.system('cls' if os.name == 'nt' else 'clear')

def decode_mime_words(s):
    # (Logika sama, warning pakai rprint)
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
        rprint(f"[yellow][WARN] Gagal mendekode header: {e}. Header asli: {s}[/]")
        return str(s) if isinstance(s, str) else s.decode('utf-8', errors='replace') if isinstance(s, bytes) else "[Decoding Error]"

def get_text_from_email(msg):
    # (Logika sama, warning pakai rprint)
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
                    rprint(f"[yellow][WARN] Tidak bisa mendekode bagian email (charset: {part.get_content_charset()}): {e}[/]")
    else:
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                if payload: text_content = payload.decode(charset, errors='replace')
            except Exception as e:
                 rprint(f"[yellow][WARN] Tidak bisa mendekode body email (charset: {msg.get_content_charset()}): {e}[/]")
    return " ".join(text_content.split()).lower()

# --- Fungsi Beep ---
# (Output pakai rprint)
def trigger_beep(action):
    try:
        if action == "buy":
            rprint(f"[bold magenta]🔊 BEEP![/] [dim]('BUY')[/]")
            subprocess.run(["beep", "-f", "1000", "-l", "300"], check=True, capture_output=True, text=True)
            time.sleep(0.1)
            subprocess.run(["beep", "-f", "1200", "-l", "200"], check=True, capture_output=True, text=True)
        elif action == "sell":
            rprint(f"[bold magenta]🔊 BEEP![/] [dim]('SELL')[/]")
            subprocess.run(["beep", "-f", "700", "-l", "500"], check=True, capture_output=True, text=True)
        else:
             rprint(f"[yellow][WARN] Aksi beep tidak dikenal '{action}'.[/]")
    except FileNotFoundError:
        rprint(f"[yellow][WARN] Perintah 'beep' tidak ditemukan. Beep dilewati.[/]")
        rprint(f"[dim]         (Untuk Linux, coba: sudo apt install beep / sudo yum install beep)[/]")
    except subprocess.CalledProcessError as e:
        rprint(f"[bold red][ERROR] Gagal menjalankan 'beep': {e}[/]")
        if e.stderr: rprint(f"[red]         Stderr: {e.stderr.strip()}[/]")
    except Exception as e:
        rprint(f"[bold red][ERROR] Kesalahan tak terduga saat beep: {e}[/]")

# --- Fungsi Eksekusi Binance ---
# (Output pakai rprint, tambah rich formatting untuk detail order sukses/error)
def get_binance_client(settings):
    """Membuat instance Binance client."""
    if not BINANCE_AVAILABLE:
        rprint(f"[bold red][ERROR] Library python-binance tidak terinstall. Tidak bisa membuat client.[/]")
        return None
    api_key = settings.get('binance_api_key')
    api_secret = settings.get('binance_api_secret')
    if not api_key or not api_secret:
        rprint(f"[bold red][ERROR] API Key atau Secret Key Binance belum diatur di konfigurasi.[/]")
        return None

    status_text = Text("Mencoba koneksi ke Binance API...", style="cyan")
    if RICH_AVAILABLE and console:
        with console.status(status_text, spinner="dots"):
            try:
                client = Client(api_key, api_secret)
                client.ping() # Tes koneksi
                rprint(f"[bold green]✅ [BINANCE] Koneksi dan autentikasi berhasil.[/]")
                return client
            except BinanceAPIException as e:
                rprint(f"[bold red]❌ [BINANCE ERROR] Gagal terhubung/autentikasi: Status={e.status_code}, Pesan='{e.message}'[/]")
                if "timestamp" in e.message.lower(): rprint(f"[yellow]   -> Periksa apakah waktu sistem Anda sinkron.[/]")
                if "signature" in e.message.lower() or "invalid key" in e.message.lower(): rprint(f"[yellow]   -> Periksa kembali API Key dan Secret Key Anda.[/]")
                return None
            except requests.exceptions.RequestException as e:
                rprint(f"[bold red]❌ [NETWORK ERROR] Gagal menghubungi Binance API: {e}[/]")
                rprint(f"[yellow]   -> Periksa koneksi internet Anda.[/]")
                return None
            except Exception as e:
                rprint(f"[bold red]❌ [ERROR] Gagal membuat Binance client: {e}[/]")
                # traceback.print_exc() # Uncomment jika butuh detail traceback
                return None
    else: # Fallback tanpa spinner
        rprint(status_text.plain)
        # Logika try-except diulang agar tidak duplikat kode terlalu banyak
        try:
            client = Client(api_key, api_secret)
            client.ping()
            rprint("[INFO] Koneksi Binance berhasil.")
            return client
        except Exception as e:
            rprint(f"[ERROR] Koneksi Binance gagal: {e}")
            return None


def execute_binance_order(client, settings, side):
    """Mengeksekusi order MARKET BUY atau SELL di Binance."""
    if not client:
        rprint(f"[red][BINANCE] Eksekusi dibatalkan, client tidak valid.[/]")
        return False
    if not settings.get("execute_binance_orders", False):
        rprint(f"[yellow][BINANCE] Eksekusi order dinonaktifkan. Order dilewati.[/]")
        return False

    pair = settings.get('trading_pair', '').upper()
    if not pair:
        rprint(f"[red][BINANCE ERROR] Trading pair belum diatur.[/]")
        return False

    order_details = {}
    action_desc = ""
    order_successful = False
    result_details = {}

    try:
        if side == Client.SIDE_BUY:
            quote_qty = settings.get('buy_quote_quantity', 0.0)
            if quote_qty <= 0:
                 rprint(f"[red][BINANCE ERROR] Kuantitas Beli (buy_quote_quantity) harus > 0.[/]")
                 return False
            order_details = {'symbol': pair, 'side': Client.SIDE_BUY, 'type': Client.ORDER_TYPE_MARKET, 'quoteOrderQty': quote_qty}
            action_desc = f"[bold magenta]BUY {quote_qty} (quote) of {pair}[/]"

        elif side == Client.SIDE_SELL:
            base_qty = settings.get('sell_base_quantity', 0.0)
            if base_qty <= 0:
                 rprint(f"[yellow][BINANCE WARN] Kuantitas Jual (sell_base_quantity) adalah 0. Order SELL tidak dieksekusi.[/]")
                 return False # Bukan error, tapi tidak eksekusi
            order_details = {'symbol': pair, 'side': Client.SIDE_SELL, 'type': Client.ORDER_TYPE_MARKET, 'quantity': base_qty}
            action_desc = f"[bold magenta]SELL {base_qty} (base) of {pair}[/]"
        else:
            rprint(f"[red][BINANCE ERROR] Sisi order tidak valid: {side}[/]")
            return False

        rprint(f"[cyan]Binance 執行:[/cyan] Mencoba eksekusi {action_desc}...")

        status_text = Text(f"Mengirim order {side} {pair}...", style="cyan")
        if RICH_AVAILABLE and console:
             with console.status(status_text, spinner="arrow3"):
                 order_result = client.create_order(**order_details)
                 time.sleep(0.5) # Beri jeda sedikit
        else:
             rprint(status_text.plain)
             order_result = client.create_order(**order_details)


        rprint(f"[bold green]✅ [BINANCE SUCCESS] Order berhasil dieksekusi![/]")
        # Tampilkan detail order dengan format lebih rapi
        result_details = {
            "Order ID": str(order_result.get('orderId')),
            "Symbol": order_result.get('symbol'),
            "Side": order_result.get('side'),
            "Status": order_result.get('status')
        }
        if order_result.get('fills') and len(order_result.get('fills')) > 0:
            total_qty = sum(float(f['qty']) for f in order_result['fills'])
            total_quote_qty = sum(float(f['cummulativeQuoteQty']) for f in order_result['fills'])
            avg_price = total_quote_qty / total_qty if total_qty else 0
            result_details["Avg Price"] = f"{avg_price:.8f}"
            result_details["Filled Qty (Base)"] = f"{total_qty:.8f}"
            result_details["Filled Qty (Quote)"] = f"{total_quote_qty:.4f}"
        elif order_result.get('cummulativeQuoteQty'):
             result_details["Total Cost/Proceeds (Quote)"] = f"{float(order_result['cummulativeQuoteQty']):.4f}"

        # Cetak detail menggunakan cara yang lebih terstruktur (jika rich ada)
        if RICH_AVAILABLE:
             for key, value in result_details.items():
                 rprint(f"  [dim]{key:<25}:[/] [bright_white]{value}[/]")
        else:
             for key, value in result_details.items():
                 print(f"  {key}: {value}")

        order_successful = True

    except BinanceAPIException as e:
        rprint(f"[bold red]❌ [BINANCE API ERROR] Gagal eksekusi: Status={e.status_code}, Kode={e.code}, Pesan='{e.message}'[/]")
        if e.code == -2010: rprint(f"[red]   -> Kemungkinan saldo tidak cukup.[/]")
        elif e.code == -1121: rprint(f"[red]   -> Trading pair '{pair}' tidak valid.[/]")
        elif e.code == -1013 or 'MIN_NOTIONAL' in str(e.message): rprint(f"[red]   -> Order size terlalu kecil (cek MIN_NOTIONAL).[/]")
        elif e.code == -1111: rprint(f"[red]   -> Kuantitas order tidak sesuai aturan LOT_SIZE.[/]")
    except BinanceOrderException as e:
        rprint(f"[bold red]❌ [BINANCE ORDER ERROR] Gagal eksekusi: Status={e.status_code}, Kode={e.code}, Pesan='{e.message}'[/]")
    except requests.exceptions.RequestException as e:
        rprint(f"[bold red]❌ [NETWORK ERROR] Gagal mengirim order ke Binance: {e}[/]")
    except Exception as e:
        rprint(f"[bold red]❌ [ERROR] Kesalahan tak terduga saat eksekusi order Binance:[/]")
        if RICH_AVAILABLE and console: console.print_exception(show_locals=False)
        else: traceback.print_exc()

    return order_successful

# --- Fungsi Pemrosesan Email ---
# (Output pakai rprint, tambah Rule pemisah)
def process_email(mail, email_id, settings, binance_client):
    global running
    if not running: return

    target_keyword_lower = settings['target_keyword'].lower()
    trigger_keyword_lower = settings['trigger_keyword'].lower()
    email_id_str = email_id.decode('utf-8')

    try:
        # Gunakan status untuk fetch
        status_text = Text(f"Mengambil email ID {email_id_str}...", style="dim cyan")
        fetch_success = False
        raw_email = None
        if RICH_AVAILABLE and console:
             with console.status(status_text, spinner="moon"):
                 status, data = mail.fetch(email_id, "(RFC822)")
                 if status == 'OK':
                     raw_email = data[0][1]
                     fetch_success = True
                 else:
                     rprint(f"[red][ERROR] Gagal mengambil email ID {email_id_str}: {status}[/]")
                 time.sleep(0.2) # Sedikit jeda
        else:
             rprint(status_text.plain)
             status, data = mail.fetch(email_id, "(RFC822)")
             if status == 'OK':
                 raw_email = data[0][1]
                 fetch_success = True
             else:
                  rprint(f"[ERROR] Gagal mengambil email: {status}")

        if not fetch_success or not raw_email:
            return # Keluar jika fetch gagal

        msg = email.message_from_bytes(raw_email)
        subject = decode_mime_words(msg["Subject"])
        sender = decode_mime_words(msg["From"])
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Tampilkan info email dalam Panel jika rich tersedia
        email_info_text = Text()
        email_info_text.append(f"ID    : {email_id_str}\n", style="dim")
        email_info_text.append(f"Dari  : {sender}\n", style="white")
        email_info_text.append(f"Subjek: {subject}", style="bright_white")

        if RICH_AVAILABLE:
            rprint(Panel(email_info_text, title=f"📧 Email Diterima ({timestamp})", border_style="blue", expand=False))
        else:
            rprint(f"\n--- Email Diterima ({timestamp}) ---")
            print(f" ID    : {email_id_str}")
            print(f" Dari  : {sender}")
            print(f" Subjek: {subject}")

        body = get_text_from_email(msg)
        full_content = (subject.lower() + " " + body)

        if target_keyword_lower in full_content:
            rprint(f"[green]🎯 Keyword target '{settings['target_keyword']}' ditemukan.[/]")
            try:
                target_index = full_content.find(target_keyword_lower)
                trigger_index = full_content.find(trigger_keyword_lower, target_index + len(target_keyword_lower))

                if trigger_index != -1:
                    start_word_index = trigger_index + len(trigger_keyword_lower)
                    text_after_trigger = full_content[start_word_index:].lstrip()
                    words_after_trigger = text_after_trigger.split(maxsplit=1)

                    if words_after_trigger:
                        action_word = words_after_trigger[0].strip('.,!?:;()[]{}').lower()
                        rprint(f"[green]🔑 Keyword trigger '{settings['trigger_keyword']}' ditemukan. Aksi: [bold cyan]{action_word}[/][/]")

                        # --- Trigger Aksi ---
                        order_attempted = False
                        execute_binance = settings.get("execute_binance_orders", False)

                        if action_word == "buy":
                            trigger_beep("buy")
                            if execute_binance:
                                if binance_client:
                                    execute_binance_order(binance_client, settings, Client.SIDE_BUY)
                                    order_attempted = True
                                else: rprint(f"[yellow][WARN] Eksekusi Binance aktif tapi client tidak valid.[/]")

                        elif action_word == "sell":
                            can_sell = settings.get('sell_base_quantity', 0.0) > 0
                            trigger_beep("sell")
                            if execute_binance:
                                if can_sell:
                                    if binance_client:
                                        execute_binance_order(binance_client, settings, Client.SIDE_SELL)
                                        order_attempted = True
                                    else: rprint(f"[yellow][WARN] Eksekusi Binance aktif tapi client tidak valid.[/]")
                                elif settings.get('sell_base_quantity') <= 0:
                                    rprint(f"[yellow][INFO] Aksi 'sell', tapi 'sell_base_quantity'=0. Order Binance dilewati.[/]")

                        else:
                            rprint(f"[blue][INFO] Kata setelah trigger ('{action_word}') bukan 'buy'/'sell'. Tidak ada aksi market.[/]")

                        if execute_binance and action_word in ["buy", "sell"] and not order_attempted and not (action_word == "sell" and settings.get('sell_base_quantity', 0.0) <= 0):
                             rprint(f"[yellow][BINANCE] Eksekusi tidak dilakukan (lihat error client di atas).[/]")

                    else: rprint(f"[yellow][WARN] Trigger ditemukan, tapi tidak ada kata setelahnya.[/]")
                else: rprint(f"[yellow][WARN] Target ditemukan, tapi trigger '{settings['trigger_keyword']}' tidak ditemukan [u]setelahnya[/].[/]")

            except Exception as e:
                 rprint(f"[bold red][ERROR] Gagal parsing kata setelah trigger: {e}[/]")
                 if RICH_AVAILABLE and console: console.print_exception(show_locals=False)
                 else: traceback.print_exc()
        else:
            rprint(f"[blue][INFO] Keyword target '{settings['target_keyword']}' tidak ditemukan.[/]")

        # Tandai email sebagai sudah dibaca ('Seen')
        try:
            # rprint(f"[dim]Menandai email {email_id_str} sebagai 'Seen'...[/]", end='\r')
            mail.store(email_id, '+FLAGS', '\\Seen')
            # rprint(" " * 40, end='\r') # Clear message
        except Exception as e:
            rprint(f"\n[red][ERROR] Gagal menandai email {email_id_str} sebagai 'Seen': {e}[/]")

        # Tambahkan pemisah Rule
        if RICH_AVAILABLE: rprint(Rule(style="dim blue"))
        else: print("-------------------------------------------")

    except Exception as e:
        rprint(f"[bold red][ERROR] Gagal memproses email ID {email_id_str}:[/]")
        if RICH_AVAILABLE and console: console.print_exception(show_locals=False)
        else: traceback.print_exc()
        if RICH_AVAILABLE: rprint(Rule(style="dim red")) # Pemisah error

# --- Fungsi Listening Utama ---
# (Gunakan spinner untuk status, rprint untuk log, Rule pemisah)
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
    check_interval = settings['check_interval_seconds']

    # --- Setup Binance Client ---
    execute_binance = settings.get("execute_binance_orders", False)
    if execute_binance:
        if not BINANCE_AVAILABLE:
             rprint(f"[bold red][FATAL] Eksekusi Binance aktif tapi library python-binance tidak ada![/]")
             rprint(f"[yellow] -> Install: pip install python-binance atau nonaktifkan eksekusi.[/]")
             running = False
             return
        rprint(Rule("[bold cyan]Inisialisasi Binance[/]", style="cyan"))
        binance_client = get_binance_client(settings)
        if not binance_client:
            rprint(f"[bold red][FATAL] Gagal menginisialisasi Binance Client.[/]")
            rprint(f"[yellow] -> Periksa API Key/Secret, koneksi, dan waktu sistem.[/]")
            rprint(f"[yellow] -> Program akan lanjut untuk notifikasi email saja.[/]")
        else:
            # Pesan sukses sudah ada di get_binance_client
            pass
        rprint(Rule(style="cyan"))
    else:
        rprint(Panel("[yellow]ℹ️ Eksekusi order Binance dinonaktifkan.[/]\n[dim](Hanya notifikasi email dan beep yang akan aktif)[/]", title="Info", border_style="yellow", expand=False))

    spinner_name = "dots" # Default spinner
    if RICH_AVAILABLE: spinner_name = "simpleDotsScrolling" # Pilih spinner keren jika ada

    while running:
        try:
            # --- Koneksi IMAP ---
            if not mail or mail.state != 'SELECTED':
                status_text = Text(f"Menghubungkan ke IMAP {settings['imap_server']}...", style="cyan")
                if RICH_AVAILABLE and console:
                    with console.status(status_text, spinner="earth"):
                        try:
                            mail = imaplib.IMAP4_SSL(settings['imap_server'], timeout=30)
                            rv, desc = mail.login(settings['email_address'], settings['app_password'])
                            if rv != 'OK': raise imaplib.IMAP4.error(f"Login failed: {desc}")
                            mail.select("inbox")
                            rprint(f"[bold green]✅ Login email berhasil![/] [dim]({settings['email_address']})[/]")
                            rprint(Rule("[bold green]Memulai Mode Mendengarkan[/]", style="green"))
                            consecutive_errors = 0
                            wait_time = initial_wait_time
                        except (imaplib.IMAP4.error, OSError, socket.gaierror, socket.error) as conn_err:
                             rprint(f"[bold red]❌ Login Email / Koneksi GAGAL![/]")
                             rprint(f"[red]   Pesan: {conn_err}[/]")
                             if "authentication failed" in str(conn_err).lower() or "invalid credentials" in str(conn_err).lower():
                                 rprint(f"[yellow]   -> Periksa Alamat Email & App Password.[/]")
                                 rprint(f"[yellow]   -> Pastikan Akses IMAP diaktifkan & Less Secure Apps (jika perlu) diizinkan.[/]")
                                 running = False # Berhenti jika otentikasi gagal
                             else:
                                 rprint(f"[yellow]   -> Periksa Server IMAP & Koneksi Internet.[/]")
                             mail = None # Pastikan mail None jika gagal
                             raise conn_err # Lemparkan lagi untuk ditangkap di blok except luar
                else: # Fallback tanpa spinner
                    rprint(status_text.plain)
                    try:
                        mail = imaplib.IMAP4_SSL(settings['imap_server'], timeout=30)
                        rv, desc = mail.login(settings['email_address'], settings['app_password'])
                        if rv != 'OK': raise imaplib.IMAP4.error(f"Login failed: {desc}")
                        mail.select("inbox")
                        rprint("[INFO] Login email berhasil.")
                        rprint("--- Memulai Mode Mendengarkan ---")
                        consecutive_errors = 0
                        wait_time = initial_wait_time
                    except Exception as conn_err:
                        rprint(f"[ERROR] Login/Koneksi Gagal: {conn_err}")
                        mail = None
                        raise conn_err

            # --- Loop Cek Email & Koneksi ---
            status_listen = f"[blue]Mendengarkan email baru... Cek setiap {check_interval} detik[/]"
            if RICH_AVAILABLE and console:
                 with console.status(status_listen, spinner=spinner_name):
                     while running:
                         current_time = time.time()
                         if current_time - last_check_time < check_interval:
                             time.sleep(0.5)
                             continue

                         # Cek IMAP NOOP
                         try:
                             status, _ = mail.noop()
                             if status != 'OK':
                                 rprint(f"\n[yellow][WARN] Koneksi IMAP NOOP gagal ({status}). Reconnecting...[/]")
                                 try: mail.close()
                                 except Exception: pass
                                 mail = None; break
                         except (imaplib.IMAP4.abort, imaplib.IMAP4.readonly, BrokenPipeError, OSError) as noop_err:
                             rprint(f"\n[yellow][WARN] Koneksi IMAP terputus ({type(noop_err).__name__}). Reconnecting...[/]")
                             try: mail.logout()
                             except Exception: pass
                             mail = None; break

                         # Cek Binance Ping (jika aktif & perlu)
                         if binance_client and current_time - getattr(binance_client, '_last_ping_time', 0) > max(60, check_interval * 5):
                             try:
                                 # Ping tanpa status/spinner agar tidak terlalu berisik
                                 binance_client.ping()
                                 setattr(binance_client, '_last_ping_time', current_time)
                             except Exception as ping_err:
                                 rprint(f"\n[yellow][WARN] Ping ke Binance API gagal ({ping_err}). Re-init client...[/]")
                                 binance_client = get_binance_client(settings) # Coba buat ulang
                                 if binance_client:
                                     rprint(f"[green]   -> Binance client berhasil dibuat ulang.[/]")
                                     setattr(binance_client, '_last_ping_time', current_time)
                                 else:
                                     rprint(f"[red]   -> Gagal membuat ulang Binance client.[/]")
                                 time.sleep(5) # Jeda

                         # Cek Email UNSEEN
                         status, messages = mail.search(None, '(UNSEEN)')
                         if status != 'OK':
                             rprint(f"\n[red][ERROR] Gagal mencari email UNSEEN: {status}[/]")
                             try: mail.close()
                             except Exception: pass
                             mail = None; break

                         email_ids = messages[0].split()
                         if email_ids:
                             num_emails = len(email_ids)
                             # Keluar dari status spinner sebelum print email
                             console.show_cursor(True)
                             console.print(f"\n[bold green][!] Menemukan {num_emails} email baru! Memproses...[/]")
                             console.show_cursor(False) # Sembunyikan lagi
                             # Hentikan spinner sementara
                             console.live.stop()

                             for i, email_id in enumerate(email_ids):
                                 if not running: break
                                 # rprint(f"[dim]--- Memproses email {i+1}/{num_emails} ---[/]") # Bisa diaktifkan jika perlu
                                 process_email(mail, email_id, settings, binance_client)
                             if not running: break
                             # rprint(Rule(style="dim green"))
                             rprint(f"[green][INFO] Selesai memproses {num_emails} email. Kembali mendengarkan...[/]")
                             # Mulai lagi spinner setelah selesai proses
                             console.live.start(refresh=True)


                         last_check_time = current_time
                         # Update status spinner dengan '.' bergerak jika tidak ada email
                         if not email_ids:
                            dots = "." * (int(time.time()) % 4)
                            console.live.update(Text(f"{status_listen} {dots}", style="blue"), refresh=True)

                         time.sleep(0.1) # Short sleep dalam loop inner

            else: # Fallback tanpa Rich spinner
                while running:
                    current_time = time.time()
                    if current_time - last_check_time < check_interval:
                        time.sleep(1)
                        continue
                    print(f"[INFO] Mengecek email...", end='\r')
                    # (Logika cek IMAP, Binance, Email sama seperti di atas, tapi pakai print biasa)
                    # ... (Implementasi fallback cek IMAP, Binance, Email) ...
                    # Cek IMAP NOOP
                    try:
                        status, _ = mail.noop()
                        if status != 'OK': raise Exception(f"NOOP failed: {status}")
                    except Exception as noop_err:
                        print(f"\n[WARN] Koneksi IMAP terputus/gagal NOOP: {noop_err}. Reconnecting...")
                        try: mail.logout()
                        except: pass
                        mail=None; break # Reconnect di loop luar

                    # Cek Binance (tanpa ping di fallback)

                    # Cek Email
                    status, messages = mail.search(None, '(UNSEEN)')
                    if status != 'OK':
                        print(f"\n[ERROR] Gagal cari email: {status}")
                        try: mail.logout()
                        except: pass
                        mail=None; break

                    email_ids = messages[0].split()
                    if email_ids:
                        print(f"\n[INFO] Ditemukan {len(email_ids)} email baru!")
                        for email_id in email_ids:
                            if not running: break
                            process_email(mail, email_id, settings, binance_client)
                        if not running: break
                        print("[INFO] Selesai proses. Kembali mendengarkan...")
                    else:
                        print(f"[INFO] Tidak ada email baru. Cek lagi dalam {check_interval}s.   ", end='\r')


                    last_check_time = current_time
                    time.sleep(1) # Sedikit jeda

            # Keluar loop inner (baik karena error atau stop)
            if mail and mail.state == 'SELECTED':
                try: mail.close()
                except Exception: pass


        except (imaplib.IMAP4.error, imaplib.IMAP4.abort, BrokenPipeError, OSError, socket.error, socket.gaierror) as e:
            rprint(f"\n[bold red]❌ [ERROR] Kesalahan IMAP/Koneksi Jaringan: {e}[/]")
            consecutive_errors += 1
            if "login failed" in str(e).lower() or "authentication failed" in str(e).lower():
                rprint(f"[bold red][FATAL] Login Gagal! Periksa kredensial.[/]")
                running = False
            elif consecutive_errors >= max_consecutive_errors:
                 rprint(f"[yellow][WARN] Terlalu banyak error ({consecutive_errors}). Jeda {long_wait_time} detik...[/]")
                 time.sleep(long_wait_time); wait_time = initial_wait_time; consecutive_errors = 0
            else:
                 rprint(f"[yellow][WARN] Mencoba reconnect dalam {wait_time} detik... (Error: {consecutive_errors})[/]")
                 time.sleep(wait_time); wait_time = min(wait_time * 2, 30)
        except Exception as e:
            rprint(f"\n[bold red]❌ [ERROR] Kesalahan tak terduga di loop utama:[/]")
            if RICH_AVAILABLE and console: console.print_exception(show_locals=False)
            else: traceback.print_exc()
            consecutive_errors += 1
            rprint(f"[yellow][WARN] Mencoba lanjut setelah error. Tunggu {wait_time} detik... (Error: {consecutive_errors})[/]")
            time.sleep(wait_time); wait_time = min(wait_time * 2, 60)
            if consecutive_errors >= max_consecutive_errors + 2:
                 rprint(f"[bold red][FATAL] Terlalu banyak error tak terduga. Berhenti.[/]")
                 running = False
        finally:
            if mail and mail.state != 'LOGOUT':
                try: mail.logout()
                except Exception: pass
            mail = None
            if RICH_AVAILABLE and console:
                 console.show_cursor(True) # Pastikan cursor terlihat jika loop berhenti
        if running: time.sleep(0.5)

    rprint(Rule("[bold yellow]Mode Mendengarkan Dihentikan[/]", style="yellow"))


# --- Fungsi Menu Pengaturan (MODIFIED with Rich) ---
def show_settings(settings):
    """Menampilkan dan mengedit pengaturan menggunakan Rich & Prompt Toolkit (via Inquirer)."""
    while True:
        clear_screen()
        rprint(Panel("[bold cyan]🔧 Pengaturan Email & Binance Listener[/]", title_align="left", border_style="cyan"))

        # --- Tampilkan Pengaturan dalam Tabel/Panel ---
        # Email Settings Panel
        email_table = Table.grid(padding=(0, 1))
        email_table.add_column("Setting", style="dim cyan", width=15)
        email_table.add_column("Value")
        email_table.add_row("Alamat Email", Text(settings['email_address'] or "[Belum diatur]", style="white" if settings['email_address'] else "dim red"))
        app_pass_display = f"*{'*' * (len(settings['app_password']) - 1)}" if settings['app_password'] else "[Belum diatur]"
        email_table.add_row("App Password", Text(app_pass_display, style="white" if settings['app_password'] else "dim red"))
        email_table.add_row("Server IMAP", Text(settings['imap_server'], style="white"))
        email_table.add_row("Interval Cek", Text(f"{settings['check_interval_seconds']} detik", style="white"))
        email_table.add_row("Keyword Target", Text(f"'{settings['target_keyword']}'", style="yellow"))
        email_table.add_row("Keyword Trigger", Text(f"'{settings['trigger_keyword']}'", style="magenta"))
        rprint(Panel(email_table, title="📧 Email Settings", border_style="blue", title_align="left", padding=1))

        # Binance Settings Panel
        binance_table = Table.grid(padding=(0, 1))
        binance_table.add_column("Setting", style="dim cyan", width=15)
        binance_table.add_column("Value")
        lib_status = "[bold green]Tersedia[/]" if BINANCE_AVAILABLE else "[bold red]Tidak Tersedia[/] [dim](Install 'python-binance')[/]"
        binance_table.add_row("Library Status", lib_status)
        api_key_display = f"{settings['binance_api_key'][:4]}...{settings['binance_api_key'][-4:]}" if len(settings['binance_api_key']) > 8 else ("[OK]" if settings['binance_api_key'] else "[Belum diatur]")
        api_secret_display = f"{settings['binance_api_secret'][:4]}...{settings['binance_api_secret'][-4:]}" if len(settings['binance_api_secret']) > 8 else ("[OK]" if settings['binance_api_secret'] else "[Belum diatur]")
        binance_table.add_row("API Key", Text(api_key_display, style="white" if settings['binance_api_key'] else "dim red"))
        binance_table.add_row("API Secret", Text(api_secret_display, style="white" if settings['binance_api_secret'] else "dim red"))
        binance_table.add_row("Trading Pair", Text(settings['trading_pair'] or "[Belum diatur]", style="white" if settings['trading_pair'] else "dim red"))
        binance_table.add_row("Buy Quote Qty", Text(f"{settings['buy_quote_quantity']:.2f} [dim](USDT dll)[/]", style="green" if settings['buy_quote_quantity'] > 0 else "red"))
        binance_table.add_row("Sell Base Qty", Text(f"{settings['sell_base_quantity']:.8f} [dim](BTC dll)[/]", style="green" if settings['sell_base_quantity'] >= 0 else "red"))
        exec_status = "[bold green]Aktif[/]" if settings['execute_binance_orders'] else "[bold red]Nonaktif[/]"
        binance_table.add_row("Eksekusi Order", exec_status)
        rprint(Panel(binance_table, title="💰 Binance Settings", border_style="yellow", title_align="left", padding=1))

        rprint(Rule(style="dim"))

        # --- Opsi Menu Pengaturan ---
        choice = None
        if INQUIRER_AVAILABLE:
             # Menggunakan Text dari Rich dalam choices inquirer
            choices = [
                (Text("✏️  Edit Pengaturan", style="yellow"), 'edit'),
                (Text("⬅️  Kembali ke Menu Utama", style="white"), 'back')
            ]
            questions = [
                inquirer.List('action',
                              message=Text("Pilih aksi", style="bold magenta"),
                              choices=choices,
                              carousel=True)
            ]
            try:
                # inquirer.prompt tidak secara native mendukung objek Text rich, jadi kita tampilkan plain text
                plain_choices = [(c[0].plain, c[1]) for c in choices]
                plain_questions = [
                    inquirer.List('action', message="Pilih aksi:", choices=plain_choices, carousel=True)
                ]
                # answers = inquirer.prompt(plain_questions, theme=GreenPassion())
                answers = inquirer.prompt(plain_questions) # Coba tanpa tema custom
                choice = answers['action'] if answers else 'back'
            except Exception as e:
                rprint(f"[red]Error menu interaktif: {e}[/]")
                choice = 'back'
            except KeyboardInterrupt:
                rprint(f"\n[yellow]Edit dibatalkan.[/]")
                choice = 'back'
                time.sleep(1)
        else: # Fallback
             rprint(Text("Pilih aksi:", style="bold magenta"))
             rprint("[yellow]E[/] - Edit Pengaturan")
             rprint("[white]K[/] - Kembali ke Menu Utama")
             choice_input = Prompt.ask("[bold magenta]Pilihan Anda (E/K)[/]", choices=['e', 'k', 'E', 'K'], default='k') if RICH_AVAILABLE else input("Pilih opsi (E/K): ").lower().strip()
             choice = 'edit' if choice_input.lower() == 'e' else 'back'


        # --- Proses Pilihan ---
        if choice == 'edit':
            rprint(Rule("[bold magenta]✏️ Edit Pengaturan[/]", style="magenta"))
            rprint("[dim](Kosongkan input untuk mempertahankan nilai saat ini)[/]")

            # --- Gunakan Rich Prompts jika tersedia ---
            if RICH_AVAILABLE:
                # Email
                rprint(Rule("Email", style="blue"))
                settings['email_address'] = Prompt.ask(" 1. Email", default=settings['email_address'] or "")
                settings['app_password'] = Prompt.ask(" 2. App Password", password=True, default=settings['app_password'] or "")
                settings['imap_server'] = Prompt.ask(" 3. Server IMAP", default=settings['imap_server'])
                settings['check_interval_seconds'] = IntPrompt.ask(" 4. Interval (detik) [min 5]", default=settings['check_interval_seconds'], choices=[str(i) for i in range(5, 301)]) # Batasi pilihan?
                settings['target_keyword'] = Prompt.ask(" 5. Keyword Target", default=settings['target_keyword'])
                settings['trigger_keyword'] = Prompt.ask(" 6. Keyword Trigger", default=settings['trigger_keyword'])

                # Binance
                rprint(Rule("Binance", style="yellow"))
                if not BINANCE_AVAILABLE: rprint("[yellow]   (Library Binance tidak terinstall)[/]")
                settings['binance_api_key'] = Prompt.ask(" 7. API Key", default=settings['binance_api_key'] or "")
                settings['binance_api_secret'] = Prompt.ask(" 8. API Secret", password=True, default=settings['binance_api_secret'] or "")
                settings['trading_pair'] = Prompt.ask(" 9. Trading Pair (e.g., BTCUSDT)", default=settings['trading_pair']).upper()
                settings['buy_quote_quantity'] = FloatPrompt.ask("10. Buy Quote Qty (> 0)", default=settings['buy_quote_quantity'])
                settings['sell_base_quantity'] = FloatPrompt.ask("11. Sell Base Qty (>= 0)", default=settings['sell_base_quantity'])
                if BINANCE_AVAILABLE:
                     settings['execute_binance_orders'] = Confirm.ask("12. Aktifkan Eksekusi Order Binance?", default=settings['execute_binance_orders'])
                else:
                     settings['execute_binance_orders'] = False # Paksa nonaktif jika lib tidak ada

            else: # Fallback Input Biasa
                 # ... (kode input biasa dari versi sebelumnya bisa dimasukkan di sini) ...
                 # Contoh Email:
                 new_val = input(f" 1. Email [{settings['email_address']}]: ").strip()
                 if new_val: settings['email_address'] = new_val
                 # ... (lanjutkan untuk semua setting) ...
                 # Contoh Binance Execute:
                 while True:
                     current_exec = settings['execute_binance_orders']
                     exec_prompt = "Aktif" if current_exec else "Nonaktif"
                     new_val_str = input(f"12. Eksekusi Order Binance? ({exec_prompt}) [y/n]: ").lower().strip()
                     if not new_val_str: break
                     if new_val_str == 'y': settings['execute_binance_orders'] = True; break
                     elif new_val_str == 'n': settings['execute_binance_orders'] = False; break
                     else: print("   [ERROR] Masukkan 'y' atau 'n'.")

            # Validasi setelah input (contoh)
            if settings['check_interval_seconds'] < 5: settings['check_interval_seconds'] = 5
            if settings['buy_quote_quantity'] <= 0: settings['buy_quote_quantity'] = DEFAULT_SETTINGS['buy_quote_quantity']; rprint("[yellow]Buy Qty direset ke default karena <= 0[/]")
            if settings['sell_base_quantity'] < 0: settings['sell_base_quantity'] = DEFAULT_SETTINGS['sell_base_quantity']; rprint("[yellow]Sell Qty direset ke default karena < 0[/]")


            save_settings(settings) # Simpan perubahan
            rprint(Panel("[bold green]✅ Pengaturan berhasil diperbarui![/]", border_style="green", expand=False))
            if RICH_AVAILABLE: Prompt.ask("[dim]Tekan Enter untuk kembali...[/]")
            else: input("Tekan Enter untuk kembali...")


        elif choice == 'back':
            break # Keluar dari loop pengaturan

# --- Fungsi Menu Utama (MODIFIED with Rich) ---
def main_menu():
    """Menampilkan menu utama aplikasi dengan tampilan Rich."""
    settings = load_settings()

    while True:
        clear_screen()
        # --- Header ---
        header_text = Text(" Exora AI - Email & Binance Listener ", style="bold magenta on white", justify="center")
        rprint(Panel(header_text, border_style="magenta", padding=(1, 0)))

        # --- Status Konfigurasi ---
        status_panels = []
        # Email Status
        email_text = Text()
        email_ok = bool(settings.get('email_address'))
        pass_ok = bool(settings.get('app_password'))
        email_text.append("📧 Email        : ", style="cyan")
        email_text.append(f"✅ OK" if email_ok else f"❌ Kosong", style="green" if email_ok else "red")
        email_text.append(" | ", style="dim")
        email_text.append("🔑 App Password : ", style="cyan")
        email_text.append(f"✅ OK" if pass_ok else f"❌ Kosong", style="green" if pass_ok else "red")
        status_panels.append(Panel(email_text, title="Email Status", border_style="blue", padding=(0,1)))

        # Binance Status
        if BINANCE_AVAILABLE:
            binance_text = Text()
            api_ok = bool(settings.get('binance_api_key'))
            secret_ok = bool(settings.get('binance_api_secret'))
            pair = settings.get('trading_pair')
            pair_ok = bool(pair)
            buy_qty = settings.get('buy_quote_quantity', 0)
            buy_ok = buy_qty > 0
            sell_qty = settings.get('sell_base_quantity', 0)
            sell_ok = sell_qty >= 0 # Boleh 0
            exec_active = settings.get("execute_binance_orders")

            binance_text.append("🔑 API/Secret : ", style="cyan")
            binance_text.append(f"✅ OK" if api_ok and secret_ok else f"❌ Perlu Diisi", style="green" if api_ok and secret_ok else "red")
            binance_text.append(" | ", style="dim")
            binance_text.append("⚖️ Pair        : ", style="cyan")
            binance_text.append(f"✅ {pair}" if pair_ok else f"❌ Kosong", style="green" if pair_ok else "red")
            binance_text.append("\n") # Baris baru
            binance_text.append("🛒 Buy Qty    : ", style="cyan")
            binance_text.append(f"✅ {buy_qty:.2f}" if buy_ok else f"❌ <= 0", style="green" if buy_ok else "red")
            binance_text.append(" | ", style="dim")
            binance_text.append("📉 Sell Qty   : ", style="cyan")
            binance_text.append(f"✅ {sell_qty:.8f}" if sell_ok else f"❌ < 0", style="green" if sell_ok else "red")
            binance_text.append(" | ", style="dim")
            binance_text.append("⚡ Eksekusi    : ", style="cyan")
            binance_text.append(f"✅ Aktif" if exec_active else f"🟡 Nonaktif", style="green" if exec_active else "yellow")
            status_panels.append(Panel(binance_text, title="Binance Status", border_style="yellow", padding=(0,1)))
        else:
             status_panels.append(Panel("[red]Binance tidak tersedia (Install [i]python-binance[/])[/]", title="Binance Status", border_style="red"))

        rprint(Columns(status_panels) if RICH_AVAILABLE else "\n".join([p.content if isinstance(p, Panel) else str(p) for p in status_panels])) # Tampilkan status
        rprint(Rule(style="dim"))

        # --- Pilihan Menu ---
        choice_key = None
        menu_title = Text("MENU UTAMA", style="bold magenta")

        if INQUIRER_AVAILABLE:
            # Definisikan pilihan untuk inquirer (pakai Text Rich)
            start_label = Text("▶️  1. Mulai Mendengarkan ")
            if settings.get("execute_binance_orders") and BINANCE_AVAILABLE:
                 start_label.append("(Email & Binance)", style="dim green")
            else:
                 start_label.append("(Email Only)", style="dim blue")

            choices = [
                (start_label, 'start'),
                (Text("🔧 2. Pengaturan", style="cyan"), 'settings'),
                (Text("🚪 3. Keluar", style="red"), 'exit')
            ]
            plain_choices = [(c[0].plain, c[1]) for c in choices] # Inquirer butuh string
            questions = [
                inquirer.List('main_choice',
                              message=menu_title.plain, # Message inquirer harus string
                              choices=plain_choices,
                              carousel=True)
            ]
            try:
                 answers = inquirer.prompt(questions) # Coba tanpa tema
                 choice_key = answers['main_choice'] if answers else 'exit'
            except Exception as e:
                 rprint(f"[red]Error menu interaktif: {e}[/]")
                 choice_key = 'exit'
            except KeyboardInterrupt:
                 rprint(f"\n[yellow]Keluar dari menu...[/]")
                 choice_key = 'exit'
                 time.sleep(1)
        else: # Fallback
             rprint(menu_title)
             rprint("[green]1.[/] Mulai Mendengarkan " + ("(Email & Binance)" if settings.get("execute_binance_orders") and BINANCE_AVAILABLE else "(Email Only)"))
             rprint("[cyan]2.[/] Pengaturan")
             rprint("[red]3.[/] Keluar")
             choice_input = Prompt.ask("[bold magenta]Masukkan pilihan (1/2/3)[/]", choices=['1', '2', '3'], default='3') if RICH_AVAILABLE else input("Pilihan (1/2/3): ").strip()
             if choice_input == '1': choice_key = 'start'
             elif choice_input == '2': choice_key = 'settings'
             elif choice_input == '3': choice_key = 'exit'
             else: choice_key = 'invalid'

        # --- Proses Pilihan ---
        if choice_key == 'start':
            rprint(Rule(style="dim green"))
            # Validasi (logika sama, pesan pakai rprint)
            valid_email = settings.get('email_address') and settings.get('app_password')
            execute_binance = settings.get("execute_binance_orders", False)
            valid_binance_config = False
            if execute_binance and BINANCE_AVAILABLE:
                 valid_binance_config = (
                     settings.get('binance_api_key') and
                     settings.get('binance_api_secret') and
                     settings.get('trading_pair') and
                     settings.get('buy_quote_quantity', 0) > 0 and
                     settings.get('sell_base_quantity', 0) >= 0
                 )

            error_messages = []
            if not valid_email: error_messages.append("[bold red]❌ Email/App Password belum lengkap![/]")
            if execute_binance and not BINANCE_AVAILABLE: error_messages.append("[bold red]❌ Eksekusi Binance aktif tapi library tidak ada![/]")
            if execute_binance and BINANCE_AVAILABLE and not valid_binance_config: error_messages.append("[bold red]❌ Konfigurasi Binance belum lengkap/valid untuk eksekusi![/]")

            if error_messages:
                rprint(Panel("\n".join(error_messages), title="[bold yellow]Tidak Bisa Memulai[/]", border_style="red", padding=1))
                rprint(f"[yellow]-> Silakan perbaiki via menu '[cyan]Pengaturan[/]'.[/]")
                if RICH_AVAILABLE: Prompt.ask("[dim]Tekan Enter untuk kembali...[/]")
                else: input("Tekan Enter...")
            else:
                clear_screen()
                mode = "Email & Binance Order" if execute_binance and BINANCE_AVAILABLE else "Email Listener Only"
                rprint(Panel(f"[bold green]🚀 Memulai Mode: {mode}[/]", expand=False, border_style="green"))
                start_listening(settings) # Mulai listener
                # Kembali ke menu utama setelah selesai
                rprint(f"\n[yellow]Kembali ke Menu Utama...[/]")
                time.sleep(2)


        elif choice_key == 'settings':
            show_settings(settings)
            settings = load_settings() # Load ulang jika ada perubahan

        elif choice_key == 'exit':
            rprint(f"\n[bold cyan]👋 Terima kasih! Sampai jumpa![/]")
            if RICH_AVAILABLE and console: console.show_cursor(True)
            sys.exit(0)

        elif choice_key == 'invalid': # Hanya untuk fallback input teks
            rprint(f"\n[bold red][ERROR] Pilihan tidak valid.[/]")
            time.sleep(1.5)


# --- Entry Point ---
if __name__ == "__main__":
    # Cek dependensi utama
    if not RICH_AVAILABLE and not INQUIRER_AVAILABLE:
         print("WARNING: 'rich' dan 'inquirer' tidak ditemukan. Tampilan akan sangat dasar.")
         print("         Disarankan install: pip install rich inquirer")
         time.sleep(3)
    elif not RICH_AVAILABLE:
        print("WARNING: 'rich' tidak ditemukan. Tampilan tidak akan maksimal.")
        print("         Install: pip install rich")
        time.sleep(2)
    elif not INQUIRER_AVAILABLE:
        # Sudah ada warning di atas, tidak perlu ulang
        pass

    # Jalankan menu utama
    try:
        main_menu()
    except KeyboardInterrupt:
        if RICH_AVAILABLE and console: console.show_cursor(True)
        rprint(f"\n[bold yellow][WARN] Program dihentikan paksa.[/]")
        sys.exit(1)
    except Exception as e:
        # Tangani error fatal
        clear_screen()
        rprint(Panel("[bold red on white] FATAL ERROR [/]", expand=False))
        rprint(f"[bold red]Terjadi error kritis yang tidak tertangani:[/]")
        if RICH_AVAILABLE and console: console.print_exception(show_locals=True, word_wrap=True) # Tampilkan traceback dengan Rich
        else: traceback.print_exc()
        rprint(f"\n[red]Pesan: {e}[/]")
        rprint("[yellow]Program akan keluar.[/]")
        if RICH_AVAILABLE: Prompt.ask("[dim]Tekan Enter untuk keluar...[/]")
        else: input("Tekan Enter...")
        if RICH_AVAILABLE and console: console.show_cursor(True)
        sys.exit(1)
