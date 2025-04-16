# HANYA CONTOH KONSEP - Perlu Instalasi: pip install prompt_toolkit
from prompt_toolkit.shortcuts import radiolist_dialog

def main_menu_tui():
    result = radiolist_dialog(
        title="Menu Utama",
        text="Silakan pilih opsi:",
        values=[
            ("start", "1. Mulai Mendengarkan"),
            ("settings", "2. Pengaturan"),
            ("exit", "3. Keluar")
        ]
    ).run()

    if result == "start":
        print("Memulai...")
        # Panggil fungsi start_listening() Anda
    elif result == "settings":
        print("Membuka Pengaturan...")
        # Panggil fungsi show_settings() Anda (perlu diubah juga)
    elif result == "exit":
        print("Keluar...")
        # Keluar
    else: # Jika user menekan Esc/Cancel
        print("Dibatalkan.")

# Panggil menu TUI baru
# main_menu_tui()
```        Ini akan menampilkan dialog di terminal tempat Anda bisa menggunakan panah dan Enter (dan mungkin mouse klik pada beberapa terminal) untuk memilih.
