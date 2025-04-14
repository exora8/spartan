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

# --- Binance Integration ---
try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException, BinanceOrderException
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False
    print("\n!!! WARNING: Library 'python-binance' tidak ditemukan. !!!")
    print("!!!          Fitur eksekusi order Binance tidak akan berfungsi. !!!")
    print("!!!          Install dengan: pip install python-binance         !!!\n")
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

# --- Kode Warna ANSI ---
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
    print(f"\n{YELLOW}[WARN] Ctrl+C terdeteksi. Menghentikan program...{RESET}")
    running = False
    time.sleep(1.5)
    print(f"{RED}[EXIT] Keluar dari program.{RESET}")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# --- Fungsi Konfigurasi ---
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
                    print(f"{YELLOW}[WARN] Interval cek di '{CONFIG_FILE}' < 5 detik, direset ke 10.{RESET}")
                    settings["check_interval_seconds"] = 10

                if not isinstance(settings.get("buy_quote_quantity"), (int, float)) or settings.get("buy_quote_quantity") <= 0:
                     print(f"{YELLOW}[WARN] 'buy_quote_quantity' tidak valid, direset ke {DEFAULT_SETTINGS['buy_quote_quantity']}.{RESET}")
                     settings["buy_quote_quantity"] = DEFAULT_SETTINGS['buy_quote_quantity']

                if not isinstance(settings.get("sell_base_quantity"), (int, float)) or settings.get("sell_base_quantity") < 0: # Allow 0
                     print(f"{YELLOW}[WARN] 'sell_base_quantity' tidak valid, direset ke {DEFAULT_SETTINGS['sell_base_quantity']}.{RESET}")
                     settings["sell_base_quantity"] = DEFAULT_SETTINGS['sell_base_quantity']

                if not isinstance(settings.get("execute_binance_orders"), bool):
                    print(f"{YELLOW}[WARN] 'execute_binance_orders' tidak valid, direset ke False.{RESET}")
                    settings["execute_binance_orders"] = False

                # Save back any corrections made
                save_settings(settings)

        except json.JSONDecodeError:
            print(f"{RED}[ERROR] File konfigurasi '{CONFIG_FILE}' rusak. Menggunakan default & menyimpan ulang.{RESET}")
            save_settings(settings) # Simpan default yang bersih
        except Exception as e:
            print(f"{RED}[ERROR] Gagal memuat konfigurasi: {e}{RESET}")
            # Tidak menyimpan ulang jika error tidak diketahui
    else:
        # Jika file tidak ada, simpan default awal
        print(f"{YELLOW}[INFO] File konfigurasi '{CONFIG_FILE}' tidak ditemukan. Membuat dengan nilai default.{RESET}")
        save_settings(settings)
    return settings


def save_settings(settings):
    """Menyimpan pengaturan ke file JSON."""
    try:
        # Pastikan tipe data benar sebelum menyimpan
        settings['check_interval_seconds'] = int(settings.get('check_interval_seconds', 10))
        settings['buy_quote_quantity'] = float(settings.get('buy_quote_quantity', 11.0))
        settings['sell_base_quantity'] = float(settings.get('sell_base_quantity', 0.0))
        settings['execute_binance_orders'] = bool(settings.get('execute_binance_orders', False))

        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings, f, indent=4, sort_keys=True) # Urutkan kunci agar lebih rapi
        print(f"{GREEN}[INFO] Pengaturan berhasil disimpan ke '{CONFIG_FILE}'{RESET}")
    except Exception as e:
        print(f"{RED}[ERROR] Gagal menyimpan konfigurasi: {e}{RESET}")

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
                    print(f"{YELLOW}[WARN] Tidak bisa mendekode bagian email: {e}{RESET}")
    else:
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                text_content = payload.decode(charset, errors='replace')
            except Exception as e:
                 print(f"{YELLOW}[WARN] Tidak bisa mendekode body email: {e}{RESET}")
    return text_content.lower()

# --- Fungsi Beep ---
def trigger_beep(action):
    # ... (fungsi trigger_beep tetap sama) ...
    try:
        if action == "buy":
            print(f"{MAGENTA}[ACTION] Memicu BEEP untuk '{BOLD}BUY{RESET}{MAGENTA}'{RESET}")
            subprocess.run(["beep", "-f", "1000", "-l", "500", "-D", "500", "-r", "5"], check=True, capture_output=True, text=True)
        elif action == "sell":
            print(f"{MAGENTA}[ACTION] Memicu BEEP untuk '{BOLD}SELL{RESET}{MAGENTA}'{RESET}")
            subprocess.run(["beep", "-f", "700", "-l", "1000", "-D", "500", "-r", "2"], check=True, capture_output=True, text=True)
        else:
             print(f"{YELLOW}[WARN] Aksi beep tidak dikenal '{action}'.{RESET}")
    except FileNotFoundError:
        print(f"{YELLOW}[WARN] Perintah 'beep' tidak ditemukan. Beep dilewati.{RESET}")
    except subprocess.CalledProcessError as e:
        print(f"{RED}[ERROR] Gagal menjalankan 'beep': {e}{RESET}")
        if e.stderr: print(f"{RED}         Stderr: {e.stderr.strip()}{RESET}")
    except Exception as e:
        print(f"{RED}[ERROR] Kesalahan tak terduga saat beep: {e}{RESET}")

# --- Fungsi Eksekusi Binance ---
def get_binance_client(settings):
    """Membuat instance Binance client."""
    if not BINANCE_AVAILABLE:
        print(f"{RED}[ERROR] Library python-binance tidak terinstall. Tidak bisa membuat client.{RESET}")
        return None
    if not settings.get('binance_api_key') or not settings.get('binance_api_secret'):
        print(f"{RED}[ERROR] API Key atau Secret Key Binance belum diatur di konfigurasi.{RESET}")
        return None
    try:
        client = Client(settings['binance_api_key'], settings['binance_api_secret'])
        # Test koneksi (opsional tapi bagus)
        client.ping()
        print(f"{GREEN}[BINANCE] Koneksi ke Binance API berhasil.{RESET}")
        return client
    except BinanceAPIException as e:
        print(f"{RED}[BINANCE ERROR] Gagal terhubung/autentikasi ke Binance: {e}{RESET}")
        return None
    except Exception as e:
        print(f"{RED}[ERROR] Gagal membuat Binance client: {e}{RESET}")
        return None

def execute_binance_order(client, settings, side):
    """Mengeksekusi order MARKET BUY atau SELL di Binance."""
    if not client:
        print(f"{RED}[BINANCE] Eksekusi dibatalkan, client tidak valid.{RESET}")
        return False
    if not settings.get("execute_binance_orders", False):
        print(f"{YELLOW}[BINANCE] Eksekusi order dinonaktifkan di pengaturan ('execute_binance_orders': false). Order dilewati.{RESET}")
        return False # Dianggap tidak gagal, hanya dilewati

    pair = settings.get('trading_pair', '').upper()
    if not pair:
        print(f"{RED}[BINANCE ERROR] Trading pair belum diatur di konfigurasi.{RESET}")
        return False

    order_details = {}
    action_desc = ""

    try:
        if side == Client.SIDE_BUY:
            quote_qty = settings.get('buy_quote_quantity', 0.0)
            if quote_qty <= 0:
                 print(f"{RED}[BINANCE ERROR] Kuantitas Beli (buy_quote_quantity) harus > 0.{RESET}")
                 return False
            order_details = {
                'symbol': pair,
                'side': Client.SIDE_BUY,
                'type': Client.ORDER_TYPE_MARKET,
                'quoteOrderQty': quote_qty
            }
            action_desc = f"MARKET BUY {quote_qty} (quote) of {pair}"

        elif side == Client.SIDE_SELL:
            base_qty = settings.get('sell_base_quantity', 0.0)
            if base_qty <= 0:
                 print(f"{RED}[BINANCE ERROR] Kuantitas Jual (sell_base_quantity) harus > 0.{RESET}")
                 return False
            order_details = {
                'symbol': pair,
                'side': Client.SIDE_SELL,
                'type': Client.ORDER_TYPE_MARKET,
                'quantity': base_qty # Jual sejumlah base asset
            }
            action_desc = f"MARKET SELL {base_qty} (base) of {pair}"
        else:
            print(f"{RED}[BINANCE ERROR] Sisi order tidak valid: {side}{RESET}")
            return False

        print(f"{MAGENTA}[BINANCE] Mencoba eksekusi: {action_desc}...{RESET}")
        order_result = client.create_order(**order_details)

        print(f"{GREEN}[BINANCE SUCCESS] Order berhasil dieksekusi!{RESET}")
        print(f"  Order ID : {order_result.get('orderId')}")
        print(f"  Symbol   : {order_result.get('symbol')}")
        print(f"  Side     : {order_result.get('side')}")
        print(f"  Status   : {order_result.get('status')}")
        # Info fill (harga rata-rata dan kuantitas terisi)
        if order_result.get('fills'):
            total_qty = sum(float(f['qty']) for f in order_result['fills'])
            total_quote_qty = sum(float(f['qty']) * float(f['price']) for f in order_result['fills'])
            avg_price = total_quote_qty / total_qty if total_qty else 0
            print(f"  Avg Price: {avg_price:.8f}") # Sesuaikan presisi jika perlu
            print(f"  Filled Qty: {total_qty:.8f}")
        return True

    except BinanceAPIException as e:
        print(f"{RED}[BINANCE API ERROR] Gagal eksekusi order: {e.status_code} - {e.message}{RESET}")
        # Contoh error spesifik:
        if e.code == -2010: # Insufficient balance
            print(f"{RED}         -> Kemungkinan saldo tidak cukup.{RESET}")
        elif e.code == -1121: # Invalid symbol
            print(f"{RED}         -> Trading pair '{pair}' tidak valid.{RESET}")
        elif e.code == -1013 or 'MIN_NOTIONAL' in e.message: # Min notional / Lot size
             print(f"{RED}         -> Order size terlalu kecil (cek minimum order/MIN_NOTIONAL atau LOT_SIZE).{RESET}")
        return False
    except BinanceOrderException as e:
        print(f"{RED}[BINANCE ORDER ERROR] Gagal eksekusi order: {e.status_code} - {e.message}{RESET}")
        return False
    except Exception as e:
        print(f"{RED}[ERROR] Kesalahan tak terduga saat eksekusi order Binance: {e}{RESET}")
        traceback.print_exc()
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
        status, data = mail.fetch(email_id, "(RFC822)")
        if status != 'OK':
            print(f"{RED}[ERROR] Gagal mengambil email ID {email_id_str}: {status}{RESET}")
            return

        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        subject = decode_mime_words(msg["Subject"])
        sender = decode_mime_words(msg["From"])
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print(f"\n{CYAN}--- Email Baru Diterima ({timestamp}) ---{RESET}")
        print(f" ID    : {email_id_str}")
        print(f" Dari  : {sender}")
        print(f" Subjek: {subject}")

        body = get_text_from_email(msg)
        full_content = (subject.lower() + " " + body)

        if target_keyword_lower in full_content:
            print(f"{GREEN}[INFO] Keyword target '{settings['target_keyword']}' ditemukan.{RESET}")
            try:
                target_index = full_content.index(target_keyword_lower)
                trigger_index = full_content.index(trigger_keyword_lower, target_index + len(target_keyword_lower))
                start_word_index = trigger_index + len(trigger_keyword_lower)
                text_after_trigger = full_content[start_word_index:].lstrip()
                words_after_trigger = text_after_trigger.split(maxsplit=1)

                if words_after_trigger:
                    action_word = words_after_trigger[0].strip('.,!?:;()[]{}').lower()
                    print(f"{GREEN}[INFO] Keyword trigger '{settings['trigger_keyword']}' ditemukan. Kata berikutnya: '{BOLD}{action_word}{RESET}{GREEN}'{RESET}")

                    # --- Trigger Aksi (Beep dan/atau Binance) ---
                    order_executed = False # Tandai apakah order sudah dicoba
                    if action_word == "buy":
                        trigger_beep("buy")
                        # Coba eksekusi Binance BUY
                        if binance_client:
                           execute_binance_order(binance_client, settings, Client.SIDE_BUY)
                           order_executed = True
                        elif settings.get("execute_binance_orders"):
                            print(f"{YELLOW}[WARN] Eksekusi Binance aktif tapi client tidak valid/tersedia.{RESET}")

                    elif action_word == "sell":
                        trigger_beep("sell")
                        # Coba eksekusi Binance SELL
                        if binance_client:
                           execute_binance_order(binance_client, settings, Client.SIDE_SELL)
                           order_executed = True
                        elif settings.get("execute_binance_orders"):
                           print(f"{YELLOW}[WARN] Eksekusi Binance aktif tapi client tidak valid/tersedia.{RESET}")
                    else:
                        print(f"{YELLOW}[WARN] Kata setelah '{settings['trigger_keyword']}' ({action_word}) bukan 'buy' atau 'sell'. Tidak ada aksi market.{RESET}")

                    if not order_executed and settings.get("execute_binance_orders") and action_word in ["buy", "sell"]:
                         print(f"{YELLOW}[BINANCE] Eksekusi tidak dilakukan (lihat pesan error di atas atau cek status client).{RESET}")


                else:
                    print(f"{YELLOW}[WARN] Tidak ada kata yang terbaca setelah '{settings['trigger_keyword']}'.{RESET}")

            except ValueError:
                print(f"{YELLOW}[WARN] Keyword trigger '{settings['trigger_keyword']}' tidak ditemukan {BOLD}setelah{RESET}{YELLOW} '{settings['target_keyword']}'.{RESET}")
            except Exception as e:
                 print(f"{RED}[ERROR] Gagal parsing kata setelah trigger: {e}{RESET}")
        else:
            print(f"{BLUE}[INFO] Keyword target '{settings['target_keyword']}' tidak ditemukan dalam email ini.{RESET}")

        # Tandai email sebagai sudah dibaca ('Seen')
        try:
            print(f"{BLUE}[INFO] Menandai email {email_id_str} sebagai sudah dibaca.{RESET}")
            mail.store(email_id, '+FLAGS', '\\Seen')
        except Exception as e:
            print(f"{RED}[ERROR] Gagal menandai email {email_id_str} sebagai 'Seen': {e}{RESET}")
        print(f"{CYAN}-------------------------------------------{RESET}")

    except Exception as e:
        print(f"{RED}[ERROR] Gagal memproses email ID {email_id_str}:{RESET}")
        traceback.print_exc()

# --- Fungsi Listening Utama ---
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
             print(f"{RED}[FATAL] Eksekusi Binance diaktifkan tapi library python-binance tidak ada! Nonaktifkan atau install library.{RESET}")
             running = False # Hentikan sebelum loop utama
             return
        print(f"{CYAN}[SYS] Mencoba menginisialisasi koneksi Binance API...{RESET}")
        binance_client = get_binance_client(settings)
        if not binance_client:
            print(f"{RED}[FATAL] Gagal menginisialisasi Binance Client. Periksa API Key/Secret dan koneksi.{RESET}")
            print(f"{YELLOW}         Eksekusi order tidak akan berjalan. Anda bisa menonaktifkannya di Pengaturan.{RESET}")
            # Kita tidak menghentikan program, mungkin user hanya ingin notifikasi email
            # running = False
            # return
        else:
            print(f"{GREEN}[SYS] Binance Client siap.{RESET}")
    else:
        print(f"{YELLOW}[INFO] Eksekusi order Binance dinonaktifkan ('execute_binance_orders': false).{RESET}")

    # --- Loop Utama Email Listener ---
    while running:
        try:
            # (Bagian koneksi IMAP tetap sama)
            print(f"{CYAN}[SYS] Mencoba menghubungkan ke server IMAP ({settings['imap_server']})...{RESET}")
            mail = imaplib.IMAP4_SSL(settings['imap_server'])
            print(f"{GREEN}[SYS] Terhubung ke {settings['imap_server']}{RESET}")
            print(f"{CYAN}[SYS] Mencoba login sebagai {settings['email_address']}...{RESET}")
            mail.login(settings['email_address'], settings['app_password'])
            print(f"{GREEN}[SYS] Login email berhasil sebagai {BOLD}{settings['email_address']}{RESET}")
            mail.select("inbox")
            print(f"{GREEN}[INFO] Memulai mode mendengarkan di INBOX... (Tekan Ctrl+C untuk berhenti){RESET}")
            print("-" * 50)

            while running:
                try:
                    status, _ = mail.noop() # Cek koneksi IMAP
                    if status != 'OK':
                        print(f"{YELLOW}[WARN] Koneksi IMAP NOOP gagal ({status}). Mencoba reconnect...{RESET}")
                        break
                except Exception as NopErr:
                     print(f"{YELLOW}[WARN] Koneksi IMAP terputus ({NopErr}). Mencoba reconnect...{RESET}")
                     break

                # Cek koneksi Binance jika client ada (opsional, tapi bagus)
                if binance_client:
                    try:
                         binance_client.ping()
                    except Exception as PingErr:
                         print(f"{YELLOW}[WARN] Ping ke Binance API gagal ({PingErr}). Mencoba membuat ulang client...{RESET}")
                         # Coba buat ulang client sekali sebelum loop berikutnya
                         binance_client = get_binance_client(settings)
                         if not binance_client:
                              print(f"{RED}       Gagal membuat ulang Binance client. Eksekusi mungkin gagal.{RESET}")
                         time.sleep(5) # Beri jeda setelah error ping

                # (Bagian cek email UNSEEN tetap sama)
                status, messages = mail.search(None, '(UNSEEN)')
                if status != 'OK':
                     print(f"{RED}[ERROR] Gagal mencari email: {status}{RESET}")
                     break

                email_ids = messages[0].split()
                if email_ids:
                    print(f"\n{GREEN}[INFO] Menemukan {len(email_ids)} email baru!{RESET}")
                    for email_id in email_ids:
                        if not running: break
                        # Kirim client Binance ke process_email
                        process_email(mail, email_id, settings, binance_client)
                    if not running: break
                    print("-" * 50)
                    print(f"{GREEN}[INFO] Selesai memproses. Kembali mendengarkan...{RESET}")
                else:
                    wait_interval = settings['check_interval_seconds']
                    print(f"{BLUE}[INFO] Tidak ada email baru. Cek lagi dalam {wait_interval} detik... {RESET}          ", end='\r')
                    for _ in range(wait_interval):
                         if not running: break
                         time.sleep(1)
                    if not running: break
                    print(" " * 80, end='\r') # Hapus pesan tunggu

            # Tutup koneksi IMAP jika keluar loop inner
            if mail and mail.state == 'SELECTED':
                try: mail.close()
                except Exception: pass

        # (Bagian Exception Handling untuk IMAP & Koneksi tetap sama)
        except (imaplib.IMAP4.error, imaplib.IMAP4.abort) as e:
            print(f"{RED}[ERROR] Kesalahan IMAP: {e}{RESET}")
            if "authentication failed" in str(e).lower() or "invalid credentials" in str(e).lower():
                print(f"{RED}[FATAL] Login Email GAGAL! Periksa alamat email dan App Password.{RESET}")
                running = False # Hentikan loop utama
                return
            print(f"{YELLOW}[WARN] Akan mencoba menghubungkan kembali dalam {wait_time} detik...{RESET}")
            time.sleep(wait_time)
        except (ConnectionError, OSError, socket.error, socket.gaierror) as e:
             print(f"{RED}[ERROR] Kesalahan Koneksi: {e}{RESET}")
             print(f"{YELLOW}[WARN] Periksa koneksi internet. Mencoba lagi dalam {wait_time} detik...{RESET}")
             time.sleep(wait_time)
        except Exception as e:
            print(f"{RED}[ERROR] Kesalahan tak terduga di loop utama:{RESET}")
            traceback.print_exc()
            print(f"{YELLOW}[WARN] Akan mencoba menghubungkan kembali dalam {wait_time} detik...{RESET}")
            time.sleep(wait_time)
        finally:
            if mail:
                try:
                    if mail.state != 'LOGOUT': mail.logout()
                    print(f"{CYAN}[SYS] Logout dari server IMAP.{RESET}")
                except Exception: pass
            mail = None
        if running: time.sleep(2) # Jeda sebelum retry koneksi

    print(f"{YELLOW}[INFO] Mode mendengarkan dihentikan.{RESET}")


# --- Fungsi Menu Pengaturan ---
def show_settings(settings):
    """Menampilkan dan mengedit pengaturan, termasuk Binance."""
    while True:
        clear_screen()
        print(f"{BOLD}{CYAN}--- Pengaturan Email & Binance Listener ---{RESET}")
        print("\n--- Email Settings ---")
        print(f" 1. {CYAN}Alamat Email{RESET}   : {settings['email_address'] or '[Belum diatur]'}")
        print(f" 2. {CYAN}App Password{RESET}   : {settings['app_password'] or '[Belum diatur]'}") # Tidak disembunyikan sesuai req
        print(f" 3. {CYAN}Server IMAP{RESET}    : {settings['imap_server']}")
        print(f" 4. {CYAN}Interval Cek{RESET}   : {settings['check_interval_seconds']} detik")
        print(f" 5. {CYAN}Keyword Target{RESET} : {settings['target_keyword']}")
        print(f" 6. {CYAN}Keyword Trigger{RESET}: {settings['trigger_keyword']}")

        print("\n--- Binance Settings ---")
        binance_status = f"{GREEN}Tersedia{RESET}" if BINANCE_AVAILABLE else f"{RED}Tidak Tersedia (Install 'python-binance'){RESET}"
        print(f" Library Status      : {binance_status}")
        print(f" 7. {CYAN}API Key{RESET}        : {settings['binance_api_key'] or '[Belum diatur]'}")
        print(f" 8. {CYAN}API Secret{RESET}     : {settings['binance_api_secret'] or '[Belum diatur]'}")
        print(f" 9. {CYAN}Trading Pair{RESET}   : {settings['trading_pair'] or '[Belum diatur]'}")
        print(f"10. {CYAN}Buy Quote Qty{RESET}  : {settings['buy_quote_quantity']} (e.g., USDT)")
        print(f"11. {CYAN}Sell Base Qty{RESET}  : {settings['sell_base_quantity']} (e.g., BTC)")
        exec_status = f"{GREEN}Aktif{RESET}" if settings['execute_binance_orders'] else f"{RED}Nonaktif{RESET}"
        print(f"12. {CYAN}Eksekusi Order{RESET} : {exec_status}")
        print("-" * 30)

        print("\nOpsi:")
        print(f" {YELLOW}E{RESET} - Edit Pengaturan")
        print(f" {YELLOW}K{RESET} - Kembali ke Menu Utama")
        print("-" * 30)

        choice = input("Pilih opsi (E/K): ").lower().strip()

        if choice == 'e':
            print(f"\n{BOLD}{MAGENTA}--- Edit Pengaturan ---{RESET}")
            # --- Edit Email ---
            print(f"{CYAN}--- Email ---{RESET}")
            new_val = input(f" 1. Email [{settings['email_address']}]: ").strip()
            if new_val: settings['email_address'] = new_val
            new_val = input(f" 2. App Password [{settings['app_password']}]: ").strip() # Tidak pakai getpass
            if new_val: settings['app_password'] = new_val
            new_val = input(f" 3. Server IMAP [{settings['imap_server']}]: ").strip()
            if new_val: settings['imap_server'] = new_val
            while True:
                new_val_str = input(f" 4. Interval (detik) [{settings['check_interval_seconds']}], min 5: ").strip()
                if not new_val_str: break
                try:
                    new_interval = int(new_val_str)
                    if new_interval >= 5: settings['check_interval_seconds'] = new_interval; break
                    else: print(f"   {RED}[ERROR] Interval minimal 5 detik.{RESET}")
                except ValueError: print(f"   {RED}[ERROR] Masukkan angka.{RESET}")
            new_val = input(f" 5. Keyword Target [{settings['target_keyword']}]: ").strip()
            if new_val: settings['target_keyword'] = new_val
            new_val = input(f" 6. Keyword Trigger [{settings['trigger_keyword']}]: ").strip()
            if new_val: settings['trigger_keyword'] = new_val

             # --- Edit Binance ---
            print(f"\n{CYAN}--- Binance ---{RESET}")
            if not BINANCE_AVAILABLE:
                 print(f"{YELLOW}   (Library Binance tidak terinstall, pengaturan Binance mungkin tidak berpengaruh){RESET}")

            new_val = input(f" 7. API Key [{settings['binance_api_key']}]: ").strip()
            if new_val: settings['binance_api_key'] = new_val
            new_val = input(f" 8. API Secret [{settings['binance_api_secret']}]: ").strip()
            if new_val: settings['binance_api_secret'] = new_val
            new_val = input(f" 9. Trading Pair (e.g., BTCUSDT) [{settings['trading_pair']}]: ").strip().upper()
            if new_val: settings['trading_pair'] = new_val
            while True:
                 new_val_str = input(f"10. Buy Quote Qty (e.g., 11.0 USDT) [{settings['buy_quote_quantity']}], > 0: ").strip()
                 if not new_val_str: break
                 try:
                     new_qty = float(new_val_str)
                     if new_qty > 0: settings['buy_quote_quantity'] = new_qty; break
                     else: print(f"   {RED}[ERROR] Kuantitas Beli harus > 0.{RESET}")
                 except ValueError: print(f"   {RED}[ERROR] Masukkan angka desimal (e.g., 11.0).{RESET}")
            while True:
                 new_val_str = input(f"11. Sell Base Qty (e.g., 0.0005 BTC) [{settings['sell_base_quantity']}], >= 0: ").strip()
                 if not new_val_str: break
                 try:
                     new_qty = float(new_val_str)
                     if new_qty >= 0: settings['sell_base_quantity'] = new_qty; break
                     else: print(f"   {RED}[ERROR] Kuantitas Jual harus >= 0.{RESET}")
                 except ValueError: print(f"   {RED}[ERROR] Masukkan angka desimal (e.g., 0.0005).{RESET}")
            while True:
                 current_exec = settings['execute_binance_orders']
                 exec_prompt = f"{GREEN}Aktif{RESET}" if current_exec else f"{RED}Nonaktif{RESET}"
                 new_val_str = input(f"12. Eksekusi Order Binance? (y/n) [{exec_prompt}]: ").lower().strip()
                 if not new_val_str: break
                 if new_val_str == 'y': settings['execute_binance_orders'] = True; break
                 elif new_val_str == 'n': settings['execute_binance_orders'] = False; break
                 else: print(f"   {RED}[ERROR] Masukkan 'y' atau 'n'.{RESET}")


            save_settings(settings)
            print(f"\n{GREEN}[INFO] Pengaturan diperbarui.{RESET}")
            time.sleep(2)

        elif choice == 'k':
            break # Keluar dari loop pengaturan
        else:
            print(f"{RED}[ERROR] Pilihan tidak valid. Coba lagi.{RESET}")
            time.sleep(1.5)

# --- Fungsi Menu Utama ---
def main_menu():
    """Menampilkan menu utama aplikasi."""
    settings = load_settings()

    while True:
        clear_screen()
        print(f"{BOLD}{MAGENTA}========================================{RESET}")
        print(f"{BOLD}{MAGENTA}   Exora AI - Email & Binance Listener  {RESET}")
        print(f"{BOLD}{MAGENTA}========================================{RESET}")
        print("\nSilakan pilih opsi:\n")
        print(f" {GREEN}1.{RESET} Mulai Mendengarkan (Email" + (f" & {BOLD}Binance{RESET}" if settings.get("execute_binance_orders") else "") + ")")
        print(f" {CYAN}2.{RESET} Pengaturan")
        print(f" {YELLOW}3.{RESET} Keluar")
        print("-" * 40)

        # Tampilkan status konfigurasi penting
        email_status = f"{GREEN}OK{RESET}" if settings['email_address'] else f"{RED}X{RESET}"
        pass_status = f"{GREEN}OK{RESET}" if settings['app_password'] else f"{RED}X{RESET}"
        api_status = f"{GREEN}OK{RESET}" if settings['binance_api_key'] else f"{RED}X{RESET}"
        secret_status = f"{GREEN}OK{RESET}" if settings['binance_api_secret'] else f"{RED}X{RESET}"
        pair_status = f"{GREEN}{settings['trading_pair']}{RESET}" if settings['trading_pair'] else f"{RED}X{RESET}"
        exec_mode = f"{GREEN}AKTIF{RESET}" if settings['execute_binance_orders'] else f"{YELLOW}NONAKTIF{RESET}"

        print(f" Status Email : [{email_status}] Email | [{pass_status}] App Pass")
        print(f" Status Binance: [{api_status}] API | [{secret_status}] Secret | [{pair_status}] Pair | Eksekusi [{exec_mode}]")
        print("-" * 40)

        choice = input("Masukkan pilihan Anda (1/2/3): ").strip()

        if choice == '1':
            # Validasi dasar sebelum memulai
            valid_email = settings['email_address'] and settings['app_password']
            valid_binance = settings['binance_api_key'] and settings['binance_api_secret'] and settings['trading_pair'] \
                            and settings['buy_quote_quantity'] > 0 and settings['sell_base_quantity'] > 0 # Perlu sell > 0 jika mau sell
            execute_binance = settings.get("execute_binance_orders")

            if not valid_email:
                print(f"\n{RED}[ERROR] Pengaturan Email (Alamat/App Password) belum lengkap!{RESET}")
                print(f"{YELLOW}         Silakan masuk ke menu 'Pengaturan' (pilihan 2).{RESET}")
                time.sleep(4)
            elif execute_binance and not BINANCE_AVAILABLE:
                 print(f"\n{RED}[ERROR] Eksekusi Binance aktif tapi library 'python-binance' tidak ditemukan!{RESET}")
                 print(f"{YELLOW}         Install library atau nonaktifkan eksekusi di Pengaturan.{RESET}")
                 time.sleep(4)
            elif execute_binance and not valid_binance:
                 print(f"\n{RED}[ERROR] Pengaturan Binance (API/Secret/Pair/Qty) belum lengkap atau tidak valid!{RESET}")
                 if settings['sell_base_quantity'] <= 0:
                      print(f"{YELLOW}         -> Kuantitas Jual (sell_base_quantity) harus > 0 jika ingin eksekusi SELL.{RESET}")
                 print(f"{YELLOW}         Silakan periksa menu 'Pengaturan' (pilihan 2).{RESET}")
                 time.sleep(5)
            else:
                # Siap memulai
                clear_screen()
                mode = "Email & Binance Order" if execute_binance else "Email Listener Only"
                print(f"{BOLD}{GREEN}--- Memulai Mode: {mode} ---{RESET}")
                start_listening(settings)
                print(f"\n{YELLOW}[INFO] Kembali ke Menu Utama...{RESET}")
                time.sleep(2)
        elif choice == '2':
            show_settings(settings)
            settings = load_settings() # Load ulang jika ada perubahan
        elif choice == '3':
            print(f"\n{CYAN}Terima kasih! Sampai jumpa!{RESET}")
            sys.exit(0)
        else:
            print(f"\n{RED}[ERROR] Pilihan tidak valid. Masukkan 1, 2, atau 3.{RESET}")
            time.sleep(1.5)

# --- Entry Point ---
if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}[WARN] Program dihentikan paksa.{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{BOLD}{RED}===== ERROR KRITIS ====={RESET}")
        traceback.print_exc()
        print(f"\n{RED}Terjadi error kritis yang tidak tertangani: {e}{RESET}")
        print("Program akan keluar.")
        sys.exit(1)
