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

# --- Konfigurasi & Variabel Global ---
CONFIG_FILE = "config.json"
DEFAULT_SETTINGS = {
    "email_address": "",
    "app_password": "",
    "imap_server": "imap.gmail.com",
    "check_interval_seconds": 10, # <-- Default diubah ke 10 detik
    "target_keyword": "Exora AI",
    "trigger_keyword": "order",
}

# Variabel global untuk mengontrol loop utama
running = True

# --- Kode Warna ANSI (standar terminal, tidak perlu library) ---
# Jika terminal tidak support warna, ini akan diabaikan atau tampil sebagai teks biasa.
# Anda bisa mengganti nilainya menjadi string kosong jika warna mengganggu.
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
    """Menangani sinyal SIGINT (Ctrl+C) untuk keluar dengan bersih."""
    global running
    print(f"\n{YELLOW}[WARN] Ctrl+C terdeteksi. Menghentikan program...{RESET}")
    running = False
    # Beri sedikit waktu agar loop utama bisa berhenti
    time.sleep(1.5)
    # Keluar paksa jika masih berjalan setelah jeda
    print(f"{RED}[EXIT] Keluar dari program.{RESET}")
    sys.exit(0)

# Daftarkan signal handler
signal.signal(signal.SIGINT, signal_handler)

# --- Fungsi Konfigurasi ---
def load_settings():
    """Memuat pengaturan dari file JSON."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                settings = json.load(f)
                # Pastikan semua kunci default ada
                for key, value in DEFAULT_SETTINGS.items():
                    if key not in settings:
                        settings[key] = value
                # Pastikan interval >= 5 detik
                if settings.get("check_interval_seconds", 10) < 5:
                    print(f"{YELLOW}[WARN] Interval cek di '{CONFIG_FILE}' < 5 detik, direset ke 10.{RESET}")
                    settings["check_interval_seconds"] = 10
                    save_settings(settings) # Simpan perbaikan
                return settings
        except json.JSONDecodeError:
            print(f"{RED}[ERROR] File konfigurasi '{CONFIG_FILE}' rusak. Menggunakan default.{RESET}")
            return DEFAULT_SETTINGS.copy()
        except Exception as e:
            print(f"{RED}[ERROR] Gagal memuat konfigurasi: {e}{RESET}")
            return DEFAULT_SETTINGS.copy()
    else:
        return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    """Menyimpan pengaturan ke file JSON."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
        print(f"{GREEN}[INFO] Pengaturan berhasil disimpan ke '{CONFIG_FILE}'{RESET}")
    except Exception as e:
        print(f"{RED}[ERROR] Gagal menyimpan konfigurasi: {e}{RESET}")

# --- Fungsi Utilitas ---
def clear_screen():
    """Membersihkan layar konsol."""
    os.system('cls' if os.name == 'nt' else 'clear')

def decode_mime_words(s):
    """Mendekode header email yang mungkin terenkode."""
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
    """Mengekstrak konten teks dari objek email (menangani multipart)."""
    text_content = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))

            # Cari bagian teks plain, abaikan lampiran
            if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                    charset = part.get_content_charset() or 'utf-8'
                    payload = part.get_payload(decode=True)
                    text_content += payload.decode(charset, errors='replace') # Ganti error decode
                except Exception as e:
                    print(f"{YELLOW}[WARN] Tidak bisa mendekode bagian email: {e}{RESET}")
    else:
        # Email bukan multipart, coba ambil body langsung
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                text_content = payload.decode(charset, errors='replace') # Ganti error decode
            except Exception as e:
                 print(f"{YELLOW}[WARN] Tidak bisa mendekode body email: {e}{RESET}")

    return text_content.lower() # Kembalikan dalam huruf kecil

# --- Fungsi Beep ---
def trigger_beep(action):
    """Memicu pola beep berdasarkan aksi (buy/sell)."""
    try:
        if action == "buy":
            print(f"{MAGENTA}[ACTION] Memicu BEEP untuk '{BOLD}BUY{RESET}{MAGENTA}' (5 detik on/off){RESET}")
            # Beep -f frekuensi -l durasi(ms) -D jeda(ms) -r pengulangan
            subprocess.run(["beep", "-f", "1000", "-l", "500", "-D", "500", "-r", "5"], check=True, capture_output=True, text=True)
        elif action == "sell":
            print(f"{MAGENTA}[ACTION] Memicu BEEP untuk '{BOLD}SELL{RESET}{MAGENTA}' (2 kali beep){RESET}")
            subprocess.run(["beep", "-f", "700", "-l", "1000", "-D", "500", "-r", "2"], check=True, capture_output=True, text=True)
        else:
             print(f"{YELLOW}[WARN] Aksi tidak dikenal '{action}', tidak ada beep.{RESET}")

    except FileNotFoundError:
        print(f"{RED}[ERROR] Perintah 'beep' tidak ditemukan.{RESET}")
        print(f"{YELLOW}         Pastikan sudah terinstall (misal: 'sudo apt install beep') dan bisa diakses PATH.{RESET}")
    except subprocess.CalledProcessError as e:
        print(f"{RED}[ERROR] Gagal menjalankan 'beep': {e}{RESET}")
        if e.stderr:
            print(f"{RED}         Stderr: {e.stderr.strip()}{RESET}")
        print(f"{YELLOW}         Pastikan user punya izin atau modul 'pcspkr' dimuat.{RESET}")
    except Exception as e:
        print(f"{RED}[ERROR] Kesalahan tak terduga saat beep: {e}{RESET}")

# --- Fungsi Pemrosesan Email ---
def process_email(mail, email_id, settings):
    """Mengambil, mem-parsing, dan memproses satu email."""
    global running
    if not running: return

    target_keyword_lower = settings['target_keyword'].lower()
    trigger_keyword_lower = settings['trigger_keyword'].lower()
    email_id_str = email_id.decode('utf-8') # Untuk logging

    try:
        # Ambil data email (RFC822 standard)
        status, data = mail.fetch(email_id, "(RFC822)")
        if status != 'OK':
            print(f"{RED}[ERROR] Gagal mengambil email ID {email_id_str}: {status}{RESET}")
            return

        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)

        # Dekode subjek dan pengirim
        subject = decode_mime_words(msg["Subject"])
        sender = decode_mime_words(msg["From"])
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print(f"\n{CYAN}--- Email Baru Diterima ({timestamp}) ---{RESET}")
        print(f" ID    : {email_id_str}")
        print(f" Dari  : {sender}")
        print(f" Subjek: {subject}")

        # Ekstrak konten teks
        body = get_text_from_email(msg)

        # Gabungkan subjek dan body untuk pencarian keyword
        full_content = (subject.lower() + " " + body)

        # 1. Cari keyword target
        if target_keyword_lower in full_content:
            print(f"{GREEN}[INFO] Keyword target '{settings['target_keyword']}' ditemukan.{RESET}")

            # 2. Cari keyword pemicu setelah keyword target
            try:
                target_index = full_content.index(target_keyword_lower)
                # Cari trigger *setelah* target
                trigger_index = full_content.index(trigger_keyword_lower, target_index + len(target_keyword_lower))

                # 3. Ambil kata setelah keyword pemicu
                start_word_index = trigger_index + len(trigger_keyword_lower)
                text_after_trigger = full_content[start_word_index:].lstrip() # Hapus spasi di depan
                words_after_trigger = text_after_trigger.split(maxsplit=1) # Ambil kata pertama

                if words_after_trigger:
                    action_word = words_after_trigger[0].strip('.,!?:;()[]{}').lower() # Bersihkan tanda baca
                    print(f"{GREEN}[INFO] Keyword trigger '{settings['trigger_keyword']}' ditemukan. Kata berikutnya: '{BOLD}{action_word}{RESET}{GREEN}'{RESET}")

                    # 4. Cek apakah kata adalah 'buy' atau 'sell'
                    if action_word == "buy":
                        trigger_beep("buy")
                    elif action_word == "sell":
                        trigger_beep("sell")
                    else:
                        print(f"{YELLOW}[WARN] Kata setelah '{settings['trigger_keyword']}' ({action_word}) bukan 'buy' atau 'sell'.{RESET}")
                else:
                    print(f"{YELLOW}[WARN] Tidak ada kata yang terbaca setelah '{settings['trigger_keyword']}'.{RESET}")

            except ValueError:
                # ValueError bisa terjadi jika trigger_keyword tidak ditemukan *setelah* target_keyword
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
        traceback.print_exc() # Cetak traceback lengkap untuk error ini

# --- Fungsi Listening Utama ---
def start_listening(settings):
    """Memulai loop untuk memeriksa email baru."""
    global running
    running = True
    mail = None
    wait_time = 30 # Waktu tunggu sebelum reconnect (detik)

    while running:
        try:
            print(f"{CYAN}[SYS] Mencoba menghubungkan ke server IMAP ({settings['imap_server']})...{RESET}")
            mail = imaplib.IMAP4_SSL(settings['imap_server'])
            print(f"{GREEN}[SYS] Terhubung ke {settings['imap_server']}{RESET}")

            print(f"{CYAN}[SYS] Mencoba login sebagai {settings['email_address']}...{RESET}")
            mail.login(settings['email_address'], settings['app_password'])
            print(f"{GREEN}[SYS] Login berhasil sebagai {BOLD}{settings['email_address']}{RESET}")

            mail.select("inbox")
            print(f"{GREEN}[INFO] Memulai mode mendengarkan di INBOX... (Tekan Ctrl+C untuk berhenti){RESET}")
            print("-" * 50)

            last_check_time = time.time()

            while running:
                # Cek jika koneksi masih OK (opsional tapi bagus)
                try:
                    status, _ = mail.noop()
                    if status != 'OK':
                        print(f"{YELLOW}[WARN] Koneksi IMAP NOOP gagal ({status}). Mencoba reconnect...{RESET}")
                        break # Keluar loop cek, paksa reconnect
                except Exception as NopErr:
                     print(f"{YELLOW}[WARN] Koneksi IMAP terputus ({NopErr}). Mencoba reconnect...{RESET}")
                     break # Keluar loop cek, paksa reconnect


                # Cari email yang belum dibaca
                status, messages = mail.search(None, '(UNSEEN)')

                if status != 'OK':
                     print(f"{RED}[ERROR] Gagal mencari email: {status}{RESET}")
                     break # Keluar loop cek, coba reconnect

                email_ids = messages[0].split()
                if email_ids:
                    print(f"\n{GREEN}[INFO] Menemukan {len(email_ids)} email baru!{RESET}")
                    for email_id in email_ids:
                        if not running: break
                        process_email(mail, email_id, settings)
                    if not running: break
                    print("-" * 50)
                    print(f"{GREEN}[INFO] Selesai memproses. Kembali mendengarkan...{RESET}")
                    last_check_time = time.time() # Reset timer setelah proses email
                else:
                    # Tidak ada email baru, tunggu interval
                    wait_interval = settings['check_interval_seconds']
                    # Pesan tunggu dengan \r
                    print(f"{BLUE}[INFO] Tidak ada email baru. Cek lagi dalam {wait_interval} detik... {RESET}          ", end='\r')

                    # Sleep dalam potongan 1 detik agar bisa diinterupsi Ctrl+C
                    for _ in range(wait_interval):
                         if not running: break
                         time.sleep(1)
                    if not running: break

                    # Hapus pesan tunggu sebelum cetak pesan berikutnya atau loop lagi
                    print(" " * 80, end='\r')
                    last_check_time = time.time()


            # Jika keluar dari loop cek (karena error atau sinyal), coba tutup koneksi
            if mail and mail.state == 'SELECTED':
                try:
                    mail.close()
                except Exception:
                    pass # Abaikan error saat close jika memang sudah bermasalah

        except (imaplib.IMAP4.error, imaplib.IMAP4.abort) as e:
            print(f"{RED}[ERROR] Kesalahan IMAP: {e}{RESET}")
            if "authentication failed" in str(e).lower() or "invalid credentials" in str(e).lower():
                print(f"{RED}[FATAL] Login GAGAL! Periksa alamat email dan App Password.{RESET}")
                print(f"{YELLOW}         Pastikan IMAP diaktifkan di pengaturan Gmail Anda.{RESET}")
                running = False # Hentikan loop utama jika login gagal
                return # Kembali ke menu utama
            print(f"{YELLOW}[WARN] Akan mencoba menghubungkan kembali dalam {wait_time} detik...{RESET}")
            time.sleep(wait_time)
        except (ConnectionError, OSError, socket.error, socket.gaierror) as e: # Tangani lebih banyak error koneksi
             print(f"{RED}[ERROR] Kesalahan Koneksi: {e}{RESET}")
             print(f"{YELLOW}[WARN] Periksa koneksi internet Anda. Mencoba lagi dalam {wait_time} detik...{RESET}")
             time.sleep(wait_time)
        except Exception as e:
            print(f"{RED}[ERROR] Kesalahan tak terduga di loop utama:{RESET}")
            traceback.print_exc()
            print(f"{YELLOW}[WARN] Akan mencoba menghubungkan kembali dalam {wait_time} detik...{RESET}")
            time.sleep(wait_time)
        finally:
            # Pastikan logout terjadi jika objek mail ada dan belum logout
            if mail:
                try:
                    if mail.state != 'LOGOUT':
                         mail.logout()
                         print(f"{CYAN}[SYS] Logout dari server IMAP.{RESET}")
                except Exception:
                    # Kadang logout gagal jika koneksi sudah mati, abaikan saja
                    pass
            mail = None # Reset objek mail

        # Tambahkan jeda singkat sebelum loop reconnect berikutnya jika tidak dihentikan
        if running:
            time.sleep(2)

    print(f"{YELLOW}[INFO] Mode mendengarkan dihentikan.{RESET}")

# --- Fungsi Menu Pengaturan ---
def show_settings(settings):
    """Menampilkan dan mengedit pengaturan."""

    while True:
        clear_screen()
        print(f"{BOLD}{CYAN}--- Pengaturan Email Listener ---{RESET}")
        print("\nPengaturan Saat Ini:")
        print(f" 1. {CYAN}Alamat Email{RESET}   : {settings['email_address'] or '[Belum diatur]'}")
        # Tetap sembunyikan password
        print(f" 2. {CYAN}App Password{RESET}   : {'*' * len(settings['app_password']) if settings['app_password'] else '[Belum diatur]'}")
        print(f" 3. {CYAN}Server IMAP{RESET}    : {settings['imap_server']}")
        print(f" 4. {CYAN}Interval Cek{RESET}   : {settings['check_interval_seconds']} detik")
        print(f" 5. {CYAN}Keyword Target{RESET} : {settings['target_keyword']}")
        print(f" 6. {CYAN}Keyword Trigger{RESET}: {settings['trigger_keyword']}")
        print("-" * 30)
        print("\nOpsi:")
        print(f" {YELLOW}E{RESET} - Edit Pengaturan")
        print(f" {YELLOW}K{RESET} - Kembali ke Menu Utama")
        print("-" * 30)

        choice = input("Pilih opsi (E/K): ").lower().strip()

        if choice == 'e':
            print(f"\n{BOLD}{MAGENTA}--- Edit Pengaturan ---{RESET}")
            # 1. Email
            current_email = settings['email_address']
            new_email = input(f" 1. Masukkan alamat Email Gmail baru [{current_email or 'kosong'}]: ").strip()
            if new_email:
                settings['email_address'] = new_email

            # 2. App Password
            print(f" 2. Masukkan App Password Gmail baru (generate dari Akun Google).")
            print(f"    {YELLOW}(Kosongkan untuk tidak mengubah){RESET}")
            new_password = getpass.getpass("    App Password: ")
            if new_password:
                 settings['app_password'] = new_password

            # 3. Server IMAP (jarang diubah untuk Gmail)
            current_server = settings['imap_server']
            new_server = input(f" 3. Server IMAP baru [{current_server}]: ").strip()
            if new_server:
                settings['imap_server'] = new_server

            # 4. Interval Cek
            current_interval = settings['check_interval_seconds']
            while True:
                new_interval_str = input(f" 4. Interval cek (detik) baru [{current_interval}], min 5: ").strip()
                if not new_interval_str:
                    break # Tidak ada perubahan
                try:
                    new_interval = int(new_interval_str)
                    if new_interval >= 5:
                        settings['check_interval_seconds'] = new_interval
                        break
                    else:
                        print(f"   {RED}[ERROR] Interval minimal adalah 5 detik.{RESET}")
                except ValueError:
                    print(f"   {RED}[ERROR] Input tidak valid, masukkan angka.{RESET}")

            # 5. Keyword Target
            current_target = settings['target_keyword']
            new_target = input(f" 5. Keyword target baru [{current_target}]: ").strip()
            if new_target:
                settings['target_keyword'] = new_target

            # 6. Keyword Trigger
            current_trigger = settings['trigger_keyword']
            new_trigger = input(f" 6. Keyword trigger baru [{current_trigger}]: ").strip()
            if new_trigger:
                settings['trigger_keyword'] = new_trigger

            save_settings(settings)
            print(f"\n{GREEN}[INFO] Pengaturan diperbarui.{RESET}")
            time.sleep(2)
            # Kembali ke tampilan pengaturan setelah edit

        elif choice == 'k':
            break # Keluar dari loop pengaturan
        else:
            print(f"{RED}[ERROR] Pilihan tidak valid. Coba lagi.{RESET}")
            time.sleep(1.5)
            # Layar akan dibersihkan di awal loop berikutnya

# --- Fungsi Menu Utama ---
def main_menu():
    """Menampilkan menu utama aplikasi."""
    settings = load_settings()

    while True:
        clear_screen()
        print(f"{BOLD}{MAGENTA}========================================{RESET}")
        print(f"{BOLD}{MAGENTA}       Exora AI - Email Listener       {RESET}")
        print(f"{BOLD}{MAGENTA}========================================{RESET}")
        print("\nSilakan pilih opsi:\n")
        print(f" {GREEN}1.{RESET} Mulai Mendengarkan Email")
        print(f" {CYAN}2.{RESET} Pengaturan")
        print(f" {YELLOW}3.{RESET} Keluar")
        print("-" * 40)

        # Tampilkan status konfigurasi singkat
        email_status = f"{GREEN}OK{RESET}" if settings['email_address'] else f"{RED}Belum diatur{RESET}"
        pass_status = f"{GREEN}OK{RESET}" if settings['app_password'] else f"{RED}Belum diatur{RESET}"
        print(f" Status: Email [{email_status}] | App Pass [{pass_status}]")
        print("-" * 40)

        choice = input("Masukkan pilihan Anda (1/2/3): ").strip()

        if choice == '1':
            if not settings['email_address'] or not settings['app_password']:
                print(f"\n{RED}[ERROR] Alamat Email atau App Password belum diatur!{RESET}")
                print(f"{YELLOW}         Silakan masuk ke menu 'Pengaturan' (pilihan 2) terlebih dahulu.{RESET}")
                time.sleep(4)
            else:
                clear_screen()
                print(f"{BOLD}{GREEN}--- Memulai Mode Mendengarkan ---{RESET}")
                start_listening(settings)
                # Jika kembali dari start_listening (misal, karena error login fatal atau Ctrl+C)
                print(f"\n{YELLOW}[INFO] Kembali ke Menu Utama...{RESET}")
                time.sleep(2)
        elif choice == '2':
            show_settings(settings)
            # Setelah kembali dari pengaturan, load ulang jika ada perubahan
            settings = load_settings()
        elif choice == '3':
            print(f"\n{CYAN}Terima kasih telah menggunakan Exora AI Listener! Sampai jumpa!{RESET}")
            sys.exit(0)
        else:
            print(f"\n{RED}[ERROR] Pilihan tidak valid. Masukkan 1, 2, atau 3.{RESET}")
            time.sleep(1.5)

# --- Entry Point ---
if __name__ == "__main__":
    # Import socket di sini untuk menangani errornya di listener
    import socket
    try:
        main_menu()
    except KeyboardInterrupt:
        # Menangkap KeyboardInterrupt di level tertinggi jika signal handler gagal
        print(f"\n{YELLOW}[WARN] Program dihentikan paksa.{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{BOLD}{RED}===== ERROR KRITIS ====={RESET}")
        traceback.print_exc() # Cetak traceback lengkap
        print(f"\n{RED}Terjadi error kritis yang tidak tertangani: {e}{RESET}")
        print("Program akan keluar.")
        sys.exit(1)
