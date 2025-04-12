#!/usr/bin/env bash

# Script Email Listener & Binance Trader
# Versi: 1.5 (Fix TUI Corruption, Binance API Call Fix)
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
SCRIPT_MAIN_PID=$$ # Simpan PID script utama untuk perbandingan di log_message

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
    for cmd in dialog neomutt curl openssl jq grep sed awk cut date mktemp tail wc kill sleep clear pgrep; do
        if ! command -v "$cmd" &> /dev/null; then
            missing_deps+=("$cmd")
        fi
    done
    # Cek neomutt atau mutt
    EMAIL_CLIENT=$(command -v neomutt || command -v mutt)
    if [[ -z "$EMAIL_CLIENT" ]]; then
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
}

# Fungsi load konfigurasi
load_config() {
    if [ -f "$CONFIG_FILE" ]; then
        chmod 600 "$CONFIG_FILE" # Pastikan permission benar
        # Gunakan source untuk cara load yang lebih robust (handle spasi, dll)
        # Tapi pastikan file config aman dan hanya berisi definisi variabel!
        # Atau tetap pakai grep jika khawatir dengan sourcing file eksternal
        GMAIL_USER=$(grep -Po "^GMAIL_USER *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        GMAIL_APP_PASS=$(grep -Po "^GMAIL_APP_PASS *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        BINANCE_API_KEY=$(grep -Po "^BINANCE_API_KEY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        BINANCE_SECRET_KEY=$(grep -Po "^BINANCE_SECRET_KEY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        TRADE_SYMBOL=$(grep -Po "^TRADE_SYMBOL *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        TRADE_QUANTITY=$(grep -Po "^TRADE_QUANTITY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        CHECK_INTERVAL=$(grep -Po "^CHECK_INTERVAL *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)

        # Validasi dasar setelah load
        if [[ -z "$GMAIL_USER" || -z "$GMAIL_APP_PASS" || -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$TRADE_SYMBOL" || -z "$TRADE_QUANTITY" ]]; then
            log_message "WARNING: File konfigurasi $CONFIG_FILE ada tapi tidak lengkap atau gagal parse (Variabel Wajib)."
            # Set default interval jika ada tapi kosong atau tidak ada
            CHECK_INTERVAL="${CHECK_INTERVAL:-60}"
            return 1 # Tetap return 1 karena konfigurasi utama tidak lengkap
        fi
        CHECK_INTERVAL="${CHECK_INTERVAL:-60}" # Set default jika hanya interval yang kosong
        log_message "Konfigurasi berhasil dimuat dari $CONFIG_FILE."
        return 0
    else
        log_message "INFO: File konfigurasi $CONFIG_FILE tidak ditemukan."
        return 1
    fi
}

# Fungsi simpan konfigurasi
save_config() {
    # Pastikan direktori ada jika $CONFIG_FILE mengandung path
    mkdir -p "$(dirname "$CONFIG_FILE")"
    # Hapus file lama sebelum menulis baru
    rm -f "$CONFIG_FILE"
    # Tulis konfigurasi
    {
        echo "# Konfigurasi Email Trader (v1.5)"
        echo "GMAIL_USER='${GMAIL_USER}'"
        echo "GMAIL_APP_PASS='${GMAIL_APP_PASS}'"
        echo "BINANCE_API_KEY='${BINANCE_API_KEY}'"
        echo "BINANCE_SECRET_KEY='${BINANCE_SECRET_KEY}'"
        echo "TRADE_SYMBOL='${TRADE_SYMBOL}'"
        echo "TRADE_QUANTITY='${TRADE_QUANTITY}'"
        echo "CHECK_INTERVAL='${CHECK_INTERVAL}'"
    } > "$CONFIG_FILE" # Redirect output group ke file

    chmod 600 "$CONFIG_FILE"
    log_message "Konfigurasi berhasil disimpan di $CONFIG_FILE"
    info_msg "Konfigurasi berhasil disimpan di $CONFIG_FILE"
}

# Fungsi konfigurasi interaktif
configure_settings() {
    # Cek jika listener sedang jalan, jangan biarkan konfigurasi diubah
    if is_listener_running; then
        error_msg "Listener sedang aktif (PID: $LISTENER_PID). Hentikan listener terlebih dahulu sebelum mengubah konfigurasi."
        return 1
    fi

    load_config # Muat nilai saat ini jika ada untuk ditampilkan di input

    # Simpan nilai sementara
    local temp_gmail_user="${GMAIL_USER}"
    local temp_gmail_pass="${GMAIL_APP_PASS}"
    local temp_api_key="${BINANCE_API_KEY}"
    local temp_secret_key="${BINANCE_SECRET_KEY}"
    local temp_symbol="${TRADE_SYMBOL}"
    local temp_quantity="${TRADE_QUANTITY}"
    local temp_interval="${CHECK_INTERVAL:-60}"

    local input_gmail_user input_gmail_pass input_api_key input_secret_key input_symbol input_quantity input_interval exit_status

    # Gunakan temporary file untuk menampung input dialog
    local temp_file
    temp_file=$(mktemp) || { error_msg "Gagal membuat file temporary untuk dialog."; return 1; }
    trap 'rm -f "$temp_file"' RETURN # Hapus temp file saat fungsi selesai

    # Gunakan --form untuk input multi-field yang lebih baik
    exec 3>&1 # Simpan stdout asli
    dialog --clear --title "Konfigurasi Email Trader" --form "\nMasukkan detail konfigurasi:" 20 70 0 \
        "Alamat Gmail:"          1 1 "$temp_gmail_user"      1 25 60 0 \
        "Gmail App Password:"    2 1 "$temp_gmail_pass"      2 25 60 0 \
        "Binance API Key:"       3 1 "$temp_api_key"       3 25 60 0 \
        "Binance Secret Key:"    4 1 "$temp_secret_key"    4 25 60 0 \
        "Simbol Trading (cth: BTCUSDT):" 5 1 "$temp_symbol"    5 25 60 0 \
        "Quantity Trading (cth: 0.001):" 6 1 "$temp_quantity"  6 25 60 0 \
        "Interval Cek (detik, cth: 60):" 7 1 "$temp_interval"  7 25 60 0 \
    2> "$temp_file"
    exit_status=$?
    exec 3>&- # Tutup file descriptor 3

    if [ $exit_status -ne 0 ]; then
        info_msg "Konfigurasi dibatalkan."
        return 1
    fi

    # Baca hasil dari temporary file
    input_gmail_user=$(sed -n '1p' "$temp_file")
    input_gmail_pass=$(sed -n '2p' "$temp_file")
    input_api_key=$(sed -n '3p' "$temp_file")
    input_secret_key=$(sed -n '4p' "$temp_file")
    input_symbol=$(sed -n '5p' "$temp_file")
    input_quantity=$(sed -n '6p' "$temp_file")
    input_interval=$(sed -n '7p' "$temp_file")
    rm -f "$temp_file" # Hapus file temporary

    # Validasi input dasar
    if [[ -z "$input_gmail_user" || -z "$input_gmail_pass" || -z "$input_api_key" || -z "$input_secret_key" || -z "$input_symbol" || -z "$input_quantity" || -z "$input_interval" ]]; then
         error_msg "Semua field konfigurasi harus diisi."
         return 1
    fi
    if ! [[ "$input_interval" =~ ^[1-9][0-9]*$ ]]; then
        error_msg "Interval cek email harus berupa angka positif (detik)."
        return 1
     fi
     # Validasi quantity lebih ketat (harus angka positif, bisa desimal)
     if ! [[ "$input_quantity" =~ ^[+]?([0-9]+(\.[0-9]*)?|\.[0-9]+)$ ]] || ! awk "BEGIN {exit !($input_quantity > 0)}"; then
        error_msg "Quantity trading harus berupa angka positif lebih besar dari 0 (misal: 0.001 atau 10)."
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

    save_config # Panggil fungsi simpan
    return 0
}


# Fungsi untuk logging ke file
log_message() {
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    # Tambahkan PID jika ada (lebih jelas bedakan main script vs listener)
    local pid_info="[PID $$]"
    # if [[ "$$" != "$SCRIPT_MAIN_PID" ]]; then # Cek jika PID saat ini BUKAN PID script utama
    #    pid_info="[Listener PID $$]"
    # fi
    # Append ke log file, pastikan LOG_FILE ada path default jika kosong
    echo "[$timestamp]$pid_info $1" >> "${LOG_FILE:-/tmp/email_trader_fallback.log}"
}

# --- Fungsi Background Listener ---

# Fungsi cek email baru yang cocok
check_email() {
    log_message "Mencari email baru dari $GMAIL_USER dengan identifier: '$EMAIL_IDENTIFIER'"
    local email_body_file
    # Pastikan mktemp aman
    email_body_file=$(mktemp --suffix=.eml) || { log_message "ERROR: Gagal membuat file temporary untuk email."; return 1; }
    trap 'rm -f "$email_body_file"' RETURN # Hapus temp file saat fungsi selesai

    # Jalankan neomutt/mutt, redirect stdout dan stderr internalnya untuk kebersihan
    "$EMAIL_CLIENT" \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail="" query_command=""' \
        -e 'push "<limit>~U ~S \"'${EMAIL_IDENTIFIER}'\"\n<pipe-message>cat > '${email_body_file}'\n<exit>"' \
        > /dev/null 2>&1
        # -e 'push "<limit>~N (~b \"'${EMAIL_IDENTIFIER}'\" | ~s \"'${EMAIL_IDENTIFIER}'\")\n<pipe-message>cat > '${email_body_file}'\n<exit>"' > /dev/null 2>&1
        # Alternatif: Hanya cari di Subject (~S) dan Unread (~U) agar lebih cepat & spesifik
        # -e 'push "<limit>~U ~S \"'${EMAIL_IDENTIFIER}'\"\n<pipe-message>cat > '${email_body_file}'\n<exit>"' > /dev/null 2>&1

    local mutt_exit_code=$?
    # Jangan log error jika exit code 1 (biasanya no new mail)
    if [[ $mutt_exit_code -ne 0 && $mutt_exit_code -ne 1 ]]; then
        log_message "WARNING: Perintah $EMAIL_CLIENT keluar dengan kode $mutt_exit_code (Mungkin error koneksi/autentikasi)"
    fi

    # Cek apakah file body email *ada isinya*
    if [ -s "$email_body_file" ]; then
        log_message "Email yang cocok ditemukan. Memproses..."
        # Panggil parse_email_body dengan file sebagai argumen
        if parse_email_body "$email_body_file"; then
             # Jika parsing dan eksekusi berhasil, tandai sebagai dibaca
             mark_email_as_read
        else
             # Jika gagal parse atau eksekusi, jangan tandai dibaca agar bisa dicek manual/diulang
             log_message "Action tidak ditemukan atau gagal parse/eksekusi, email TIDAK ditandai dibaca."
        fi
        # File temporary akan dihapus oleh trap
        return 0 # Email ditemukan dan diproses (berhasil atau gagal)
    else
        # Jika exit code 0 atau 1 tapi file kosong, berarti tidak ada email cocok
        # log_message "Tidak ada email baru yang cocok ditemukan." # Mungkin terlalu verbose untuk dilog setiap saat
        # File temporary akan dihapus oleh trap
        return 1 # Tidak ada email baru yang cocok
    fi
}

# Fungsi parsing body email
parse_email_body() {
    local body_file="$1"
    log_message "Parsing isi email dari $body_file"
    local action=""

    # Perbaiki grep: case-insensitive (-i), whole word (-w), quiet (-q)
    # Cari di seluruh file body
    if grep -qiw "BUY" "$body_file"; then
        action="BUY"
    elif grep -qiw "SELL" "$body_file"; then
        action="SELL"
    fi

    # Cek identifier lagi di body untuk keamanan ganda (opsional tapi bagus)
    # if ! grep -qF "$EMAIL_IDENTIFIER" "$body_file"; then
    #     log_message "WARNING: Action '$action' terdeteksi, tapi identifier '$EMAIL_IDENTIFIER' tidak ditemukan di body email ini. Mengabaikan."
    #     return 1 # Gagal Parse
    # fi

    if [[ "$action" == "BUY" ]]; then
        log_message "Action terdeteksi: BUY"
        execute_binance_order "BUY" "$TRADE_SYMBOL" "$TRADE_QUANTITY"
        return $? # Return status from execute_binance_order
    elif [[ "$action" == "SELL" ]]; then
        log_message "Action terdeteksi: SELL"
        execute_binance_order "SELL" "$TRADE_SYMBOL" "$TRADE_QUANTITY"
        return $? # Return status from execute_binance_order
    else
        log_message "WARNING: Tidak ada action 'BUY' atau 'SELL' yang valid terdeteksi dalam email yang cocok."
        return 1 # Gagal Parse (tidak ada action)
    fi
}

# Fungsi untuk menandai email sebagai sudah dibaca
mark_email_as_read() {
    log_message "Menandai email yang cocok sebagai sudah dibaca..."
    # Targetkan email Unread (~U) yang cocok dengan Subject (~S)
    "$EMAIL_CLIENT" \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail="" query_command=""' \
        -e 'push "<limit>~U ~S \"'${EMAIL_IDENTIFIER}'\"\n<clear-flag>N\n<sync-mailbox><exit>"' > /dev/null 2>&1
        # Alternatif jika identifier ada di body:
        # -e 'push "<limit>~U (~b \"'${EMAIL_IDENTIFIER}'\" | ~s \"'${EMAIL_IDENTIFIER}'\")\n<clear-flag>N\n<sync-mailbox><exit>"' > /dev/null 2>&1
    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        log_message "Perintah untuk menandai email dibaca telah dikirim (menargetkan email belum dibaca yang cocok)."
    else
        # Jangan terlalu khawatir jika exit code 1 (mungkin tidak ada yg cocok lagi/sudah terbaca proses lain)
        [[ $exit_code -ne 1 ]] && log_message "WARNING: Perintah $EMAIL_CLIENT untuk menandai email dibaca mungkin gagal (exit code: $exit_code)."
    fi
}

# Fungsi generate signature Binance
generate_binance_signature() {
    local query_string="$1"
    local secret="$2"
    # Pastikan tidak ada newline di akhir output signature
    echo -n "$query_string" | openssl dgst -sha256 -hmac "$secret" | sed 's/^.* //'
}

# Fungsi eksekusi order Binance
execute_binance_order() {
    local side="$1"
    local symbol="$2"
    local quantity="$3"
    local timestamp
    timestamp=$(date +%s%3N) # Waktu dalam milidetik

    if [[ -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$symbol" || -z "$quantity" ]]; then
        log_message "ERROR: Konfigurasi Binance tidak lengkap (API Key/Secret/Symbol/Quantity). Tidak bisa membuat order."
        return 1
    fi

    local api_endpoint="https://api.binance.com"
    local order_path="/api/v3/order"

    # --- PERBAIKAN API CALL ---
    # Parameter untuk order POST harus dikirim sebagai data payload (-d), bukan query string
    # Signature dihitung HANYA dari data payload ini.
    local params="symbol=${symbol}&side=${side}&type=MARKET&quantity=${quantity}×tamp=${timestamp}"
    local signature
    signature=$(generate_binance_signature "$params" "$BINANCE_SECRET_KEY")
    if [ -z "$signature" ]; then
        log_message "ERROR: Gagal menghasilkan signature Binance. Periksa error openssl di log."
        return 1
    fi

    # URL endpoint (tanpa parameter data)
    local full_url="${api_endpoint}${order_path}"
    # Parameter data + signature untuk dikirim
    local post_data="${params}&signature=${signature}"

    log_message "Mengirim order ke Binance: URL=$full_url DATA=$params" # Jangan log signature

    local response curl_exit_code http_code body
    # Kirim sebagai POST dengan data (-d)
    # Tambahkan timeout koneksi dan total waktu
    response=$(curl --connect-timeout 10 --max-time 20 -s -w "\n%{http_code}" \
                  -H "X-MBX-APIKEY: ${BINANCE_API_KEY}" \
                  -X POST "$full_url" -d "$post_data" 2>>"$LOG_FILE")
    curl_exit_code=$?

    # Ekstrak body dan http_code (lebih aman)
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d') # Hapus baris terakhir (http_code)

    if [ $curl_exit_code -ne 0 ]; then
        log_message "ERROR: curl gagal menghubungi Binance (Curl Exit code: $curl_exit_code). Periksa koneksi & log stderr curl."
        return 1
    fi

    log_message "Response Binance (HTTP $http_code): $body"

    # Cek jika http code adalah 2xx (sukses)
    if [[ "$http_code" =~ ^2 ]]; then
        # Coba parse response JSON dengan jq untuk info lebih detail
        local orderId status clientOrderId msg code
        orderId=$(echo "$body" | jq -r '.orderId // empty')
        status=$(echo "$body" | jq -r '.status // "UNKNOWN"')
        clientOrderId=$(echo "$body" | jq -r '.clientOrderId // empty')

        if [[ -n "$orderId" && "$status" != "UNKNOWN" ]]; then
            log_message "SUCCESS: Order $side $symbol $quantity berhasil. Order ID: $orderId, Client Order ID: $clientOrderId, Status: $status"
            # Bisa tambahkan notifikasi sukses di sini
            return 0
        else
            # Mungkin sukses tapi response tidak standar? Log warning.
            log_message "WARNING: HTTP $http_code diterima tapi orderId/status tidak terparsir dari response JSON. Body: $body"
            return 0 # Anggap sukses jika HTTP 2xx
        fi
    else
        # Jika HTTP code bukan 2xx, ini adalah error
        local err_code err_msg
        err_code=$(echo "$body" | jq -r '.code // "?"')
        err_msg=$(echo "$body" | jq -r '.msg // "Tidak ada pesan error spesifik dari Binance."')
        log_message "ERROR: Gagal menempatkan order $side $symbol. Kode Error Binance: $err_code Pesan: $err_msg"
        # Bisa tambahkan notifikasi GAGAL di sini
        return 1
    fi
}


# Fungsi Loop Utama Listener (untuk dijalankan di background)
listener_loop() {
    # Pastikan variabel konfigurasi di-export agar terbaca oleh sub-shell/proses background
    export GMAIL_USER GMAIL_APP_PASS BINANCE_API_KEY BINANCE_SECRET_KEY TRADE_SYMBOL TRADE_QUANTITY EMAIL_IDENTIFIER EMAIL_CLIENT LOG_FILE CHECK_INTERVAL

    # Ambil interval dari variabel environment (yang sudah di-export)
    local check_interval="${CHECK_INTERVAL:-60}"
    if ! [[ "$check_interval" =~ ^[1-9][0-9]*$ ]]; then
        # Log error jika interval tidak valid di dalam listener itu sendiri
        log_message "ERROR_LISTENER: Interval cek email tidak valid ('$check_interval'). Menggunakan default 60 detik."
        check_interval=60
    fi

    # Trap sinyal di dalam loop background agar bisa keluar dengan bersih
    trap 'log_message "Listener loop (PID $$) dihentikan oleh sinyal."; exit 0' SIGTERM SIGINT

    log_message "Listener loop dimulai (PID $$). Interval: ${check_interval} detik. Log: $LOG_FILE"
    while true; do
        log_message "Memulai siklus pengecekan email..." # Log awal siklus
        # Panggil check_email, tidak perlu cek return value secara eksplisit di sini
        # karena check_email sudah melakukan logging internal
        check_email

        log_message "Siklus selesai. Menunggu ${check_interval} detik..." # Log akhir siklus
        sleep "$check_interval"

        # --- Log Rotation/Trimming Sederhana ---
        local max_log_lines=1000
        local current_lines
        # Dapatkan jumlah baris, handle error jika wc gagal
        current_lines=$(wc -l < "$LOG_FILE" 2>/dev/null)
        if [[ "$current_lines" =~ ^[0-9]+$ ]]; then
            if [[ "$current_lines" -gt "$max_log_lines" ]]; then
                 log_message "INFO_LISTENER: File log ($LOG_FILE) melebihi $max_log_lines baris, memangkas..."
                 # Gunakan tail untuk ambil N baris terakhir, timpa file asli (lebih aman dari mv sementara)
                 tail -n "$max_log_lines" "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
                 if [ $? -ne 0 ]; then log_message "WARNING_LISTENER: Gagal memangkas file log."; fi
            fi
        else
             log_message "WARNING_LISTENER: Gagal mendapatkan jumlah baris log (output wc: '$current_lines')."
        fi
        # --- Akhir Log Rotation ---
    done
}

# --- Fungsi Kontrol Listener ---

# Cek apakah listener sedang berjalan berdasarkan PID file
is_listener_running() {
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE")
        # Cek apakah PID ada dan prosesnya benar-benar ada
        if [[ -n "$pid" ]] && ps -p "$pid" > /dev/null; then
            LISTENER_PID="$pid" # Update variabel global
            return 0 # Sedang berjalan
        else
            # File PID ada tapi proses tidak jalan (stale PID file)
            log_message "INFO: File PID ($PID_FILE) ditemukan tapi proses $pid tidak berjalan. Menghapus file PID basi."
            rm -f "$PID_FILE"
            LISTENER_PID=""
            return 1 # Tidak berjalan
        fi
    else
        LISTENER_PID=""
        return 1 # Tidak berjalan (tidak ada PID file)
    fi
}

# Memulai listener
start_listener() {
    if is_listener_running; then
        error_msg "Listener sudah berjalan (PID: $LISTENER_PID)."
        return 1
    fi

    # Pastikan konfigurasi sudah dimuat dan valid sebelum memulai
    if ! load_config; then
        error_msg "Konfigurasi belum lengkap atau gagal dimuat. Silakan cek Pengaturan. Tidak bisa memulai listener."
        return 1
    fi

    log_message "Memulai listener di background..."
    # --- PERBAIKAN UTAMA: Redirect stdout & stderr dari listener_loop ke LOG_FILE ---
    ( listener_loop ) >>"$LOG_FILE" 2>&1 &
    local pid=$!

    # Simpan PID ke file
    echo "$pid" > "$PID_FILE"
    if [ $? -ne 0 ]; then
       log_message "ERROR: Gagal menyimpan PID $pid ke $PID_FILE. Mencoba menghentikan listener..."
       kill "$pid" 2>/dev/null # Coba hentikan proses yang baru saja dimulai
       error_msg "Gagal menyimpan file PID. Listener tidak dimulai."
       LISTENER_PID="" # Pastikan PID global kosong
       return 1
    fi

    # Tunggu sebentar untuk memastikan proses benar-benar jalan (opsional)
    sleep 0.5
    if ! kill -0 "$pid" 2>/dev/null; then
        log_message "ERROR: Listener process (PID: $pid) tidak ditemukan setelah dimulai. Mungkin langsung exit? Cek log."
        error_msg "Listener gagal dimulai atau langsung berhenti. Periksa log ($LOG_FILE)."
        rm -f "$PID_FILE" # Hapus PID file jika proses gagal start
        LISTENER_PID=""
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
        # Jangan tampilkan error jika memang tidak ada yang perlu dihentikan
        info_msg "Listener tidak sedang berjalan."
        return 1 # Return 1 untuk menandakan tidak ada aksi
    fi

    log_message "Mengirim sinyal TERM ke listener (PID: $LISTENER_PID)..."
    if kill -TERM "$LISTENER_PID" 2>/dev/null; then
        local count=0
        local max_wait=10 # Tunggu maksimal 5 detik (10 * 0.5s)
        # Loop untuk menunggu proses berhenti
        while kill -0 "$LISTENER_PID" 2>/dev/null; do
            ((count++))
            if [ "$count" -gt "$max_wait" ]; then
                log_message "WARNING: Listener (PID: $LISTENER_PID) tidak berhenti dengan TERM setelah $((max_wait / 2)) detik. Mengirim KILL."
                kill -KILL "$LISTENER_PID" 2>/dev/null
                sleep 0.5 # Beri waktu sedikit setelah KILL
                break # Keluar loop setelah KILL
            fi
            sleep 0.5
        done

        # Cek lagi apakah proses sudah berhenti
        if ! kill -0 "$LISTENER_PID" 2>/dev/null; then
            log_message "Listener (PID: $LISTENER_PID) berhasil dihentikan."
            info_msg "Listener (PID: $LISTENER_PID) berhasil dihentikan."
        else
            log_message "ERROR: Gagal menghentikan listener (PID: $LISTENER_PID) bahkan dengan KILL. Mungkin perlu intervensi manual."
            error_msg "Gagal menghentikan listener (PID: $LISTENER_PID) sepenuhnya."
            # Jangan hapus PID file jika gagal stop, sebagai penanda
            return 1 # Gagal stop
        fi
    else
        log_message "WARNING: Gagal mengirim sinyal TERM ke PID $LISTENER_PID (mungkin sudah berhenti atau tidak ada izin)."
        # Cek apakah prosesnya memang sudah tidak ada
        if ! kill -0 "$LISTENER_PID" 2>/dev/null; then
            info_msg "Listener (PID: $LISTENER_PID) sepertinya sudah berhenti."
        else
            error_msg "Gagal mengirim sinyal ke listener (PID: $LISTENER_PID)."
            return 1 # Gagal kirim sinyal
        fi
    fi

    # Hapus file PID hanya jika proses berhasil dihentikan atau dipastikan tidak ada
    rm -f "$PID_FILE"
    LISTENER_PID="" # Reset PID global
    return 0 # Berhasil stop atau proses memang sudah tidak ada
}


# Menampilkan log real-time menggunakan tailboxbg
show_live_log() {
    if ! is_listener_running; then
        error_msg "Listener tidak sedang berjalan. Tidak ada log real-time untuk ditampilkan."
        return 1
    fi
     # Cek apakah file log ada
     if [[ ! -f "$LOG_FILE" ]]; then
        error_msg "File log ($LOG_FILE) tidak ditemukan."
        return 1
     fi
     clear
     # Gunakan --tailboxbg untuk tampilan background non-blocking
     # --no-kill penting agar menutup window tidak membunuh proses tail
     dialog --title "Email Listener - Log Real-time (PID: $LISTENER_PID)" \
            --no-kill \
            --tailboxbg "$LOG_FILE" 25 90
     # Setelah dialog ditutup (user tekan OK/Enter), kembali ke menu
     log_message "Menutup tampilan log real-time (listener tetap berjalan)."
     clear # Bersihkan sisa dialog
}

# Fungsi Tampilkan Log Statis (dari awal file)
view_static_log() {
    clear
    if [ -f "$LOG_FILE" ] && [ -s "$LOG_FILE" ]; then # Cek file ada dan tidak kosong
        # Gunakan --textbox untuk view statis
        dialog --title "Log Aktivitas Statis ($LOG_FILE)" --cr-wrap --textbox "$LOG_FILE" 25 90
    else
        info_msg "File log ($LOG_FILE) belum ada atau kosong."
    fi
    clear # Bersihkan sisa dialog
}

# --- Fungsi Menu Utama ---
main_menu() {
    while true; do
        clear
        # Selalu cek status listener di awal loop untuk update menu
        is_listener_running
        local listener_status_msg=""
        local menu_items=() # Array untuk menyimpan opsi menu

        # Bangun menu secara dinamis berdasarkan status listener
        if [[ -n "$LISTENER_PID" ]]; then
            # Listener Aktif
            listener_status_msg=" (Listener Aktif - PID: $LISTENER_PID)"
            menu_items+=("1" "Lihat Log Listener (Real-time)"
                         "2" "Hentikan Listener"
                         "3" "Pengaturan (Nonaktif)" # Opsi nonaktif
                         "4" "Lihat Log Statis Keseluruhan"
                         "5" "Keluar")
            local menu_height=18
            local list_height=5
        else
            # Listener Tidak Aktif
            listener_status_msg=" (Listener Tidak Aktif)"
            menu_items+=("1" "Mulai Listener"
                         "2" "Pengaturan"
                         "3" "Lihat Log Statis Keseluruhan"
                         "4" "Keluar")
            local menu_height=17
            local list_height=4
        fi

        # Tampilkan dialog menu
        CHOICE=$(dialog --clear --stdout \
                        --title "Email Trader v1.5 - Menu Utama$listener_status_msg" \
                        --cancel-label "Keluar" \
                        --menu "Pilih tindakan:" $menu_height 75 $list_height "${menu_items[@]}")

        local exit_status=$?

        # Handle Cancel (Esc) atau tombol Keluar dari dialog
        if [[ $exit_status -ne 0 ]]; then
            CHOICE="Keluar_Signal" # Tandai sebagai keluar via cancel/esc
        fi

        # Proses pilihan berdasarkan status listener saat menu ditampilkan
        if [[ -n "$LISTENER_PID" ]]; then # === Listener Aktif ===
            case "$CHOICE" in
                1) show_live_log ;;
                2) stop_listener ;;
                3) error_msg "Listener harus dihentikan terlebih dahulu untuk mengakses Pengaturan." ;;
                4) view_static_log ;;
                5 | "Keluar_Signal") # Handle pilihan 5 atau Esc/Cancel
                    clear
                    echo "Menghentikan listener sebelum keluar..."
                    stop_listener # Coba hentikan dengan bersih
                    echo "Script dihentikan."
                    log_message "--- Script Dihentikan via Menu Keluar (Listener Aktif) ---"
                    exit 0 # Keluar dari script
                    ;;
                *) error_msg "Pilihan tidak valid." ;; # Seharusnya tidak terjadi dengan menu
            esac
        else # === Listener Tidak Aktif ===
             case "$CHOICE" in
                1)
                    start_listener
                    # Optional: Jika start berhasil, langsung tampilkan log?
                    # if is_listener_running; then
                    #    sleep 1 # Beri waktu listener mulai log
                    #    show_live_log
                    # fi
                    ;;
                2) configure_settings ;;
                3) view_static_log ;;
                4 | "Keluar_Signal") # Handle pilihan 4 atau Esc/Cancel
                    clear
                    echo "Script dihentikan."
                    log_message "--- Script Dihentikan (Listener tidak aktif) ---"
                    exit 0 # Keluar dari script
                    ;;
                *) error_msg "Pilihan tidak valid." ;; # Seharusnya tidak terjadi
            esac
        fi
        # Pause sebentar sebelum loop berikutnya (opsional, jika perlu lihat pesan info/error)
        # read -p "Tekan Enter untuk kembali ke menu..." -t 5 # Timeout 5 detik
    done
}

# --- Main Program Execution ---

# Setup trap untuk exit bersih saat script dihentikan (Ctrl+C, kill, etc.)
cleanup() {
    local exit_code=$?
    echo # Newline setelah potensi karakter Ctrl+C (^C)
    log_message "--- Script Menerima Sinyal Exit (Kode: $exit_code) ---"
    # Cek apakah listener *masih* berjalan saat cleanup dipanggil
    # Gunakan pengecekan langsung, jangan panggil is_listener_running() lagi di trap
    local current_pid=""
    if [ -f "$PID_FILE" ]; then current_pid=$(cat "$PID_FILE"); fi

    if [[ -n "$current_pid" ]] && kill -0 "$current_pid" 2>/dev/null; then
        echo " Membersihkan: Menghentikan listener (PID: $current_pid) sebelum keluar..."
        # Kirim TERM, tunggu sebentar, paksa KILL jika perlu
        kill -TERM "$current_pid" &> /dev/null
        sleep 0.5
        kill -KILL "$current_pid" &> /dev/null # Pastikan berhenti
        rm -f "$PID_FILE" # Hapus PID file setelah kill
        echo " Membersihkan: Listener dihentikan."
        log_message "Listener (PID: $current_pid) dihentikan paksa saat script exit/cleanup."
    elif [[ -f "$PID_FILE" ]]; then
         # Jika file PID ada tapi proses tidak ada, hapus saja filenya
         rm -f "$PID_FILE"
         log_message "Membersihkan: Menghapus file PID basi ($PID_FILE)."
    fi
    echo " Script selesai."
    # Pastikan terminal kembali normal jika dialog terinterupsi
    stty sane
    clear
    # Exit dengan kode asli jika bukan 0, atau 130 untuk Ctrl+C (SIGINT)
    if [[ "$exit_code" == "0" ]]; then exit 0; else exit $((128 + exit_code)); fi
}
# Tangkap sinyal INT (Ctrl+C), TERM (kill), dan EXIT (keluar normal/error)
trap cleanup INT TERM EXIT

# --- Inisialisasi ---
clear
echo "Memulai Email Trader v1.5..."
check_deps
log_message "--- Script Email Trader v1.5 Dimulai (PID: $SCRIPT_MAIN_PID) ---"

# Cek status listener saat startup
is_listener_running
if [[ -n "$LISTENER_PID" ]]; then
    log_message "INFO: Script dimulai, listener dari sesi sebelumnya terdeteksi aktif (PID: $LISTENER_PID)."
    info_msg "Listener dari sesi sebelumnya terdeteksi aktif (PID: $LISTENER_PID).\nAnda dapat menghentikannya dari menu."
    sleep 2 # Beri waktu user membaca pesan
fi

# Coba load konfigurasi awal
if ! load_config; then
    # Hanya tampilkan dialog setup awal jika listener TIDAK sedang aktif
    if ! is_listener_running; then
        clear
        dialog --title "Setup Awal Diperlukan" \
            --yesno "File konfigurasi ($CONFIG_FILE) tidak ditemukan atau tidak lengkap.\n\nApakah Anda ingin melakukan konfigurasi sekarang?" 10 70
        response=$?
        case $response in
            0) # Yes
                if ! configure_settings; then
                    clear
                    echo "Konfigurasi awal dibatalkan atau gagal. Script tidak dapat dilanjutkan."
                    log_message "FATAL: Konfigurasi awal gagal/dibatalkan. Script berhenti."
                    exit 1
                fi
                # Coba load lagi setelah konfigurasi berhasil
                if ! load_config; then
                    clear
                    echo "Gagal memuat konfigurasi bahkan setelah setup awal. Script berhenti."
                    log_message "FATAL: Gagal memuat konfigurasi setelah setup. Script berhenti."
                    exit 1
                fi
                ;;
            1|255) # No atau Esc
                clear
                echo "Konfigurasi awal dilewati. Script tidak dapat berfungsi tanpa konfigurasi."
                log_message "FATAL: Konfigurasi awal dilewati. Script berhenti."
                exit 1
                ;;
        esac
    else
        # Jika listener aktif tapi config gagal load (misal file rusak/dihapus)
        log_message "WARNING: Konfigurasi gagal dimuat, tapi listener sedang aktif (PID: $LISTENER_PID). Pengaturan tidak bisa diakses sampai listener dihentikan & config diperbaiki."
        error_msg "WARNING: Konfigurasi gagal dimuat ($CONFIG_FILE).\nListener dari sesi sebelumnya mungkin berjalan dengan konfigurasi lama.\nHentikan listener dan perbaiki konfigurasi jika perlu."
        sleep 3
    fi
fi

# Masuk ke menu utama
main_menu

# Exit normal seharusnya ditangani oleh trap EXIT
exit 0
