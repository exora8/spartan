#!/usr/bin/env python3
import subprocess
import sys
import os
import time
import getpass
import re # Import regex
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# --- Konfigurasi ---
PING_HOST = "8.8.8.8"
DEFAULT_VPN_NAME = None
# >>>>> AKTIFKAN DEBUG INI UNTUK MELIHAT PARSING <<<<<
DEBUG_PARSING = True
# --- Akhir Konfigurasi ---

console = Console()

# ... (Fungsi run_command, check_root tetap sama seperti v2) ...
def run_command(command_list, check=True, capture_output=True, text=True, timeout=30):
    """Menjalankan command system dan mengembalikan output."""
    try:
        result = subprocess.run(
            command_list,
            check=check,
            capture_output=capture_output,
            text=text,
            timeout=timeout,
            env={**os.environ, 'LC_ALL': 'C'} # Force locale C
        )
        return result
    except FileNotFoundError:
        console.print(f"[bold red]Error:[/bold red] Perintah '{command_list[0]}' tidak ditemukan. Pastikan NetworkManager (nmcli) terinstall.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error menjalankan perintah:[/bold red] {' '.join(command_list)}")
        if e.stderr and e.stderr.strip():
            console.print(f"[red]Stderr:[/red]\n{e.stderr.strip()}")
        if e.stdout and e.stdout.strip():
            console.print(f"[yellow]Stdout:[/yellow]\n{e.stdout.strip()}")
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
        console.print("[bold yellow]Peringatan:[/bold yellow] Script ini sangat disarankan dijalankan dengan hak akses root (sudo).")
        console.print("Menjalankan tanpa sudo mungkin gagal saat mencoba koneksi.")
        # Tidak exit, biarkan user mencoba tapi beri peringatan

# --- FUNGSI SCAN WIFI YANG DIPERBARUI ---
def scan_wifi():
    """Scan jaringan Wi-Fi menggunakan nmcli dengan parsing yang lebih robust."""
    console.print("[cyan]🔍 Memindai jaringan Wi-Fi di sekitar...[/cyan]")
    # Fields: BSSID,SSID,CHAN,RATE,SIGNAL,SECURITY (6 fields)
    # Tetap pakai -g, tapi parsing akan lebih hati-hati
    cmd = ["nmcli", "-g", "BSSID,SSID,CHAN,RATE,SIGNAL,SECURITY", "dev", "wifi", "list", "--rescan", "yes"]
    result = run_command(cmd, capture_output=True, text=True, timeout=25) # Tambah sedikit timeout

    if result is None or isinstance(result, subprocess.CalledProcessError) or not result.stdout:
        stderr_msg = getattr(result, 'stderr', '').strip()
        if stderr_msg:
             console.print(f"[red]Error dari nmcli scan: {stderr_msg}[/red]")
        else:
             console.print("[bold red]❌ Gagal memindai Wi-Fi atau tidak ada output dari nmcli.[/bold red]")
        return None

    networks = []
    seen_ssids = set()
    raw_lines = result.stdout.strip().split('\n')

    if DEBUG_PARSING:
        console.print(f"\n[grey50]-- DEBUG: Output Mentah nmcli ({len(raw_lines)} baris) --[/grey50]")
        for i, line in enumerate(raw_lines):
             console.print(f"[grey50]  L{i+1}: {line}[/grey50]")
        console.print("[grey50]-- Akhir DEBUG Mentah --[/grey50]\n")

    for i, line in enumerate(raw_lines):
        line = line.strip()
        if not line: continue

        # --- LOGIKA PARSING BARU ---
        # Kita tahu ada 5 ':' sebagai pemisah KECUALI jika ada ':' di dalam SSID itu sendiri.
        # nmcli -g SEHARUSNYA menangani ini dengan escaping (\:) tapi mari kita coba cara lain.
        # Asumsi: BSSID, CHAN, RATE, SIGNAL, SECURITY tidak mengandung ':'
        # Jadi, SSID adalah semua di antara ':' pertama dan ':' kedua dari *belakang*
        parts = line.split(':')

        if len(parts) >= 6: # Minimal harus ada 6 bagian (5 pemisah)
            bssid = parts[0].strip()
            # Bagian terakhir adalah security, sebelumnya signal, sebelumnya rate, sebelumnya channel
            security_str = parts[-1].strip()
            signal_str = parts[-2].strip()
            rate_str = parts[-3].strip()
            chan = parts[-4].strip()
            # Semua yang ditengah adalah SSID (gabungkan kembali jika SSID mengandung ':')
            ssid = ":".join(parts[1:-4]).strip()

            if DEBUG_PARSING:
                console.print(f"[grey50]  DEBUG L{i+1}: Parsing line '{line}'[/grey50]")
                console.print(f"[grey50]    -> BSSID : '{bssid}'[/grey50]")
                console.print(f"[grey50]    -> SSID  : '{ssid}' <<--- PERIKSA INI![/grey50]")
                console.print(f"[grey50]    -> CHAN  : '{chan}'[/grey50]")
                console.print(f"[grey50]    -> RATE  : '{rate_str}'[/grey50]")
                console.print(f"[grey50]    -> SIGNAL: '{signal_str}'[/grey50]")
                console.print(f"[grey50]    -> SECUR : '{security_str}'[/grey50]")

            # Validasi dasar
            if not ssid or not bssid: # Perlu SSID dan BSSID
                if DEBUG_PARSING: console.print(f"[yellow]  -> Skipping L{i+1}: SSID atau BSSID kosong.[/yellow]")
                continue

            # Bersihkan rate
            rate = rate_str.split(" ")[0]
            if not rate.isdigit(): rate = "?"

            # Keamanan & Ikon
            security = security_str if security_str else "Open"
            sec_icon = "🔒" if security != "Open" else "🔓"

            # Sinyal
            signal = 0
            if signal_str.isdigit():
                signal = int(signal_str)
            else:
                 if DEBUG_PARSING: console.print(f"[yellow]  -> Warning L{i+1}: Signal '{signal_str}' tidak valid, set ke 0.[/yellow]")


            # Tambahkan ke daftar jika SSID unik (berdasarkan nama SSID hasil parse)
            # PENTING: Gunakan SSID hasil parsing yang (semoga) sudah benar
            if ssid not in seen_ssids:
                networks.append({
                    "bssid": bssid,
                    "ssid": ssid, # <--- Simpan SSID yang sudah diparsing
                    "signal": signal,
                    "security": security,
                    "icon": sec_icon,
                    "rate": rate,
                    "channel": chan
                })
                seen_ssids.add(ssid)
            else:
                 if DEBUG_PARSING: console.print(f"[grey50]  -> Skipping L{i+1}: Duplicate SSID '{ssid}' already added.[/grey50]")

        else:
            # Baris ini tidak punya cukup bagian (minimal 6)
            console.print(f"[yellow]⚠️ Peringatan: Melewati baris L{i+1} format tidak terduga ({len(parts)} bagian):[/yellow] '{line}'")
            if DEBUG_PARSING: console.print(f"[grey50]     Parts found: {parts}[/grey50]")

    # ... (sisanya sama seperti v2, urutkan, etc.) ...

    if DEBUG_PARSING and networks:
        console.print("\n[grey50]-- DEBUG: Hasil Parsing Jaringan --[/grey50]")
        for idx, net in enumerate(networks):
             console.print(f"[grey50]  #{idx+1}: SSID='{net['ssid']}', Signal={net['signal']}%, Security='{net['security']}'[/grey50]")
        console.print("[grey50]-- Akhir DEBUG Hasil --[/grey50]\n")


    if not networks and raw_lines:
         console.print("[yellow]Tidak ada jaringan yang berhasil diparsing dari output nmcli.[/yellow]")
    elif not networks:
         console.print("[yellow]Tidak ada jaringan Wi-Fi yang terdeteksi.[/yellow]")

    networks.sort(key=lambda x: x["signal"], reverse=True)
    return networks


# ... (Fungsi display_networks, connect_wifi, check_internet, connect_vpn tetap sama seperti v2) ...
def display_networks(networks):
    """Menampilkan jaringan Wi-Fi dalam tabel."""
    if not networks:
        return
    table = Table(title="📶 Jaringan Wi-Fi Tersedia", show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=3)
    table.add_column("SSID", style="cyan", min_width=20, no_wrap=True) # Tampilkan SSID hasil parse
    table.add_column("Sinyal", style="green", justify="right")
    table.add_column("Keamanan", style="yellow")
    table.add_column("Icon", style="dim")
    table.add_column("Rate(Mbps)", style="blue", justify="right")

    for i, net in enumerate(networks):
        signal_str = f"{net['signal']}%"
        rate_str = f"{net['rate']}" if net['rate'] != "?" else "[dim]?[/dim]"
        table.add_row(str(i + 1), net["ssid"], signal_str, net["security"], net["icon"], rate_str)
    console.print(table)

def connect_wifi(ssid, password=None):
    """Menghubungkan ke jaringan Wi-Fi yang dipilih."""
    # Tambahkan debug print di sini juga untuk memastikan SSID yang DIKIRIM ke nmcli
    console.print(f"[bold yellow]DEBUG:[/bold yellow] Mencoba koneksi nmcli dengan SSID: '[cyan]{ssid}[/cyan]'")
    cmd = ["nmcli", "dev", "wifi", "connect", ssid] # Gunakan SSID yang sudah diparsing
    if password:
        cmd.extend(["password", password])

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        progress.add_task(f"Menghubungkan ke [cyan]'{ssid}'[/cyan]...", total=None)
        result = run_command(cmd, timeout=60)

    if result and result.returncode == 0 and "successfully activated" in result.stdout:
        console.print(f"[bold green]✔️ Berhasil terhubung ke Wi-Fi:[/bold green] [cyan]{ssid}[/cyan]")
        return True
    else:
        console.print(f"[bold red]❌ Gagal terhubung ke Wi-Fi:[/bold red] [cyan]{ssid}[/cyan]")
        stderr_msg = getattr(result, 'stderr', '').strip()
        stdout_msg = getattr(result, 'stdout', '').strip()
        if stderr_msg: console.print(f"[red]   -> Detail Error (stderr): {stderr_msg}[/red]")
        elif stdout_msg and ("Error:" in stdout_msg or "No network with SSID" in stdout_msg): # Tangkap error di stdout juga
             console.print(f"[red]   -> Detail Error (stdout): {stdout_msg}[/red]")
        elif result is None: console.print("[red]   -> Perintah koneksi timeout atau gagal dieksekusi.[/red]")
        elif isinstance(result, subprocess.CalledProcessError): console.print(f"[red]   -> Perintah nmcli gagal dengan return code {result.returncode}.[/red]")
        # Tambahkan saran jika errornya "No network with SSID"
        if stderr_msg and "No network with SSID" in stderr_msg or stdout_msg and "No network with SSID" in stdout_msg:
            console.print("[red]      (Pastikan SSID yang ditampilkan di tabel sudah benar dan jaringan masih tersedia)[/red]")
        return False

def check_internet():
    """Memeriksa koneksi internet dengan ping."""
    cmd = ["ping", "-c", "1", "-W", "3", PING_HOST]
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        progress.add_task(f"Memeriksa koneksi internet (ping {PING_HOST})...", total=None)
        result = run_command(cmd, check=False, timeout=5)
    if result and result.returncode == 0:
        console.print("[bold green]✔️ Koneksi internet terdeteksi![/bold green]")
        return True
    else:
        console.print(f"[bold red]❌ Tidak ada koneksi internet (tidak bisa ping {PING_HOST}).[/bold red]")
        stderr_msg = getattr(result, 'stderr', '').strip()
        stdout_msg = getattr(result, 'stdout', '').strip()
        if stderr_msg: console.print(f"[red]   -> Detail Error: {stderr_msg}[/red]")
        elif stdout_msg: console.print(f"[yellow]   -> Output Ping: {stdout_msg}[/yellow]")
        elif result is None: console.print("[red]   -> Perintah ping timeout atau gagal dieksekusi.[/red]")
        return False

def connect_vpn(vpn_name):
    """Menghubungkan ke koneksi VPN yang sudah dikonfigurasi."""
    cmd = ["nmcli", "con", "up", "id", vpn_name]
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        progress.add_task(f"Mencoba menghubungkan ke VPN [magenta]'{vpn_name}'[/magenta]...", total=None)
        result = run_command(cmd, timeout=90)
    if result and result.returncode == 0 and "successfully activated" in result.stdout:
        console.print(f"[bold green]✔️ Berhasil terhubung ke VPN:[/bold green] [magenta]{vpn_name}[/magenta]")
        return True
    else:
        console.print(f"[bold red]❌ Gagal terhubung ke VPN:[/bold red] [magenta]{vpn_name}[/magenta]")
        stderr_msg = getattr(result, 'stderr', '').strip()
        stdout_msg = getattr(result, 'stdout', '').strip()
        if stderr_msg: console.print(f"[red]   -> Detail Error (stderr): {stderr_msg}[/red]")
        elif stdout_msg and "Error:" in stdout_msg: console.print(f"[red]   -> Detail Error (stdout): {stdout_msg}[/red]")
        elif result is None: console.print("[red]   -> Perintah koneksi VPN timeout atau gagal dieksekusi.[/red]")
        elif isinstance(result, subprocess.CalledProcessError): console.print(f"[red]   -> Perintah nmcli gagal dengan return code {result.returncode}.[/red]")

        console.print("[yellow]-- Mencoba menampilkan daftar koneksi VPN yang tersedia --[/yellow]")
        list_cmd = ["nmcli", "-g", "NAME,TYPE", "connection", "show"]
        list_result = run_command(list_cmd, check=False, timeout=10)
        vpn_connections = []
        if list_result and list_result.returncode == 0 and list_result.stdout :
            lines = list_result.stdout.strip().split('\n')
            vpn_connections = [line.split(':')[0].strip() for line in lines if ':vpn' in line or ':wireguard' in line]
        if vpn_connections:
            console.print("[yellow]   Koneksi VPN/WireGuard yang terdeteksi:[/yellow]")
            for vpn in vpn_connections: console.print(f"[yellow]   - [bold]{vpn}[/bold][/yellow]")
            console.print(f"[yellow]   Pastikan nama '{vpn_name}' benar.[/yellow]")
        else:
            console.print("[yellow]   Tidak ada koneksi VPN/WireGuard ditemukan.[/yellow]")
        console.print("[yellow]-- Akhir daftar VPN --[/yellow]")
        return False


# --- Main Execution ---
if __name__ == "__main__":
    # check_root() # Peringatan saja, tidak memaksa exit
    console.print(Panel("[bold blue]🚀 Script Koneksi Wi-Fi & VPN (v3 - Fix Parsing) 🚀[/bold blue]", expand=False, border_style="blue"))

    networks = scan_wifi()

    if networks is None:
        console.print("[red]Gagal melanjutkan karena scan Wi-Fi bermasalah.[/red]")
        sys.exit(1)
    if not networks:
         console.print("[red]Tidak ada jaringan Wi-Fi valid ditemukan. Keluar.[/red]")
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
                # >>>>> DEBUG: Tampilkan SSID yang dipilih <<<<<
                console.print(f"[bold yellow]DEBUG:[/bold yellow] Anda memilih Jaringan #{choice} dengan SSID: '[cyan]{selected_network['ssid']}[/cyan]'")
            else:
                console.print(f"[red]Pilihan tidak valid.[/red]")
        except ValueError:
            console.print("[red]Input tidak valid.[/red]")
        except (KeyboardInterrupt, EOFError):
             console.print("\n[yellow]Input dibatalkan.[/yellow]")
             sys.exit(1)

    # Gunakan SSID dari selected_network yang sudah diparsing dengan benar
    ssid_to_connect = selected_network["ssid"]
    password = None
    if selected_network["security"] != "Open":
        try:
            password = getpass.getpass(f"Masukkan password untuk [cyan]'{ssid_to_connect}'[/cyan] {selected_network['icon']}: ")
            if not password:
                 console.print("[yellow]Password tidak dimasukkan. Mencoba tanpa password...[/yellow]")
        except (KeyboardInterrupt, EOFError):
             console.print("\n[yellow]Input password dibatalkan.[/yellow]")
             sys.exit(1)

    if connect_wifi(ssid_to_connect, password): # Pass SSID yang sudah benar
        console.print("[cyan]Memberi jeda beberapa detik...[/cyan]")
        time.sleep(5)
        if check_internet():
            vpn_to_connect = DEFAULT_VPN_NAME
            if not vpn_to_connect:
                 try:
                    vpn_to_connect_input = input("Masukkan nama koneksi VPN atau [bold]Enter[/bold] untuk skip: ").strip()
                    if vpn_to_connect_input: vpn_to_connect = vpn_to_connect_input
                    else: console.print("[yellow]Koneksi VPN dilewati.[/yellow]")
                 except (KeyboardInterrupt, EOFError):
                    console.print("\n[yellow]Input VPN dibatalkan.[/yellow]")
                    vpn_to_connect = None
            if vpn_to_connect:
                connect_vpn(vpn_to_connect)
        else:
            console.print("[yellow]Tidak dapat melanjutkan ke VPN (tidak ada internet).[/yellow]")

    console.print("\n[bold blue]✨ Script selesai. ✨[/bold blue]")
    sys.exit(0)
