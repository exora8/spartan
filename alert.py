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
import shutil # Untuk mendapatkan lebar terminal (opsional)

# --- Playsound Integration (BARU) ---
try:
    # Coba import playsound versi 1.2.2 karena versi lebih baru kadang error di beberapa sistem
    # Jika error, coba 'pip install playsound==1.2.2'
    # Jika masih error, mungkin perlu dependency lain (cek dokumentasi playsound)
    from playsound import playsound
    PLAYSOUND_AVAILABLE = True
except ImportError:
    PLAYSOUND_AVAILABLE = False
    print("\n!!! WARNING: Library 'playsound' tidak ditemukan. !!!")
    print("!!!          Fitur memainkan MP3 tidak akan berfungsi.    !!!")
    print("!!!          Install dengan: pip install playsound==1.2.2 !!!\n") # Rekomendasikan versi spesifik
    time.sleep(3)
    # Definisikan dummy function jika playsound tidak ada
    def playsound(filepath):
        print(f"!!! WARNING: 'playsound' tidak ada, tidak bisa memainkan {os.path.basename(filepath)} !!!")
        pass # Jangan error, hanya beri warning

# --- Inquirer Integration ---
try:
    import inquirer
    from inquirer.themes import GreenPassion as InquirerTheme
    INQUIRER_AVAILABLE = True
except ImportError:
    INQUIRER_AVAILABLE = False
    print("\n!!! WARNING: Library 'inquirer' tidak ditemukan. Menu akan pakai input biasa. !!!")
    print("!!!          Install dengan: pip install inquirer                              !!!\n")
    time.sleep(3)
    class InquirerTheme: pass

# --- Binance Integration (Tetap ada, tapi eksekusinya di-bypass untuk MP3) ---
try:
    from binance.client import Client
    import requests
    from binance.exceptions import BinanceAPIException, BinanceOrderException
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False
    # Pesan warning tetap ditampilkan jika ingin pakai fitur Binance lain
    print("\n!!! INFO: Library 'python-binance' tidak ditemukan. !!!")
    print("!!!       Fitur eksekusi order Binance tidak akan aktif (script ini pakai MP3). !!!")
    print("!!!       Jika ingin KEMBALI pakai Binance: pip install python-binance requests !!!\n")
    class BinanceAPIException(Exception): pass
    class BinanceOrderException(Exception): pass
    class Client:
        SIDE_BUY = 'BUY'
        SIDE_SELL = 'SELL'
        ORDER_TYPE_MARKET = 'MARKET'
    if 'requests' not in sys.modules:
        class requests:
            class exceptions:
                RequestException = Exception

# --- Konfigurasi & Variabel Global ---
CONFIG_FILE = "config.json"
# Hapus setting Binance yang TIDAK relevan lagi jika fokus ke MP3
# Tapi biarkan saja agar struktur config sama jika ingin switch kembali
DEFAULT_SETTINGS = {
    "email_address": "", "app_password": "", "imap_server": "imap.gmail.com",
    "check_interval_seconds": 10, "target_keyword": "Exora AI", "trigger_keyword": "order",
    # Opsi Binance tetap ada, tapi 'execute_binance_orders' tidak akan memicu order saat MP3 aktif
    "binance_api_key": "", "binance_api_secret": "", "trading_pair": "BTCUSDT",
    "buy_quote_quantity": 11.0, "sell_base_quantity": 0.0, "execute_binance_orders": False,
    # Tambah flag untuk kontrol MP3 (opsional, tapi bagus untuk fleksibilitas)
    "play_mp3_on_signal": True # Defaultnya aktif mainkan MP3
}
running = True

# --- Kode Warna ANSI ---
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"

# --- Fungsi Penanganan Sinyal (Ctrl+C) ---
def signal_handler(sig, frame):
    global running
    print(f"\n{YELLOW}{BOLD}[WARN] Ctrl+C terdeteksi. Menghentikan program...{RESET}")
    running = False
    # Beri waktu agar loop utama bisa berhenti dengan bersih jika sedang proses
    time.sleep(1.5)
    print(f"{RED}{BOLD}[EXIT] Keluar dari program.{RESET}")
    sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)

# --- Fungsi Utilitas (Termasuk Helper Tampilan) ---
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def get_terminal_width(default=70):
    try:
        return shutil.get_terminal_size(fallback=(default, 24)).columns
    except Exception:
        return default

def print_centered(text, color=RESET, style=BOLD):
    width = get_terminal_width()
    padding = (width - len(text)) // 2
    print(f"{' ' * padding}{style}{color}{text}{RESET}")

def print_header(title):
    width = get_terminal_width()
    print(f"\n{BOLD}{MAGENTA}╭{'─' * (width - 2)}╮{RESET}")
    print_centered(title, MAGENTA, BOLD)
    print(f"{BOLD}{MAGENTA}╰{'─' * (width - 2)}╯{RESET}")

def print_separator(char='─', color=DIM):
    width = get_terminal_width()
    print(f"{color}{char * width}{RESET}")

# --- Fungsi Konfigurasi ---
def load_settings():
    settings = DEFAULT_SETTINGS.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_settings = json.load(f)
                # Update settings dari file, tambahkan key baru jika tidak ada
                for key in DEFAULT_SETTINGS:
                    if key in loaded_settings:
                        settings[key] = loaded_settings[key]
                    # else: # Key baru dari DEFAULT_SETTINGS akan tetap ada
                    #     pass

                # Validasi tipe data penting
                settings["check_interval_seconds"] = int(settings.get("check_interval_seconds", 10))
                if settings["check_interval_seconds"] < 5: settings["check_interval_seconds"] = 5
                settings["buy_quote_quantity"] = float(settings.get("buy_quote_quantity", 0))
                settings["sell_base_quantity"] = float(settings.get("sell_base_quantity", 0))
                settings["execute_binance_orders"] = bool(settings.get("execute_binance_orders", False))
                settings["play_mp3_on_signal"] = bool(settings.get("play_mp3_on_signal", True)) # Validasi flag baru

                # Simpan kembali jika ada key default baru atau koreksi minor (opsional)
                # Ini memastikan file config selalu up-to-date dengan struktur DEFAULT_SETTINGS
                save_settings(settings)

        except json.JSONDecodeError:
            print(f"{RED}[ERROR] File konfigurasi '{CONFIG_FILE}' rusak. Menggunakan default & menyimpan ulang.{RESET}")
            save_settings(settings) # Simpan default
        except Exception as e:
            print(f"{RED}[ERROR] Gagal memuat konfigurasi: {e}{RESET}")
            # Mungkin tetap pakai default yang sudah dicopy di awal
    else:
        print(f"{YELLOW}[INFO] File konfigurasi '{CONFIG_FILE}' tidak ditemukan. Membuat dengan nilai default.{RESET}")
        save_settings(settings) # Buat file baru
    return settings

def save_settings(settings):
    try:
        # Pastikan semua key dari DEFAULT ada di dict yang disimpan
        settings_to_save = {}
        for key in DEFAULT_SETTINGS:
            # Ambil nilai dari settings saat ini, atau default jika tidak ada
            settings_to_save[key] = settings.get(key, DEFAULT_SETTINGS[key])

            # Pastikan tipe data benar sebelum simpan (ulangi validasi ringan)
            if key == 'check_interval_seconds': settings_to_save[key] = int(settings_to_save[key])
            elif key in ['buy_quote_quantity', 'sell_base_quantity']: settings_to_save[key] = float(settings_to_save[key])
            elif key in ['execute_binance_orders', 'play_mp3_on_signal']: settings_to_save[key] = bool(settings_to_save[key])

        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings_to_save, f, indent=2, sort_keys=True)
    except Exception as e:
        print(f"{RED}[ERROR] Gagal menyimpan konfigurasi: {e}{RESET}")

# --- Fungsi Utilitas Email & Beep ---
def decode_mime_words(s):
    # (Fungsi ini tidak berubah)
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
    except Exception: return str(s) if isinstance(s, str) else "[DecodeErr]"

def get_text_from_email(msg):
    # (Fungsi ini tidak berubah)
    text_content = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdisp = str(part.get("Content-Disposition"))
            if ctype == "text/plain" and "attachment" not in cdisp.lower():
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    if payload: text_content += payload.decode(charset, errors='replace') + "\n"
                except Exception: pass
    else:
        if msg.get_content_type() == "text/plain":
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                if payload: text_content = payload.decode(charset, errors='replace')
            except Exception: pass
    return " ".join(text_content.split()).lower()

def trigger_beep(action):
    # (Fungsi ini tidak berubah, bisa tetap dipakai atau di-comment jika MP3 cukup)
    try:
        prefix = f"{MAGENTA}{BOLD}[BEEP]{RESET}" # Ubah prefix biar jelas
        if action == "buy":
            print(f"{prefix} Beep 'BUY'")
            subprocess.run(["beep", "-f", "1000", "-l", "300"], check=True, capture_output=True)
            time.sleep(0.1)
            subprocess.run(["beep", "-f", "1200", "-l", "200"], check=True, capture_output=True)
        elif action == "sell":
            print(f"{prefix} Beep 'SELL'")
            subprocess.run(["beep", "-f", "700", "-l", "500"], check=True, capture_output=True)
        else: print(f"{YELLOW}[WARN] Aksi beep '{action}' tidak dikenal.{RESET}")
    except FileNotFoundError:
        print(f"{YELLOW}[WARN] Perintah 'beep' tidak ditemukan. {DIM}(Coba: pkg install beep){RESET}")
    except Exception: pass # Jangan crash jika beep error

# --- Fungsi Pemutaran MP3 (BARU) ---
def play_action_sound(action, settings):
    """Memainkan file buy.mp3 atau sell.mp3."""
    if not settings.get("play_mp3_on_signal", False):
        # Fitur MP3 dinonaktifkan di setting
        return

    if not PLAYSOUND_AVAILABLE:
        # Library tidak ada, pesan error sudah muncul saat startup
        print(f"{YELLOW}[!] Fitur MP3 tidak jalan (library 'playsound' tidak ada).{RESET}")
        return

    action_lower = action.lower()
    if action_lower not in ["buy", "sell"]:
        print(f"{RED}[ERROR] Aksi '{action}' tidak valid untuk play sound.{RESET}")
        return

    filename = f"{action_lower}.mp3"
    # Dapatkan path absolut ke direktori script ini dijalankan
    script_dir = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join(script_dir, filename)

    prefix = f"{GREEN}{BOLD}[MP3]{RESET}"
    print(f"{prefix} Mencoba memainkan: {filename}...")

    try:
        playsound(filepath)
        print(f"{prefix} Selesai memainkan {filename}.")
    except Exception as e:
        # Tangani error spesifik dari playsound jika diketahui, atau general
        print(f"{RED}{BOLD}[X] Gagal memainkan MP3!{RESET}")
        # Cek apakah file ada (meskipun playsound mungkin punya error sendiri)
        if not os.path.exists(filepath):
            print(f"{RED}    └─ File '{filename}' tidak ditemukan di direktori script!{RESET}")
            print(f"{DIM}       Pastikan file ada di: {script_dir}{RESET}")
        else:
            # Error lain dari playsound (codec, device, dll)
            print(f"{RED}    └─ Error: {e}{RESET}")
            print(f"{DIM}       (Mungkin masalah codec, device audio, atau permission?){RESET}")
            if "codec" in str(e).lower():
                print(f"{DIM}       (Coba konversi MP3 ke format lain atau install codec: apt install ffmpeg){RESET}")

# --- Fungsi Eksekusi Binance (TIDAK DIPAKAI LANGSUNG LAGI, tapi biarkan ada) ---
def get_binance_client(settings):
    # (Fungsi ini tidak berubah, mungkin dipanggil di start_listening tapi tidak untuk eksekusi order)
    if not BINANCE_AVAILABLE: return None
    api_key = settings.get('binance_api_key')
    api_secret = settings.get('binance_api_secret')
    if not api_key or not api_secret:
        # Pesan ini mungkin tetap relevan jika user MENGAKTIFKAN execute_binance_orders
        # meskipun logic MP3 yang jalan duluan.
        if settings.get("execute_binance_orders"):
             print(f"{YELLOW}[WARN] Eksekusi Binance aktif tapi Kunci API belum diatur.{RESET}")
        return None
    try:
        print(f"{CYAN}[...] Menghubungkan ke Binance API (jika diperlukan)...{RESET}")
        client = Client(api_key, api_secret)
        client.ping()
        print(f"{GREEN}[OK] Koneksi Binance API berhasil.{RESET}")
        return client
    except (BinanceAPIException, BinanceOrderException) as e:
        print(f"{RED}{BOLD}[X] Gagal koneksi/autentikasi Binance!{RESET}")
        print(f"{RED}    └─ Error {e.status_code}/{e.code}: {e.message}{RESET}")
        # ... (pesan error detail lainnya tetap sama) ...
        return None
    except requests.exceptions.RequestException as e:
        print(f"{RED}{BOLD}[X] Gagal menghubungi Binance API (Network Error)!{RESET}")
        print(f"{RED}    └─ {e}{RESET}")
        return None
    except Exception as e:
        print(f"{RED}{BOLD}[X] Error tidak dikenal saat membuat Binance client:{RESET}")
        print(f"{RED}    └─ {e}{RESET}")
        return None

def execute_binance_order(client, settings, side):
    # (Fungsi ini TIDAK akan dipanggil dari process_email jika fokus ke MP3)
    # (Biarkan saja definisinya di sini)
    if not client: return False
    # Pengecekan ini penting jika fungsi ini *tetap* dipanggil dari tempat lain
    if not settings.get("execute_binance_orders", False):
        print(f"{YELLOW}[INFO] Panggilan execute_binance_order, tapi eksekusi dinonaktifkan di setting.{RESET}")
        return False # Safety check

    pair = settings.get('trading_pair', '').upper()
    if not pair: print(f"{RED}[!] Trading pair belum diatur.{RESET}"); return False

    # ... (Sisa logic eksekusi order tetap sama, tapi tidak akan terpicu dari email) ...
    order_details = {}
    action_desc = ""
    qty = 0
    is_buy = side == Client.SIDE_BUY

    try:
        if is_buy:
            qty = settings.get('buy_quote_quantity', 0.0)
            if qty <= 0: print(f"{RED}[!] Kuantitas Beli ({qty}) harus > 0.{RESET}"); return False
            order_details = {'symbol': pair, 'side': side, 'type': Client.ORDER_TYPE_MARKET, 'quoteOrderQty': qty}
            action_desc = f"BUY {qty} USDT senilai {pair}"
        else: # SELL
            qty = settings.get('sell_base_quantity', 0.0)
            if qty <= 0: print(f"{YELLOW}[!] Kuantitas Jual ({qty}) <= 0. Order dilewati.{RESET}"); return False
            order_details = {'symbol': pair, 'side': side, 'type': Client.ORDER_TYPE_MARKET, 'quantity': qty}
            action_desc = f"SELL {qty} {pair.replace('USDT', '')}"

        print(f"{MAGENTA}{BOLD}[BINANCE ACTION]{RESET} Eksekusi: {action_desc}...")
        order_result = client.create_order(**order_details)
        print(f"{GREEN}{BOLD}[SUCCESS]{RESET} Order {side} {pair} berhasil!")
        # ... (Sisa print hasil order) ...
        return True
    except (BinanceAPIException, BinanceOrderException) as e:
        print(f"{RED}{BOLD}[X] Gagal eksekusi order Binance!{RESET}")
        print(f"{RED}    └─ Error {e.status_code}/{e.code}: {e.message}{RESET}")
        # ... (Sisa pesan error detail) ...
        return False
    except requests.exceptions.RequestException as e:
         print(f"{RED}{BOLD}[X] Gagal mengirim order (Network Error)!{RESET}")
         print(f"{RED}    └─ {e}{RESET}")
         return False
    except Exception as e:
        print(f"{RED}{BOLD}[X] Error tidak dikenal saat eksekusi order:{RESET}")
        print(f"{RED}    └─ {e}{RESET}")
        return False


# --- Fungsi Pemrosesan Email (DIMODIFIKASI) ---
def process_email(mail, email_id, settings, binance_client): # binance_client tetap di-pass, just in case
    global running
    if not running: return

    target_kw = settings['target_keyword'].lower()
    trigger_kw = settings['trigger_keyword'].lower()
    email_id_str = email_id.decode('utf-8')
    log_prefix = f"[{BLUE}EMAIL {email_id_str}{RESET}]"

    try:
        status, data = mail.fetch(email_id, "(RFC822)")
        if status != 'OK':
            print(f"{log_prefix} {RED}Gagal fetch: {status}{RESET}")
            return

        msg = email.message_from_bytes(data[0][1])
        subject = decode_mime_words(msg["Subject"])
        sender = decode_mime_words(msg["From"])
        timestamp = datetime.datetime.now().strftime("%H:%M")

        print(f"\n{CYAN}╭─ Email Baru [{timestamp}] {'─'*(get_terminal_width() - 22)}{RESET}") # Sesuaikan panjang garis
        print(f"{CYAN}│{RESET} {DIM}ID    :{RESET} {email_id_str}")
        print(f"{CYAN}│{RESET} {DIM}Dari  :{RESET} {sender[:40]}{'...' if len(sender)>40 else ''}")
        print(f"{CYAN}│{RESET} {DIM}Subjek:{RESET} {subject[:50]}{'...' if len(subject)>50 else ''}")

        body = get_text_from_email(msg)
        full_content = (subject.lower() + " " + body)

        if target_kw in full_content:
            print(f"{CYAN}│{RESET} {GREEN}[✓] Target '{settings['target_keyword']}' ditemukan.{RESET}")
            try:
                target_idx = full_content.find(target_kw)
                trigger_idx = full_content.find(trigger_kw, target_idx + len(target_kw))

                if trigger_idx != -1:
                    text_after = full_content[trigger_idx + len(trigger_kw):].lstrip()
                    action_word = text_after.split(maxsplit=1)[0].strip('.,!?:;()[]{}').lower() if text_after else ""

                    if action_word in ["buy", "sell"]:
                        print(f"{CYAN}│{RESET} {GREEN}[✓] Trigger '{settings['trigger_keyword']}' -> Aksi: {BOLD}{action_word.upper()}{RESET}")

                        # --- Trigger Aksi: Beep dan/atau MP3 ---
                        trigger_beep(action_word) # Tetap panggil beep jika 'beep' terinstall
                        play_action_sound(action_word, settings) # Panggil fungsi MP3 BARU

                        # --- Bagian Eksekusi Binance DI-SKIP ---
                        # execute_binance = settings.get("execute_binance_orders", False)
                        # if execute_binance and binance_client:
                        #     print(f"{CYAN}│{RESET} {DIM}(Eksekusi Binance aktif, tapi script ini fokus ke MP3){RESET}")
                        #     # Jika INGIN menjalankan KEDUANYA (MP3 dan Order), uncomment baris di bawah
                        #     # print(f"{CYAN}│{RESET} {MAGENTA}[!] Mencoba eksekusi Binance juga...{RESET}")
                        #     # execute_binance_order(binance_client, settings, Client.SIDE_BUY if action_word == "buy" else Client.SIDE_SELL)
                        # elif execute_binance and not binance_client:
                        #      print(f"{CYAN}│{RESET} {YELLOW}[!] Eksekusi Binance aktif, tapi koneksi Binance bermasalah.{RESET}")

                    elif action_word:
                        print(f"{CYAN}│{RESET} {YELLOW}[?] Trigger ditemukan, tapi kata '{action_word}' bukan 'buy'/'sell'.{RESET}")
                    else:
                        print(f"{CYAN}│{RESET} {YELLOW}[?] Trigger ditemukan, tapi tidak ada kata aksi setelahnya.{RESET}")
                else:
                     print(f"{CYAN}│{RESET} {YELLOW}[?] Target ditemukan, tapi trigger '{settings['trigger_keyword']}' tidak ada SETELAHNYA.{RESET}")
            except Exception as e:
                 print(f"{CYAN}│{RESET} {RED}[X] Error parsing setelah trigger: {e}{RESET}")
                 traceback.print_exc() # Tampilkan detail error parsing
        else:
             print(f"{CYAN}│{RESET} {BLUE}[-] Target '{settings['target_keyword']}' tidak ditemukan.{RESET}")

        # Tandai sudah dibaca
        try:
            mail.store(email_id, '+FLAGS', '\\Seen')
            print(f"{CYAN}│{RESET} {DIM}Email ditandai sudah dibaca.{RESET}")
        except Exception as e:
            print(f"{CYAN}│{RESET} {RED}[X] Gagal tandai dibaca: {e}{RESET}")

        print(f"{CYAN}╰{'─' * (get_terminal_width() - 1)}{RESET}") # Footer akhir

    except Exception as e:
        print(f"{log_prefix} {RED}{BOLD}FATAL Error proses email:{RESET}")
        traceback.print_exc()


# --- Fungsi Listening Utama ---
def start_listening(settings):
    global running
    running = True
    mail = None
    # Client Binance mungkin masih dibuat jika setting 'execute_binance_orders' aktif,
    # tapi tidak akan digunakan untuk eksekusi dari process_email
    binance_client = None
    last_check_time = time.time()
    consecutive_errors = 0
    max_errors = 5 # Mungkin tidak relevan jika error koneksi IMAP langsung retry
    wait_time = 2 # Detik, untuk backoff awal
    long_wait = 60 # Detik, batas backoff maksimal

    # --- Setup Binance (Hanya jika setting execute_binance_orders AKTIF) ---
    # Ini berguna jika suatu saat ingin MENGGABUNGKAN MP3 dan Order, atau switch kembali
    execute_binance = settings.get("execute_binance_orders", False)
    mp3_active = settings.get("play_mp3_on_signal", True)

    if execute_binance:
        if not BINANCE_AVAILABLE:
            print(f"{RED}{BOLD}[X] FATAL: Eksekusi Binance diaktifkan tapi library tidak ada!{RESET}")
            print(f"{DIM}   Nonaktifkan 'Eksekusi Order' di Pengaturan atau install library.{RESET}")
            running = False; return # Jangan lanjut jika user ingin eksekusi tapi library tidak ada
        print_separator('─', CYAN)
        print_centered("Inisialisasi Koneksi Binance (Karena Setting Aktif)", CYAN, BOLD)
        binance_client = get_binance_client(settings) # Tetap coba konek
        if not binance_client:
            print(f"{YELLOW}[!] Gagal koneksi awal Binance. {DIM}(Meskipun tidak eksekusi order saat ini){RESET}")
        print_separator('─', CYAN)
        time.sleep(1)
    elif BINANCE_AVAILABLE: # Library ada, tapi eksekusi nonaktif
         print_separator('─', YELLOW)
         print_centered("Eksekusi Order Binance: NONAKTIF", YELLOW, BOLD)
         print(f"{DIM}   (Script akan fokus pada pemutaran MP3 jika diaktifkan){RESET}")
         print_separator('─', YELLOW)
         time.sleep(1)

    # Info Mode MP3
    print_separator('─', GREEN if mp3_active else YELLOW)
    if mp3_active:
        print_centered("Mode Pemutaran MP3: AKTIF", GREEN, BOLD)
        if not PLAYSOUND_AVAILABLE: print(f"{YELLOW}{DIM}   (Tapi library 'playsound' tidak ada, cek warning di atas){RESET}")
        print(f"{DIM}   (Akan memainkan buy.mp3/sell.mp3 jika sinyal terdeteksi){RESET}")
    else:
        print_centered("Mode Pemutaran MP3: NONAKTIF", YELLOW, BOLD)
    print_separator('─', GREEN if mp3_active else YELLOW)
    time.sleep(1)


    # --- Loop Utama ---
    print(f"\n{GREEN}{BOLD}Memulai listener... (Ctrl+C untuk berhenti){RESET}")
    wait_indicator_chars = ['∙', '·', '˙', ' ']
    indicator_idx = 0

    while running:
        try:
            # --- Koneksi IMAP ---
            if not mail or mail.state != 'SELECTED':
                print(f"\n{CYAN}[...] Menghubungkan ke IMAP {settings['imap_server']}...{RESET}")
                try:
                    # Timeout koneksi 20 detik, operasi lain mungkin lebih pendek by default
                    mail = imaplib.IMAP4_SSL(settings['imap_server'], timeout=20)
                    rv, desc = mail.login(settings['email_address'], settings['app_password'])
                    if rv != 'OK': raise imaplib.IMAP4.error(f"Login gagal: {desc}")
                    rv, data = mail.select("inbox")
                    if rv != 'OK': raise imaplib.IMAP4.error(f"Gagal select inbox: {data}")
                    print(f"{GREEN}[OK] Terhubung & Login ke {settings['email_address']}. Inbox dipilih. Mendengarkan...{RESET}")
                    consecutive_errors = 0; wait_time = 2 # Reset error & backoff
                except (imaplib.IMAP4.error, OSError, socket.error, socket.timeout) as login_err: # Tambah socket.timeout
                    print(f"{RED}{BOLD}[X] Gagal koneksi/login IMAP!{RESET}")
                    print(f"{RED}    └─ {login_err}{RESET}")
                    if "authentication failed" in str(login_err).lower():
                         print(f"{YELLOW}       ↳ Periksa Email/App Password & Izin IMAP.{RESET}")
                         print(f"{RED}{BOLD}       Program berhenti karena otentikasi gagal.{RESET}")
                         running = False # Berhenti total jika otentikasi gagal
                    else:
                        print(f"{YELLOW}       ↳ Periksa server IMAP, port, & koneksi internet.{RESET}")
                        consecutive_errors += 1
                    if mail: # Coba logout jika instance sempat dibuat
                        try: mail.logout()
                        except Exception: pass
                    mail = None # Pastikan state bersih
                    # Jangan break, biarkan loop luar handle backoff/exit

            # --- Loop Cek Email & Koneksi Aktif ---
            if mail and mail.state == 'SELECTED':
                # Loop ini akan terus berjalan sampai koneksi putus atau program dihentikan
                while running:
                    current_time = time.time()
                    # Cek apakah sudah waktunya check email lagi
                    if current_time - last_check_time < settings['check_interval_seconds']:
                        time.sleep(0.5) # Tidur sebentar agar tidak sibuk terus
                        continue # Kembali ke awal loop inner

                    # Jaga Koneksi dengan NOOP (atau IDLE jika didukung server & diinginkan)
                    try:
                        # print(f"{DIM}Sending NOOP...{RESET}", end='\r') # Debug
                        status, _ = mail.noop()
                        # print(f"{DIM}NOOP status: {status}   {RESET}", end='\r') # Debug
                        if status != 'OK':
                            raise imaplib.IMAP4.abort(f"NOOP gagal, status: {status}")
                    except (imaplib.IMAP4.abort, imaplib.IMAP4.readonly, BrokenPipeError, OSError, socket.error, socket.timeout) as noop_err:
                        print(f"\n{YELLOW}[!] Koneksi IMAP terputus ({type(noop_err).__name__}). Mencoba reconnect...{RESET}")
                        try: mail.logout() # Coba logout bersih
                        except Exception: pass
                        mail = None # Reset state
                        consecutive_errors += 1
                        break # Keluar dari loop inner untuk reconnect di loop outer

                    # Binance Ping Check (opsional, jika client ada dan setting eksekusi aktif)
                    if execute_binance and binance_client and current_time - getattr(binance_client, '_last_ping', 0) > 180: # Cek tiap 3 menit
                         try:
                             # print(f"{DIM}Pinging Binance...{RESET}", end='\r') # Debug
                             binance_client.ping()
                             setattr(binance_client, '_last_ping', current_time)
                             # print(f"{DIM}Ping Binance OK.    {RESET}", end='\r') # Debug
                         except Exception as ping_err:
                             print(f"\n{YELLOW}[!] Ping Binance gagal ({ping_err}). Mencoba reconnect Binance...{RESET}")
                             binance_client = get_binance_client(settings) # Coba buat ulang client
                             setattr(binance_client, '_last_ping', current_time) # Update waktu coba

                    # Cek Email Baru (UNSEEN)
                    try:
                        # print(f"{DIM}Searching UNSEEN...{RESET}", end='\r') # Debug
                        status, messages = mail.search(None, '(UNSEEN)')
                        # print(f"{DIM}Search status: {status}   {RESET}", end='\r') # Debug
                        if status != 'OK':
                            print(f"\n{RED}[X] Gagal cari email UNSEEN: Status {status}, Pesan: {messages}. Reconnecting...{RESET}")
                            try: mail.logout()
                            except Exception: pass
                            mail = None; consecutive_errors += 1
                            break # Reconnect

                        email_ids = messages[0].split()
                        if email_ids:
                            num = len(email_ids)
                            print(f"\n{GREEN}{BOLD}[!] {num} email baru ditemukan! Memproses...{RESET}")
                            # Proses satu per satu
                            for i, eid in enumerate(email_ids):
                                if not running: break # Cek jika Ctrl+C ditekan saat proses batch
                                print(f"{DIM}--- Proses email {i+1}/{num} (ID: {eid.decode()}) ---{RESET}")
                                process_email(mail, eid, settings, binance_client)
                            if not running: break
                            print(f"{GREEN}[OK] Selesai proses {num} email. Mendengarkan lagi...{RESET}")
                        else:
                            # Tampilkan indikator tunggu jika tidak ada email baru
                            indicator_idx = (indicator_idx + 1) % len(wait_indicator_chars)
                            wait_char = wait_indicator_chars[indicator_idx]
                            print(f"{BLUE}[{wait_char}] Menunggu email baru... {DIM}(Interval: {settings['check_interval_seconds']}s){RESET}   ", end='\r', flush=True)

                    except (imaplib.IMAP4.error, OSError, socket.error, socket.timeout) as search_err:
                         print(f"\n{RED}[X] Error saat mencari email: {search_err}. Reconnecting...{RESET}")
                         try: mail.logout()
                         except Exception: pass
                         mail = None; consecutive_errors += 1
                         break # Reconnect

                    last_check_time = current_time
                    if not running: break # Cek lagi sebelum akhir loop inner

                # Keluar loop inner (jika running=False atau ada error yg butuh reconnect)
                # Jika mail masih ada & state selected, coba close inbox sebelum reconnect/exit
                if mail and mail.state == 'SELECTED':
                   try:
                       # print(f"{DIM}Closing inbox...{RESET}") # Debug
                       mail.close()
                   except Exception as close_err:
                       # print(f"{YELLOW}[WARN] Gagal close inbox: {close_err}{RESET}") # Debug
                       pass # Mungkin koneksi sudah mati

        # --- Exception Handling Loop Luar (Error koneksi/login awal, atau error tak terduga) ---
        except (imaplib.IMAP4.error, imaplib.IMAP4.abort, socket.error, socket.timeout, OSError) as e:
             # Tangani error yang terjadi SEBELUM masuk loop inner (misal saat login/select)
             # atau error parah lainnya
             print(f"\n{RED}{BOLD}[X] Error IMAP/Network di loop utama: {type(e).__name__} - {e}{RESET}")
             consecutive_errors += 1
             # Jika error login gagal otentikasi, 'running' sudah False, loop akan berhenti
        except Exception as e:
             print(f"\n{RED}{BOLD}[X] Error tak terduga di loop utama:{RESET}")
             traceback.print_exc()
             consecutive_errors += 1

        # --- Cleanup & Backoff ---
        finally:
            # Pastikan logout jika instance mail masih ada (meskipun mungkin error)
            if mail and mail.state != 'LOGOUT':
                # print(f"{DIM}Final logout attempt...{RESET}") # Debug
                try: mail.logout()
                except Exception: pass
            mail = None # Penting untuk memicu reconnect di iterasi berikutnya

            if not running:
                print(f"{YELLOW}[INFO] Loop utama berhenti.{RESET}")
                break # Keluar dari while running

            # Logika Backoff jika ada error
            if consecutive_errors > 0:
                # Exponential backoff: 2, 4, 8, 16, 32, max 60 detik
                current_wait = wait_time * (2**(consecutive_errors-1))
                current_wait = min(current_wait, long_wait) # Batasi waktu tunggu maks
                print(f"{YELLOW}[!] Terjadi error ({consecutive_errors}x berturut-turut). Mencoba lagi dalam {current_wait:.0f} detik...{RESET}")
                # Tidur dengan cara yang bisa diinterupsi Ctrl+C
                sleep_start = time.time()
                while time.time() - sleep_start < current_wait:
                     if not running: break # Cek flag 'running' secara berkala
                     time.sleep(0.5)
                if not running: break # Keluar jika dihentikan saat backoff
            else:
                 # Jeda singkat jika tidak ada error (sudah ada sleep di loop inner)
                 pass
                 # time.sleep(0.1) # Opsi: jeda sangat singkat antar loop utama

    print(f"\n{YELLOW}{BOLD}[INFO] Listener dihentikan.{RESET}")

# --- Fungsi Menu Pengaturan (Tambahkan Opsi MP3) ---
def show_settings(settings):
    while True:
        clear_screen()
        print_header("Pengaturan")

        print(f"\n{BOLD}{CYAN} E M A I L {RESET}")
        print(f"{DIM}─────────────────────────────{RESET}")
        print(f" {CYAN}1. Alamat Email{RESET}   : {settings['email_address'] or f'{DIM}[Kosong]{RESET}'}")
        app_pass_disp = f"{GREEN}Terisi{RESET}" if settings['app_password'] else f"{RED}Kosong{RESET}"
        print(f" {CYAN}2. App Password{RESET}   : {app_pass_disp}")
        print(f" {CYAN}3. Server IMAP{RESET}    : {settings['imap_server']}")
        print(f" {CYAN}4. Interval Cek{RESET}   : {settings['check_interval_seconds']} detik")
        print(f" {CYAN}5. Keyword Target{RESET} : '{settings['target_keyword']}'")
        print(f" {CYAN}6. Keyword Trigger{RESET}: '{settings['trigger_keyword']}'")

        print(f"\n{BOLD}{YELLOW} M P 3   S I G N A L {RESET}")
        print(f"{DIM}─────────────────────────────{RESET}")
        mp3_status = f"{GREEN}{BOLD}Aktif{RESET}" if settings['play_mp3_on_signal'] else f"{YELLOW}Nonaktif{RESET}"
        print(f" {YELLOW}7. Mainkan MP3?{RESET}   : {mp3_status}")
        if settings['play_mp3_on_signal']:
             lib_stat = f"{GREEN}OK{RESET}" if PLAYSOUND_AVAILABLE else f"{RED}Tidak Ada!{RESET}"
             print(f"   {DIM}└─ Library 'playsound': {lib_stat} {DIM} (Perlu: buy.mp3 & sell.mp3){RESET}")

        print(f"\n{BOLD}{CYAN} B I N A N C E (Opsional) {RESET}")
        print(f"{DIM}─────────────────────────────{RESET}")
        if BINANCE_AVAILABLE:
            print(f" {DIM}Library Status{RESET}     : {GREEN}Terinstall{RESET}")
            api_key_disp = f"{GREEN}Terisi{RESET}" if settings['binance_api_key'] else f"{RED}Kosong{RESET}"
            api_sec_disp = f"{GREEN}Terisi{RESET}" if settings['binance_api_secret'] else f"{RED}Kosong{RESET}"
            print(f" {CYAN}8. API Key{RESET}        : {api_key_disp}")
            print(f" {CYAN}9. API Secret{RESET}     : {api_sec_disp}")
            print(f" {CYAN}10. Trading Pair{RESET}   : {settings['trading_pair'] or f'{DIM}[Kosong]{RESET}'}")
            print(f" {CYAN}11. Buy Quote Qty{RESET} : {settings['buy_quote_quantity']} {DIM}(USDT){RESET}")
            print(f" {CYAN}12. Sell Base Qty{RESET} : {settings['sell_base_quantity']} {DIM}(Base){RESET}")
            exec_status = f"{GREEN}{BOLD}Aktif{RESET}" if settings['execute_binance_orders'] else f"{YELLOW}Nonaktif{RESET}"
            print(f" {CYAN}13. Eksekusi Order{RESET}  : {exec_status} {DIM}(MP3 akan tetap main jika aktif){RESET}")
        else:
             print(f" {DIM}Library Status{RESET}     : {RED}Tidak Terinstall{RESET}")
             print(f" {DIM}(Install: pip install python-binance requests){RESET}")

        print_separator(color=MAGENTA)

        # --- Opsi Menu Pengaturan ---
        if INQUIRER_AVAILABLE:
            questions = [
                inquirer.List('action',
                              message=f"{YELLOW}Pilih Aksi{RESET}",
                              choices=[('✏️  Edit Pengaturan', 'edit'), ('💾 Simpan & Kembali', 'back')],
                              carousel=True)
            ]
            try:
                 answers = inquirer.prompt(questions, theme=InquirerTheme())
                 choice = answers['action'] if answers else 'back'
            except Exception as e: print(f"{RED}Error menu: {e}{RESET}"); choice = 'back'
            except KeyboardInterrupt: print(f"\n{YELLOW}Edit dibatalkan.{RESET}"); choice = 'back'; time.sleep(1)
        else: # Fallback
             choice_input = input("Pilih (E=Edit, K=Kembali): ").lower().strip()
             choice = 'edit' if choice_input == 'e' else 'back'

        # --- Proses Pilihan Edit ---
        if choice == 'edit':
            print(f"\n{BOLD}{MAGENTA}--- Edit Pengaturan ---{RESET}")
            print(f"{DIM}(Kosongkan input untuk skip / tidak ubah){RESET}")

            # Edit Email
            print(f"\n{CYAN}--- Email ---{RESET}")
            # (Input 1-6 sama seperti sebelumnya)
            if val := input(f" 1. Email [{settings['email_address']}]: ").strip(): settings['email_address'] = val
            print(f" 2. App Password (input tersembunyi): ", end='', flush=True)
            try: pwd = getpass.getpass("")
            except Exception: pwd = input(" App Password [***]: ").strip()
            if pwd: settings['app_password'] = pwd; print(f"{GREEN}OK{RESET}")
            else: print(f"{DIM}Skip{RESET}")
            if val := input(f" 3. IMAP Server [{settings['imap_server']}]: ").strip(): settings['imap_server'] = val
            while True:
                val_str = input(f" 4. Interval (detik) [{settings['check_interval_seconds']}], min 5: ").strip()
                if not val_str: break
                try: iv = int(val_str); settings['check_interval_seconds'] = max(5, iv); break
                except ValueError: print(f"{RED}[!] Angka bulat.{RESET}")
            if val := input(f" 5. Keyword Target [{settings['target_keyword']}]: ").strip(): settings['target_keyword'] = val
            if val := input(f" 6. Keyword Trigger [{settings['trigger_keyword']}]: ").strip(): settings['trigger_keyword'] = val

            # Edit MP3 Toggle
            print(f"\n{YELLOW}--- MP3 Signal ---{RESET}")
            while True:
                 curr = settings['play_mp3_on_signal']
                 prompt = f"{GREEN}Aktif{RESET}" if curr else f"{YELLOW}Nonaktif{RESET}"
                 val_str = input(f" 7. Mainkan MP3? ({prompt}) [y/n]: ").lower().strip()
                 if not val_str: break
                 if val_str == 'y': settings['play_mp3_on_signal'] = True; break
                 elif val_str == 'n': settings['play_mp3_on_signal'] = False; break
                 else: print(f"{RED}[!] y/n saja.{RESET}")

            # Edit Binance (Opsional)
            print(f"\n{CYAN}--- Binance (Opsional) ---{RESET}")
            if not BINANCE_AVAILABLE: print(f"{YELLOW}(Library tidak ada, setting Binance mungkin tidak relevan){RESET}")
            # (Input 8-12 sama seperti sebelumnya, hanya nomornya geser)
            if val := input(f" 8. API Key [***]: ").strip(): settings['binance_api_key'] = val
            print(f" 9. API Secret (input tersembunyi): ", end='', flush=True)
            try: sec = getpass.getpass("")
            except Exception: sec = input(" API Secret [***]: ").strip()
            if sec: settings['binance_api_secret'] = sec; print(f"{GREEN}OK{RESET}")
            else: print(f"{DIM}Skip{RESET}")
            if val := input(f"10. Trading Pair [{settings['trading_pair']}]: ").strip().upper(): settings['trading_pair'] = val
            while True:
                 val_str = input(f"11. Buy Quote Qty [{settings['buy_quote_quantity']}], >= 0: ").strip()
                 if not val_str: break
                 try: settings['buy_quote_quantity'] = max(0.0, float(val_str)); break
                 except ValueError: print(f"{RED}[!] Angka desimal.{RESET}")
            while True:
                 val_str = input(f"12. Sell Base Qty [{settings['sell_base_quantity']}], >= 0: ").strip()
                 if not val_str: break
                 try: settings['sell_base_quantity'] = max(0.0, float(val_str)); break
                 except ValueError: print(f"{RED}[!] Angka desimal.{RESET}")
            while True:
                 curr = settings['execute_binance_orders']
                 prompt = f"{GREEN}Aktif{RESET}" if curr else f"{YELLOW}Nonaktif{RESET}"
                 val_str = input(f"13. Eksekusi Order Binance? ({prompt}) [y/n]: ").lower().strip()
                 if not val_str: break
                 if val_str == 'y':
                     if BINANCE_AVAILABLE: settings['execute_binance_orders'] = True; break
                     else: print(f"{RED}[!] Library Binance tidak ada! Tidak bisa diaktifkan.{RESET}"); break
                 elif val_str == 'n': settings['execute_binance_orders'] = False; break
                 else: print(f"{RED}[!] y/n saja.{RESET}")

            # Simpan otomatis setelah edit selesai
            save_settings(settings)
            print(f"\n{GREEN}{BOLD}[OK] Pengaturan disimpan!{RESET}")
            input(f"{DIM}Tekan Enter untuk kembali...{RESET}")
            # Loop akan kembali ke awal show_settings

        elif choice == 'back':
            save_settings(settings) # Simpan perubahan terakhir
            print(f"\n{GREEN}Pengaturan disimpan. Kembali ke Menu Utama...{RESET}")
            time.sleep(1.5)
            break

# --- Fungsi Menu Utama (Update Status) ---
def main_menu():
    settings = load_settings()

    while True:
        clear_screen()
        print_header("Exora AI - Email Listener (MP3 Mode)") # Update Judul

        # --- Tampilkan Status Ringkas ---
        print(f"\n{BOLD}{CYAN} S T A T U S {RESET}")
        print(f"{DIM}─────────────────────────────{RESET}")

        # Email Status
        email_ok = bool(settings.get('email_address'))
        pass_ok = bool(settings.get('app_password'))
        print(f" {CYAN}Email Listener:{RESET}")
        print(f"   ├─ Config: Email [{GREEN if email_ok else RED}{'✓' if email_ok else 'X'}{RESET}] | App Pass [{GREEN if pass_ok else RED}{'✓' if pass_ok else 'X'}{RESET}]")
        print(f"   └─ Server: {settings.get('imap_server', '?')}, Interval: {settings.get('check_interval_seconds')}s")

        # MP3 Status
        print(f" {YELLOW}MP3 Signal:{RESET}")
        mp3_active = settings.get("play_mp3_on_signal", True)
        mp3_status = f"{GREEN}{BOLD}AKTIF{RESET}" if mp3_active else f"{YELLOW}NONAKTIF{RESET}"
        print(f"   ├─ Status  : {mp3_status}")
        lib_stat = f"{GREEN}✓{RESET}" if PLAYSOUND_AVAILABLE else f"{RED}X{RESET}"
        file_check = "??" # Nanti bisa tambah cek file jika perlu
        print(f"   └─ Req     : Library {lib_stat} | Files (buy/sell.mp3) {DIM}[Cek Manual]{RESET}")
        if mp3_active and not PLAYSOUND_AVAILABLE:
             print(f"     {RED}{DIM}↳ Library 'playsound' tidak ada! Install: pip install playsound==1.2.2{RESET}")

        # Binance Status (Tetap tampilkan jika library ada)
        print(f" {CYAN}Binance Order (Opsional):{RESET}")
        if BINANCE_AVAILABLE:
            lib_status = f"{GREEN}✓ Terinstall{RESET}"
            exec_active = settings.get("execute_binance_orders", False)
            exec_status = f"{GREEN}{BOLD}AKTIF{RESET}" if exec_active else f"{YELLOW}NONAKTIF{RESET}"
            api_ok = bool(settings.get('binance_api_key'))
            sec_ok = bool(settings.get('binance_api_secret'))

            print(f"   ├─ Library : {lib_status}")
            print(f"   ├─ Akun    : API [{GREEN if api_ok else RED}{'✓' if api_ok else 'X'}{RESET}] | Secret [{GREEN if sec_ok else RED}{'✓' if sec_ok else 'X'}{RESET}]")
            print(f"   └─ Eksekusi: {exec_status} {DIM}(Prioritas MP3 jika aktif){RESET}")
        else:
            lib_status = f"{RED}X Tidak Terinstall{RESET}"
            print(f"   └─ Library : {lib_status}")

        print_separator(color=MAGENTA)

        # --- Pilihan Menu Utama ---
        menu_prompt = f"{YELLOW}Pilih Menu {DIM}(↑/↓ Enter){RESET}" if INQUIRER_AVAILABLE else f"{YELLOW}Ketik Pilihan:{RESET}"

        if INQUIRER_AVAILABLE:
            choices = []
            # Opsi Mulai
            start_label = "▶️  Mulai Listener"
            start_mode = f" {DIM}("
            if mp3_active: start_mode += f"{YELLOW}MP3{DIM}"
            if execute_binance and BINANCE_AVAILABLE:
                if mp3_active: start_mode += " & "
                start_mode += f"{CYAN}Binance{DIM}"
            elif not mp3_active and not execute_binance:
                start_mode += "Email Only" # Jika keduanya nonaktif
            if not mp3_active and execute_binance and not BINANCE_AVAILABLE:
                start_mode += f"{RED}Binance Error{DIM}" # Jika mau eksekusi tapi lib ga ada

            start_mode += f"){RESET}"
            choices.append((start_label + start_mode, 'start'))
            choices.append(('⚙️  Pengaturan', 'settings'))
            choices.append(('🚪 Keluar', 'exit'))

            questions = [inquirer.List('main_choice', message=menu_prompt, choices=choices, carousel=True)]
            try:
                answers = inquirer.prompt(questions, theme=InquirerTheme())
                choice_key = answers['main_choice'] if answers else 'exit'
            except Exception as e: print(f"{RED}Menu error: {e}{RESET}"); choice_key = 'exit'
            except KeyboardInterrupt: print(f"\n{YELLOW}Keluar...{RESET}"); choice_key = 'exit'; time.sleep(1)
        else: # Fallback
            print(f"\n{menu_prompt}")
            print(f" 1. Mulai Listener")
            print(f" 2. Pengaturan")
            print(f" 3. Keluar")
            print_separator(color=MAGENTA)
            choice_input = input("Pilihan (1/2/3): ").strip()
            choice_map = {'1': 'start', '2': 'settings', '3': 'exit'}
            choice_key = choice_map.get(choice_input, 'invalid')

        # --- Proses Pilihan ---
        if choice_key == 'start':
            print_separator()
            errors = []
            # Validasi Email tetap wajib
            if not settings.get('email_address') or not settings.get('app_password'):
                errors.append("Email/App Password belum lengkap.")

            # Validasi MP3 jika aktif
            mp3_active = settings.get("play_mp3_on_signal", True)
            if mp3_active and not PLAYSOUND_AVAILABLE:
                errors.append("Mode MP3 aktif tapi library 'playsound' tidak ditemukan.")
                # Bisa tambah cek file mp3 jika mau:
                # script_dir = os.path.dirname(os.path.abspath(__file__))
                # if not os.path.exists(os.path.join(script_dir, 'buy.mp3')): errors.append("File buy.mp3 tidak ditemukan.")
                # if not os.path.exists(os.path.join(script_dir, 'sell.mp3')): errors.append("File sell.mp3 tidak ditemukan.")

            # Validasi Binance jika eksekusi aktif (meskipun MP3 prioritas)
            execute_binance = settings.get("execute_binance_orders", False)
            if execute_binance:
                if not BINANCE_AVAILABLE: errors.append("Eksekusi Binance aktif tapi library tidak ada.")
                else:
                    # Cek API/Secret hanya jika eksekusi Binance benar-benar aktif
                    if not settings.get('binance_api_key'): errors.append("Eksekusi Binance aktif tapi API Key kosong.")
                    if not settings.get('binance_api_secret'): errors.append("Eksekusi Binance aktif tapi API Secret kosong.")
                    # Cek pair/qty tetap penting jika eksekusi aktif
                    # if not settings.get('trading_pair'): errors.append("Binance Trading Pair kosong.")
                    # if settings.get('buy_quote_quantity', 0) <= 0: errors.append("Binance Buy Qty harus > 0.")

            if errors:
                print(f"\n{BOLD}{RED}--- TIDAK BISA MEMULAI ---{RESET}")
                for i, err in enumerate(errors): print(f" {RED}{i+1}. {err}{RESET}")
                print(f"\n{YELLOW}Perbaiki di menu 'Pengaturan' atau install library yang diperlukan.{RESET}")
                input(f"{DIM}Tekan Enter untuk kembali...{RESET}")
            else:
                clear_screen()
                mode = []
                if mp3_active: mode.append("MP3 Signal")
                if execute_binance and BINANCE_AVAILABLE: mode.append("Binance Order")
                if not mode: mode_str = "Email Listener Only"
                else: mode_str = " & ".join(mode)

                print_header(f"Memulai Mode: {mode_str}")
                start_listening(settings)
                # Kembali ke menu setelah listener berhenti
                print(f"\n{YELLOW}[INFO] Kembali ke Menu Utama...{RESET}")
                time.sleep(2)

        elif choice_key == 'settings':
            show_settings(settings)
            settings = load_settings() # Muat ulang jika ada perubahan

        elif choice_key == 'exit':
            print(f"\n{CYAN}Terima kasih! Sampai jumpa lagi 👋{RESET}")
            sys.exit(0)

        elif choice_key == 'invalid':
            print(f"{RED}[!] Pilihan tidak valid.{RESET}")
            time.sleep(1)

# --- Entry Point ---
if __name__ == "__main__":
    if sys.version_info < (3, 6):
        print("Error: Butuh Python 3.6+"); sys.exit(1)

    # Pastikan user tahu cara install playsound jika belum ada
    if not PLAYSOUND_AVAILABLE:
        print(f"{YELLOW}Tips: Untuk fitur MP3, jalankan: {RESET}pip install playsound==1.2.2")
        print(f"{DIM}(Versi 1.2.2 seringkali lebih stabil daripada versi terbaru){RESET}")
        time.sleep(2) # Beri waktu user membaca sebelum menu muncul

    try:
        main_menu()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Program dihentikan paksa.{RESET}"); sys.exit(1)
    except Exception as e:
        # Clear screen mungkin menyembunyikan error penting jika terjadi SEBELUM menu tampil
        # clear_screen()
        print(f"\n{BOLD}{RED}===== ERROR KRITIS TAK TERDUGA ====={RESET}")
        traceback.print_exc()
        print(f"\n{RED}Error: {e}{RESET}")
        input("Tekan Enter untuk keluar...")
        sys.exit(1)
