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

# Import Rich untuk tampilan CLI yang lebih baik
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint # Menggunakan print dari rich

CONSOLE = Console()
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
    CONSOLE.print("\n[bold yellow]Keluar dari program...[/bold yellow]")
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
            CONSOLE.print(f"[bold red]Error:[/bold red] File konfigurasi '{CONFIG_FILE}' rusak. Menggunakan default.")
            return DEFAULT_SETTINGS.copy()
        except Exception as e:
            CONSOLE.print(f"[bold red]Error saat memuat konfigurasi:[/bold red] {e}")
            return DEFAULT_SETTINGS.copy()
    else:
        return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    """Menyimpan pengaturan ke file JSON."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
        rprint(f"[green]Pengaturan berhasil disimpan ke '{CONFIG_FILE}'[/green]")
    except Exception as e:
        CONSOLE.print(f"[bold red]Error saat menyimpan konfigurasi:[/bold red] {e}")

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
                    CONSOLE.print(f"[yellow]Warning:[/yellow] Tidak bisa mendekode bagian email: {e}")
    else:
        # Email bukan multipart, coba ambil body langsung
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                text_content = payload.decode(charset, errors='ignore')
            except Exception as e:
                 CONSOLE.print(f"[yellow]Warning:[/yellow] Tidak bisa mendekode body email: {e}")

    return text_content.lower() # Kembalikan dalam huruf kecil untuk pencarian case-insensitive

# --- Fungsi Beep ---
def trigger_beep(action):
    """Memicu pola beep berdasarkan aksi (buy/sell)."""
    try:
        if action == "buy":
            CONSOLE.print("[bold green]ACTION:[/bold green] Memicu BEEP untuk 'BUY' (5 detik on/off)")
            # Beep -f frekuensi -l durasi(ms) -D jeda(ms) -r pengulangan
            # 5x (500ms on + 500ms off) = 5000ms = 5 detik
            subprocess.run(["beep", "-f", "1000", "-l", "500", "-D", "500", "-r", "5"], check=True, capture_output=True)
        elif action == "sell":
            CONSOLE.print("[bold red]ACTION:[/bold red] Memicu BEEP untuk 'SELL' (2 kali beep)")
            # 2x (1000ms on + 500ms off)
            subprocess.run(["beep", "-f", "700", "-l", "1000", "-D", "500", "-r", "2"], check=True, capture_output=True)
        else:
             CONSOLE.print(f"[yellow]Warning:[/yellow] Aksi tidak dikenal '{action}', tidak ada beep.")

    except FileNotFoundError:
        CONSOLE.print("[bold red]Error:[/bold red] Perintah 'beep' tidak ditemukan. Pastikan sudah terinstall (`sudo apt install beep`) dan bisa diakses.")
    except subprocess.CalledProcessError as e:
        CONSOLE.print(f"[bold red]Error saat menjalankan 'beep':[/bold red] {e}")
        if e.stderr:
            CONSOLE.print(f"[red]Stderr:[/red] {e.stderr.decode()}")
        rprint("[yellow]Pastikan user memiliki izin untuk menggunakan 'beep' atau modul 'pcspkr' dimuat.[/yellow]")
    except Exception as e:
        CONSOLE.print(f"[bold red]Error tak terduga saat beep:[/bold red] {e}")

# --- Fungsi Pemrosesan Email ---
def process_email(mail, email_id, settings):
    """Mengambil, mem-parsing, dan memproses satu email."""
    global running
    if not running: return # Hentikan jika sinyal keluar diterima

    target_keyword_lower = settings['target_keyword'].lower()
    trigger_keyword_lower = settings['trigger_keyword'].lower()

    try:
        # Ambil data email (RFC822 standard)
        status, data = mail.fetch(email_id, "(RFC822)")
        if status != 'OK':
            CONSOLE.print(f"[red]Error mengambil email ID {email_id}: {status}[/red]")
            return

        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)

        # Dekode subjek
        subject = decode_mime_words(msg["Subject"])
        sender = decode_mime_words(msg["From"])
        CONSOLE.print(f"\n[cyan]--- Email Baru Diterima ---[/cyan]")
        CONSOLE.print(f"[bold]Dari:[/bold] {sender}")
        CONSOLE.print(f"[bold]Subjek:[/bold] {subject}")

        # Ekstrak konten teks
        body = get_text_from_email(msg)

        # Gabungkan subjek dan body untuk pencarian keyword (opsional, bisa body saja)
        full_content = (subject.lower() + " " + body)

        # 1. Cari keyword target ("Exora AI")
        if target_keyword_lower in full_content:
            CONSOLE.print(f"[green]Keyword '{settings['target_keyword']}' ditemukan.[/green]")

            # 2. Cari keyword pemicu ("order") setelah keyword target
            # Cari posisi keyword target pertama
            try:
                target_index = full_content.index(target_keyword_lower)
                # Cari keyword pemicu setelah keyword target
                trigger_index = full_content.index(trigger_keyword_lower, target_index)

                # 3. Ambil kata setelah keyword pemicu
                # Cari spasi setelah trigger keyword
                start_word_index = trigger_index + len(trigger_keyword_lower)
                # Ambil substring setelah trigger keyword dan hilangkan spasi di awal
                text_after_trigger = full_content[start_word_index:].lstrip()
                # Pisahkan kata pertama
                words_after_trigger = text_after_trigger.split()

                if words_after_trigger:
                    action_word = words_after_trigger[0]
                    CONSOLE.print(f"[blue]Trigger '{settings['trigger_keyword']}' ditemukan. Kata berikutnya: '{action_word}'[/blue]")

                    # 4. Cek apakah kata adalah 'buy' atau 'sell'
                    if action_word == "buy":
                        trigger_beep("buy")
                    elif action_word == "sell":
                        trigger_beep("sell")
                    else:
                        CONSOLE.print(f"[yellow]Kata setelah '{settings['trigger_keyword']}' bukan 'buy' atau 'sell'.[/yellow]")
                else:
                    CONSOLE.print(f"[yellow]Tidak ada kata setelah '{settings['trigger_keyword']}'.[/yellow]")

            except ValueError:
                # Jika .index() gagal (keyword tidak ditemukan di posisi yang diharapkan)
                CONSOLE.print(f"[yellow]Keyword '{settings['trigger_keyword']}' tidak ditemukan setelah '{settings['target_keyword']}'.[/yellow]")
            except Exception as e:
                 CONSOLE.print(f"[red]Error saat parsing kata setelah trigger: {e}[/red]")

        else:
            CONSOLE.print(f"[yellow]Keyword '{settings['target_keyword']}' tidak ditemukan dalam email.[/yellow]")

        # Tandai email sebagai sudah dibaca ('Seen')
        try:
            mail.store(email_id, '+FLAGS', '\\Seen')
        except Exception as e:
            CONSOLE.print(f"[red]Error menandai email {email_id} sebagai 'Seen': {e}[/red]")

    except Exception as e:
        CONSOLE.print(f"[bold red]Error memproses email ID {email_id}:[/bold red] {e}")
        # Pertimbangkan untuk tidak menandai sebagai 'Seen' jika error parah

# --- Fungsi Listening Utama ---
def start_listening(settings):
    """Memulai loop untuk memeriksa email baru."""
    global running
    running = True # Pastikan state berjalan di set
    mail = None # Inisialisasi mail

    while running:
        try:
            with CONSOLE.status("[bold cyan]Menghubungkan ke server IMAP...", spinner="dots"):
                mail = imaplib.IMAP4_SSL(settings['imap_server'])
            rprint(f"[green]Terhubung ke {settings['imap_server']}[/green]")

            with CONSOLE.status("[bold cyan]Melakukan login...", spinner="dots"):
                 mail.login(settings['email_address'], settings['app_password'])
            rprint(f"[green]Login berhasil sebagai {settings['email_address']}[/green]")

            mail.select("inbox")
            rprint("[bold blue]Memulai mode mendengarkan email di INBOX... (Tekan Ctrl+C untuk berhenti)[/bold blue]")

            while running: # Loop pengecekan email
                # Cari email yang belum dibaca
                status, messages = mail.search(None, '(UNSEEN)')

                if status != 'OK':
                     CONSOLE.print(f"[red]Error mencari email: {status}[/red]")
                     # Coba reconnect di iterasi berikutnya
                     break # Keluar dari loop pengecekan, masuk ke loop reconnect

                email_ids = messages[0].split()
                if email_ids:
                    rprint(f"\n[bold yellow]>>> Menemukan {len(email_ids)} email baru! <<<[/bold yellow]")
                    for email_id in email_ids:
                        if not running: break # Cek sebelum proses tiap email
                        process_email(mail, email_id, settings)
                    if not running: break # Cek setelah loop proses email
                    rprint("[bold blue]Selesai memproses email baru. Kembali mendengarkan...[/bold blue]")
                else:
                    # Tidak ada email baru, tampilkan status menunggu
                    with CONSOLE.status(f"[bold cyan]Menunggu email baru... Cek lagi dalam {settings['check_interval_seconds']} detik.", spinner="line"):
                        # Sleep sambil bisa diinterupsi oleh Ctrl+C
                        for _ in range(settings['check_interval_seconds']):
                             if not running: break
                             time.sleep(1)
                    if not running: break # Cek setelah sleep

                # Kirim NOOP secara berkala untuk menjaga koneksi tetap hidup (misal setiap 5 menit)
                # Jika interval cek pendek, mungkin tidak perlu
                # mail.noop()

            # Jika keluar dari loop pengecekan (karena !running atau error)
            if mail and mail.state == 'SELECTED':
                mail.close()

        except imaplib.IMAP4.error as e:
            CONSOLE.print(f"[bold red]Error IMAP:[/bold red] {e}")
            if "authentication failed" in str(e).lower():
                rprint("[bold red]Login gagal! Periksa alamat email dan App Password.[/bold red]")
                return # Kembali ke menu utama jika login gagal
            rprint("[yellow]Akan mencoba menghubungkan kembali dalam 30 detik...[/yellow]")
            time.sleep(30)
        except ConnectionError as e:
             CONSOLE.print(f"[bold red]Error Koneksi:[/bold red] {e}")
             rprint("[yellow]Akan mencoba menghubungkan kembali dalam 30 detik...[/yellow]")
             time.sleep(30)
        except Exception as e:
            CONSOLE.print(f"[bold red]Terjadi error tak terduga di loop listening:[/bold red] {e}")
            rprint("[yellow]Akan mencoba menghubungkan kembali dalam 30 detik...[/yellow]")
            time.sleep(30)
        finally:
            # Pastikan logout jika objek mail ada dan koneksi masih terbuka
            if mail:
                try:
                    if mail.state != 'LOGOUT':
                         mail.logout()
                         rprint("[yellow]Logout dari server IMAP.[/yellow]")
                except Exception as e:
                    # Mungkin koneksi sudah ditutup
                    pass #CONSOLE.print(f"[yellow]Warning: Error saat logout: {e}[/yellow]")
            mail = None # Reset objek mail

        if not running:
            break # Keluar dari loop reconnect jika diminta berhenti

    rprint("[bold yellow]Mode mendengarkan dihentikan.[/bold yellow]")


# --- Fungsi Menu Pengaturan ---
def show_settings(settings):
    """Menampilkan dan mengedit pengaturan."""
    clear_screen()
    rprint(Panel.fit("[bold cyan]Pengaturan Email Listener[/bold cyan]", border_style="blue"))

    while True:
        rprint("\n[bold]Pengaturan Saat Ini:[/bold]")
        rprint(f"1. Alamat Email   : [yellow]{settings['email_address'] or '[Belum diatur]'}[/yellow]")
        rprint(f"2. App Password   : [yellow]{'*' * len(settings['app_password']) if settings['app_password'] else '[Belum diatur]'}[/yellow]")
        rprint(f"3. Server IMAP    : [yellow]{settings['imap_server']}[/yellow]")
        rprint(f"4. Interval Cek   : [yellow]{settings['check_interval_seconds']} detik[/yellow]")
        rprint(f"5. Keyword Target : [yellow]{settings['target_keyword']}[/yellow]")
        rprint(f"6. Keyword Trigger: [yellow]{settings['trigger_keyword']}[/yellow]")
        rprint("\n[bold]Opsi:[/bold]")
        rprint("[cyan]e[/cyan] - Edit Pengaturan")
        rprint("[cyan]k[/cyan] - Kembali ke Menu Utama")

        choice = CONSOLE.input("\nPilih opsi: ").lower()

        if choice == 'e':
            rprint("\n[bold blue]--- Edit Pengaturan ---[/bold blue]")
            # Edit Email
            new_email = CONSOLE.input(f"Masukkan alamat Email Gmail baru (biarkan kosong untuk skip): ").strip()
            if new_email:
                settings['email_address'] = new_email

            # Edit App Password
            rprint(Text("Masukkan App Password Gmail baru (penting: generate dari Akun Google, bukan password utama). Biarkan kosong untuk skip:", style="yellow"))
            new_password = getpass.getpass("App Password: ")
            if new_password:
                 settings['app_password'] = new_password

            # Edit Interval
            while True:
                new_interval_str = CONSOLE.input(f"Masukkan interval cek (detik) baru (biarkan kosong untuk skip, min 5): ").strip()
                if not new_interval_str:
                    break
                try:
                    new_interval = int(new_interval_str)
                    if new_interval >= 5:
                        settings['check_interval_seconds'] = new_interval
                        break
                    else:
                        rprint("[red]Interval minimal adalah 5 detik.[/red]")
                except ValueError:
                    rprint("[red]Input tidak valid, masukkan angka.[/red]")

            # Edit Keyword Target
            new_target = CONSOLE.input(f"Masukkan keyword target baru (contoh: '{settings['target_keyword']}', biarkan kosong untuk skip): ").strip()
            if new_target:
                settings['target_keyword'] = new_target

            # Edit Keyword Trigger
            new_trigger = CONSOLE.input(f"Masukkan keyword trigger baru (contoh: '{settings['trigger_keyword']}', biarkan kosong untuk skip): ").strip()
            if new_trigger:
                settings['trigger_keyword'] = new_trigger

            save_settings(settings)
            rprint("[green]Pengaturan diperbarui.[/green]")
            time.sleep(2)
            clear_screen()
            rprint(Panel.fit("[bold cyan]Pengaturan Email Listener[/bold cyan]", border_style="blue")) # Tampilkan panel lagi

        elif choice == 'k':
            break
        else:
            rprint("[red]Pilihan tidak valid.[/red]")
            time.sleep(1)
            clear_screen()
            rprint(Panel.fit("[bold cyan]Pengaturan Email Listener[/bold cyan]", border_style="blue")) # Tampilkan panel lagi


# --- Fungsi Menu Utama ---
def main_menu():
    """Menampilkan menu utama aplikasi."""
    settings = load_settings()

    while True:
        clear_screen()
        title = Text("🚀 Exora AI - Email Listener 🚀", style="bold magenta", justify="center")
        menu_text = Text.assemble(
            "\nSilakan pilih opsi:\n\n",
            "[ 1 ] ", Text("Mulai Mendengarkan Email", style="bold green"), "\n",
            "[ 2 ] ", Text("Pengaturan", style="bold yellow"), "\n",
            "[ 3 ] ", Text("Keluar", style="bold red"), "\n"
        )
        rprint(Panel(menu_text, title=title, border_style="blue", expand=False))

        choice = CONSOLE.input("Masukkan pilihan Anda (1/2/3): ")

        if choice == '1':
            if not settings['email_address'] or not settings['app_password']:
                rprint("[bold red]Error:[/bold red] Alamat Email atau App Password belum diatur di Pengaturan!")
                time.sleep(3)
            else:
                clear_screen()
                rprint(Panel.fit("[bold green]Memulai Mode Mendengarkan...[/bold green]", border_style="green"))
                start_listening(settings) # Mulai loop utama
                # Setelah loop selesai (misal karena Ctrl+C atau error login), kembali ke menu
                rprint("\nKembali ke menu utama...")
                time.sleep(2)
        elif choice == '2':
            show_settings(settings)
            # Pengaturan mungkin berubah, muat ulang? Sebenarnya sudah di-pass by reference
            # tapi untuk kejelasan, bisa load ulang jika diperlukan
            # settings = load_settings()
        elif choice == '3':
            rprint("[bold blue]Terima kasih telah menggunakan script ini! Sampai jumpa![/bold blue]")
            sys.exit(0) # Keluar dari script
        else:
            rprint("[bold red]Pilihan tidak valid.[/bold red]")
            time.sleep(1.5)


# --- Entry Point ---
if __name__ == "__main__":
    try:
        main_menu()
    except Exception as e:
        CONSOLE.print_exception(show_locals=True)
        rprint(f"\n[bold red]Terjadi error kritis yang tidak tertangani:[/bold red] {e}")
        rprint("Program akan keluar.")
        sys.exit(1)
