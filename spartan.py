import imaplib
import email
from email.header import decode_header
import json
import time
import os
import sys
import re # Untuk parsing yang lebih fleksibel
import winsound # Hanya untuk Windows!
from getpass import getpass # Untuk input password tersembunyi

# Rich untuk CLI yang lebih baik
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

# Inisialisasi Console Rich
console = Console()

CONFIG_FILE = 'config.json'
DEFAULT_CONFIG = {
    "email": "MASUKKAN_EMAIL_ANDA@gmail.com",
    "app_password": "MASUKKAN_APP_PASSWORD_ANDA",
    "check_interval_seconds": 60
}

# --- Fungsi Konfigurasi ---
def load_config():
    """Memuat konfigurasi dari file JSON."""
    if not os.path.exists(CONFIG_FILE):
        console.print(f"[yellow]File konfigurasi '{CONFIG_FILE}' tidak ditemukan. Membuat default.[/yellow]")
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            # Pastikan semua kunci ada
            for key, value in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = value
            return config
    except json.JSONDecodeError:
        console.print(f"[bold red]Error: Format file '{CONFIG_FILE}' tidak valid. Menggunakan default.[/bold red]")
        # Mungkin backup file lama dan buat yang baru
        # os.rename(CONFIG_FILE, CONFIG_FILE + '.bak')
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    except Exception as e:
        console.print(f"[bold red]Error saat memuat konfigurasi: {e}. Menggunakan default.[/bold red]")
        return DEFAULT_CONFIG

def save_config(config):
    """Menyimpan konfigurasi ke file JSON."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        # console.print(f"[green]Konfigurasi disimpan ke '{CONFIG_FILE}'[/green]")
    except Exception as e:
        console.print(f"[bold red]Error saat menyimpan konfigurasi: {e}[/bold red]")

# --- Fungsi Beep (Windows Specific) ---
def beep_buy():
    """Memainkan suara beep untuk sinyal BUY (5 detik on/off)."""
    console.print("[bold green]>>> BUY Signal Detected! Playing sound... <<<[/bold green]")
    frequency = 1000  # Hz
    duration_on = 500  # milliseconds
    duration_off = 500 # milliseconds
    start_time = time.time()
    while time.time() - start_time < 5: # Loop selama 5 detik
        try:
            winsound.Beep(frequency, duration_on)
            time.sleep(duration_off / 1000.0) # Sleep butuh detik
        except RuntimeError:
             console.print("[yellow]Tidak bisa memainkan suara (mungkin tidak ada sound device?).[/yellow]")
             break # Keluar jika error
        except Exception as e:
             console.print(f"[red]Error saat beep: {e}[/red]")
             break

def beep_sell():
    """Memainkan suara beep untuk sinyal SELL (2 kali beep dalam 5 detik)."""
    console.print("[bold red]>>> SELL Signal Detected! Playing sound... <<<[/bold red]")
    frequency = 1500  # Hz (beda frekuensi biar beda)
    duration = 1000  # milliseconds (1 detik beep)
    try:
        winsound.Beep(frequency, duration)
        time.sleep(0.5) # Jeda antar beep
        winsound.Beep(frequency, duration)
    except RuntimeError:
         console.print("[yellow]Tidak bisa memainkan suara (mungkin tidak ada sound device?).[/yellow]")
    except Exception as e:
         console.print(f"[red]Error saat beep: {e}[/red]")


# --- Fungsi Email ---
def clean_text(text):
    """Membersihkan teks dari karakter aneh dan spasi berlebih."""
    if text is None:
        return ""
    # Hapus spasi berlebih dan ganti newline dengan spasi
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_email_body(msg):
    """Mendapatkan body teks dari objek email, menangani multipart."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))

            # Cari bagian text/plain, abaikan attachment
            if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                    # Coba decode payload
                    charset = part.get_content_charset()
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode(charset if charset else 'utf-8', errors='ignore')
                        break # Ambil body text/plain pertama saja
                except Exception as e:
                    console.print(f"[yellow]Warning: Tidak bisa decode bagian email: {e}[/yellow]")
                    # Coba ambil payload mentah jika decode gagal
                    raw_payload = part.get_payload()
                    if isinstance(raw_payload, str):
                         body = raw_payload # Anggap saja sudah string
                         break

    else: # Email bukan multipart
        content_type = msg.get_content_type()
        if content_type == "text/plain":
             try:
                charset = msg.get_content_charset()
                payload = msg.get_payload(decode=True)
                if payload:
                    body = payload.decode(charset if charset else 'utf-8', errors='ignore')
             except Exception as e:
                console.print(f"[yellow]Warning: Tidak bisa decode body email non-multipart: {e}[/yellow]")
                raw_payload = msg.get_payload()
                if isinstance(raw_payload, str):
                     body = raw_payload

    return clean_text(body)

def parse_email_for_signal(text_content):
    """Menganalisa teks email untuk mencari sinyal 'Exora AI' dan order 'buy'/'sell'."""
    if not text_content:
        return None

    text_lower = text_content.lower() # Case-insensitive

    if "exora ai" not in text_lower:
        return None # Tidak ada keyword utama

    # Cari kata 'order'
    match = re.search(r'order\s+(\w+)', text_lower) # Cari 'order' diikuti satu kata
    if match:
        signal = match.group(1).strip() # Ambil kata setelah 'order'
        if signal == "buy":
            return "buy"
        elif signal == "sell":
            return "sell"

    return None # Tidak ditemukan pola 'order buy' atau 'order sell'

def check_emails(config, live_status):
    """Menghubungkan ke Gmail, memeriksa email baru, dan memprosesnya."""
    signals_found = []
    try:
        live_status.update(Text("Menghubungkan ke Gmail IMAP...", style="cyan"), spinner="dots")
        mail = imaplib.IMAP4_SSL('imap.gmail.com')

        live_status.update(Text(f"Login sebagai {config['email']}...", style="cyan"), spinner="dots")
        mail.login(config['email'], config['app_password'])

        live_status.update(Text("Memilih folder INBOX...", style="cyan"), spinner="dots")
        mail.select('inbox')

        # Cari email yang belum dibaca (UNSEEN)
        live_status.update(Text("Mencari email baru (UNSEEN)...", style="cyan"), spinner="dots")
        status, messages = mail.search(None, 'UNSEEN')

        if status == 'OK':
            email_ids = messages[0].split()
            if not email_ids:
                live_status.update(Text("Tidak ada email baru.", style="green"), spinner="dots")
                time.sleep(2) # Beri waktu user membaca status
            else:
                console.print(f"[bold yellow]Ditemukan {len(email_ids)} email baru.[/bold yellow]")

                for i, email_id in enumerate(email_ids):
                    current_progress = f"Memproses email {i+1}/{len(email_ids)}"
                    live_status.update(Text(current_progress, style="cyan"), spinner="dots")

                    # Ambil data email (RFC822 = seluruh email)
                    res, msg_data = mail.fetch(email_id, '(RFC822)')

                    if res == 'OK':
                        for response_part in msg_data:
                            if isinstance(response_part, tuple):
                                # Parse email dari bytes
                                msg = email.message_from_bytes(response_part[1])

                                # Decode subject
                                subject, encoding = decode_header(msg['Subject'])[0]
                                if isinstance(subject, bytes):
                                    subject = subject.decode(encoding if encoding else 'utf-8', errors='ignore')

                                from_ = msg.get('From')
                                console.print(f"\n[dim]Membaca email dari:[/dim] {from_} \n[dim]Subject:[/dim] {subject}")

                                # Dapatkan body email (text/plain)
                                body = get_email_body(msg)
                                # console.print(f"[dim]Body Preview:[/dim] {body[:100]}...") # Opsi: Tampilkan preview body

                                # Parse untuk sinyal
                                signal = parse_email_for_signal(subject + " " + body) # Cek subject dan body

                                if signal == "buy":
                                    signals_found.append("buy")
                                    beep_buy()
                                elif signal == "sell":
                                    signals_found.append("sell")
                                    beep_sell()
                                else:
                                     console.print("[dim]Tidak ada sinyal 'Exora AI' dengan order 'buy'/'sell' ditemukan.[/dim]")

                                # Tandai email sebagai sudah dibaca (SEEN)
                                try:
                                     mail.store(email_id, '+FLAGS', '\\Seen')
                                     # console.print("[dim]Email ditandai sebagai sudah dibaca.[/dim]")
                                except Exception as e_store:
                                    console.print(f"[yellow]Warning: Gagal menandai email {email_id} sebagai SEEN: {e_store}[/yellow]")
                    else:
                        console.print(f"[yellow]Warning: Gagal fetch email ID {email_id}[/yellow]")
                    time.sleep(0.5) # Jeda sedikit antar pemrosesan email

        else:
            console.print(f"[red]Error saat mencari email: {status}[/red]")

        # Logout dari server
        mail.logout()
        live_status.update(Text("Logout dari Gmail.", style="cyan"), spinner="dots")
        time.sleep(1)

    except imaplib.IMAP4.error as e:
        console.print(f"[bold red]Error IMAP: {e}[/bold red]")
        live_status.update(Text("Error IMAP. Cek koneksi/credential.", style="red"), spinner="dots")
        time.sleep(5)
    except ConnectionRefusedError:
         console.print("[bold red]Error: Koneksi ke server IMAP ditolak. Firewall?[/bold red]")
         live_status.update(Text("Koneksi ditolak.", style="red"), spinner="dots")
         time.sleep(5)
    except Exception as e:
        console.print(f"[bold red]Terjadi error tak terduga: {e}[/bold red]")
        import traceback
        traceback.print_exc() # Tampilkan detail error untuk debug
        live_status.update(Text(f"Error: {e}", style="red"), spinner="dots")
        time.sleep(5)

    return signals_found # Kembalikan daftar sinyal yang ditemukan (jika perlu)

# --- Fungsi Tampilan CLI ---
def display_homepage():
    """Menampilkan menu utama."""
    console.clear()
    console.print(Panel(
        "[bold cyan]🚀 Gmail Signal Listener 🚀[/bold cyan]\n\n"
        "Pilih Opsi:\n"
        "[1] Mulai Mendengarkan Email\n"
        "[2] Pengaturan (Email & App Password)\n"
        "[3] Keluar",
        title="Main Menu",
        border_style="blue"
    ))
    choice = Prompt.ask("Masukkan pilihan", choices=["1", "2", "3"], default="1")
    return choice

def display_settings(config):
    """Menampilkan dan mengedit pengaturan."""
    console.clear()
    while True:
        console.print(Panel(
            f"[bold yellow]🔧 Pengaturan Saat Ini 🔧[/bold yellow]\n\n"
            f"1. Email Akun Gmail : [cyan]{config['email']}[/cyan]\n"
            f"2. App Password     : [cyan]{'*' * len(config.get('app_password', '')) if config.get('app_password') else '[Belum Diatur]'}[/cyan]\n"
            f"3. Interval Cek (dtk): [cyan]{config['check_interval_seconds']}[/cyan]\n\n"
            "Pilih nomor untuk diedit, [S] untuk Simpan & Kembali, atau [K] untuk Kembali tanpa simpan.",
            title="Settings",
            border_style="yellow"
        ))
        choice = Prompt.ask("Pilihan Anda", choices=["1", "2", "3", "S", "K", "s", "k"], default="K").upper()

        if choice == "1":
            new_email = Prompt.ask("Masukkan Email Gmail baru", default=config['email'])
            if "@" in new_email and "." in new_email: # Validasi sederhana
                 config['email'] = new_email
            else:
                 console.print("[red]Format email tidak valid.[/red]")
                 time.sleep(1)
        elif choice == "2":
            console.print("[bold yellow]Masukkan App Password Gmail Anda.[/bold yellow]")
            console.print("[dim](Input akan tersembunyi. Dapatkan dari: Akun Google > Keamanan > Sandi Aplikasi)[/dim]")
            new_password = getpass("App Password baru: ")
            if new_password:
                config['app_password'] = new_password
            else:
                console.print("[yellow]Input password kosong, tidak diubah.[/yellow]")
                time.sleep(1)
        elif choice == "3":
             while True:
                 try:
                     new_interval = int(Prompt.ask("Masukkan interval cek email baru (detik)", default=str(config['check_interval_seconds'])))
                     if new_interval >= 10: # Minimal interval 10 detik
                         config['check_interval_seconds'] = new_interval
                         break
                     else:
                          console.print("[red]Interval minimal 10 detik.[/red]")
                 except ValueError:
                     console.print("[red]Masukkan angka yang valid.[/red]")
        elif choice == "S":
            save_config(config)
            console.print("[green]Pengaturan disimpan![/green]")
            time.sleep(1)
            break
        elif choice == "K":
            # Reload config jika user batal edit
            config = load_config()
            console.print("[yellow]Perubahan dibatalkan.[/yellow]")
            time.sleep(1)
            break
        console.clear() # Refresh tampilan setelah edit
    return config # Kembalikan config yang mungkin sudah diupdate

def start_listening(config):
    """Memulai loop utama untuk memeriksa email secara berkala."""
    console.clear()
    console.print(Panel("[bold green]🎧 Memulai Mode Mendengarkan... Tekan Ctrl+C untuk berhenti. 🎧[/bold green]", border_style="green"))

    if not config.get('email') or config['email'] == DEFAULT_CONFIG['email'] or \
       not config.get('app_password') or config['app_password'] == DEFAULT_CONFIG['app_password']:
        console.print("[bold red]Error: Email atau App Password belum diatur dengan benar.[/bold red]")
        console.print("[yellow]Silakan atur melalui menu 'Pengaturan' terlebih dahulu.[/yellow]")
        time.sleep(4)
        return # Kembali ke menu utama

    spinner = Spinner("dots", text=Text("Menunggu...", style="cyan"))
    try:
        with Live(spinner, refresh_per_second=10, console=console) as live:
             while True:
                live.update(Text(f"Mengecek email setiap {config['check_interval_seconds']} detik...", style="cyan"), spinner="dots")
                check_emails(config, live) # Pass 'live' object untuk update status
                # Setelah selesai cek, tampilkan status menunggu
                for i in range(config['check_interval_seconds'], 0, -1):
                    live.update(Text(f"Menunggu {i} detik untuk pengecekan berikutnya...", style="blue"), spinner="dots")
                    time.sleep(1)

    except KeyboardInterrupt:
        console.print("\n[bold yellow]Interupsi diterima. Menghentikan listener...[/bold yellow]")
        time.sleep(1)
    except Exception as e:
        console.print(f"\n[bold red]Error tak terduga di loop utama: {e}[/bold red]")
        time.sleep(3)


# --- Main Execution ---
if __name__ == "__main__":
    config = load_config()

    while True:
        choice = display_homepage()
        if choice == "1":
            start_listening(config)
        elif choice == "2":
            config = display_settings(config) # Update config jika ada perubahan
        elif choice == "3":
            console.print("[bold blue]Terima kasih telah menggunakan script ini! Sampai jumpa! 👋[/bold blue]")
            sys.exit(0)
