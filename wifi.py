#!/usr/bin/env python3
import subprocess
import sys
import os
import time
import getpass
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# --- Konfigurasi ---
PING_HOST = "8.8.8.8"  # Host untuk cek koneksi internet
# Nama koneksi VPN yang SUDAH DIKONFIGURASI di NetworkManager
# Biarkan None agar ditanyakan saat runtime, atau isi nama defaultnya
DEFAULT_VPN_NAME = None 
# --- Akhir Konfigurasi ---

console = Console()

def run_command(command_list, check=True, capture_output=True, text=True, timeout=30):
    """Menjalankan command system dan mengembalikan output."""
    try:
        # Penting: Jalankan nmcli sebagai root jika script tidak dijalankan dengan sudo
        # Namun, cara terbaik adalah menjalankan seluruh script dengan sudo
        result = subprocess.run(
            command_list,
            check=check,
            capture_output=capture_output,
            text=text,
            timeout=timeout
        )
        return result
    except FileNotFoundError:
        console.print(f"[bold red]Error:[/bold red] Perintah '{command_list[0]}' tidak ditemukan. Pastikan NetworkManager (nmcli) terinstall.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error menjalankan perintah:[/bold red] {' '.join(command_list)}")
        if e.stderr:
            console.print(f"[red]Stderr:[/red]\n{e.stderr.strip()}")
        if e.stdout:
            console.print(f"[yellow]Stdout:[/yellow]\n{e.stdout.strip()}")
        # Jangan exit di sini, biarkan fungsi pemanggil yang handle
        return None
    except subprocess.TimeoutExpired:
        console.print(f"[bold red]Error:[/bold red] Perintah '{' '.join(command_list)}' timed out.")
        return None
    except Exception as e:
        console.print(f"[bold red]Error tak terduga:[/bold red] {e}")
        return None

def check_root():
    """Memeriksa apakah script dijalankan sebagai root."""
    if os.geteuid() != 0:
        console.print("[bold yellow]Peringatan:[/bold yellow] Script ini perlu dijalankan dengan hak akses root (sudo) untuk mengelola jaringan.")
        console.print("Silakan jalankan ulang menggunakan: [cyan]sudo python3 wifi_vpn_connect.py[/cyan]")
        sys.exit(1)

def scan_wifi():
    """Scan jaringan Wi-Fi menggunakan nmcli."""
    console.print("[cyan]🔍 Memindai jaringan Wi-Fi di sekitar...[/cyan]")
    # -g (--get-values) lebih mudah diparsing
    # Fields: BSSID,SSID,CHAN,RATE,SIGNAL,SECURITY
    cmd = ["nmcli", "-g", "BSSID,SSID,CHAN,RATE,SIGNAL,SECURITY", "dev", "wifi", "list", "--rescan", "yes"]
    result = run_command(cmd, capture_output=True, text=True, timeout=15)

    if result is None or result.returncode != 0:
        console.print("[bold red]❌ Gagal memindai Wi-Fi.[/bold red]")
        return None

    networks = []
    seen_ssids = set() # Untuk menghindari duplikat SSID dengan sinyal berbeda
    raw_lines = result.stdout.strip().split('\n')

    for line in raw_lines:
        try:
            bssid, ssid, chan, rate, signal, security = line.split(':', 5)
            # Bersihkan nilai rate (hapus " Mbit/s")
            rate = rate.replace(" Mbit/s", "").strip()
            # Pilih BSSID dengan sinyal terbaik jika SSID sama
            if ssid and ssid not in seen_ssids:
                 # Hanya tampilkan SSID yang belum terlihat
                 if security:
                     sec_icon = "🔒"
                 else:
                     sec_icon = "🔓" # Ikon untuk jaringan terbuka
                 networks.append({
                     "bssid": bssid,
                     "ssid": ssid,
                     "signal": int(signal),
                     "security": security if security else "Open",
                     "icon": sec_icon,
                     "rate": rate,
                     "channel": chan
                 })
                 seen_ssids.add(ssid) # Tandai SSID sudah ditambahkan
            # Jika SSID sudah ada, cek apakah sinyal baru lebih baik (opsional, bisa kompleks)
            # Untuk simpelnya, kita ambil yang pertama muncul saja
        except ValueError:
            console.print(f"[yellow]⚠️ Peringatan: Melewati baris output nmcli yang tidak valid:[/yellow] {line}")
            continue # Lewati baris yang formatnya tidak sesuai

    # Urutkan berdasarkan sinyal (tertinggi dulu)
    networks.sort(key=lambda x: x["signal"], reverse=True)
    return networks

def display_networks(networks):
    """Menampilkan jaringan Wi-Fi dalam tabel."""
    if not networks:
        console.print("[yellow]Tidak ada jaringan Wi-Fi yang ditemukan.[/yellow]")
        return

    table = Table(title="📶 Jaringan Wi-Fi Tersedia", show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=3)
    table.add_column("SSID", style="cyan", min_width=20)
    table.add_column("Sinyal", style="green", justify="right")
    table.add_column("Keamanan", style="yellow")
    table.add_column("Icon", style="dim")
    # table.add_column("Rate (Mbps)", style="blue", justify="right") # Optional
    # table.add_column("Ch", style="dim", justify="right") # Optional

    for i, net in enumerate(networks):
        signal_str = f"{net['signal']}%"
        table.add_row(
            str(i + 1),
            net["ssid"],
            signal_str,
            net["security"],
            net["icon"],
            # net["rate"], # Optional
            # net["channel"] # Optional
        )

    console.print(table)

def connect_wifi(ssid, password=None):
    """Menghubungkan ke jaringan Wi-Fi yang dipilih."""
    cmd = ["nmcli", "dev", "wifi", "connect", ssid]
    if password:
        cmd.extend(["password", password])

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(f"Menghubungkan ke [cyan]'{ssid}'[/cyan]...", total=None)
        result = run_command(cmd, timeout=60) # Timeout lebih lama untuk koneksi

    if result and "successfully activated" in result.stdout:
        console.print(f"[bold green]✔️ Berhasil terhubung ke Wi-Fi:[/bold green] [cyan]{ssid}[/cyan]")
        return True
    else:
        console.print(f"[bold red]❌ Gagal terhubung ke Wi-Fi:[/bold red] [cyan]{ssid}[/cyan]")
        if result and result.stderr:
           # Coba deteksi error umum
           if "Secrets were required" in result.stderr or "Invalid password" in result.stderr:
               console.print("[red]   -> Kemungkinan password salah atau tipe keamanan tidak cocok.[/red]")
           elif "timeout" in result.stderr.lower():
                console.print("[red]   -> Waktu koneksi habis (timeout). Sinyal mungkin lemah atau ada masalah jaringan.[/red]")
           else:
               console.print(f"[red]   -> Error dari nmcli: {result.stderr.strip()}[/red]")
        elif not result:
             console.print("[red]   -> Tidak ada output atau error dari nmcli (kemungkinan timeout atau proses terhenti).[/red]")
        return False

def check_internet():
    """Memeriksa koneksi internet dengan ping."""
    cmd = ["ping", "-c", "1", "-W", "3", PING_HOST] # Kirim 1 paket, tunggu max 3 detik
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(f"Memeriksa koneksi internet (ping {PING_HOST})...", total=None)
        # Jangan gunakan check=True karena ping return 1 jika host down, itu bukan error script
        result = run_command(cmd, check=False, timeout=5)

    if result and result.returncode == 0:
        console.print("[bold green]✔️ Koneksi internet terdeteksi![/bold green]")
        return True
    else:
        console.print(f"[bold red]❌ Tidak ada koneksi internet (tidak bisa ping {PING_HOST}).[/bold red]")
        return False

def connect_vpn(vpn_name):
    """Menghubungkan ke koneksi VPN yang sudah dikonfigurasi."""
    cmd = ["nmcli", "con", "up", "id", vpn_name]
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(f"Mencoba menghubungkan ke VPN [magenta]'{vpn_name}'[/magenta]...", total=None)
        result = run_command(cmd, timeout=60) # Timeout VPN bisa lebih lama

    if result and "successfully activated" in result.stdout:
        console.print(f"[bold green]✔️ Berhasil terhubung ke VPN:[/bold green] [magenta]{vpn_name}[/magenta]")
        return True
    else:
        console.print(f"[bold red]❌ Gagal terhubung ke VPN:[/bold red] [magenta]{vpn_name}[/magenta]")
        if result and result.stderr:
            console.print(f"[red]   -> Error dari nmcli: {result.stderr.strip()}[/red]")
        elif not result:
             console.print("[red]   -> Tidak ada output atau error dari nmcli.[/red]")

        # Coba tampilkan daftar koneksi VPN yang ada jika gagal
        console.print("[yellow]Mencoba menampilkan daftar koneksi VPN yang tersedia...[/yellow]")
        list_cmd = ["nmcli", "-g", "NAME,TYPE", "con", "show"]
        list_result = run_command(list_cmd, check=False)
        if list_result and list_result.stdout:
            vpn_connections = [line.split(':')[0] for line in list_result.stdout.strip().split('\n') if ':vpn' in line or ':wireguard' in line]
            if vpn_connections:
                console.print("[yellow]   Koneksi VPN yang terdeteksi di NetworkManager:[/yellow]")
                for vpn in vpn_connections:
                    console.print(f"[yellow]   - {vpn}[/yellow]")
            else:
                console.print("[yellow]   Tidak ada koneksi tipe VPN atau WireGuard yang ditemukan di NetworkManager.[/yellow]")
        return False

# --- Main Execution ---
if __name__ == "__main__":
    check_root()
    console.print(Panel("[bold blue]🚀 Script Koneksi Wi-Fi & VPN 🚀[/bold blue]", expand=False))

    networks = scan_wifi()

    if not networks:
        console.print("[red]Keluar.[/red]")
        sys.exit(1)

    display_networks(networks)

    selected_network = None
    while selected_network is None:
        try:
            choice = input(f"Pilih nomor jaringan Wi-Fi (1-{len(networks)}) atau 'q' untuk keluar: ")
            if choice.lower() == 'q':
                console.print("[yellow]Dibatalkan oleh user.[/yellow]")
                sys.exit(0)
            choice_index = int(choice) - 1
            if 0 <= choice_index < len(networks):
                selected_network = networks[choice_index]
            else:
                console.print(f"[red]Pilihan tidak valid. Masukkan angka antara 1 dan {len(networks)}.[/red]")
        except ValueError:
            console.print("[red]Input tidak valid. Masukkan nomor saja.[/red]")
        except KeyboardInterrupt:
             console.print("\n[yellow]Dibatalkan oleh user (Ctrl+C).[/yellow]")
             sys.exit(1)


    ssid_to_connect = selected_network["ssid"]
    password = None
    if selected_network["security"] != "Open":
        try:
            # Menggunakan getpass untuk input password tersembunyi
            password = getpass.getpass(f"Masukkan password untuk [cyan]'{ssid_to_connect}'[/cyan] {selected_network['icon']}: ")
        except KeyboardInterrupt:
             console.print("\n[yellow]Dibatalkan saat input password.[/yellow]")
             sys.exit(1)
        if not password:
             console.print("[yellow]Password tidak dimasukkan. Mencoba menghubungkan tanpa password (mungkin gagal).[/yellow]")


    if connect_wifi(ssid_to_connect, password):
        console.print("[cyan]Menunggu beberapa detik sebelum cek internet...[/cyan]")
        time.sleep(5) # Beri waktu agar koneksi stabil / IP didapatkan

        if check_internet():
            # Tanyakan nama VPN jika belum di set di config
            vpn_to_connect = DEFAULT_VPN_NAME
            if not vpn_to_connect:
                 try:
                    vpn_to_connect = input("Masukkan nama koneksi VPN (sesuai di NetworkManager) atau Enter untuk skip: ")
                 except KeyboardInterrupt:
                    console.print("\n[yellow]Dibatalkan oleh user (Ctrl+C).[/yellow]")
                    sys.exit(1)

            if vpn_to_connect and vpn_to_connect.strip():
                vpn_to_connect = vpn_to_connect.strip()
                connect_vpn(vpn_to_connect)
            else:
                console.print("[yellow]Skipping koneksi VPN.[/yellow]")
        else:
            console.print("[yellow]Tidak dapat melanjutkan ke koneksi VPN karena tidak ada internet.[/yellow]")

    console.print("\n[bold blue]✨ Script selesai. ✨[/bold blue]")
    sys.exit(0) # Exit setelah semua selesai
