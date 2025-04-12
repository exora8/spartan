#!/usr/bin/env bash

# Script Email Listener & Binance Trader
# Versi: 1.5 (Fixed UI Glitch from Background Output, Binance Param Fix)
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

# --- Fungsi ---

# Fungsi untuk menampilkan pesan error dengan dialog
error_msg() {
    clear
    dialog --title "Error" --msgbox "$1" 8 60
    log_message "ERROR_DIALOG: $1"
}

# Fungsi untuk menampilkan info dengan dialog
info_msg() {
    clear
    dialog --title "Info" --msgbox "$1" 8 60
}

# Fungsi cek dependensi
check_deps() {
    local missing_deps=()
    # Tambahkan jq untuk parsing JSON response Binance
    for cmd in dialog neomutt curl openssl jq grep sed awk cut date mktemp tail wc kill sleep wait clear pgrep; do
        if ! command -v "$cmd" &> /dev/null; then
            missing_deps+=("$cmd")
        fi
    done
    if ! command -v neomutt &> /dev/null && ! command -v mutt &> /dev/null; then
         missing_deps+=("neomutt atau mutt")
    fi
    if [ ${#missing_deps[@]} -ne 0 ]; then
        echo "ERROR: Dependensi berikut tidak ditemukan atau tidak ada di PATH:" >&2
        printf " - %s\n" "${missing_deps[@]}" >&2
        echo "Silakan install terlebih dahulu sebelum menjalankan script." >&2
        if command -v dialog &> /dev/null; then
            dialog --title "Error Dependensi" --cr-wrap --msgbox "Dependensi berikut tidak ditemukan:\n\n$(printf -- '- %s\n' "${missing_deps[@]}")\n\nSilakan install terlebih dahulu." 15 70
        fi
        exit 1
    fi
    EMAIL_CLIENT=$(command -v neomutt || command -v mutt)
}

# Fungsi load konfigurasi
load_config() {
    if [ -f "$CONFIG_FILE" ]; then
        chmod 600 "$CONFIG_FILE" # Pastikan permission benar saat load
        GMAIL_USER=$(grep -Po "^GMAIL_USER *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        GMAIL_APP_PASS=$(grep -Po "^GMAIL_APP_PASS *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        BINANCE_API_KEY=$(grep -Po "^BINANCE_API_KEY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        BINANCE_SECRET_KEY=$(grep -Po "^BINANCE_SECRET_KEY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        TRADE_SYMBOL=$(grep -Po "^TRADE_SYMBOL *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        TRADE_QUANTITY=$(grep -Po "^TRADE_QUANTITY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        CHECK_INTERVAL=$(grep -Po "^CHECK_INTERVAL *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)

        # Default check interval jika tidak ada di config
        CHECK_INTERVAL="${CHECK_INTERVAL:-60}"

        if [[ -z "$GMAIL_USER" || -z "$GMAIL_APP_PASS" || -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$TRADE_SYMBOL" || -z "$TRADE_QUANTITY" || -z "$CHECK_INTERVAL" ]]; then
            log_message "WARNING: File konfigurasi $CONFIG_FILE ada tapi tidak lengkap atau gagal parse."
            return 1
        fi
        # Validasi sederhana setelah load
        if ! [[ "$CHECK_INTERVAL" =~ ^[1-9][0-9]*$ ]]; then
            log_message "WARNING: CHECK_INTERVAL '$CHECK_INTERVAL' di config tidak valid. Menggunakan default 60."
            CHECK_INTERVAL=60
        fi
         if ! [[ "$TRADE_QUANTITY" =~ ^[+]?([0-9]+(\.[0-9]*)?|\.[0-9]+)$ && "$TRADE_QUANTITY" != "0" && "$TRADE_QUANTITY" != "0.0" ]]; then
            log_message "WARNING: TRADE_QUANTITY '$TRADE_QUANTITY' di config tidak valid. Trading mungkin gagal."
            # Tidak return 1, biarkan user menyadari via log/error Binance
        fi

        log_message "Konfigurasi berhasil dimuat dari $CONFIG_FILE."
        return 0
    else
        log_message "INFO: File konfigurasi $CONFIG_FILE tidak ditemukan."
        return 1
    fi
}

# Fungsi simpan konfigurasi
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
    info_msg "Konfigurasi berhasil disimpan di $CONFIG_FILE"
}

# Fungsi konfigurasi interaktif (Password/Secret Key visible)
configure_settings() {
    # Cek jika listener sedang jalan, jangan biarkan konfigurasi diubah
    if is_listener_running; then
        error_msg "Listener sedang aktif (PID: $LISTENER_PID). Hentikan listener terlebih dahulu sebelum mengubah konfigurasi."
        return 1
    fi

    # Muat nilai saat ini jika ada, atau gunakan string kosong jika gagal
    load_config || true

    local temp_gmail_user="${GMAIL_USER:-}"
    local temp_gmail_pass="${GMAIL_APP_PASS:-}"
    local temp_api_key="${BINANCE_API_KEY:-}"
    local temp_secret_key="${BINANCE_SECRET_KEY:-}"
    local temp_symbol="${TRADE_SYMBOL:-}"
    local temp_quantity="${TRADE_QUANTITY:-}"
    local temp_interval="${CHECK_INTERVAL:-60}"

    local input_gmail_user input_gmail_pass input_api_key input_secret_key input_symbol input_quantity input_interval exit_status

    # --- Input Fields with Clear ---
    clear
    input_gmail_user=$(dialog --stdout --title "Konfigurasi" --inputbox "Alamat Gmail Anda:" 8 60 "$temp_gmail_user")
    exit_status=$?
    [[ $exit_status -ne 0 ]] && { info_msg "Konfigurasi dibatalkan."; return 1; }

    clear
    # --- Inputbox untuk password agar visible ---
    input_gmail_pass=$(dialog --stdout --title "Konfigurasi" --inputbox "Gmail App Password Anda (Bukan Password Utama!):" 8 70 "$temp_gmail_pass")
    exit_status=$?
    [[ $exit_status -ne 0 ]] && { info_msg "Konfigurasi dibatalkan."; return 1; }

    clear
    input_api_key=$(dialog --stdout --title "Konfigurasi" --inputbox "Binance API Key Anda:" 8 70 "$temp_api_key")
    exit_status=$?
    [[ $exit_status -ne 0 ]] && { info_msg "Konfigurasi dibatalkan."; return 1; }

    clear
    # --- Inputbox untuk secret key agar visible ---
    input_secret_key=$(dialog --stdout --title "Konfigurasi" --inputbox "Binance Secret Key Anda:" 8 70 "$temp_secret_key")
    exit_status=$?
    [[ $exit_status -ne 0 ]] && { info_msg "Konfigurasi dibatalkan."; return 1; }

    clear
    input_symbol=$(dialog --stdout --title "Konfigurasi" --inputbox "Simbol Trading (contoh: BTCUSDT):" 8 60 "$temp_symbol")
    exit_status=$?
    [[ $exit_status -ne 0 ]] && { info_msg "Konfigurasi dibatalkan."; return 1; }

    clear
    input_quantity=$(dialog --stdout --title "Konfigurasi" --inputbox "Jumlah Quantity Trading (contoh: 0.001):" 8 60 "$temp_quantity")
    exit_status=$?
    [[ $exit_status -ne 0 ]] && { info_msg "Konfigurasi dibatalkan."; return 1; }

    clear
    input_interval=$(dialog --stdout --title "Konfigurasi" --inputbox "Interval Cek Email (detik, contoh: 60):" 8 60 "$temp_interval")
    exit_status=$?
    [[ $exit_status -ne 0 ]] && { info_msg "Konfigurasi dibatalkan."; return 1; }

    # Validasi input dasar
    if [[ -z "$input_gmail_user" || -z "$input_gmail_pass" || -z "$input_api_key" || -z "$input_secret_key" || -z "$input_symbol" || -z "$input_quantity" || -z "$input_interval" ]]; then
         error_msg "Semua field konfigurasi harus diisi."
         return 1
    fi
    if ! [[ "$input_interval" =~ ^[1-9][0-9]*$ ]]; then
        error_msg "Interval cek email harus berupa angka positif (detik)."
        return 1
     fi
     if ! [[ "$input_quantity" =~ ^[+]?([0-9]+(\.[0-9]*)?|\.[0-9]+)$ && "$input_quantity" != "0" && "$input_quantity" != "0.0" ]]; then
        error_msg "Quantity trading harus berupa angka positif (misal: 0.001 atau 10)."
        return 1
     fi

    # Update variabel global
    GMAIL_USER="$input_gmail_user"
    GMAIL_APP_PASS="$input_gmail_pass"
    BINANCE_API_KEY="$input_api_key"
    BINANCE_SECRET_KEY="$input_secret_key"
    TRADE_SYMBOL=$(echo "$input_symbol" | tr 'a-z' 'A-Z') # Pastikan uppercase
    TRADE_QUANTITY="$input_quantity"
    CHECK_INTERVAL="$input_interval"

    save_config
    return 0
}

# Fungsi untuk logging ke file
log_message() {
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    # Tambahkan PID jika ada
    local pid_info=""
    # Hanya log PID dari proses background (jika $$ berbeda dari SCRIPT_MAIN_PID)
    if [[ -n "$$" && "$$" != "$SCRIPT_MAIN_PID" ]]; then
       pid_info=" [PID $$]"
    fi
    # Pastikan LOG_FILE punya nilai fallback jika belum diset saat awal
    echo "[$timestamp]$pid_info $1" >> "${LOG_FILE:-/tmp/email_trader_fallback.log}"
}

# --- Fungsi Background Listener ---

# Fungsi cek email baru yang cocok
check_email() {
    # Variabel ini akan di-export ke sub-proses oleh listener_loop
    log_message "Mencari email baru dari $GMAIL_USER dengan identifier: '$EMAIL_IDENTIFIER'"
    local email_body_file
    # Arahkan stderr mktemp ke log juga
    email_body_file=$(mktemp 2>>"$LOG_FILE") || { log_message "ERROR: Gagal membuat file temporary untuk email."; return 1; }

    # Jalankan Neomutt/Mutt
    # Redirect stdout/stderr ke /dev/null karena kita tidak butuh output langsungnya di sini
    # Kita hanya peduli exit code dan isi file $email_body_file
    "$EMAIL_CLIENT" \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail="" imap_check_subscribed=no' \
        -e 'push "<limit>~U (~b \"'${EMAIL_IDENTIFIER}'\" | ~s \"'${EMAIL_IDENTIFIER}'\")\n<pipe-message>cat > '${email_body_file}'\n<exit>"' > /dev/null 2>&1
        # ~U: Limit ke email yang belum dibaca (Unread)
    local mutt_exit_code=$?

    # Hanya log error jika exit code bukan 0 (sukses) atau 1 (tidak ada email baru yg cocok)
    if [[ $mutt_exit_code -ne 0 && $mutt_exit_code -ne 1 ]]; then
        log_message "WARNING: Perintah $EMAIL_CLIENT keluar dengan kode $mutt_exit_code (Mungkin error koneksi, password salah, atau query salah)"
    fi

    if [ -s "$email_body_file" ]; then
        log_message "Email yang cocok ditemukan (belum dibaca). Memproses..."
        parse_email_body "$email_body_file"
        local parse_status=$?
        rm "$email_body_file" # Hapus file temp setelah selesai
        if [ $parse_status -eq 0 ]; then
             # Jika parsing & eksekusi berhasil, tandai email dibaca
             mark_email_as_read
        else
             log_message "Action tidak ditemukan atau gagal parse/eksekusi, email TIDAK ditandai dibaca."
        fi
        return 0 # Email ditemukan dan diproses (berhasil atau gagal prosesnya)
    else
        # Jika exit code 0 atau 1 tapi file kosong, berarti tidak ada email *belum dibaca* yang cocok
        log_message "Tidak ada email baru (belum dibaca) yang cocok ditemukan."
        rm "$email_body_file" # Hapus file temp kosong
        return 1 # Tidak ada email yang cocok
    fi
}

# Fungsi parsing body email
parse_email_body() {
    local body_file="$1"
    log_message "Parsing isi email dari $body_file"
    local action=""

    # Perbaiki grep agar case-insensitive (-i) dan hanya match kata utuh (-w)
    # Arahkan stderr ke log jika grep error (jarang terjadi tapi best practice)
    if grep -qiw "buy" "$body_file" 2>>"$LOG_FILE"; then
        action="BUY"
    elif grep -qiw "sell" "$body_file" 2>>"$LOG_FILE"; then
        action="SELL"
    fi

    # Cek identifier lagi untuk keamanan ganda (Optional, karena filter mutt sudah ada)
    # Jika filter mutt sudah sangat spesifik, ini mungkin tidak perlu
    # if ! grep -qF "$EMAIL_IDENTIFIER" "$body_file" 2>>"$LOG_FILE"; then
    #     log_message "WARNING: Action '$action' terdeteksi, tapi identifier '$EMAIL_IDENTIFIER' tidak ditemukan di body email ini. Mengabaikan."
    #     return 1 # Gagal Parse
    # fi

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

# Fungsi untuk menandai email sebagai sudah dibaca
mark_email_as_read() {
    log_message "Menandai email sebagai sudah dibaca..."
    # Targetkan email yang *persis sama* dengan yang baru saja diproses
    # Ini lebih aman daripada menandai semua yg belum dibaca jika ada >1 email masuk bersamaan
    # Kita pakai query yang sama (~U: Unread, dengan identifier) dan flag N (New/Recent)
    "$EMAIL_CLIENT" \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail="" imap_check_subscribed=no' \
        -e 'push "<limit>~U (~b \"'${EMAIL_IDENTIFIER}'\" | ~s \"'${EMAIL_IDENTIFIER}'\")\n<clear-flag>N\n<sync-mailbox><exit>"' > /dev/null 2>&1
        # <clear-flag>N : Menghapus flag 'New' (efektif menandai sebagai 'read')
        # <sync-mailbox>: Memastikan perubahan disimpan di server IMAP
    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        log_message "Perintah untuk menandai email dibaca (menghapus flag 'New') telah dikirim."
    elif [ $exit_code -eq 1 ]; then
        log_message "INFO: Tidak ada email 'New' yang cocok untuk ditandai dibaca saat ini (mungkin sudah dibaca oleh proses lain atau race condition)."
    else
        log_message "WARNING: Perintah $EMAIL_CLIENT untuk menandai email dibaca mungkin gagal (exit code: $exit_code)."
    fi
}

# Fungsi generate signature Binance
generate_binance_signature() {
    local query_string="$1"
    local secret="$2"
    # Arahkan stderr openssl ke log
    echo -n "$query_string" | openssl dgst -sha256 -hmac "$secret" 2>>"$LOG_FILE" | sed 's/^.* //'
}

# Fungsi eksekusi order Binance
execute_binance_order() {
    local side="$1"
    local timestamp
    timestamp=$(date +%s%3N) # Timestamp milidetik untuk Binance
    if [[ -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$TRADE_SYMBOL" || -z "$TRADE_QUANTITY" ]]; then
        log_message "ERROR: Konfigurasi Binance tidak lengkap. Tidak bisa membuat order."
        return 1
    fi

    local api_endpoint="https://api.binance.com" # Gunakan api.binance.com (global) atau sesuaikan jika perlu (api1/2/3)
    local order_path="/api/v3/order"
    # Perbaiki: Gunakan '&' sebagai pemisah parameter URL
    local params="symbol=${TRADE_SYMBOL}&side=${side}&type=MARKET&quantity=${TRADE_QUANTITY}×tamp=${timestamp}"
    local signature
    signature=$(generate_binance_signature "$params" "$BINANCE_SECRET_KEY")
    if [ -z "$signature" ]; then
        log_message "ERROR: Gagal menghasilkan signature Binance. Periksa error openssl di log."
        return 1
    fi

    # Gabungkan URL, parameter, dan signature
    local full_url="${api_endpoint}${order_path}?${params}&signature=${signature}"
    log_message "Mengirim order ke Binance: SIDE=$side SYMBOL=$TRADE_SYMBOL QTY=$TRADE_QUANTITY"
    # Uncomment untuk debug URL lengkap (hati-hati dengan secret key di log!)
    # log_message "DEBUG: Full URL (tanpa API Key header): $full_url"

    local response curl_exit_code http_code body
    # Tambahkan timeout ke curl dan minta error verbose jika gagal (-v bisa berisik)
    # Arahkan stderr curl ke log file
    response=$(curl --connect-timeout 10 --max-time 20 -s -w "\nHTTP_CODE:%{http_code}" -H "X-MBX-APIKEY: ${BINANCE_API_KEY}" -X POST "$full_url" 2>>"$LOG_FILE")
    curl_exit_code=$?

    # Ekstrak HTTP code dan body dari response
    http_code=$(echo "$response" | grep "^HTTP_CODE:" | cut -d':' -f2)
    body=$(echo "$response" | sed '$d') # Hapus baris terakhir (HTTP_CODE)

    if [ $curl_exit_code -ne 0 ]; then
        log_message "ERROR: curl gagal menghubungi Binance (Curl Exit code: $curl_exit_code). Cek log untuk detail stderr curl."
        return 1
    fi

    log_message "Response Binance (HTTP $http_code): $body"

    # Periksa HTTP status code
    if [[ "$http_code" =~ ^2 ]]; then # 2xx berarti sukses
        local orderId status clientOrderId fillPrice fillQty
        # Parse lebih aman pakai jq, handle jika jq gagal atau field tidak ada
        orderId=$(echo "$body" | jq -r '.orderId // empty' 2>>"$LOG_FILE")
        status=$(echo "$body" | jq -r '.status // "UNKNOWN"' 2>>"$LOG_FILE")
        clientOrderId=$(echo "$body" | jq -r '.clientOrderId // empty' 2>>"$LOG_FILE")
        # Untuk MARKET order, cek fills untuk harga dan qty aktual
        fillPrice=$(echo "$body" | jq -r 'if .fills? and (.fills | length > 0) then .fills[0].price else "N/A" end' 2>>"$LOG_FILE")
        fillQty=$(echo "$body" | jq -r 'if .fills? and (.fills | length > 0) then .fills[0].qty else "N/A" end' 2>>"$LOG_FILE")


        if [ -n "$orderId" ]; then
            log_message "SUCCESS: Order berhasil ditempatkan. Order ID: $orderId, Status: $status, Fill Price: $fillPrice, Fill Qty: $fillQty (Client ID: $clientOrderId)"
            # Di sini bisa ditambahkan notifikasi ke Telegram/Discord jika mau
            return 0
        else
            # Jika HTTP 2xx tapi tidak ada orderId (aneh, tapi mungkin terjadi)
            log_message "WARNING: HTTP $http_code diterima tapi tidak ada Order ID di response JSON. Body: $body"
            return 0 # Anggap sukses jika HTTP 2xx agar email ditandai dibaca
        fi
    else
        # Jika HTTP bukan 2xx (4xx, 5xx, dll)
        local err_code err_msg
        err_code=$(echo "$body" | jq -r '.code // "?"' 2>>"$LOG_FILE")
        err_msg=$(echo "$body" | jq -r '.msg // "Tidak ada pesan error spesifik"' 2>>"$LOG_FILE")
        log_message "ERROR: Gagal menempatkan order (HTTP $http_code). Kode Error Binance: $err_code Pesan: $err_msg"
        # Di sini bisa ditambahkan notifikasi GAGAL ke Telegram/Discord jika mau
        return 1 # Gagal
    fi
}

# Fungsi Loop Utama Listener (untuk dijalankan di background)
listener_loop() {
    # Pastikan variabel konfigurasi di-export agar terbaca oleh sub-shell/proses background
    # Export variabel yang dibutuhkan oleh check_email, parse_email_body, execute_binance_order, mark_email_as_read
    export GMAIL_USER GMAIL_APP_PASS BINANCE_API_KEY BINANCE_SECRET_KEY \
           TRADE_SYMBOL TRADE_QUANTITY EMAIL_IDENTIFIER EMAIL_CLIENT LOG_FILE \
           SCRIPT_MAIN_PID # Export SCRIPT_MAIN_PID agar log_message bisa bedakan

    # Dapatkan interval dari environment (sudah di-export oleh start_listener jika pakai metode subshell)
    # atau load lagi jika perlu (tapi export lebih baik)
    local check_interval="${CHECK_INTERVAL:-60}" # Fallback jika export gagal
    if ! [[ "$check_interval" =~ ^[1-9][0-9]*$ ]]; then
        log_message "[LISTENER LOOP] WARNING: Interval cek email tidak valid ($check_interval). Menggunakan default 60 detik."
        check_interval=60
    fi

    # Trap sinyal di dalam loop background agar bisa exit bersih
    trap 'log_message "[LISTENER LOOP] Listener loop (PID $$) dihentikan oleh sinyal."; exit 0' SIGTERM SIGINT

    log_message "[LISTENER LOOP] Listener loop dimulai (PID $$). Interval: ${check_interval} detik. Output diarahkan ke $LOG_FILE"
    while true; do
        log_message "[LISTENER LOOP] Memulai siklus pengecekan email..."
        # Fungsi check_email akan memanggil parse_email -> execute_order -> mark_read
        check_email
        # Tidak perlu cek return code di sini, log sudah ada di dalam check_email/sub-fungsi
        log_message "[LISTENER LOOP] Siklus selesai. Menunggu ${check_interval} detik..."
        sleep "$check_interval"

        # Log rotation/trimming sederhana
        local max_log_lines=1000
        local current_lines
        current_lines=$(wc -l < "$LOG_FILE" 2>/dev/null) # Redirect error wc jika file tidak ada
        if [[ "$current_lines" =~ ^[0-9]+$ && "$current_lines" -gt "$max_log_lines" ]]; then
             log_message "[LISTENER LOOP] INFO: File log ($LOG_FILE) dipangkas ke $max_log_lines baris terakhir."
             # Cara pangkas yang lebih aman dan handle error
             local temp_log="${LOG_FILE}.tmp.$$"
             tail -n "$max_log_lines" "$LOG_FILE" > "$temp_log" 2>/dev/null
             if [ $? -eq 0 ]; then
                 mv "$temp_log" "$LOG_FILE" 2>/dev/null
                 if [ $? -ne 0 ]; then
                     log_message "[LISTENER LOOP] WARNING: Gagal memindahkan log sementara ke log utama."
                     rm -f "$temp_log" # Clean up temp file on failure
                 fi
             else
                 log_message "[LISTENER LOOP] WARNING: Gagal membuat log sementara dari tail."
                 rm -f "$temp_log" # Clean up temp file on failure
             fi
        elif ! [[ "$current_lines" =~ ^[0-9]+$ ]]; then
             # Jangan log error jika file log baru saja dibuat / masih kosong
             if [ -f "$LOG_FILE" ]; then
                log_message "[LISTENER LOOP] WARNING: Gagal mendapatkan jumlah baris log (output wc: '$current_lines')."
             fi
        fi
    done
}

# --- Fungsi Kontrol Listener ---

# Cek apakah listener sedang berjalan
is_listener_running() {
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE")
        # Cek apakah pid numerik dan prosesnya ada
        if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
            LISTENER_PID="$pid" # Update variabel global
            return 0 # Sedang berjalan
        else
            # PID file ada tapi proses tidak jalan (atau pid tidak valid), hapus file PID basi
            log_message "INFO: File PID ditemukan ($PID_FILE, PID: $pid) tapi proses tidak berjalan atau PID tidak valid. Menghapus file PID."
            rm -f "$PID_FILE"
            LISTENER_PID=""
            return 1 # Tidak berjalan
        fi
    else
        LISTENER_PID=""
        return 1 # Tidak berjalan (file PID tidak ada)
    fi
}

# Memulai listener
start_listener() {
    if is_listener_running; then
        error_msg "Listener sudah berjalan (PID: $LISTENER_PID)."
        return 1
    fi

    if ! load_config; then
        error_msg "Konfigurasi belum lengkap atau gagal dimuat. Tidak bisa memulai listener. Silakan cek Pengaturan."
        return 1
    fi

    # Export variabel yang dibutuhkan oleh listener_loop SEBELUM memulai subshell
    export GMAIL_USER GMAIL_APP_PASS BINANCE_API_KEY BINANCE_SECRET_KEY \
           TRADE_SYMBOL TRADE_QUANTITY CHECK_INTERVAL EMAIL_IDENTIFIER \
           EMAIL_CLIENT LOG_FILE SCRIPT_MAIN_PID

    log_message "Memulai listener di background..."
    # Jalankan listener_loop di background
    # Arahkan SEMUA stdout (1) dan stderr (2) dari subshell ke LOG_FILE
    # Ini mencegah output listener bocor ke terminal utama dan mengganggu dialog
    (listener_loop >> "$LOG_FILE" 2>&1) &
    local pid=$!

    # Beri sedikit waktu untuk memastikan proses benar-benar start sebelum cek PID
    sleep 0.5

    # Cek apakah proses background berhasil dimulai
    if ! kill -0 "$pid" 2>/dev/null; then
        log_message "ERROR: Proses listener (PID $pid) gagal dimulai atau langsung exit. Cek $LOG_FILE untuk detail."
        error_msg "Gagal memulai proses listener. Cek log."
        # Hapus file PID jika terlanjur dibuat (walaupun seharusnya belum)
        rm -f "$PID_FILE"
        return 1
    fi

    # Simpan PID ke file *setelah* memastikan proses berjalan
    echo "$pid" > "$PID_FILE"
    if [ $? -ne 0 ]; then
       log_message "ERROR: Gagal menyimpan PID $pid ke $PID_FILE. Menghentikan listener..."
       # Coba hentikan proses yang mungkin berjalan
       kill "$pid" 2>/dev/null
       sleep 0.5
       kill -9 "$pid" 2>/dev/null
       error_msg "Gagal menyimpan file PID. Listener dihentikan."
       return 1
    fi

    LISTENER_PID="$pid"
    log_message "Listener berhasil dimulai di background (PID: $LISTENER_PID)."
    info_msg "Listener berhasil dimulai (PID: $LISTENER_PID). Log aktivitas bisa dilihat di menu."
    return 0
}


# Menghentikan listener
stop_listener() {
    if ! is_listener_running; then
        # Jika LISTENER_PID masih ada nilainya tapi is_listener_running false, berarti PID basi
        if [[ -n "$LISTENER_PID" ]]; then
             log_message "INFO: Mencoba menghentikan listener, tapi proses PID $LISTENER_PID sudah tidak berjalan. Membersihkan..."
             rm -f "$PID_FILE"
             LISTENER_PID=""
        fi
        error_msg "Listener tidak sedang berjalan."
        return 1
    fi

    log_message "Mengirim sinyal TERM ke listener (PID: $LISTENER_PID)..."
    if kill -TERM "$LISTENER_PID" 2>/dev/null; then
        local count=0
        local max_wait=10 # Tunggu maksimal 5 detik (10 * 0.5s)
        log_message "Menunggu listener (PID: $LISTENER_PID) berhenti..."
        while kill -0 "$LISTENER_PID" 2>/dev/null; do
            ((count++))
            if [ "$count" -gt $max_wait ]; then
                log_message "WARNING: Listener (PID: $LISTENER_PID) tidak berhenti dengan TERM setelah $(($max_wait / 2)) detik. Mengirim KILL."
                kill -KILL "$LISTENER_PID" 2>/dev/null
                # Beri jeda sedikit setelah KILL
                sleep 0.5
                break
            fi
            sleep 0.5
        done

        # Cek lagi setelah loop/KILL
        if ! kill -0 "$LISTENER_PID" 2>/dev/null; then
            log_message "Listener (PID: $LISTENER_PID) berhasil dihentikan."
            info_msg "Listener (PID: $LISTENER_PID) berhasil dihentikan."
            # Hapus file PID hanya jika berhasil berhenti
            rm -f "$PID_FILE"
            LISTENER_PID=""
            return 0
        else
            log_message "ERROR: Gagal menghentikan listener (PID: $LISTENER_PID) bahkan dengan KILL."
            error_msg "Gagal menghentikan listener (PID: $LISTENER_PID). Cek proses manual."
            # Jangan hapus PID file jika gagal kill, agar user tahu PID nya
            return 1 # Gagal berhenti
        fi
    else
        log_message "WARNING: Gagal mengirim sinyal TERM ke PID $LISTENER_PID (mungkin sudah berhenti tepat sebelum kill). Memeriksa ulang..."
        # Cek lagi apakah prosesnya benar-benar hilang
        if ! kill -0 "$LISTENER_PID" 2>/dev/null; then
            log_message "INFO: Proses $LISTENER_PID memang sudah tidak berjalan. Membersihkan PID file."
            rm -f "$PID_FILE"
            LISTENER_PID=""
            info_msg "Listener sudah berhenti."
            return 0
        else
            log_message "ERROR: Gagal mengirim TERM tapi proses $LISTENER_PID masih berjalan. Aneh."
            error_msg "Gagal mengirim sinyal ke listener (PID: $LISTENER_PID) tapi proses masih ada."
            return 1 # Gagal
        fi
    fi
}

# Menampilkan log real-time
show_live_log() {
     # Cek file log ada atau tidak
     if [ ! -f "$LOG_FILE" ]; then
        error_msg "File log ($LOG_FILE) belum ada."
        return 1
     fi
     # Cek status listener untuk info judul
     is_listener_running
     local title_status="Statis"
     if [[ -n "$LISTENER_PID" ]]; then
         title_status="Real-time (Listener PID: $LISTENER_PID)"
     fi
     clear
     # Gunakan tailboxbg agar bisa scroll dan update otomatis
     # --no-kill penting agar menutup dialog tidak mencoba kill 'tail'
     dialog --title "Email Listener - Log $title_status" \
            --no-kill \
            --tailboxbg "$LOG_FILE" 25 90
     log_message "Menutup tampilan log (listener tetap berjalan jika aktif)."
     clear # Bersihkan layar setelah dialog ditutup
}

# Fungsi Tampilkan Log Statis (sekarang pakai show_live_log juga)
view_static_log() {
    show_live_log # Kita bisa pakai fungsi yang sama, tailboxbg bagus untuk lihat log statis juga
}

# --- Fungsi Menu Utama ---
main_menu() {
    while true; do
        clear
        # Selalu update status listener setiap kali loop menu
        is_listener_running

        local listener_status_msg=""
        local menu_items=()
        local choice_map=() # Untuk mapping nomor pilihan ke action

        if [[ -n "$LISTENER_PID" ]]; then
            # Listener Aktif
            listener_status_msg=" (Listener Aktif - PID: $LISTENER_PID)"
            menu_items+=("1" "Lihat Log Listener (Real-time)" \
                         "2" "Hentikan Listener" \
                         "3" "Pengaturan (Nonaktif)" \
                         "4" "Lihat Log Statis" \
                         "5" "Keluar")
            choice_map[1]="show_live_log"
            choice_map[2]="stop_listener"
            choice_map[3]="disabled_settings"
            choice_map[4]="view_static_log"
            choice_map[5]="exit_script"
        else
            # Listener Tidak Aktif
            listener_status_msg=" (Listener Tidak Aktif)"
            menu_items+=("1" "Mulai Listener" \
                         "2" "Pengaturan" \
                         "3" "Lihat Log Statis" \
                         "4" "Keluar")
            choice_map[1]="start_listener_and_log" # Aksi gabungan
            choice_map[2]="configure_settings"
            choice_map[3]="view_static_log"
            choice_map[4]="exit_script"
        fi

        CHOICE=$(dialog --clear --stdout \
                        --title "Email Trader v1.5 - Menu Utama$listener_status_msg" \
                        --cancel-label "Keluar" \
                        --menu "Pilih tindakan:" 17 70 6 "${menu_items[@]}")

        exit_status=$?

        # Handle Cancel atau Esc (dianggap keluar)
        if [ $exit_status -ne 0 ]; then
            action="exit_script"
        else
            # Ambil action dari map berdasarkan nomor pilihan
            action="${choice_map[$CHOICE]}"
            # Jika pilihan tidak ada di map (seharusnya tidak terjadi)
            if [[ -z "$action" ]]; then
                action="invalid_choice"
            fi
        fi

        # Eksekusi action
        case "$action" in
            show_live_log) show_live_log ;;
            stop_listener) stop_listener ;;
            disabled_settings) error_msg "Hentikan listener dulu untuk masuk ke Pengaturan." ;;
            view_static_log) view_static_log ;;
            start_listener_and_log)
                start_listener
                # Jika start berhasil, langsung tampilkan log
                if is_listener_running; then
                    sleep 1 # Beri waktu sedikit untuk listener mulai log
                    show_live_log
                fi
                ;;
            configure_settings) configure_settings ;;
            exit_script)
                clear
                if is_listener_running; then
                    echo "Menghentikan listener sebelum keluar..."
                    stop_listener # Coba hentikan dengan bersih
                    # Jika stop_listener gagal, trap akan force kill
                fi
                echo "Script dihentikan."
                log_message "--- Script Dihentikan via Menu Keluar ---"
                exit 0 # Exit normal
                ;;
            invalid_choice|*) error_msg "Pilihan tidak valid." ;;
        esac

        # Tidak perlu 'read' atau 'sleep' di sini, loop akan kembali menampilkan menu

    done
}

# --- Main Program Execution ---

SCRIPT_MAIN_PID=$$ # Simpan PID script utama untuk perbandingan di log_message

# Setup trap untuk exit bersih (Ctrl+C, kill)
cleanup() {
    local exit_code=$?
    # Pastikan kita tidak di dalam subshell listener saat cleanup
    if [[ "$$" == "$SCRIPT_MAIN_PID" ]]; then
        echo # Newline after potential Ctrl+C char
        log_message "--- Script Menerima Sinyal Exit (Code: $exit_code) di PID $$ ---"
        if is_listener_running; then
            echo " Membersihkan: Mengirim sinyal KILL paksa ke listener (PID: $LISTENER_PID)..."
            # Jangan panggil stop_listener di trap karena bisa kompleks dan deadlock
            # Cukup kirim sinyal kill paling kuat dan hapus PID file
            kill -KILL "$LISTENER_PID" 2>/dev/null
            rm -f "$PID_FILE"
            echo " Listener (PID: $LISTENER_PID) dihentikan paksa."
            log_message "Listener (PID: $LISTENER_PID) dihentikan paksa via trap cleanup."
        else
            log_message "Trap cleanup: Listener tidak terdeteksi berjalan."
        fi
        echo " Script selesai."
        clear
        # Exit dengan kode yang sesuai (130 untuk SIGINT/Ctrl+C)
        [[ "$exit_code" == "0" ]] && exit 0 || exit "$exit_code"
    fi
}
# Tangkap SIGINT (Ctrl+C), SIGTERM (kill), dan EXIT (exit normal)
# EXIT trap akan jalan terakhir setelah sinyal lain ditangani (jika tidak di-exit sebelumnya)
trap cleanup SIGINT SIGTERM EXIT

# --- Start Script ---
check_deps
log_message "--- Script Email Trader v1.5 Dimulai (PID: $$) ---"

# Cek status listener saat startup (mungkin ada dari sesi sebelumnya)
is_listener_running
if [[ -n "$LISTENER_PID" ]]; then
    log_message "INFO: Script dimulai, listener dari sesi sebelumnya terdeteksi aktif (PID: $LISTENER_PID)."
    # Tanyakan user mau diapakan listener lama?
    clear
    dialog --title "Listener Aktif Ditemukan" --yesno "Listener dari sesi sebelumnya (PID: $LISTENER_PID) terdeteksi aktif.\n\nApakah Anda ingin menghentikannya sekarang?" 10 70
    if [ $? -eq 0 ]; then # Jika user pilih Yes
        stop_listener
    else
        info_msg "Ok, listener sebelumnya (PID: $LISTENER_PID) dibiarkan berjalan. Anda bisa menghentikannya dari menu nanti."
    fi
fi

# Coba load config, jika gagal dan listener TIDAK aktif, paksa konfigurasi
if ! load_config; then
    if ! is_listener_running; then
        clear
        dialog --title "Setup Awal Diperlukan" \
            --msgbox "File konfigurasi ($CONFIG_FILE) tidak ditemukan atau tidak lengkap.\n\nAnda akan diarahkan ke menu konfigurasi." 10 70
        # Jika konfigurasi dibatalkan atau gagal, exit
        if ! configure_settings; then
            clear
            echo "Konfigurasi awal dibatalkan atau gagal. Script tidak dapat dilanjutkan."
            log_message "FATAL: Konfigurasi awal gagal. Script berhenti."
            exit 1
        fi
        # Coba load lagi setelah konfigurasi
        if ! load_config; then
            clear
            echo "Gagal memuat konfigurasi bahkan setelah setup awal. Script berhenti."
            log_message "FATAL: Gagal memuat konfigurasi setelah setup. Script berhenti."
            exit 1
        fi
    else
        # Config gagal load TAPI listener aktif (dari sesi lama?)
        log_message "WARNING: Konfigurasi gagal dimuat, tapi listener (PID: $LISTENER_PID) sedang aktif. Pengaturan tidak bisa diakses sampai listener dihentikan."
        info_msg "Konfigurasi gagal dimuat, tapi listener (PID: $LISTENER_PID) aktif. Hentikan listener untuk mengakses Pengaturan."
    fi
fi

# Masuk ke menu utama
main_menu

# Exit normal seharusnya ditangani oleh action "exit_script" atau trap EXIT
exit 0
