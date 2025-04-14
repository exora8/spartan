#!/usr/bin/env python3
import subprocess
import sys
import os
import time
import getpass
import re # <-- Import modul Regex
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

# ... (Fungsi run_command, check_root tetap sama seperti v2/v3) ...
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
        console.print(f"[bold red]Error:[/bold red] Perintah '{command_list[0]}' tidak ditemukan.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        # Error sudah ditangani di pemanggil jika diperlukan
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
        console.print("[bold yellow]Peringatan:[/bold yellow] Script ini sangat disarankan dijalankan dengan `sudo`.")
        # Tidak memaksa exit

# --- FUNGSI SCAN WIFI YANG DIPERBARUI DENGAN REGEX ---
def scan_wifi():
    """Scan jaringan Wi-Fi menggunakan nmcli dengan parsing Regex."""
    console.print("[cyan]🔍 Memindai jaringan Wi-Fi di sekitar...[/cyan]")
    cmd = ["nmcli", "-e", "no", "-g", "BSSID,SSID,CHAN,RATE,SIGNAL,SECURITY", "dev", "wifi", "list", "--rescan", "yes"]
    # `-e no`: Minta nmcli TIDAK meng-escape karakter spesial seperti ':'
    # Kita akan handle pemisahan sendiri dengan regex yg lebih canggih
    # Update: Ternyata `-e no` malah bikin kacau jika SSID mengandung ':'.
    # Balik pakai default (escape aktif) dan regex untuk split.
    cmd = ["nmcli", "-g", "BSSID,SSID,CHAN,RATE,SIGNAL,SECURITY", "dev", "wifi", "list", "--rescan", "yes"]

    result = run_command(cmd, capture_output=True, text=True, timeout=25)

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

    # Regex untuk split berdasarkan ':' yang TIDAK diawali '\' (negative lookbehind)
    # Akan split maksimal 5 kali untuk mendapatkan 6 field
    # Contoh: "AA\:BB:CC:SS\:ID:1:100:80:WPA2"
    # Hasil split: ['AA\:BB', 'CC', 'SS\:ID', '1', '100', '80:WPA2'] -> INI SALAH jika security ada ':'
    # Mari kita coba pendekatan regex matching group saja
    # Pola: (BSSID):(SSID):(CHAN):(RATE):(SIGNAL):(SECURITY)
    #       ^-----^ ^----^ ^----^ ^----^ ^------^ ^--------^
    # Kita perlu menangani '\:' di dalam setiap grup.
    # Pola field: [^:]*(?:\\:[^:]*)* -> cocok non-colon ATAU escaped-colon diikuti non-colon, berulang
    field_pattern = r'([^:]*(?:\\:[^:]*)*)' # Pola untuk 1 field yg mungkin ada '\:'
    # Gabungkan 6 field dipisah ':'
    line_regex = re.compile(
        r'^' +             # Awal baris
        field_pattern + r':' + # Grup 1: BSSID
        field_pattern + r':' + # Grup 2: SSID
        field_pattern + r':' + # Grup 3: CHAN
        field_pattern + r':' + # Grup 4: RATE
        field_pattern + r':' + # Grup 5: SIGNAL
        field_pattern +        # Grup 6: SECURITY (bisa kosong)
        r'$'               # Akhir baris
    )


    for i, line in enumerate(raw_lines):
        line = line.strip()
        if not line: continue

        match = line_regex.match(line)

        if match:
            # Ambil semua 6 grup hasil match
            bssid_raw, ssid_raw, chan_raw, rate_raw, signal_raw, security_raw = match.groups()

            # --- Unescape dan Bersihkan ---
            # Ganti '\:' menjadi ':' di BSSID dan SSID (yg paling mungkin)
            bssid = bssid_raw.replace('\\:', ':').strip()
            ssid = ssid_raw.replace('\\:', ':').strip()
            chan = chan_raw.strip() # Channel biasanya angka saja
            rate_str = rate_raw.replace('\\:',':').strip() # Rate bisa ada spasi
            signal_str = signal_raw.strip() # Signal angka saja
            security = security_raw.replace('\\:',':').strip() if security_raw else "Open" # Keamanan bisa kompleks

            if DEBUG_PARSING:
                console.print(f"[grey50]  DEBUG L{i+1}: Parsing line '{line}'[/grey50]")
                console.print(f"[grey50]    -> RAW   : B='{bssid_raw}' S='{ssid_raw}' Ch='{chan_raw}' R='{rate_raw}' Si='{signal_raw}' Se='{security_raw}'[/grey50]")
                console.print(f"[grey50]    -> PARSED: B='{bssid}' S='{ssid}' Ch='{chan}' R='{rate_str}' Si='{signal_str}' Se='{security}' <<--- PERIKSA SSID[/grey50]")


            # Validasi dasar
            if not ssid or not bssid:
                if DEBUG_PARSING: console.print(f"[yellow]  -> Skipping L{i+1}: SSID atau BSSID kosong setelah parse.[/yellow]")
                continue

            # Bersihkan rate
            rate = rate_str.split(" ")[0]
            if not rate.isdigit(): rate = "?"

            # Ikon Keamanan
            sec_icon = "🔒" if security != "Open" else "🔓"

            # Sinyal
            signal = 0
            if signal_str.isdigit():
                signal = int(signal_str)
            else:
                 if DEBUG_PARSING: console.print(f"[yellow]  -> Warning L{i+1}: Signal '{signal_str}' tidak valid, set ke 0.[/yellow]")

            # Tambahkan ke daftar jika SSID unik (berdasarkan nama SSID hasil parse)
            if ssid not in seen_ssids:
                networks.append({
                    "bssid": bssid,
                    "ssid": ssid, # <-- SSID yang sudah bersih
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
            # Baris ini tidak cocok dengan pola Regex sama sekali
            console.print(f"[yellow]⚠️ Peringatan: Melewati baris L{i+1} format tidak cocok Regex:[/yellow] '{line}'")

    # ... (Sisa fungsi scan_wifi: logging hasil, sort, return) ...
    if DEBUG_PARSING and networks:
        console.print("\n[grey50]-- DEBUG: Hasil Parsing Jaringan (Setelah Regex & Unescape) --[/grey50]")
        for idx, net in enumerate(networks):
             console.print(f"[grey50]  #{idx+1}: SSID='[cyan]{net['ssid']}[/cyan]', Signal={net['signal']}%, Security='{net['security']}', BSSID='{net['bssid']}'[/grey50]")
        console.print("[grey50]-- Akhir DEBUG Hasil --[/grey50]\n")

    if not networks and raw_lines:
         console.print("[yellow]Tidak ada jaringan yang berhasil diparsing dari output nmcli.[/yellow]")
    elif not networks:
         console.print("[yellow]Tidak ada jaringan Wi-Fi yang terdeteksi.[/yellow]")

    networks.sort(key=lambda x: x["signal"], reverse=True)
    return networks


# ... (Fungsi display_networks, connect_wifi, check_internet, connect_vpn SAMA seperti v3) ...
# Pastikan mereka menggunakan 'ssid' dari dictionary `net` yang sudah diparsing dgn benar.
def display_networks(networks):
    """Menampilkan jaringan Wi-Fi dalam tabel."""
    if not networks: return
    table = Table(title="📶 Jaringan Wi-Fi Tersedia", show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=3)
    table.add_column("SSID", style="cyan", min_width=20, no_wrap=True) # Tampilkan SSID hasil parse
    table.add_column("Sinyal", style="green", justify="right")
    table.add_column("Keamanan", style="yellow", max_width=25, overflow="ellipsis") # Batasi lebar & potong jika perlu
    table.add_column("Icon", style="dim")
    table.add_column("Rate(Mbps)", style="blue", justify="right")

    for i, net in enumerate(networks):
        signal_str = f"{net['signal']}%"
        rate_str = f"{net['rate']}" if net['rate'] != "?" else "[dim]?[/dim]"
        # Escape markup Rich di SSID dan Security untuk mencegah error tampilan jika mengandung [ atau ]
        display_ssid = net['ssid'].replace('[','\\[')
        display_security = net['security'].replace('[','\\[')
        table.add_row(str(i + 1), display_ssid, signal_str, display_security, net["icon"], rate_str)
    console.print(table)

def connect_wifi(ssid, password=None):
    """Menghubungkan ke jaringan Wi-Fi yang dipilih."""
    # DEBUG untuk memastikan SSID yg dikirim ke NMCLI
    console.print(f"[bold yellow]DEBUG:[/bold yellow] Mencoba koneksi nmcli dengan SSID: '[cyan]{ssid}[/cyan]'") # SSID harusnya sudah benar
    cmd = ["nmcli", "dev", "wifi", "connect", ssid]
    if password:
        cmd.extend(["password", password])

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        progress.add_task(f"Menghubungkan ke [cyan]'{ssid}'[/cyan]...", total=None)
        result = run_command(cmd, timeout=60) # Timeout bisa disesuaikan

    if result and result.returncode == 0 and ("successfully activated" in result.stdout or "Connection successfully activated" in result.stdout): # Cek beberapa variasi pesan sukses
        console.print(f"[bold green]✔️ Berhasil terhubung ke Wi-Fi:[/bold green] [cyan]{ssid}[/cyan]")
        return True
    else:
        console.print(f"[bold red]❌ Gagal terhubung ke Wi-Fi:[/bold red] [cyan]{ssid}[/cyan]")
        stderr_msg = getattr(result, 'stderr', '').strip()
        stdout_msg = getattr(result, 'stdout', '').strip()
        error_msg = stderr_msg if stderr_msg else stdout_msg # Prioritaskan stderr

        if error_msg:
             console.print(f"[red]   -> Detail Error: {error_msg}[/red]")
             if "Secrets were required" in error_msg or "Invalid password" in error_msg:
                 console.print("[red]      (Kemungkinan password salah atau tipe keamanan tidak cocok)[/red]")
             elif "timeout" in error_msg.lower():
                 console.print("[red]      (Waktu koneksi habis. Sinyal lemah atau masalah jaringan)[/red]")
             elif "No network with SSID" in error_msg:
                 console.print("[red]      (SSID tidak ditemukan oleh nmcli saat koneksi. Jaringan hilang atau SSID salah parse?)[/red]")
                 console.print(f"[red]      (SSID yang dicoba: '{ssid}')[/red]")
        elif result is None:
             console.print("[red]   -> Perintah koneksi timeout atau gagal dieksekusi.[/red]")
        elif isinstance(result, subprocess.CalledProcessError):
             console.print(f"[red]   -> Perintah nmcli gagal dengan return code {result.returncode}.[/red]")
        return False

# ... (check_internet, connect_vpn, main execution block sama seperti v3) ...
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
        elif result is None: console.print("[red]   -> Perintah ping timeout.[/red]")
        return False

def connect_vpn(vpn_name):
    """Menghubungkan ke koneksi VPN yang sudah dikonfigurasi."""
    cmd = ["nmcli", "con", "up", "id", vpn_name]
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        progress.add_task(f"Mencoba menghubungkan ke VPN [magenta]'{vpn_name}'[/magenta]...", total=None)
        result = run_command(cmd, timeout=90)
    if result and result.returncode == 0 and ("successfully activated" in result.stdout or "Connection successfully activated" in result.stdout):
        console.print(f"[bold green]✔️ Berhasil terhubung ke VPN:[/bold green] [magenta]{vpn_name}[/magenta]")
        return True
    else:
        console.print(f"[bold red]❌ Gagal terhubung ke VPN:[/bold red] [magenta]{vpn_name}[/magenta]")
        stderr_msg = getattr(result, 'stderr', '').strip()
        stdout_msg = getattr(result, 'stdout', '').strip()
        error_msg = stderr_msg if stderr_msg else stdout_msg
        if error_msg: console.print(f"[red]   -> Detail Error: {error_msg}[/red]")
        elif result is None: console.print("[red]   -> Perintah koneksi VPN timeout.[/red]")
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
        else:
            console.print("[yellow]   Tidak ada koneksi VPN/WireGuard ditemukan.[/yellow]")
        console.print("[yellow]-- Akhir daftar VPN --[/yellow]")
        return False

if __name__ == "__main__":
    # check_root()
    console.print(Panel("[bold blue]🚀 Script Koneksi Wi-Fi & VPN (v4 - Regex Parser) 🚀[/bold blue]", expand=False, border_style="blue"))

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
                if DEBUG_PARSING: # Tampilkan SSID yg dipilih user dari list yg sdh diparse
                     console.print(f"[bold yellow]DEBUG:[/bold yellow] Anda memilih Jaringan #{choice} -> SSID: '[cyan]{selected_network['ssid']}[/cyan]'")
            else:
                console.print(f"[red]Pilihan tidak valid.[/red]")
        except ValueError:
            console.print("[red]Input tidak valid.[/red]")
        except (KeyboardInterrupt, EOFError):
             console.print("\n[yellow]Input dibatalkan.[/yellow]")
             sys.exit(1)

    ssid_to_connect = selected_network["ssid"] # Ini sudah SSID yg bersih hasil regex
    password = None
    if selected_network["security"] != "Open":
        try:
            # Pastikan prompt menampilkan SSID yg benar
            password = getpass.getpass(f"Masukkan password untuk [cyan]'{ssid_to_connect}'[/cyan] {selected_network['icon']}: ")
            if not password:
                 console.print("[yellow]Password tidak dimasukkan. Mencoba tanpa password...[/yellow]")
        except (KeyboardInterrupt, EOFError):
             console.print("\n[yellow]Input password dibatalkan.[/yellow]")
             sys.exit(1)

    if connect_wifi(ssid_to_connect, password):
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
