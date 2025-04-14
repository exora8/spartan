#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import time
import platform
import socket
import sys
import psutil # Perlu install: pip install psutil rich
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.layout import Layout
from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table
from rich.progress import track
from rich.prompt import Prompt
import traceback # Untuk debugging error

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
        # Coba cara umum dulu
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1) # Timeout cepat
        s.connect(("8.8.8.8", 80)) # Connect ke DNS Google (gak kirim data)
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        # Jika gagal, coba dapatkan dari hostname (mungkin tidak selalu akurat)
        try:
             hostname = socket.gethostname()
             ip = socket.gethostbyname(hostname)
             # Hindari loopback jika ada IP lain
             if ip == '127.0.0.1':
                 # Coba cari interface lain (lebih kompleks, mungkin perlu library netifaces)
                 # Untuk sekarang, fallback ke N/A jika hanya loopback yg ketemu
                 all_ips = socket.gethostbyname_ex(hostname)[-1]
                 non_loopback = [i for i in all_ips if i != '127.0.0.1']
                 if non_loopback:
                     return non_loopback[0]
                 else:
                     return "N/A (Loopback only?)"
             return ip
        except socket.gaierror:
             return "N/A (Hostname resolve failed)"
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
        cpu_freq = psutil.cpu_freq()
        freq_current = f"{cpu_freq.current:.2f} Mhz" if cpu_freq else "N/A"
        info['CPU'] = f"{platform.processor()} ({cpu_count_physical} Cores / {cpu_count_logical} Threads)"
        info['CPU Freq'] = freq_current
        info['CPU Usage'] = f"{psutil.cpu_percent(interval=0.5)}%" # Interval singkat
        # Info RAM
        mem = psutil.virtual_memory()
        info['RAM Total'] = f"{mem.total / (1024**3):.2f} GB"
        info['RAM Used'] = f"{mem.used / (1024**3):.2f} GB ({mem.percent}%)"
        # Info Disk (Root)
        try:
            disk = psutil.disk_usage('/')
            info['Disk / Total'] = f"{disk.total / (1024**3):.2f} GB"
            info['Disk / Used'] = f"{disk.used / (1024**3):.2f} GB ({disk.percent}%)"
        except FileNotFoundError:
            info['Disk /'] = "N/A (Mount point '/' not found?)"
        # Uptime
        boot_time_timestamp = psutil.boot_time()
        elapsed_seconds = time.time() - boot_time_timestamp
        days, remainder = divmod(elapsed_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        info['Uptime'] = f"{int(days)}d {int(hours)}h {int(minutes)}m"

    except Exception as e:
        info['Error'] = f"Gagal mengambil info: {e}"
    return info

def run_command(command, sudo=False):
    """Menjalankan command sistem (opsional dengan sudo)."""
    cmd_list = list(command) # Salin list agar tidak mengubah original
    if sudo and os.geteuid() != 0: # Cek jika perlu sudo dan belum root
        cmd_list.insert(0, 'sudo')

    try:
        console.print(f"\n[yellow]Menjalankan:[/yellow] {' '.join(cmd_list)}")
        if sudo and os.geteuid() != 0:
             console.print("[bold yellow]Membutuhkan hak akses root (sudo). Masukkan password jika diminta.[/bold yellow]")

        # Menggunakan Popen agar bisa lanjut tanpa menunggu command selesai (misal shutdown/reboot)
        # text=True (atau encoding) penting untuk stdout/stderr sebagai string
        process = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')

        # Untuk shutdown/reboot, kita tidak perlu menunggu output
        is_shutdown_cmd = any(cmd in cmd_list for cmd in ['shutdown', 'reboot', 'poweroff', 'halt'])
        if is_shutdown_cmd:
            console.print("[green]Perintah dikirim... Server akan segera shutdown/restart.[/green]")
            time.sleep(3) # Beri jeda agar pesan terlihat
            # Mungkin tidak kembali dari sini jika shutdown/reboot cepat
            return None, None # Tidak mengembalikan output/error

        # Untuk command lain, tunggu dan ambil output/error
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            console.print(f"[bold red]Error (Kode: {process.returncode}):[/bold red]\n{stderr}")
            return stdout, stderr # Kembalikan keduanya jika ada error
        return stdout, None
    except FileNotFoundError:
        console.print(f"[bold red]Error:[/bold red] Perintah '{cmd_list[0]}' tidak ditemukan. Pastikan sudah terinstall dan ada di PATH.")
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
    return Panel(title_text, style="bold blue", border_style="blue", title=f"[dim]{AUTHOR}[/dim]" if AUTHOR else None, title_align="right", subtitle=f"[dim]{platform.node()}[/dim]", subtitle_align="left")

def create_main_content():
    """Membuat panel konten utama dengan pesan selamat datang dan waktu."""
    return Panel(
            Text.assemble(
                (f"Selamat datang di ", "white"),
                (APP_NAME, "bold cyan"),
                ("!\nKetik nomor menu dan tekan Enter.", "white"),
                ("\n\nServer Time: ", "dim white"),
                (time.strftime('%Y-%m-%d %H:%M:%S %Z'), "yellow"), # Tambah Timezone
                justify="center" # Pusatkan teks
            ),
            border_style="dim blue",
            title="[ Main Menu ]",
            title_align="center",
            padding=(2, 2) # Beri padding internal
        )

def create_taskbar(options, current_selection_text=""):
    """Membuat panel taskbar."""
    taskbar_items = []
    for i, option in enumerate(options):
        # Beri style berbeda jika ini adalah pilihan yang akan dieksekusi
        # Gunakan background yang kontras untuk highlight
        style = "black on bright_blue" if option == current_selection_text else "none"
        taskbar_items.append(Text(f" {i+1}.{option} ", style=style))
        taskbar_items.append(Text(" │ ", style="dim blue")) # Separator lebih jelas

    # Hilangkan separator terakhir
    if taskbar_items:
        taskbar_items.pop()

    # Gabungkan semua text jadi satu untuk panel
    taskbar_text = Text.assemble(*taskbar_items, justify="center")
    return Panel(taskbar_text, style="blue", border_style="blue") # Hapus title taskbar agar lebih clean

def display_device_info():
    """Menampilkan informasi perangkat dalam tabel."""
    clear_screen()
    console.print(Panel("[bold green]🚀 Informasi Perangkat 🚀[/bold green]", style="green", border_style="green", padding=1))
    info = {} # Inisialisasi info
    try:
        with console.status("[yellow]Mengambil data...", spinner="dots") as status:
            # Perbarui teks status saat mengambil data
            status.update("[yellow]Mengambil info sistem...")
            info = get_device_info()
            time.sleep(0.3)
            status.update("[yellow]Mengambil info CPU...")
            # Panggil ulang cpu_percent untuk nilai yang lebih akurat setelah jeda
            info['CPU Usage'] = f"{psutil.cpu_percent(interval=0.2)}%"
            time.sleep(0.2)
            status.update("[green]Selesai!")
            time.sleep(0.5) # Biar keliatan selesai
    except Exception as e:
        # Tangkap error jika get_device_info gagal total
        console.print(f"[bold red]Error Kritis saat mengambil info:[/bold red] {e}")
        info['Error'] = f"Error Kritis: {e}" # Pastikan ada key 'Error'

    if 'Error' in info:
        # Tampilkan error jika ada, bahkan jika sebagian info berhasil diambil
        console.print(f"[bold red]Error saat mengambil data:[/bold red] {info['Error']}")

    # Selalu coba tampilkan tabel, meskipun ada error (beberapa info mungkin ada)
    table = Table(show_header=True, header_style="bold magenta", border_style="dim blue", title="[ System Overview ]")
    table.add_column("Parameter", style="cyan", width=20, justify="right")
    table.add_column("Value", style="white", min_width=30) # Beri min_width agar tidak terlalu sempit

    # Hanya tampilkan item yang tidak Error
    for key, value in info.items():
        if key != 'Error': # Jangan tampilkan key 'Error' di tabel
             table.add_row(f"{key} :", str(value)) # Tambahkan ':' untuk estetika

    if table.row_count > 0: # Hanya print tabel jika ada isinya
        console.print(table)
    else:
        console.print("[yellow]Tidak ada informasi yang bisa ditampilkan.[/yellow]")


    console.print("\n[yellow]Tekan Enter untuk kembali ke menu utama...[/yellow]")
    input() # Tunggu user menekan Enter

def start_spartan_script():
    """Mulai script spartan.py."""
    clear_screen()
    console.print(f"[bold cyan]Mencoba menjalankan {SPARTAN_SCRIPT}...[/bold cyan]")
    time.sleep(1)

    # Dapatkan path absolut ke direktori script ini berjalan
    current_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(current_dir, SPARTAN_SCRIPT) # Cari di direktori yang sama

    if not os.path.exists(script_path):
        console.print(f"[bold red]Error:[/bold red] File '{SPARTAN_SCRIPT}' tidak ditemukan di direktori:")
        console.print(f"[dim]{current_dir}[/dim]")
        console.print("\n[yellow]Tekan Enter untuk kembali...[/yellow]")
        input()
        return

    command = []
    # Cek apakah executable (hanya relevan di Linux/Mac)
    if os.name != 'nt' and not os.access(script_path, os.X_OK):
         # Coba jalankan dengan python jika tidak executable
         console.print(f"[yellow]Script tidak executable, mencoba menjalankan dengan '{os.path.basename(sys.executable)} {SPARTAN_SCRIPT}'...[/yellow]")
         command = [sys.executable, script_path] # sys.executable -> path python yg sedang jalan
    else:
         # Jika executable (atau di Windows, coba jalankan langsung)
         # Untuk memastikan .py dijalankan dengan Python di Windows, lebih aman pakai sys.executable
         if script_path.endswith('.py'):
             command = [sys.executable, script_path]
         else: # Jika bukan .py tapi executable (misal script bash atau binary)
              command = [script_path]


    # --- Menjalankan script spartan.py ---
    original_stty = None
    try:
        console.print(f"Menjalankan: {' '.join(command)}")
        # Simpan state terminal asli (penting jika spartan.py mengubah mode terminal)
        if os.name != 'nt': # stty hanya ada di Unix-like
            try:
                stty_proc = subprocess.run(['stty', '-g'], capture_output=True, text=True, check=True)
                original_stty = stty_proc.stdout.strip()
            except (FileNotFoundError, subprocess.CalledProcessError) as stty_err:
                 console.print(f"[yellow]Warning: Tidak bisa menyimpan state 'stty': {stty_err}[/yellow]")

        # Jalankan script sebagai subproses dan tunggu selesai
        # Ini akan memblokir sampai spartan.py selesai/ditutup
        process = subprocess.run(command, check=False) # check=False agar kita bisa cek returncode manual

        if process.returncode != 0:
             console.print(f"\n[bold yellow]Warning:[/bold yellow] {SPARTAN_SCRIPT} selesai dengan kode error: {process.returncode}")
        else:
             console.print(f"\n[green]{SPARTAN_SCRIPT} selesai dijalankan.[/green]")

    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error saat menjalankan {SPARTAN_SCRIPT}:[/bold red] {e}")
    except FileNotFoundError:
         # Ini seharusnya tidak terjadi jika sys.executable valid, tapi jaga-jaga
         console.print(f"[bold red]Error:[/bold red] Interpreter Python '{command[0]}' tidak ditemukan.")
    except Exception as e:
         console.print(f"[bold red]Error tak terduga saat menjalankan {SPARTAN_SCRIPT}:[/bold red]")
         console.print_exception(show_locals=False) # Tampilkan traceback error
    finally:
        # Pulihkan state terminal setelah script selesai atau error
        if original_stty and os.name != 'nt':
            try:
                subprocess.run(['stty', original_stty], check=True)
            except (FileNotFoundError, subprocess.CalledProcessError) as stty_restore_err:
                 console.print(f"[yellow]Warning: Tidak bisa memulihkan state 'stty': {stty_restore_err}[/yellow]")

        # Jeda sebelum kembali ke menu
        console.print("\n[yellow]Kembali ke menu utama dalam 3 detik...[/yellow]")
        time.sleep(3)
        # clear_screen() akan dipanggil di loop utama setelah action selesai


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
        Layout(name="main", ratio=1),
        Layout(name="taskbar", size=3) # Ukuran taskbar disesuaikan Panel
    )

    # --- FIX: Isi konten awal SEBELUM Live dimulai ---
    layout["header"].update(create_header())
    layout["main"].update(create_main_content())
    layout["taskbar"].update(create_taskbar(option_names))
    # --- AKHIR FIX ---

    # Gunakan screen=True agar UI menempati seluruh layar dan kembali normal saat keluar
    # transient=True agar output dari action (seperti print di run_command) tidak tercampur
    with Live(layout, refresh_per_second=4, screen=True, transient=True) as live:
        while True:
            # Update bagian yang dinamis (header animasi, waktu di main)
            layout["header"].update(create_header())
            layout["main"].update(create_main_content())
            # Taskbar hanya diupdate saat highlight diperlukan atau sebelum prompt

            # Dapatkan input di luar Live context agar tidak bentrok
            live.stop() # Hentikan Live update SEMENTARA untuk input
            choice = None # Inisialisasi choice
            try:
                # Pastikan taskbar dalam keadaan normal sebelum prompt
                layout["taskbar"].update(create_taskbar(option_names, current_selection_text=""))
                # Tampilkan layout yang sudah diupdate (terutama taskbar normal) sebelum prompt
                # Tidak perlu start/stop lagi, Prompt akan handle renderingnya sendiri
                # live.start(refresh=True)
                # time.sleep(0.05) # Jeda singkat jika diperlukan
                # live.stop()

                # Gunakan Prompt dari Rich untuk input yang lebih bagus
                choice = Prompt.ask(
                    Text.assemble((" Pilih Opsi ", "yellow"), (f"(1-{len(menu_options)})", "bold yellow"), (":", "yellow")), # Prompt lebih menarik
                    choices=list(menu_options.keys()),
                    show_choices=False, # Sembunyikan pilihan default prompt (1,2,3,4,5)
                    # default="5" # Bisa set default jika mau
                )
            except (KeyboardInterrupt, EOFError): # Tangani Ctrl+C atau Ctrl+D
                choice = str(len(menu_options)) # Anggap pilih Exit
                console.print("\n[yellow]Input dibatalkan, memilih Exit.[/yellow]")
                time.sleep(1)
            # Tidak perlu live.start() di sini, akan dihandle oleh logic pilihan atau awal loop berikutnya

            if choice in menu_options:
                option_name, action = menu_options[choice]

                if action is None: # Opsi Exit
                    # live.stop() sudah dipanggil sebelum prompt
                    clear_screen() # Hapus UI Live sebelum pesan keluar
                    console.print(f"[bold green]Exiting {APP_NAME}. Sampai jumpa![/bold green]")
                    # Animasi keluar sederhana
                    for i in track(range(3), description="[red]Shutting down interface..."):
                        time.sleep(0.3)
                    break # Keluar dari loop utama (Live akan otomatis dihentikan)

                # --- Bagian Highlight Taskbar & Eksekusi Action ---
                # live.stop() sudah dipanggil sebelum prompt
                layout["taskbar"].update(create_taskbar(option_names, current_selection_text=option_name))

                # Tampilkan highlight sesaat sebelum action
                live.start(refresh=True) # Mulai Live HANYA untuk menampilkan highlight
                time.sleep(0.4) # Jeda highlight
                live.stop() # Hentikan lagi SEBELUM menjalankan action (agar output action tidak bentrok)
                # --- Akhir Bagian Highlight ---

                clear_screen() # Bersihkan layar SEBELUM action dijalankan
                action() # Jalankan fungsi yang dipilih (misal: display_device_info, run_command)
                # clear_screen() akan dipanggil lagi di awal display_device_info atau start_spartan, jadi mungkin tidak perlu di sini?
                # Tapi biarkan untuk konsistensi jika action tidak clear screen sendiri
                clear_screen()
                # Tidak perlu live.start() di sini, loop akan lanjut dan Live akan start otomatis di awal loop berikutnya
                # Jeda singkat agar user sadar kembali ke menu
                console.print("[dim]Kembali ke menu...[/dim]")
                time.sleep(0.8)
                # Loop akan lanjut, live.start() akan dipanggil oleh context manager 'Live'

            else:
                 # --- Input tidak valid ---
                 # live.stop() sudah dipanggil sebelum prompt
                 original_main_content = layout["main"].renderable # Simpan konten main
                 layout["main"].update(Panel("[bold red] Pilihan tidak valid! Coba lagi. [/bold red]", border_style="red", title="[ Error ]", title_align="center"))
                 # Reset taskbar ke normal jika pilihan salah
                 layout["taskbar"].update(create_taskbar(option_names))

                 live.start(refresh=True) # Tampilkan pesan error dan taskbar normal
                 time.sleep(1.8) # Tahan pesan error sebentar
                 live.stop() # Stop lagi sebelum kembali ke loop normal

                 # Kembalikan konten main (opsional, karena akan di-refresh di loop berikutnya)
                 # layout["main"].update(original_main_content)
                 # Loop lanjut, live akan start di awal loop berikutnya

        # Akhir dari 'with Live(...):'
        # Live akan otomatis stop dan keluar dari screen mode di sini


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Tangkap error tak terduga DILUAR loop utama Live
        # Pastikan keluar dari mode layar alternatif jika ada error
        # Buat console baru untuk memastikan tidak terpengaruh state sebelumnya
        final_console = Console()
        final_console.show_cursor(True)
        # Coba keluar dari screen mode rich jika terjadi error
        # Ini penting jika error terjadi SAAT Live aktif
        if final_console.is_alt_screen:
             try:
                 # Matikan alt screen secara eksplisit
                 # Ini mungkin diperlukan jika 'Live' tidak bersih saat crash
                 final_console.switch_to_alt_screen(False)
                 # print("\n[Debug] Switched off alt screen.") # Pesan debug jika diperlukan
             except Exception as exit_err:
                 print(f"\n[Warning] Gagal mematikan alt screen: {exit_err}")

        # Bersihkan layar setelah (mencoba) keluar dari alt screen
        clear_screen()
        print("\n" * 3) # Beri jarak dari atas
        final_console.print(Panel(f"[bold red on black] [!] Terjadi Error Kritis [!] [/bold red on black]\n\n {e}", border_style="bold red", title="[ Fatal Error ]"))
        print("\nTraceback:")
        # Tampilkan traceback untuk debugging
        traceback.print_exc()
        print("\n[yellow]Interface dihentikan paksa karena error.[/yellow]")
        print("[dim]Silakan cek pesan error di atas untuk detailnya.[/dim]")

    finally:
        # Pastikan cursor selalu terlihat saat keluar, APAPUN yang terjadi
        # Gunakan console baru lagi untuk isolasi
        final_console = Console()
        final_console.show_cursor(True)
        # Pastikan tidak ada sisa alt screen (jaga-jaga kedua)
        if final_console.is_alt_screen:
             try:
                 final_console.switch_to_alt_screen(False)
             except Exception:
                 pass # Abaikan jika gagal di finally
        # print("[Debug] Script exit.") # Pesan debug jika diperlukan
