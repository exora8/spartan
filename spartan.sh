#!/usr/bin/env bash

# Script Email Listener & Binance Trader
# Versi: 1.6 (Aggressive Output Suppression & Debug Logging)
# Author: [Nama Kamu/AI] & Kontributor

# --- Konfigurasi Awal ---
CONFIG_FILE="$HOME/.email_trader_rc"
LOG_FILE="/tmp/email_trader.log"
PID_FILE="/tmp/email_trader.pid"
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"
chmod 600 "$PID_FILE" 2>/dev/null

# Identifier Email yang Dicari (Subject atau Body)
EMAIL_IDENTIFIER="Exora AI (V5 SPOT + SR Filter) (1M)" # Contoh

# --- Variabel Global ---
LISTENER_PID=""
SCRIPT_MAIN_PID=$$
export SCRIPT_MAIN_PID # Export agar bisa dicek di subshell/trap

# --- Konstanta Tampilan ---
DIALOG_BACKTITLE="Email->Binance Trader v1.6"

# --- Fungsi ---

# Fungsi untuk logging ke file (TAMBAHKAN DEBUG)
log_message() {
    # Verifikasi kita di proses utama atau tidak
    # Izinkan log dari proses utama atau proses yang PID-nya ada di PID_FILE
    local current_pid=$$
    local known_listener_pid=""
    if [ -f "$PID_FILE" ]; then known_listener_pid=$(cat "$PID_FILE" 2>/dev/null); fi

    # Hanya proses utama atau listener yang terdaftar yang boleh log
    if [[ "$current_pid" != "$SCRIPT_MAIN_PID" ]] && [[ "$current_pid" != "$known_listener_pid" ]]; then
        # Log proses 'asing' sekali saja jika perlu untuk debug, lalu return
        # echo "[$(date '+%Y-%m-%d %H:%M:%S')] [UNKNOWN PID $current_pid] Attempted to log: $1" >> "$LOG_FILE"
        return
    fi

    local timestamp prefix pid_info caller
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    # Dapatkan nama fungsi pemanggil (mungkin perlu disesuaikan jika kedalaman call stack berubah)
    caller="${FUNCNAME[1]}"
    # Handle jika dipanggil dari top level
    if [[ -z "$caller" || "$caller" == "main" || "$caller" == "source" ]]; then caller="main_script"; fi


    if [[ "$current_pid" == "$SCRIPT_MAIN_PID" ]]; then
        prefix="[MAIN]"
        pid_info="[$$]"
    elif [[ -n "$known_listener_pid" && "$current_pid" == "$known_listener_pid" ]]; then
        prefix="[LISTENER]"
        pid_info="[$$]"
    else
         # Seharusnya tidak tercapai karena return di atas, tapi sebagai fallback
        prefix="[OTHER]"
        pid_info="[$$]"
    fi

    echo "[$timestamp] $prefix$pid_info ($caller) $1" >> "${LOG_FILE:-/tmp/email_trader_fallback.log}"
}


# Fungsi untuk menampilkan pesan error dengan dialog
error_msg() {
    log_message "Displaying error dialog: $1"
    # Pastikan layar bersih sebelum dialog
    clear
    dialog --backtitle "$DIALOG_BACKTITLE" --title "Error" --msgbox "\n$1" 8 65 # Tambah newline
    # Pastikan layar bersih setelah dialog
    clear
}

# Fungsi untuk menampilkan info dengan dialog
info_msg() {
     log_message "Displaying info dialog: $1"
     clear
     dialog --backtitle "$DIALOG_BACKTITLE" --title "Info" --msgbox "\n$1" 8 65
     clear
}

# Fungsi untuk menampilkan info sementara (auto-close)
infobox_msg() {
    log_message "Displaying infobox: $1"
    # Tidak perlu clear sebelum infobox karena biasanya cepat
    dialog --backtitle "$DIALOG_BACKTITLE" --title "Info" --infobox "$1" 5 50
    sleep 2 # Jeda singkat
    # Tidak perlu clear setelah infobox, biarkan menu berikutnya yg clear
}

# Fungsi cek dependensi
check_deps() {
    log_message "Checking dependencies..."
    local missing_deps=()
    # Tambahkan timeout dan stty
    for cmd in dialog neomutt curl openssl jq grep sed awk cut date mktemp tail wc kill sleep wait clear pgrep timeout stty; do
        if ! command -v "$cmd" &> /dev/null; then
            missing_deps+=("$cmd")
        fi
    done
    if ! command -v neomutt &> /dev/null && ! command -v mutt &> /dev/null; then
         missing_deps+=("neomutt atau mutt")
    fi
    if [ ${#missing_deps[@]} -ne 0 ]; then
        # Output error ke stderr jika dialog belum tentu ada
        echo "ERROR: Dependensi berikut tidak ditemukan atau tidak ada di PATH:" >&2
        printf " - %s\n" "${missing_deps[@]}" >&2
        echo "Silakan install terlebih dahulu sebelum menjalankan script." >&2
        log_message "ERROR: Missing dependencies: ${missing_deps[*]}"
        # Coba tampilkan dialog jika ada
        if command -v dialog &> /dev/null; then
             dialog --backtitle "$DIALOG_BACKTITLE" --title "Error Dependensi" --cr-wrap --msgbox "Dependensi berikut tidak ditemukan:\n\n$(printf -- '- %s\n' "${missing_deps[@]}")\n\nSilakan install terlebih dahulu." 15 70
        fi
        exit 1 # Keluar dari script
    fi
    # Dapatkan path email client
    if command -v neomutt &> /dev/null; then
        EMAIL_CLIENT=$(command -v neomutt)
    elif command -v mutt &> /dev/null; then
        EMAIL_CLIENT=$(command -v mutt)
    fi
    log_message "Dependencies check passed. Email client: $EMAIL_CLIENT"
}


# Fungsi load konfigurasi (tambahkan logging)
load_config() {
    log_message "Loading configuration from $CONFIG_FILE..."
    if [ -f "$CONFIG_FILE" ]; then
        chmod 600 "$CONFIG_FILE" # Pastikan permission
        # Grep variabel
        GMAIL_USER=$(grep -Po "^GMAIL_USER *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        GMAIL_APP_PASS=$(grep -Po "^GMAIL_APP_PASS *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        BINANCE_API_KEY=$(grep -Po "^BINANCE_API_KEY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        BINANCE_SECRET_KEY=$(grep -Po "^BINANCE_SECRET_KEY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        TRADE_SYMBOL=$(grep -Po "^TRADE_SYMBOL *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        TRADE_QUANTITY=$(grep -Po "^TRADE_QUANTITY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        CHECK_INTERVAL=$(grep -Po "^CHECK_INTERVAL *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)

        # Validasi kelengkapan
        if [[ -z "$GMAIL_USER" || -z "$GMAIL_APP_PASS" || -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$TRADE_SYMBOL" || -z "$TRADE_QUANTITY" || -z "$CHECK_INTERVAL" ]]; then
            log_message "WARNING: Config file exists but incomplete or failed parse."
            # Kosongkan variabel jika tidak lengkap untuk konsistensi
            GMAIL_USER="" GMAIL_APP_PASS="" BINANCE_API_KEY="" BINANCE_SECRET_KEY="" TRADE_SYMBOL="" TRADE_QUANTITY="" CHECK_INTERVAL=""
            return 1 # Gagal load
        fi
        log_message "Configuration loaded successfully."
        CHECK_INTERVAL="${CHECK_INTERVAL:-60}" # Default interval
        # Export variabel agar bisa diakses oleh proses background (listener_loop)
        export GMAIL_USER GMAIL_APP_PASS BINANCE_API_KEY BINANCE_SECRET_KEY TRADE_SYMBOL TRADE_QUANTITY EMAIL_IDENTIFIER EMAIL_CLIENT LOG_FILE CHECK_INTERVAL
        return 0 # Sukses load
    else
        log_message "INFO: Config file $CONFIG_FILE not found."
        return 1 # Gagal load
    fi
}

# Fungsi simpan konfigurasi (tambahkan logging)
save_config() {
    log_message "Saving configuration..."
    # Buat backup sebelum menimpa (opsional tapi bagus)
    if [ -f "$CONFIG_FILE" ]; then cp "$CONFIG_FILE" "$CONFIG_FILE.bak"; fi

    # Tulis konfigurasi baru
    {
        echo "# Konfigurasi Email Trader (v1.6)";
        echo "GMAIL_USER='${GMAIL_USER}'";
        echo "GMAIL_APP_PASS='${GMAIL_APP_PASS}'";
        echo "BINANCE_API_KEY='${BINANCE_API_KEY}'";
        echo "BINANCE_SECRET_KEY='${BINANCE_SECRET_KEY}'";
        echo "TRADE_SYMBOL='${TRADE_SYMBOL}'";
        echo "TRADE_QUANTITY='${TRADE_QUANTITY}'";
        echo "CHECK_INTERVAL='${CHECK_INTERVAL}'";
    } > "$CONFIG_FILE" # Timpa file

    # Cek apakah penulisan berhasil
    if [ $? -ne 0 ]; then
        log_message "ERROR: Failed to write to config file $CONFIG_FILE!"
        error_msg "Gagal menyimpan konfigurasi! Cek izin tulis."
        # Coba restore backup jika ada
        if [ -f "$CONFIG_FILE.bak" ]; then mv "$CONFIG_FILE.bak" "$CONFIG_FILE"; fi
        return 1
    fi

    chmod 600 "$CONFIG_FILE"
    log_message "Configuration saved successfully to $CONFIG_FILE"
    # Hapus backup jika sukses (opsional)
    rm -f "$CONFIG_FILE.bak" &>/dev/null

    info_msg "Konfigurasi berhasil disimpan."
    # Reload dan export variabel setelah disimpan
    if ! load_config >/dev/null 2>&1; then # Suppress output load_config
         log_message "ERROR: Failed to reload config after saving!"
         error_msg "Konfigurasi disimpan, tetapi gagal memuat ulang. Mungkin ada masalah?"
         return 1 # Kembalikan status error jika reload gagal
    fi
    return 0 # Sukses simpan dan reload
}

# Fungsi konfigurasi interaktif (tambahkan logging)
configure_settings() {
    log_message "Entering configuration settings..."
    # Cek listener aktif (suppress output is_listener_running)
    if is_listener_running >/dev/null 2>&1; then
        error_msg "Listener sedang aktif (PID: $LISTENER_PID). Hentikan listener terlebih dahulu."
        log_message "Configure cancelled: Listener is running."
        return 1
    fi

    # Muat nilai saat ini, abaikan return value karena kita akan menimpa
    load_config >/dev/null 2>&1
    local temp_gmail_user="${GMAIL_USER:-}"
    local temp_gmail_pass="${GMAIL_APP_PASS:-}"
    local temp_api_key="${BINANCE_API_KEY:-}"
    local temp_secret_key="${BINANCE_SECRET_KEY:-}"
    local temp_symbol="${TRADE_SYMBOL:-}"
    local temp_quantity="${TRADE_QUANTITY:-}"
    local temp_interval="${CHECK_INTERVAL:-60}" # Default interval 60

    # Gunakan temporary file untuk form dialog
    local input_gmail_user input_gmail_pass input_api_key input_secret_key input_symbol input_quantity input_interval exit_status temp_file
    temp_file=$(mktemp) || { error_msg "Gagal membuat file temporary."; return 1; }
    # Pastikan temp file dihapus saat fungsi selesai atau error
    trap 'rm -f "$temp_file" &>/dev/null' RETURN

    clear # Clear sebelum dialog form
    dialog --backtitle "$DIALOG_BACKTITLE" --title "Konfigurasi Akun & API" \
        --insecure --passwordform "\nMasukkan detail konfigurasi (Password terlihat):" 20 75 0 \
        "Alamat Gmail:"          1 1 "$temp_gmail_user"      1 28 65 0 \
        "Gmail App Password:"    2 1 "$temp_gmail_pass"      2 28 65 0 \
        "Binance API Key:"       3 1 "$temp_api_key"         3 28 65 0 \
        "Binance Secret Key:"    4 1 "$temp_secret_key"      4 28 65 0 \
        "Simbol Trading:"        5 1 "$temp_symbol"          5 28 65 0 \
        "Quantity per Trade:"    6 1 "$temp_quantity"        6 28 65 0 \
        "Interval Cek (detik):"  7 1 "$temp_interval"        7 28 65 0 \
        2>"$temp_file"

    exit_status=$?
    clear # Clear setelah dialog form

    if [ $exit_status -ne 0 ]; then
        # User tekan Cancel/Esc
        rm -f "$temp_file" &>/dev/null
        info_msg "Konfigurasi dibatalkan."
        log_message "Configuration cancelled by user."
        return 1
    fi

    # Baca hasil dari temporary file per baris
    {
    read -r input_gmail_user
    read -r input_gmail_pass
    read -r input_api_key
    read -r input_secret_key
    read -r input_symbol
    read -r input_quantity
    read -r input_interval
    } < "$temp_file"
    rm -f "$temp_file" &>/dev/null # Hapus temp file

    # Validasi input dasar
    log_message "Validating configuration input..."
    if [[ -z "$input_gmail_user" || -z "$input_gmail_pass" || -z "$input_api_key" || -z "$input_secret_key" || -z "$input_symbol" || -z "$input_quantity" || -z "$input_interval" ]]; then
         error_msg "Semua field konfigurasi harus diisi."
         log_message "Configuration validation failed: Empty fields."
         return 1 # Kembali ke menu tanpa menyimpan
    fi
    # Validasi interval (harus angka positif)
    if ! [[ "$input_interval" =~ ^[1-9][0-9]*$ ]]; then
        error_msg "Interval cek email harus berupa angka positif (detik)."
        log_message "Configuration validation failed: Invalid interval '$input_interval'."
        return 1
     fi
     # Validasi quantity (harus angka positif, bisa desimal)
     # Regex lebih ketat: harus ada angka sebelum/sesudah titik jika ada titik
     if ! [[ "$input_quantity" =~ ^[+]?([0-9]*\.[0-9]+|[0-9]+)$ && "$input_quantity" != "0" && "$input_quantity" != "0." && "$input_quantity" != ".0" ]]; then
        error_msg "Quantity trading harus berupa angka positif (misal: 0.001, 10, 0.5)."
        log_message "Configuration validation failed: Invalid quantity '$input_quantity'."
        return 1
     fi

    # Update variabel global (belum disimpan ke file)
    GMAIL_USER="$input_gmail_user"
    GMAIL_APP_PASS="$input_gmail_pass"
    BINANCE_API_KEY="$input_api_key"
    BINANCE_SECRET_KEY="$input_secret_key"
    TRADE_SYMBOL=$(echo "$input_symbol" | tr 'a-z' 'A-Z' | sed 's/[^A-Z0-9]//g') # Uppercase & cleanup
    TRADE_QUANTITY="$input_quantity"
    CHECK_INTERVAL="$input_interval"
    log_message "Configuration validated. Saving..."

    # Simpan konfigurasi ke file
    if ! save_config; then
        log_message "Configuration saving failed."
        # Pesan error sudah ditampilkan oleh save_config
        return 1 # Gagal simpan
    fi

    log_message "Exiting configuration settings successfully."
    return 0 # Sukses
}


# --- Fungsi Background Listener ---
# (check_email, parse_email_body, mark_email_as_read, generate_binance_signature, execute_binance_order)
# Pastikan fungsi-fungsi ini HANYA menggunakan log_message() untuk output.

check_email() {
    log_message "Starting email check cycle..."
    local email_body_file mutt_exit_code parse_status
    # Gunakan mktemp dengan template untuk debug jika perlu
    email_body_file=$(mktemp /tmp/email_trader_body.XXXXXX) || { log_message "ERROR: Failed to create temp file for email body."; return 1; }
    # Pastikan file temp dihapus apapun yang terjadi
    trap 'rm -f "$email_body_file" &>/dev/null' RETURN

    log_message "Checking IMAP with '$EMAIL_CLIENT' for identifier '$EMAIL_IDENTIFIER'"
    # Gunakan timeout dan redirect error mutt ke log jika perlu (optional, bisa jadi noisy)
    # timeout 30 "$EMAIL_CLIENT" \
    #     -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
    #     -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail="" net_timeout=15' \
    #     -e 'push "<limit>~N (~b \"'${EMAIL_IDENTIFIER}'\" | ~s \"'${EMAIL_IDENTIFIER}'\")\n<pipe-message>cat > '${email_body_file}'\n<exit>"' # 2>> "$LOG_FILE.mutt_error"

    # Versi lebih bersih tanpa redirect error mutt ke file
    timeout 30 "$EMAIL_CLIENT" \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail="" net_timeout=15' \
        -e 'push "<limit>~N (~b \"'${EMAIL_IDENTIFIER}'\" | ~s \"'${EMAIL_IDENTIFIER}'\")\n<pipe-message>cat > '${email_body_file}'\n<exit>"'

    mutt_exit_code=$?
    log_message "'$EMAIL_CLIENT' finished with exit code: $mutt_exit_code."

    # Analisis exit code mutt/neomutt
    # 0: Sukses (bisa ada atau tidak ada email baru)
    # 1: Biasanya tidak ada email baru yang cocok dengan limit
    # >1: Error (koneksi, auth, dll)
    # 124: Timeout dari command `timeout`

    if [[ "$mutt_exit_code" -gt 1 && "$mutt_exit_code" -ne 124 ]]; then
        log_message "WARNING: Mutt/Neomutt reported an error (code $mutt_exit_code). Check credentials/connection."
        # Mungkin perlu penanganan khusus jika error berulang?
        return 1 # Anggap gagal cek
    elif [[ "$mutt_exit_code" -eq 124 ]]; then
        log_message "WARNING: Timeout occurred during email check. Skipping this cycle."
        return 1 # Anggap gagal cek
    fi

    # Cek apakah file body berisi sesuatu (menandakan email cocok ditemukan)
    if [ -s "$email_body_file" ]; then
        log_message "Match found. Email body saved to $email_body_file. Parsing..."
        # Parsing dan eksekusi
        if parse_email_body "$email_body_file"; then
             # Jika parsing & order sukses, tandai sudah dibaca
             mark_email_as_read
             log_message "Email processed successfully."
             rm -f "$email_body_file" &>/dev/null # Hapus file setelah sukses
             return 0 # Sukses proses
        else
             # Jika parsing/order gagal, JANGAN tandai dibaca agar bisa dicek manual
             log_message "Email parsing or order execution failed. Email NOT marked as read."
             # Biarkan file body untuk debug jika perlu? Atau hapus?
             # rm -f "$email_body_file" &>/dev/null
             return 1 # Gagal proses
        fi
    else
        # File body kosong ATAU exit code 0/1 tapi file kosong
        log_message "No matching new email found in this cycle."
        rm -f "$email_body_file" &>/dev/null # Hapus file kosong
        return 1 # Tidak ada email baru
    fi
}

parse_email_body() {
    local body_file="$1" action
    log_message "Parsing email body from $body_file..."

    # Deteksi action (case-insensitive word match)
    if grep -qiw "buy" "$body_file"; then action="BUY";
    elif grep -qiw "sell" "$body_file"; then action="SELL";
    else action=""; fi
    log_message "Detected action: '$action'"

    # Verifikasi identifier ada di body (sebagai sanity check)
    # Gunakan -F untuk fixed string, lebih cepat dan aman
    if ! grep -qF "$EMAIL_IDENTIFIER" "$body_file"; then
        log_message "WARNING: Action '$action' detected, but identifier '$EMAIL_IDENTIFIER' NOT found in body. Ignoring."
        return 1 # Gagal parse
    fi

    # Eksekusi berdasarkan action
    if [[ "$action" == "BUY" ]]; then
        log_message "Executing Binance order for BUY..."
        execute_binance_order "BUY"
        return $? # Kembalikan status dari execute_binance_order
    elif [[ "$action" == "SELL" ]]; then
        log_message "Executing Binance order for SELL..."
        execute_binance_order "SELL"
        return $? # Kembalikan status dari execute_binance_order
    else
        log_message "WARNING: No valid 'BUY' or 'SELL' action found in the matched email."
        return 1 # Gagal parse
    fi
}

mark_email_as_read() {
    log_message "Attempting to mark email as read..."
    # Targetkan email yang UNREAD dan cocok dengan identifier
    # Menggunakan tag-prefix untuk menandai hanya yang baru diproses (jika mungkin)
    # Atau cukup limit ke ~U (Unread)
    timeout 15 "$EMAIL_CLIENT" \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail="" net_timeout=10' \
        -e 'push "<limit>~U (~b \"'${EMAIL_IDENTIFIER}'\" | ~s \"'${EMAIL_IDENTIFIER}'\")\n<tag-prefix><clear-flag>N<untag-pattern>.\n<sync-mailbox><exit>"'

    local exit_code=$?
    log_message "Mark as read command finished with code: $exit_code"
    if [[ $exit_code -eq 0 ]]; then
        log_message "Mark as read command sent successfully."
    elif [[ $exit_code -eq 124 ]]; then
         log_message "WARNING: Timeout occurred while marking email as read."
    elif [[ $exit_code -ne 1 ]]; then # Abaikan exit code 1 (no match)
        log_message "WARNING: Failed to mark email as read (code $exit_code)."
    fi
}

generate_binance_signature() {
    local query_string="$1" secret="$2" signature
    # Pastikan openssl ada
    if ! command -v openssl &> /dev/null; then
        log_message "ERROR: openssl command not found. Cannot generate signature."
        return 1
    fi
    # Hasilkan signature, tangkap error openssl jika ada
    signature=$(echo -n "$query_string" | openssl dgst -sha256 -hmac "$secret" 2>&1)
    local openssl_status=$?
    if [ $openssl_status -ne 0 ]; then
        log_message "ERROR: openssl failed (code $openssl_status) generating signature. Error: $signature"
        return 1
    fi
    # Ambil hanya bagian hash hex
    echo "$signature" | sed 's/^.*\(stdin\)= //
'
    return 0
}

execute_binance_order() {
    local side="$1" timestamp params signature full_url response curl_exit_code http_code body orderId status clientOrderId err_code err_msg
    log_message "Preparing Binance order: SIDE=$side, SYMBOL=$TRADE_SYMBOL, QTY=$TRADE_QUANTITY"
    timestamp=$(date +%s%3N)

    # Cek konfigurasi lagi sebelum membuat request
    if [[ -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$TRADE_SYMBOL" || -z "$TRADE_QUANTITY" ]]; then
        log_message "ERROR: Binance configuration incomplete in execute_binance_order."
        return 1
    fi

    local api_endpoint="https://api.binance.com" order_path="/api/v3/order"
    # Pastikan parameter diurutkan secara alfabet jika diperlukan (untuk Binance biasanya tidak, tapi praktik bagus)
    params="quantity=${TRADE_QUANTITY}&side=${side}&symbol=${TRADE_SYMBOL}×tamp=${timestamp}&type=MARKET"
    log_message "Generating signature for params: $params"
    signature=$(generate_binance_signature "$params" "$BINANCE_SECRET_KEY")
    if [ $? -ne 0 ] || [ -z "$signature" ]; then
        log_message "ERROR: Failed to generate Binance signature."
        return 1
    fi
    log_message "Signature generated successfully."

    full_url="${api_endpoint}${order_path}?${params}&signature=${signature}"
    # Jangan log URL lengkap dengan signature di produksi jika log bisa diakses publik
    log_message "Sending POST request to Binance API..."

    # Variabel untuk menampung error curl
    local curl_stderr_file
    curl_stderr_file=$(mktemp) || { log_message "ERROR: Failed to create temp file for curl error."; return 1; }
    trap 'rm -f "$curl_stderr_file" &>/dev/null' RETURN

    # Curl dengan timeout, simpan http_code, redirect stderr ke file temp
    response=$(curl --connect-timeout 10 --max-time 20 -s -w "\nHTTP_CODE:%{http_code}" \
               -H "X-MBX-APIKEY: ${BINANCE_API_KEY}" -X POST "$full_url" \
               2> "$curl_stderr_file")
    curl_exit_code=$?

    # Cek error curl
    if [ $curl_exit_code -ne 0 ]; then
        local curl_error_msg
        curl_error_msg=$(cat "$curl_stderr_file")
        log_message "ERROR: curl command failed (code: $curl_exit_code). Error: $curl_error_msg"
        rm -f "$curl_stderr_file" &>/dev/null
        return 1
    fi
    rm -f "$curl_stderr_file" &>/dev/null # Hapus file jika curl sukses

    # Ekstrak HTTP code dan body
    http_code=$(echo "$response" | grep '^HTTP_CODE:' | cut -d':' -f2)
    body=$(echo "$response" | sed '$d') # Hapus baris HTTP_CODE

    log_message "Binance Response - HTTP Code: $http_code"
    log_message "Binance Response - Body: $body"

    # Analisis respon berdasarkan HTTP code
    if [[ "$http_code" =~ ^2 ]]; then # Sukses (2xx)
        # Coba parse JSON
        if ! command -v jq &> /dev/null; then
            log_message "WARNING: jq command not found. Cannot parse successful Binance response body."
            # Anggap sukses jika 2xx tapi tidak bisa parse detail
            return 0
        fi
        orderId=$(echo "$body" | jq -r '.orderId // empty')
        status=$(echo "$body" | jq -r '.status // "UNKNOWN"')
        clientOrderId=$(echo "$body" | jq -r '.clientOrderId // empty')
        if [ -n "$orderId" ]; then
            log_message "SUCCESS: Order placed. ID: $orderId, Status: $status, ClientOrderID: $clientOrderId"
            # Di sini bisa tambahkan notifikasi sukses (Telegram, dll)
            return 0 # Sukses
        else
            log_message "WARNING: HTTP 2xx received but failed to parse orderId from response. Body: $body"
            # Anggap sukses parsial karena 2xx
            return 0
        fi
    else # Gagal (selain 2xx)
        log_message "ERROR: Binance API returned non-2xx HTTP code ($http_code)."
        if command -v jq &> /dev/null; then
            err_code=$(echo "$body" | jq -r '.code // "?"')
            err_msg=$(echo "$body" | jq -r '.msg // "No specific error message in JSON."')
            log_message "Binance Error Details - Code: $err_code, Message: $err_msg"
        else
            log_message "Binance Error Body (jq not found): $body"
        fi
         # Di sini bisa tambahkan notifikasi gagal (Telegram, dll)
        return 1 # Gagal
    fi
}


# Fungsi Loop Utama Listener (dijalankan di background)
listener_loop() {
    # Setup trap di dalam listener loop
    trap 'log_message "Received termination signal. Exiting listener loop."; exit 0' SIGTERM SIGINT

    # Dapatkan interval dari environment variable (sudah di-export oleh load_config)
    local check_interval="${CHECK_INTERVAL:-60}" # Default jika env var kosong
    if ! [[ "$check_interval" =~ ^[1-9][0-9]*$ ]]; then
        log_message "WARNING: Invalid CHECK_INTERVAL '$check_interval' in listener. Using 60s."
        check_interval=60
    fi
    log_message "Listener loop started. Check interval: ${check_interval}s."

    # Loop utama listener
    while true; do
        log_message "Executing check_email function..."
        # Panggil fungsi cek email
        check_email
        # check_email() sudah menangani logging internalnya
        log_message "check_email function finished. Sleeping for ${check_interval}s..."
        # Tidur selama interval yang ditentukan
        sleep "$check_interval"

        # Log trimming (opsional)
        # Cek ukuran log file dan pangkas jika perlu
        local max_log_lines=1000 current_lines log_size_kb
        if [ -f "$LOG_FILE" ]; then
            current_lines=$(wc -l < "$LOG_FILE")
            log_size_kb=$(( $(wc -c < "$LOG_FILE") / 1024 )) # Ukuran dalam KB
            # Pangkas jika melebihi batas baris ATAU batas ukuran (misal 10MB)
            if [[ "$current_lines" =~ ^[0-9]+$ && ("$current_lines" -gt "$max_log_lines" || "$log_size_kb" -gt 10240) ]]; then
                 log_message "INFO: Log file size ($current_lines lines, $log_size_kb KB) exceeds limit. Trimming..."
                 # Cara pangkas yang lebih aman
                 tail -n "$max_log_lines" "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
                 if [ $? -ne 0 ]; then log_message "WARNING: Failed to trim log file."; fi
            fi
        fi
    done
}

# --- Fungsi Kontrol Listener ---

# Cek apakah listener sedang berjalan via PID file (SUPPRESS OUTPUT)
is_listener_running() {
    # Fungsi ini seharusnya TIDAK menghasilkan output ke stdout/stderr
    # Logging sudah dilakukan oleh fungsi ini sendiri
    log_message "Checking listener status..."
    local pid=""
    if [ -f "$PID_FILE" ]; then
        # Baca PID dari file, suppress error jika file kosong/rusak
        pid=$(cat "$PID_FILE" 2>/dev/null)
        # Cek apakah PID valid (angka) dan prosesnya masih berjalan
        # Redirect output `kill -0` agar tidak muncul di terminal
        if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" >/dev/null 2>&1; then
            # Proses berjalan, update variabel global
            LISTENER_PID="$pid"
            log_message "Listener is RUNNING (PID: $LISTENER_PID)."
            return 0 # Status: Berjalan
        else
            # File PID ada tapi proses tidak jalan (stale)
            log_message "Stale PID file found ($PID_FILE points to PID $pid, which is not running). Removing PID file."
            # Hapus file PID basi, suppress error jika gagal hapus
            rm -f "$PID_FILE" >/dev/null 2>&1
            LISTENER_PID=""
            return 1 # Status: Tidak Berjalan
        fi
    else
        # File PID tidak ditemukan
        LISTENER_PID=""
        log_message "Listener is NOT RUNNING (no PID file)."
        return 1 # Status: Tidak Berjalan
    fi
}

# Memulai listener (dengan redirect agresif)
start_listener() {
    log_message "Attempting to start listener..."
    # Cek dulu apakah sudah jalan (suppress output is_listener_running)
    if is_listener_running >/dev/null 2>&1; then
        error_msg "Listener sudah berjalan (PID: $LISTENER_PID)."
        log_message "Start cancelled: Listener already running."
        return 1 # Gagal start
    fi

    # Load konfigurasi (suppress output load_config)
    # load_config juga export variabel yg dibutuhkan listener_loop
    if ! load_config >/dev/null 2>&1; then
        error_msg "Konfigurasi belum lengkap atau gagal dimuat. Tidak bisa memulai listener. Silakan cek 'Pengaturan'."
        log_message "Start cancelled: Config load failed."
        return 1 # Gagal start
    fi

    # Tampilkan pesan singkat ke user
    infobox_msg "Memulai listener di background..."
    log_message "Forking listener loop process..."

    # === JALANKAN LISTENER DI BACKGROUND ===
    # Redirect SEMUA output (stdout & stderr) dari subshell ini ke /dev/null
    # listener_loop akan log ke file via log_message()
    ( listener_loop ) >/dev/null 2>&1 &
    local pid=$! # Tangkap PID dari proses background

    # === VERIFIKASI PROSES BACKGROUND ===
    # Beri waktu sedikit agar proses sempat start atau gagal
    sleep 0.5
    # Cek apakah proses dengan PID tersebut benar-benar berjalan (suppress output kill)
    if ! kill -0 "$pid" >/dev/null 2>&1; then
        log_message "ERROR: Failed to start listener process (PID $pid did not start or died immediately)."
        error_msg "Gagal memulai listener. Cek log ($LOG_FILE) untuk kemungkinan error di awal."
        # Pastikan tidak ada file PID jika gagal start
        rm -f "$PID_FILE" >/dev/null 2>&1
        return 1 # Gagal start
    fi

    # === SIMPAN PID ===
    # Proses background berjalan, simpan PID ke file
    echo "$pid" > "$PID_FILE"
    if [ $? -ne 0 ]; then
       # Error saat menulis file PID (masalah permission?)
       log_message "ERROR: Failed to write PID $pid to $PID_FILE! Stopping the orphaned listener..."
       # Coba hentikan proses listener yang sudah terlanjur jalan
       kill "$pid" >/dev/null 2>&1
       error_msg "Gagal menyimpan file PID! Listener dihentikan. Cek izin tulis di /tmp."
       return 1 # Gagal start
    fi
    # Amankan file PID
    chmod 600 "$PID_FILE"

    # === SUKSES ===
    LISTENER_PID="$pid" # Update variabel global
    log_message "Listener started successfully (PID: $LISTENER_PID)."
    # Tampilkan pesan sukses singkat ke user
    infobox_msg "Listener berhasil dimulai (PID: $LISTENER_PID)."
    return 0 # Sukses start
}

# Menghentikan listener (dengan output minimal ke terminal)
stop_listener() {
    log_message "Attempting to stop listener..."
    # Cek dulu apakah listener sedang berjalan (suppress output is_listener_running)
    if ! is_listener_running >/dev/null 2>&1; then
        # Tidak perlu error jika memang tidak jalan
        info_msg "Listener memang tidak sedang berjalan."
        log_message "Stop cancelled: Listener was not running."
        return 1 # Kembalikan 1 untuk menandakan tidak ada aksi stop yg dilakukan
    fi

    # Listener berjalan, tampilkan pesan ke user
    infobox_msg "Menghentikan listener (PID: $LISTENER_PID)..."
    log_message "Sending TERM signal to listener (PID: $LISTENER_PID)."

    # Kirim sinyal TERM (15) - cara sopan untuk berhenti
    # Suppress output kill
    if kill -TERM "$LISTENER_PID" >/dev/null 2>&1; then
        local count=0 wait_seconds=5 # Tunggu maksimal 5 detik
        # Tampilkan progress stop HANYA di terminal utama
        clear
        echo -n "Menghentikan listener (PID: $LISTENER_PID): "
        # Loop cek status sambil menunggu
        while kill -0 "$LISTENER_PID" >/dev/null 2>&1; do # Suppress output kill -0
            ((count++))
            # Jika sudah menunggu terlalu lama
            if [ "$count" -gt $((wait_seconds * 2)) ]; then # Cek 2x per detik
                echo "[TIMEOUT]" # Beri tahu user di terminal
                log_message "WARNING: Listener did not stop with TERM after ${wait_seconds}s. Sending KILL signal."
                # Paksa berhenti dengan sinyal KILL (9)
                kill -KILL "$LISTENER_PID" >/dev/null 2>&1 # Suppress output kill -KILL
                sleep 0.5 # Beri waktu untuk KILL
                break # Keluar dari loop tunggu
            fi
            echo -n "." # Tampilkan titik sebagai progress
            sleep 0.5
        done
        echo # Newline setelah titik-titik atau [TIMEOUT]

        # Cek sekali lagi apakah sudah benar-benar berhenti
        if ! kill -0 "$LISTENER_PID" >/dev/null 2>&1; then # Suppress output kill -0
            log_message "Listener stopped successfully (PID: $LISTENER_PID)."
            info_msg "Listener (PID: $LISTENER_PID) berhasil dihentikan."
        else
            # Jika masih jalan bahkan setelah KILL (sangat jarang)
            log_message "ERROR: Failed to stop listener (PID: $LISTENER_PID) even with KILL signal."
            error_msg "Gagal menghentikan listener (PID: $LISTENER_PID). Mungkin perlu kill manual dari terminal lain (`kill -9 $LISTENER_PID`)."
            # Jangan hapus PID file jika gagal stop total
            return 1 # Gagal stop
        fi
    else
        # Gagal mengirim sinyal TERM (mungkin proses sudah hilang?)
        log_message "WARNING: Failed to send TERM signal to PID $LISTENER_PID (process might have already stopped)."
        info_msg "Gagal mengirim sinyal stop (listener mungkin sudah berhenti)."
        # Anggap sudah berhenti karena tidak bisa dikirimi sinyal
    fi

    # === CLEANUP SETELAH STOP ===
    # Hapus file PID setelah proses dipastikan berhenti atau gagal dikirimi sinyal
    log_message "Removing PID file: $PID_FILE"
    rm -f "$PID_FILE" >/dev/null 2>&1 # Suppress output rm
    LISTENER_PID="" # Reset variabel global
    # Tidak perlu clear di sini, info_msg/error_msg sudah handle
    return 0 # Sukses stop (atau sudah berhenti)
}


# Menampilkan log real-time (tidak berubah, pastikan clear setelahnya)
show_live_log() {
    log_message "Showing live log..."
    # Cek listener aktif (suppress output)
    if ! is_listener_running >/dev/null 2>&1; then
        error_msg "Listener tidak sedang berjalan. Tidak ada log real-time untuk ditampilkan."
        log_message "Show log cancelled: Listener not running."
        return 1
    fi
     # Clear layar sebelum menampilkan tailbox
     clear
     dialog --backtitle "$DIALOG_BACKTITLE" \
            --title "Log Listener Real-time (PID: $LISTENER_PID) - [Tekan Esc/Cancel untuk Kembali]" \
            --no-kill `# <-- Jangan bunuh proses tail` \
            --tailboxbg "$LOG_FILE" 25 90
     # Setelah dialog ditutup (user tekan Esc/Cancel)
     log_message "Live log view closed by user (listener remains active)."
     clear # Bersihkan layar setelah dialog log ditutup
     return 0
}

# Fungsi Tampilkan Log Statis (tidak berubah, pastikan clear setelahnya)
view_static_log() {
    log_message "Showing static log..."
    # Cek apakah file log ada dan tidak kosong
    if [ ! -f "$LOG_FILE" ] || [ ! -s "$LOG_FILE" ]; then
         info_msg "File log ($LOG_FILE) belum ada atau kosong."
         log_message "Show static log cancelled: Log file empty or not found."
         return 1
    fi
    # Clear layar sebelum menampilkan textbox
    clear
    dialog --backtitle "$DIALOG_BACKTITLE" \
           --title "Log Aktivitas Statis ($LOG_FILE) - [Tekan Esc/OK untuk Kembali]" \
           --textbox "$LOG_FILE" 25 90
    # Setelah dialog ditutup
    log_message("Static log view closed by user.")
    clear # Bersihkan layar setelah dialog log ditutup
    return 0
}


# --- Fungsi Menu Utama (Refined) ---
main_menu() {
    log_message "Entering main menu loop..."
    while true; do
        # 1. Cek status listener (output sudah disuppress di fungsinya)
        # Fungsi ini juga mengupdate variabel global LISTENER_PID
        is_listener_running

        # 2. Siapkan item menu & status berdasarkan LISTENER_PID
        local listener_status_msg menu_items menu_height=6 CHOICE choice_file exit_status confirm_exit confirm_view
        if [[ -n "$LISTENER_PID" ]]; then
            listener_status_msg="Listener AKTIF (PID: $LISTENER_PID)"
            menu_items=("1" "Lihat Log Real-time"
                         "2" "Hentikan Listener"
                         "3" "Pengaturan (Nonaktif)"
                         "4" "Lihat Log Statis"
                         "5" "Keluar")
        else
            listener_status_msg="Listener TIDAK AKTIF"
             menu_items=("1" "Mulai Listener"
                         "2" "Pengaturan"
                         "3" "Lihat Log Statis"
                         "4" "Keluar")
             menu_height=5 # Menu lebih pendek
        fi

        # 3. Tampilkan dialog menu (gunakan temp file untuk hasil)
        # Temporary file untuk menyimpan pilihan dari dialog
        choice_file=$(mktemp /tmp/email_trader_menu.XXXXXX) || { log_message "CRITICAL: Cannot create temp file for menu choice."; echo "Fatal error creating temp file." >&2; exit 1; }
        # Pastikan temp file dihapus saat fungsi return
        trap 'rm -f "$choice_file" &>/dev/null' RETURN

        clear # Pastikan layar bersih SEBELUM dialog menu muncul
        log_message "Displaying main menu (Status: $listener_status_msg)..."
        # Tampilkan menu, arahkan error (pilihan) ke temp file
        dialog --backtitle "$DIALOG_BACKTITLE" \
               --title "Menu Utama - Status: $listener_status_msg" \
               --cancel-label "Keluar" \
               --ok-label "Pilih" \
               --menu "\nPilih tindakan:" 18 75 $menu_height "${menu_items[@]}" 2>"$choice_file"

        exit_status=$? # Tangkap status exit dialog
        CHOICE=$(cat "$choice_file" 2>/dev/null) # Baca pilihan dari temp file
        rm -f "$choice_file" &>/dev/null # Hapus temp file

        # 4. Handle Cancel/Esc (exit_status != 0) atau Pilihan "Keluar"
        # Jika user menekan Esc atau Cancel, exit_status tidak 0
        if [[ $exit_status -ne 0 ]]; then
            log_message "Menu cancelled by user (ESC/Cancel pressed)."
            # Jika listener aktif, beri konfirmasi sebelum keluar
            if [[ -n "$LISTENER_PID" ]]; then
                clear
                dialog --backtitle "$DIALOG_BACKTITLE" --title "Konfirmasi Keluar" --yesno "Listener sedang aktif (PID: $LISTENER_PID).\n\nYakin ingin keluar dan menghentikan listener?" 8 60
                confirm_exit=$? # 0=Yes, 1=No, 255=Esc
                clear
                if [ $confirm_exit -eq 0 ]; then # User pilih Yes
                    log_message "User confirmed exit while listener active."
                    CHOICE="Keluar" # Proses sebagai pilihan Keluar di bawah
                else
                    log_message "User cancelled exit confirmation."
                    continue # Kembali ke awal loop menu tanpa melakukan apa-apa
                fi
            else
                # Jika listener tidak aktif, Cancel/Esc langsung dianggap Keluar
                 log_message "ESC/Cancel pressed while listener inactive. Setting choice to Keluar."
                CHOICE="Keluar"
            fi
        fi

        # 5. Proses Pilihan yang Valid (CHOICE berisi nomor menu atau "Keluar")
        log_message "Processing menu choice: '$CHOICE'"
        # Gunakan status listener *saat menu ditampilkan* untuk menentukan aksi
        if [[ "$listener_status_msg" == *"AKTIF"* ]]; then # Listener AKTIF
            case "$CHOICE" in
                1) show_live_log ;;
                2) stop_listener ;; # Fungsi ini handle output & clear screen
                3) error_msg "Hentikan listener dulu untuk masuk ke Pengaturan." ;;
                4) view_static_log ;;
                5|"Keluar")
                    log_message "Exiting script via menu (listener active scenario)."
                    stop_listener # Coba hentikan listener (handle pesan jika sudah berhenti)
                    log_message "Exiting main menu loop to terminate script."
                    return 0 # Keluar dari fungsi main_menu, script akan berakhir
                    ;;
                *) clear; error_msg "Pilihan '$CHOICE' tidak valid." ;; # Handle pilihan aneh
            esac
        else # Listener TIDAK AKTIF
             case "$CHOICE" in
                1)
                    start_listener # Fungsi ini handle output & pesan
                    # Tanyakan apakah mau lihat log jika start berhasil
                    if is_listener_running >/dev/null 2>&1; then # Cek lagi statusnya
                        clear
                        dialog --backtitle "$DIALOG_BACKTITLE" --title "Listener Dimulai" --yesno "Listener berhasil dimulai (PID: $LISTENER_PID).\n\nLihat log real-time sekarang?" 8 60
                        confirm_view=$?
                        clear
                        if [ $confirm_view -eq 0 ]; then # User pilih Yes
                           show_live_log
                        fi
                    fi
                    ;;
                2) configure_settings ;; # Fungsi ini handle output & clear screen
                3) view_static_log ;;
                4|"Keluar")
                    log_message "Exiting script via menu (listener inactive scenario)."
                    log_message "Exiting main menu loop to terminate script."
                    return 0 # Keluar dari fungsi main_menu
                    ;;
                *) clear; error_msg "Pilihan '$CHOICE' tidak valid." ;; # Handle pilihan aneh
            esac
        fi
        # Jeda singkat sebelum loop berikutnya (opsional, bisa membantu render?)
        # sleep 0.1
    done
}


# --- Main Program Execution ---

# Fungsi cleanup (dipanggil saat exit)
cleanup() {
    # Hanya jalankan jika ini proses utama
    if [[ "$$" == "$SCRIPT_MAIN_PID" ]]; then
        local exit_code=$?
        # Log hanya jika script belum selesai normal
        if [[ "$exit_code" -ne 0 ]]; then
             log_message "Cleanup initiated by signal or non-zero exit (Exit Code: $exit_code)."
        else
             log_message "Cleanup initiated by normal exit."
        fi

        # Cek listener aktif & hentikan jika perlu
        local current_pid=""
        if [ -f "$PID_FILE" ]; then current_pid=$(cat "$PID_FILE" 2>/dev/null); fi

        if [[ "$current_pid" =~ ^[0-9]+$ ]] && kill -0 "$current_pid" >/dev/null 2>&1; then
            echo # Newline untuk memisahkan dari output dialog/menu
            echo " Membersihkan: Menghentikan listener aktif (PID: $current_pid)..."
            # Kirim TERM, tunggu sebentar, lalu KILL
            kill -TERM "$current_pid" >/dev/null 2>&1
            sleep 0.3 # Tunggu sedikit
            kill -KILL "$current_pid" >/dev/null 2>&1 # Pastikan berhenti
            rm -f "$PID_FILE" >/dev/null 2>&1
            echo " Listener dihentikan."
            log_message "Listener (PID: $current_pid) stopped during cleanup."
        else
            # Hapus file PID basi jika ada
             rm -f "$PID_FILE" >/dev/null 2>&1
        fi
        # Kembalikan terminal ke kondisi normal
        stty sane >/dev/null 2>&1
        echo " Pembersihan selesai."
        log_message "Cleanup finished."
    fi
    # Jangan exit dari dalam trap EXIT untuk menghindari loop
}

# Setup trap
# SIGINT (Ctrl+C) dan SIGTERM (kill): panggil cleanup lalu exit
trap 'cleanup; exit 130' SIGINT
trap 'cleanup; exit 143' SIGTERM
# EXIT (normal atau via exit N): panggil cleanup SAJA
trap cleanup EXIT


# --- Start Script ---
# 0. Bersihkan layar awal
clear

# 1. Check Deps (keluar jika gagal)
check_deps || exit 1

# 2. Log Start
log_message "--- Script Email Trader v1.6 Started (PID: $$) ---"

# 3. Cek status listener dari sesi sebelumnya
# Gunakan is_listener_running tapi tampilkan info jika aktif
if is_listener_running >/dev/null 2>&1; then
    info_msg "Listener dari sesi sebelumnya terdeteksi aktif (PID: $LISTENER_PID)."
fi

# 4. Load Konfigurasi Awal atau Jalankan Setup
# Suppress output load_config di sini
if ! load_config >/dev/null 2>&1; then
    log_message "Initial config load failed."
    # Jika listener TIDAK aktif, jalankan setup
    if ! is_listener_running >/dev/null 2>&1; then
        clear
        dialog --backtitle "$DIALOG_BACKTITLE" --title "Setup Awal Diperlukan" \
            --msgbox "File konfigurasi ($CONFIG_FILE) tidak ditemukan atau tidak lengkap.\n\nMenjalankan setup awal..." 10 70
        clear
        # configure_settings menangani pesan sukses/gagalnya sendiri
        if ! configure_settings; then
            log_message "FATAL: Initial configuration failed or cancelled. Exiting."
            # Pesan error sudah ditampilkan, cukup exit
            exit 1 # Trap EXIT akan panggil cleanup
        fi
        # Setelah setup, config seharusnya sudah ter-load oleh save_config
        # Cek lagi untuk memastikan
         if ! load_config >/dev/null 2>&1; then
            log_message "FATAL: Failed to load config even after successful setup!? Exiting."
            error_msg "Gagal memuat konfigurasi setelah setup berhasil!? Script berhenti."
            exit 1 # Trap EXIT akan panggil cleanup
        fi
        log_message("Initial setup and config load successful.")
    else
        # Listener aktif TAPI config gagal load -> Ini masalah serius!
         log_message "CRITICAL: Listener active but config failed to load! Listener might malfunction."
         error_msg "KRITIS: Listener aktif (PID: $LISTENER_PID) TAPI konfigurasi gagal dimuat!\n\nListener mungkin tidak bisa trading. Hentikan listener dan perbaiki konfigurasi via menu Pengaturan."
         # Jangan exit, biarkan user masuk menu untuk stop listener & config
    fi
fi

# 5. Masuk ke Menu Utama
# main_menu akan loop sampai user memilih Keluar
main_menu

# 6. Script selesai normal setelah keluar dari main_menu
log_message "--- Script Email Trader v1.6 Finished Normally ---"
# Trap EXIT akan otomatis dipanggil di sini untuk cleanup

# Exit dengan status 0 (sukses)
exit 0
