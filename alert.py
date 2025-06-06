# -*- coding: utf-8 -*-
import imaplib
import email
from email.header import decode_header
import time
import datetime # Untuk timestamp
import subprocess # Tetap dibutuhkan untuk termux-media-player
import json
import os
import getpass
import sys
import signal # Untuk menangani Ctrl+C
import traceback # Untuk mencetak traceback error
import socket # Untuk error koneksi IMAP
import shutil # Untuk mendapatkan lebar terminal & cek command

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

# --- Konfigurasi & Variabel Global ---
CONFIG_FILE = "config.json"
DEFAULT_SETTINGS = {
    "email_address": "", "app_password": "", "imap_server": "imap.gmail.com",
    "check_interval_seconds": 10, "target_keyword": "Exora AI", "trigger_keyword": "order",
    "play_mp3_on_signal": True
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
    # Coba hentikan media player jika sedang jalan (opsional)
    try:
        subprocess.run(["termux-media-player", "stop"], capture_output=True, timeout=1)
    except Exception:
        pass # Abaikan jika gagal
    running = False
    time.sleep(1.5)
    print(f"{RED}{BOLD}[EXIT] Keluar dari program.{RESET}")
    sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)

# --- Fungsi Utilitas Tampilan ---
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
                for key in DEFAULT_SETTINGS:
                    if key in loaded_settings:
                        settings[key] = loaded_settings[key]

                settings["check_interval_seconds"] = int(settings.get("check_interval_seconds", 10))
                if settings["check_interval_seconds"] < 5: settings["check_interval_seconds"] = 5
                settings["play_mp3_on_signal"] = bool(settings.get("play_mp3_on_signal", True))

                save_settings(settings)

        except json.JSONDecodeError:
            print(f"{RED}[ERROR] File konfigurasi '{CONFIG_FILE}' rusak. Menggunakan default & menyimpan ulang.{RESET}")
            save_settings(settings)
        except Exception as e:
            print(f"{RED}[ERROR] Gagal memuat konfigurasi: {e}{RESET}")
    else:
        print(f"{YELLOW}[INFO] File konfigurasi '{CONFIG_FILE}' tidak ditemukan. Membuat dengan nilai default.{RESET}")
        save_settings(settings)
    return settings

def save_settings(settings):
    try:
        settings_to_save = {}
        for key in DEFAULT_SETTINGS:
            settings_to_save[key] = settings.get(key, DEFAULT_SETTINGS[key])
            if key == 'check_interval_seconds': settings_to_save[key] = int(settings_to_save[key])
            elif key == 'play_mp3_on_signal': settings_to_save[key] = bool(settings_to_save[key])

        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings_to_save, f, indent=2, sort_keys=True)
    except Exception as e:
        print(f"{RED}[ERROR] Gagal menyimpan konfigurasi: {e}{RESET}")

# --- Fungsi Utilitas Email & Beep ---
def decode_mime_words(s):
    # ... (fungsi sama) ...
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
    # ... (fungsi sama) ...
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
    # ... (fungsi sama, opsional) ...
    try:
        prefix = f"{MAGENTA}{BOLD}[BEEP]{RESET}"
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
        print(f"{YELLOW}[WARN] Perintah 'beep' tidak ditemukan. {DIM}(Opsional: pkg install beep){RESET}")
    except Exception: pass

# --- Fungsi Pemutaran MP3 (Menggunakan Termux:API) ---
def play_action_sound(action, settings):
    """Memainkan file buy.mp3 atau sell.mp3 menggunakan termux-media-player."""
    if not settings.get("play_mp3_on_signal", False):
        return # Fitur MP3 dinonaktifkan

    action_lower = action.lower()
    if action_lower not in ["buy", "sell"]:
        print(f"{RED}[ERROR] Aksi '{action}' tidak valid untuk play sound.{RESET}")
        return

    filename = f"{action_lower}.mp3"
    script_dir = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join(script_dir, filename)

    prefix = f"{GREEN}{BOLD}[MP3]{RESET}"
    print(f"{prefix} Mencoba memainkan: {filename} (via termux-media-player)...")

    # 1. Cek file MP3 ada
    if not os.path.exists(filepath):
        print(f"{RED}{BOLD}[X] Gagal memainkan MP3!{RESET}")
        print(f"{RED}    └─ File '{filename}' tidak ditemukan di direktori script!{RESET}")
        print(f"{DIM}       Lokasi: {script_dir}{RESET}")
        return

    # 2. Coba jalankan termux-media-player
    try:
        # Cek dulu apakah command `termux-media-player` ada
        if not shutil.which("termux-media-player"):
            raise FileNotFoundError("Perintah 'termux-media-player' tidak ditemukan.")

        # Perintahnya simpel: termux-media-player play <namafile>
        result = subprocess.run(
            ["termux-media-player", "play", filepath],
            check=True,          # Raise error jika command gagal
            capture_output=True, # Tangkap output
            text=True,
            timeout=10 # Tambahkan timeout agar tidak hang jika API bermasalah
        )
        # Jika berhasil, termux-media-player biasanya tidak banyak output
        print(f"{prefix} Perintah play '{filename}' dikirim ke Termux:API.")
        # Catatan: Playback mungkin berjalan di background, script lanjut

    except FileNotFoundError:
        # Error jika perintah 'termux-media-player' tidak ada
        print(f"{RED}{BOLD}[X] Gagal memainkan MP3!{RESET}")
        print(f"{RED}    └─ Perintah 'termux-media-player' tidak ditemukan!{RESET}")
        print(f"{YELLOW}       Pastikan sudah install dengan menjalankan:{RESET}")
        print(f"{YELLOW}       pkg install termux-api{RESET}")
        print(f"{DIM}       (Mungkin juga perlu install aplikasi Termux:API dari store){RESET}")

    except subprocess.TimeoutExpired:
         print(f"{RED}{BOLD}[X] Gagal memainkan MP3 via termux-media-player!{RESET}")
         print(f"{RED}    └─ Perintah timed out. Termux:API mungkin tidak responsif.{RESET}")

    except subprocess.CalledProcessError as e:
        # Error jika termux-media-player jalan tapi gagal
        print(f"{RED}{BOLD}[X] Gagal memainkan MP3 via termux-media-player!{RESET}")
        print(f"{RED}    └─ termux-media-player keluar dengan error (code: {e.returncode}).{RESET}")
        if e.stderr:
            print(f"{DIM}       Pesan error:\n{e.stderr.strip()}{RESET}")
        if e.stdout:
            print(f"{DIM}       Output:\n{e.stdout.strip()}{RESET}")
        print(f"{DIM}       (Cek apakah file MP3 valid dan Termux:API berfungsi?){RESET}")

    except Exception as e:
        # Error tak terduga lainnya
        print(f"{RED}{BOLD}[X] Error tak terduga saat mencoba memainkan MP3 via Termux:API:{RESET}")
        print(f"{RED}    └─ {e}{RESET}")
        traceback.print_exc()

# --- Fungsi Pemrosesan Email ---
def process_email(mail, email_id, settings):
    # ... (fungsi sama, panggil play_action_sound yg baru) ...
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

        print(f"\n{CYAN}╭─ Email Baru [{timestamp}] {'─'*(get_terminal_width() - 22)}{RESET}")
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
                        trigger_beep(action_word) # Panggil beep (opsional)
                        play_action_sound(action_word, settings) # Panggil fungsi MP3 (yg pakai Termux:API)

                    elif action_word:
                        print(f"{CYAN}│{RESET} {YELLOW}[?] Trigger ditemukan, tapi kata '{action_word}' bukan 'buy'/'sell'.{RESET}")
                    else:
                        print(f"{CYAN}│{RESET} {YELLOW}[?] Trigger ditemukan, tapi tidak ada kata aksi setelahnya.{RESET}")
                else:
                     print(f"{CYAN}│{RESET} {YELLOW}[?] Target ditemukan, tapi trigger '{settings['trigger_keyword']}' tidak ada SETELAHNYA.{RESET}")
            except Exception as e:
                 print(f"{CYAN}│{RESET} {RED}[X] Error parsing setelah trigger: {e}{RESET}")
                 traceback.print_exc()
        else:
             print(f"{CYAN}│{RESET} {BLUE}[-] Target '{settings['target_keyword']}' tidak ditemukan.{RESET}")

        try:
            mail.store(email_id, '+FLAGS', '\\Seen')
            print(f"{CYAN}│{RESET} {DIM}Email ditandai sudah dibaca.{RESET}")
        except Exception as e:
            print(f"{CYAN}│{RESET} {RED}[X] Gagal tandai dibaca: {e}{RESET}")

        print(f"{CYAN}╰{'─' * (get_terminal_width() - 1)}{RESET}")

    except Exception as e:
        print(f"{log_prefix} {RED}{BOLD}FATAL Error proses email:{RESET}")
        traceback.print_exc()


# --- Fungsi Listening Utama ---
def start_listening(settings):
    # ... (fungsi sama) ...
    global running
    running = True
    mail = None
    last_check_time = time.time()
    consecutive_errors = 0
    wait_time = 2
    long_wait = 60

    mp3_active = settings.get("play_mp3_on_signal", True)
    termux_api_ok = shutil.which("termux-media-player") is not None

    print_separator('─', GREEN if mp3_active else YELLOW)
    if mp3_active:
        print_centered("Mode Pemutaran MP3: AKTIF (via Termux:API)", GREEN, BOLD)
        if termux_api_ok:
            print(f"{DIM}   (Termux:API terdeteksi. Perlu: buy.mp3 & sell.mp3){RESET}")
        else:
            print(f"{YELLOW}{DIM}   (WARNING: Termux:API command tidak terdeteksi! Install: pkg install termux-api){RESET}")
    else:
        print_centered("Mode Pemutaran MP3: NONAKTIF", YELLOW, BOLD)
    print_separator('─', GREEN if mp3_active else YELLOW)
    time.sleep(1)

    print(f"\n{GREEN}{BOLD}Memulai listener... (Ctrl+C untuk berhenti){RESET}")
    wait_indicator_chars = ['∙', '·', '˙', ' ']
    indicator_idx = 0

    while running:
        try:
            if not mail or mail.state != 'SELECTED':
                print(f"\n{CYAN}[...] Menghubungkan ke IMAP {settings['imap_server']}...{RESET}")
                try:
                    mail = imaplib.IMAP4_SSL(settings['imap_server'], timeout=20)
                    rv, desc = mail.login(settings['email_address'], settings['app_password'])
                    if rv != 'OK': raise imaplib.IMAP4.error(f"Login gagal: {desc}")
                    rv, data = mail.select("inbox")
                    if rv != 'OK': raise imaplib.IMAP4.error(f"Gagal select inbox: {data}")
                    print(f"{GREEN}[OK] Terhubung & Login ke {settings['email_address']}. Mendengarkan...{RESET}")
                    consecutive_errors = 0; wait_time = 2
                except (imaplib.IMAP4.error, OSError, socket.error, socket.timeout) as login_err:
                    print(f"{RED}{BOLD}[X] Gagal koneksi/login IMAP!{RESET}")
                    print(f"{RED}    └─ {login_err}{RESET}")
                    if "authentication failed" in str(login_err).lower():
                         print(f"{YELLOW}       ↳ Periksa Email/App Password & Izin IMAP.{RESET}")
                         print(f"{RED}{BOLD}       Program berhenti.{RESET}")
                         running = False
                    else:
                        print(f"{YELLOW}       ↳ Periksa server IMAP & koneksi internet.{RESET}")
                        consecutive_errors += 1
                    if mail:
                        try: mail.logout()
                        except Exception: pass
                    mail = None

            if mail and mail.state == 'SELECTED':
                while running:
                    current_time = time.time()
                    if current_time - last_check_time < settings['check_interval_seconds']:
                        time.sleep(0.5)
                        continue

                    try:
                        status, _ = mail.noop()
                        if status != 'OK':
                            raise imaplib.IMAP4.abort(f"NOOP gagal, status: {status}")
                    except (imaplib.IMAP4.abort, imaplib.IMAP4.readonly, BrokenPipeError, OSError, socket.error, socket.timeout) as noop_err:
                        print(f"\n{YELLOW}[!] Koneksi IMAP terputus ({type(noop_err).__name__}). Mencoba reconnect...{RESET}")
                        try: mail.logout()
                        except Exception: pass
                        mail = None
                        consecutive_errors += 1
                        break

                    try:
                        status, messages = mail.search(None, '(UNSEEN)')
                        if status != 'OK':
                            print(f"\n{RED}[X] Gagal cari email UNSEEN: {status}. Reconnecting...{RESET}")
                            try: mail.logout()
                            except Exception: pass
                            mail = None; consecutive_errors += 1
                            break

                        email_ids = messages[0].split()
                        if email_ids:
                            num = len(email_ids)
                            print(f"\n{GREEN}{BOLD}[!] {num} email baru ditemukan! Memproses...{RESET}")
                            for i, eid in enumerate(email_ids):
                                if not running: break
                                print(f"{DIM}--- Proses email {i+1}/{num} (ID: {eid.decode()}) ---{RESET}")
                                process_email(mail, eid, settings)
                            if not running: break
                            print(f"{GREEN}[OK] Selesai proses {num} email. Mendengarkan lagi...{RESET}")
                        else:
                            indicator_idx = (indicator_idx + 1) % len(wait_indicator_chars)
                            wait_char = wait_indicator_chars[indicator_idx]
                            print(f"{BLUE}[{wait_char}] Menunggu email baru... {DIM}(Interval: {settings['check_interval_seconds']}s){RESET}   ", end='\r', flush=True)

                    except (imaplib.IMAP4.error, OSError, socket.error, socket.timeout) as search_err:
                         print(f"\n{RED}[X] Error saat mencari email: {search_err}. Reconnecting...{RESET}")
                         try: mail.logout()
                         except Exception: pass
                         mail = None; consecutive_errors += 1
                         break

                    last_check_time = current_time
                    if not running: break

                if mail and mail.state == 'SELECTED':
                   try: mail.close()
                   except Exception: pass

        except (imaplib.IMAP4.error, imaplib.IMAP4.abort, socket.error, socket.timeout, OSError) as e:
             print(f"\n{RED}{BOLD}[X] Error IMAP/Network di loop utama: {type(e).__name__} - {e}{RESET}")
             consecutive_errors += 1
        except Exception as e:
             print(f"\n{RED}{BOLD}[X] Error tak terduga di loop utama:{RESET}")
             traceback.print_exc()
             consecutive_errors += 1

        finally:
            if mail and mail.state != 'LOGOUT':
                try: mail.logout()
                except Exception: pass
            mail = None

            if not running:
                print(f"{YELLOW}[INFO] Loop utama berhenti.{RESET}")
                break

            if consecutive_errors > 0:
                current_wait = wait_time * (2**(consecutive_errors-1))
                current_wait = min(current_wait, long_wait)
                print(f"{YELLOW}[!] Terjadi error ({consecutive_errors}x). Mencoba lagi dalam {current_wait:.0f} detik...{RESET}")
                sleep_start = time.time()
                while time.time() - sleep_start < current_wait:
                     if not running: break
                     time.sleep(0.5)
                if not running: break
            else:
                 pass

    print(f"\n{YELLOW}{BOLD}[INFO] Listener dihentikan.{RESET}")


# --- Fungsi Menu Pengaturan ---
def show_settings(settings):
    # ... (fungsi sama, update teks MP3) ...
    while True:
        clear_screen()
        print_header("Pengaturan Listener Email MP3")

        print(f"\n{BOLD}{CYAN} E M A I L {RESET}")
        print(f"{DIM}─────────────────────────────{RESET}")
        print(f" {CYAN}1. Alamat Email{RESET}   : {settings['email_address'] or f'{DIM}[Kosong]{RESET}'}")
        app_pass_disp = f"{GREEN}Terisi{RESET}" if settings['app_password'] else f"{RED}Kosong{RESET}"
        print(f" {CYAN}2. App Password{RESET}   : {app_pass_disp}")
        print(f" {CYAN}3. Server IMAP{RESET}    : {settings['imap_server']}")
        print(f" {CYAN}4. Interval Cek{RESET}   : {settings['check_interval_seconds']} detik")
        print(f" {CYAN}5. Keyword Target{RESET} : '{settings['target_keyword']}'")
        print(f" {CYAN}6. Keyword Trigger{RESET}: '{settings['trigger_keyword']}'")

        print(f"\n{BOLD}{YELLOW} M P 3   S I G N A L   (via Termux:API) {RESET}")
        print(f"{DIM}─────────────────────────────{RESET}")
        mp3_status = f"{GREEN}{BOLD}Aktif{RESET}" if settings['play_mp3_on_signal'] else f"{YELLOW}Nonaktif{RESET}"
        print(f" {YELLOW}7. Mainkan MP3?{RESET}   : {mp3_status}")
        termux_api_ok = shutil.which("termux-media-player") is not None
        termux_api_stat = f"{GREEN}OK{RESET}" if termux_api_ok else f"{RED}Tidak Ada!{RESET}"
        print(f"   {DIM}└─ Termux:API Cmd : {termux_api_stat} {DIM} (Perlu: buy.mp3 & sell.mp3){RESET}")
        if not termux_api_ok:
            print(f"     {RED}{DIM}↳ Install dengan: pkg install termux-api{RESET}")

        print_separator(color=MAGENTA)

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
        else:
             choice_input = input("Pilih (E=Edit, K=Kembali): ").lower().strip()
             choice = 'edit' if choice_input == 'e' else 'back'

        if choice == 'edit':
            print(f"\n{BOLD}{MAGENTA}--- Edit Pengaturan ---{RESET}")
            print(f"{DIM}(Kosongkan input untuk skip / tidak ubah){RESET}")

            print(f"\n{CYAN}--- Email ---{RESET}")
            # ... (input email 1-6 sama) ...
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


            print(f"\n{YELLOW}--- MP3 Signal (via Termux:API) ---{RESET}")
            while True:
                 curr = settings['play_mp3_on_signal']
                 prompt = f"{GREEN}Aktif{RESET}" if curr else f"{YELLOW}Nonaktif{RESET}"
                 val_str = input(f" 7. Mainkan MP3? ({prompt}) [y/n]: ").lower().strip()
                 if not val_str: break
                 if val_str == 'y': settings['play_mp3_on_signal'] = True; break
                 elif val_str == 'n': settings['play_mp3_on_signal'] = False; break
                 else: print(f"{RED}[!] y/n saja.{RESET}")

            save_settings(settings)
            print(f"\n{GREEN}{BOLD}[OK] Pengaturan disimpan!{RESET}")
            input(f"{DIM}Tekan Enter untuk kembali...{RESET}")

        elif choice == 'back':
            save_settings(settings)
            print(f"\n{GREEN}Pengaturan disimpan. Kembali ke Menu Utama...{RESET}")
            time.sleep(1.5)
            break

# --- Fungsi Menu Utama ---
def main_menu():
    # ... (fungsi sama, update teks MP3) ...
    settings = load_settings()

    while True:
        clear_screen()
        print_header("Exora AI - Email Listener MP3 (via Termux:API)")

        print(f"\n{BOLD}{CYAN} S T A T U S {RESET}")
        print(f"{DIM}─────────────────────────────{RESET}")

        email_ok = bool(settings.get('email_address'))
        pass_ok = bool(settings.get('app_password'))
        print(f" {CYAN}Email Listener:{RESET}")
        print(f"   ├─ Config: Email [{GREEN if email_ok else RED}{'✓' if email_ok else 'X'}{RESET}] | App Pass [{GREEN if pass_ok else RED}{'✓' if pass_ok else 'X'}{RESET}]")
        print(f"   └─ Server: {settings.get('imap_server', '?')}, Interval: {settings.get('check_interval_seconds')}s")

        print(f" {YELLOW}MP3 Signal (via Termux:API):{RESET}")
        mp3_active = settings.get("play_mp3_on_signal", True)
        mp3_status = f"{GREEN}{BOLD}AKTIF{RESET}" if mp3_active else f"{YELLOW}NONAKTIF{RESET}"
        print(f"   ├─ Status  : {mp3_status}")
        termux_api_ok = shutil.which("termux-media-player") is not None
        termux_api_stat = f"{GREEN}✓ Terinstall{RESET}" if termux_api_ok else f"{RED}X Tidak Ditemukan!{RESET}"
        print(f"   └─ Req     : {termux_api_stat} | Files (buy/sell.mp3) {DIM}[Cek Manual]{RESET}")
        if mp3_active and not termux_api_ok:
             print(f"     {RED}{DIM}↳ Termux:API command tidak ada! Install: pkg install termux-api{RESET}")

        print_separator(color=MAGENTA)

        menu_prompt = f"{YELLOW}Pilih Menu {DIM}(↑/↓ Enter){RESET}" if INQUIRER_AVAILABLE else f"{YELLOW}Ketik Pilihan:{RESET}"

        if INQUIRER_AVAILABLE:
            choices = []
            start_label = "▶️  Mulai Listener"
            start_mode = f" {DIM}("
            if mp3_active: start_mode += f"{YELLOW}MP3 Mode{DIM}"
            else: start_mode += "Email Only"
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
        else:
            print(f"\n{menu_prompt}")
            print(f" 1. Mulai Listener")
            print(f" 2. Pengaturan")
            print(f" 3. Keluar")
            print_separator(color=MAGENTA)
            choice_input = input("Pilihan (1/2/3): ").strip()
            choice_map = {'1': 'start', '2': 'settings', '3': 'exit'}
            choice_key = choice_map.get(choice_input, 'invalid')

        if choice_key == 'start':
            print_separator()
            errors = []
            if not settings.get('email_address') or not settings.get('app_password'):
                errors.append("Email/App Password belum lengkap.")

            mp3_active = settings.get("play_mp3_on_signal", True)
            # Validasi Termux:API jika MP3 aktif
            if mp3_active and not shutil.which("termux-media-player"):
                errors.append("Mode MP3 aktif tapi perintah 'termux-media-player' tidak ditemukan. (Install: pkg install termux-api)")

            if errors:
                print(f"\n{BOLD}{RED}--- TIDAK BISA MEMULAI ---{RESET}")
                for i, err in enumerate(errors): print(f" {RED}{i+1}. {err}{RESET}")
                print(f"\n{YELLOW}Perbaiki di 'Pengaturan' atau install 'termux-api'.{RESET}")
                input(f"{DIM}Tekan Enter untuk kembali...{RESET}")
            else:
                clear_screen()
                mode = "MP3 Mode (via Termux:API)" if mp3_active else "Email Listener Only"
                print_header(f"Memulai Mode: {mode}")
                start_listening(settings)
                print(f"\n{YELLOW}[INFO] Kembali ke Menu Utama...{RESET}")
                time.sleep(2)

        elif choice_key == 'settings':
            show_settings(settings)
            settings = load_settings()

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

    # Beri tahu user soal termux-api jika belum ada
    if not shutil.which("termux-media-player"):
        print(f"{YELLOW}Tips: Untuk fitur MP3, script ini butuh Termux:API.{RESET}")
        print(f"{YELLOW}      Jalankan di Termux: {RESET}pkg install termux-api")
        print(f"{DIM}(Pastikan juga file buy.mp3 & sell.mp3 ada di folder script){RESET}")
        print(f"{DIM}(Mungkin perlu juga install aplikasi Termux:API dari F-Droid/Play Store){RESET}")
        time.sleep(4) # Beri waktu baca sebelum menu

    try:
        main_menu()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Program dihentikan paksa.{RESET}"); sys.exit(1)
    except Exception as e:
        print(f"\n{BOLD}{RED}===== ERROR KRITIS TAK TERDUGA ====={RESET}")
        traceback.print_exc()
        print(f"\n{RED}Error: {e}{RESET}")
        input("Tekan Enter untuk keluar...")
        sys.exit(1)
