import pywifi
from pywifi import const
import subprocess
import time
import netifaces
import requests
from tqdm import tqdm
from colorama import Fore, Style, init
import os
from dotenv import load_dotenv

# Inisialisasi colorama untuk output berwarna
init(autoreset=True)

# Load environment variables dari file .env
load_dotenv()

VPN_PROVIDER = os.getenv("VPN_PROVIDER")
VPN_CONFIG = os.getenv("VPN_CONFIG")
VPN_USERNAME = os.getenv("VPN_USERNAME")
VPN_PASSWORD = os.getenv("VPN_PASSWORD")

# --- Fungsi-fungsi ---

def scan_wifi():
    """Memindai jaringan WiFi di sekitar."""
    wifi = pywifi.PyWiFi()
    ifaces = wifi.interfaces()
    if not ifaces:
        print(Fore.RED + "Tidak ada antarmuka WiFi yang terdeteksi." + Style.RESET_ALL)
        return None

    iface = ifaces.pop()
    print(Fore.YELLOW + f"Memindai jaringan WiFi menggunakan antarmuka: {iface.name()}" + Style.RESET_ALL)

    iface.scan()
    time.sleep(5)  # Beri waktu untuk pemindaian selesai
    scan_results = iface.scan_results()
    if not scan_results:
        print(Fore.YELLOW + "Tidak ada jaringan WiFi yang ditemukan." + Style.RESET_ALL)
        return None

    print(Fore.GREEN + "\nDaftar Jaringan WiFi Tersedia:" + Style.RESET_ALL)
    for i, network in enumerate(scan_results):
        print(f"{i+1}. {network.ssid}")
    return scan_results, iface

def pilih_wifi(scan_results):
    """Meminta pengguna untuk memilih jaringan WiFi."""
    while True:
        try:
            pilihan = int(input(Fore.CYAN + "Pilih nomor jaringan WiFi untuk dihubungkan: " + Style.RESET_ALL))
            if 1 <= pilihan <= len(scan_results):
                return scan_results[(pilihan - 1)]
            else:
                print(Fore.RED + "Pilihan tidak valid. Silakan coba lagi." + Style.RESET_ALL)
        except ValueError:
            print(Fore.RED + "Input tidak valid. Masukkan angka." + Style.RESET_ALL)

def connect_wifi(iface, selected_network):
    """Mencoba menghubungkan ke jaringan WiFi yang dipilih."""
    profile = pywifi.Profile()
    profile.ssid = selected_network.ssid
    profile.auth = const.AUTH_WPA2PSK  # Asumsi menggunakan WPA2 PSK, sesuaikan jika beda
    profile.akm.append(const.AKM_TKIP)
    profile.akm.append(const.AKM_CCMP)
    profile.cipher = const.CIPHER_CCMP  # Asumsi menggunakan CCMP, sesuaikan jika beda

    # **PENTING:** Untuk script ini berjalan tanpa interaksi lebih lanjut,
    # kamu perlu menyimpan password WiFi di suatu tempat yang aman atau
    # meminta input password di sini. Untuk kesederhanaan, ini dihilangkan.
    # Jika kamu ingin otomatis terhubung ke jaringan yang sudah dikenal,
    # kamu bisa menyimpan profilnya dan menggunakannya kembali.

    print(Fore.YELLOW + f"Mencoba menghubungkan ke: {selected_network.ssid}..." + Style.RESET_ALL)

    iface.remove_all_network_profiles()
    tmp_profile = iface.add_network_profile(profile)

    iface.connect(tmp_profile)
    time.sleep(10)  # Beri waktu untuk koneksi

    if iface.status() == const.IFACE_CONNECTED:
        print(Fore.GREEN + f"Berhasil terhubung ke: {selected_network.ssid}" + Style.RESET_ALL)
        return True
    else:
        print(Fore.RED + f"Gagal terhubung ke: {selected_network.ssid}. Pastikan password benar (jika diperlukan)." + Style.RESET_ALL)
        return False

def check_internet():
    """Memeriksa koneksi internet."""
    url = "https://www.google.com"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()  # Akan menimbulkan HTTPError untuk respons buruk (4xx atau 5xx)
        print(Fore.GREEN + "Koneksi internet terdeteksi." + Style.RESET_ALL)
        return True
    except requests.exceptions.RequestException as e:
        print(Fore.RED + f"Tidak ada koneksi internet: {e}" + Style.RESET_ALL)
        return False

def connect_vpn():
    """Menghubungkan ke VPN menggunakan OpenVPN."""
    if not VPN_PROVIDER or not VPN_CONFIG:
        print(Fore.YELLOW + "Informasi VPN belum lengkap di file .env. Melewati koneksi VPN." + Style.RESET_ALL)
        return

    print(Fore.YELLOW + f"Mencoba menghubungkan ke VPN ({VPN_PROVIDER})..." + Style.RESET_ALL)
    command = ["sudo", "openvpn", "--config", VPN_CONFIG]
    if VPN_USERNAME and VPN_PASSWORD:
        command.extend(["--auth-user-pass", "auth.txt"])
        with open("auth.txt", "w") as f:
            f.write(f"{VPN_USERNAME}\n{VPN_PASSWORD}")

    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Tampilkan output VPN secara real-time (opsional)
        for line in iter(process.stdout.readline, b''):
            print(Fore.BLUE + "[VPN Output] " + line.decode('utf-8').strip() + Style.RESET_ALL)
        process.wait()
        if process.returncode == 0:
            print(Fore.GREEN + f"Berhasil terhubung ke VPN ({VPN_PROVIDER})." + Style.RESET_ALL)
        else:
            stderr_output = process.stderr.read().decode('utf-8').strip()
            print(Fore.RED + f"Gagal menghubungkan ke VPN ({VPN_PROVIDER}):\n{stderr_output}" + Style.RESET_ALL)
    except FileNotFoundError:
        print(Fore.RED + "Perintah 'openvpn' tidak ditemukan. Pastikan OpenVPN sudah terinstal." + Style.RESET_ALL)
    except Exception as e:
        print(Fore.RED + f"Terjadi kesalahan saat menghubungkan VPN: {e}" + Style.RESET_ALL)
    finally:
        if os.path.exists("auth.txt"):
            os.remove("auth.txt")

# --- Alur Utama Script ---

if __name__ == "__main__":
    print(Fore.MAGENTA + "--- Auto WiFi Connect + VPN ---" + Style.RESET_ALL)

    wifi_data = scan_wifi()
    if wifi_data:
        scan_results, iface = wifi_data
        selected = pilih_wifi(scan_results)
        if selected:
            if connect_wifi(iface, selected):
                if check_internet():
                    connect_vpn()

    print(Fore.CYAN + "\nSelesai." + Style.RESET_ALL)
