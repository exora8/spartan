import imaplib
import email
from email.header import decode_header
import time
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
    "check_interval_seconds": 60, # Periksa email setiap 60 detik
    "target_keyword": "Exora AI",
    "trigger_keyword": "order",
}

# Variabel global untuk mengontrol loop utama
running = True

# --- Fungsi Penanganan Sinyal (Ctrl+C) ---
def signal_handler(sig, frame):
    """Menangani sinyal SIGINT (Ctrl+C) untuk keluar dengan bersih."""
    global running
    print("\nINFO: Keluar dari program...")
    running = False
    # Beri sedikit waktu agar loop utama bisa berhenti
    time.sleep(1)
    # Keluar paksa jika masih berjalan setelah jeda (misalnya jika terjebak di login)
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
                return settings
        except json.JSONDecodeError:
            print(f"ERROR: File konfigurasi '{CONFIG_FILE}' rusak. Menggunakan default.")
            return DEFAULT_SETTINGS.copy()
        except Exception as e:
            print(f"ERROR saat memuat konfigurasi: {e}")
            return DEFAULT_SETTINGS.copy()
    else:
        return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    """Menyimpan pengaturan ke file JSON."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
        print(f"INFO: Pengaturan berhasil disimpan ke '{CONFIG_FILE}'")
    except Exception as e:
        print(f"ERROR saat menyimpan konfigurasi: {e}")

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
            result.append(part.decode(encoding or 'utf-8', errors='ignore'))
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
                    text_content += payload.decode(charset, errors='ignore')
                except Exception as e:
                    print(f"WARN: Tidak bisa mendekode bagian email: {e}")
    else:
        # Email bukan multipart, coba ambil body langsung
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                text_content = payload.decode(charset, errors='ignore')
            except Exception as e:
                 print(f"WARN: Tidak bisa mendekode body email: {e}")

    return text_content.lower() # Kembalikan dalam huruf kecil

# --- Fungsi Beep ---
def trigger_beep(action):
    """Memicu pola beep berdasarkan aksi (buy/sell)."""
    try:
        if action == "buy":
            print("ACTION: Memicu BEEP untuk 'BUY' (5 detik on/off)")
            # Beep -f frekuensi -l durasi(ms) -D jeda(ms) -r pengulangan
            subprocess.run(["beep", "-f", "1000", "-l", "500", "-D", "500", "-r", "5"], check=True, capture_output=True)
        elif action == "sell":
            print("ACTION: Memicu BEEP untuk 'SELL' (2 kali beep)")
            subprocess.run(["beep", "-f", "700", "-l", "1000", "-D", "500", "-r", "2"], check=True, capture_output=True)
        else:
             print(f"WARN: Aksi tidak dikenal '{action}', tidak ada beep.")

    except FileNotFoundError:
        print("ERROR: Perintah 'beep' tidak ditemukan. Pastikan sudah terinstall (`sudo apt install beep`) dan bisa diakses.")
    except subprocess.CalledProcessError as e:
        print(f"ERROR saat menjalankan 'beep': {e}")
        if e.stderr:
            print(f"Stderr: {e.stderr.decode()}")
        print("WARN: Pastikan user memiliki izin untuk menggunakan 'beep' atau modul 'pcspkr' dimuat.")
    except Exception as e:
        print(f"ERROR tak terduga saat beep: {e}")

# --- Fungsi Pemrosesan Email ---
def process_email(mail, email_id, settings):
    """Mengambil, mem-parsing, dan memproses satu email."""
    global running
    if not running: return

    target_keyword_lower = settings['target_keyword'].lower()
    trigger_keyword_lower = settings['trigger_keyword'].lower()

    try:
        # Ambil data email (RFC822 standard)
        status, data = mail.fetch(email_id, "(RFC822)")
        if status != 'OK':
            print(f"ERROR: Gagal mengambil email ID {email_id}: {status}")
            return

        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)

        # Dekode subjek
        subject = decode_mime_words(msg["Subject"])
        sender = decode_mime_words(msg["From"])
        print(f"\n--- Email Baru Diterima ---")
        print(f"Dari: {sender}")
        print(f"Subjek: {subject}")

        # Ekstrak konten teks
        body = get_text_from_email(msg)

        # Gabungkan subjek dan body untuk pencarian keyword
        full_content = (subject.lower() + " " + body)

        # 1. Cari keyword target
        if target_keyword_lower in full_content:
            print(f"INFO: Keyword '{settings['target_keyword']}' ditemukan.")

            # 2. Cari keyword pemicu setelah keyword target
            try:
                target_index = full_content.index(target_keyword_lower)
                trigger_index = full_content.index(trigger_keyword_lower, target_index)

                # 3. Ambil kata setelah keyword pemicu
                start_word_index = trigger_index + len(trigger_keyword_lower)
                text_after_trigger = full_content[start_word_index:].lstrip()
                words_after_trigger = text_after_trigger.split()

                if words_after_trigger:
                    action_word = words_after_trigger[0]
                    print(f"INFO: Trigger '{settings['trigger_keyword']}' ditemukan. Kata berikutnya: '{action_word}'")

                    # 4. Cek apakah kata adalah 'buy' atau 'sell'
                    if action_word == "buy":
                        trigger_beep("buy")
                    elif action_word == "sell":
                        trigger_beep("sell")
                    else:
                        print(f"WARN: Kata setelah '{settings['trigger_keyword']}' bukan 'buy' atau 'sell'.")
                else:
                    print(f"WARN: Tidak ada kata setelah '{settings['trigger_keyword']}'.")

            except ValueError:
                print(f"WARN: Keyword '{settings['trigger_keyword']}' tidak ditemukan setelah '{settings['target_keyword']}'.")
            except Exception as e:
                 print(f"ERROR saat parsing kata setelah trigger: {e}")

        else:
            print(f"INFO: Keyword '{settings['target_keyword']}' tidak ditemukan dalam email.")

        # Tandai email sebagai sudah dibaca ('Seen')
        try:
            mail.store(email_id, '+FLAGS', '\\Seen')
        except Exception as e:
            print(f"ERROR menandai email {email_id} sebagai 'Seen': {e}")

    except Exception as e:
        print(f"ERROR memproses email ID {email_id}:")
        traceback.print_exc() # Cetak traceback lengkap untuk error ini

# --- Fungsi Listening Utama ---
def start_listening(settings):
    """Memulai loop untuk memeriksa email baru."""
    global running
    running = True
    mail = None

    while running:
        try:
            print("INFO: Menghubungkan ke server IMAP...")
            mail = imaplib.IMAP4_SSL(settings['imap_server'])
            print(f"INFO: Terhubung ke {settings['imap_server']}")

            print("INFO: Melakukan login...")
            mail.login(settings['email_address'], settings['app_password'])
            print(f"INFO: Login berhasil sebagai {settings['email_address']}")

            mail.select("inbox")
            print("INFO: Memulai mode mendengarkan email di INBOX... (Tekan Ctrl+C untuk berhenti)")

            while running:
                # Cari email yang belum dibaca
                status, messages = mail.search(None, '(UNSEEN)')

                if status != 'OK':
                     print(f"ERROR mencari email: {status}")
                     break # Keluar loop cek, coba reconnect

                email_ids = messages[0].split()
                if email_ids:
                    print(f"\nINFO: Menemukan {len(email_ids)} email baru!")
                    for email_id in email_ids:
                        if not running: break
                        process_email(mail, email_id, settings)
                    if not running: break
                    print("INFO: Selesai memproses email baru. Kembali mendengarkan...")
                else:
                    # Tidak ada email baru, tunggu
                    print(f"INFO: Menunggu email baru... Cek lagi dalam {settings['check_interval_seconds']} detik.", end='\r')
                    # Sleep sambil bisa diinterupsi
                    for _ in range(settings['check_interval_seconds']):
                         if not running: break
                         time.sleep(1)
                    if not running: break
                    print(" " * 80, end='\r') # Hapus pesan menunggu

            if mail and mail.state == 'SELECTED':
                mail.close()

        except imaplib.IMAP4.error as e:
            print(f"ERROR IMAP: {e}")
            if "authentication failed" in str(e).lower():
                print("ERROR: Login gagal! Periksa alamat email dan App Password.")
                return # Kembali ke menu utama
            print("WARN: Akan mencoba menghubungkan kembali dalam 30 detik...")
            time.sleep(30)
        except ConnectionError as e:
             print(f"ERROR Koneksi: {e}")
             print("WARN: Akan mencoba menghubungkan kembali dalam 30 detik...")
             time.sleep(30)
        except Exception as e:
            print(f"ERROR tak terduga di loop listening:")
            traceback.print_exc()
            print("WARN: Akan mencoba menghubungkan kembali dalam 30 detik...")
            time.sleep(30)
        finally:
            if mail:
                try:
                    if mail.state != 'LOGOUT':
                         mail.logout()
                         print("INFO: Logout dari server IMAP.")
                except Exception:
                    pass
            mail = None

        if not running:
            break

    print("INFO: Mode mendengarkan dihentikan.")

# --- Fungsi Menu Pengaturan ---
def show_settings(settings):
    """Menampilkan dan mengedit pengaturan."""
    clear_screen()
    print("--- Pengaturan Email Listener ---")

    while True:
        print("\nPengaturan Saat Ini:")
        print(f"1. Alamat Email   : {settings['email_address'] or '[Belum diatur]'}")
        # Tetap sembunyikan password
        print(f"2. App Password   : {'*' * len(settings['app_password']) if settings['app_password'] else '[Belum diatur]'}")
        print(f"3. Server IMAP    : {settings['imap_server']}")
        print(f"4. Interval Cek   : {settings['check_interval_seconds']} detik")
        print(f"5. Keyword Target : {settings['target_keyword']}")
        print(f"6. Keyword Trigger: {settings['trigger_keyword']}")
        print("\nOpsi:")
        print("e - Edit Pengaturan")
        print("k - Kembali ke Menu Utama")

        choice = input("\nPilih opsi: ").lower()

        if choice == 'e':
            print("\n--- Edit Pengaturan ---")
            new_email = input(f"Masukkan alamat Email Gmail baru (kosongkan untuk skip): ").strip()
            if new_email:
                settings['email_address'] = new_email

            print("Masukkan App Password Gmail baru (generate dari Akun Google). Kosongkan untuk skip:")
            new_password = getpass.getpass("App Password: ")
            if new_password:
                 settings['app_password'] = new_password

            while True:
                new_interval_str = input(f"Interval cek (detik) baru (kosongkan skip, min 5): ").strip()
                if not new_interval_str:
                    break
                try:
                    new_interval = int(new_interval_str)
                    if new_interval >= 5:
                        settings['check_interval_seconds'] = new_interval
                        break
                    else:
                        print("ERROR: Interval minimal adalah 5 detik.")
                except ValueError:
                    print("ERROR: Input tidak valid, masukkan angka.")

            new_target = input(f"Keyword target baru (kosongkan skip): ").strip()
            if new_target:
                settings['target_keyword'] = new_target

            new_trigger = input(f"Keyword trigger baru (kosongkan skip): ").strip()
            if new_trigger:
                settings['trigger_keyword'] = new_trigger

            save_settings(settings)
            print("INFO: Pengaturan diperbarui.")
            time.sleep(2)
            clear_screen()
            print("--- Pengaturan Email Listener ---")

        elif choice == 'k':
            break
        else:
            print("ERROR: Pilihan tidak valid.")
            time.sleep(1)
            clear_screen()
            print("--- Pengaturan Email Listener ---")


# --- Fungsi Menu Utama ---
def main_menu():
    """Menampilkan menu utama aplikasi."""
    settings = load_settings()

    while True:
        clear_screen()
        print("================================")
        print("  Exora AI - Email Listener   ")
        print("================================")
        print("\nSilakan pilih opsi:\n")
        print("1. Mulai Mendengarkan Email")
        print("2. Pengaturan")
        print("3. Keluar")
        print("-" * 32)

        choice = input("Masukkan pilihan Anda (1/2/3): ")

        if choice == '1':
            if not settings['email_address'] or not settings['app_password']:
                print("\nERROR: Alamat Email atau App Password belum diatur di Pengaturan!")
                time.sleep(3)
            else:
                clear_screen()
                print("--- Memulai Mode Mendengarkan ---")
                start_listening(settings)
                print("\nINFO: Kembali ke menu utama...")
                time.sleep(2)
        elif choice == '2':
            show_settings(settings)
        elif choice == '3':
            print("\nINFO: Terima kasih! Sampai jumpa!")
            sys.exit(0)
        else:
            print("\nERROR: Pilihan tidak valid.")
            time.sleep(1.5)

# --- Entry Point ---
if __name__ == "__main__":
    try:
        main_menu()
    except Exception as e:
        print("\nERROR KRITIS:")
        traceback.print_exc() # Cetak traceback lengkap
        print(f"\nTerjadi error kritis yang tidak tertangani: {e}")
        print("Program akan keluar.")
        sys.exit(1)
