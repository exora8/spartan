#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import platform
import subprocess
import random

# --- Konfigurasi ---
SCRIPT_SPARTAN_LAIN = "spartan.py" # Nama script python lain yang mau dijalankan
KECEPATAN_ANIMASI_ART = 0.03 # Detik per baris (makin kecil makin cepat)
KECEPATAN_ANIMASI_TEKS = 0.05 # Detik per karakter (untuk efek ketik)
KARAKTER_PROMPT = ['>', '#', '$', '*'] # Karakter yang ganti-ganti di prompt input

# --- ASCII Art Spartan (Pilih salah satu atau ganti dengan art favorit lu) ---
# Art oleh 'jgs' (Joan G. Stark) atau sumber lain - pastikan atribusi jika perlu
SPARTAN_ART = r"""
                                       .--.
                                      /.-. '----------.
                                      \'-' .--"--""-"-'
                                       '--' LIL_, lIL
                                          | . /..\ . \
                                          \ L \__/ / \
                                           '.'-.__.-' .'
                                             '--\ '--'
                                                 L__j
                                               .' .'.
                                              / L / \
                                             J  |  L
                                             |  J  |
                                             L / \ J
                                            .'`. .'`.
                                           / L / \ L \
                                          J  |  |  |  L
                                          |  J  |  J  |
                                          L / \ L / \ J
                                         .'`. .'`. .'`.
                                        / J / L J L \ L\
                                       J  |  |  |  |  | L
                                       |  L  |  J  |  J |
                                       L_/ \_L_/ \_L_/ \J
                                      .'`. .'`. .'`. .'`.
                                     / L / L J \ J \ L \
                                    J _|  | | | | | |  |_L
                                    | `'.| | | | | | |.'`|
                                    L___/ `'.| | | |.'` \__J
                                   .'`'.'.`'.`'.`'.'.'.'`'.
                                  / L / L \ L \ L \ L \ L \
                                 J  |  J  |  J  |  J  |  J  |
                                /|  |  |  |  |  |  |  |  |  |
                                J \ J /| / \ | / \ | / \ | / L
                                L__\|/ |/  \|/  \|/  \|/  |/__J
                               .'`'.`'.`'.'`'.'`'.'`'.'`'.'`'.
                              / L / L \ L \ L \ L \ L \ L \ L \
                             J J | | | | | | | | | | | | | | | J
                             | | | | | | | | | | | | | | | | | |
                             L L | | | | | | | | | | | | | | | J
                             |_| | | | | | | | | | | | | | | |_|
                             | | | | | | | | | | | | | | | | | |
                             L_| | | | | | | | | | | | | | | |_J
                             | | | | | | | | | | | | | | | | | |
                             J J | | | | | | | | | | | | | | | L
                             L L | | | | | | | | | | | | | | | J
                             | | | | | | | | | | | | | | | | | |
                             L_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_J
                             | |_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_| |
                             J / / / / / / / / / / / / / / / / L
                             \/_/ / / / / / / / / / / / / / / \/
                              \/_/ / / / / / / / / / / / / / \/
                               \__/ / / / / / / / / / / / / \/
                                \__/ / / / / / / / / / / / \/
                                 \_______________________/
                                  \_____________________/
                                     \_______________/
                                        \_________/
                                          \_____/
                                           `---'
"""

# --- Fungsi Bantuan ---

def clear_screen():
    """Membersihkan layar terminal."""
    os.system('cls' if os.name == 'nt' else 'clear')

def animate_typing(text, delay=KECEPATAN_ANIMASI_TEKS):
    """Animasi teks seperti sedang diketik."""
    for char in text:
        print(char, end='', flush=True)
        time.sleep(delay)
    print() # Pindah baris setelah selesai

def animate_ascii_art(art, delay=KECEPATAN_ANIMASI_ART):
    """Animasi menampilkan ASCII art baris per baris."""
    lines = art.strip().split('\n')
    clear_screen()
    for line in lines:
        print(line)
        time.sleep(delay)
    time.sleep(0.5) # Jeda sejenak setelah art muncul semua

def get_distro_name():
    """Mencoba mendapatkan nama distro Linux."""
    try:
        with open('/etc/os-release') as f:
            for line in f:
                if line.startswith('PRETTY_NAME='):
                    return line.split('=')[1].strip().strip('"')
    except FileNotFoundError:
        pass # Abaikan jika file tidak ada
    # Fallback jika /etc/os-release tidak ada atau tidak punya PRETTY_NAME
    try:
        distro_info = platform.freedesktop_os_release()
        return distro_info.get('PRETTY_NAME', platform.system()) # Coba lagi via platform
    except Exception: # Tangkap semua exception dari freedesktop_os_release jika gagal
        return platform.system() # Fallback paling akhir: nama sistem operasi umum

def show_device_info():
    """Menampilkan informasi perangkat."""
    clear_screen()
    print("🛡️ === INFORMASI PERANGKAT === 🛡️")
    print("-" * 30)
    animate_typing(f"Hostname       : {platform.node()}")
    animate_typing(f"Sistem Operasi : {get_distro_name()} {platform.release()}")
    animate_typing(f"Arsitektur     : {platform.machine()}")
    animate_typing(f"Versi Kernel   : {platform.version()}")
    animate_typing(f"Prosesor       : {platform.processor() if platform.processor() else 'N/A'}")

    print("\n--- Info CPU (dari lscpu) ---")
    try:
        lscpu_out = subprocess.run(['lscpu'], capture_output=True, text=True, check=True, timeout=5)
        cpu_info = ""
        relevant_lines = ['Architecture', 'CPU(s)', 'Model name', 'CPU max MHz', 'Vendor ID']
        for line in lscpu_out.stdout.splitlines():
            for relevant in relevant_lines:
                if line.startswith(relevant):
                    cpu_info += line + "\n"
                    break # Hanya ambil satu baris per keyword
        animate_typing(cpu_info.strip(), delay=0.01) # Animasi lebih cepat untuk output command
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f" Gagal mendapatkan info CPU detail: {e}")
    except Exception as e:
         print(f" Terjadi error tak terduga saat mengambil info CPU: {e}")

    print("\n--- Info Memori (dari free -h) ---")
    try:
        free_out = subprocess.run(['free', '-h'], capture_output=True, text=True, check=True, timeout=5)
        animate_typing(free_out.stdout.strip(), delay=0.01)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f" Gagal mendapatkan info memori: {e}")
    except Exception as e:
         print(f" Terjadi error tak terduga saat mengambil info memori: {e}")


    print("\n--- Info Disk Usage (/) (dari df -h /) ---")
    try:
        df_out = subprocess.run(['df', '-h', '/'], capture_output=True, text=True, check=True, timeout=5)
        animate_typing(df_out.stdout.strip(), delay=0.01)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f" Gagal mendapatkan info disk: {e}")
    except Exception as e:
         print(f" Terjadi error tak terduga saat mengambil info disk: {e}")


    print("\n" + "-" * 30)
    input(" Tekan [Enter] untuk kembali ke menu...")

def display_taskbar_menu():
    """Menampilkan menu taskbar dan mendapatkan pilihan user."""
    print("\n" + "═" * 60) # Garis pemisah ala taskbar
    print(" TASBAR SPARTAN: ")
    print("  [1] Mulai Script Spartan Lainnya ({})".format(SCRIPT_SPARTAN_LAIN))
    print("  [2] Info Perangkat")
    print("  [3] Restart Server (butuh sudo)")
    print("  [4] Shutdown Server (butuh sudo)")
    print("  [0] Keluar Homepage")
    print("═" * 60)

    # Prompt input dengan animasi karakter simpel
    prompt_char = random.choice(KARAKTER_PROMPT)
    try:
        choice = input(f" Pilih Opsi {prompt_char} ")
        return choice.strip()
    except EOFError: # Handle jika input diakhiri (misal Ctrl+D)
        return '0' # Anggap sebagai pilihan keluar

def run_external_script(script_name):
    """Menjalankan script Python eksternal."""
    clear_screen()
    animate_typing(f"🚀 Memulai {script_name}...")
    time.sleep(1)
    try:
        # Menggunakan sys.executable memastikan script dijalankan dgn interpreter python yg sama
        # check=True akan raise CalledProcessError jika script gagal
        subprocess.run([sys.executable, script_name], check=True)
        clear_screen() # Bersihkan layar setelah script selesai
        animate_typing(f"✅ {script_name} selesai. Kembali ke Homepage Spartan.")
        time.sleep(2)
    except FileNotFoundError:
        clear_screen()
        animate_typing(f"❌ Error: Script '{script_name}' tidak ditemukan.")
        animate_typing("Pastikan script ada di direktori yang sama atau dalam PATH.")
        time.sleep(3)
    except subprocess.CalledProcessError as e:
        clear_screen()
        animate_typing(f"❌ Error saat menjalankan {script_name}:")
        animate_typing(f"   Return code: {e.returncode}")
        # Coba tampilkan output error jika ada
        if e.stderr:
             animate_typing(f"   Error output:\n{e.stderr}")
        elif e.stdout:
             animate_typing(f"   Output:\n{e.stdout}")
        time.sleep(4)
    except Exception as e:
        clear_screen()
        animate_typing(f"❌ Terjadi error tak terduga saat mencoba menjalankan {script_name}:")
        animate_typing(str(e))
        time.sleep(4)

def confirm_and_execute(action_name, command):
    """Meminta konfirmasi dan menjalankan command sistem (biasanya butuh sudo)."""
    clear_screen()
    print(f"⚠️ PERINGATAN! ⚠️")
    animate_typing(f"Anda akan melakukan: {action_name.upper()}")
    animate_typing("Tindakan ini biasanya memerlukan hak akses 'sudo'.")
    time.sleep(0.5)
    try:
        confirm = input(f"Apakah Anda yakin ingin melanjutkan? (ketik 'yes' untuk konfirmasi): ").lower()
        if confirm == 'yes':
            animate_typing(f"🛡️ Melaksanakan {action_name}... MOLON LABE!")
            time.sleep(1)
            # os.system lebih simpel untuk command yg mungkin interaktif minta password sudo
            # Tapi kurang aman dibanding subprocess jika command-nya dari input user (di sini aman krn command fixed)
            exit_code = os.system(command)
            if exit_code != 0:
                 # Jika gagal (misal password sudo salah atau user bukan sudoer)
                 animate_typing(f" Gagal menjalankan command. Kode keluar: {exit_code}")
                 animate_typing(f" Pastikan Anda punya hak akses 'sudo' atau command '{command}' valid.")
                 time.sleep(3)
            # Jika berhasil, script mungkin tidak akan sampai sini krn server mati/restart
            time.sleep(5) # Jeda sedikit kalaupun command tidak langsung exit
        else:
            animate_typing("🚫 Tindakan dibatalkan.")
            time.sleep(1.5)
    except EOFError:
        animate_typing("\n🚫 Input dibatalkan.")
        time.sleep(1.5)


# --- Main Loop ---
if __name__ == "__main__":
    try:
        while True:
            # 1. Animasi ASCII Art
            animate_ascii_art(SPARTAN_ART)

            # 2. Judul
            print("\n" + " " * 10 + "🔥 === SELAMAT DATANG DI HOMEPAGE SERVER SPARTAN === 🔥")

            # 3. Tampilkan Taskbar Menu
            choice = display_taskbar_menu()

            # 4. Proses Pilihan
            if choice == '1':
                run_external_script(SCRIPT_SPARTAN_LAIN)
            elif choice == '2':
                show_device_info()
            elif choice == '3':
                confirm_and_execute("Restart Server", "sudo reboot")
            elif choice == '4':
                confirm_and_execute("Shutdown Server", "sudo shutdown -h now")
            elif choice == '0':
                clear_screen()
                animate_typing("🛡️ Meninggalkan Homepage Spartan... Sampai jumpa, Ksatria!")
                time.sleep(1)
                animate_typing("MOLON LABE!")
                time.sleep(1.5)
                break # Keluar dari loop while
            else:
                animate_typing(" Pilihan tidak valid. Coba lagi, Ksatria!")
                time.sleep(1.5)

    except KeyboardInterrupt:
        clear_screen()
        print("\n🛑 Ctrl+C terdeteksi. Keluar dari Homepage Spartan... MOLON LABE!")
        time.sleep(1.5)
    finally:
        clear_screen() # Pastikan layar bersih saat script benar-benar berakhir
        # Mungkin perlu reset warna terminal jika menggunakan library pewarnaan
        # os.system('tput sgr0') # Contoh reset terminal (jika perlu)
