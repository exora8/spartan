#!/usr/bin/env bash

# Script Email Listener & Binance Trader
# Versi: 1.5 (Revisi Tampilan CLI & Log Handling)
# Author: [Nama Kamu/AI] & Kontributor

# --- Konfigurasi Awal ---
CONFIG_FILE="$HOME/.email_trader_rc"
LOG_FILE="/tmp/email_trader.log"
PID_FILE="/tmp/email_trader.pid" # File untuk menyimpan PID listener
SCRIPT_TITLE="Email Trader v1.5"

# Pastikan file log ada dan writable, buat jika belum ada
touch "$LOG_FILE" || { echo "ERROR: Tidak dapat membuat/mengakses file log: $LOG_FILE" >&2; exit 1; }
chmod 600 "$LOG_FILE" # Amankan log jika perlu (opsional tergantung environment)

# Identifier Email yang Dicari (Subject atau Body)
EMAIL_IDENTIFIER="Exora AI (V5 SPOT + SR Filter) (1M)" # Contoh, ganti sesuai kebutuhan

# --- Variabel Global ---
LISTENER_PID="" # Akan diisi dari PID_FILE saat script start
SCRIPT_MAIN_PID=$$ # Simpan PID script utama

# --- Fungsi Dialog & Pesan ---

# Wrapper untuk dialog dengan backtitle
_dialog() {
    dialog --backtitle "$SCRIPT_TITLE" "$@"
}

# Fungsi untuk menampilkan pesan error dengan dialog
error_msg() {
    log_message "ERROR_DIALOG: $1"
    _dialog --title "⛔ Error" --msgbox "$1" 10 60
}

# Fungsi untuk menampilkan info dengan dialog
info_msg() {
    _dialog --title "ℹ️ Info" --msgbox "$1" 10 60
}

# Fungsi untuk menampilkan pesan singkat non-blocking
infobox_msg() {
    _dialog --title "⏳ Proses" --infobox "$1" 5 50
    sleep 1 # Beri waktu user untuk membaca
}

# Fungsi untuk konfirmasi ya/tidak
confirm_msg() {
    _dialog --title "❓ Konfirmasi" --yesno "$1" 8 60
    return $? # Return 0 for Yes, 1 for No
}

# --- Fungsi Inti ---

# Fungsi cek dependensi
check_deps() {
    local missing_deps=()
    # Tambahkan jq untuk parsing JSON response Binance
    for cmd in dialog neomutt curl openssl jq grep sed awk cut date mktemp tail wc kill sleep clear pgrep wc; do
        if ! command -v "$cmd" &> /dev/null; then
            missing_deps+=("$cmd")
        fi
    done
    # Cek mutt atau neomutt
    if ! command -v neomutt &> /dev/null && ! command -v mutt &> /dev/null; then
         missing_deps+=("neomutt atau mutt")
    fi

    if [ ${#missing_deps[@]} -ne 0 ]; then
        local dep_list
        dep_list=$(printf -- '- %s\n' "${missing_deps[@]}")
        echo "ERROR: Dependensi berikut tidak ditemukan:" >&2
        echo "$dep_list" >&2
        echo "Silakan install terlebih dahulu." >&2
        # Cek apakah dialog ada untuk menampilkan pesan error
        if command -v dialog &> /dev/null; then
            _dialog --title "⛔ Error Dependensi" --msgbox "Dependensi berikut tidak ditemukan:\n\n$dep_list\n\nSilakan install terlebih dahulu sebelum menjalankan script." 15 70
        fi
        exit 1
    fi
    # Pilih email client yang tersedia
    EMAIL_CLIENT=$(command -v neomutt || command -v mutt)
}

# Fungsi load konfigurasi
load_config() {
    if [ -f "$CONFIG_FILE" ]; then
        chmod 600 "$CONFIG_FILE" # Pastikan permission benar
        # Source file untuk cara load yg lebih robust
        # Tapi grep lebih aman jika format tidak standar
        GMAIL_USER=$(grep -Po "^GMAIL_USER *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        GMAIL_APP_PASS=$(grep -Po "^GMAIL_APP_PASS *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        BINANCE_API_KEY=$(grep -Po "^BINANCE_API_KEY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        BINANCE_SECRET_KEY=$(grep -Po "^BINANCE_SECRET_KEY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        TRADE_SYMBOL=$(grep -Po "^TRADE_SYMBOL *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        TRADE_QUANTITY=$(grep -Po "^TRADE_QUANTITY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        CHECK_INTERVAL=$(grep -Po "^CHECK_INTERVAL *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)

        # Validasi dasar setelah load
        if [[ -z "$GMAIL_USER" || -z "$GMAIL_APP_PASS" || -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$TRADE_SYMBOL" || -z "$TRADE_QUANTITY" || -z "$CHECK_INTERVAL" ]]; then
            log_message "WARNING: File konfigurasi $CONFIG_FILE ada tapi tidak lengkap atau gagal parse."
            # Kosongkan variabel jika tidak lengkap agar check selanjutnya gagal
            GMAIL_USER="" GMAIL_APP_PASS="" BINANCE_API_KEY="" BINANCE_SECRET_KEY="" TRADE_SYMBOL="" TRADE_QUANTITY="" CHECK_INTERVAL=""
            return 1
        fi

        # Validasi tipe data lebih ketat saat load
        if ! [[ "$CHECK_INTERVAL" =~ ^[1-9][0-9]*$ ]]; then
            log_message "WARNING: Nilai CHECK_INTERVAL ('$CHECK_INTERVAL') di $CONFIG_FILE tidak valid. Harus angka positif."
            CHECK_INTERVAL="" # Reset agar load gagal
            return 1
        fi
         if ! [[ "$TRADE_QUANTITY" =~ ^[+]?([0-9]+(\.[0-9]*)?|\.[0-9]+)$ && $(bc <<< "$TRADE_QUANTITY > 0") -eq 1 ]]; then
             log_message "WARNING: Nilai TRADE_QUANTITY ('$TRADE_QUANTITY') di $CONFIG_FILE tidak valid. Harus angka desimal positif."
             TRADE_QUANTITY="" # Reset agar load gagal
             return 1
         fi

        log_message "Konfigurasi berhasil dimuat dari $CONFIG_FILE."
        CHECK_INTERVAL="${CHECK_INTERVAL:-60}" # Default jika kosong (seharusnya tidak terjadi karena validasi di atas)
        return 0
    else
        log_message "INFO: File konfigurasi $CONFIG_FILE tidak ditemukan."
        return 1
    fi
}

# Fungsi simpan konfigurasi
save_config() {
    # Backup konfigurasi lama (opsional)
    # cp "$CONFIG_FILE" "${CONFIG_FILE}.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null

    # Tulis konfigurasi baru
    # Menggunakan printf untuk keamanan jika ada karakter aneh di variabel
    printf "%s\n" \
        "# Konfigurasi Email Trader (v1.5)" \
        "GMAIL_USER='$GMAIL_USER'" \
        "GMAIL_APP_PASS='$GMAIL_APP_PASS'" \
        "BINANCE_API_KEY='$BINANCE_API_KEY'" \
        "BINANCE_SECRET_KEY='$BINANCE_SECRET_KEY'" \
        "TRADE_SYMBOL='$TRADE_SYMBOL'" \
        "TRADE_QUANTITY='$TRADE_QUANTITY'" \
        "CHECK_INTERVAL='$CHECK_INTERVAL'" > "$CONFIG_FILE"

    if [ $? -eq 0 ]; then
        chmod 600 "$CONFIG_FILE"
        log_message "Konfigurasi berhasil disimpan di $CONFIG_FILE"
        info_msg "Konfigurasi berhasil disimpan."
        return 0
    else
        log_message "ERROR: Gagal menyimpan konfigurasi ke $CONFIG_FILE"
        error_msg "Gagal menyimpan konfigurasi ke $CONFIG_FILE"
        return 1
    fi
}

# Fungsi konfigurasi interaktif (Password/Secret Key visible dengan inputbox)
configure_settings() {
    if is_listener_running; then
        error_msg "Listener sedang aktif (PID: $LISTENER_PID).\nHentikan listener terlebih dahulu untuk mengubah konfigurasi."
        return 1
    fi

    # Muat nilai saat ini jika ada, atau default kosong
    load_config &>/dev/null # Muat tanpa menampilkan pesan warning ke log jika gagal parse

    local temp_gmail_user="${GMAIL_USER}"
    local temp_gmail_pass="${GMAIL_APP_PASS}"
    local temp_api_key="${BINANCE_API_KEY}"
    local temp_secret_key="${BINANCE_SECRET_KEY}"
    local temp_symbol="${TRADE_SYMBOL}"
    local temp_quantity="${TRADE_QUANTITY}"
    local temp_interval="${CHECK_INTERVAL:-60}" # Default interval 60s

    local input_values exit_status

    # Menggunakan mixedform untuk input yang lebih baik (jika memungkinkan)
    # Format: label y x item y x field_length input_length flags
    # Inputbox lebih sederhana dan sesuai permintaan awal, jadi kita pakai itu
    # --- Input Fields Sequentially ---
    local field_values=()
    local labels=(
        "Alamat Gmail Anda:"
        "Gmail App Password (Visible):"
        "Binance API Key:"
        "Binance Secret Key (Visible):"
        "Simbol Trading (cth: BTCUSDT):"
        "Jumlah Quantity (cth: 0.001):"
        "Interval Cek Email (detik):"
    )
    local current_values=(
        "$temp_gmail_user"
        "$temp_gmail_pass"
        "$temp_api_key"
        "$temp_secret_key"
        "$temp_symbol"
        "$temp_quantity"
        "$temp_interval"
    )
    local input_vars=("input_gmail_user" "input_gmail_pass" "input_api_key" "input_secret_key" "input_symbol" "input_quantity" "input_interval")

    for i in "${!labels[@]}"; do
        # Gunakan inputbox untuk setiap field
        local current_input
        current_input=$(_dialog --stdout --title "🔧 Pengaturan - Langkah $((i + 1))/${#labels[@]}" \
                            --inputbox "${labels[$i]}" 10 70 "${current_values[$i]}" 2>&1 >/dev/tty)
        exit_status=$?
        if [[ $exit_status -ne 0 ]]; then
            info_msg "Konfigurasi dibatalkan."
            return 1
        fi
        # Simpan hasil ke array atau langsung ke variabel sementara
        eval "${input_vars[$i]}=\"$current_input\"" # Assign ke variabel dinamis
    done

    # Validasi setelah semua input didapatkan
    if [[ -z "$input_gmail_user" || -z "$input_gmail_pass" || -z "$input_api_key" || -z "$input_secret_key" || -z "$input_symbol" || -z "$input_quantity" || -z "$input_interval" ]]; then
         error_msg "Semua field konfigurasi harus diisi."
         return 1
    fi
    if ! [[ "$input_interval" =~ ^[1-9][0-9]*$ ]]; then
        error_msg "Interval cek email harus berupa angka positif (detik)."
        return 1
    fi
     # Gunakan bc untuk perbandingan desimal yang aman
     if ! [[ "$input_quantity" =~ ^[+]?([0-9]+(\.[0-9]*)?|\.[0-9]+)$ ]] || [[ $(bc <<< "$input_quantity <= 0") -eq 1 ]]; then
        error_msg "Quantity trading harus berupa angka desimal positif (misal: 0.001 atau 10)."
        return 1
     fi

    # Update variabel global jika validasi lolos
    GMAIL_USER="$input_gmail_user"
    GMAIL_APP_PASS="$input_gmail_pass"
    BINANCE_API_KEY="$input_api_key"
    BINANCE_SECRET_KEY="$input_secret_key"
    TRADE_SYMBOL=$(echo "$input_symbol" | tr '[:lower:]' '[:upper:]') # Konversi ke uppercase
    TRADE_QUANTITY="$input_quantity"
    CHECK_INTERVAL="$input_interval"

    # Simpan konfigurasi
    save_config
    return $? # Return status from save_config
}

# Fungsi untuk logging ke file
log_message() {
    # Pastikan LOG_FILE valid sebelum mencoba menulis
    if [[ -z "$LOG_FILE" || ! -w "$LOG_FILE" ]]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] Log file '$LOG_FILE' not defined or not writable. Message: $1" >&2
        return 1
    fi
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    # Tambahkan PID jika ada dan BUKAN PID script utama
    local pid_info=""
    if [[ -n "$$" && "$$" != "$SCRIPT_MAIN_PID" ]]; then
       pid_info=" [PID $$]"
    fi
    # Hindari potentially sensitive data di log jika memungkinkan
    # echo "[$timestamp]$pid_info $1" >> "$LOG_FILE"
    # Contoh: Masking password/key jika muncul di log (perlu penyesuaian)
    local log_entry="[$timestamp]$pid_info $1"
    # Sederhana saja untuk sekarang, tidak ada masking otomatis
    echo "$log_entry" >> "$LOG_FILE"
}

# --- Fungsi Background Listener (Tidak ada perubahan mayor di logika ini) ---

# Fungsi cek email baru yang cocok
check_email() {
    # Pastikan variabel konfigurasi ada
    if [[ -z "$GMAIL_USER" || -z "$GMAIL_APP_PASS" || -z "$EMAIL_IDENTIFIER" || -z "$EMAIL_CLIENT" ]]; then
        log_message "ERROR: Konfigurasi email tidak lengkap di check_email. Tidak bisa memeriksa."
        return 1 # Error konfigurasi
    fi

    log_message "Mencari email baru dari $GMAIL_USER (Identifier: '$EMAIL_IDENTIFIER')..."
    local email_body_file exit_code
    email_body_file=$(mktemp)
    if [[ -z "$email_body_file" || ! -f "$email_body_file" ]]; then
        log_message "ERROR: Gagal membuat file temporary untuk email."
        return 1 # Error system
    fi

    # Jalankan mutt/neomutt, redirect stderr ke log file, stdout diabaikan
    "$EMAIL_CLIENT" \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail="" query_command=""' \
        -e 'push "<limit>~N (~b \"'${EMAIL_IDENTIFIER}'\" | ~s \"'${EMAIL_IDENTIFIER}'\")\n<pipe-message>cat > '${email_body_file}'\n<exit>"' > /dev/null 2>>"$LOG_FILE"
    exit_code=$?

    # Analisis exit code
    if [ $exit_code -eq 0 ] && [ -s "$email_body_file" ]; then
        # Exit code 0 DAN file tidak kosong = email cocok ditemukan
        log_message "Email yang cocok ditemukan. Memproses..."
        parse_email_body "$email_body_file"
        local parse_status=$?
        rm "$email_body_file" # Hapus file temp
        if [ $parse_status -eq 0 ]; then
             mark_email_as_read # Tandai dibaca HANYA jika parse & eksekusi sukses
             log_message "Email diproses dan ditandai dibaca."
             return 0 # Email ditemukan dan diproses
        else
             log_message "Action tidak ditemukan atau gagal parse/eksekusi, email TIDAK ditandai dibaca."
             return 2 # Email ditemukan tapi gagal proses
        fi
    elif [ $exit_code -eq 0 ] || [ $exit_code -eq 1 ]; then
        # Exit code 0 atau 1 (no new mail) DAN file kosong = tidak ada email cocok
        log_message "Tidak ada email baru yang cocok ditemukan."
        rm "$email_body_file"
        return 1 # Tidak ada email cocok
    else
        # Exit code selain 0 atau 1 = error mutt/neomutt
        log_message "WARNING: Perintah $EMAIL_CLIENT keluar dengan kode $exit_code (Mungkin error koneksi/otentikasi). Cek log untuk detail stderr."
        rm "$email_body_file"
        return 1 # Anggap tidak ada email atau error
    fi
}

# Fungsi parsing body email
parse_email_body() {
    local body_file="$1"
    log_message "Parsing isi email dari $body_file"
    local action=""

    # Case-insensitive, whole word match
    if grep -qiw "buy" "$body_file"; then
        action="BUY"
    elif grep -qiw "sell" "$body_file"; then
        action="SELL"
    fi

    # Keamanan ganda: cek identifier lagi di body
    # Gunakan "fixed strings" (-F) dan quiet (-q)
    if ! grep -Fq "$EMAIL_IDENTIFIER" "$body_file"; then
        log_message "WARNING: Action '$action' terdeteksi, tapi identifier '$EMAIL_IDENTIFIER' tidak ada di body. Mengabaikan."
        return 1 # Gagal Parse (identifier mismatch)
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
        log_message "WARNING: Tidak ada action 'BUY' atau 'SELL' yang valid terdeteksi dalam email (Identifier: '$EMAIL_IDENTIFIER')."
        return 1 # Gagal Parse (action not found)
    fi
}

# Fungsi menandai email sebagai sudah dibaca
mark_email_as_read() {
    log_message "Menandai email sebagai sudah dibaca..."
     "$EMAIL_CLIENT" \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail="" query_command=""' \
        -e 'push "<limit>~U (~b \"'${EMAIL_IDENTIFIER}'\" | ~s \"'${EMAIL_IDENTIFIER}'\")\n<clear-flag>N\n<sync-mailbox><exit>"' > /dev/null 2>>"$LOG_FILE" # Target Unread saja
    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        log_message "Perintah untuk menandai email dibaca (yang cocok & belum dibaca) berhasil dikirim."
    elif [ $exit_code -eq 1 ]; then
         log_message "INFO: Tidak ada email UNREAD yang cocok untuk ditandai dibaca ($EMAIL_CLIENT exit code 1)."
    else
        log_message "WARNING: Perintah $EMAIL_CLIENT untuk menandai email dibaca mungkin gagal (exit code: $exit_code)."
    fi
}

# Fungsi generate signature Binance
generate_binance_signature() {
    local query_string="$1"
    local secret="$2"
    # Pastikan secret tidak kosong
    if [[ -z "$secret" ]]; then
        log_message "ERROR: Binance Secret Key kosong saat generate signature."
        return 1
    fi
    # Hasilkan signature, redirect stderr ke log
    local signature
    signature=$(echo -n "$query_string" | openssl dgst -sha256 -hmac "$secret" 2>>"$LOG_FILE" | sed 's/^.* //')
    if [[ -z "$signature" ]]; then
        log_message "ERROR: Gagal menghasilkan signature Binance (openssl error?). Cek log."
        return 1
    fi
    echo -n "$signature" # Output signature ke stdout
    return 0
}

# Fungsi eksekusi order Binance
execute_binance_order() {
    local side="$1"
    local timestamp
    timestamp=$(date +%s%3N) # Miliseconds timestamp

    if [[ -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$TRADE_SYMBOL" || -z "$TRADE_QUANTITY" ]]; then
        log_message "ERROR: Konfigurasi Binance tidak lengkap. Order $side dibatalkan."
        return 1
    fi

    local api_endpoint="https://api.binance.com" # Bisa diganti ke testnet jika perlu
    local order_path="/api/v3/order"
    # Parameter string HARUS sesuai urutan & format dokumentasi Binance
    # timestamp harus ada untuk keamanan
    # Ganti '×' dengan '&' jika itu typo di script lama
    local params="symbol=${TRADE_SYMBOL}&side=${side}&type=MARKET&quantity=${TRADE_QUANTITY}×tamp=${timestamp}"

    local signature
    signature=$(generate_binance_signature "$params" "$BINANCE_SECRET_KEY")
    if [ $? -ne 0 ] || [[ -z "$signature" ]]; then
        # Error sudah di-log oleh generate_binance_signature
        return 1
    fi

    local full_url="${api_endpoint}${order_path}?${params}&signature=${signature}"
    log_message "Mengirim order ke Binance: SIDE=$side SYMBOL=$TRADE_SYMBOL QTY=$TRADE_QUANTITY"

    local response http_code body curl_exit_code
    # Gunakan -w untuk memisahkan http_code, tambahkan timeout
    # Redirect stderr curl ke log file
    response=$(curl --connect-timeout 10 --max-time 20 -s -w "\nHTTP_CODE:%{http_code}" \
                 -H "X-MBX-APIKEY: ${BINANCE_API_KEY}" -X POST "$full_url" 2>>"$LOG_FILE")
    curl_exit_code=$?

    # Ekstrak body dan http_code
    http_code=$(echo "$response" | grep '^HTTP_CODE:' | cut -d':' -f2)
    body=$(echo "$response" | sed '$d') # Hapus baris terakhir (HTTP_CODE)

    if [ $curl_exit_code -ne 0 ]; then
        log_message "ERROR: curl gagal menghubungi Binance (Exit code: $curl_exit_code). Cek log untuk detail stderr curl."
        return 1
    fi

    log_message "Response Binance (HTTP $http_code): $body"

    # Gunakan jq untuk parsing response JSON yang lebih aman
    if [[ "$http_code" =~ ^2 ]]; then # Kode 2xx (Sukses)
        local orderId status clientOrderId filledQty cummulativeQuoteQty
        orderId=$(echo "$body" | jq -r '.orderId // empty' 2>>"$LOG_FILE")
        status=$(echo "$body" | jq -r '.status // "UNKNOWN"' 2>>"$LOG_FILE")
        clientOrderId=$(echo "$body" | jq -r '.clientOrderId // empty' 2>>"$LOG_FILE")
        filledQty=$(echo "$body" | jq -r '.executedQty // "N/A"' 2>>"$LOG_FILE")
        cummulativeQuoteQty=$(echo "$body" | jq -r '.cummulativeQuoteQty // "N/A"' 2>>"$LOG_FILE")

        if [[ -n "$orderId" && "$status" != "UNKNOWN" ]]; then
            log_message "SUCCESS: Order $side $TRADE_SYMBOL berhasil. ID: $orderId, Status: $status, Qty Filled: $filledQty, Total Cost/Proceeds: $cummulativeQuoteQty USDT"
            # TODO: Tambahkan notifikasi sukses (Telegram, etc.) jika perlu
            return 0
        else
            log_message "WARNING: Order $side $TRADE_SYMBOL - HTTP $http_code diterima tapi detail order tidak lengkap di response. Body: $body"
            # Anggap sukses jika HTTP 2xx, tapi beri warning
            return 0
        fi
    else # Kode error (4xx, 5xx)
        local err_code err_msg
        err_code=$(echo "$body" | jq -r '.code // "?"' 2>>"$LOG_FILE")
        err_msg=$(echo "$body" | jq -r '.msg // "Tidak ada pesan error spesifik"' 2>>"$LOG_FILE")
        log_message "ERROR: Gagal menempatkan order $side $TRADE_SYMBOL. Kode Binance: $err_code, Pesan: $err_msg"
        # TODO: Tambahkan notifikasi GAGAL (Telegram, etc.) jika perlu
        return 1
    fi
}

# Fungsi Loop Utama Listener (untuk dijalankan di background)
listener_loop() {
    # Pastikan variabel konfigurasi di-export agar terbaca oleh sub-shell/proses background
    # Atau lebih baik, pass sebagai argumen atau load config di dalam loop?
    # Untuk simple, kita export saja (pastikan tidak ada karakter sensitif di nama var)
    export GMAIL_USER GMAIL_APP_PASS BINANCE_API_KEY BINANCE_SECRET_KEY TRADE_SYMBOL TRADE_QUANTITY CHECK_INTERVAL EMAIL_IDENTIFIER EMAIL_CLIENT LOG_FILE

    # Dapatkan interval dari variabel (sudah divalidasi saat load/configure)
    local check_interval="${CHECK_INTERVAL}"

    # Log rotation settings
    local max_log_lines=1000 # Jumlah baris maksimum sebelum dipangkas
    local lines_to_keep=500  # Jumlah baris yang disimpan setelah pangkas

    # Trap sinyal di dalam loop background agar bisa keluar bersih
    trap 'log_message "Listener loop (PID $$) menerima sinyal TERM/INT. Menghentikan..."; exit 0' SIGTERM SIGINT

    log_message "Listener loop dimulai (PID $$). Interval: ${check_interval} detik. Log: $LOG_FILE"
    while true; do
        log_message "[Loop $$] Memulai siklus pengecekan email..."

        # Jalankan check_email dan log hasilnya
        check_email
        local check_status=$? # 0=Processed, 1=No Mail/Error, 2=Found but Failed Process
        log_message "[Loop $$] Hasil check_email: $check_status"

        log_message "[Loop $$] Siklus selesai. Menunggu ${check_interval} detik..."
        sleep "$check_interval"

        # Log Rotation/Trimming (setelah sleep agar tidak delay siklus utama)
        local current_lines
        # Pastikan file ada sebelum wc
        if [[ -f "$LOG_FILE" ]]; then
            current_lines=$(wc -l < "$LOG_FILE")
            if [[ "$current_lines" =~ ^[0-9]+$ && "$current_lines" -gt "$max_log_lines" ]]; then
                 log_message "INFO [Loop $$]: File log ($current_lines baris) melebihi $max_log_lines. Memangkas ke $lines_to_keep baris terakhir..."
                 # Cara pangkas yang lebih aman: temporary file
                 tail -n "$lines_to_keep" "$LOG_FILE" > "${LOG_FILE}.tmp" 2>/dev/null && mv "${LOG_FILE}.tmp" "$LOG_FILE" 2>/dev/null
                 if [ $? -ne 0 ]; then
                    log_message "WARNING [Loop $$]: Gagal memangkas file log."
                 else
                    log_message "INFO [Loop $$]: File log berhasil dipangkas."
                 fi
            elif ! [[ "$current_lines" =~ ^[0-9]+$ ]]; then
                 log_message "WARNING [Loop $$]: Gagal mendapatkan jumlah baris log (output wc: $current_lines)."
            fi
        else
             log_message "WARNING [Loop $$]: File log $LOG_FILE tidak ditemukan saat akan rotasi."
        fi
    done
}

# --- Fungsi Kontrol Listener ---

# Cek apakah listener sedang berjalan (lebih robust)
is_listener_running() {
    LISTENER_PID="" # Reset
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE")
        # Cek apakah pid numerik dan prosesnya ada
        if [[ "$pid" =~ ^[0-9]+$ ]] && ps -p "$pid" > /dev/null; then
            # Cek apakah itu benar proses listener kita (misal cek command line jika memungkinkan)
            # Untuk simple, kita anggap PID valid jika prosesnya ada
            LISTENER_PID="$pid"
            return 0 # Sedang berjalan
        else
            # PID file ada tapi proses tidak jalan atau PID tidak valid
            log_message "INFO: File PID ($PID_FILE) menunjuk ke proses $pid yang tidak valid/tidak berjalan. Menghapus file PID basi."
            rm -f "$PID_FILE"
            return 1 # Tidak berjalan
        fi
    else
        return 1 # Tidak berjalan (tidak ada PID file)
    fi
}

# Memulai listener
start_listener() {
    if is_listener_running; then
        error_msg "Listener sudah berjalan (PID: $LISTENER_PID)."
        return 1
    fi

    # Pastikan konfigurasi valid SEBELUM memulai
    if ! load_config; then
        error_msg "Konfigurasi belum lengkap atau tidak valid.\nSilakan perbaiki melalui menu Pengaturan."
        return 1
    fi

    infobox_msg "Memulai listener di background..."
    log_message "Memulai listener di background..."

    # Jalankan listener_loop di background, redirect outputnya (walaupun seharusnya tidak ada) ke log
    # Ini penting agar tidak ada output bocor ke terminal utama
    (listener_loop >> "$LOG_FILE" 2>&1) &
    local pid=$!

    # Cek apakah proses background berhasil dimulai
    sleep 0.5 # Beri sedikit waktu
    if ! ps -p "$pid" > /dev/null; then
        log_message "ERROR: Gagal memulai proses listener di background."
        error_msg "Gagal memulai listener di background.\nCek $LOG_FILE untuk detail error."
        rm -f "$PID_FILE" # Pastikan tidak ada PID file jika gagal start
        return 1
    fi

    # Simpan PID ke file
    echo "$pid" > "$PID_FILE"
    if [ $? -ne 0 ]; then
       log_message "ERROR: Gagal menyimpan PID $pid ke $PID_FILE. Menghentikan listener yang mungkin berjalan..."
       kill "$pid" 2>/dev/null # Coba hentikan
       error_msg "Gagal menyimpan file PID.\nListener mungkin tidak dimulai dengan benar."
       rm -f "$PID_FILE" # Hapus lagi jika gagal tulis
       return 1
    fi

    LISTENER_PID="$pid"
    log_message "Listener berhasil dimulai di background (PID: $LISTENER_PID)."
    info_msg "Listener berhasil dimulai (PID: $LISTENER_PID).\nLog aktivitas bisa dilihat di menu."
    return 0
}

# Menghentikan listener
stop_listener() {
    if ! is_listener_running; then
        # Tidak perlu error jika memang tidak jalan, mungkin user klik dua kali
        info_msg "Listener tidak sedang berjalan."
        return 1 # Kembalikan 1 jika tidak ada yang dihentikan
    fi

    infobox_msg "Menghentikan listener (PID: $LISTENER_PID)..."
    log_message "Mengirim sinyal TERM ke listener (PID: $LISTENER_PID)..."

    # Kirim sinyal TERM dulu (lebih bersih)
    if kill -TERM "$LISTENER_PID" 2>/dev/null; then
        local count=0
        local max_wait=10 # Tunggu maksimal 5 detik (10 * 0.5s)
        log_message "Menunggu listener (PID: $LISTENER_PID) berhenti..."
        while kill -0 "$LISTENER_PID" 2>/dev/null; do
            ((count++))
            if [ "$count" -gt "$max_wait" ]; then
                log_message "WARNING: Listener (PID: $LISTENER_PID) tidak berhenti dengan TERM setelah $((max_wait / 2)) detik. Mengirim KILL."
                kill -KILL "$LISTENER_PID" 2>/dev/null
                sleep 0.5 # Beri waktu kill
                break
            fi
            printf "." # Progress indicator kecil di log
            sleep 0.5
        done
        echo # Newline setelah titik-titik progress di log

        # Cek lagi setelah loop
        if ! kill -0 "$LISTENER_PID" 2>/dev/null; then
            log_message "Listener (PID: $LISTENER_PID) berhasil dihentikan."
            info_msg "Listener (PID: $LISTENER_PID) berhasil dihentikan."
            rm -f "$PID_FILE" # Hapus PID file HANYA jika berhasil berhenti
            LISTENER_PID=""
            return 0 # Sukses berhenti
        else
            log_message "ERROR: Gagal menghentikan listener (PID: $LISTENER_PID) bahkan dengan KILL."
            error_msg "Gagal menghentikan listener (PID: $LISTENER_PID).\nAnda mungkin perlu menghentikannya manual: kill -9 $LISTENER_PID"
            # Jangan hapus PID file jika gagal kill
            return 1 # Gagal berhenti
        fi
    else
        log_message "WARNING: Gagal mengirim sinyal TERM ke PID $LISTENER_PID (mungkin sudah berhenti?). Memeriksa ulang..."
        # Cek ulang apakah prosesnya memang sudah tidak ada
        if ! kill -0 "$LISTENER_PID" 2>/dev/null; then
             log_message "INFO: Listener (PID: $LISTENER_PID) memang sudah tidak berjalan."
             info_msg "Listener sudah tidak berjalan."
             rm -f "$PID_FILE" # Hapus PID basi
             LISTENER_PID=""
             return 0 # Anggap sukses jika sudah berhenti
        else
             log_message "ERROR: Gagal mengirim TERM tapi proses $LISTENER_PID masih ada. Coba hentikan manual."
             error_msg "Gagal mengirim sinyal ke listener (PID: $LISTENER_PID) tapi proses masih ada."
             return 1 # Gagal
        fi
    fi
}

# Menampilkan log real-time
show_live_log() {
    if ! is_listener_running; then
        error_msg "Listener tidak sedang berjalan.\nTidak ada log real-time untuk ditampilkan."
        return 1
    fi
     # Tidak perlu clear, dialog akan handle
     _dialog --title "📜 Log Listener Real-time (PID: $LISTENER_PID)" \
            --no-kill \
            --tailboxbg "$LOG_FILE" 25 90
     # Setelah dialog ditutup (user tekan OK/Cancel), layar akan dibersihkan oleh menu utama
     log_message "Menutup tampilan log real-time (listener tetap berjalan)."
     # Tidak perlu clear di sini, menu utama akan refresh
}

# Fungsi Tampilkan Log Statis
view_static_log() {
    if [ ! -f "$LOG_FILE" ]; then
        info_msg "File log ($LOG_FILE) belum ada."
        return 1
    elif [ ! -s "$LOG_FILE" ]; then
        info_msg "File log ($LOG_FILE) kosong."
        return 1
    fi
     # Tidak perlu clear
    _dialog --title "📄 Log Aktivitas Statis ($LOG_FILE)" --cr-wrap --textbox "$LOG_FILE" 25 90
    # Tidak perlu clear di sini
}

# --- Fungsi Menu Utama ---
main_menu() {
    while true; do
        # Cek status listener di setiap iterasi loop menu
        is_listener_running

        local listener_status_msg listener_status_icon menu_height
        local -a menu_items # Declare sebagai array

        if [[ -n "$LISTENER_PID" ]]; then
            listener_status_msg="Listener: AKTIF (PID: $LISTENER_PID)"
            listener_status_icon="🟢"
            menu_items=(
                "1" "Lihat Log Listener (Real-time)"
                "2" "Hentikan Listener"
                "3" "Pengaturan (Nonaktif)" # Opsi dinonaktifkan
                "4" "Lihat Log Statis"
                "0" "Keluar & Hentikan Listener"
            )
            menu_height=18 # Tinggi menu
            menu_choices=7 # Jumlah pilihan + label
        else
            listener_status_msg="Listener: TIDAK AKTIF"
            listener_status_icon="🔴"
            menu_items=(
                "1" "Mulai Listener"
                "2" "Pengaturan"
                "3" "Lihat Log Statis"
                "0" "Keluar"
            )
            menu_height=17 # Tinggi menu
            menu_choices=6 # Jumlah pilihan + label
        fi

        # Gunakan --cancel-label untuk tombol Keluar/Cancel yang lebih jelas
        CHOICE=$(_dialog --clear --stdout \
                        --title "Menu Utama - [$listener_status_icon $listener_status_msg]" \
                        --cancel-label "Keluar" \
                        --menu "Pilih tindakan:" $menu_height 75 $menu_choices "${menu_items[@]}" 2>&1 >/dev/tty)
                        # Redirect stderr ke stdout, lalu stdout utama ke tty agar dialog tampil benar

        exit_status=$?

        # Handle Cancel (Escape/Tombol Cancel) atau pilihan "0"
        if [[ $exit_status -ne 0 ]] || [[ "$CHOICE" == "0" ]]; then
            if [[ -n "$LISTENER_PID" ]]; then
                if confirm_msg "Listener sedang berjalan.\nAnda yakin ingin keluar dan menghentikan listener?"; then
                    infobox_msg "Menghentikan listener sebelum keluar..."
                    stop_listener # Coba hentikan dengan bersih
                    log_message "--- Script Dihentikan via Menu Keluar (Listener Dihentikan) ---"
                    break # Keluar dari loop while
                else
                    continue # Kembali ke menu
                fi
            else
                log_message "--- Script Dihentikan (Listener tidak aktif) ---"
                break # Keluar dari loop while
            fi
        fi

        # Proses pilihan berdasarkan status listener saat menu ditampilkan
        if [[ -n "$LISTENER_PID" ]]; then # Listener Aktif
            case "$CHOICE" in
                1) show_live_log ;;
                2) stop_listener ;;
                3) error_msg "Hentikan listener dulu untuk masuk ke Pengaturan." ;;
                4) view_static_log ;;
                *) error_msg "Pilihan '$CHOICE' tidak valid." ;;
            esac
        else # Listener Tidak Aktif
             case "$CHOICE" in
                1)
                    start_listener
                    # Opsional: Langsung tampilkan log setelah start berhasil?
                    # if is_listener_running; then
                    #    sleep 1 # Beri waktu sedikit untuk listener mulai log
                    #    show_live_log
                    # fi
                    ;;
                2) configure_settings ;;
                3) view_static_log ;;
                *) error_msg "Pilihan '$CHOICE' tidak valid." ;;
            esac
        fi
        # Tidak perlu sleep atau pause di sini, user akan kembali ke menu
    done
}

# --- Main Program Execution ---

# Setup trap untuk exit bersih (Ctrl+C, SIGTERM)
cleanup() {
    local exit_code=$?
    # Kembalikan terminal ke kondisi normal jika dialog crash
    clear
    tput cnorm # Pastikan kursor terlihat
    echo # Newline setelah potentially Ctrl+C char (^C)

    log_message "--- Script Menerima Sinyal Exit (Code: $exit_code) ---"

    # Hanya hentikan listener jika script utama yang menerima sinyal
    # dan listener memang sedang berjalan DARI SESI INI (cek PID file lagi)
    if is_listener_running; then
        echo "!! Sinyal exit diterima. Menghentikan listener (PID: $LISTENER_PID) secara paksa..."
        log_message "NOTICE: Menghentikan listener (PID: $LISTENER_PID) karena script utama exit/sinyal."
        # Langsung kirim KILL karena ini darurat/cleanup, jangan tunggu TERM
        kill -KILL "$LISTENER_PID" 2>/dev/null
        rm -f "$PID_FILE"
        echo "Listener dihentikan."
        log_message "Listener (PID: $LISTENER_PID) dihentikan paksa saat script exit."
    fi
    echo "Script selesai."
    exit "$exit_code" # Keluar dengan kode exit asli jika ada
}
# Trap sinyal umum yang menyebabkan terminasi
# Jangan trap EXIT jika tidak ingin cleanup dijalankan pada exit normal dari 'break' di main_menu
trap cleanup SIGINT SIGTERM SIGHUP

# --- Eksekusi Utama ---
clear
echo "Memulai $SCRIPT_TITLE..."
echo "Mengecek dependensi..."
check_deps
log_message "--- Script Email Trader v1.5 Dimulai (PID: $$) ---"
sleep 1

# Cek status listener saat startup (dari sesi sebelumnya mungkin)
if is_listener_running; then
    log_message "INFO: Script dimulai, listener dari sesi sebelumnya terdeteksi aktif (PID: $LISTENER_PID)."
    info_msg "Listener dari sesi sebelumnya terdeteksi aktif (PID: $LISTENER_PID).\nAnda dapat menghentikannya dari menu."
fi

# Coba load konfigurasi, jika gagal dan listener TIDAK jalan, paksa konfigurasi
if ! load_config; then
    if ! is_listener_running; then
        _dialog --title "⚠️ Setup Awal Diperlukan" \
            --msgbox "File konfigurasi ($CONFIG_FILE) tidak ditemukan atau tidak valid.\n\nAnda akan diarahkan ke menu konfigurasi." 10 70
        if ! configure_settings; then
            clear # Bersihkan layar setelah dialog
            echo "Konfigurasi awal dibatalkan atau gagal. Script tidak dapat dilanjutkan."
            log_message "FATAL: Konfigurasi awal gagal/dibatalkan. Script berhenti."
            exit 1
        fi
        # Coba load lagi setelah konfigurasi berhasil disimpan
        if ! load_config; then
            clear
            echo "Gagal memuat konfigurasi setelah setup awal. Script berhenti."
            log_message "FATAL: Gagal memuat konfigurasi setelah setup. Script berhenti."
            exit 1
        fi
    else
        # Konfigurasi gagal load TAPI listener jalan (dari sesi lalu)
        log_message "WARNING: Konfigurasi gagal dimuat, tapi listener (PID $LISTENER_PID) sedang aktif. Pengaturan tidak bisa diakses sampai listener dihentikan."
        error_msg "WARNING: Konfigurasi gagal dimuat ($CONFIG_FILE).\nListener (PID $LISTENER_PID) dari sesi lalu masih aktif.\nPengaturan tidak bisa diubah. Hentikan listener dulu jika perlu mengkonfigurasi ulang."
    fi
fi

# Masuk ke menu utama
main_menu

# Keluar setelah loop menu selesai (user memilih keluar)
clear
echo "Script $SCRIPT_TITLE telah berhenti."
exit 0
