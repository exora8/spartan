import os
import sys
import time
import random
import platform
import socket
import subprocess
try:
    from pyfiglet import Figlet
except ImportError:
    print("Error: Modul 'pyfiglet' belum terinstall.")
    print("Silakan install dengan: pip install pyfiglet")
    sys.exit(1)

# --- Konfigurasi ---
APP_TITLE = "exora"
SPARTAN_SCRIPT = "spartan.py" # Pastikan file ini ada atau ganti path
REFRESH_RATE = 0.5 # Detik (untuk animasi warna)
FIGLET_FONT = 'slant' # Coba font lain: 'standard', 'big', 'doom', 'banner3-D'

# --- Kode Warna ANSI ---
COLORS = [
    "\033[31m",  # Merah
    "\033[32m",  # Hijau
    "\033[33m",  # Kuning
    "\033[34m",  # Biru
    "\033[35m",  # Magenta
    "\033[36m",  # Cyan
    "\033[91m",  # Merah Terang
    "\033[92m",  # Hijau Terang
    "\033[93m",  # Kuning Terang
    "\033[94m",  # Biru Terang
    "\033[95m",  # Magenta Terang
    "\033[96m",  # Cyan Terang
]
RESET_COLOR = "\033[0m"
BOLD = "\033[1m"

# --- Fungsi Helper ---
def clear_screen():
    """Membersihkan layar terminal."""
    os.system('cls' if os.name == 'nt' else 'clear')

def get_terminal_size():
    """Mendapatkan ukuran terminal (lebar, tinggi)."""
    try:
        return os.get_terminal_size()
    except OSError:
        return 80, 24 # Default jika gagal

def display_header(text, font):
    """Menampilkan ASCII art dengan warna acak."""
    f = Figlet(font=font)
    ascii_art = f.renderText(text)
    color = random.choice(COLORS)
    print(f"{BOLD}{color}{ascii_art}{RESET_COLOR}")

def display_taskbar():
    """Menampilkan taskbar di bagian bawah."""
    width, _ = get_terminal_size()
    options = "[S]tart Spartan | [I]nfo | [R]estart | [H]alt | [Q]uit"
    # Buat garis pemisah atau latar belakang sederhana
    bar = f"{BOLD}{COLORS[3]}{'═' * width}{RESET_COLOR}"
    # Pusatkan opsi di taskbar jika memungkinkan
    padding = (width - len(options.replace('[S]', 'S').replace('[I]', 'I').replace('[R]', 'R').replace('[H]', 'H').replace('[Q]', 'Q'))) // 2
    taskbar_text = f"{' ' * padding}{BOLD}{COLORS[6]}{options}{RESET_COLOR}"

    # Menggunakan ANSI escape code untuk memposisikan kursor ke baris terakhir
    # \033[<L>;<C>H -> Pindahkan kursor ke baris L, kolom C
    # \033[K -> Hapus dari kursor sampai akhir baris
    # Kita akan print di dua baris terakhir
    sys.stdout.write(f"\033[{get_terminal_size()[1]-1};1H") # Pindah ke baris kedua dari bawah
    sys.stdout.write(bar + '\n') # Print garis
    sys.stdout.write(f"\033[{get_terminal_size()[1]};1H") # Pindah ke baris terakhir
    sys.stdout.write(taskbar_text + "\033[K") # Print opsi dan hapus sisa baris
    sys.stdout.flush()

def get_device_info():
    """Mengumpulkan dan memformat info perangkat."""
    info = []
    try:
        info.append(f"Hostname: {socket.gethostname()}")
    except Exception as e:
        info.append(f"Hostname: Error ({e})")

    info.append(f"OS: {platform.system()} {platform.release()} ({platform.machine()})")
    info.append(f"Platform: {platform.platform()}")

    try:
        # Coba dapatkan IP address utama (mungkin perlu penyesuaian di sistem tertentu)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        s.connect(('8.8.8.8', 80)) # Terhubung ke IP eksternal (tidak mengirim data)
        ip_address = s.getsockname()[0]
        s.close()
        info.append(f"IP Address: {ip_address}")
    except Exception:
        info.append("IP Address: Tidak dapat dideteksi")

    try:
        # Dapatkan uptime (Linux/macOS)
        uptime_str = subprocess.check_output(['uptime', '-p'], text=True).strip()
        info.append(f"Uptime: {uptime_str.replace('up ', '')}")
    except FileNotFoundError:
         info.append("Uptime: Perintah 'uptime' tidak ditemukan")
    except Exception as e:
        info.append(f"Uptime: Error ({e})")

    return "\n".join(info)

def run_spartan():
    """Menjalankan script spartan.py."""
    clear_screen()
    print(f"{BOLD}{COLORS[1]}Menjalankan {SPARTAN_SCRIPT}...{RESET_COLOR}\n")
    try:
        # Menggunakan sys.executable untuk memastikan menggunakan interpreter python yang sama
        subprocess.run([sys.executable, SPARTAN_SCRIPT], check=True)
    except FileNotFoundError:
        print(f"{BOLD}{COLORS[0]}Error: Script '{SPARTAN_SCRIPT}' tidak ditemukan.{RESET_COLOR}")
        input("\nTekan Enter untuk kembali...")
    except subprocess.CalledProcessError as e:
        print(f"{BOLD}{COLORS[0]}Error saat menjalankan '{SPARTAN_SCRIPT}': {e}{RESET_COLOR}")
        input("\nTekan Enter untuk kembali...")
    except Exception as e:
        print(f"{BOLD}{COLORS[0]}Terjadi error tak terduga: {e}{RESET_COLOR}")
        input("\nTekan Enter untuk kembali...")

def shutdown_system():
    """Mematikan sistem (memerlukan sudo)."""
    clear_screen()
    print(f"{BOLD}{COLORS[0]}PERINGATAN: Ini akan mematikan server!{RESET_COLOR}")
    confirm = input("Ketik 'yes' untuk konfirmasi shutdown: ").lower()
    if confirm == 'yes':
        print("Mencoba mematikan sistem (memerlukan hak akses root/sudo)...")
        try:
            # Coba jalankan shutdown. Mungkin perlu password sudo.
            os.system('sudo shutdown now')
            print("Perintah shutdown dikirim.")
            time.sleep(10) # Beri waktu sebelum mungkin keluar
        except Exception as e:
            print(f"{BOLD}{COLORS[0]}Gagal menjalankan shutdown: {e}{RESET_COLOR}")
            print("Pastikan Anda menjalankan script ini dengan user yang punya hak sudo,")
            print("atau jalankan perintah 'sudo shutdown now' secara manual.")
            input("\nTekan Enter untuk kembali...")
    else:
        print("Shutdown dibatalkan.")
        time.sleep(2)

def restart_system():
    """Merestart sistem (memerlukan sudo)."""
    clear_screen()
    print(f"{BOLD}{COLORS[0]}PERINGATAN: Ini akan merestart server!{RESET_COLOR}")
    confirm = input("Ketik 'yes' untuk konfirmasi restart: ").lower()
    if confirm == 'yes':
        print("Mencoba merestart sistem (memerlukan hak akses root/sudo)...")
        try:
            # Coba jalankan reboot. Mungkin perlu password sudo.
            os.system('sudo reboot')
            print("Perintah restart dikirim.")
            time.sleep(10) # Beri waktu sebelum mungkin keluar
        except Exception as e:
            print(f"{BOLD}{COLORS[0]}Gagal menjalankan restart: {e}{RESET_COLOR}")
            print("Pastikan Anda menjalankan script ini dengan user yang punya hak sudo,")
            print("atau jalankan perintah 'sudo reboot' secara manual.")
            input("\nTekan Enter untuk kembali...")
    else:
        print("Restart dibatalkan.")
        time.sleep(2)

# --- Main Loop ---
def main():
    last_input_time = time.time()
    try:
        while True:
            clear_screen()
            # Tampilkan header dengan animasi warna
            display_header(APP_TITLE, FIGLET_FONT)

            # Tambahkan sedikit padding di bawah header
            print("\n" * 2)
            print(f"{BOLD}{COLORS[5]}Selamat datang di Homepage Server Anda!{RESET_COLOR}".center(get_terminal_size()[0]))
            print("\n" * 3) # Beri ruang sebelum taskbar

            # Tampilkan taskbar
            display_taskbar()

            # Cek input non-blocking (susah tanpa library khusus seperti curses)
            # Sebagai gantinya, kita pakai input() tapi dengan timeout 'pura-pura'
            # dengan hanya menunggu input setelah sekian detik tidak ada aktivitas
            # Atau lebih baik, kita langsung minta input saja di setiap loop

            # Minta input di posisi yang aman (misalnya, satu baris di atas taskbar)
            rows, _ = get_terminal_size()
            sys.stdout.write(f"\033[{rows - 3};1H") # Pindah kursor 2 baris di atas taskbar bawah
            sys.stdout.write("\033[K") # Hapus baris input sebelumnya
            try:
                choice = input(f"{BOLD}{COLORS[2]}Pilih opsi: {RESET_COLOR}").lower()
            except EOFError: # Jika input diakhiri (misal Ctrl+D)
                choice = 'q'


            # Proses Pilihan
            if choice == 's':
                run_spartan()
            elif choice == 'i':
                clear_screen()
                display_header(APP_TITLE, FIGLET_FONT) # Tampilkan header lagi
                print(f"\n{BOLD}{COLORS[4]}--- Informasi Perangkat ---{RESET_COLOR}\n")
                print(get_device_info())
                print(f"\n{BOLD}-------------------------{RESET_COLOR}")
                input("\nTekan Enter untuk kembali...")
            elif choice == 'r':
                restart_system()
                # Jika restart berhasil, script mungkin tidak akan lanjut
                # Jika gagal atau dibatalkan, loop akan lanjut
            elif choice == 'h':
                shutdown_system()
                # Jika shutdown berhasil, script mungkin tidak akan lanjut
                # Jika gagal atau dibatalkan, loop akan lanjut
            elif choice == 'q':
                clear_screen()
                print(f"{BOLD}{COLORS[1]}Terima kasih! Sampai jumpa.{RESET_COLOR}")
                sys.exit(0)
            else:
                # Jika input tidak valid, cukup refresh layar di iterasi berikutnya
                pass

            # Sedikit delay untuk animasi (jika tidak ada input)
            # Jika kita selalu meminta input, delay ini tidak terlalu efektif
            # time.sleep(REFRESH_RATE)

    except KeyboardInterrupt:
        clear_screen()
        print(f"\n{BOLD}{COLORS[1]}Keluar... Sampai jumpa!{RESET_COLOR}")
        sys.exit(0)
    finally:
        # Pastikan kursor terlihat dan warna kembali normal saat keluar
        sys.stdout.write("\033[?25h") # Tampilkan kursor
        print(RESET_COLOR)

if __name__ == "__main__":
    main()
