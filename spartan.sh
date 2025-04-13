#!/bin/bash

# --- Konfigurasi Awal & Variabel Global ---
CONFIG_FILE="email_monitor.conf"
EMAIL=""
PASSWORD="" # HARUS GUNAKAN APP PASSWORD GMAIL!
INTERVAL=5
SEARCH_TERM="Exora AI"
initial_uid_next="" # Menyimpan UIDNEXT saat monitoring dimulai

# --- Fungsi Utilitas Tampilan (tput) ---
# (Sama seperti sebelumnya - tidak perlu diubah)
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
# (Sama seperti sebelumnya - tidak perlu diubah)
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
# (Sama seperti sebelumnya - tidak perlu diubah)
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
    done
    print_warning "Alert selesai."
    sleep 1 # Jeda setelah alert
}

# Fungsi untuk mem-parsing body email
parse_email_body() {
    local body=$1
    local uid=$2 # Terima UID untuk logging
    print_status "Memeriksa body email (UID: $uid)..."

    # 1. Cek apakah mengandung SEARCH_TERM (Exora AI)
    #    Meskipun Subject sudah difilter, cek lagi di body untuk keamanan
    if echo "$body" | grep -qi "$SEARCH_TERM"; then
        # print_status "Ditemukan '${SEARCH_TERM}'. Mencari kata 'order'..." # Kurangi verbosity

        # 2. Cari kata 'order' dan kata setelahnya (buy/sell) - case insensitive
        local action
        action=$(echo "$body" | grep -oPi "order\s+\K(buy|sell)")

        if [[ -n "$action" ]]; then
            action_lower=$(echo "$action" | tr '[:upper:]' '[:lower:]') # Konversi ke huruf kecil
            print_success "UID: ${uid} - Ditemukan trigger: ${BOLD}${action_lower}${RESET}"
            if [[ "$action_lower" == "buy" ]]; then
                trigger_alert "buy"
            elif [[ "$action_lower" == "sell" ]]; then
                trigger_alert "sell"
            fi
        else
             # Tidak perlu print jika tidak ada action, karena email mungkin hanya notifikasi biasa
             # print_status "UID: ${uid} - Kata 'order' diikuti 'buy' atau 'sell' tidak ditemukan."
             : # No-op, lewati saja
        fi
    else
        # Seharusnya tidak terjadi jika filter subject curl bekerja
        # print_status "UID: ${uid} - '${SEARCH_TERM}' tidak ditemukan di body."
        : # No-op
    fi
}

# Fungsi untuk memeriksa email baru (DIMODIFIKASI)
check_new_email() {
    if [[ -z "$initial_uid_next" ]]; then
        print_error "Initial UID Next belum ditentukan. Tidak dapat memeriksa email."
        # Mungkin perlu menghentikan loop atau mencoba lagi mengambil UIDNEXT
        sleep 5 # Tunggu sebelum mencoba lagi (jika dalam loop)
        return 1
    fi

    print_status "Mengecek email baru (UID >= $initial_uid_next) di imap.gmail.com..."

    local imap_url="imaps://imap.gmail.com:993/INBOX"
    # --- KRITERIA PENCARIAN BARU ---
    # Cari email dengan UID >= initial_uid_next, belum dibaca (UNSEEN),
    # dan cocok dengan SEARCH_TERM di SUBJECT
    local search_criteria="UID ${initial_uid_next}:* UNSEEN SUBJECT \"${SEARCH_TERM}\""

    # Ambil daftar UID email yang cocok
    local uid_list_raw
    uid_list_raw=$(curl -s --connect-timeout 10 --max-time 15 --url "$imap_url" \
        --user "$EMAIL:$PASSWORD" \
        -X "UID SEARCH ${search_criteria}")

    # Cek error curl
     if [[ $? -ne 0 ]]; then
        print_error "Gagal menghubungi server IMAP atau query SEARCH."
        return 1
     fi

    # Ekstrak hanya UID dari output (* SEARCH UIDs)
    local uid_list
    uid_list=$(echo "$uid_list_raw" | grep -oP '\* SEARCH \K[0-9 ]+' | sed 's/ /\n/g') # Pisahkan UID jika ada spasi

    if [[ -z "$uid_list" ]]; then
        print_status "Tidak ada email baru (UNSEEN, UID >= ${initial_uid_next}) yang cocok ditemukan."
        return 0 # Keluar jika tidak ada email baru
    fi

    print_success "Ditemukan potensi email baru! UID(s): $(echo $uid_list | tr '\n' ' ')" # Tampilkan UID dalam satu baris

    # Proses setiap UID yang ditemukan
    local processed_count=0
    for uid in $uid_list; do
        # Validasi UID (pastikan itu angka dan >= initial_uid_next, meskipun SEARCH seharusnya sudah handle)
        if [[ ! "$uid" =~ ^[0-9]+$ || "$uid" -lt "$initial_uid_next" ]]; then
            print_warning "Melewati UID tidak valid atau lebih kecil dari initial: $uid"
            continue
        fi

        print_status "Memproses email dengan UID: $uid"

        # Ambil BODY email berdasarkan UID
        local email_body_raw
        email_body_raw=$(curl -s --connect-timeout 10 --max-time 15 --url "$imap_url" \
                     --user "$EMAIL:$PASSWORD" \
                     -X "UID FETCH $uid BODY[TEXT]") # Ambil bagian teks saja

        if [[ $? -ne 0 ]]; then
            print_error "Gagal mengambil body email untuk UID: $uid (Curl Error)"
            continue # Lanjut ke UID berikutnya jika gagal
        fi

        if [[ -z "$email_body_raw" ]]; then
            print_warning "Body email kosong atau gagal diambil untuk UID: $uid (Empty Body)"
             # Tandai sebagai SEEN agar tidak dicek lagi? Mungkin tidak perlu jika UNSEEN bekerja.
            continue
        fi


        # --- Membersihkan Body Email (Penting!) ---
        # Output FETCH BODY[TEXT] seringkali mengandung info IMAP di awal
        # dan mungkin encoding aneh atau multipart boundaries.
        # Ini contoh pembersihan dasar, mungkin perlu disesuaikan:
        # 1. Hapus baris awal sampai baris kosong pertama (header IMAP/MIME)
        # 2. Decode Quoted-Printable jika ada (lebih kompleks, di luar bash murni)
        # 3. Handle character sets (lebih kompleks)

        # Pembersihan dasar: Hapus header fetch sampai baris kosong
        local email_body
        email_body=$(echo "$email_body_raw" | sed -e '1,/^$/d' -e 's/\r//g') # Hapus CR

        if [[ -z "$email_body" ]]; then
             print_warning "Body email menjadi kosong setelah pembersihan dasar (UID: $uid)"
             continue
        fi

        # --- Parsing ---
        parse_email_body "$email_body" "$uid"
        processed_count=$((processed_count + 1))

        # --- Tandai sebagai SEEN (Opsional tapi Direkomendasikan) ---
        # Agar tidak diproses lagi jika script restart atau UNSEEN tidak langsung update
        # print_status "Menandai UID $uid sebagai SEEN..."
        # curl -s --connect-timeout 5 --max-time 10 --url "$imap_url" \
        #     --user "$EMAIL:$PASSWORD" \
        #     -X "UID STORE $uid +FLAGS (\Seen)" > /dev/null
        # if [[ $? -ne 0 ]]; then
        #     print_warning "Gagal menandai UID $uid sebagai SEEN."
        # fi
        # Catatan: Menandai SEEN akan membuatnya terbaca di Klien Email lain.
        # Jika tidak ingin ditandai SEEN, cukup andalkan filter UNSEEN di pencarian berikutnya.

    done

    if [[ $processed_count -gt 0 ]]; then
        print_success "Selesai memproses $processed_count email baru."
    fi
    return 0
}


# --- Fungsi Menu ---
# (show_settings_menu sama seperti sebelumnya)
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

# (show_main_menu sama seperti sebelumnya)
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
            1) start_monitoring ;; # Panggil fungsi start_monitoring
            2) show_settings_menu ;;
            3) print_header; print_status "Keluar..."; exit 0 ;;
            *) print_error "Pilihan tidak valid!"; sleep 1 ;;
        esac
    done
}

# Fungsi untuk memulai monitoring (DIMODIFIKASI)
start_monitoring() {
    print_header

    # --- Dapatkan UIDNEXT Awal ---
    print_status "Menghubungkan ke IMAP untuk mendapatkan status awal mailbox..."
    local imap_url="imaps://imap.gmail.com:993/INBOX"
    local status_output
    status_output=$(curl -s --connect-timeout 10 --max-time 15 --url "$imap_url" \
        --user "$EMAIL:$PASSWORD" \
        -X "STATUS INBOX (UIDNEXT)")

    if [[ $? -ne 0 ]]; then
        print_error "Gagal mendapatkan status awal INBOX (UIDNEXT) dari server."
        print_error "Pastikan detail login benar, IMAP aktif, dan koneksi internet stabil."
        print_warning "Monitoring tidak dapat dimulai tanpa UID awal."
        sleep 3
        return # Kembali ke menu utama
    fi

    # Ekstrak UIDNEXT dari output
    initial_uid_next=$(echo "$status_output" | grep -oP '\(UIDNEXT \K[0-9]+')

    if [[ -z "$initial_uid_next" ]]; then
        print_error "Gagal mem-parsing UIDNEXT dari respons server: $status_output"
        print_warning "Monitoring tidak dapat dimulai."
        sleep 3
        return # Kembali ke menu utama
    else
        print_success "Status awal mailbox didapatkan. Hanya akan memproses email baru dengan UID >= ${initial_uid_next}"
    fi
    # --- Selesai Mendapatkan UIDNEXT ---

    print_warning "Memulai monitoring email setiap ${INTERVAL} detik..."
    print_warning "Hanya akan memproses email baru (UID >= ${initial_uid_next}) yang cocok."
    print_warning "Tekan ${BOLD}Ctrl+C${RESET} untuk berhenti."
    echo

    # Loop utama monitoring
    while true; do
        check_new_email # Panggil fungsi check_new_email
        # Tangani jika check_new_email gagal (misal, return 1)
        if [[ $? -ne 0 ]]; then
             print_warning "Terjadi error pada siklus pengecekan terakhir. Mencoba lagi dalam ${INTERVAL} detik..."
        fi
        sleep "$INTERVAL"
    done
}

# --- Main Execution ---
trap 'echo; print_error "Monitoring dihentikan oleh user."; exit 1' SIGINT SIGTERM # Handle Ctrl+C

load_config # Muat konfigurasi saat script dimulai
show_main_menu # Tampilkan menu utama
