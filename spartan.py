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

# --- Integrasi Pihak Ketiga & Pemeriksaan ---
try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException, BinanceOrderException
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False
    # Pesan peringatan tetap ada di bawah

try:
    from inquirerpy import prompt, inquirer
    from inquirerpy.base.control import Choice
    from inquirerpy.separator import Separator
    from rich.console import Console # Untuk tampilan lebih kaya (opsional tapi bagus)
    from rich.panel import Panel # Untuk box di menu
    INQUIRER_AVAILABLE = True
    console = Console() # Buat instance console Rich
except ImportError:
    INQUIRER_AVAILABLE = False
    # Pesan peringatan akan ditampilkan jika library dibutuhkan

# --- Tampilkan Peringatan Library yang Hilang di Awal ---
if not BINANCE_AVAILABLE:
    print("\n" + "="*60)
    print("!!! PERINGATAN: Library 'python-binance' tidak ditemukan.          !!!")
    print("!!!             Fitur eksekusi order Binance tidak akan berfungsi.  !!!")
    print("!!!             Install dengan: pip install python-binance          !!!")
    print("="*60 + "\n")
    # Definisikan exception dummy jika library tidak ada agar script tidak crash
    class BinanceAPIException(Exception): pass
    class BinanceOrderException(Exception): pass
    class Client: # Dummy class
        # Tambahkan konstanta dummy jika script Anda menggunakannya
        SIDE_BUY = 'BUY'
        SIDE_SELL = 'SELL'
        ORDER_TYPE_MARKET = 'MARKET'

if not INQUIRER_AVAILABLE:
    print("\n" + "="*60)
    print("!!! PERINGATAN: Library 'inquirerpy' dan/atau 'rich' tidak ditemukan. !!!")
    print("!!!             Tampilan menu interaktif tidak akan berfungsi.        !!!")
    print("!!!             Install dengan: pip install inquirerpy rich           !!!")
    print("="*60 + "\n")
    # Keluar jika library UI tidak ada, karena menu utama bergantung padanya
    print("!!! PROGRAM TIDAK DAPAT DILANJUTKAN TANPA LIBRARY UI !!!")
    sys.exit(1)


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

# --- Kode Warna ANSI (Rich akan lebih banyak digunakan untuk style) ---
# Anda masih bisa menggunakan kode ANSI jika mau, tapi Rich lebih fleksibel
RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"

# --- Fungsi Penanganan Sinyal (Ctrl+C) ---
def signal_handler(sig, frame):
    global running
    console.print(f"\n[yellow][WARN] Ctrl+C terdeteksi. Menghentikan program...[/yellow]")
    running = False
    time.sleep(1.5)
    console.print(f"[red][EXIT] Keluar dari program.[/red]")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# --- Fungsi Konfigurasi (Menggunakan Rich untuk output) ---
def load_settings():
    """Memuat pengaturan dari file JSON, memastikan semua kunci ada."""
    settings = DEFAULT_SETTINGS.copy() # Mulai dengan default
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_settings = json.load(f)
                settings.update(loaded_settings) # Timpa default dengan yg dari file

                # Validasi tambahan setelah load
                if settings.get("check_interval_seconds", 10) < 5:
                    console.print(f"[yellow][WARN] Interval cek di '{CONFIG_FILE}' < 5 detik, direset ke 10.[/yellow]")
                    settings["check_interval_seconds"] = 10

                if not isinstance(settings.get("buy_quote_quantity"), (int, float)) or settings.get("buy_quote_quantity") <= 0:
                     console.print(f"[yellow][WARN] 'buy_quote_quantity' tidak valid, direset ke {DEFAULT_SETTINGS['buy_quote_quantity']}.[/yellow]")
                     settings["buy_quote_quantity"] = DEFAULT_SETTINGS['buy_quote_quantity']

                if not isinstance(settings.get("sell_base_quantity"), (int, float)) or settings.get("sell_base_quantity") < 0: # Allow 0
                     console.print(f"[yellow][WARN] 'sell_base_quantity' tidak valid, direset ke {DEFAULT_SETTINGS['sell_base_quantity']}.[/yellow]")
                     settings["sell_base_quantity"] = DEFAULT_SETTINGS['sell_base_quantity']

                if not isinstance(settings.get("execute_binance_orders"), bool):
                    console.print(f"[yellow][WARN] 'execute_binance_orders' tidak valid, direset ke False.[/yellow]")
                    settings["execute_binance_orders"] = False

                # Save back any corrections made
                save_settings(settings, silent=True) # Simpan perbaikan tanpa print success

        except json.JSONDecodeError:
            console.print(f"[red][ERROR] File konfigurasi '{CONFIG_FILE}' rusak. Menggunakan default & menyimpan ulang.[/red]")
            save_settings(settings) # Simpan default yang bersih
        except Exception as e:
            console.print(f"[red][ERROR] Gagal memuat konfigurasi: {e}[/red]")
            # Tidak menyimpan ulang jika error tidak diketahui
    else:
        # Jika file tidak ada, simpan default awal
        console.print(f"[yellow][INFO] File konfigurasi '{CONFIG_FILE}' tidak ditemukan. Membuat dengan nilai default.[/yellow]")
        save_settings(settings)
    return settings


def save_settings(settings, silent=False):
    """Menyimpan pengaturan ke file JSON."""
    try:
        # Pastikan tipe data benar sebelum menyimpan
        settings['check_interval_seconds'] = int(settings.get('check_interval_seconds', 10))
        settings['buy_quote_quantity'] = float(settings.get('buy_quote_quantity', 11.0))
        settings['sell_base_quantity'] = float(settings.get('sell_base_quantity', 0.0))
        settings['execute_binance_orders'] = bool(settings.get('execute_binance_orders', False))

        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings, f, indent=4, sort_keys=True) # Urutkan kunci agar lebih rapi
        if not silent:
            console.print(f"[green][INFO] Pengaturan berhasil disimpan ke '{CONFIG_FILE}'[/green]")
    except Exception as e:
        console.print(f"[red][ERROR] Gagal menyimpan konfigurasi: {e}[/red]")

# --- Fungsi Utilitas ---
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def decode_mime_words(s):
    # ... (fungsi decode_mime_words tetap sama) ...
    if not s:
        return ""
    decoded_parts = decode_header(s)
    result = []
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(encoding or 'utf-8', errors='replace')) # Ganti error decode
        else:
            result.append(part)
    return "".join(result)

def get_text_from_email(msg):
    # ... (fungsi get_text_from_email tetap sama) ...
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
                    console.print(f"[yellow][WARN] Tidak bisa mendekode bagian email: {e}[/yellow]")
    else:
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                text_content = payload.decode(charset, errors='replace')
            except Exception as e:
                 console.print(f"[yellow][WARN] Tidak bisa mendekode body email: {e}[/yellow]")
    return text_content.lower()

# --- Fungsi Beep ---
def trigger_beep(action):
    # ... (fungsi trigger_beep tetap sama, tapi output pakai Rich) ...
    try:
        if action == "buy":
            console.print(f"[magenta][ACTION] Memicu BEEP untuk '[bold]BUY[/bold]'[/magenta]")
            subprocess.run(["beep", "-f", "1000", "-l", "500", "-D", "500", "-r", "5"], check=True, capture_output=True, text=True)
        elif action == "sell":
            console.print(f"[magenta][ACTION] Memicu BEEP untuk '[bold]SELL[/bold]'[/magenta]")
            subprocess.run(["beep", "-f", "700", "-l", "1000", "-D", "500", "-r", "2"], check=True, capture_output=True, text=True)
        else:
             console.print(f"[yellow][WARN] Aksi beep tidak dikenal '{action}'.[/yellow]")
    except FileNotFoundError:
        console.print(f"[yellow][WARN] Perintah 'beep' tidak ditemukan. Beep dilewati.[/yellow]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red][ERROR] Gagal menjalankan 'beep': {e}[/red]")
        if e.stderr: console.print(f"[red]         Stderr: {e.stderr.strip()}[/red]")
    except Exception as e:
        console.print(f"[red][ERROR] Kesalahan tak terduga saat beep: {e}[/red]")

# --- Fungsi Eksekusi Binance (Output pakai Rich) ---
def get_binance_client(settings):
    """Membuat instance Binance client."""
    if not BINANCE_AVAILABLE:
        console.print(f"[red][ERROR] Library python-binance tidak terinstall. Tidak bisa membuat client.[/red]")
        return None
    if not settings.get('binance_api_key') or not settings.get('binance_api_secret'):
        console.print(f"[red][ERROR] API Key atau Secret Key Binance belum diatur di konfigurasi.[/red]")
        return None
    try:
        client = Client(settings['binance_api_key'], settings['binance_api_secret'])
        # Test koneksi (opsional tapi bagus)
        client.ping()
        console.print(f"[green][BINANCE] Koneksi ke Binance API berhasil.[/green]")
        return client
    except BinanceAPIException as e:
        console.print(f"[red][BINANCE ERROR] Gagal terhubung/autentikasi ke Binance: {e}[/red]")
        return None
    except Exception as e:
        console.print(f"[red][ERROR] Gagal membuat Binance client: {e}[/red]")
        return None

def execute_binance_order(client, settings, side):
    """Mengeksekusi order MARKET BUY atau SELL di Binance."""
    if not client:
        console.print(f"[red][BINANCE] Eksekusi dibatalkan, client tidak valid.[/red]")
        return False
    if not settings.get("execute_binance_orders", False):
        console.print(f"[yellow][BINANCE] Eksekusi order dinonaktifkan di pengaturan ('execute_binance_orders': false). Order dilewati.[/yellow]")
        return False # Dianggap tidak gagal, hanya dilewati

    pair = settings.get('trading_pair', '').upper()
    if not pair:
        console.print(f"[red][BINANCE ERROR] Trading pair belum diatur di konfigurasi.[/red]")
        return False

    order_details = {}
    action_desc = ""

    try:
        # Gunakan konstanta dummy jika library binance tidak ada
        side_buy = Client.SIDE_BUY if BINANCE_AVAILABLE else 'BUY'
        side_sell = Client.SIDE_SELL if BINANCE_AVAILABLE else 'SELL'
        order_type_market = Client.ORDER_TYPE_MARKET if BINANCE_AVAILABLE else 'MARKET'

        if side == side_buy:
            quote_qty = settings.get('buy_quote_quantity', 0.0)
            if quote_qty <= 0:
                 console.print(f"[red][BINANCE ERROR] Kuantitas Beli (buy_quote_quantity) harus > 0.[/red]")
                 return False
            order_details = {
                'symbol': pair,
                'side': side_buy,
                'type': order_type_market,
                'quoteOrderQty': quote_qty
            }
            action_desc = f"MARKET BUY {quote_qty} (quote) of {pair}"

        elif side == side_sell:
            base_qty = settings.get('sell_base_quantity', 0.0)
            if base_qty <= 0:
                 console.print(f"[red][BINANCE ERROR] Kuantitas Jual (sell_base_quantity) harus > 0.[/red]")
                 return False
            order_details = {
                'symbol': pair,
                'side': side_sell,
                'type': order_type_market,
                'quantity': base_qty # Jual sejumlah base asset
            }
            action_desc = f"MARKET SELL {base_qty} (base) of {pair}"
        else:
            console.print(f"[red][BINANCE ERROR] Sisi order tidak valid: {side}[/red]")
            return False

        console.print(f"[magenta][BINANCE] Mencoba eksekusi: {action_desc}...[/magenta]")
        # --- INI BAGIAN UTAMA YANG BERINTERAKSI DENGAN BINANCE ---
        # Jika BINANCE_AVAILABLE False, bagian ini seharusnya tidak dieksekusi
        # karena sudah dicek di get_binance_client dan di awal execute_binance_order
        order_result = client.create_order(**order_details)
        # ---------------------------------------------------------

        console.print(f"[green][BINANCE SUCCESS] Order berhasil dieksekusi![/green]")
        console.print(f"  Order ID : {order_result.get('orderId')}")
        console.print(f"  Symbol   : {order_result.get('symbol')}")
        console.print(f"  Side     : {order_result.get('side')}")
        console.print(f"  Status   : {order_result.get('status')}")
        # Info fill (harga rata-rata dan kuantitas terisi)
        if order_result.get('fills'):
            total_qty = sum(float(f['qty']) for f in order_result['fills'])
            total_quote_qty = sum(float(f['qty']) * float(f['price']) for f in order_result['fills'])
            avg_price = total_quote_qty / total_qty if total_qty else 0
            console.print(f"  Avg Price: {avg_price:.8f}") # Sesuaikan presisi jika perlu
            console.print(f"  Filled Qty: {total_qty:.8f}")
        return True

    except BinanceAPIException as e:
        console.print(f"[red][BINANCE API ERROR] Gagal eksekusi order: {e.status_code} - {e.message}[/red]")
        if hasattr(e, 'code'):
            if e.code == -2010: # Insufficient balance
                console.print(f"[red]         -> Kemungkinan saldo tidak cukup.[/red]")
            elif e.code == -1121: # Invalid symbol
                console.print(f"[red]         -> Trading pair '{pair}' tidak valid.[/red]")
            elif e.code == -1013 or ('MIN_NOTIONAL' in e.message if hasattr(e, 'message') else False): # Min notional / Lot size
                 console.print(f"[red]         -> Order size terlalu kecil (cek minimum order/MIN_NOTIONAL atau LOT_SIZE).[/red]")
        return False
    except BinanceOrderException as e:
        console.print(f"[red][BINANCE ORDER ERROR] Gagal eksekusi order: {e.status_code} - {e.message}[/red]")
        return False
    except Exception as e:
        console.print(f"[red][ERROR] Kesalahan tak terduga saat eksekusi order Binance: {e}[/red]")
        traceback.print_exc()
        return False

# --- Fungsi Pemrosesan Email (Output pakai Rich) ---
def process_email(mail, email_id, settings, binance_client): # Tambah binance_client
    """Mengambil, mem-parsing, dan memproses satu email, lalu eksekusi order jika sesuai."""
    global running
    if not running: return

    target_keyword_lower = settings['target_keyword'].lower()
    trigger_keyword_lower = settings['trigger_keyword'].lower()
    email_id_str = email_id.decode('utf-8')

    try:
        status, data = mail.fetch(email_id, "(RFC822)")
        if status != 'OK':
            console.print(f"[red][ERROR] Gagal mengambil email ID {email_id_str}: {status}[/red]")
            return

        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        subject = decode_mime_words(msg["Subject"])
        sender = decode_mime_words(msg["From"])
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        console.print(f"\n[cyan]--- Email Baru Diterima ({timestamp}) ---[/cyan]")
        console.print(f" [bold]ID[/bold]    : {email_id_str}")
        console.print(f" [bold]Dari[/bold]  : {sender}")
        console.print(f" [bold]Subjek[/bold]: {subject}")

        body = get_text_from_email(msg)
        full_content = (subject.lower() + " " + body)

        if target_keyword_lower in full_content:
            console.print(f"[green][INFO] Keyword target '{settings['target_keyword']}' ditemukan.[/green]")
            try:
                target_index = full_content.index(target_keyword_lower)
                trigger_index = full_content.index(trigger_keyword_lower, target_index + len(target_keyword_lower))
                start_word_index = trigger_index + len(trigger_keyword_lower)
                text_after_trigger = full_content[start_word_index:].lstrip()
                words_after_trigger = text_after_trigger.split(maxsplit=1)

                if words_after_trigger:
                    action_word = words_after_trigger[0].strip('.,!?:;()[]{}').lower()
                    console.print(f"[green][INFO] Keyword trigger '{settings['trigger_keyword']}' ditemukan. Kata berikutnya: '[bold]{action_word}[/bold]'[/green]")

                    # --- Trigger Aksi (Beep dan/atau Binance) ---
                    order_executed = False # Tandai apakah order sudah dicoba
                    side_buy = Client.SIDE_BUY if BINANCE_AVAILABLE else 'BUY'
                    side_sell = Client.SIDE_SELL if BINANCE_AVAILABLE else 'SELL'

                    if action_word == "buy":
                        trigger_beep("buy")
                        # Coba eksekusi Binance BUY
                        if binance_client:
                           execute_binance_order(binance_client, settings, side_buy)
                           order_executed = True
                        elif settings.get("execute_binance_orders"):
                            console.print(f"[yellow][WARN] Eksekusi Binance aktif tapi client tidak valid/tersedia.[/yellow]")

                    elif action_word == "sell":
                        trigger_beep("sell")
                        # Coba eksekusi Binance SELL
                        if binance_client:
                           execute_binance_order(binance_client, settings, side_sell)
                           order_executed = True
                        elif settings.get("execute_binance_orders"):
                           console.print(f"[yellow][WARN] Eksekusi Binance aktif tapi client tidak valid/tersedia.[/yellow]")
                    else:
                        console.print(f"[yellow][WARN] Kata setelah '{settings['trigger_keyword']}' ({action_word}) bukan 'buy' atau 'sell'. Tidak ada aksi market.[/yellow]")

                    if not order_executed and settings.get("execute_binance_orders") and action_word in ["buy", "sell"]:
                         console.print(f"[yellow][BINANCE] Eksekusi tidak dilakukan (lihat pesan error di atas atau cek status client).[/yellow]")

                else:
                    console.print(f"[yellow][WARN] Tidak ada kata yang terbaca setelah '{settings['trigger_keyword']}'.[/yellow]")

            except ValueError:
                console.print(f"[yellow][WARN] Keyword trigger '{settings['trigger_keyword']}' tidak ditemukan [bold]setelah[/bold] '{settings['target_keyword']}'.[/yellow]")
            except Exception as e:
                 console.print(f"[red][ERROR] Gagal parsing kata setelah trigger: {e}[/red]")
        else:
            console.print(f"[blue][INFO] Keyword target '{settings['target_keyword']}' tidak ditemukan dalam email ini.[/blue]")

        # Tandai email sebagai sudah dibaca ('Seen')
        try:
            console.print(f"[blue][INFO] Menandai email {email_id_str} sebagai sudah dibaca.[/blue]")
            mail.store(email_id, '+FLAGS', '\\Seen')
        except Exception as e:
            console.print(f"[red][ERROR] Gagal menandai email {email_id_str} sebagai 'Seen': {e}[/red]")
        console.print(f"[cyan]-------------------------------------------[/cyan]")

    except Exception as e:
        console.print(f"[red][ERROR] Gagal memproses email ID {email_id_str}:[/red]")
        traceback.print_exc()

# --- Fungsi Listening Utama (Output pakai Rich) ---
def start_listening(settings):
    """Memulai loop untuk memeriksa email baru dan menyiapkan client Binance."""
    global running
    running = True
    mail = None
    binance_client = None # Inisialisasi client Binance
    wait_time = 30

    # --- Setup Binance Client di Awal (jika diaktifkan) ---
    if settings.get("execute_binance_orders"):
        if not BINANCE_AVAILABLE:
             console.print(f"[bold red][FATAL] Eksekusi Binance diaktifkan tapi library python-binance tidak ada! Nonaktifkan atau install library.[/bold red]")
             running = False # Hentikan sebelum loop utama
             return
        console.print(f"[cyan][SYS] Mencoba menginisialisasi koneksi Binance API...[/cyan]")
        binance_client = get_binance_client(settings)
        if not binance_client:
            console.print(f"[bold red][FATAL] Gagal menginisialisasi Binance Client. Periksa API Key/Secret dan koneksi.[/bold red]")
            console.print(f"[yellow]         Eksekusi order tidak akan berjalan. Anda bisa menonaktifkannya di Pengaturan.[/yellow]")
            # Kita tidak menghentikan program, mungkin user hanya ingin notifikasi email
        else:
            console.print(f"[green][SYS] Binance Client siap.[/green]")
    else:
        console.print(f"[yellow][INFO] Eksekusi order Binance dinonaktifkan ('execute_binance_orders': false).[/yellow]")

    # --- Loop Utama Email Listener ---
    while running:
        try:
            console.print(f"[cyan][SYS] Mencoba menghubungkan ke server IMAP ({settings['imap_server']})...[/cyan]")
            mail = imaplib.IMAP4_SSL(settings['imap_server'])
            console.print(f"[green][SYS] Terhubung ke {settings['imap_server']}[/green]")
            console.print(f"[cyan][SYS] Mencoba login sebagai {settings['email_address']}...[/cyan]")
            mail.login(settings['email_address'], settings['app_password'])
            console.print(f"[green][SYS] Login email berhasil sebagai [bold]{settings['email_address']}[/bold][/green]")
            mail.select("inbox")
            console.print(f"[green][INFO] Memulai mode mendengarkan di INBOX... (Tekan Ctrl+C untuk berhenti)[/green]")
            console.print("-" * 50)

            while running:
                try:
                    status, _ = mail.noop() # Cek koneksi IMAP
                    if status != 'OK':
                        console.print(f"[yellow][WARN] Koneksi IMAP NOOP gagal ({status}). Mencoba reconnect...[/yellow]")
                        break
                except Exception as NopErr:
                     console.print(f"[yellow][WARN] Koneksi IMAP terputus ({NopErr}). Mencoba reconnect...[/yellow]")
                     break

                # Cek koneksi Binance jika client ada (opsional, tapi bagus)
                if binance_client and BINANCE_AVAILABLE: # Pastikan library ada juga
                    try:
                         binance_client.ping()
                    except Exception as PingErr:
                         console.print(f"[yellow][WARN] Ping ke Binance API gagal ({PingErr}). Mencoba membuat ulang client...[/yellow]")
                         # Coba buat ulang client sekali sebelum loop berikutnya
                         binance_client = get_binance_client(settings)
                         if not binance_client:
                              console.print(f"[red]       Gagal membuat ulang Binance client. Eksekusi mungkin gagal.[/red]")
                         time.sleep(5) # Beri jeda setelah error ping

                status, messages = mail.search(None, '(UNSEEN)')
                if status != 'OK':
                     console.print(f"[red][ERROR] Gagal mencari email: {status}[/red]")
                     break

                email_ids = messages[0].split()
                if email_ids:
                    console.print(f"\n[green][INFO] Menemukan {len(email_ids)} email baru![/green]")
                    for email_id in email_ids:
                        if not running: break
                        process_email(mail, email_id, settings, binance_client)
                    if not running: break
                    console.print("-" * 50)
                    console.print(f"[green][INFO] Selesai memproses. Kembali mendengarkan...[/green]")
                else:
                    wait_interval = settings['check_interval_seconds']
                    # Gunakan Rich status untuk pesan tunggu yang lebih baik
                    with console.status(f"[blue]Tidak ada email baru. Cek lagi dalam {wait_interval} detik...", spinner="dots"):
                        for _ in range(wait_interval):
                             if not running: break
                             time.sleep(1)
                    if not running: break
                    # Tidak perlu clear line karena status Rich menangani itu

            # Tutup koneksi IMAP jika keluar loop inner
            if mail and mail.state == 'SELECTED':
                try: mail.close()
                except Exception: pass

        except (imaplib.IMAP4.error, imaplib.IMAP4.abort) as e:
            console.print(f"[red][ERROR] Kesalahan IMAP: {e}[/red]")
            if "authentication failed" in str(e).lower() or "invalid credentials" in str(e).lower():
                console.print(f"[bold red][FATAL] Login Email GAGAL! Periksa alamat email dan App Password.[/bold red]")
                running = False # Hentikan loop utama
                return
            console.print(f"[yellow][WARN] Akan mencoba menghubungkan kembali dalam {wait_time} detik...[/yellow]")
            time.sleep(wait_time)
        except (ConnectionError, OSError, socket.error, socket.gaierror) as e:
             console.print(f"[red][ERROR] Kesalahan Koneksi: {e}[/red]")
             console.print(f"[yellow][WARN] Periksa koneksi internet. Mencoba lagi dalam {wait_time} detik...[/yellow]")
             time.sleep(wait_time)
        except Exception as e:
            console.print(f"[red][ERROR] Kesalahan tak terduga di loop utama:[/red]")
            traceback.print_exc()
            console.print(f"[yellow][WARN] Akan mencoba menghubungkan kembali dalam {wait_time} detik...[/yellow]")
            time.sleep(wait_time)
        finally:
            if mail:
                try:
                    if mail.state != 'LOGOUT': mail.logout()
                    console.print(f"[cyan][SYS] Logout dari server IMAP.[/cyan]")
                except Exception: pass
            mail = None
        if running: time.sleep(2) # Jeda sebelum retry koneksi

    console.print(f"[yellow][INFO] Mode mendengarkan dihentikan.[/yellow]")


# --- Fungsi Menu Pengaturan (Menggunakan Inquirer & Rich) ---
def show_settings(settings):
    """Menampilkan dan mengedit pengaturan, termasuk Binance."""
    while True:
        clear_screen()
        # Menggunakan Rich Panel untuk tampilan lebih menarik
        settings_display = (
            f"[bold cyan]--- Pengaturan Email ---[/bold cyan]\n"
            f" 1. [cyan]Alamat Email[/cyan]   : [bold]{settings['email_address'] or '[Belum diatur]'}[/bold]\n"
            f" 2. [cyan]App Password[/cyan]   : [bold]{'*' * len(settings['app_password']) if settings['app_password'] else '[Belum diatur]'}[/bold]\n" # Sembunyikan password
            f" 3. [cyan]Server IMAP[/cyan]    : [bold]{settings['imap_server']}[/bold]\n"
            f" 4. [cyan]Interval Cek[/cyan]   : [bold]{settings['check_interval_seconds']} detik[/bold]\n"
            f" 5. [cyan]Keyword Target[/cyan] : [bold]{settings['target_keyword']}[/bold]\n"
            f" 6. [cyan]Keyword Trigger[/cyan]: [bold]{settings['trigger_keyword']}[/bold]\n\n"
            f"[bold blue]--- Binance Settings ---[/bold blue]\n"
        )
        binance_status = f"[green]Tersedia[/green]" if BINANCE_AVAILABLE else f"[red]Tidak Tersedia (Install 'python-binance')[/red]"
        settings_display += f" Library Status      : {binance_status}\n"
        settings_display += (
            f" 7. [cyan]API Key[/cyan]        : [bold]{settings['binance_api_key'][:5] + '...' if settings['binance_api_key'] else '[Belum diatur]'}[/bold]\n" # Tampilkan sebagian
            f" 8. [cyan]API Secret[/cyan]     : [bold]{'*' * 8 if settings['binance_api_secret'] else '[Belum diatur]'}[/bold]\n" # Sembunyikan
            f" 9. [cyan]Trading Pair[/cyan]   : [bold]{settings['trading_pair'] or '[Belum diatur]'}[/bold]\n"
            f"10. [cyan]Buy Quote Qty[/cyan]  : [bold]{settings['buy_quote_quantity']} (e.g., USDT)[/bold]\n"
            f"11. [cyan]Sell Base Qty[/cyan]  : [bold]{settings['sell_base_quantity']} (e.g., BTC)[/bold]\n"
        )
        exec_status = f"[bold green]Aktif[/bold green]" if settings['execute_binance_orders'] else f"[bold red]Nonaktif[/bold red]"
        settings_display += f"12. [cyan]Eksekusi Order[/cyan] : {exec_status}\n"

        console.print(Panel(settings_display, title="🔧 Pengaturan Saat Ini", border_style="magenta", expand=False))

        # --- Menggunakan Inquirer untuk pilihan Edit/Kembali ---
        try:
            action_question = [
                 inquirer.list_message(
                    message="Pilih Opsi:",
                    choices=[
                        Choice(value='edit', name='📝 Edit Pengaturan'),
                        Choice(value='back', name='⬅️  Kembali ke Menu Utama'),
                    ],
                    default='edit',
                    carousel=True # Agar pilihan bisa berputar
                )
            ]
            choice = prompt(action_question, raise_keyboard_interrupt=True)['list_message']

        except KeyboardInterrupt:
            console.print("\n[yellow]Pembatalan oleh pengguna.[/yellow]")
            break # Kembali ke menu utama jika Ctrl+C ditekan di sini

        if choice == 'edit':
            console.print(f"\n[bold magenta]--- Edit Pengaturan ---[/bold magenta]")
            try:
                 # --- Edit menggunakan inquirer prompts ---
                 questions = [
                    # Email
                    inquirer.text(message="1. Email:", default=settings['email_address']),
                    inquirer.secret(message="2. App Password (biarkan kosong jika tidak berubah):", default=''), # Kosongkan default agar tidak terisi otomatis
                    inquirer.text(message="3. Server IMAP:", default=settings['imap_server']),
                    inquirer.number(message="4. Interval Cek (detik, min 5):", default=settings['check_interval_seconds'], min_allowed=5, validate=lambda x: x >= 5, invalid_message="Interval minimal 5 detik"),
                    inquirer.text(message="5. Keyword Target:", default=settings['target_keyword']),
                    inquirer.text(message="6. Keyword Trigger:", default=settings['trigger_keyword']),
                    # Binance
                    inquirer.text(message="7. Binance API Key (biarkan kosong jika tidak berubah):", default=''),
                    inquirer.secret(message="8. Binance API Secret (biarkan kosong jika tidak berubah):", default=''),
                    inquirer.text(message="9. Trading Pair (e.g., BTCUSDT):", default=settings['trading_pair']),
                    inquirer.number(message="10. Buy Quote Qty (e.g., 11.0, > 0):", default=settings['buy_quote_quantity'], float_allowed=True, min_allowed=0.00000001, validate=lambda x: x > 0, invalid_message="Kuantitas Beli harus > 0"), # sedikit di atas 0
                    inquirer.number(message="11. Sell Base Qty (e.g., 0.0005, >= 0):", default=settings['sell_base_quantity'], float_allowed=True, min_allowed=0, validate=lambda x: x >= 0, invalid_message="Kuantitas Jual harus >= 0"),
                    inquirer.confirm(message="12. Aktifkan Eksekusi Order Binance?", default=settings['execute_binance_orders']),
                 ]
                 new_settings = prompt(questions, raise_keyboard_interrupt=True)

                 # Update settings jika ada perubahan
                 settings['email_address'] = new_settings[0] if new_settings[0] else settings['email_address']
                 if new_settings[1]: settings['app_password'] = new_settings[1] # Hanya update jika diisi
                 settings['imap_server'] = new_settings[2] if new_settings[2] else settings['imap_server']
                 settings['check_interval_seconds'] = int(new_settings[3]) # Inquirer number mengembalikan float/int
                 settings['target_keyword'] = new_settings[4] if new_settings[4] else settings['target_keyword']
                 settings['trigger_keyword'] = new_settings[5] if new_settings[5] else settings['trigger_keyword']

                 if new_settings[6]: settings['binance_api_key'] = new_settings[6].strip()
                 if new_settings[7]: settings['binance_api_secret'] = new_settings[7].strip()
                 settings['trading_pair'] = new_settings[8].strip().upper() if new_settings[8] else settings['trading_pair']
                 settings['buy_quote_quantity'] = float(new_settings[9])
                 settings['sell_base_quantity'] = float(new_settings[10])
                 settings['execute_binance_orders'] = new_settings[11]

                 save_settings(settings)
                 console.print(f"\n[green][INFO] Pengaturan diperbarui.[/green]")
                 time.sleep(2)

            except KeyboardInterrupt:
                console.print("\n[yellow]Edit dibatalkan.[/yellow]")
                time.sleep(1.5)
            except Exception as e:
                console.print(f"\n[red][ERROR] Terjadi kesalahan saat mengedit: {e}[/red]")
                time.sleep(2)


        elif choice == 'back':
            break # Keluar dari loop pengaturan

# --- Fungsi Menu Utama (Menggunakan Inquirer & Rich) ---
def main_menu():
    """Menampilkan menu utama aplikasi."""
    settings = load_settings()

    while True:
        clear_screen()
        # --- Tampilan Header ---
        console.print(Panel(
            "[bold magenta]Exora AI - Email & Binance Listener[/bold magenta]",
            title="✨ Selamat Datang ✨",
            border_style="bold blue",
            expand=False
        ))

        # --- Tampilkan Status Konfigurasi ---
        email_status = "[green]OK[/green]" if settings['email_address'] else "[red]X[/red]"
        pass_status = "[green]OK[/green]" if settings['app_password'] else "[red]X[/red]"
        api_status = "[green]OK[/green]" if settings['binance_api_key'] else "[red]X[/red]"
        secret_status = "[green]OK[/green]" if settings['binance_api_secret'] else "[red]X[/red]"
        pair_status = f"[green]{settings['trading_pair']}[/green]" if settings['trading_pair'] else "[red]X[/red]"
        exec_mode = f"[bold green]AKTIF[/bold green]" if settings['execute_binance_orders'] else f"[yellow]NONAKTIF[/yellow]"

        status_text = (
            f"Status Email  : [{email_status}] Email | [{pass_status}] App Pass\n"
            f"Status Binance: [{api_status}] API | [{secret_status}] Secret | [{pair_status}] Pair | Eksekusi [{exec_mode}]"
        )
        console.print(Panel(status_text, title="ℹ️ Status Konfigurasi", border_style="green", expand=False))
        console.print("-" * 40)


        # --- Pilihan Menu dengan Inquirer ---
        binance_part = f" & [bold blue]Binance[/bold blue]" if settings.get("execute_binance_orders") else ""
        try:
            menu_questions = [
                inquirer.list_message(
                    message="Silakan pilih opsi:",
                    choices=[
                        Choice(value='start', name=f'🚀 Mulai Mendengarkan (Email{binance_part})'),
                        Choice(value='settings', name='⚙️ Pengaturan'),
                        Separator(),
                        Choice(value='exit', name='🚪 Keluar'),
                    ],
                    default='start',
                    carousel=True,
                )
            ]
            choice = prompt(menu_questions, raise_keyboard_interrupt=True)['list_message']

        except KeyboardInterrupt:
             console.print(f"\n\n[yellow]Keluar dari program...[/yellow]")
             sys.exit(0)

        if choice == 'start':
            # Validasi dasar sebelum memulai
            valid_email = settings['email_address'] and settings['app_password']
            # Validasi Binance sedikit disesuaikan: sell qty bisa 0 jika tidak ingin sell
            valid_binance_core = settings['binance_api_key'] and settings['binance_api_secret'] and settings['trading_pair']
            valid_buy_qty = settings['buy_quote_quantity'] > 0
            # Jika mau eksekusi, perlu validasi lebih
            execute_binance = settings.get("execute_binance_orders")

            ready_to_start = True
            if not valid_email:
                console.print(f"\n[bold red][ERROR] Pengaturan Email (Alamat/App Password) belum lengkap![/bold red]")
                console.print(f"[yellow]         Silakan masuk ke menu 'Pengaturan'.[/yellow]")
                ready_to_start = False
                time.sleep(4)

            if execute_binance:
                 if not BINANCE_AVAILABLE:
                     console.print(f"\n[bold red][ERROR] Eksekusi Binance aktif tapi library 'python-binance' tidak ditemukan![/bold red]")
                     console.print(f"[yellow]         Install library atau nonaktifkan eksekusi di Pengaturan.[/yellow]")
                     ready_to_start = False
                     time.sleep(4)
                 elif not valid_binance_core:
                     console.print(f"\n[bold red][ERROR] Eksekusi Binance aktif tapi pengaturan dasar (API/Secret/Pair) belum lengkap![/bold red]")
                     console.print(f"[yellow]         Silakan periksa menu 'Pengaturan'.[/yellow]")
                     ready_to_start = False
                     time.sleep(4)
                 elif not valid_buy_qty:
                     console.print(f"\n[bold red][ERROR] Kuantitas Beli (buy_quote_quantity) harus lebih besar dari 0![/bold red]")
                     console.print(f"[yellow]         Silakan periksa menu 'Pengaturan'.[/yellow]")
                     ready_to_start = False
                     time.sleep(4)
                 # Tidak wajib validasi sell > 0 di sini, karena mungkin hanya ingin trigger BUY

            if ready_to_start:
                clear_screen()
                mode = "Email & Binance Order" if execute_binance else "Email Listener Only"
                console.print(f"[bold green]--- Memulai Mode: {mode} ---[/bold green]")
                start_listening(settings)
                console.print(f"\n[yellow][INFO] Kembali ke Menu Utama...[/yellow]")
                time.sleep(2)

        elif choice == 'settings':
            show_settings(settings)
            settings = load_settings() # Load ulang jika ada perubahan

        elif choice == 'exit':
            console.print(f"\n[cyan]Terima kasih! Sampai jumpa![/cyan]")
            sys.exit(0)


# --- Entry Point ---
if __name__ == "__main__":
    # Cek library UI lagi sebelum mulai
    if not INQUIRER_AVAILABLE:
         print("\nCRITICAL ERROR: Library 'inquirerpy' dan/atau 'rich' diperlukan.")
         print("Install dengan: pip install inquirerpy rich")
         sys.exit(1)

    try:
        main_menu()
    except KeyboardInterrupt:
        console.print(f"\n[yellow][WARN] Program dihentikan paksa.[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]===== ERROR KRITIS =====[/bold red]")
        # Mencetak traceback dengan format Rich yang lebih baik
        console.print_exception(show_locals=True)
        console.print(f"\n[red]Terjadi error kritis yang tidak tertangani: {e}[/red]")
        console.print("Program akan keluar.")
        sys.exit(1)
