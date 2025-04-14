#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import subprocess
import platform
import sys
import shlex # For safer command splitting

# --- Konstanta & Konfigurasi ---
APP_NAME = "EXORA SPARTAN - Server Interface"
SPARTAN_SCRIPT = "spartan.py"  # Nama script python yang akan dijalankan
ANIMATION_DELAY = 0.15      # Detik antar frame animasi (atur kecepatan di sini)

# ANSI Colors & Styles
CLR_RESET = "\033[0m"
CLR_BOLD = "\033[1m"
CLR_RED = "\033[91m"
CLR_GREEN = "\033[92m"
CLR_YELLOW = "\033[93m"
CLR_BLUE = "\033[94m"
CLR_MAGENTA = "\033[95m"
CLR_CYAN = "\033[96m"
CLR_WHITE = "\033[97m"

# Palet warna untuk animasi teks
ANIMATION_COLORS = [CLR_CYAN, CLR_BLUE, CLR_MAGENTA, CLR_RED, CLR_YELLOW, CLR_GREEN]

# ASCII Art (Font: Standard - patorjk.com/software/taag/)
# Pastikan tidak ada backslash di akhir baris jika menyalin dari web
ASCII_ART = [
    "  ______ _____  ____          _____ ____  _    ____ _____ _   _   ",
    " |  ____|  __ \|  _ \   /\   / ____/ __ \| |  / __ \_   _| \ | |  ",
    " | |__  | |__) | |_) | /  \ | |   | |  | | | | |  | || | |  \| |  ",
    " |  __| |  _  /|  _ < / /\ \| |   | |  | | | | |  | || | | . ` |  ",
    " | |____| | \ \| |_) / ____ \ |___| |__| | | | |__| || |_| |\  |  ",
    " |______|_|  \_\____/_/    \_\_____\____/|_|_| \____/_____|_| \_|  ",
]
ART_HEIGHT = len(ASCII_ART)
# Hitung lebar art (ambil baris terpanjang) - penting untuk centering
ART_WIDTH = max(len(line) for line in ASCII_ART) if ASCII_ART else 0

# --- Fungsi Helper ---

def get_terminal_size():
    """Mendapatkan ukuran terminal (kolom, baris). Default jika gagal."""
    try:
        return os.get_terminal_size()
    except OSError:
        return os.terminal_size((80, 24)) # Default size

def clear_screen():
    """Membersihkan layar terminal."""
    # Kirim perintah 'clear' (Linux/macOS) atau 'cls' (Windows)
    os.system('cls' if os.name == 'nt' else 'clear')

def display_animated_art(color_offset, term_cols):
    """Menampilkan ASCII art dengan warna berputar."""
    if not ASCII_ART or ART_WIDTH == 0:
        return

    # Hitung padding kiri untuk centering
    left_padding = max(0, (term_cols - ART_WIDTH) // 2)
    padding_str = " " * left_padding

    print("\n" * 2) # Beri jarak dari atas

    for line in ASCII_ART:
        colored_line = ""
        char_in_art_index = 0 # Hanya hitung karakter non-spasi untuk warna
        for char in line:
            if char != ' ':
                # Pilih warna berdasarkan indeks karakter + offset, lalu wrap around
                color_index = (char_in_art_index + color_offset) % len(ANIMATION_COLORS)
                colored_line += f"{ANIMATION_COLORS[color_index]}{char}{CLR_RESET}"
                char_in_art_index += 1
            else:
                colored_line += char # Tambahkan spasi tanpa warna
        print(f"{padding_str}{colored_line}")

    print("\n") # Beri jarak sebelum taskbar

def display_taskbar(term_cols):
    """Menampilkan menu taskbar di bagian bawah."""
    # Opsi menu
    menu_items = [
        f"{CLR_BOLD}[1]{CLR_RESET} Start {SPARTAN_SCRIPT}",
        f"{CLR_BOLD}[2]{CLR_RESET} Device Info",
        f"{CLR_BOLD}[3]{CLR_RESET}{CLR_YELLOW} Restart{CLR_RESET}",
        f"{CLR_BOLD}[4]{CLR_RESET}{CLR_RED} Shutdown{CLR_RESET}",
        f"{CLR_BOLD}[Q]{CLR_RESET} Quit",
    ]
    menu_string = "  |  ".join(menu_items)

    # Hapus kode warna untuk perhitungan panjang
    plain_menu_string = "".join(c for c in menu_string if c not in ''.join(ANIMATION_COLORS) + CLR_RESET + CLR_BOLD + CLR_RED + CLR_YELLOW)

    # Buat garis pemisah sepanjang lebar terminal
    separator = "═" * term_cols

    # Hitung padding kiri untuk centering menu
    left_padding = max(0, (term_cols - len(plain_menu_string)) // 2)
    padding_str = " " * left_padding

    print(separator)
    print(f"{padding_str}{menu_string}")
    print(separator)
    print(f"{CLR_BOLD}Enter your choice:{CLR_RESET} ", end="")
    sys.stdout.flush() # Pastikan prompt muncul sebelum input

def run_command(command_str, requires_sudo=False, capture_output=False):
    """Menjalankan perintah shell dengan aman, opsi sudo dan capture output."""
    command_list = shlex.split(command_str) # Pecah string jadi list argumen yg aman
    prefix = []

    if requires_sudo and os.geteuid() != 0: # Cek apakah sudah root
        prefix = ['sudo']
        print(f"{CLR_YELLOW}Command requires root privileges. Running with sudo...{CLR_RESET}")
        time.sleep(0.5) # Sedikit jeda

    full_command = prefix + command_list
    print(f"Executing: {CLR_CYAN}{' '.join(full_command)}{CLR_RESET}")

    try:
        if capture_output:
            result = subprocess.run(full_command, check=True, capture_output=True, text=True)
            return result.stdout
        else:
            # Gunakan Popen agar tidak menunggu selesai (penting untuk shutdown/reboot)
            # Tapi kita tidak perlu interaksi lebih lanjut di sini
            # subprocess.run() cukup, Python akan menunggu sampai proses dimulai
            subprocess.run(full_command, check=True)
            return True # Sukses memulai
    except FileNotFoundError:
        print(f"{CLR_RED}Error: Command '{command_list[0]}' not found.{CLR_RESET}")
        print("Please ensure it's installed and in your system's PATH.")
        return None # Error: command tidak ditemukan
    except subprocess.CalledProcessError as e:
        print(f"{CLR_RED}Error executing command: {e}{CLR_RESET}")
        if e.stderr:
            print(f"Stderr: {e.stderr}")
        # Bisa jadi karena user cancel sudo password, atau command gagal
        return False # Error: command gagal
    except Exception as e:
        print(f"{CLR_RED}An unexpected error occurred: {e}{CLR_RESET}")
        return False # Error lainnya

def show_device_info():
    """Menampilkan informasi dasar sistem."""
    clear_screen()
    print(f"{CLR_BOLD}{CLR_BLUE}--- System Information ---{CLR_RESET}")
    try:
        uname = platform.uname()
        print(f" System:    {uname.system} {uname.release} ({uname.machine})")
        print(f" Hostname:  {uname.node}")
        print(f" Kernel:    {uname.version}")
        print(f" Processor: {uname.processor if uname.processor else 'N/A'}")

        # Coba dapatkan info RAM/CPU jika psutil terinstall (opsional tapi bagus)
        try:
            import psutil
            print("-" * 26)
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            print(f" RAM Total: {mem.total / (1024**3):.2f} GB")
            print(f" RAM Used:  {mem.percent}% ({mem.used / (1024**3):.2f} GB)")
            print(f" SWAP Total:{swap.total / (1024**3):.2f} GB")
            print(f" SWAP Used: {swap.percent}%")
            print("-" * 26)
            cpu_freq = psutil.cpu_freq()
            print(f" CPU Cores: {psutil.cpu_count(logical=False)} Physical, {psutil.cpu_count(logical=True)} Logical")
            if cpu_freq:
                 print(f" CPU Freq:  {cpu_freq.current:.0f} MHz (Current)")
            print(f" CPU Load:  {psutil.cpu_percent(interval=0.5)}%") # Cek load singkat
        except ImportError:
            print("-" * 26)
            print(f"{CLR_YELLOW}(Install 'psutil' for more details: {CLR_BOLD}pip install psutil{CLR_RESET}{CLR_YELLOW}){CLR_RESET}")
        except Exception as e:
            print(f"{CLR_RED}Error getting psutil info: {e}{CLR_RESET}")

    except Exception as e:
        print(f"{CLR_RED}Error retrieving system info: {e}{CLR_RESET}")

    print(f"\n{CLR_BOLD}{CLR_BLUE}--- End Information ---{CLR_RESET}")
    input("\nPress Enter to return to the main menu...")

def start_spartan_script():
    """Mencoba menjalankan script spartan.py."""
    clear_screen()
    print(f"{CLR_BOLD}Attempting to start {SPARTAN_SCRIPT}...{CLR_RESET}")
    # Periksa apakah file ada
    if not os.path.exists(SPARTAN_SCRIPT):
        print(f"{CLR_RED}Error: Script '{SPARTAN_SCRIPT}' not found in the current directory.{CLR_RESET}")
        print("Please make sure the script exists and has execute permissions if needed.")
        input("\nPress Enter to continue...")
        return

    # Jalankan dengan python3
    # Menggunakan sys.executable memastikan kita pakai interpreter python yg sama
    result = run_command(f"{sys.executable} {SPARTAN_SCRIPT}")

    if result is None or result is False:
        print(f"\n{CLR_RED}Failed to start {SPARTAN_SCRIPT}.{CLR_RESET}")
    else:
        print(f"\n{CLR_GREEN}{SPARTAN_SCRIPT} has finished or exited.{CLR_RESET}")

    input("\nPress Enter to return to the main menu...")

# --- Loop Utama ---

def main_loop():
    """Loop utama untuk animasi dan input menu."""
    color_offset = 0
    last_input_time = time.time()

    # Cek awal apakah spartan.py ada
    if not os.path.exists(SPARTAN_SCRIPT):
         print(f"{CLR_BOLD}{CLR_YELLOW}Warning:{CLR_RESET} Script target '{SPARTAN_SCRIPT}' not found.")
         print("The 'Start Spartan' option will likely fail.")
         print("Continuing in 3 seconds...")
         time.sleep(3)

    try:
        while True:
            term_cols, term_rows = get_terminal_size()

            # Cek apakah terminal cukup besar
            min_rows = ART_HEIGHT + 7 # Art + padding + taskbar + prompt
            if term_cols < ART_WIDTH or term_rows < min_rows:
                clear_screen()
                print(f"{CLR_RED}Terminal too small!{CLR_RESET}")
                print(f"Minimum required size: {ART_WIDTH} columns, {min_rows} rows.")
                print(f"Current size: {term_cols} columns, {term_rows} rows.")
                print("Please resize your terminal and press Enter.")
                # Tunggu user resize, pakai input sederhana
                try:
                   input()
                except EOFError: # Handle Ctrl+D saat resize
                    break
                continue # Coba lagi setelah resize

            # --- Drawing ---
            clear_screen()
            # Tampilkan Judul Aplikasi
            print(f"{CLR_BOLD}{APP_NAME.center(term_cols)}{CLR_RESET}")
            # Tampilkan ASCII Art Animasi
            display_animated_art(color_offset, term_cols)
            # Tampilkan Taskbar
            display_taskbar(term_cols)

            # --- Input Handling (Non-blocking would be complex, using blocking input) ---
            # Animasi akan 'pause' saat menunggu input di sini
            try:
                choice = input().strip().upper()
            except EOFError: # Tangkap Ctrl+D sebagai Quit
                 choice = 'Q'
            except KeyboardInterrupt: # Tangkap Ctrl+C sebagai Quit
                 choice = 'Q'
                 print("\nCtrl+C detected.") # Beri feedback

            # --- Action Handling ---
            action_taken = True # Asumsikan aksi diambil, kecuali invalid choice
            if choice == '1':
                start_spartan_script()
            elif choice == '2':
                show_device_info()
            elif choice == '3':
                clear_screen()
                confirm = input(f"{CLR_BOLD}{CLR_YELLOW}Are you sure you want to RESTART the server? (y/N): {CLR_RESET}").strip().lower()
                if confirm == 'y':
                    print("Issuing restart command...")
                    if run_command("reboot", requires_sudo=True):
                        print(f"{CLR_GREEN}Restart command sent. Exiting interface...{CLR_RESET}")
                        time.sleep(3) # Beri waktu user membaca
                        break # Keluar dari loop karena server akan mati
                    else:
                        print(f"{CLR_RED}Restart command failed or was cancelled.{CLR_RESET}")
                        input("\nPress Enter to continue...")
                else:
                    print("Restart cancelled.")
                    time.sleep(1)
            elif choice == '4':
                clear_screen()
                confirm = input(f"{CLR_BOLD}{CLR_RED}Are you sure you want to SHUT DOWN the server? (y/N): {CLR_RESET}").strip().lower()
                if confirm == 'y':
                    print("Issuing shutdown command...")
                    # 'shutdown now' atau 'poweroff' biasanya bisa dipakai
                    if run_command("shutdown now", requires_sudo=True):
                        print(f"{CLR_GREEN}Shutdown command sent. Exiting interface...{CLR_RESET}")
                        time.sleep(3) # Beri waktu user membaca
                        break # Keluar dari loop karena server akan mati
                    else:
                        print(f"{CLR_RED}Shutdown command failed or was cancelled.{CLR_RESET}")
                        input("\nPress Enter to continue...")
                else:
                    print("Shutdown cancelled.")
                    time.sleep(1)
            elif choice == 'Q':
                print("\nExiting interface...")
                break # Keluar dari loop while True
            else:
                action_taken = False # Tidak ada aksi valid
                print(f"\n{CLR_RED}Invalid choice: '{choice}'. Please try again.{CLR_RESET}")
                time.sleep(1.5) # Jeda singkat sebelum refresh

            # Update color offset for next frame only if no action was taken
            # This makes the animation run smoother between inputs
            if not action_taken:
                color_offset = (color_offset + 1) % 100 # Reset offset agar tidak terlalu besar

            # Kontrol kecepatan loop (jika tidak ada input blocking)
            # Karena input() blocking, sleep ini mungkin tidak terlalu perlu
            # Tapi kita bisa tambahkan sedikit jeda agar tidak terlalu 'flashy' jika user cepat input
            # time.sleep(ANIMATION_DELAY)
            # Kita letakkan color_offset update di sini agar animasi terus berjalan meskipun input salah
            color_offset = (color_offset + 1) % 1000 # Modulo besar agar siklus panjang


    except KeyboardInterrupt:
        print("\nCtrl+C detected. Exiting gracefully...")
    finally:
        # Pastikan terminal bersih saat keluar
        clear_screen()
        print(f"{CLR_BOLD}{CLR_GREEN}Exited {APP_NAME}. Goodbye!{CLR_RESET}")
        # Mengembalikan kursor jika tersembunyi (tidak dilakukan di script ini)
        # print("\033[?25h") # Tampilkan kursor kembali jika disembunyikan

if __name__ == "__main__":
    # Opsional: Sembunyikan kursor saat berjalan (bisa mengganggu input)
    # print("\033[?25l", end="")
    main_loop()
    # Pastikan kursor muncul lagi saat keluar (terutama jika disembunyikan)
    # print("\033[?25h", end="")
