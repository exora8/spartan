#!/bin/bash

# --- Konfigurasi Awal & Variabel Global ---
CONFIG_FILE="email_monitor.conf"
EMAIL=""
PASSWORD="" # HARUS GUNAKAN APP PASSWORD GMAIL!
INTERVAL=5
SEARCH_TERM="Exora AI"
LAST_UID="" # Menyimpan UID email terakhir yang diproses

# --- Fungsi Utilitas Tampilan (tput) ---
# Cek apakah tput tersedia
if command -v tput >/dev/null 2>&1; then
    BOLD=$(tput bold)
    UNDERLINE=$(tput smul)
    RESET=$(tput sgr0)
    RED=$(tput setaf 1)
    GREEN=$(tput setaf 2)
    YELLOW=$(tput setaf 3)
    BLUE=$(tput setaf 4)
    MAGENTA=$(tput setaf 5)
    CYAN=$(tput setaf 6)
else
    # Fallback jika tput tidak ada
    BOLD=""
    UNDERLINE=""
    RESET=""
    RED=""
    GREEN=""
    YELLOW=""
    BLUE=""
    MAGENTA=""
    CYAN=""
fi

# --- Fungsi Bantuan Tampilan ---
clear_screen() {
    clear
}

print_header() {
    clear_screen
    echo "${BLUE}${BOLD}=============================================${RESET}"
    echo "${BLUE}${BOLD}      ${CYAN}Gmail Monitor for '${SEARCH_TERM}'${RESET}"
    echo "${BLUE}${BOLD}=============================================${RESET}"
    echo
}

print_status() {
    echo "${CYAN}[*]${RESET} $1"
}

print_success() {
    echo "${GREEN}[+]${RESET} $1"
}

print_warning() {
    echo "${YELLOW}[!]${RESET} ${BOLD}$1${RESET}"
}

print_error() {
    echo "${RED}[-]${RESET} ${BOLD}$1${RESET}"
}

# --- Fungsi Konfigurasi ---
load_config() {
    if [[ -f "$CONFIG_FILE" ]]; then
        # Sumber file konfigurasi dengan aman (mencegah eksekusi perintah)
        while IFS='=' read -r key value; do
            # Hapus quote jika ada
            value="${value%\"}"
            value="${value#\"}"
            case "$key" in
                EMAIL) EMAIL="$value" ;;
                PASSWORD) PASSWORD="$value" ;;
                INTERVAL) INTERVAL="$value" ;;
                SEARCH_TERM) SEARCH_TERM="$value" ;;
            esac
        done < "$CONFIG_FILE"
        print_success "Konfigurasi dimuat dari $CONFIG_FILE"
    else
        print_warning "File konfigurasi $CONFIG_FILE tidak ditemukan. Gunakan nilai default atau atur melalui menu."
    fi
    # Set default jika kosong setelah load
    EMAIL="${EMAIL:-"your_email@gmail.com"}"
    PASSWORD="${PASSWORD:-"YOUR_APP_PASSWORD"}"
    INTERVAL="${INTERVAL:-5}"
    SEARCH_TERM="${SEARCH_TERM:-"Exora AI"}"
}

save_config() {
    print_status "Menyimpan konfigurasi ke $CONFIG_FILE..."
    # Pastikan hanya user yang bisa baca/tulis
    (
        umask 077 # Hanya izinkan user rwx
        echo "EMAIL=\"$EMAIL\"" > "$CONFIG_FILE"
        echo "PASSWORD=\"$PASSWORD\"" >> "$CONFIG_FILE"
        echo "INTERVAL=\"$INTERVAL\"" >> "$CONFIG_FILE"
        echo "SEARCH_TERM=\"$SEARCH_TERM\"" >> "$CONFIG_FILE"
    )
    if [[ $? -eq 0 ]]; then
        print_success "Konfigurasi berhasil disimpan."
    else
        print_error "Gagal menyimpan konfigurasi. Periksa izin file."
    fi
    sleep 1
}

# --- Fungsi Inti ---

# Fungsi untuk membunyikan alert
trigger_alert() {
    local type=$1 # "buy" atau "sell"
    print_warning "ALERT! Terdeteksi order '${type}' untuk '${SEARCH_TERM}'!"
    print_warning "Memulai alert beep selama 5 detik..."
    local end_time=$((SECONDS + 5))
    while [[ $SECONDS -lt $end_time ]]; do
        printf '\a' # Bunyikan bell
        sleep 0.5  # Jeda singkat
        # Mungkin perlu jeda tambahan agar terdengar hidup-mati
        # sleep 0.3
    done
    print_warning "Alert selesai."
    sleep 1 # Jeda setelah alert
}

# Fungsi untuk mem-parsing body email
parse_email_body() {
    local body=$1
    print_status "Memeriksa body email..."

    # 1. Cek apakah mengandung SEARCH_TERM (Exora AI)
    if echo "$body" | grep -qi "$SEARCH_TERM"; then
        print_status "Ditemukan '${SEARCH_TERM}'. Mencari kata 'order'..."

        # 2. Cari kata 'order' dan kata setelahnya (buy/sell) - case insensitive
        # Menggunakan grep -oP (Perl Regex) untuk ekstraksi yang lebih tepat
        # \K -> Memulai match setelah 'order '
        # (buy|sell) -> Mencocokkan 'buy' atau 'sell'
        local action
        action=$(echo "$body" | grep -oPi "order\s+\K(buy|sell)")

        if [[ -n "$action" ]]; then
            action_lower=$(echo "$action" | tr '[:upper:]' '[:lower:]') # Konversi ke huruf kecil
            print_success "Ditemukan trigger: ${BOLD}${action_lower}${RESET}"
            if [[ "$action_lower" == "buy" ]]; then
                trigger_alert "buy"
            elif [[ "$action_lower" == "sell" ]]; then
                trigger_alert "sell"
            fi
        else
             print_status "Kata 'order' diikuti 'buy' atau 'sell' tidak ditemukan setelah '${SEARCH_TERM}'."
        fi
    else
        # Seharusnya tidak terjadi jika filter curl bekerja, tapi sebagai pengaman
        print_status "'${SEARCH_TERM}' tidak ditemukan di body email ini."
    fi
}

# Fungsi untuk memeriksa email baru
check_new_email() {
    print_status "Menghubungkan ke imap.gmail.com (Interval: ${INTERVAL}s)..."

    # Gunakan curl untuk mencari email BARU (UNSEEN) yang mengandung SEARCH_TERM di SUBJECT
    # Ini lebih efisien daripada mengambil semua email
    # Kita ambil UID dan BODY-nya
    local imap_url="imaps://imap.gmail.com:993/INBOX"
    local search_criteria="SUBJECT \"${SEARCH_TERM}\" UNSEEN" # Cari di Subject dan yang belum dibaca

    # Ambil daftar UID email yang cocok
    # TODO: Perlu penanganan error koneksi yang lebih baik
    local uid_list
    uid_list=$(curl -s --connect-timeout 10 --max-time 15 --url "$imap_url" \
        --user "$EMAIL:$PASSWORD" \
        -X "UID SEARCH ${search_criteria}" | grep -oP '\* SEARCH \K.*')

    if [[ -z "$uid_list" ]]; then
        print_status "Tidak ada email baru yang cocok ditemukan."
        return # Keluar jika tidak ada email baru
    fi

    print_success "Ditemukan email baru yang cocok! UID: $uid_list"

    # Proses setiap UID yang ditemukan
    local latest_processed_uid=$LAST_UID
    for uid in $uid_list; do
        # Hanya proses UID yang lebih besar dari yang terakhir diproses
        if [[ -z "$LAST_UID" || "$uid" -gt "$LAST_UID" ]]; then
            print_status "Memproses email dengan UID: $uid"

            # Ambil BODY email berdasarkan UID
            local email_body
            email_body=$(curl -s --connect-timeout 10 --max-time 15 --url "$imap_url" \
                         --user "$EMAIL:$PASSWORD" \
                         -X "UID FETCH $uid BODY[TEXT]") # Ambil bagian teks saja

            if [[ $? -ne 0 || -z "$email_body" ]]; then
                print_error "Gagal mengambil body email untuk UID: $uid"
                continue # Lanjut ke UID berikutnya jika gagal
            fi

            # Bersihkan sedikit body email (opsional, tergantung format asli)
            # Mungkin perlu penghapusan header atau encoding tertentu
            # Contoh sederhana: hapus baris awal sampai baris kosong pertama
             email_body=$(echo "$email_body" | sed '1,/^$/d')

            parse_email_body "$email_body"
            latest_processed_uid=$uid # Update UID terakhir yang berhasil diproses
        else
             print_status "Melewati UID: $uid (sudah diproses atau lebih lama)"
        fi
    done
    LAST_UID=$latest_processed_uid # Simpan UID terakhir yang diproses untuk sesi berikutnya
}


# --- Fungsi Menu ---
show_settings_menu() {
    while true; do
        print_header
        echo "${YELLOW}${BOLD}--- Pengaturan ---${RESET}"
        echo "1. Set Email          : ${GREEN}${EMAIL}${RESET}"
        echo "2. Set App Password   : ${GREEN}${PASSWORD:0:1}***${PASSWORD: -1:1}${RESET} ${RED}(Sangat Tidak Aman!)${RESET}"
        echo "3. Set Interval (detik): ${GREEN}${INTERVAL}${RESET}"
        echo "4. Set Teks Pencarian : ${GREEN}${SEARCH_TERM}${RESET}"
        echo "5. ${YELLOW}Simpan & Kembali${RESET}"
        echo
        read -rp "${BOLD}Pilih opsi (1-5): ${RESET}" choice

        case $choice in
            1) read -rp "Masukkan Email Gmail baru: " EMAIL ;;
            2) read -rsp "Masukkan ${BOLD}App Password${RESET} Gmail baru: " PASSWORD; echo ;;
            3) read -rp "Masukkan Interval cek baru (detik): " INTERVAL ;;
            4) read -rp "Masukkan Teks Pencarian baru (di Subject/Body): " SEARCH_TERM ;;
            5) save_config; return ;;
            *) print_error "Pilihan tidak valid!" ; sleep 1 ;;
        esac
         # Validasi input (opsional)
        if [[ "$choice" == "3" && ! "$INTERVAL" =~ ^[0-9]+$ ]]; then
            print_error "Interval harus berupa angka!"
            INTERVAL=5 # Reset ke default jika salah
            sleep 1
        fi
    done
}

show_main_menu() {
    while true; do
        print_header
        echo "${MAGENTA}${BOLD}--- Menu Utama ---${RESET}"
        echo "1. ${GREEN}Mulai Monitoring${RESET}"
        echo "2. ${YELLOW}Pengaturan${RESET}"
        echo "3. ${RED}Keluar${RESET}"
        echo
        echo "${CYAN}Status:${RESET}"
        echo "  Email    : ${GREEN}${EMAIL}${RESET}"
        echo "  Interval : ${GREEN}${INTERVAL} detik${RESET}"
        echo "  Cari Teks: ${GREEN}${SEARCH_TERM}${RESET}"
        echo "  ${YELLOW}Password : ${RED}Disembunyikan (Gunakan App Password!)${RESET}"
        echo
        read -rp "${BOLD}Pilih opsi (1-3): ${RESET}" choice

        case $choice in
            1) start_monitoring ;;
            2) show_settings_menu ;;
            3) print_header; print_status "Keluar..."; exit 0 ;;
            *) print_error "Pilihan tidak valid!"; sleep 1 ;;
        esac
    done
}

start_monitoring() {
    print_header
    print_warning "Memulai monitoring email setiap ${INTERVAL} detik..."
    print_warning "Tekan ${BOLD}Ctrl+C${RESET} untuk berhenti."
    echo

    # Reset LAST_UID saat monitoring dimulai ulang
    LAST_UID=""
    # Lakukan cek awal sekali
    check_new_email

    # Loop utama monitoring
    while true; do
        sleep "$INTERVAL"
        check_new_email
    done
}

# --- Main Execution ---
trap 'echo; print_error "Monitoring dihentikan oleh user."; exit 1' SIGINT SIGTERM # Handle Ctrl+C

load_config # Muat konfigurasi saat script dimulai
show_main_menu # Tampilkan menu utama
