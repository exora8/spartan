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
# Set True untuk melihat output debug parsing wifi (jika masih ada masalah)
DEBUG_PARSING = False
# --- Akhir Konfigurasi ---

console = Console()

def run_command(command_list, check=True, capture_output=True, text=True, timeout=30):
    """Menjalankan command system dan mengembalikan output."""
    try:
        result = subprocess.run(
            command_list,
            check=check,
            capture_output=capture_output,
            text=text,
            timeout=timeout,
            # Pastikan environment language tidak mengganggu output nmcli
            env={**os.environ, 'LC_ALL': 'C'}
        )
        return result
    except FileNotFoundError:
        console.print(f"[bold red]Error:[/bold red] Perintah '{command_list[0]}' tidak ditemukan. Pastikan NetworkManager (nmcli) terinstall.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error menjalankan perintah:[/bold red] {' '.join(command_list)}")
        # Jangan tampilkan stderr/stdout jika kosong atau hanya newline
        if e.stderr and e.stderr.strip():
            console.print(f"[red]Stderr:[/red]\n{e.stderr.strip()}")
        if e.stdout and e.stdout.strip():
            console.print(f"[yellow]Stdout:[/yellow]\n{e.stdout.strip()}")
        # Mengembalikan objek error agar pemanggil bisa cek stderr
        return e
    except subprocess.TimeoutExpired:
        console.print(f"[bold red]Error:[/bold red] Perintah '{' '.join(command_list)}' timed out.")
        return None
    except Exception as e:
        console.print(f"[bold red]Error tak terduga saat menjalankan perintah:[/bold red] {e}")
        return None

def check_root():
    """Memeriksa apakah script dijalankan sebagai root."""
    if os.geteuid() != 0:
        console.print("[bold yellow]Peringatan:[/bold yellow] Script ini sangat disarankan dijalankan dengan hak akses root (sudo) untuk mengelola jaringan.")
        console.print("Silakan jalankan ulang menggunakan: [cyan]sudo python3 {sys.argv[0]}[/cyan]")
        # Beri kesempatan user untuk lanjut, tapi mungkin akan gagal nanti
        try:
            cont = input("Lanjutkan tanpa sudo? (mungkin gagal) [y/N]: ")
            if cont.lower() != 'y':
                sys.exit(1)
        except KeyboardInterrupt:
            print("\nKeluar.")
            sys.exit(1)


def scan_wifi():
    """Scan jaringan Wi-Fi menggunakan nmcli dengan parsing yang lebih robust."""
    console.print("[cyan]🔍 Memindai jaringan Wi-Fi di sekitar...[/cyan]")
    # Fields: BSSID,SSID,CHAN,RATE,SIGNAL,SECURITY (6 fields)
    cmd = ["nmcli", "-g", "BSSID,SSID,CHAN,RATE,SIGNAL,SECURITY", "dev", "wifi", "list", "--rescan", "yes"]
    result = run_command(cmd, capture_output=True, text=True, timeout=20) # Timeout lebih lama dikit

    # Periksa jika command gagal atau tidak ada output
    if result is None or isinstance(result, subprocess.CalledProcessError) or not result.stdout:
         # Jika result adalah error, coba tampilkan stderr jika ada
        stderr_msg = getattr(result, 'stderr', '').strip()
        if stderr_msg:
             console.print(f"[red]Error dari nmcli scan: {stderr_msg}[/red]")
        else:
             console.print("[bold red]❌ Gagal memindai Wi-Fi atau tidak ada output dari nmcli.[/bold red]")
        return None # Kembalikan None jika gagal

    networks = []
    seen_ssids = set() # Untuk menghindari duplikat SSID
    raw_lines = result.stdout.strip().split('\n')

    if DEBUG_PARSING:
        console.print(f"\n[grey50]-- DEBUG: Output Mentah nmcli ({len(raw_lines)} baris) --[/grey50]")
        for i, line in enumerate(raw_lines):
             console.print(f"[grey50]  Line {i+1}: {line}[/grey50]")
        console.print("[grey50]-- Akhir DEBUG --[/grey50]\n")


    for i, line in enumerate(raw_lines):
        line = line.strip()
        if not line:  # Lewati baris kosong
            continue

        # Split dengan ':' maksimal 5 kali -> menghasilkan 6 bagian
        parts = line.split(':', 5)

        if len(parts) == 6:
            # Unpack dan bersihkan spasi ekstra dari setiap bagian
            bssid, ssid, chan, rate_str, signal_str, security_str = map(str.strip, parts)

            # Validasi dasar (SSID tidak boleh kosong)
            if not ssid:
                if DEBUG_PARSING: console.print(f"[grey50]DEBUG: Skipping line {i+1} (SSID kosong): '{line}'[/grey50]")
                continue

            # Bersihkan nilai rate (hapus " Mbit/s" dll)
            rate = rate_str.split(" ")[0] # Ambil angka sebelum spasi pertama
            if not rate.isdigit(): rate = "?" # Jika bukan angka, tandai tidak diketahui

            # Tentukan keamanan dan ikon
            security = security_str if security_str else "Open"
            sec_icon = "🔒" if security != "Open" else "🔓"

            # Konversi sinyal ke integer, tangani jika bukan angka
            signal = 0
            if signal_str.isdigit():
                signal = int(signal_str)
            else:
                if DEBUG_PARSING: console.print(f"[grey50]DEBUG: Invalid signal value '{signal_str}' in line {i+1}, setting signal to 0.[/grey50]")

            # Tambahkan ke daftar jika SSID unik
            if ssid not in seen_ssids:
                networks.append({
                    "bssid": bssid,
                    "ssid": ssid,
                    "signal": signal,
                    "security": security,
                    "icon": sec_icon,
                    "rate": rate,
                    "channel": chan
                })
                seen_ssids.add(ssid)
            # else: # Logika jika ingin handle BSSID berbeda untuk SSID yg sama
            #    if DEBUG_PARSING: print(f"DEBUG: Duplicate SSID '{ssid}' found, skipping.")

        else:
            # Ini adalah baris yang menyebabkan error sebelumnya!
            console.print(f"[yellow]⚠️ Peringatan: Melewati baris output nmcli #{i+1} yang formatnya tidak terduga ({len(parts)} bagian):[/yellow] '{line}'")

    if not networks and raw_lines:
         console.print("[yellow]Tidak ada jaringan yang berhasil diparsing dari output nmcli.[/yellow]")
    elif not networks:
         console.print("[yellow]Tidak ada jaringan Wi-Fi yang terdeteksi.[/yellow]")


    # Urutkan berdasarkan sinyal (tertinggi dulu)
    networks.sort(key=lambda x: x["signal"], reverse=True)
    return networks


def display_networks(networks):
    """Menampilkan jaringan Wi-Fi dalam tabel."""
    if not networks:
        # Pesan sudah ditampilkan di scan_wifi jika kosong
        return

    table = Table(title="📶 Jaringan Wi-Fi Tersedia", show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=3)
    table.add_column("SSID", style="cyan", min_width=20, no_wrap=True) # no_wrap agar tidak pecah
    table.add_column("Sinyal", style="green", justify="right")
    table.add_column("Keamanan", style="yellow")
    table.add_column("Icon", style="dim")
    table.add_column("Rate(Mbps)", style="blue", justify="right") # Optional

    for i, net in enumerate(networks):
        signal_str = f"{net['signal']}%"
        # Tampilkan '?' jika rate tidak diketahui
        rate_str = f"{net['rate']}" if net['rate'] != "?" else "[dim]?[/dim]"

        table.add_row(
            str(i + 1),
            net["ssid"],
            signal_str,
            net["security"],
            net["icon"],
            rate_str
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
        transient=True, # Hilangkan progress bar setelah selesai
    ) as progress:
        progress.add_task(f"Menghubungkan ke [cyan]'{ssid}'[/cyan]...", total=None)
        result = run_command(cmd, timeout=60) # Timeout lebih lama untuk koneksi

    # Cek sukses berdasarkan return code dan output stdout
    if result and result.returncode == 0 and "successfully activated" in result.stdout:
        console.print(f"[bold green]✔️ Berhasil terhubung ke Wi-Fi:[/bold green] [cyan]{ssid}[/cyan]")
        return True
    else:
        console.print(f"[bold red]❌ Gagal terhubung ke Wi-Fi:[/bold red] [cyan]{ssid}[/cyan]")
        # Coba berikan detail error jika ada
        stderr_msg = getattr(result, 'stderr', '').strip()
        stdout_msg = getattr(result, 'stdout', '').strip() # Kadang error ada di stdout juga
        if stderr_msg:
            console.print(f"[red]   -> Detail Error (stderr): {stderr_msg}[/red]")
            # Deteksi error umum
            if "Secrets were required" in stderr_msg or "Invalid password" in stderr_msg:
                 console.print("[red]      (Kemungkinan password salah atau tipe keamanan tidak cocok)[/red]")
            elif "timeout" in stderr_msg.lower():
                 console.print("[red]      (Waktu koneksi habis. Sinyal mungkin lemah atau ada masalah jaringan)[/red]")
        elif stdout_msg and "Error:" in stdout_msg:
             console.print(f"[red]   -> Detail Error (stdout): {stdout_msg}[/red]")
        elif result is None:
             console.print("[red]   -> Perintah koneksi timeout atau gagal dieksekusi.[/red]")
        elif isinstance(result, subprocess.CalledProcessError):
            # Jika return code != 0 tapi tidak ada stderr spesifik
            console.print(f"[red]   -> Perintah nmcli gagal dengan return code {result.returncode}.[/red]")

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
        # check=False karena ping return non-zero jika host down, itu bukan error script
        result = run_command(cmd, check=False, timeout=5)

    # Ping sukses jika return code 0
    if result and result.returncode == 0:
        console.print("[bold green]✔️ Koneksi internet terdeteksi![/bold green]")
        return True
    else:
        console.print(f"[bold red]❌ Tidak ada koneksi internet (tidak bisa ping {PING_HOST}).[/bold red]")
        # Coba berikan info tambahan jika ping gagal
        stderr_msg = getattr(result, 'stderr', '').strip()
        stdout_msg = getattr(result, 'stdout', '').strip()
        if stderr_msg:
            console.print(f"[red]   -> Detail Error: {stderr_msg}[/red]")
        elif stdout_msg:
             # Output ping biasanya di stdout, bisa jadi "unknown host" dll
             console.print(f"[yellow]   -> Output Ping: {stdout_msg}[/yellow]")
        elif result is None:
             console.print("[red]   -> Perintah ping timeout atau gagal dieksekusi.[/red]")

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
        result = run_command(cmd, timeout=90) # Timeout VPN bisa lebih lama

    # Cek sukses
    if result and result.returncode == 0 and "successfully activated" in result.stdout:
        console.print(f"[bold green]✔️ Berhasil terhubung ke VPN:[/bold green] [magenta]{vpn_name}[/magenta]")
        return True
    else:
        console.print(f"[bold red]❌ Gagal terhubung ke VPN:[/bold red] [magenta]{vpn_name}[/magenta]")
        stderr_msg = getattr(result, 'stderr', '').strip()
        stdout_msg = getattr(result, 'stdout', '').strip()
        if stderr_msg:
            console.print(f"[red]   -> Detail Error (stderr): {stderr_msg}[/red]")
        elif stdout_msg and "Error:" in stdout_msg:
             console.print(f"[red]   -> Detail Error (stdout): {stdout_msg}[/red]")
        elif result is None:
             console.print("[red]   -> Perintah koneksi VPN timeout atau gagal dieksekusi.[/red]")
        elif isinstance(result, subprocess.CalledProcessError):
             console.print(f"[red]   -> Perintah nmcli gagal dengan return code {result.returncode}.[/red]")


        # Tampilkan daftar koneksi VPN yang ada jika gagal
        console.print("[yellow]-- Mencoba menampilkan daftar koneksi VPN yang tersedia --[/yellow]")
        list_cmd = ["nmcli", "-g", "NAME,TYPE", "connection", "show"]
        list_result = run_command(list_cmd, check=False, timeout=10)
        vpn_connections = []
        if list_result and list_result.returncode == 0 and list_result.stdout :
            lines = list_result.stdout.strip().split('\n')
            vpn_connections = [line.split(':')[0].strip() for line in lines if ':vpn' in line or ':wireguard' in line]

        if vpn_connections:
            console.print("[yellow]   Koneksi VPN/WireGuard yang terdeteksi di NetworkManager:[/yellow]")
            for vpn in vpn_connections:
                console.print(f"[yellow]   - [bold]{vpn}[/bold][/yellow]")
            console.print(f"[yellow]   Pastikan nama '{vpn_name}' sudah benar dan konfigurasinya valid.[/yellow]")
        else:
            console.print("[yellow]   Tidak ada koneksi tipe VPN atau WireGuard yang ditemukan di NetworkManager.[/yellow]")
            console.print("[yellow]   Pastikan Anda sudah menambahkan koneksi VPN via nmcli/nmtui/GUI.[/yellow]")
        console.print("[yellow]-- Akhir daftar VPN --[/yellow]")
        return False

# --- Main Execution ---
if __name__ == "__main__":
    # check_root() # Pengecekan root sekarang opsional tapi direkomendasikan
    console.print(Panel("[bold blue]🚀 Script Koneksi Wi-Fi & VPN (v2) 🚀[/bold blue]", expand=False, border_style="blue"))

    networks = scan_wifi()

    # Jika scan gagal atau tidak ada network yg valid, keluar
    if networks is None:
        console.print("[red]Gagal melanjutkan karena scan Wi-Fi bermasalah.[/red]")
        sys.exit(1)
    if not networks:
         console.print("[red]Tidak ada jaringan Wi-Fi yang bisa dipilih. Keluar.[/red]")
         sys.exit(1)


    display_networks(networks)

    selected_network = None
    while selected_network is None:
        try:
            choice = input(f"Pilih nomor jaringan Wi-Fi [bold](1-{len(networks)})[/bold] atau 'q' untuk keluar: ")
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
        except (KeyboardInterrupt, EOFError):
             console.print("\n[yellow]Input dibatalkan.[/yellow]")
             sys.exit(1)


    ssid_to_connect = selected_network["ssid"]
    password = None
    # Minta password hanya jika BUKAN 'Open'
    if selected_network["security"] != "Open":
        try:
            password = getpass.getpass(f"Masukkan password untuk [cyan]'{ssid_to_connect}'[/cyan] {selected_network['icon']}: ")
            if not password:
                 console.print("[yellow]Password tidak dimasukkan. Mencoba menghubungkan tanpa password (kemungkinan gagal jika jaringan terproteksi)...[/yellow]")
        except (KeyboardInterrupt, EOFError):
             console.print("\n[yellow]Input password dibatalkan.[/yellow]")
             sys.exit(1)

    # Coba hubungkan ke Wifi
    if connect_wifi(ssid_to_connect, password):
        console.print("[cyan]Memberi jeda beberapa detik agar koneksi stabil...[/cyan]")
        time.sleep(5) # Jeda setelah konek wifi

        # Cek Internet
        if check_internet():
            # Tanyakan nama VPN jika belum di set di config
            vpn_to_connect = DEFAULT_VPN_NAME
            if not vpn_to_connect:
                 try:
                    vpn_to_connect_input = input("Masukkan nama koneksi VPN (sesuai di NetworkManager) atau [bold]Enter[/bold] untuk skip: ").strip()
                    if vpn_to_connect_input: # Hanya set jika user memasukkan sesuatu
                        vpn_to_connect = vpn_to_connect_input
                    else:
                         console.print("[yellow]Koneksi VPN dilewati.[/yellow]")

                 except (KeyboardInterrupt, EOFError):
                    console.print("\n[yellow]Input VPN dibatalkan.[/yellow]")
                    vpn_to_connect = None # Pastikan jadi None jika dibatalkan

            # Jika ada nama VPN (dari default atau input), coba connect
            if vpn_to_connect:
                connect_vpn(vpn_to_connect)
            # else: Koneksi VPN memang di-skip

        else:
            console.print("[yellow]Tidak dapat melanjutkan ke koneksi VPN karena tidak ada koneksi internet.[/yellow]")
    # else: connect_wifi sudah menampilkan pesan error

    console.print("\n[bold blue]✨ Script selesai. ✨[/bold blue]")
    sys.exit(0) # Exit normal
