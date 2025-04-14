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

# --- Rich Integration --- RICH: Start
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.table import Table
    from rich.live import Live
    from rich.spinner import Spinner
    from rich.progress import track, Progress # track untuk loop sederhana, Progress untuk custom
    from rich.prompt import Prompt, Confirm # Untuk input yang lebih baik
    RICH_AVAILABLE = True
    console = Console() # Global console object
except ImportError:
    RICH_AVAILABLE = False
    # Fallback ke print biasa jika rich tidak ada
    class Console:
        def print(self, *args, **kwargs): print(*args)
        def rule(self, *args, **kwargs): print("-" * 40)
        def clear(self): os.system('cls' if os.name == 'nt' else 'clear')
        def status(self, *args, **kwargs): return DummyStatus()
        def input(self, *args, **kwargs): return input(*args)
        def print_exception(self, **kwargs): traceback.print_exc()
    class DummyStatus:
        def __enter__(self): pass
        def __exit__(self, *args): pass
    class Panel:
        def __init__(self, content, **kwargs): self.content = content
        def __rich_console__(self, console, options): yield self.content # Simple fallback
    class Text:
        def __init__(self, content, *args, **kwargs): self.content = content
        def __rich_console__(self, console, options): yield self.content # Simple fallback
    # Dummy Prompt/Confirm jika rich tidak ada
    class Prompt:
        @staticmethod
        def ask(*args, **kwargs):
            prompt_text = args[0] if args else ""
            default = kwargs.get('default', None)
            if default is not None:
                prompt_text += f" [{default}]"
            return input(prompt_text + ": ").strip()
    class Confirm:
         @staticmethod
         def ask(*args, **kwargs):
            prompt_text = args[0] if args else ""
            default = kwargs.get('default', False)
            prompt_text += f" [{'Y/n' if default else 'y/N'}]"
            while True:
                resp = input(prompt_text + ": ").lower().strip()
                if not resp: return default
                if resp == 'y': return True
                if resp == 'n': return False

    console = Console()
    print("\n!!! WARNING: Library 'rich' tidak ditemukan. Tampilan akan standar. !!!")
    print("!!!          Install dengan: pip install rich                      !!!\n")
# --- RICH: End

# --- Binance Integration ---
try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException, BinanceOrderException
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False
    # RICH: Gunakan console.print untuk konsistensi
    console.print("\n[bold yellow]!!! WARNING: Library 'python-binance' tidak ditemukan. !!!")
    console.print("[bold yellow]!!!          Fitur eksekusi order Binance tidak akan berfungsi. !!!")
    console.print("[bold yellow]!!!          Install dengan: pip install python-binance         !!!\n")
    # Definisikan exception dummy jika library tidak ada agar script tidak crash
    class BinanceAPIException(Exception): pass
    class BinanceOrderException(Exception): pass
    class Client: pass # Dummy class

# --- Konfigurasi & Variabel Global ---
CONFIG_FILE = "config.json"
DEFAULT_SETTINGS = {
    # Email Settings
    "email_address": "",
    "app_password": "",
    "imap_server": "imap.gmail.com",
    "check_interval_seconds": 10, # Default 10 detik
    "target_keyword": "Exora AI",
    "trigger_keyword": "order",
    # Binance Settings
    "binance_api_key": "",
    "binance_api_secret": "",
    "trading_pair": "BTCUSDT", # Contoh: BTCUSDT, ETHUSDT, dll.
    "buy_quote_quantity": 11.0, # Jumlah quote currency untuk dibeli (misal: 11 USDT)
    "sell_base_quantity": 0.0, # Jumlah base currency untuk dijual (misal: 0.0005 BTC) - default 0 agar aman
    "execute_binance_orders": False # Default: Jangan eksekusi order (safety)
}

# Variabel global untuk mengontrol loop utama
running = True

# --- Kode Warna ANSI (Tidak dipakai jika Rich tersedia) --- RICH: Dikomentari
# RESET = "\033[0m"
# BOLD = "\033[1m"
# RED = "\033[91m"
# GREEN = "\033[92m"
# YELLOW = "\033[93m"
# BLUE = "\033[94m"
# MAGENTA = "\033[95m"
# CYAN = "\033[96m"

# --- Fungsi Penanganan Sinyal (Ctrl+C) ---
def signal_handler(sig, frame):
    global running
    # RICH: Gunakan console.print dengan style
    console.print(f"\n[bold yellow][WARN][/] Ctrl+C terdeteksi. Menghentikan program...")
    running = False
    time.sleep(1) # Kurangi sleep agar lebih responsif
    console.print(f"[bold red][EXIT][/] Keluar dari program.")
    # RICH: Lakukan cleanup console jika perlu (biasanya tidak untuk exit langsung)
    console.show_cursor(True)
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# --- Fungsi Konfigurasi ---
def load_settings():
    """Memuat pengaturan dari file JSON, memastikan semua kunci ada."""
    settings = DEFAULT_SETTINGS.copy() # Mulai dengan default
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                # RICH: Tampilkan status saat loading
                with console.status(f"[cyan]Membaca konfigurasi '{CONFIG_FILE}'...", spinner="dots"):
                    loaded_settings = json.load(f)
                    time.sleep(0.5) # Sedikit jeda untuk efek loading
                settings.update(loaded_settings) # Timpa default dengan yg dari file

                # Validasi tambahan setelah load (RICH: gunakan console.print)
                if settings.get("check_interval_seconds", 10) < 5:
                    console.print(f"[yellow][WARN][/] Interval cek di '{CONFIG_FILE}' < 5 detik, direset ke 10.")
                    settings["check_interval_seconds"] = 10

                if not isinstance(settings.get("buy_quote_quantity"), (int, float)) or settings.get("buy_quote_quantity") <= 0:
                     console.print(f"[yellow][WARN][/] 'buy_quote_quantity' tidak valid, direset ke {DEFAULT_SETTINGS['buy_quote_quantity']}.")
                     settings["buy_quote_quantity"] = DEFAULT_SETTINGS['buy_quote_quantity']

                if not isinstance(settings.get("sell_base_quantity"), (int, float)) or settings.get("sell_base_quantity") < 0: # Allow 0
                     console.print(f"[yellow][WARN][/] 'sell_base_quantity' tidak valid, direset ke {DEFAULT_SETTINGS['sell_base_quantity']}.")
                     settings["sell_base_quantity"] = DEFAULT_SETTINGS['sell_base_quantity']

                if not isinstance(settings.get("execute_binance_orders"), bool):
                    console.print(f"[yellow][WARN][/] 'execute_binance_orders' tidak valid, direset ke False.")
                    settings["execute_binance_orders"] = False

                # Save back any corrections made
                save_settings(settings, silent=True) # Simpan tanpa notifikasi ulang

        except json.JSONDecodeError:
            console.print(f"[bold red][ERROR][/] File konfigurasi '{CONFIG_FILE}' rusak. Menggunakan default & menyimpan ulang.")
            save_settings(settings) # Simpan default yang bersih
        except Exception as e:
            console.print(f"[bold red][ERROR][/] Gagal memuat konfigurasi: {e}")
            # Tidak menyimpan ulang jika error tidak diketahui
    else:
        # Jika file tidak ada, simpan default awal
        console.print(f"[yellow][INFO][/] File konfigurasi '{CONFIG_FILE}' tidak ditemukan. Membuat dengan nilai default.")
        save_settings(settings)
    return settings


def save_settings(settings, silent=False): # RICH: Tambah argumen silent
    """Menyimpan pengaturan ke file JSON."""
    try:
        # Pastikan tipe data benar sebelum menyimpan
        settings['check_interval_seconds'] = int(settings.get('check_interval_seconds', 10))
        settings['buy_quote_quantity'] = float(settings.get('buy_quote_quantity', 11.0))
        settings['sell_base_quantity'] = float(settings.get('sell_base_quantity', 0.0))
        settings['execute_binance_orders'] = bool(settings.get('execute_binance_orders', False))

        with open(CONFIG_FILE, 'w') as f:
            # RICH: Status saat menyimpan
             with console.status(f"[cyan]Menyimpan konfigurasi ke '{CONFIG_FILE}'...", spinner="dots"):
                json.dump(settings, f, indent=4, sort_keys=True) # Urutkan kunci agar lebih rapi
                time.sleep(0.5) # Jeda untuk efek

        if not silent: # RICH: Cek flag silent
            console.print(f"[green][INFO][/] Pengaturan berhasil disimpan ke '[bold cyan]{CONFIG_FILE}[/]'")
    except Exception as e:
        console.print(f"[bold red][ERROR][/] Gagal menyimpan konfigurasi: {e}")

# --- Fungsi Utilitas ---
def clear_screen():
    # RICH: Gunakan console.clear()
    console.clear()

def decode_mime_words(s):
    # ... (fungsi decode_mime_words tetap sama, tidak ada output visual) ...
    if not s:
        return ""
    try:
        decoded_parts = decode_header(s)
        result = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                # Cobalah beberapa encoding umum jika None atau gagal
                if not encoding or encoding.lower() == 'unknown-8bit':
                    try:
                        result.append(part.decode('utf-8', errors='replace'))
                    except UnicodeDecodeError:
                        try:
                            result.append(part.decode('iso-8859-1', errors='replace'))
                        except UnicodeDecodeError:
                             result.append(part.decode('cp1252', errors='replace'))
                else:
                     result.append(part.decode(encoding, errors='replace'))
            else:
                result.append(part)
        return "".join(result)
    except Exception:
        # Fallback jika decode_header gagal
        return str(s)


def get_text_from_email(msg):
    # ... (fungsi get_text_from_email tetap sama, tapi pakai console.print untuk warning) ...
    text_content = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            # Periksa content type text/plain dan bukan attachment
            if content_type == "text/plain" and "attachment" not in content_disposition.lower():
                try:
                    charset = part.get_content_charset() or 'utf-8' # Default ke utf-8
                    payload = part.get_payload(decode=True)
                    text_content += payload.decode(charset, errors='replace') # Ganti error decode
                except Exception as e:
                    # RICH: Gunakan console.print untuk warning
                    console.print(f"[yellow][WARN][/] Tidak bisa mendekode bagian email (multipart): {e}")
            # Tambahkan: Coba ambil text/html jika text/plain tidak ada atau kosong
            elif "text/html" in content_type and not text_content and "attachment" not in content_disposition.lower():
                 try:
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    # Ini akan berisi tag HTML, mungkin perlu dibersihkan nanti jika perlu
                    # Untuk tujuan keyword matching, ini mungkin sudah cukup
                    text_content += payload.decode(charset, errors='replace')
                 except Exception as e:
                     console.print(f"[yellow][WARN][/] Tidak bisa mendekode bagian email (HTML): {e}")

    else: # Bukan multipart
        content_type = msg.get_content_type()
        if "text/plain" in content_type:
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                text_content = payload.decode(charset, errors='replace')
            except Exception as e:
                 # RICH: Gunakan console.print untuk warning
                 console.print(f"[yellow][WARN][/] Tidak bisa mendekode body email (plain): {e}")
        # Coba ambil html jika plain tidak ada
        elif "text/html" in content_type and not text_content:
             try:
                 charset = msg.get_content_charset() or 'utf-8'
                 payload = msg.get_payload(decode=True)
                 text_content = payload.decode(charset, errors='replace') # Mengandung HTML
             except Exception as e:
                  console.print(f"[yellow][WARN][/] Tidak bisa mendekode body email (HTML): {e}")

    return text_content.lower() # Kembalikan dalam lowercase untuk matching

# --- Fungsi Beep ---
def trigger_beep(action):
    # ... (fungsi trigger_beep tetap sama, tapi pakai console.print) ...
    try:
        style = "bold magenta"
        if action == "buy":
            console.print(f"[{style}][ACTION][/] Memicu BEEP untuk '[bold green]BUY[/]'")
            # Pertimbangkan async jika beep lama, tapi untuk beep pendek biasanya tidak masalah
            subprocess.run(["beep", "-f", "1000", "-l", "300", "-D", "50", "-r", "2"], check=True, capture_output=True, text=True) # Lebih pendek
        elif action == "sell":
            console.print(f"[{style}][ACTION][/] Memicu BEEP untuk '[bold red]SELL[/]'")
            subprocess.run(["beep", "-f", "700", "-l", "500", "-D", "50", "-r", "1"], check=True, capture_output=True, text=True) # Lebih pendek
        else:
             console.print(f"[yellow][WARN][/] Aksi beep tidak dikenal '{action}'.")
    except FileNotFoundError:
        console.print(f"[yellow][WARN][/] Perintah 'beep' tidak ditemukan. Beep dilewati.")
    except subprocess.CalledProcessError as e:
        console.print(f"[red][ERROR][/] Gagal menjalankan 'beep': {e}")
        if e.stderr: console.print(f"[red]         Stderr: {e.stderr.strip()}[/]")
    except Exception as e:
        console.print(f"[red][ERROR][/] Kesalahan tak terduga saat beep: {e}")

# --- Fungsi Eksekusi Binance ---
def get_binance_client(settings):
    """Membuat instance Binance client."""
    if not BINANCE_AVAILABLE:
        console.print(f"[red][ERROR][/] Library python-binance tidak terinstall. Tidak bisa membuat client.")
        return None
    if not settings.get('binance_api_key') or not settings.get('binance_api_secret'):
        console.print(f"[red][ERROR][/] API Key atau Secret Key Binance belum diatur di konfigurasi.")
        return None
    try:
        # RICH: Gunakan status saat mencoba koneksi
        with console.status("[cyan]Menghubungkan ke Binance API...", spinner="earth"):
            client = Client(settings['binance_api_key'], settings['binance_api_secret'])
            # Test koneksi (opsional tapi bagus)
            client.ping()
            time.sleep(0.5) # Jeda untuk efek
        console.print(f"[green][BINANCE][/] Koneksi ke Binance API berhasil.")
        return client
    except BinanceAPIException as e:
        console.print(f"[bold red][BINANCE ERROR][/] Gagal terhubung/autentikasi ke Binance: {e}")
        return None
    except Exception as e:
        console.print(f"[bold red][ERROR][/] Gagal membuat Binance client: {e}")
        return None

def execute_binance_order(client, settings, side):
    """Mengeksekusi order MARKET BUY atau SELL di Binance."""
    if not client:
        console.print(f"[red][BINANCE][/] Eksekusi dibatalkan, client tidak valid.")
        return False
    if not settings.get("execute_binance_orders", False):
        console.print(f"[yellow][BINANCE][/] Eksekusi order dinonaktifkan di pengaturan ('execute_binance_orders': false). Order dilewati.")
        return False # Dianggap tidak gagal, hanya dilewati

    pair = settings.get('trading_pair', '').upper()
    if not pair:
        console.print(f"[red][BINANCE ERROR][/] Trading pair belum diatur di konfigurasi.")
        return False

    order_details = {}
    action_desc = ""
    side_str = "UNKNOWN"

    try:
        if side == Client.SIDE_BUY:
            side_str = "[bold green]BUY[/]"
            quote_qty = settings.get('buy_quote_quantity', 0.0)
            if quote_qty <= 0:
                 console.print(f"[red][BINANCE ERROR][/] Kuantitas Beli (buy_quote_quantity) harus > 0.")
                 return False
            order_details = {
                'symbol': pair,
                'side': Client.SIDE_BUY,
                'type': Client.ORDER_TYPE_MARKET,
                'quoteOrderQty': quote_qty
            }
            action_desc = f"MARKET BUY [cyan]{quote_qty:.4f}[/] (quote) of [bold yellow]{pair}[/]"

        elif side == Client.SIDE_SELL:
            side_str = "[bold red]SELL[/]"
            base_qty = settings.get('sell_base_quantity', 0.0)
            if base_qty <= 0:
                 console.print(f"[red][BINANCE ERROR][/] Kuantitas Jual (sell_base_quantity) harus > 0.")
                 return False
            order_details = {
                'symbol': pair,
                'side': Client.SIDE_SELL,
                'type': Client.ORDER_TYPE_MARKET,
                'quantity': base_qty # Jual sejumlah base asset
            }
            action_desc = f"MARKET SELL [cyan]{base_qty:.8f}[/] (base) of [bold yellow]{pair}[/]" # Sesuaikan presisi
        else:
            console.print(f"[red][BINANCE ERROR][/] Sisi order tidak valid: {side}")
            return False

        console.print(f"[magenta][BINANCE][/] Mencoba eksekusi: {action_desc}...")
        # RICH: Gunakan status saat order sedang diproses
        with console.status(f"[cyan]Mengirim order {side_str} ke Binance...", spinner="arrow3"):
            order_result = client.create_order(**order_details)
            time.sleep(0.5) # Jeda efek

        console.print(f"[bold green][BINANCE SUCCESS][/] Order berhasil dieksekusi!")

        # RICH: Tampilkan hasil dalam tabel agar rapi
        result_table = Table(show_header=False, box=None, padding=(0, 2))
        result_table.add_column(style="dim")
        result_table.add_column()
        result_table.add_row("Order ID", f"[cyan]{order_result.get('orderId')}[/]")
        result_table.add_row("Symbol", f"[yellow]{order_result.get('symbol')}[/]")
        result_table.add_row("Side", side_str)
        result_table.add_row("Status", f"[green]{order_result.get('status')}[/]")

        # Info fill (harga rata-rata dan kuantitas terisi)
        if order_result.get('fills'):
            total_qty = sum(float(f['qty']) for f in order_result['fills'])
            total_quote_qty = sum(float(f['qty']) * float(f['price']) for f in order_result['fills'])
            avg_price = total_quote_qty / total_qty if total_qty else 0
            result_table.add_row("Avg Price", f"{avg_price:.8f}") # Sesuaikan presisi jika perlu
            result_table.add_row("Filled Qty", f"{total_qty:.8f}")

        console.print(result_table)
        return True

    except BinanceAPIException as e:
        console.print(f"[bold red][BINANCE API ERROR][/] Gagal eksekusi order: {e.status_code} - {e.message}")
        # Contoh error spesifik:
        if e.code == -2010: console.print(f"[red]         -> Kemungkinan saldo tidak cukup.[/]")
        elif e.code == -1121: console.print(f"[red]         -> Trading pair '{pair}' tidak valid.[/]")
        elif e.code == -1013 or 'MIN_NOTIONAL' in e.message: console.print(f"[red]         -> Order size terlalu kecil (cek minimum order/MIN_NOTIONAL atau LOT_SIZE).[/]")
        return False
    except BinanceOrderException as e:
        console.print(f"[bold red][BINANCE ORDER ERROR][/] Gagal eksekusi order: {e.status_code} - {e.message}")
        return False
    except Exception as e:
        console.print(f"[bold red][ERROR][/] Kesalahan tak terduga saat eksekusi order Binance:")
        # RICH: Gunakan console.print_exception untuk traceback yang rapi
        console.print_exception(show_locals=False) # show_locals=True bisa sangat verbose
        return False

# --- Fungsi Pemrosesan Email ---
def process_email(mail, email_id, settings, binance_client): # Tambah binance_client
    """Mengambil, mem-parsing, dan memproses satu email, lalu eksekusi order jika sesuai."""
    global running
    if not running: return

    target_keyword_lower = settings['target_keyword'].lower()
    trigger_keyword_lower = settings['trigger_keyword'].lower()
    email_id_str = email_id.decode('utf-8')

    try:
        # RICH: Status saat fetch email
        with console.status(f"[cyan]Mengambil email ID {email_id_str}...", spinner="simpleDots"):
            status, data = mail.fetch(email_id, "(RFC822)")
            time.sleep(0.1) # Jeda kecil

        if status != 'OK':
            console.print(f"[red][ERROR][/] Gagal mengambil email ID {email_id_str}: {status}")
            return

        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        subject = decode_mime_words(msg["Subject"])
        sender = decode_mime_words(msg["From"])
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # RICH: Gunakan Panel untuk menampilkan detail email
        email_content = Table(show_header=False, box=None, padding=(0, 1))
        email_content.add_column(style="dim cyan")
        email_content.add_column()
        email_content.add_row("ID", email_id_str)
        email_content.add_row("Dari", sender)
        email_content.add_row("Subjek", subject)

        console.print(Panel(email_content, title=f"Email Diterima ({timestamp})", border_style="blue", expand=False))

        # RICH: Status saat parsing body
        with console.status(f"[cyan]Memproses body email {email_id_str}...", spinner="simpleDotsScrolling"):
             body = get_text_from_email(msg)
             time.sleep(0.2)
        full_content = (subject.lower() + " " + body)

        if target_keyword_lower in full_content:
            console.print(f"[green][INFO][/] Keyword target '[bold]{settings['target_keyword']}[/]' ditemukan.")
            try:
                # Cari trigger SETELAH target
                target_index = full_content.find(target_keyword_lower)
                trigger_index = -1
                if target_index != -1:
                    # Cari trigger setelah target ditemukan
                     trigger_index = full_content.find(trigger_keyword_lower, target_index + len(target_keyword_lower))

                if trigger_index != -1:
                    start_word_index = trigger_index + len(trigger_keyword_lower)
                    text_after_trigger = full_content[start_word_index:].lstrip()
                    words_after_trigger = text_after_trigger.split(maxsplit=1)

                    if words_after_trigger:
                        action_word = words_after_trigger[0].strip('.,!?:;()[]{}').lower()
                        action_style = "[bold green]" if action_word == "buy" else "[bold red]" if action_word == "sell" else "[bold yellow]"
                        console.print(f"[green][INFO][/] Keyword trigger '[bold]{settings['trigger_keyword']}[/]' ditemukan. Kata berikutnya: {action_style}{action_word.upper()}[/]")

                        # --- Trigger Aksi (Beep dan/atau Binance) ---
                        order_executed = False # Tandai apakah order sudah dicoba
                        if action_word == "buy":
                            trigger_beep("buy")
                            # Coba eksekusi Binance BUY
                            if binance_client and settings.get("execute_binance_orders"):
                               execute_binance_order(binance_client, settings, Client.SIDE_BUY)
                               order_executed = True
                            elif settings.get("execute_binance_orders") and not binance_client:
                                console.print(f"[yellow][WARN][/] Eksekusi Binance aktif tapi client tidak valid/tersedia.")

                        elif action_word == "sell":
                            trigger_beep("sell")
                            # Coba eksekusi Binance SELL
                            if binance_client and settings.get("execute_binance_orders"):
                               execute_binance_order(binance_client, settings, Client.SIDE_SELL)
                               order_executed = True
                            elif settings.get("execute_binance_orders") and not binance_client:
                               console.print(f"[yellow][WARN][/] Eksekusi Binance aktif tapi client tidak valid/tersedia.")
                        else:
                            console.print(f"[yellow][WARN][/] Kata setelah '[bold]{settings['trigger_keyword']}[/]' ({action_style}{action_word.upper()}[/]) bukan 'buy' atau 'sell'. Tidak ada aksi market.")

                        # RICH: Pesan jika eksekusi aktif tapi tidak jalan karena error sebelumnya
                        if not order_executed and settings.get("execute_binance_orders") and action_word in ["buy", "sell"] and binance_client:
                             console.print(f"[yellow][BINANCE][/] Eksekusi tidak dilakukan (lihat pesan error di atas).")


                    else:
                        console.print(f"[yellow][WARN][/] Tidak ada kata yang terbaca setelah '[bold]{settings['trigger_keyword']}[/]'.")

                else: # trigger_index == -1
                    console.print(f"[yellow][WARN][/] Keyword trigger '[bold]{settings['trigger_keyword']}[/]' tidak ditemukan [bold]setelah[/] '[bold]{settings['target_keyword']}[/]'.")

            except Exception as e:
                 console.print(f"[red][ERROR][/] Gagal parsing kata setelah trigger: {e}")
        else:
            console.print(f"[blue][INFO][/] Keyword target '[bold]{settings['target_keyword']}[/]' tidak ditemukan dalam email ini.")

        # Tandai email sebagai sudah dibaca ('Seen')
        try:
            # RICH: Status saat marking email
            with console.status(f"[dim]Menandai email {email_id_str} sebagai 'Seen'...", spinner="point"):
                mail.store(email_id, '+FLAGS', '\\Seen')
                time.sleep(0.1)
            # console.print(f"[dim blue][INFO] Menandai email {email_id_str} sebagai sudah dibaca.[/dim blue]") # Optional: bisa di-disable agar tidak terlalu verbose
        except Exception as e:
            console.print(f"[red][ERROR][/] Gagal menandai email {email_id_str} sebagai 'Seen': {e}")
        # RICH: Garis pemisah antar email
        console.rule(style="dim blue")

    except Exception as e:
        console.print(f"[bold red][ERROR] Gagal memproses email ID {email_id_str}:[/]")
        console.print_exception(show_locals=False)

# --- Fungsi Listening Utama ---
def start_listening(settings):
    """Memulai loop untuk memeriksa email baru dan menyiapkan client Binance."""
    global running
    running = True
    mail = None
    binance_client = None # Inisialisasi client Binance
    wait_time = 30 # Waktu tunggu sebelum reconnect
    connection_attempts = 0
    max_conn_attempts = 3 # Batasi percobaan koneksi berturut-turut

    # RICH: Helper untuk status panel
    def generate_status_panel(status_text, email_count=0, last_check_ts=None):
        status_color = "cyan"
        if "Gagal" in status_text or "Error" in status_text or "Terputus" in status_text:
            status_color = "yellow"
        elif "Mendengarkan" in status_text:
            status_color = "green"

        table = Table.grid(padding=(0, 1), expand=True)
        table.add_column(justify="left", ratio=1)
        table.add_column(justify="right", style="dim")

        status_line = f"Status: [{status_color}]{status_text}[/]"
        time_line = f"Email Diproses: {email_count} | Cek Terakhir: {last_check_ts if last_check_ts else '-'}"
        table.add_row(status_line, time_line)
        return Panel(table, border_style="dim", title="Listener Status")

    # --- Setup Binance Client di Awal (jika diaktifkan) ---
    if settings.get("execute_binance_orders"):
        if not BINANCE_AVAILABLE:
             console.print(f"[bold red][FATAL][/] Eksekusi Binance diaktifkan tapi library python-binance tidak ada! Nonaktifkan atau install library.")
             running = False # Hentikan sebelum loop utama
             return
        console.print(Panel("[cyan]Mencoba menginisialisasi koneksi Binance API...[/]", border_style="cyan"))
        binance_client = get_binance_client(settings)
        if not binance_client:
            console.print(f"[bold red][FATAL][/] Gagal menginisialisasi Binance Client. Periksa API Key/Secret dan koneksi.")
            console.print(f"[yellow]         Eksekusi order tidak akan berjalan. Anda bisa menonaktifkannya di Pengaturan.[/]")
            # Kita tidak menghentikan program, mungkin user hanya ingin notifikasi email
            # running = False
            # return
        else:
            console.print(Panel("[green]Binance Client siap.[/]", border_style="green"))
    else:
        console.print(Panel("[yellow]Eksekusi order Binance dinonaktifkan ('execute_binance_orders': false).[/]", border_style="yellow"))

    # --- RICH: Gunakan Live untuk status bar dan progress ---
    processed_email_count = 0
    last_check_timestamp = None
    current_status_text = "Inisialisasi..."

    with Live(generate_status_panel(current_status_text), refresh_per_second=4, console=console, vertical_overflow="visible") as live:
        while running:
            try:
                # --- Koneksi IMAP ---
                if not mail or mail.state != 'SELECTED':
                    connection_attempts += 1
                    if connection_attempts > max_conn_attempts:
                         console.print(f"[bold red][FATAL][/] Gagal terhubung ke IMAP setelah {max_conn_attempts} percobaan. Periksa detail & koneksi.")
                         running = False
                         break

                    current_status_text = f"Menghubungkan ke IMAP ({settings['imap_server']})... ({connection_attempts}/{max_conn_attempts})"
                    live.update(generate_status_panel(current_status_text, processed_email_count, last_check_timestamp))
                    mail = imaplib.IMAP4_SSL(settings['imap_server'], timeout=30) # Tambah timeout
                    # console.print(f"[green][SYS][/] Terhubung ke {settings['imap_server']}") # Log jika perlu

                    current_status_text = f"Login sebagai {settings['email_address']}..."
                    live.update(generate_status_panel(current_status_text, processed_email_count, last_check_timestamp))
                    mail.login(settings['email_address'], settings['app_password'])
                    # console.print(f"[green][SYS][/] Login email berhasil sebagai [bold]{settings['email_address']}[/]") # Log jika perlu

                    mail.select("inbox")
                    current_status_text = "Memulai mode mendengarkan di INBOX..."
                    live.update(generate_status_panel(current_status_text, processed_email_count, last_check_timestamp))
                    console.print(Panel(f"Mendengarkan email untuk [bold cyan]{settings['email_address']}[/] di INBOX", style="bold green", title="Listener Aktif"))
                    console.rule(style="green")
                    connection_attempts = 0 # Reset counter jika berhasil

                # --- Loop Cek Email ---
                while running:
                    try:
                        # Cek koneksi IMAP
                        with console.status("[dim]Cek koneksi IMAP...", spinner="point"):
                            status, _ = mail.noop()
                            time.sleep(0.2)
                        if status != 'OK':
                            current_status_text = f"Koneksi IMAP NOOP gagal ({status}). Reconnect..."
                            live.update(generate_status_panel(current_status_text, processed_email_count, last_check_timestamp))
                            console.print(f"[yellow][WARN][/] Koneksi IMAP NOOP gagal ({status}). Mencoba reconnect...")
                            break # Keluar loop inner untuk reconnect
                    except Exception as NopErr:
                         current_status_text = f"Koneksi IMAP terputus ({type(NopErr).__name__}). Reconnect..."
                         live.update(generate_status_panel(current_status_text, processed_email_count, last_check_timestamp))
                         console.print(f"[yellow][WARN][/] Koneksi IMAP terputus ({NopErr}). Mencoba reconnect...")
                         break

                    # Cek koneksi Binance jika client ada
                    if binance_client and settings.get("execute_binance_orders"):
                        try:
                             with console.status("[dim]Cek koneksi Binance...", spinner="point"):
                                 binance_client.ping()
                                 time.sleep(0.2)
                        except Exception as PingErr:
                             console.print(f"[yellow][WARN][/] Ping ke Binance API gagal ({PingErr}). Mencoba membuat ulang client...")
                             binance_client = get_binance_client(settings) # Coba buat ulang
                             if not binance_client:
                                  console.print(f"[red]       Gagal membuat ulang Binance client. Eksekusi mungkin gagal.[/]")
                                  # Tidak break, biarkan email tetap jalan jika bisa
                             time.sleep(5) # Beri jeda setelah error ping

                    # Cari email UNSEEN
                    current_status_text = "Mencari email baru (UNSEEN)..."
                    live.update(generate_status_panel(current_status_text, processed_email_count, last_check_timestamp))
                    status, messages = mail.search(None, '(UNSEEN)')
                    last_check_timestamp = datetime.datetime.now().strftime("%H:%M:%S")

                    if status != 'OK':
                         current_status_text = f"Gagal mencari email ({status}). Reconnect..."
                         live.update(generate_status_panel(current_status_text, processed_email_count, last_check_timestamp))
                         console.print(f"[red][ERROR][/] Gagal mencari email: {status}")
                         break

                    email_ids = messages[0].split()
                    if email_ids:
                        console.print(f"\n[bold green][INFO][/] Menemukan {len(email_ids)} email baru!")
                        console.rule(style="green")
                        for email_id in email_ids:
                            if not running: break
                            # Kirim client Binance ke process_email
                            process_email(mail, email_id, settings, binance_client)
                            processed_email_count += 1
                        if not running: break
                        # console.rule(style="green") # Pindah rule ke akhir process_email
                        current_status_text = f"Selesai proses {len(email_ids)} email. Mendengarkan..."
                        live.update(generate_status_panel(current_status_text, processed_email_count, last_check_timestamp))
                        console.print(f"[green][INFO][/] Selesai memproses. Kembali mendengarkan...")
                    else:
                        # Tidak ada email baru, tunggu interval
                        wait_interval = settings['check_interval_seconds']
                        current_status_text = f"Tidak ada email baru. Menunggu {wait_interval} detik..."
                        # RICH: Gunakan Progress bar untuk animasi menunggu
                        with Progress(
                            "[progress.description]{task.description}",
                            Spinner("dots", style="cyan"),
                            "[progress.percentage]{task.percentage:>3.0f}%",
                            console=console, # Targetkan progress ke console yang sama
                            transient=True # Hapus progress bar setelah selesai
                        ) as progress:
                            wait_task = progress.add_task("[cyan]Menunggu...", total=wait_interval)
                            for _ in range(wait_interval):
                                if not running: break
                                progress.update(wait_task, advance=1)
                                live.update(generate_status_panel(f"Mendengarkan... ({wait_interval - progress.tasks[0].completed}/{wait_interval}s)", processed_email_count, last_check_timestamp))
                                time.sleep(1)
                        if not running: break
                        # Update status setelah selesai menunggu
                        current_status_text = "Mendengarkan..."
                        live.update(generate_status_panel(current_status_text, processed_email_count, last_check_timestamp))

                # Tutup koneksi IMAP jika keluar loop inner (untuk reconnect)
                if mail and mail.state == 'SELECTED':
                    try:
                        with console.status("[dim]Menutup koneksi IMAP...", spinner="point"):
                           mail.close()
                           time.sleep(0.2)
                    except Exception: pass
                if mail and mail.state == 'AUTH':
                    try:
                        with console.status("[dim]Logout dari IMAP...", spinner="point"):
                            mail.logout()
                            time.sleep(0.2)
                    except Exception: pass
                mail = None # Set None agar reconnect di loop luar

            except (imaplib.IMAP4.error, imaplib.IMAP4.abort) as e:
                console.print(f"[bold red][ERROR][/] Kesalahan IMAP: {e}")
                current_status_text = f"Kesalahan IMAP ({type(e).__name__}). Reconnect..."
                if "authentication failed" in str(e).lower() or "invalid credentials" in str(e).lower():
                    console.print(f"[bold red][FATAL][/] Login Email GAGAL! Periksa alamat email dan App Password.")
                    running = False # Hentikan loop utama
                    break # Keluar dari loop utama
                # Coba reconnect setelah jeda
                # (Handling reconnect sudah ada di awal loop while)
            except (ConnectionError, OSError, socket.error, socket.gaierror) as e:
                 console.print(f"[bold red][ERROR][/] Kesalahan Koneksi: {e}")
                 current_status_text = f"Kesalahan Koneksi ({type(e).__name__}). Reconnect..."
                 console.print(f"[yellow][WARN][/] Periksa koneksi internet.")
                 # Coba reconnect setelah jeda
            except Exception as e:
                console.print(f"[bold red][ERROR][/] Kesalahan tak terduga di loop utama:")
                console.print_exception(show_locals=False)
                current_status_text = f"Kesalahan Tak Terduga ({type(e).__name__}). Reconnect..."
                # Coba reconnect setelah jeda
            finally:
                # Pastikan mail di-logout jika masih ada state aneh
                if mail and mail.state != 'LOGOUT':
                    try: mail.logout()
                    except Exception: pass
                mail = None # Set None untuk trigger reconnect

                if running:
                    # RICH: Jeda sebelum retry dengan status
                    wait_msg = f"Mencoba lagi dalam {wait_time} detik..."
                    live.update(generate_status_panel(f"{current_status_text} {wait_msg}", processed_email_count, last_check_timestamp))
                    with Progress("[progress.description]{task.description}", Spinner("circle", style="yellow"), console=console, transient=True) as progress:
                         wait_task = progress.add_task(f"[yellow]{wait_msg}", total=wait_time)
                         for _ in range(wait_time):
                             if not running: break
                             progress.update(wait_task, advance=1)
                             time.sleep(1)


    console.print(Panel("[yellow]Mode mendengarkan dihentikan.[/]", border_style="yellow"))


# --- Fungsi Menu Pengaturan ---
def show_settings(settings):
    """Menampilkan dan mengedit pengaturan, termasuk Binance."""
    while True:
        clear_screen()
        console.print(Panel(Text("Pengaturan Email & Binance Listener", justify="center", style="bold cyan"), border_style="cyan", title="⚙️ Pengaturan"))

        # RICH: Gunakan Tabel untuk menampilkan settings
        settings_table = Table(title="Pengaturan Saat Ini", border_style="blue", show_header=False, box=None)
        settings_table.add_column("Item", style="dim cyan", width=20)
        settings_table.add_column("Nilai", style="white")

        # --- Email Settings ---
        settings_table.add_row("[bold]--- Email ---[/]", "")
        settings_table.add_row("1. Alamat Email", settings['email_address'] or "[italic grey50]Belum diatur[/]")
        settings_table.add_row("2. App Password", ('*' * len(settings['app_password'])) if settings['app_password'] else "[italic grey50]Belum diatur[/]") # Sembunyikan password
        settings_table.add_row("3. Server IMAP", settings['imap_server'])
        settings_table.add_row("4. Interval Cek", f"{settings['check_interval_seconds']} detik")
        settings_table.add_row("5. Keyword Target", f"'{settings['target_keyword']}'")
        settings_table.add_row("6. Keyword Trigger", f"'{settings['trigger_keyword']}'")

        # --- Binance Settings ---
        settings_table.add_row("", "") # Spacer
        settings_table.add_row("[bold]--- Binance ---[/]", "")
        binance_status = f"[green]Tersedia[/]" if BINANCE_AVAILABLE else f"[red]Tidak Tersedia (Install 'python-binance')[/]"
        settings_table.add_row("Library Status", binance_status)
        settings_table.add_row("7. API Key", settings['binance_api_key'] or "[italic grey50]Belum diatur[/]")
        settings_table.add_row("8. API Secret", ('*' * len(settings['binance_api_secret'])) if settings['binance_api_secret'] else "[italic grey50]Belum diatur[/]") # Sembunyikan secret
        settings_table.add_row("9. Trading Pair", settings['trading_pair'] or "[italic grey50]Belum diatur[/]")
        settings_table.add_row("10. Buy Quote Qty", f"{settings['buy_quote_quantity']} (e.g., USDT)")
        settings_table.add_row("11. Sell Base Qty", f"{settings['sell_base_quantity']} (e.g., BTC)")
        exec_status = f"[bold green]Aktif[/]" if settings['execute_binance_orders'] else f"[bold red]Nonaktif[/]"
        settings_table.add_row("12. Eksekusi Order", exec_status)

        console.print(settings_table)
        console.rule()

        # RICH: Gunakan Prompt untuk input
        console.print("Opsi:")
        console.print(" [bold yellow]E[/] - Edit Pengaturan")
        console.print(" [bold yellow]K[/] - Kembali ke Menu Utama")
        console.rule()
        choice = Prompt.ask("Pilih opsi", choices=["E", "K"], default="K").lower()

        if choice == 'e':
            console.print(Panel(Text("Edit Pengaturan", justify="center", style="bold magenta"), border_style="magenta"))

            # RICH: Gunakan Prompt.ask untuk input yang lebih terstruktur
            # --- Edit Email ---
            console.print("[bold cyan]--- Email ---[/]")
            settings['email_address'] = Prompt.ask(" 1. Email", default=settings['email_address'])
            # Gunakan password=True untuk menyembunyikan input password
            new_password = Prompt.ask(" 2. App Password (biarkan kosong jika tidak berubah)", default="", password=True)
            if new_password: settings['app_password'] = new_password
            settings['imap_server'] = Prompt.ask(" 3. Server IMAP", default=settings['imap_server'])
            while True:
                try:
                    interval_str = Prompt.ask(f" 4. Interval (detik, min 5)", default=str(settings['check_interval_seconds']))
                    new_interval = int(interval_str)
                    if new_interval >= 5: settings['check_interval_seconds'] = new_interval; break
                    else: console.print(f"   [red]Interval minimal 5 detik.[/]")
                except ValueError: console.print(f"   [red]Masukkan angka.[/]")
            settings['target_keyword'] = Prompt.ask(" 5. Keyword Target", default=settings['target_keyword'])
            settings['trigger_keyword'] = Prompt.ask(" 6. Keyword Trigger", default=settings['trigger_keyword'])

            # --- Edit Binance ---
            console.print("\n[bold cyan]--- Binance ---[/]")
            if not BINANCE_AVAILABLE:
                 console.print(f"[yellow]   (Library Binance tidak terinstall, pengaturan Binance mungkin tidak berpengaruh)[/]")

            settings['binance_api_key'] = Prompt.ask(" 7. API Key", default=settings['binance_api_key'])
            new_secret = Prompt.ask(" 8. API Secret (biarkan kosong jika tidak berubah)", default="", password=True)
            if new_secret: settings['binance_api_secret'] = new_secret
            settings['trading_pair'] = Prompt.ask(" 9. Trading Pair (e.g., BTCUSDT)", default=settings['trading_pair']).upper()

            while True:
                 try:
                     qty_str = Prompt.ask(f"10. Buy Quote Qty (e.g., 11.0 USDT, > 0)", default=str(settings['buy_quote_quantity']))
                     new_qty = float(qty_str)
                     if new_qty > 0: settings['buy_quote_quantity'] = new_qty; break
                     else: console.print(f"   [red]Kuantitas Beli harus > 0.[/]")
                 except ValueError: console.print(f"   [red]Masukkan angka desimal (e.g., 11.0).[/]")
            while True:
                 try:
                     qty_str = Prompt.ask(f"11. Sell Base Qty (e.g., 0.0005 BTC, >= 0)", default=str(settings['sell_base_quantity']))
                     new_qty = float(qty_str)
                     if new_qty >= 0: settings['sell_base_quantity'] = new_qty; break
                     else: console.print(f"   [red]Kuantitas Jual harus >= 0.[/]")
                 except ValueError: console.print(f"   [red]Masukkan angka desimal (e.g., 0.0005).[/]")

            # RICH: Gunakan Confirm untuk Y/N
            settings['execute_binance_orders'] = Confirm.ask(f"12. Eksekusi Order Binance?", default=settings['execute_binance_orders'])


            save_settings(settings)
            console.print("\n[green]Pengaturan diperbarui. Tekan Enter untuk kembali...[/]")
            input() # Jeda sederhana

        elif choice == 'k':
            break # Keluar dari loop pengaturan

# --- Fungsi Menu Utama ---
def main_menu():
    """Menampilkan menu utama aplikasi."""
    settings = load_settings() # Load di awal

    while True:
        clear_screen()
        # RICH: Panel utama untuk menu
        console.print(Panel(
            Text("Exora AI - Email & Binance Listener", justify="center", style="bold magenta"),
            border_style="bold magenta",
            title="🚀 Selamat Datang! 🚀",
            padding=(1, 2)
        ))

        # RICH: Gunakan Tabel untuk opsi menu
        menu_table = Table.grid(padding=(1, 2), expand=True)
        menu_table.add_column(style="green", justify="right", width=3)
        menu_table.add_column()

        exec_label = f" & [bold cyan]Binance[/]" if settings.get("execute_binance_orders") else ""
        menu_table.add_row("1.", f"Mulai Mendengarkan (Email{exec_label})")
        menu_table.add_row("[cyan]2.[/]", "Pengaturan")
        menu_table.add_row("[yellow]3.[/]", "Keluar")
        console.print(menu_table)
        console.rule(style="magenta")

        # RICH: Tampilkan status konfigurasi dalam tabel
        status_table = Table.grid(padding=(0,1), expand=True)
        status_table.add_column(style="dim", width=15)
        status_table.add_column()

        email_status = "[green]OK[/]" if settings['email_address'] else "[red]X[/]"
        pass_status = "[green]OK[/]" if settings['app_password'] else "[red]X[/]"
        api_status = "[green]OK[/]" if settings['binance_api_key'] else "[red]X[/]"
        secret_status = "[green]OK[/]" if settings['binance_api_secret'] else "[red]X[/]"
        pair_status = f"[green]{settings['trading_pair']}[/]" if settings['trading_pair'] else "[red]X[/]"
        exec_mode = f"[bold green]AKTIF[/]" if settings.get("execute_binance_orders") else f"[bold yellow]NONAKTIF[/]"

        status_table.add_row("Status Email:", f"[{email_status}] Email | [{pass_status}] App Pass")
        if BINANCE_AVAILABLE:
             status_table.add_row("Status Binance:", f"[{api_status}] API | [{secret_status}] Secret | [{pair_status}] Pair | Eksekusi [{exec_mode}]")
        else:
            status_table.add_row("Status Binance:", "[red]Library tidak terinstall[/]")
        console.print(Panel(status_table, title="Status Konfigurasi", border_style="dim"))
        console.rule(style="magenta")

        # RICH: Gunakan Prompt untuk pilihan
        choice = Prompt.ask("Masukkan pilihan Anda", choices=["1", "2", "3"], default="3")

        if choice == '1':
            # Validasi dasar sebelum memulai
            valid_email = settings['email_address'] and settings['app_password']
            # Validasi kuantitas Binance (Buy harus > 0. Sell harus >= 0)
            valid_binance_creds = settings['binance_api_key'] and settings['binance_api_secret'] and settings['trading_pair']
            valid_binance_buy_qty = settings['buy_quote_quantity'] > 0
            valid_binance_sell_qty = settings['sell_base_quantity'] >= 0 # Boleh 0 jika tidak mau sell
            execute_binance = settings.get("execute_binance_orders")

            error_messages = []
            if not valid_email:
                error_messages.append("[red]Pengaturan Email (Alamat/App Password) belum lengkap![/]")
            if execute_binance:
                if not BINANCE_AVAILABLE:
                    error_messages.append("[red]Eksekusi Binance aktif tapi library 'python-binance' tidak ditemukan![/]")
                elif not valid_binance_creds:
                     error_messages.append("[red]Pengaturan Binance (API/Secret/Pair) belum lengkap![/]")
                elif not valid_binance_buy_qty:
                     error_messages.append("[red]Kuantitas Beli (buy_quote_quantity) harus lebih besar dari 0.[/]")
                # Tidak perlu error jika sell_base_quantity = 0, kecuali jika ada logika khusus yg mengharuskan sell bisa dieksekusi
                # elif not valid_binance_sell_qty: # Komentari ini jika 0 valid
                #      error_messages.append("[red]Kuantitas Jual (sell_base_quantity) harus 0 atau lebih besar.[/]")

            if error_messages:
                console.print(Panel("\n".join(error_messages) + "\n\n[yellow]Silakan masuk ke menu 'Pengaturan' (pilihan 2).[/]",
                                    title="[bold red]Validasi Gagal[/]", border_style="red", padding=(1,2)))
                time.sleep(4)
            else:
                # Siap memulai
                clear_screen()
                mode = "Email & Binance Order" if execute_binance else "Email Listener Only"
                console.print(Panel(f"Memulai Mode: [bold green]{mode}[/]", border_style="green", title="🚀 Memulai Listener 🚀"))
                start_listening(settings)
                console.print("\n[yellow]Kembali ke Menu Utama...[/]")
                time.sleep(2)
        elif choice == '2':
            show_settings(settings)
            settings = load_settings() # Load ulang jika ada perubahan
        elif choice == '3':
            console.print(f"\n[bold cyan]Terima kasih! Sampai jumpa! 👋[/]")
            sys.exit(0)

# --- Entry Point ---
if __name__ == "__main__":
    try:
        # RICH: Cek ketersediaan library di awal
        if not RICH_AVAILABLE:
            console.print("[bold yellow]WARNING: Library 'rich' tidak terinstall. Tampilan akan standar.[/]")
            console.print("[bold yellow]         Disarankan install dengan 'pip install rich' untuk pengalaman terbaik.[/]")
            time.sleep(2) # Beri waktu untuk membaca warning
        main_menu()
    except KeyboardInterrupt:
        # Signal handler sudah menangani ini, tapi sebagai fallback
        console.print(f"\n[yellow][WARN][/] Program dihentikan paksa.")
        sys.exit(1)
    except Exception as e:
        console.rule("[bold red]===== ERROR KRITIS =====[/]", style="red")
        # RICH: Gunakan console.print_exception
        console.print_exception(show_locals=True) # Tampilkan local var untuk debug
        console.rule(style="red")
        console.print(f"\n[bold red]Terjadi error kritis yang tidak tertangani: {e}[/]")
        console.print("[bold red]Program akan keluar.[/]")
        sys.exit(1)
    finally:
         # RICH: Pastikan cursor terlihat saat keluar
         if RICH_AVAILABLE:
            console.show_cursor(True)
