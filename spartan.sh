#!/bin/bash

# --- Konfigurasi Awal ---
CONFIG_FILE="listener_settings.conf"
DEFAULT_MAILBOX="$HOME/gmail_inbox" # Contoh: File tempat fetchmail menyimpan email baru
DEFAULT_CHECK_INTERVAL=60 # Detik

# --- Variabel Global ---
MAILBOX_FILE=""
CHECK_INTERVAL=""
LAST_MAILBOX_SIZE=-1 # Ukuran terakhir file mailbox untuk deteksi email baru

# --- Fungsi Tampilan & UI ---

# Fungsi clear screen dan tampilkan header
function show_header() {
    clear
    tput setaf 3 # Warna Kuning
    echo "========================================"
    echo "   Gmail Order Listener v1.0 (Bash)   "
    echo "========================================"
    tput sgr0 # Reset warna
    echo
}

# Animasi loading sederhana
function simple_spinner() {
    local pid=$1
    local delay=0.1
    local spinstr='|/-\'
    while [ "$(ps a | awk '{print $1}' | grep $pid)" ]; do
        local temp=${spinstr#?}
        printf " [%c]  " "$spinstr"
        local spinstr=$temp${spinstr%"$temp"}
        sleep $delay
        printf "\b\b\b\b\b\b"
    done
    printf "    \b\b\b\b"
}

# Fungsi Beep
function trigger_beep() {
    local type=$1 # "buy" or "sell"
    local duration=5
    local interval=0.5

    if [[ "$type" == "buy" ]]; then
        echo -e "\n$(tput setaf 2)>>> BUY Signal Detected! Beeping... <<<$(tput sgr0)"
        local cycles=$(echo "$duration / ($interval * 2)" | bc)
        for (( i=0; i<cycles; i++ )); do
            echo -ne '\a' # Beep ON
            sleep $interval
            # Tidak ada cara standar "beep OFF", jadi kita jeda saja
            sleep $interval
        done
        # Pastikan total waktu mendekati 5 detik
        sleep 0 # Tambahan jika perlu

    elif [[ "$type" == "sell" ]]; then
        echo -e "\n$(tput setaf 1)>>> SELL Signal Detected! Beeping (2x)... <<<$(tput sgr0)"
        echo -ne '\a' # Beep 1
        sleep $interval
        echo -ne '\a' # Beep 2
        sleep $(echo "$duration - $interval * 2" | bc) # Tunggu sisa waktu
    fi
    echo -e "\nBeep sequence finished."
}

# --- Fungsi Inti ---

# Memuat konfigurasi
function load_config() {
    if [[ -f "$CONFIG_FILE" ]]; then
        source "$CONFIG_FILE"
        echo "Konfigurasi dimuat dari $CONFIG_FILE"
    else
        echo "File konfigurasi $CONFIG_FILE tidak ditemukan, menggunakan default."
    fi
    # Gunakan default jika variabel kosong
    MAILBOX_FILE="${MAILBOX_FILE:-$DEFAULT_MAILBOX}"
    CHECK_INTERVAL="${CHECK_INTERVAL:-$DEFAULT_CHECK_INTERVAL}"

    # Validasi awal
    if [[ -z "$MAILBOX_FILE" ]]; then
        echo "$(tput setaf 1)Error: Lokasi mailbox belum diatur! Jalankan Settings.$(tput sgr0)"
        exit 1
    fi
     # Inisialisasi ukuran awal jika file ada
    if [[ -f "$MAILBOX_FILE" ]]; then
         LAST_MAILBOX_SIZE=$(stat -c%s "$MAILBOX_FILE")
    else
         LAST_MAILBOX_SIZE=0 # Anggap ukuran 0 jika file belum ada
         echo "$(tput setaf 3)Warning: Mailbox file '$MAILBOX_FILE' tidak ditemukan. Menunggu file dibuat...$(tput sgr0)"
    fi
}

# Menyimpan konfigurasi
function save_config() {
    show_header
    echo "--- Pengaturan Konfigurasi ---"
    echo "Lokasi Mailbox saat ini: $MAILBOX_FILE"
    read -p "Masukkan lokasi file mailbox baru (biarkan kosong untuk batal): " new_mailbox
    if [[ -n "$new_mailbox" ]]; then
        MAILBOX_FILE="$new_mailbox"
        echo "Lokasi mailbox diubah ke: $MAILBOX_FILE"
    fi

    echo "Interval pengecekan saat ini: $CHECK_INTERVAL detik"
    read -p "Masukkan interval pengecekan baru (detik, biarkan kosong untuk batal): " new_interval
    if [[ -n "$new_interval" ]] && [[ "$new_interval" =~ ^[0-9]+$ ]]; then
        CHECK_INTERVAL="$new_interval"
        echo "Interval pengecekan diubah ke: $CHECK_INTERVAL detik"
    elif [[ -n "$new_interval" ]]; then
        echo "$(tput setaf 1)Input interval tidak valid (harus angka).$(tput sgr0)"
    fi

    # Simpan ke file
    echo "# Konfigurasi untuk Gmail Listener" > "$CONFIG_FILE"
    echo "MAILBOX_FILE=\"$MAILBOX_FILE\"" >> "$CONFIG_FILE"
    echo "CHECK_INTERVAL=\"$CHECK_INTERVAL\"" >> "$CONFIG_FILE"
    echo "Konfigurasi disimpan ke $CONFIG_FILE."
    LAST_MAILBOX_SIZE=-1 # Reset ukuran agar dicek ulang saat mulai listen
    sleep 2
}

# Memproses email baru
function process_new_mail() {
    if [[ ! -f "$MAILBOX_FILE" ]]; then
        # File tidak ada, tidak ada yang diproses
        return
    fi

    local current_size=$(stat -c%s "$MAILBOX_FILE")

    # Hanya proses jika ukuran file bertambah
    if [[ "$current_size" -gt "$LAST_MAILBOX_SIZE" ]] && [[ "$LAST_MAILBOX_SIZE" -ne -1 ]]; then
        echo "$(tput setaf 6)Perubahan terdeteksi! Ukuran: $LAST_MAILBOX_SIZE -> $current_size. Memproses...$(tput sgr0)"

        # Ambil konten baru (pendekatan sederhana: baca semua dari offset lama)
        # Catatan: Ini sangat kasar dan bisa membaca ulang bagian email lama jika
        #         file mailbox tidak hanya ditambahkan di akhir (append-only).
        #         Untuk keandalan, memproses email individual (misal pakai formail) lebih baik.
        local new_content
        new_content=$(tail -c +"$((LAST_MAILBOX_SIZE + 1))" "$MAILBOX_FILE")

        # Cek kata kunci 'Exora AI'
        if echo "$new_content" | grep -q -i 'Exora AI'; then
            echo "Kata kunci 'Exora AI' ditemukan."

            # Cari kata 'order' dan ambil kata setelahnya (buy/sell)
            # Menggunakan grep -oP untuk lookbehind dan mencocokkan kata setelah 'order '
            # Mungkin perlu disesuaikan tergantung format email persisnya
            local order_signal
            order_signal=$(echo "$new_content" | grep -i -o -P 'order\s+\K(buy|sell)' | head -n 1)

            if [[ "$order_signal" == "buy" || "$order_signal" == "BUY" ]]; then
                trigger_beep "buy"
            elif [[ "$order_signal" == "sell" || "$order_signal" == "SELL" ]]; then
                trigger_beep "sell"
            else
                echo "Kata kunci 'order' ditemukan setelah 'Exora AI', tapi sinyal (buy/sell) tidak terdeteksi setelahnya."
            fi
        else
             echo "Tidak ada kata kunci 'Exora AI' di email baru."
        fi
    fi

    # Update ukuran terakhir
    LAST_MAILBOX_SIZE=$current_size
}

# Fungsi utama untuk mulai mendengarkan
function start_listening() {
    show_header
    echo "Memulai listener untuk file: $MAILBOX_FILE"
    echo "Interval pengecekan: $CHECK_INTERVAL detik"
    echo "Tekan CTRL+C untuk berhenti."
    echo

    if [[ ! -f "$MAILBOX_FILE" ]]; then
         echo "$(tput setaf 3)Warning: Mailbox file '$MAILBOX_FILE' tidak ditemukan. Menunggu file dibuat...$(tput sgr0)"
         # Inisialisasi ukuran ke 0 jika file belum ada saat mulai listen
         LAST_MAILBOX_SIZE=0
    elif [[ $LAST_MAILBOX_SIZE -eq -1 ]]; then
        # Jika baru mulai atau setelah setting, set ukuran awal
        LAST_MAILBOX_SIZE=$(stat -c%s "$MAILBOX_FILE")
        echo "Ukuran awal mailbox file: $LAST_MAILBOX_SIZE bytes."
    fi


    local spin='-\|/'
    local i=0
    while true; do
        # Animasi sederhana
        i=$(( (i+1) %4 ))
        printf "\r[${spin:$i:1}] Mendengarkan perubahan... (Ukuran terakhir: $LAST_MAILBOX_SIZE bytes)    "

        process_new_mail

        # Tunggu sebelum cek lagi
        # Pecah sleep agar CTRL+C lebih responsif
        for (( j=0; j<CHECK_INTERVAL; j++ )); do
             sleep 1
             # Cek lagi jika file tiba-tiba muncul
             if [[ $LAST_MAILBOX_SIZE -eq 0 ]] && [[ -f "$MAILBOX_FILE" ]]; then
                 echo -e "\n$(tput setaf 2)Mailbox file '$MAILBOX_FILE' sekarang ada! Melanjutkan pengecekan...$(tput sgr0)"
                 LAST_MAILBOX_SIZE=$(stat -c%s "$MAILBOX_FILE")
                 break # Langsung proses di iterasi berikutnya
             fi
        done

    done
}

# --- Menu Utama ---
function main_menu() {
    load_config # Muat konfigurasi saat menu utama ditampilkan

    while true; do
        show_header
        echo "Lokasi Mailbox: $MAILBOX_FILE"
        echo "Interval Cek  : $CHECK_INTERVAL detik"
        echo "----------------------------------------"
        echo "Pilih Opsi:"
        echo "  1. Mulai Mendengarkan (Listen)"
        echo "  2. Pengaturan (Settings)"
        echo "  3. Keluar (Exit)"
        echo "----------------------------------------"
        read -p "Masukkan pilihan (1-3): " choice

        case $choice in
            1)
                start_listening
                # Jika user kembali dari listening (misal dengan CTRL+C), tampilkan menu lagi
                ;;
            2)
                save_config
                load_config # Muat ulang konfigurasi setelah disimpan
                ;;
            3)
                echo "Terima kasih telah menggunakan script ini. Sampai jumpa!"
                exit 0
                ;;
            *)
                echo "$(tput setaf 1)Pilihan tidak valid. Coba lagi.$(tput sgr0)"
                sleep 1
                ;;
        esac
    done
}

# --- Eksekusi Script ---
trap 'echo -e "\n$(tput setaf 1)Listener dihentikan oleh pengguna.$(tput sgr0)"; exit 1' SIGINT # Tangani CTRL+C
main_menu
