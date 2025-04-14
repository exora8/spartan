#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import time
import platform
import socket
import sys
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.layout import Layout
from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table
from rich.progress import track
from rich.prompt import Prompt
import psutil # Perlu install: pip install psutil rich

# --- Konfigurasi ---
APP_NAME = "Exora Spartan CLI"
VERSION = "1.0"
SPARTAN_SCRIPT = "spartan.py" # Pastikan nama file ini benar
AUTHOR = "YourNameHere" # Ganti dengan nama lu atau biarin kosong

# --- Helper Functions ---
console = Console()

def clear_screen():
    """Membersihkan layar terminal."""
    os.system('cls' if os.name == 'nt' else 'clear')

def get_ip_address():
    """Mendapatkan alamat IP lokal."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)) # Connect ke DNS Google (gak kirim data)
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "N/A"

def get_device_info():
    """Mengumpulkan informasi perangkat."""
    info = {}
    try:
        info['Hostname'] = platform.node()
        info['OS'] = f"{platform.system()} {platform.release()}"
        info['Architecture'] = platform.machine()
        info['IP Address'] = get_ip_address()
        # Info CPU
        cpu_count_logical = psutil.cpu_count(logical=True)
        cpu_count_physical = psutil.cpu_count(logical=False)
        info['CPU'] = f"{platform.processor()} ({cpu_count_physical} Cores / {cpu_count_logical} Threads)"
        info['CPU Usage'] = f"{psutil.cpu_percent(interval=0.5)}%"
        # Info RAM
        mem = psutil.virtual_memory()
        info['RAM Total'] = f"{mem.total / (1024**3):.2f} GB"
        info['RAM Used'] = f"{mem.used / (1024**3):.2f} GB ({mem.percent}%)"
        # Info Disk (Root)
        disk = psutil.disk_usage('/')
        info['Disk Total'] = f"{disk.total / (1024**3):.2f} GB"
        info['Disk Used'] = f"{disk.used / (1024**3):.2f} GB ({disk.percent}%)"

    except Exception as e:
        info['Error'] = f"Gagal mengambil info: {e}"
    return info

def run_command(command, sudo=False):
    """Menjalankan command sistem (opsional dengan sudo)."""
    if sudo:
        command.insert(0, 'sudo')
    try:
        console.print(f"\n[yellow]Menjalankan:[/yellow] {' '.join(command)}")
        # Cek apakah butuh password sudo
        if sudo and os.geteuid() != 0:
             console.print("[bold yellow]Membutuhkan hak akses root (sudo). Masukkan password jika diminta.[/bold yellow]")

        # Menggunakan Popen agar bisa lanjut tanpa menunggu command selesai (misal shutdown/reboot)
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Untuk shutdown/reboot, kita tidak perlu menunggu output
        if "shutdown" in command or "reboot" in command:
            console.print("[green]Perintah dikirim...[/green]")
            time.sleep(2) # Beri jeda sedikit
            return None, None # Tidak mengembalikan output/error

        # Untuk command lain, tunggu dan ambil output/error
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            console.print(f"[bold red]Error:[/bold red]\n{stderr}")
            return None, stderr
        return stdout, None
    except FileNotFoundError:
        console.print(f"[bold red]Error:[/bold red] Perintah '{command[0]}' tidak ditemukan. Pastikan sudah terinstall.")
        return None, "Command not found"
    except Exception as e:
        console.print(f"[bold red]Error saat menjalankan command:[/bold red] {e}")
        return None, str(e)

# --- Komponen UI ---

def create_header():
    """Membuat panel header dengan animasi."""
    # Animasi sederhana: Ganti warna atau karakter
    frame = int(time.time() * 2) % 4 # Buat frame sederhana (0, 1, 2, 3)
    colors = ["bold cyan", "bold magenta", "bold yellow", "bold green"]
    chars = ["✦", "✧", "★", "☆"]

    title_text = Text.assemble(
        (f"{chars[frame]} Exora ", colors[frame]),
        ("Spartan", "bold white"),
        (f" {chars[(frame+1)%4]}", colors[frame]),
        (f" v{VERSION}", "dim white")
    )
    return Panel(title_text, style="bold blue", border_style="blue", title_align="left")

def create_taskbar(options, current_selection_text=""):
    """Membuat panel taskbar."""
    taskbar_items = []
    for i, option in enumerate(options):
         # Beri style berbeda jika ini adalah pilihan yang akan dieksekusi
        style = "on grey23" if option == current_selection_text else "none"
        taskbar_items.append(Text(f" {i+1}. {option} ", style=style))
        taskbar_items.append(Text(" | ", style="dim blue"))

    # Hilangkan separator terakhir
    if taskbar_items:
        taskbar_items.pop()

    return Panel(Text.assemble(*taskbar_items), style="blue", border_style="dim blue", title="[ Menu ]", title_align="left")

def display_device_info():
    """Menampilkan informasi perangkat dalam tabel."""
    clear_screen()
    console.print(Panel("[bold green]🚀 Informasi Perangkat 🚀[/bold green]", style="green", border_style="green"))
    with console.status("[yellow]Mengambil data...", spinner="dots"):
        info = get_device_info()
        time.sleep(0.5) # Biar keliatan loading :)

    if 'Error' in info:
        console.print(f"[bold red]Error:[/bold red] {info['Error']}")
    else:
        table = Table(show_header=True, header_style="bold magenta", border_style="dim blue")
        table.add_column("Parameter", style="cyan", width=20)
        table.add_column("Value", style="white")

        for key, value in info.items():
            table.add_row(key, value)

        console.print(table)

    console.print("\n[yellow]Tekan Enter untuk kembali ke menu utama...[/yellow]")
    input() # Tunggu user menekan Enter

def start_spartan_script():
    """Mulai script spartan.py."""
    clear_screen()
    console.print(f"[bold cyan]Mencoba menjalankan {SPARTAN_SCRIPT}...[/bold cyan]")
    time.sleep(1)

    script_path = os.path.join(os.path.dirname(__file__), SPARTAN_SCRIPT) # Cari di direktori yang sama

    if not os.path.exists(script_path):
        console.print(f"[bold red]Error:[/bold red] File '{SPARTAN_SCRIPT}' tidak ditemukan di direktori yang sama.")
        console.print("[yellow]Tekan Enter untuk kembali...[/yellow]")
        input()
        return

    # Cek apakah executable
    if not os.access(script_path, os.X_OK):
         # Coba jalankan dengan python jika tidak executable
         console.print(f"[yellow]Script tidak executable, mencoba menjalankan dengan 'python3 {SPARTAN_SCRIPT}'...[/yellow]")
         command = [sys.executable, script_path] # sys.executable -> path python yg sedang jalan
    else:
         # Jika executable, jalankan langsung
         command = [script_path]


    # Jalankan script di proses baru. Ini akan menggantikan proses saat ini.
    # Jika ingin kembali ke menu ini setelah spartan.py selesai, gunakan subprocess.run()
    # os.execvp(command[0], command)
    # --- ATAU --- (Jika ingin kembali ke menu setelah spartan.py exit)
    try:
        console.print(f"Menjalankan: {' '.join(command)}")
        # Simpan state terminal asli
        original_stty = subprocess.run(['stty', '-g'], capture_output=True, text=True).stdout.strip()
        # Jalankan script
        subprocess.run(command, check=True)
        console.print(f"\n[green]{SPARTAN_SCRIPT} selesai dijalankan.[/green]")
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error saat menjalankan {SPARTAN_SCRIPT}:[/bold red] {e}")
    except FileNotFoundError:
         console.print(f"[bold red]Error:[/bold red] Perintah '{command[0]}' tidak ditemukan.")
    except Exception as e:
         console.print(f"[bold red]Error tak terduga:[/bold red] {e}")
    finally:
        # Pulihkan state terminal setelah script selesai atau error
        if original_stty:
            subprocess.run(['stty', original_stty])
        clear_screen() # Bersihkan layar sebelum kembali ke menu
        console.print("[yellow]Kembali ke menu utama...[/yellow]")
        time.sleep(1.5)


# --- Main Loop ---
def main():
    menu_options = {
        "1": ("Start Spartan", start_spartan_script),
        "2": ("Device Info", display_device_info),
        "3": ("Restart Server", lambda: run_command(['shutdown', '-r', 'now'], sudo=True)),
        "4": ("Shutdown Server", lambda: run_command(['shutdown', '-h', 'now'], sudo=True)),
        "5": ("Exit", lambda: None) # None akan menghentikan loop
    }
    option_names = [details[0] for details in menu_options.values()]

    layout = Layout()
    layout.split(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1), # Space kosong di tengah
        Layout(name="taskbar", size=3)
    )

    with Live(layout, refresh_per_second=4, screen=True, transient=True) as live:
        while True:
            # Update header (animasi)
            layout["header"].update(create_header())
            # Update taskbar (statis)
            layout["taskbar"].update(create_taskbar(option_names))
            # Update area main (kosong atau pesan)
            layout["main"].update(Panel(
                f"[dim]Selamat datang di {APP_NAME}! Ketik nomor menu dan tekan Enter.[/dim]\n"
                f"[dim]Server time: {time.strftime('%Y-%m-%d %H:%M:%S')}[/dim]",
                border_style="dim blue"
            ))

            # Dapatkan input di luar Live context agar tidak bentrok
            live.stop() # Hentikan sementara Live update
            try:
                # Gunakan Prompt dari Rich untuk input yang lebih bagus
                choice = Prompt.ask(f"[bold yellow]Pilih Opsi (1-{len(menu_options)})[/bold yellow]",
                                    choices=list(menu_options.keys()),
                                    show_choices=False) # Sembunyikan pilihan default prompt
            except (KeyboardInterrupt, EOFError):
                choice = str(len(menu_options)) # Anggap pilih Exit jika Ctrl+C atau Ctrl+D
            live.start() # Lanjutkan Live update

            if choice in menu_options:
                option_name, action = menu_options[choice]

                if action is None: # Opsi Exit
                    live.stop() # Hentikan Live sebelum keluar
                    clear_screen()
                    console.print(f"[bold green]Exiting {APP_NAME}. Sampai jumpa![/bold green]")
                    # Animasi keluar sederhana
                    for i in track(range(3), description="[red]Shutting down interface..."):
                        time.sleep(0.3)
                    break # Keluar dari loop utama

                # Tandai taskbar sebelum eksekusi action
                live.update(layout) # Render sekali lagi dengan taskbar normal
                layout["taskbar"].update(create_taskbar(option_names, current_selection_text=option_name))
                live.update(layout) # Tampilkan taskbar dengan highlight
                time.sleep(0.5) # Jeda sesaat biar keliatan

                live.stop() # Hentikan Live update sebelum menjalankan action
                clear_screen() # Bersihkan layar sebelum action
                action() # Jalankan fungsi yang dipilih
                clear_screen() # Bersihkan layar setelah action selesai (kecuali exit)
                # Loop akan lanjut dan Live akan di-start lagi
                live.start(refresh=True) # Mulai lagi Live
            else:
                 # Jika input tidak valid, tampilkan pesan sementara
                 original_main_content = layout["main"].renderable
                 layout["main"].update(Panel("[bold red]Pilihan tidak valid![/bold red]", border_style="red"))
                 live.update(layout)
                 time.sleep(1)
                 layout["main"].update(original_main_content) # Kembalikan konten main


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Pastikan keluar dari mode layar alternatif jika ada error tak terduga
        console.show_cursor(True)
        # Keluar dari screen mode jika aktif (penting!)
        # Ini agak tricky karena state screen dikelola 'Live'
        # Mencoba membersihkan sebisanya
        clear_screen()
        print(f"\n\n[!] Terjadi error tak terduga: {e}")
        import traceback
        traceback.print_exc()
        print("\nInterface dihentikan paksa.")
    finally:
        # Pastikan cursor selalu terlihat saat keluar
        console.show_cursor(True)
