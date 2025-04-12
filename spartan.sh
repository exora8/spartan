#!/usr/bin/env bash

# Script Email Listener & Binance Trader
# Versi: 1.5 (Pure Text CLI with Colors)
# Author: [Nama Kamu/AI] & Kontributor

# --- Konfigurasi Awal ---
CONFIG_FILE="$HOME/.email_trader_rc"
LOG_FILE="/tmp/email_trader.log"
PID_FILE="/tmp/email_trader.pid" # File untuk menyimpan PID listener
touch "$LOG_FILE" # Pastikan file log ada
chmod 600 "$LOG_FILE" # Amankan log jika perlu

# Identifier Email yang Dicari (Subject atau Body)
EMAIL_IDENTIFIER="Exora AI (V5 SPOT + SR Filter) (1M)" # Contoh, ganti sesuai kebutuhan

# --- Variabel Global ---
LISTENER_PID="" # Akan diisi dari PID_FILE saat script start
SCRIPT_MAIN_PID=$$ # Simpan PID script utama

# --- Kode Warna ANSI ---
C_RESET='\033[0m'
C_BOLD='\033[1m'
C_DIM='\033[2m' # Kurang umum didukung, alternatifnya bisa warna abu-abu jika ada
C_RED='\033[0;31m'
C_GREEN='\033[0;32m'
C_YELLOW='\033[0;33m'
C_BLUE='\033[0;34m'
C_MAGENTA='\033[0;35m'
C_CYAN='\033[0;36m'
C_WHITE='\033[0;37m'
C_BG_RED='\033[41m'
C_BG_GREEN='\033[42m'
C_BG_YELLOW='\033[43m'

# --- Fungsi ---

# Fungsi jeda & clear (opsional)
pause_and_clear() {
    read -n 1 -s -r -p "$(printf "${C_DIM}Tekan tombol apa saja untuk lanjut...${C_RESET}")"
    clear
}

# Fungsi menampilkan pesan error (teks)
error_msg() {
    clear
    printf "\n${C_BOLD}${C_RED}==================== ERROR ====================${C_RESET}\n"
    printf "${C_RED}%s${C_RESET}\n" "$1"
    printf "${C_BOLD}${C_RED}==============================================${C_RESET}\n\n"
    log_message "ERROR_MSG: $1"
    pause_and_clear
}

# Fungsi menampilkan info (teks)
info_msg() {
    clear
    printf "\n${C_BOLD}${C_GREEN}==================== INFO ====================${C_RESET}\n"
    printf "${C_GREEN}%s${C_RESET}\n" "$1"
    printf "${C_BOLD}${C_GREEN}==============================================${C_RESET}\n\n"
    pause_and_clear
}

# Fungsi cek dependensi
check_deps() {
    local missing_deps=()
    # Hapus 'dialog', tambahkan 'jq'
    for cmd in neomutt curl openssl jq grep sed awk cut date mktemp tail wc kill sleep wait clear pgrep less; do
        if ! command -v "$cmd" &> /dev/null; then
             # Cek alternatif mutt
             if [[ "$cmd" == "neomutt" ]] && command -v mutt &> /dev/null; then
                 continue # mutt ada, skip neomutt
             fi
            missing_deps+=("$cmd")
        fi
    done
    # Cek lagi neomutt atau mutt secara spesifik
    if ! command -v neomutt &> /dev/null && ! command -v mutt &> /dev/null; then
         missing_deps+=("neomutt atau mutt")
    fi

    if [ ${#missing_deps[@]} -ne 0 ]; then
        clear
        printf "\n${C_BOLD}${C_RED}==================== ERROR DEPENDENSI ====================${C_RESET}\n" >&2
        printf "${C_RED}Dependensi berikut tidak ditemukan atau tidak ada di PATH:${C_RESET}\n" >&2
        printf "${C_RED} - %s\n${C_RESET}" "${missing_deps[@]}" >&2
        printf "\n${C_YELLOW}Silakan install terlebih dahulu sebelum menjalankan script.${C_RESET}\n" >&2
        printf "${C_BOLD}${C_RED}=========================================================${C_RESET}\n\n" >&2
        exit 1
    fi
    # Tetapkan EMAIL_CLIENT yang valid
    EMAIL_CLIENT=$(command -v neomutt || command -v mutt)
}

# Fungsi load konfigurasi (tanpa perubahan)
load_config() {
    if [ -f "$CONFIG_FILE" ]; then
        chmod 600 "$CONFIG_FILE"
        GMAIL_USER=$(grep -Po "^GMAIL_USER *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        GMAIL_APP_PASS=$(grep -Po "^GMAIL_APP_PASS *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        BINANCE_API_KEY=$(grep -Po "^BINANCE_API_KEY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        BINANCE_SECRET_KEY=$(grep -Po "^BINANCE_SECRET_KEY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        TRADE_SYMBOL=$(grep -Po "^TRADE_SYMBOL *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        TRADE_QUANTITY=$(grep -Po "^TRADE_QUANTITY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        CHECK_INTERVAL=$(grep -Po "^CHECK_INTERVAL *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)

        if [[ -z "$GMAIL_USER" || -z "$GMAIL_APP_PASS" || -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$TRADE_SYMBOL" || -z "$TRADE_QUANTITY" || -z "$CHECK_INTERVAL" ]]; then
            log_message "WARNING: File konfigurasi $CONFIG_FILE ada tapi tidak lengkap atau gagal parse."
            return 1
        fi
        log_message "Konfigurasi berhasil dimuat dari $CONFIG_FILE."
        CHECK_INTERVAL="${CHECK_INTERVAL:-60}"
        return 0
    else
        log_message "INFO: File konfigurasi $CONFIG_FILE tidak ditemukan."
        return 1
    fi
}

# Fungsi simpan konfigurasi (info diganti text)
save_config() {
    rm -f "$CONFIG_FILE"
    echo "# Konfigurasi Email Trader (v1.5)" > "$CONFIG_FILE"
    echo "GMAIL_USER='${GMAIL_USER}'" >> "$CONFIG_FILE"
    echo "GMAIL_APP_PASS='${GMAIL_APP_PASS}'" >> "$CONFIG_FILE"
    echo "BINANCE_API_KEY='${BINANCE_API_KEY}'" >> "$CONFIG_FILE"
    echo "BINANCE_SECRET_KEY='${BINANCE_SECRET_KEY}'" >> "$CONFIG_FILE"
    echo "TRADE_SYMBOL='${TRADE_SYMBOL}'" >> "$CONFIG_FILE"
    echo "TRADE_QUANTITY='${TRADE_QUANTITY}'" >> "$CONFIG_FILE"
    echo "CHECK_INTERVAL='${CHECK_INTERVAL}'" >> "$CONFIG_FILE"
    chmod 600 "$CONFIG_FILE"
    log_message "Konfigurasi berhasil disimpan di $CONFIG_FILE"
    # Gunakan info_msg versi teks
    info_msg "Konfigurasi berhasil disimpan di ${C_CYAN}${CONFIG_FILE}${C_GREEN}."
}

# Fungsi konfigurasi interaktif (teks)
configure_settings() {
    # Cek jika listener sedang jalan
    if is_listener_running; then
        error_msg "Listener sedang aktif (PID: $LISTENER_PID). Hentikan listener terlebih dahulu sebelum mengubah konfigurasi."
        return 1
    fi

    load_config # Muat nilai saat ini jika ada

    # Simpan nilai sementara untuk ditampilkan sebagai default
    local current_gmail_user="${GMAIL_USER}"
    local current_gmail_pass="${GMAIL_APP_PASS}" # Tidak ditampilkan, hanya untuk logika default
    local current_api_key="${BINANCE_API_KEY}"
    local current_secret_key="${BINANCE_SECRET_KEY}" # Tidak ditampilkan
    local current_symbol="${TRADE_SYMBOL}"
    local current_quantity="${TRADE_QUANTITY}"
    local current_interval="${CHECK_INTERVAL:-60}"

    # Variabel untuk menampung input baru
    local input_gmail_user input_gmail_pass input_api_key input_secret_key input_symbol input_quantity input_interval

    clear
    printf "${C_BOLD}${C_BLUE}--- Konfigurasi Email Trader ---${C_RESET}\n"
    printf "${C_DIM}Masukkan detail konfigurasi. Tekan Enter untuk memakai nilai saat ini (jika ada).\n${C_DIM}Untuk password/key, nilai saat ini tidak ditampilkan.${C_RESET}\n\n"

    # --- Input Fields ---
    read -p "$(printf "${C_YELLOW}Alamat Gmail Anda ${C_DIM}[${C_CYAN}%s${C_DIM}]${C_YELLOW}: ${C_RESET}" "${current_gmail_user:-kosong}")" input_gmail_user
    # Gunakan nilai baru jika diisi, jika tidak, gunakan nilai lama
    GMAIL_USER="${input_gmail_user:-$current_gmail_user}"

    read -p "$(printf "${C_YELLOW}Gmail App Password ${C_DIM}[${C_CYAN}*****${C_DIM}]${C_YELLOW}: ${C_RESET}")" input_gmail_pass
    # Jika user tidak input apa2, JANGAN kosongkan password yg sudah ada
    if [[ -n "$input_gmail_pass" ]]; then
        GMAIL_APP_PASS="$input_gmail_pass"
    elif [[ -z "$current_gmail_pass" ]]; then
        # Jika password lama memang kosong, dan user tidak input, set jadi kosong
         GMAIL_APP_PASS=""
    fi # Else: biarkan GMAIL_APP_PASS dengan nilai lama (current_gmail_pass)

    read -p "$(printf "${C_YELLOW}Binance API Key ${C_DIM}[${C_CYAN}%s${C_DIM}]${C_YELLOW}: ${C_RESET}" "${current_api_key:-kosong}")" input_api_key
    BINANCE_API_KEY="${input_api_key:-$current_api_key}"

    read -p "$(printf "${C_YELLOW}Binance Secret Key ${C_DIM}[${C_CYAN}*****${C_DIM}]${C_YELLOW}: ${C_RESET}")" input_secret_key
    if [[ -n "$input_secret_key" ]]; then
        BINANCE_SECRET_KEY="$input_secret_key"
    elif [[ -z "$current_secret_key" ]]; then
         BINANCE_SECRET_KEY=""
    fi

    read -p "$(printf "${C_YELLOW}Simbol Trading (cth: BTCUSDT) ${C_DIM}[${C_CYAN}%s${C_DIM}]${C_YELLOW}: ${C_RESET}" "${current_symbol:-kosong}")" input_symbol
    TRADE_SYMBOL=$(echo "${input_symbol:-$current_symbol}" | tr 'a-z' 'A-Z') # Langsung uppercase

    read -p "$(printf "${C_YELLOW}Jumlah Quantity Trading (cth: 0.001) ${C_DIM}[${C_CYAN}%s${C_DIM}]${C_YELLOW}: ${C_RESET}" "${current_quantity:-kosong}")" input_quantity
    TRADE_QUANTITY="${input_quantity:-$current_quantity}"

    read -p "$(printf "${C_YELLOW}Interval Cek Email (detik) ${C_DIM}[${C_CYAN}%s${C_DIM}]${C_YELLOW}: ${C_RESET}" "${current_interval}")" input_interval
    CHECK_INTERVAL="${input_interval:-$current_interval}"


    # --- Validasi Input (Harus diisi semua) ---
    printf "\n${C_BLUE}Memvalidasi input...${C_RESET}\n"
    local validation_passed=true
    if [[ -z "$GMAIL_USER" ]]; then printf "${C_RED}- Alamat Gmail tidak boleh kosong.${C_RESET}\n"; validation_passed=false; fi
    if [[ -z "$GMAIL_APP_PASS" ]]; then printf "${C_RED}- Gmail App Password tidak boleh kosong.${C_RESET}\n"; validation_passed=false; fi
    if [[ -z "$BINANCE_API_KEY" ]]; then printf "${C_RED}- Binance API Key tidak boleh kosong.${C_RESET}\n"; validation_passed=false; fi
    if [[ -z "$BINANCE_SECRET_KEY" ]]; then printf "${C_RED}- Binance Secret Key tidak boleh kosong.${C_RESET}\n"; validation_passed=false; fi
    if [[ -z "$TRADE_SYMBOL" ]]; then printf "${C_RED}- Simbol Trading tidak boleh kosong.${C_RESET}\n"; validation_passed=false; fi
    if [[ -z "$TRADE_QUANTITY" ]]; then
        printf "${C_RED}- Quantity Trading tidak boleh kosong.${C_RESET}\n"; validation_passed=false;
    elif ! [[ "$TRADE_QUANTITY" =~ ^[+]?([0-9]+(\.[0-9]*)?|\.[0-9]+)$ && "$TRADE_QUANTITY" != "0" && "$TRADE_QUANTITY" != "0.0" ]]; then
        printf "${C_RED}- Quantity trading harus berupa angka positif (misal: 0.001 atau 10).${C_RESET}\n"; validation_passed=false;
    fi
     if [[ -z "$CHECK_INTERVAL" ]]; then
        printf "${C_RED}- Interval Cek Email tidak boleh kosong.${C_RESET}\n"; validation_passed=false;
    elif ! [[ "$CHECK_INTERVAL" =~ ^[1-9][0-9]*$ ]]; then
        printf "${C_RED}- Interval cek email harus berupa angka positif (detik).${C_RESET}\n"; validation_passed=false;
     fi

    if ! $validation_passed; then
        printf "\n${C_RED}Konfigurasi tidak valid. Silakan coba lagi.${C_RESET}\n"
        pause_and_clear
        return 1
    fi

    printf "${C_GREEN}Validasi berhasil.${C_RESET}\n"
    save_config # Panggil save_config yang sudah diupdate
    return 0
}


# Fungsi untuk logging ke file (tanpa perubahan)
log_message() {
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    # Tambahkan PID jika ada
    local pid_info=""
    # Log PID dari proses background atau jika PID berbeda dari script utama
    if [[ -n "$$" && "$$" != "$SCRIPT_MAIN_PID" ]]; then
       pid_info=" [PID $$]"
    fi
    echo "[$timestamp]$pid_info $1" >> "${LOG_FILE:-/tmp/email_trader_fallback.log}"
}

# --- Fungsi Background Listener (tanpa perubahan mayor di logika inti) ---

# Fungsi cek email baru yang cocok
check_email() {
    log_message "Mencari email baru dari $GMAIL_USER dengan identifier: '$EMAIL_IDENTIFIER'"
    local email_body_file
    email_body_file=$(mktemp 2>>"$LOG_FILE") || { log_message "ERROR: Gagal membuat file temporary untuk email."; return 1; }

    "$EMAIL_CLIENT" \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail=""' \
        -e 'push "<limit>~N (~b \"'${EMAIL_IDENTIFIER}'\" | ~s \"'${EMAIL_IDENTIFIER}'\")\n<pipe-message>cat > '${email_body_file}'\n<exit>"' > /dev/null 2>&1
    local mutt_exit_code=$?
    # Jangan log error jika exit code 1 (biasanya no new mail)
    [ $mutt_exit_code -ne 0 ] && [ $mutt_exit_code -ne 1 ] && log_message "WARNING: Perintah $EMAIL_CLIENT keluar dengan kode $mutt_exit_code (Mungkin error koneksi)"

    if [ -s "$email_body_file" ]; then
        log_message "Email yang cocok ditemukan. Memproses..."
        parse_email_body "$email_body_file"
        local parse_status=$?
        rm "$email_body_file"
        if [ $parse_status -eq 0 ]; then
             mark_email_as_read
        else
             log_message "Action tidak ditemukan atau gagal parse/eksekusi, email tidak ditandai dibaca."
        fi
        return 0 # Email ditemukan (diproses atau tidak)
    else
        # Jika exit code 0 atau 1 tapi file kosong, berarti tidak ada email cocok
        log_message "Tidak ada email baru yang cocok ditemukan."
        rm "$email_body_file"
        return 1 # Tidak ada email
    fi
}

# Fungsi parsing body email (tanpa perubahan)
parse_email_body() {
    local body_file="$1"
    log_message "Parsing isi email dari $body_file"
    local action=""

    # Perbaiki grep agar case-insensitive dan hanya match kata utuh
    if grep -qiw "buy" "$body_file" 2>>"$LOG_FILE"; then
        action="BUY"
    elif grep -qiw "sell" "$body_file" 2>>"$LOG_FILE"; then
        action="SELL"
    fi

    # Cek identifier lagi untuk keamanan ganda
    if ! grep -q "$EMAIL_IDENTIFIER" "$body_file" 2>>"$LOG_FILE"; then
        log_message "WARNING: Action '$action' terdeteksi, tapi identifier '$EMAIL_IDENTIFIER' tidak ditemukan di body email ini. Mengabaikan."
        return 1 # Gagal Parse
    fi

    if [[ "$action" == "BUY" ]]; then
        log_message "Action terdeteksi: BUY"
        execute_binance_order "BUY"
        return $? # Return status from execute_binance_order
    elif [[ "$action" == "SELL" ]]; then
        log_message "Action terdeteksi: SELL"
        execute_binance_order "SELL"
        return $? # Return status from execute_binance_order
    else
        log_message "WARNING: Tidak ada action 'BUY' atau 'SELL' yang valid terdeteksi dalam email yang cocok."
        return 1 # Gagal Parse
    fi
}

# Fungsi untuk menandai email sebagai sudah dibaca (tanpa perubahan)
mark_email_as_read() {
    log_message "Menandai email sebagai sudah dibaca..."
    "$EMAIL_CLIENT" \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail=""' \
        -e 'push "<limit>~U (~b \"'${EMAIL_IDENTIFIER}'\" | ~s \"'${EMAIL_IDENTIFIER}'\")\n<clear-flag>N\n<sync-mailbox><exit>"' > /dev/null 2>&1 # Limit ke Unread saja
    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        log_message "Perintah untuk menandai email dibaca telah dikirim (menargetkan email belum dibaca yang cocok)."
    else
        log_message "WARNING: Perintah $EMAIL_CLIENT untuk menandai email dibaca mungkin gagal (exit code: $exit_code)."
    fi
}

# Fungsi generate signature Binance (tanpa perubahan)
generate_binance_signature() {
    local query_string="$1"
    local secret="$2"
    # Pastikan tidak ada output aneh ke stdout, redirect error ke log
    echo -n "$query_string" | openssl dgst -sha256 -hmac "$secret" 2>>"$LOG_FILE" | sed 's/^.* //'
}

# Fungsi eksekusi order Binance (tanpa perubahan)
execute_binance_order() {
    local side="$1"
    local timestamp
    timestamp=$(date +%s%3N)
    if [[ -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$TRADE_SYMBOL" || -z "$TRADE_QUANTITY" ]]; then
        log_message "ERROR: Konfigurasi Binance tidak lengkap. Tidak bisa membuat order."
        return 1
    fi

    local api_endpoint="https://api.binance.com" # Ganti ke api1/2/3 jika perlu
    local order_path="/api/v3/order"
    # Perbaiki '&' bukan '×'
    local params="symbol=${TRADE_SYMBOL}&side=${side}&type=MARKET&quantity=${TRADE_QUANTITY}×tamp=${timestamp}"
    local signature
    signature=$(generate_binance_signature "$params" "$BINANCE_SECRET_KEY")
    if [ -z "$signature" ]; then
        log_message "ERROR: Gagal menghasilkan signature Binance. Periksa error openssl di log."
        return 1
    fi

    local full_url="${api_endpoint}${order_path}?${params}&signature=${signature}"
    log_message "Mengirim order ke Binance: SIDE=$side SYMBOL=$TRADE_SYMBOL QTY=$TRADE_QUANTITY"

    local response curl_exit_code http_code body
    # Tambahkan timeout ke curl
    response=$(curl --connect-timeout 10 --max-time 20 -s -w "\n%{http_code}" -H "X-MBX-APIKEY: ${BINANCE_API_KEY}" -X POST "$full_url" 2>>"$LOG_FILE")
    curl_exit_code=$?
    # Ambil http_code dari baris terakhir, body dari sisanya
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')


    if [ $curl_exit_code -ne 0 ]; then
        log_message "ERROR: curl gagal menghubungi Binance (Curl Exit code: $curl_exit_code). Cek log untuk detail stderr curl."
        return 1
    fi

    log_message "Response Binance (HTTP $http_code): $body"

    if [[ "$http_code" =~ ^2 ]]; then
        local orderId status clientOrderId fillPrice fillQty
        # Parse lebih aman pakai jq
        orderId=$(echo "$body" | jq -r '.orderId // empty' 2>>"$LOG_FILE")
        status=$(echo "$body" | jq -r '.status // "UNKNOWN"' 2>>"$LOG_FILE")
        clientOrderId=$(echo "$body" | jq -r '.clientOrderId // empty' 2>>"$LOG_FILE")
        # Coba parse harga dan qty dari 'fills' jika ada (untuk MARKET order)
        fillPrice=$(echo "$body" | jq -r 'try .fills[0].price catch empty' 2>>"$LOG_FILE")
        fillQty=$(echo "$body" | jq -r 'try .fills[0].qty catch empty' 2>>"$LOG_FILE")

        if [ -n "$orderId" ]; then
             local success_msg="SUCCESS: Order ${side} ${TRADE_SYMBOL} berhasil. ID: ${orderId}, Status: ${status}"
             if [[ -n "$fillPrice" && -n "$fillQty" ]]; then
                 success_msg+=", Fill: ${fillQty} @ ${fillPrice}"
             fi
            log_message "$success_msg"
            # Notifikasi bisa ditambah di sini
            return 0
        else
            log_message "WARNING: HTTP 2xx diterima tapi tidak ada Order ID di response JSON. Body: $body"
            return 0 # Anggap sukses jika HTTP 2xx
        fi
    else
        local err_code err_msg
        err_code=$(echo "$body" | jq -r '.code // "?"' 2>>"$LOG_FILE")
        err_msg=$(echo "$body" | jq -r '.msg // "Tidak ada pesan error spesifik"' 2>>"$LOG_FILE")
        log_message "ERROR: Gagal menempatkan order. Kode Error Binance: $err_code Pesan: $err_msg"
        # Notifikasi GAGAL bisa ditambah di sini
        return 1
    fi
}

# Fungsi Loop Utama Listener (tanpa perubahan)
listener_loop() {
    export GMAIL_USER GMAIL_APP_PASS BINANCE_API_KEY BINANCE_SECRET_KEY TRADE_SYMBOL TRADE_QUANTITY EMAIL_IDENTIFIER EMAIL_CLIENT LOG_FILE CHECK_INTERVAL
    local check_interval="${CHECK_INTERVAL:-60}"
    if ! [[ "$check_interval" =~ ^[1-9][0-9]*$ ]]; then
        log_message "WARNING: Interval cek email tidak valid ($check_interval) di listener loop. Menggunakan default 60 detik."
        check_interval=60
    fi

    trap 'log_message "Listener loop (PID $$) dihentikan oleh sinyal."; exit 0' SIGTERM SIGINT

    log_message "Listener loop dimulai (PID $$). Interval: ${check_interval} detik."
    while true; do
        log_message "Memulai siklus pengecekan email..."
        if ! check_email; then
            : # Tidak ada email baru, tidak perlu log khusus
        fi
        log_message "Siklus selesai. Menunggu ${check_interval} detik..."
        sleep "$check_interval"

        # Log rotation/trimming (opsional tapi bagus)
        local max_log_lines=1000
        local current_lines
        current_lines=$(wc -l < "$LOG_FILE" 2>/dev/null) # Redirect error wc jika file tiba2 hilang
        if [[ "$current_lines" =~ ^[0-9]+$ && "$current_lines" -gt "$max_log_lines" ]]; then
             log_message "INFO: File log dipangkas ke $max_log_lines baris terakhir."
             # Cara pangkas yang lebih aman
             tail -n "$max_log_lines" "$LOG_FILE" > "${LOG_FILE}.tmp" 2>/dev/null && mv "${LOG_FILE}.tmp" "$LOG_FILE" 2>/dev/null
             if [ $? -ne 0 ]; then log_message "WARNING: Gagal memangkas file log."; fi
        elif ! [[ "$current_lines" =~ ^[0-9]+$ ]]; then
             # Jangan terlalu berisik jika wc gagal sekali
             : # log_message "WARNING: Gagal mendapatkan jumlah baris log (output wc: $current_lines)."
        fi
    done
}

# --- Fungsi Kontrol Listener ---

# Cek apakah listener sedang berjalan (tanpa perubahan)
is_listener_running() {
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE")
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            LISTENER_PID="$pid"
            return 0 # Sedang berjalan
        else
            log_message "INFO: File PID ditemukan ($PID_FILE) tapi proses $pid tidak berjalan. Menghapus file PID basi."
            rm -f "$PID_FILE"
            LISTENER_PID=""
            return 1 # Tidak berjalan
        fi
    else
        LISTENER_PID=""
        return 1 # Tidak berjalan
    fi
}

# Memulai listener (pesan diganti teks)
start_listener() {
    if is_listener_running; then
        error_msg "Listener sudah berjalan (PID: $LISTENER_PID)."
        return 1
    fi

    if ! load_config; then
        error_msg "Konfigurasi belum lengkap atau gagal dimuat. Tidak bisa memulai listener."
        return 1
    fi

    log_message "Memulai listener di background..."
    printf "${C_BLUE}Memulai listener di background...${C_RESET}\n"
    # Jalankan listener_loop di background
    (listener_loop) &
    local pid=$!

    # Tunggu sebentar untuk memastikan proses benar2 jalan sebelum menyimpan PID
    sleep 1
    if ! kill -0 "$pid" 2>/dev/null; then
        log_message "ERROR: Proses listener gagal dimulai atau langsung exit."
        error_msg "Gagal memulai proses listener di background."
        return 1
    fi

    # Simpan PID ke file
    echo "$pid" > "$PID_FILE"
    if [ $? -ne 0 ]; then
       log_message "ERROR: Gagal menyimpan PID $pid ke $PID_FILE. Menghentikan listener..."
       kill "$pid" 2>/dev/null # Coba hentikan proses yg mungkin sudah jalan
       error_msg "Gagal menyimpan file PID. Listener tidak dimulai."
       return 1
    fi

    LISTENER_PID="$pid"
    log_message "Listener berhasil dimulai di background (PID: $LISTENER_PID)."
    # Tampilkan info teks
    info_msg "Listener berhasil dimulai (PID: ${C_CYAN}${LISTENER_PID}${C_GREEN}). Log aktivitas bisa dilihat di menu."
    return 0
}

# Menghentikan listener (pesan diganti teks)
stop_listener() {
    if ! is_listener_running; then
        error_msg "Listener tidak sedang berjalan."
        return 1
    fi

    log_message "Mengirim sinyal TERM ke listener (PID: $LISTENER_PID)..."
    printf "${C_YELLOW}Menghentikan listener (PID: $LISTENER_PID)...${C_RESET} "
    if kill -TERM "$LISTENER_PID" 2>/dev/null; then
        local count=0
        # Tampilkan indikator loading sederhana
        while kill -0 "$LISTENER_PID" 2>/dev/null; do
            ((count++))
            if [ "$count" -gt 10 ]; then # Tunggu maksimal 5 detik (10 * 0.5s)
                printf "\n${C_RED}Listener tidak berhenti dengan TERM. Mengirim KILL...${C_RESET} "
                log_message "WARNING: Listener (PID: $LISTENER_PID) tidak berhenti dengan TERM setelah 5 detik. Mengirim KILL."
                kill -KILL "$LISTENER_PID" 2>/dev/null
                sleep 0.5 # Beri waktu sedikit setelah KILL
                break
            fi
            printf "."
            sleep 0.5
        done

        # Cek lagi setelah loop
        if ! kill -0 "$LISTENER_PID" 2>/dev/null; then
            printf "\n${C_GREEN}Listener berhasil dihentikan.${C_RESET}\n"
            log_message "Listener (PID: $LISTENER_PID) berhasil dihentikan."
            # Hapus PID file hanya jika berhasil dihentikan
            rm -f "$PID_FILE"
            LISTENER_PID=""
            pause_and_clear
            return 0
        else
            printf "\n${C_RED}ERROR: Gagal menghentikan listener (PID: $LISTENER_PID) bahkan dengan KILL.${C_RESET}\n"
            log_message "ERROR: Gagal menghentikan listener (PID: $LISTENER_PID) bahkan dengan KILL."
            # Jangan hapus PID file jika gagal stop
            pause_and_clear
            return 1 # Return error
        fi
    else
        printf "\n${C_YELLOW}WARNING: Gagal mengirim sinyal TERM ke PID $LISTENER_PID (mungkin sudah berhenti).${C_RESET}\n"
        log_message "WARNING: Gagal mengirim sinyal TERM ke PID $LISTENER_PID (mungkin sudah berhenti)."
        # Jika sinyal gagal dikirim, kemungkinan proses sudah mati, jadi hapus PID file
        rm -f "$PID_FILE"
        LISTENER_PID=""
        pause_and_clear
        return 0 # Anggap sukses jika memang sudah berhenti
    fi
}


# Menampilkan log real-time (pakai tail -f)
show_live_log() {
    if ! is_listener_running; then
        error_msg "Listener tidak sedang berjalan. Tidak ada log real-time untuk ditampilkan."
        return 1
    fi
     clear
     printf "${C_BOLD}${C_GREEN}--- Menampilkan Log Real-time (PID: $LISTENER_PID) ---${C_RESET}\n"
     printf "${C_DIM}Log dari: ${LOG_FILE}${C_RESET}\n"
     printf "${C_YELLOW}Tekan ${C_BOLD}Ctrl+C${C_YELLOW} untuk berhenti melihat log (listener tetap jalan).${C_RESET}\n\n"
     # Jalankan tail -f. Ctrl+C akan menginterupsi tail, bukan script utama jika trap SIGINT diatur benar
     # Gunakan subshell dengan trap sendiri untuk menangani Ctrl+C saat tail berjalan
     (
       trap '' SIGINT # Abaikan SIGINT di subshell agar tidak keluar dari script utama
       tail -f "$LOG_FILE"
     )
     # Setelah tail diinterupsi (Ctrl+C), kembali ke sini
     printf "\n\n${C_YELLOW}--- Selesai melihat log real-time ---${C_RESET}\n"
     pause_and_clear
}

# Fungsi Tampilkan Log Statis (pakai less)
view_static_log() {
    clear
    if [ -f "$LOG_FILE" ]; then
        printf "${C_BOLD}${C_CYAN}--- Menampilkan Log Statis ---${C_RESET}\n"
        printf "${C_DIM}Log dari: ${LOG_FILE}${C_RESET}\n"
        printf "${C_YELLOW}Gunakan panah untuk scroll, tekan '${C_BOLD}q${C_YELLOW}' untuk keluar dari tampilan log.${C_RESET}\n\n"
        # Pakai less agar bisa scroll. -R untuk memproses warna jika ada di log.
        less -R "$LOG_FILE"
        # Setelah keluar dari less, kembali ke sini
        clear
    else
        info_msg "File log (${C_CYAN}${LOG_FILE}${C_RESET}) belum ada atau kosong."
    fi
}

# --- Fungsi Menu Utama (Teks) ---
main_menu() {
    while true; do
        clear
        is_listener_running # Update status dan $LISTENER_PID

        # --- Header Keren ---
        printf "${C_BOLD}${C_CYAN}##############################################${C_RESET}\n"
        printf "${C_BOLD}${C_CYAN}#            EMAIL TRADER BOT v1.5           #${C_RESET}\n"
        printf "${C_BOLD}${C_CYAN}#        (c) $(date +%Y) [Nama Kamu/AI]            #${C_RESET}\n"
        printf "${C_BOLD}${C_CYAN}##############################################${C_RESET}\n"

        # --- Status Listener ---
        if [[ -n "$LISTENER_PID" ]]; then
            printf "\n${C_BG_GREEN}${C_BOLD}${C_WHITE} STATUS: LISTENER AKTIF ${C_RESET} ${C_GREEN}(PID: ${LISTENER_PID})${C_RESET}\n\n"
        else
            printf "\n${C_BG_YELLOW}${C_BOLD}${C_WHITE} STATUS: LISTENER TIDAK AKTIF ${C_RESET}\n\n"
        fi

        # --- Opsi Menu Dinamis ---
        printf "${C_BOLD}${C_BLUE}--- MENU UTAMA ---${C_RESET}\n"
        local options=()
        local choice_map=() # Map nomor pilihan ke aksi

        if [[ -n "$LISTENER_PID" ]]; then # Listener Aktif
            options+=("1) ${C_GREEN}Lihat Log Listener (Real-time)${C_RESET}")
            choice_map[1]="show_live_log"
            options+=("2) ${C_RED}Hentikan Listener${C_RESET}")
            choice_map[2]="stop_listener"
            options+=("3) ${C_DIM}Pengaturan (Nonaktifkan Listener Dulu)${C_RESET}") # Pilihan non-aktif
            choice_map[3]="disabled"
            options+=("4) Lihat Log Statis")
            choice_map[4]="view_static_log"
            options+=("5) ${C_MAGENTA}Keluar${C_RESET}")
            choice_map[5]="exit"
            local max_choice=5
        else # Listener Tidak Aktif
            options+=("1) ${C_GREEN}Mulai Listener${C_RESET}")
            choice_map[1]="start_listener"
            options+=("2) Pengaturan")
            choice_map[2]="configure_settings"
            options+=("3) Lihat Log Statis")
            choice_map[3]="view_static_log"
            options+=("4) ${C_MAGENTA}Keluar${C_RESET}")
            choice_map[4]="exit"
            local max_choice=4
        fi

        # Tampilkan opsi
        for opt in "${options[@]}"; do
            printf "   %s\n" "$opt"
        done
        printf "\n"

        # --- Input Pilihan ---
        local choice=""
        while true; do
            read -p "$(printf "${C_YELLOW}Masukkan pilihan Anda (1-${max_choice}): ${C_RESET}")" choice
            # Validasi: harus angka dan dalam rentang
            if [[ "$choice" =~ ^[1-9][0-9]*$ && "$choice" -ge 1 && "$choice" -le "$max_choice" ]]; then
                 # Cek apakah pilihan valid (bukan yg disabled)
                 if [[ "${choice_map[$choice]}" == "disabled" ]]; then
                      printf "${C_RED}Opsi ini tidak tersedia saat listener aktif. Hentikan listener dulu.${C_RESET}\n"
                 else
                      break # Pilihan valid
                 fi
            else
                 printf "${C_RED}Pilihan tidak valid. Masukkan angka antara 1 dan ${max_choice}.${C_RESET}\n"
            fi
        done

        # --- Proses Pilihan ---
        local action="${choice_map[$choice]}"

        case "$action" in
            "show_live_log") show_live_log ;;
            "stop_listener") stop_listener ;;
            "start_listener")
                start_listener
                # Jika start berhasil, mungkin langsung tampilkan log?
                if is_listener_running; then
                     sleep 1 # Beri waktu sedikit
                     show_live_log
                fi
                ;;
            "configure_settings") configure_settings ;;
            "view_static_log") view_static_log ;;
            "exit")
                clear
                if is_listener_running; then
                    printf "${C_YELLOW}Menghentikan listener sebelum keluar...${C_RESET}\n"
                    stop_listener # Panggil fungsi stop yg sudah ada
                fi
                printf "\n${C_BOLD}${C_MAGENTA}Terima kasih telah menggunakan Email Trader Bot! Script dihentikan.${C_RESET}\n\n"
                log_message "--- Script Dihentikan via Menu Keluar ---"
                exit 0
                ;;
            *)
                # Seharusnya tidak terjadi karena validasi di atas
                error_msg "Terjadi kesalahan internal pada pemilihan menu."
                ;;
        esac

        # Tidak perlu pause_and_clear di sini, karena setiap fungsi aksi sudah handle clear/pause jika perlu
        # Loop akan clear layar lagi

    done
}

# --- Main Program Execution ---

# Setup trap untuk exit bersih (lebih penting di CLI tanpa dialog)
cleanup() {
    local exit_code=$?
    # Pastikan kursor terlihat dan warna reset jika keluar tiba2
    printf "${C_RESET}"
    # tput cnorm # Pastikan kursor terlihat (jika terminal mendukung)

    # Jangan clear layar di sini agar pesan error terakhir terlihat
    echo # Newline after potential Ctrl+C char

    # Hanya log jika bukan exit normal dari menu
    if [[ "$exit_code" != "0" ]]; then
        log_message "--- Script Menerima Sinyal Exit (Code: $exit_code) ---"
        if is_listener_running; then
            echo "${C_YELLOW} Sinyal interupsi diterima. Menghentikan listener (PID: $LISTENER_PID) paksa...${C_RESET}"
            # Kirim sinyal langsung, jangan panggil fungsi stop_listener yg interaktif
            kill -TERM "$LISTENER_PID" &> /dev/null
            sleep 0.5
            kill -KILL "$LISTENER_PID" &> /dev/null # Pastikan berhenti
            rm -f "$PID_FILE" # Hapus PID file saat keluar paksa
            echo "${C_GREEN} Listener dihentikan.${C_RESET}"
            log_message "Listener (PID: $LISTENER_PID) dihentikan paksa saat script exit (Sinyal: $exit_code)."
        fi
        echo "${C_RED} Script dihentikan secara tidak normal (Sinyal: $exit_code).${C_RESET}"
    fi
    # Keluar dengan kode yang sesuai (130 untuk Ctrl+C)
    exit "$exit_code"
}
# Tangkap SIGINT (Ctrl+C), SIGTERM, dan EXIT (termasuk exit 0 normal)
# EXIT trap akan jalan terakhir
trap cleanup SIGINT SIGTERM EXIT

# --- Start Script ---
clear
printf "${C_BOLD}${C_CYAN}Memulai Email Trader Bot v1.5...${C_RESET}\n"
sleep 1 # Sedikit delay biar keliatan keren

check_deps
log_message "--- Script Email Trader v1.5 Dimulai (PID: $$) ---"

# Cek status listener saat startup
is_listener_running
if [[ -n "$LISTENER_PID" ]]; then
    log_message "INFO: Script dimulai, listener dari sesi sebelumnya terdeteksi aktif (PID: $LISTENER_PID)."
    printf "${C_YELLOW}INFO: Listener dari sesi sebelumnya terdeteksi aktif (PID: $LISTENER_PID).${C_RESET}\n"
    sleep 1
fi

# Coba load konfigurasi, jika gagal dan listener TIDAK aktif, paksa konfigurasi
if ! load_config; then
    if ! is_listener_running; then
        clear
        printf "\n${C_BOLD}${C_YELLOW}==================== PERHATIAN ====================${C_RESET}\n"
        printf "${C_YELLOW}File konfigurasi (${C_CYAN}${CONFIG_FILE}${C_YELLOW}) tidak ditemukan atau tidak lengkap.\n"
        printf "${C_YELLOW}Anda akan diarahkan ke menu konfigurasi.${C_RESET}\n"
        printf "${C_BOLD}${C_YELLOW}===================================================${C_RESET}\n\n"
        pause_and_clear

        if ! configure_settings; then
            clear
            printf "\n${C_BOLD}${C_RED}Konfigurasi awal dibatalkan atau gagal. Script tidak dapat dilanjutkan.${C_RESET}\n\n"
            log_message "FATAL: Konfigurasi awal gagal. Script berhenti."
            exit 1 # Langsung exit, trap EXIT akan jalan
        fi
        # Coba load lagi setelah konfigurasi berhasil
        if ! load_config; then
            clear
            printf "\n${C_BOLD}${C_RED}Gagal memuat konfigurasi bahkan setelah setup awal. Script berhenti.${C_RESET}\n\n"
            log_message "FATAL: Gagal memuat konfigurasi setelah setup. Script berhenti."
            exit 1 # Langsung exit, trap EXIT akan jalan
        fi
    else
        # Jika config gagal load TAPI listener JALAN, ini kondisi aneh.
        # Mungkin file config dihapus saat listener jalan. Beri warning.
        log_message "WARNING: Konfigurasi gagal dimuat, tapi listener sedang aktif. Pengaturan tidak bisa diakses sampai listener dihentikan dan file config diperbaiki/dibuat ulang."
        printf "\n${C_BOLD}${C_RED}WARNING:${C_RESET} ${C_YELLOW}Konfigurasi gagal dimuat (${CONFIG_FILE}), tapi listener (PID: ${LISTENER_PID}) sedang aktif.${C_RESET}\n"
        printf "${C_YELLOW}Menu Pengaturan tidak akan bisa diakses.${C_RESET}\n"
        printf "${C_YELLOW}Anda mungkin perlu menghentikan listener dan memperbaiki/membuat ulang file konfigurasi.${C_RESET}\n\n"
        pause_and_clear
    fi
fi

# --- Jalankan Menu Utama ---
main_menu

# Exit normal seharusnya ditangani oleh pilihan 'Keluar' di main_menu atau trap EXIT
exit 0
