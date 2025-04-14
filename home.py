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
WIFI_SCRIPT = "wifi.py"       # Nama file script untuk Wifi
AUTHOR = "YourNameHere" # Ganti dengan nama lu atau biarin kosong

# --- Helper Functions ---
console = Console()

def clear_screen():
    """Membersihkan layar terminal."""
    os.system('cls' if os.name == 'nt' else 'clear')

def get_ip_address():
    """Mendapatkan alamat IP lokal."""
    try:
        # Coba dapatkan IP dari interface yang aktif (lebih robust)
        interfaces = psutil.net_if_addrs()
        for if_name, if_addrs in interfaces.items():
            for addr in if_addrs:
                if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                    return addr.address
        # Fallback jika cara di atas gagal
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
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
    cmd_list = list(command) # Salin list agar tidak termodifikasi
    if sudo:
        cmd_list.insert(0, 'sudo')
    try:
        console.print(f"\n[yellow]Menjalankan:[/yellow] {' '.join(cmd_list)}")
        # Cek apakah butuh password sudo
        if sudo and os.geteuid() != 0:
             console.print("[bold yellow]Membutuhkan hak akses root (sudo). Masukkan password jika diminta.[/bold yellow]")

        process = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if "shutdown" in cmd_list or "reboot" in cmd_list:
            console.print("[green]Perintah dikirim...[/green]")
            time.sleep(2)
            return None, None

        stdout, stderr = process.communicate()
        if process.returncode != 0:
            console.print(f"[bold red]Error:[/bold red]\n{stderr}")
            return None, stderr
        return stdout, None
    except FileNotFoundError:
        console.print(f"[bold red]Error:[/bold red] Perintah '{cmd_list[0]}' tidak ditemukan. Pastikan sudah terinstall.")
        return None, "Command not found"
    except Exception as e:
        console.print(f"[bold red]Error saat menjalankan command:[/bold red] {e}")
        return None, str(e)

# --- Komponen UI ---

def create_header():
    """Membuat panel header dengan animasi."""
    frame = int(time.time() * 2) % 4
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
        style = "on grey23" if option == current_selection_text else "none"
        taskbar_items.append(Text(f" {i+1}. {option} ", style=style))
        taskbar_items.append(Text(" | ", style="dim blue"))

    if taskbar_items:
        taskbar_items.pop()

    return Panel(Text.assemble(*taskbar_items), style="blue", border_style="dim blue", title="[ Menu ]", title_align="left")

def display_device_info():
    """Menampilkan informasi perangkat dalam tabel."""
    clear_screen()
    console.print(Panel("[bold green]🚀 Informasi Perangkat 🚀[/bold green]", style="green", border_style="green"))
    with console.status("[yellow]Mengambil data...", spinner="dots"):
        info = get_device_info()
        time.sleep(0.5)

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
    input()

def run_external_script(script_name):
    """Fungsi generik untuk menjalankan script python eksternal."""
    clear_screen()
    console.print(f"[bold cyan]Mencoba menjalankan {script_name}...[/bold cyan]")
    time.sleep(1)

    script_path = os.path.join(os.path.dirname(__file__), script_name)

    if not os.path.exists(script_path):
        console.print(f"[bold red]Error:[/bold red] File '{script_name}' tidak ditemukan di direktori yang sama.")
        console.print("[yellow]Tekan Enter untuk kembali...[/yellow]")
        input()
        return

    command = []
    # Cek apakah executable
    if not os.access(script_path, os.X_OK):
         console.print(f"[yellow]Script tidak executable, mencoba menjalankan dengan '{sys.executable} {script_name}'...[/yellow]")
         command = [sys.executable, script_path]
    else:
         command = [script_path]

    original_stty = None # Inisialisasi di luar try
    try:
        console.print(f"Menjalankan: {' '.join(command)}")
        # Simpan state terminal asli (penting jika script eksternal mengubah mode terminal)
        original_stty = subprocess.run(['stty', '-g'], capture_output=True, text=True, check=False).stdout.strip()

        # Jalankan script dan tunggu selesai
        subprocess.run(command, check=True)
        console.print(f"\n[green]{script_name} selesai dijalankan.[/green]")

    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error saat menjalankan {script_name}:[/bold red] Script keluar dengan kode error {e.returncode}.")
    except FileNotFoundError:
         console.print(f"[bold red]Error:[/bold red] Perintah '{command[0]}' tidak ditemukan.")
    except Exception as e:
         console.print(f"[bold red]Error tak terduga saat menjalankan {script_name}:[/bold red] {e}")
    finally:
        # Pulihkan state terminal setelah script selesai atau error
        if original_stty:
            subprocess.run(['stty', original_stty], check=False)
        # Beri jeda sebelum kembali ke menu
        console.print("[yellow]Tekan Enter untuk kembali ke menu utama...[/yellow]")
        input()
        clear_screen() # Bersihkan layar sebelum kembali ke menu


# --- Wrapper Functions for Scripts ---
def start_spartan_script():
    run_external_script(SPARTAN_SCRIPT)

def start_wifi_script():
    run_external_script(WIFI_SCRIPT)

# --- Main Loop ---
def main():
    # --- Menu Options ---
    menu_options = {
        "1": ("Start Spartan", start_spartan_script),
        "2": ("Device Info", display_device_info),
        "3": ("Wifi Settings", start_wifi_script), # Opsi Wifi baru
        "4": ("Restart Server", lambda: run_command(['shutdown', '-r', 'now'], sudo=True)),
        "5": ("Shutdown Server", lambda: run_command(['shutdown', '-h', 'now'], sudo=True)),
        "6": ("Exit", lambda: None) # Exit jadi nomor 6
    }
    option_names = [details[0] for details in menu_options.values()]
    num_options = len(menu_options) # Jumlah opsi

    # --- Layout Setup ---
    layout = Layout()
    layout.split(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1),
        Layout(name="taskbar", size=3)
    )

    # --- Initial Content (Fix Tampilan Awal) ---
    layout["header"].update(create_header())
    layout["main"].update(Panel(
        f"[dim]Selamat datang di {APP_NAME}! Ketik nomor menu dan tekan Enter.[/dim]\n"
        f"[dim]Server time: {time.strftime('%Y-%m-%d %H:%M:%S')}[/dim]",
        border_style="dim blue"
    ))
    layout["taskbar"].update(create_taskbar(option_names))

    # --- Live Display Loop ---
    live = Live(layout, refresh_per_second=4, screen=True, transient=True)
    with live: # Menggunakan context manager live
        while True:
            # --- Update Dinamis ---
            layout["header"].update(create_header()) # Animasi header
            layout["main"].update(Panel( # Update waktu di main panel
                f"[dim]Selamat datang di {APP_NAME}! Ketik nomor menu dan tekan Enter.[/dim]\n"
                f"[dim]Server time: {time.strftime('%Y-%m-%d %H:%M:%S')}[/dim]",
                border_style="dim blue"
            ))
            # Taskbar hanya perlu diupdate saat highlight atau jika opsi berubah (tidak di sini)

            # --- Input Handling ---
            live.stop() # Stop rendering untuk input
            current_selection_text = "" # Reset selection text
            try:
                # Pastikan taskbar normal sebelum prompt
                layout["taskbar"].update(create_taskbar(option_names, current_selection_text))
                live.start(refresh=True) # Tampilkan taskbar normal
                time.sleep(0.05) # Jeda sangat singkat
                live.stop() # Stop lagi untuk Prompt

                choice = Prompt.ask(f"[bold yellow]Pilih Opsi (1-{num_options})[/bold yellow]",
                                    choices=list(menu_options.keys()),
                                    show_choices=False) # Sembunyikan daftar pilihan Prompt
            except (KeyboardInterrupt, EOFError):
                choice = str(num_options) # Anggap pilih Exit jika Ctrl+C/D
            except Exception as e:
                 # Tangani error tak terduga saat prompt
                 console.print(f"[bold red]Error input:[/bold red] {e}")
                 time.sleep(2)
                 choice = "-1" # Pilihan tidak valid untuk re-loop

            # --- Action Processing ---
            if choice in menu_options:
                option_name, action = menu_options[choice]

                if action is None: # Opsi Exit
                    # live.stop() sudah terjadi sebelum prompt
                    clear_screen()
                    console.print(f"[bold green]Exiting {APP_NAME}. Sampai jumpa![/bold green]")
                    for i in track(range(3), description="[red]Shutting down interface..."):
                        time.sleep(0.3)
                    break # Keluar dari loop utama (akan otomatis keluar dari 'with live')

                # --- Highlight Taskbar ---
                # live.stop() sudah terjadi
                layout["taskbar"].update(create_taskbar(option_names, current_selection_text=option_name))
                live.start(refresh=True) # Tampilkan highlight
                time.sleep(0.4) # Jeda highlight
                live.stop() # Stop lagi sebelum action
                # --- End Highlight ---

                clear_screen()
                action() # Jalankan fungsi yang dipilih (sudah termasuk clear screen setelahnya jika perlu)
                # Tidak perlu clear screen di sini karena action() atau run_external_script() sudah handle
                # Layout akan di-refresh di awal loop berikutnya
                # Tidak perlu live.start() di sini, loop akan lanjut
            else:
                # Pilihan tidak valid
                if choice != "-1": # Hanya tampilkan pesan jika bukan error input
                    # live.stop() sudah terjadi
                    original_main_content = layout["main"].renderable
                    layout["main"].update(Panel("[bold red]Pilihan tidak valid![/bold red]", border_style="red"))
                    layout["taskbar"].update(create_taskbar(option_names)) # Taskbar normal
                    live.start(refresh=True) # Tampilkan error
                    time.sleep(1.5)
                    live.stop() # Stop lagi
                    layout["main"].update(original_main_content) # Kembalikan main

            # live.start() akan otomatis dipanggil oleh loop berikutnya jika tidak break

    # 'with live:' akan otomatis menangani pembersihan layar alternatif saat keluar


if __name__ == "__main__":
    original_stty = None
    try:
        # Simpan stty awal jika memungkinkan, untuk pemulihan final
        original_stty = subprocess.run(['stty', '-g'], capture_output=True, text=True, check=False).stdout.strip()
        main()
    except Exception as e:
        # Penanganan error darurat
        console.show_cursor(True) # Pastikan kursor terlihat
        # Coba keluar dari screen mode rich
        try:
            temp_console = Console()
            if temp_console.is_alt_screen:
                 # Coba gunakan metode internal Live jika mungkin (meski mungkin instance sudah hilang)
                 # Jika tidak, coba cara manual
                 sys.stderr.write("\x1b[?1049l") # Command VT100 untuk keluar alt screen
                 sys.stderr.flush()
        except Exception:
            pass
        clear_screen()
        print(f"\n\n[!] Terjadi error tak terduga: {e}")
        import traceback
        traceback.print_exc()
        print("\nInterface dihentikan paksa.")
    finally:
        # Pemulihan final
        console.show_cursor(True)
        # Pulihkan stty jika tersimpan
        if original_stty:
            subprocess.run(['stty', original_stty], check=False)
        print("Exiting script.") # Pesan keluar terakhir
