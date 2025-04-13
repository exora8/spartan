#!/bin/bash

# --- Konfigurasi ---
CONFIG_FILE="$HOME/.config/exora_listener/config"
PYTHON_SCRIPT_PATH="$(dirname "$0")/gmail_checker.py" # Asumsi python script di direktori yg sama
LOG_FILE="$HOME/.local/share/exora_listener/activity.log"

# Default values (akan ditimpa oleh file config jika ada)
GMAIL_EMAIL=""
GMAIL_APP_PASSWORD=""
CHECK_INTERVAL=30 # Detik
BEEP_BUY_DURATION=5000 # Milidetik untuk beep panjang (5 detik)
BEEP_BUY_FREQ=1000 # Hz
BEEP_SELL_DURATION=500 # Milidetik untuk beep pendek
BEEP_SELL_FREQ=800  # Hz
BEEP_SELL_REPEATS=2
BEEP_SELL_DELAY=1 # Detik antar beep jual

# --- Variabel Global ---
listener_active=false
last_processed_uid="" # Untuk menghindari pemrosesan ulang email yang sama (opsional)

# --- Warna & Format (menggunakan tput) ---
BOLD=$(tput bold)
RESET=$(tput sgr0)
RED=$(tput setaf 1)
GREEN=$(tput setaf 2)
YELLOW=$(tput setaf 3)
BLUE=$(tput setaf 4)
CYAN=$(tput setaf 6)

# --- Fungsi Utility ---

# Membuat direktori jika belum ada
ensure_dirs() {
    mkdir -p "$(dirname "$CONFIG_FILE")"
    mkdir -p "$(dirname "$LOG_FILE")"
}

# Logging
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

# Memeriksa dependensi
check_dependencies() {
    local missing=0
    command -v python3 >/dev/null 2>&1 || { echo >&2 "${RED}Error:${RESET} 'python3' tidak ditemukan. Silakan install."; missing=1; }
    command -v beep >/dev/null 2>&1 || { echo >&2 "${YELLOW}Warning:${RESET} 'beep' tidak ditemukan. Notifikasi suara tidak akan berfungsi. Install 'beep'."; } # Warning, not critical failure
    [ -f "$PYTHON_SCRIPT_PATH" ] || { echo >&2 "${RED}Error:${RESET} Script Python '$PYTHON_SCRIPT_PATH' tidak ditemukan."; missing=1; }

    if [ $missing -eq 1 ]; then
        exit 1
    fi
    # Cek apakah user punya permission untuk beep (mungkin perlu adduser ke group 'input' atau modprobe pcspkr)
    # Ini hanya bisa dideteksi saat mencoba beep pertama kali.
}

# Memuat konfigurasi
load_config() {
    if [ -f "$CONFIG_FILE" ]; then
        # Source the config file carefully
        # Prevent command execution from config file
        local line
        while IFS='=' read -r key value || [[ -n "$key" ]]; do
            # Remove surrounding quotes if any, trim whitespace
            value=$(echo "$value" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e "s/^'//" -e "s/'$//" -e 's/^"//' -e 's/"$//')
            key=$(echo "$key" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
            # Assign to known variables only
            case "$key" in
                GMAIL_EMAIL) GMAIL_EMAIL="$value" ;;
                GMAIL_APP_PASSWORD) GMAIL_APP_PASSWORD="$value" ;;
                CHECK_INTERVAL) CHECK_INTERVAL="$value" ;;
                # Add other config vars here if needed
            esac
        done < "$CONFIG_FILE"
        log_message "Konfigurasi dimuat dari $CONFIG_FILE"
        return 0 # Success
    else
        log_message "File konfigurasi $CONFIG_FILE tidak ditemukan."
        return 1 # Not found
    fi
}

# Menyimpan konfigurasi
save_config() {
    ensure_dirs
    echo "# Konfigurasi Exora AI Listener" > "$CONFIG_FILE"
    echo "GMAIL_EMAIL='$GMAIL_EMAIL'" >> "$CONFIG_FILE"
    echo "GMAIL_APP_PASSWORD='$GMAIL_APP_PASSWORD'" >> "$CONFIG_FILE"
    echo "CHECK_INTERVAL='$CHECK_INTERVAL'" >> "$CONFIG_FILE"
    chmod 600 "$CONFIG_FILE" # Set permissions (read/write only for owner)
    log_message "Konfigurasi disimpan ke $CONFIG_FILE"
    echo "${GREEN}Konfigurasi disimpan.${RESET}"
}

# Meminta input user untuk konfigurasi awal
prompt_initial_config() {
    echo "${YELLOW}Konfigurasi awal diperlukan.${RESET}"
    while [ -z "$GMAIL_EMAIL" ]; do
        read -p "Masukkan alamat email Gmail Anda: " GMAIL_EMAIL
    done
    while [ -z "$GMAIL_APP_PASSWORD" ]; do
        read -sp "Masukkan Gmail App Password Anda: " GMAIL_APP_PASSWORD
        echo
    done
    read -p "Masukkan interval pengecekan (detik) [Default: $CHECK_INTERVAL]: " input_interval
    CHECK_INTERVAL=${input_interval:-$CHECK_INTERVAL} # Gunakan input atau default
    save_config
}

# --- Fungsi Inti ---

# Menjalankan Python script untuk cek email
run_email_check() {
    if [ -z "$GMAIL_EMAIL" ] || [ -z "$GMAIL_APP_PASSWORD" ]; then
        echo "${RED}Error:${RESET} Email atau App Password belum diatur di Settings."
        log_message "Gagal cek email: Konfigurasi belum lengkap."
        return 1
    fi

    # Menjalankan script python dan menangkap outputnya
    # stderr dari python akan muncul di terminal listener ini
    local email_data
    email_data=$(python3 "$PYTHON_SCRIPT_PATH" "imap.gmail.com" "$GMAIL_EMAIL" "$GMAIL_APP_PASSWORD" 2>&1)
    local python_exit_code=$?

    # Cek jika python script mengembalikan error
    if [ $python_exit_code -ne 0 ] || [[ "$email_data" == *"ERROR_PYTHON"* ]] || [[ "$email_data" == *"IMAP_ERROR_PYTHON"* ]] || [[ "$email_data" == *"GENERAL_ERROR_PYTHON"* ]]; then
        echo "${RED}Error saat menjalankan Python checker:${RESET}"
        echo "$email_data" # Tampilkan pesan error dari Python
        log_message "Error dari Python script: $email_data"
        return 1
    fi

    # Cek jika tidak ada output (tidak ada email baru yang relevan)
    if [ -z "$email_data" ]; then
        # echo "DEBUG: Tidak ada email baru yang cocok." # Uncomment for debugging
        return 2 # Indicate no new relevant email found
    fi

    # Jika ada output, kembalikan data email
    echo "$email_data"
    return 0 # Success, email data found
}

# Mem-parsing output dari Python script
parse_email_data() {
    local data="$1"
    local subject=""
    local body=""
    local uid=""

    # Ekstrak menggunakan delimiter :::
    subject=$(echo "$data" | sed -n 's/.*SUBJECT:\[\(.*\)\]:::BODY:.*/\1/p')
    body=$(echo "$data" | sed -n 's/.*BODY:\[\(.*\)\]:::UID:.*/\1/p')
    uid=$(echo "$data" | sed -n 's/.*UID:\[\(.*\)\]/\1/p')

    # Fallback jika sed gagal (misal ada karakter aneh), coba cara lain (kurang robus)
    # if [ -z "$subject" ] && [ -z "$body" ]; then ... fi

    # Gabungkan subject dan body untuk pencarian teks
    local full_content="${subject} ${body}"

    log_message "Memproses email UID: $uid | Subject: $subject"
    # echo "DEBUG: Full Content: $full_content" # Uncomment for debugging

    # Cek apakah UID ini sudah diproses sebelumnya
    # if [[ "$uid" == "$last_processed_uid" ]]; then
    #     log_message "UID $uid sudah diproses sebelumnya, dilewati."
    #     return 1 # Already processed
    # fi

    # --- Logika Parsing Utama ---
    # 1. Cari 'Exora AI' (sudah difilter di Python, tapi cek lagi untuk keamanan)
    if [[ "${full_content,,}" =~ "exora ai" ]]; then # Convert to lowercase for case-insensitive check
        # 2. Cari kata 'order' (case-insensitive)
        if [[ "${full_content,,}" =~ order[[:space:]]+([^[:space:]]+) ]]; then
            # Dapatkan kata setelah 'order'
            local action="${BASH_REMATCH[1],,}" # Ambil kata setelah order, lowercase

            log_message "Ditemukan 'order', aksi potensial: '$action'"
            # echo "DEBUG: Kata setelah 'order': $action" # Uncomment for debugging

            # 3. Cek apakah aksinya 'buy' atau 'sell'
            if [[ "$action" == "buy" ]]; then
                log_message "Aksi 'BUY' terdeteksi! Memicu notifikasi."
                trigger_beep "buy"
                last_processed_uid="$uid" # Tandai sebagai sudah diproses
                return 0 # Action found
            elif [[ "$action" == "sell" ]]; then
                log_message "Aksi 'SELL' terdeteksi! Memicu notifikasi."
                trigger_beep "sell"
                last_processed_uid="$uid" # Tandai sebagai sudah diproses
                return 0 # Action found
            else
                log_message "Kata setelah 'order' ('$action') bukan 'buy' atau 'sell'."
            fi
        else
            log_message "Ditemukan 'Exora AI' tapi kata 'order' tidak ditemukan setelahnya."
        fi
    else
         log_message "Pesan tidak mengandung 'Exora AI' (seharusnya sudah difilter Python)."
    fi

    return 1 # No relevant action found
}

# Memicu beep berdasarkan aksi
trigger_beep() {
    local type="$1"
    if ! command -v beep >/dev/null 2>&1; then
        echo "${YELLOW}Notifikasi Suara:${RESET} Perintah 'beep' tidak tersedia."
        log_message "Notifikasi suara gagal: 'beep' tidak ditemukan."
        return
    fi

    echo -n "${CYAN}Memainkan suara untuk $type... ${RESET}"
    if [ "$type" == "buy" ]; then
        # Beep panjang 5 detik
        if ! beep -f "$BEEP_BUY_FREQ" -l "$BEEP_BUY_DURATION"; then
             echo "${RED}Gagal memainkan beep 'buy'. Cek permission/konfigurasi.${RESET}"
             log_message "Gagal 'beep' untuk BUY. Error code: $?"
        else
             echo "${GREEN}OK${RESET}"
             log_message "Notifikasi suara BUY berhasil."
        fi
    elif [ "$type" == "sell" ]; then
        # Dua beep pendek dengan jeda
        local success=true
        if ! beep -f "$BEEP_SELL_FREQ" -l "$BEEP_SELL_DURATION"; then success=false; fi
        sleep "$BEEP_SELL_DELAY"
        if ! beep -f "$BEEP_SELL_FREQ" -l "$BEEP_SELL_DURATION" -D "$BEEP_SELL_DELAY" ; then success=false; fi # Coba pakai delay internal beep jika ada

        if [ "$success" = false ]; then
             echo "${RED}Gagal memainkan beep 'sell'. Cek permission/konfigurasi.${RESET}"
             log_message "Gagal 'beep' untuk SELL. Error code: $?"
        else
            echo "${GREEN}OK${RESET}"
            log_message "Notifikasi suara SELL berhasil."
        fi
    fi
}

# --- Fungsi Tampilan CLI ---

# Animasi spinner sederhana
show_spinner() {
    local pid=$! # Process ID of the previous running command
    local delay=0.1
    local spinstr='/-\|'
    while ps -p $pid > /dev/null; do
        local temp=${spinstr#?}
        printf " [%c]  " "$spinstr"
        local spinstr=$temp${spinstr%"$temp"}
        sleep $delay
        printf "\b\b\b\b\b"
    done
    printf "    \b\b\b\b"
}

# Fungsi utama untuk mode 'Listen'
start_listening() {
    if [ -z "$GMAIL_EMAIL" ] || [ -z "$GMAIL_APP_PASSWORD" ]; then
        echo "${RED}Error:${RESET} Email atau App Password belum diatur. Silakan atur di menu Settings."
        read -p "Tekan Enter untuk kembali..."
        return
    fi

    listener_active=true
    trap 'listener_active=false; echo "\n${YELLOW}Listener dihentikan.${RESET}"; log_message "Listener dihentikan oleh user."; exit' INT TERM # Handle Ctrl+C

    clear
    echo "${BLUE}=====================================${RESET}"
    echo "${BLUE}    Exora AI Email Listener ${CYAN}v1.0${RESET}"
    echo "${BLUE}=====================================${RESET}"
    echo "${GREEN}Memulai listener...${RESET} (Tekan Ctrl+C untuk berhenti)"
    echo "Mengecek email setiap ${YELLOW}${CHECK_INTERVAL}${RESET} detik."
    echo "Log aktivitas disimpan di: ${CYAN}${LOG_FILE}${RESET}"
    log_message "Listener dimulai. Interval: $CHECK_INTERVAL detik."

    while $listener_active; do
        echo -ne "${CYAN}$(date '+%H:%M:%S')${RESET} - Mengecek email... "
        local email_output
        # Jalankan pengecekan di background agar spinner bisa jalan
        run_email_check &
        local check_pid=$!
        # Tampilkan spinner selagi menunggu
        while ps -p $check_pid > /dev/null; do show_spinner; done
        # Tunggu proses selesai dan dapatkan exit code & output
        wait $check_pid
        local exit_code=$?
        # Ambil output (perlu cara jika output besar, tapi untuk ini harusnya aman)
        email_output=$(run_email_check) # Panggil lagi untuk ambil output (atau simpan ke file sementara)

        if [ $exit_code -eq 0 ]; then
            # Ada email baru yang relevan
            echo "${GREEN}Email baru ditemukan!${RESET} Memproses..."
            log_message "Email baru ditemukan, memproses..."
            # Proses email
            parse_email_data "$email_output"
            # Tidak perlu sleep jika baru saja memproses, langsung cek lagi mungkin? Atau tetap sleep.
            sleep "$CHECK_INTERVAL"
        elif [ $exit_code -eq 2 ]; then
            # Tidak ada email baru yang relevan
            echo "${GREEN}Tidak ada email baru yang cocok.${RESET}"
            sleep "$CHECK_INTERVAL"
        else
            # Terjadi error saat cek email
            echo "${RED}Gagal memeriksa email (Error Code: $exit_code). Coba lagi nanti.${RESET}"
            log_message "Gagal cek email (Error Code: $exit_code)."
            sleep $((CHECK_INTERVAL * 2)) # Tunggu lebih lama jika ada error
        fi
    done
}

# Menampilkan menu Settings
show_settings() {
    clear
    echo "${BLUE}--- Pengaturan ---${RESET}"
    echo "1. Email Gmail      : ${YELLOW}${GMAIL_EMAIL:-Belum diatur}${RESET}"
    echo "2. App Password     : ${YELLOW}${GMAIL_APP_PASSWORD:+(Tersimpan)}${RESET}" # Jangan tampilkan passwordnya
    echo "3. Interval Cek (s) : ${YELLOW}${CHECK_INTERVAL}${RESET}"
    echo "--------------------"
    echo "4. ${GREEN}Simpan & Kembali${RESET}"
    echo "5. ${RED}Kembali tanpa menyimpan${RESET}"

    local choice
    while true; do
        read -p "Pilih opsi atau nomor item untuk diubah: " choice
        case $choice in
            1) read -p "Masukkan Email Gmail baru: " GMAIL_EMAIL ;;
            2) read -sp "Masukkan Gmail App Password baru: " GMAIL_APP_PASSWORD; echo ;;
            3) read -p "Masukkan Interval Cek baru (detik): " input_interval
               # Validasi input adalah angka
               if [[ "$input_interval" =~ ^[0-9]+$ ]] && [ "$input_interval" -gt 0 ]; then
                   CHECK_INTERVAL=$input_interval
               else
                   echo "${RED}Input tidak valid, harus angka positif.${RESET}"
               fi
               ;;
            4) save_config; break ;;
            5) load_config > /dev/null # Reload config dari file jika batal
               echo "${YELLOW}Perubahan dibatalkan.${RESET}"
               break ;;
            *) echo "${RED}Pilihan tidak valid.${RESET}" ;;
        esac
        # Tampilkan ulang menu setelah perubahan
        clear
        echo "${BLUE}--- Pengaturan ---${RESET}"
        echo "1. Email Gmail      : ${YELLOW}${GMAIL_EMAIL:-Belum diatur}${RESET}"
        echo "2. App Password     : ${YELLOW}${GMAIL_APP_PASSWORD:+(Tersimpan)}${RESET}"
        echo "3. Interval Cek (s) : ${YELLOW}${CHECK_INTERVAL}${RESET}"
        echo "--------------------"
        echo "4. ${GREEN}Simpan & Kembali${RESET}"
        echo "5. ${RED}Kembali tanpa menyimpan${RESET}"
    done
}

# Menampilkan Homepage / Menu Utama
display_homepage() {
    clear
    echo "${BOLD}${BLUE}"
    cat << "EOF"
        _______ __                      ___ __        __  _
       / ____(_) /____  _________     <  / / /___    / /_(_)___  ____ ____
      / __/ / / __/ _ \/ ___/ __ \    / / / / / _ \  / __/ / __ \/ __ `/ _ \
     / /___/ / /_/  __/ /  / / / /   / / / / /  __/ / /_/ / / / / /_/ /  __/
    /_____/_/\__/\___/_/  /_/ /_/   /_/_/_/_/\___/  \__/_/_/ /_/\__, /\___/
                                    Exora AI Email Listener   /____/ ${CYAN}v1.0${RESET}
EOF
    echo "${RESET}"
    echo "${GREEN}================ Menu Utama ================${RESET}"
    echo "${CYAN}1.${RESET} ${BOLD}Mulai Listener${RESET}"
    echo "${CYAN}2.${RESET} Pengaturan (Email, Password, Interval)"
    echo "${CYAN}3.${RESET} Lihat Log Aktivitas (${YELLOW}tail -f $LOG_FILE${RESET})"
    echo "${CYAN}4.${RESET} ${RED}Keluar${RESET}"
    echo "${GREEN}===========================================${RESET}"
}

# --- Main Execution ---

# 1. Pastikan direktori ada
ensure_dirs

# 2. Cek dependensi
check_dependencies

# 3. Muat konfigurasi, jika tidak ada, minta input awal
if ! load_config; then
    prompt_initial_config
    # Muat lagi setelah dibuat
    load_config
fi

# 4. Loop Menu Utama
while true; do
    display_homepage
    read -p "${BOLD}Pilih opsi [1-4]: ${RESET}" main_choice
    case $main_choice in
        1) start_listening ;;
        2) show_settings ;;
        3) echo "${YELLOW}Menampilkan log (Tekan Ctrl+C untuk berhenti melihat log):${RESET}"; tail -f "$LOG_FILE"; read -p "Tekan Enter untuk kembali ke menu..." ;;
        4) echo "${BLUE}Terima kasih telah menggunakan Exora AI Listener!${RESET}"; log_message "Aplikasi ditutup."; exit 0 ;;
        *) echo "${RED}Pilihan tidak valid. Silakan coba lagi.${RESET}"; sleep 1 ;;
    esac
    # Jika listener dihentikan (Ctrl+C), script akan exit, tidak kembali ke sini
    # Jika kembali dari settings atau log viewer, tunggu sebentar
    if [[ "$main_choice" != "1" ]]; then
      # read -p "Tekan Enter untuk kembali ke menu utama..."
      sleep 0.5 # Jeda singkat sebelum menampilkan menu lagi
    fi
done
