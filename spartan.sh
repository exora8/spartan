#!/usr/bin/env bash

# Script Email Listener & Binance Trader
# Versi: 1.5 (Fix CLI Overwrite Bug & UI Polish)
# Author: [Nama Kamu/AI] & Kontributor

# --- Konfigurasi Awal ---
CONFIG_FILE="$HOME/.email_trader_rc"
LOG_FILE="/tmp/email_trader.log"
PID_FILE="/tmp/email_trader.pid" # File untuk menyimpan PID listener
touch "$LOG_FILE" # Pastikan file log ada
chmod 600 "$LOG_FILE" # Amankan log jika perlu
chmod 600 "$PID_FILE" 2>/dev/null # Amankan file PID jika sudah ada

# Identifier Email yang Dicari (Subject atau Body)
EMAIL_IDENTIFIER="Exora AI (V5 SPOT + SR Filter) (1M)" # Contoh, ganti sesuai kebutuhan

# --- Variabel Global ---
LISTENER_PID="" # Akan diisi dari PID_FILE saat script start
SCRIPT_MAIN_PID=$$ # Simpan PID script utama

# --- Konstanta Tampilan ---
DIALOG_BACKTITLE="Email->Binance Trader v1.5"

# --- Fungsi ---

# Fungsi untuk menampilkan pesan error dengan dialog
error_msg() {
    dialog --backtitle "$DIALOG_BACKTITLE" --title "Error" --msgbox "$1" 8 60
    log_message "ERROR_DIALOG: $1"
}

# Fungsi untuk menampilkan info dengan dialog
info_msg() {
    dialog --backtitle "$DIALOG_BACKTITLE" --title "Info" --msgbox "$1" 8 60
}

# Fungsi untuk menampilkan info sementara (auto-close)
infobox_msg() {
    dialog --backtitle "$DIALOG_BACKTITLE" --title "Info" --infobox "$1" 5 50
    sleep 2 # Beri waktu user untuk membaca sebelum hilang
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
            dialog --backtitle "$DIALOG_BACKTITLE" --title "Error Dependensi" --cr-wrap --msgbox "Dependensi berikut tidak ditemukan:\n\n$(printf -- '- %s\n' "${missing_deps[@]}")\n\nSilakan install terlebih dahulu." 15 70
        fi
        exit 1
    fi
    EMAIL_CLIENT=$(command -v neomutt || command -v mutt)
}

# Fungsi load konfigurasi
load_config() {
    if [ -f "$CONFIG_FILE" ]; then
        chmod 600 "$CONFIG_FILE" # Pastikan permission benar
        GMAIL_USER=$(grep -Po "^GMAIL_USER *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        GMAIL_APP_PASS=$(grep -Po "^GMAIL_APP_PASS *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        BINANCE_API_KEY=$(grep -Po "^BINANCE_API_KEY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        BINANCE_SECRET_KEY=$(grep -Po "^BINANCE_SECRET_KEY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        TRADE_SYMBOL=$(grep -Po "^TRADE_SYMBOL *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        TRADE_QUANTITY=$(grep -Po "^TRADE_QUANTITY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        CHECK_INTERVAL=$(grep -Po "^CHECK_INTERVAL *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)

        if [[ -z "$GMAIL_USER" || -z "$GMAIL_APP_PASS" || -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$TRADE_SYMBOL" || -z "$TRADE_QUANTITY" || -z "$CHECK_INTERVAL" ]]; then
            log_message "WARNING: File konfigurasi $CONFIG_FILE ada tapi tidak lengkap atau gagal parse."
            return 1 # Gagal load
        fi
        log_message "Konfigurasi berhasil dimuat dari $CONFIG_FILE."
        CHECK_INTERVAL="${CHECK_INTERVAL:-60}"
        # Export variabel agar bisa diakses oleh proses background (listener_loop)
        export GMAIL_USER GMAIL_APP_PASS BINANCE_API_KEY BINANCE_SECRET_KEY TRADE_SYMBOL TRADE_QUANTITY EMAIL_IDENTIFIER EMAIL_CLIENT LOG_FILE CHECK_INTERVAL
        return 0 # Sukses load
    else
        log_message "INFO: File konfigurasi $CONFIG_FILE tidak ditemukan."
        return 1 # Gagal load
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
    info_msg "Konfigurasi berhasil disimpan."
    load_config # Reload dan export variabel setelah disimpan
}

# Fungsi konfigurasi interaktif
configure_settings() {
    if is_listener_running; then
        error_msg "Listener sedang aktif (PID: $LISTENER_PID). Hentikan listener terlebih dahulu sebelum mengubah konfigurasi."
        return 1
    fi

    # Muat nilai saat ini jika ada, default ke string kosong jika tidak ada
    load_config
    local temp_gmail_user="${GMAIL_USER:-}"
    local temp_gmail_pass="${GMAIL_APP_PASS:-}"
    local temp_api_key="${BINANCE_API_KEY:-}"
    local temp_secret_key="${BINANCE_SECRET_KEY:-}"
    local temp_symbol="${TRADE_SYMBOL:-}"
    local temp_quantity="${TRADE_QUANTITY:-}"
    local temp_interval="${CHECK_INTERVAL:-60}" # Default interval 60

    local input_gmail_user input_gmail_pass input_api_key input_secret_key input_symbol input_quantity input_interval exit_status

    # Menggunakan temporary file untuk menampung input dialog
    local temp_file
    temp_file=$(mktemp) || { error_msg "Gagal membuat file temporary untuk konfigurasi."; return 1; }
    trap 'rm -f "$temp_file"' RETURN # Hapus temp file saat fungsi selesai

    dialog --backtitle "$DIALOG_BACKTITLE" --title "Konfigurasi Akun & API" \
        --form "\nMasukkan detail akun dan API:" 20 70 0 \
        "Alamat Gmail:"          1 1 "$temp_gmail_user"      1 25 60 0 \
        "Gmail App Password:"    2 1 "$temp_gmail_pass"      2 25 60 0 \
        "Binance API Key:"       3 1 "$temp_api_key"         3 25 60 0 \
        "Binance Secret Key:"    4 1 "$temp_secret_key"      4 25 60 0 \
        "Simbol Trading (cth: BTCUSDT):" 5 1 "$temp_symbol"  5 25 60 0 \
        "Quantity per Trade (cth: 0.001):" 6 1 "$temp_quantity" 6 25 60 0 \
        "Interval Cek Email (detik):" 7 1 "$temp_interval" 7 25 60 0 \
        2>"$temp_file"

    exit_status=$?
    if [ $exit_status -ne 0 ]; then
        rm -f "$temp_file"
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
    rm -f "$temp_file" # Hapus temp file setelah dibaca

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

    # Update variabel global (belum disimpan ke file)
    GMAIL_USER="$input_gmail_user"
    GMAIL_APP_PASS="$input_gmail_pass"
    BINANCE_API_KEY="$input_api_key"
    BINANCE_SECRET_KEY="$input_secret_key"
    TRADE_SYMBOL=$(echo "$input_symbol" | tr 'a-z' 'A-Z') # Uppercase symbol
    TRADE_QUANTITY="$input_quantity"
    CHECK_INTERVAL="$input_interval"

    save_config # Simpan konfigurasi ke file
    return 0
}

# Fungsi untuk logging ke file
log_message() {
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    # Tambahkan PID jika itu BUKAN PID script utama (artinya dari listener)
    local pid_info=""
    if [[ -n "$$" && "$$" != "$SCRIPT_MAIN_PID" ]]; then
       pid_info=" [PID $$]"
    fi
    echo "[$timestamp]$pid_info $1" >> "${LOG_FILE:-/tmp/email_trader_fallback.log}"
}

# --- Fungsi Background Listener ---

# Fungsi cek email baru yang cocok (dipanggil oleh listener_loop)
check_email() {
    log_message "Mencari email baru dari $GMAIL_USER..." # Log lebih singkat
    local email_body_file
    email_body_file=$(mktemp) || { log_message "ERROR: Gagal membuat file temporary untuk email."; return 1; }
    trap 'rm -f "$email_body_file"' RETURN # Pastikan temp file dihapus

    # Timeout ditambahkan ke neomutt/mutt untuk mencegah hang
    timeout 30 "$EMAIL_CLIENT" \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail="" net_timeout=15' \
        -e 'push "<limit>~N (~b \"'${EMAIL_IDENTIFIER}'\" | ~s \"'${EMAIL_IDENTIFIER}'\")\n<pipe-message>cat > '${email_body_file}'\n<exit>"'
    local mutt_exit_code=$?

    # Hanya log error jika bukan exit code 0 (sukses), 1 (no match), atau 124 (timeout)
    if [[ "$mutt_exit_code" -ne 0 && "$mutt_exit_code" -ne 1 && "$mutt_exit_code" -ne 124 ]]; then
        log_message "WARNING: Perintah $EMAIL_CLIENT keluar dengan kode $mutt_exit_code (Mungkin error koneksi/konfigurasi)"
    elif [[ "$mutt_exit_code" -eq 124 ]]; then
        log_message "WARNING: Timeout saat cek email. Melewati siklus ini."
        return 1 # Gagal cek
    fi

    if [ -s "$email_body_file" ]; then
        log_message "Email cocok ditemukan. Memproses..."
        if parse_email_body "$email_body_file"; then
             mark_email_as_read
             return 0 # Sukses proses
        else
             log_message "Action tidak ditemukan/gagal parse/order gagal, email tidak ditandai dibaca."
             return 1 # Gagal proses
        fi
    else
        log_message "Tidak ada email baru yang cocok." # Tidak perlu cek exit code lagi
        return 1 # Tidak ada email
    fi
}

# Fungsi parsing body email (dipanggil oleh check_email)
parse_email_body() {
    local body_file="$1"
    log_message "Parsing isi email..."
    local action=""

    if grep -qiw "buy" "$body_file"; then action="BUY";
    elif grep -qiw "sell" "$body_file"; then action="SELL";
    fi

    if ! grep -qF "$EMAIL_IDENTIFIER" "$body_file"; then # Gunakan -F untuk string literal
        log_message "WARNING: Action '$action' terdeteksi, tapi identifier '$EMAIL_IDENTIFIER' tidak ditemukan di body. Abaikan."
        return 1
    fi

    if [[ "$action" == "BUY" ]]; then
        log_message "Action terdeteksi: BUY. Eksekusi order..."
        execute_binance_order "BUY"
        return $?
    elif [[ "$action" == "SELL" ]]; then
        log_message "Action terdeteksi: SELL. Eksekusi order..."
        execute_binance_order "SELL"
        return $?
    else
        log_message "WARNING: Tidak ada action 'BUY'/'SELL' valid di email cocok."
        return 1
    fi
}

# Fungsi untuk menandai email sebagai sudah dibaca (dipanggil oleh check_email)
mark_email_as_read() {
    log_message "Menandai email sebagai sudah dibaca..."
    # Targetkan email yang UNREAD dan cocok
    timeout 15 "$EMAIL_CLIENT" \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail="" net_timeout=10' \
        -e 'push "<limit>~U (~b \"'${EMAIL_IDENTIFIER}'\" | ~s \"'${EMAIL_IDENTIFIER}'\")\n<tag-prefix><clear-flag>N<untag-pattern>.\n<sync-mailbox><exit>"'
    local exit_code=$?
    if [[ $exit_code -eq 0 ]]; then
        log_message "Email berhasil ditandai dibaca."
    elif [[ $exit_code -eq 124 ]]; then
         log_message "WARNING: Timeout saat menandai email dibaca."
    elif [[ $exit_code -ne 1 ]]; then # Abaikan exit code 1 (no match)
        log_message "WARNING: Gagal menandai email dibaca (exit code: $exit_code)."
    fi
}

# Fungsi generate signature Binance (dipanggil oleh execute_binance_order)
generate_binance_signature() {
    local query_string="$1" secret="$2"
    echo -n "$query_string" | openssl dgst -sha256 -hmac "$secret" | sed 's/^.* //'
}

# Fungsi eksekusi order Binance (dipanggil oleh parse_email_body)
execute_binance_order() {
    local side="$1" timestamp params signature full_url response curl_exit_code http_code body orderId status clientOrderId err_code err_msg
    timestamp=$(date +%s%3N)

    if [[ -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$TRADE_SYMBOL" || -z "$TRADE_QUANTITY" ]]; then
        log_message "ERROR: Konfigurasi Binance tidak lengkap. Tidak bisa membuat order."
        return 1
    fi

    local api_endpoint="https://api.binance.com" order_path="/api/v3/order"
    params="symbol=${TRADE_SYMBOL}&side=${side}&type=MARKET&quantity=${TRADE_QUANTITY}×tamp=${timestamp}"
    signature=$(generate_binance_signature "$params" "$BINANCE_SECRET_KEY")

    if [ -z "$signature" ]; then
        log_message "ERROR: Gagal menghasilkan signature Binance."
        return 1
    fi

    full_url="${api_endpoint}${order_path}?${params}&signature=${signature}"
    log_message "Mengirim order: ${side} ${TRADE_QUANTITY} ${TRADE_SYMBOL}..."

    # Curl dengan timeout dan logging stderr ke log utama jika error
    response=$(curl --connect-timeout 10 --max-time 20 -s -w "\n%{http_code}" -H "X-MBX-APIKEY: ${BINANCE_API_KEY}" -X POST "$full_url" 2>> "$LOG_FILE.curl_error")
    curl_exit_code=$?
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d') # Semua kecuali baris terakhir

    if [ $curl_exit_code -ne 0 ]; then
        log_message "ERROR: curl gagal (Exit code: $curl_exit_code). Cek $LOG_FILE.curl_error"
        # Optionally log the error details here from the file
        # head -n 5 "$LOG_FILE.curl_error" >> "$LOG_FILE"
        return 1
    fi
    rm -f "$LOG_FILE.curl_error" # Hapus file error jika curl sukses

    log_message "Respon Binance (HTTP $http_code): $body"

    if [[ "$http_code" =~ ^2 ]]; then
        orderId=$(echo "$body" | jq -r '.orderId // empty')
        status=$(echo "$body" | jq -r '.status // "UNKNOWN"')
        clientOrderId=$(echo "$body" | jq -r '.clientOrderId // empty')
        if [ -n "$orderId" ]; then
            log_message "SUCCESS: Order ${side} ${TRADE_QUANTITY} ${TRADE_SYMBOL} berhasil. ID: ${orderId}."
            return 0
        else
            log_message "WARNING: Order ${side} ${TRADE_QUANTITY} ${TRADE_SYMBOL}. HTTP 2xx tapi tidak ada Order ID. Body: $body"
            return 0 # Anggap sukses jika 2xx
        fi
    else
        err_code=$(echo "$body" | jq -r '.code // "?"')
        err_msg=$(echo "$body" | jq -r '.msg // "No specific error message."')
        log_message "ERROR: Order ${side} ${TRADE_QUANTITY} ${TRADE_SYMBOL} GAGAL. Code: $err_code Msg: $err_msg"
        return 1
    fi
}

# Fungsi Loop Utama Listener (dijalankan di background)
listener_loop() {
    # Trap sinyal di dalam loop background
    trap 'log_message "Listener loop (PID $$) dihentikan oleh sinyal."; exit 0' SIGTERM SIGINT

    # Ambil interval dari variabel environment yang sudah di-export
    local check_interval="${CHECK_INTERVAL:-60}"
    if ! [[ "$check_interval" =~ ^[1-9][0-9]*$ ]]; then
        log_message "WARNING: Interval cek email tidak valid ($check_interval) di listener loop. Menggunakan default 60 detik."
        check_interval=60
    fi

    log_message "Listener loop dimulai (PID $$). Interval: ${check_interval} detik."
    while true; do
        log_message "Memulai siklus pengecekan email..."
        check_email # check_email sudah handle logging internalnya
        log_message "Siklus selesai. Menunggu ${check_interval} detik..."
        sleep "$check_interval"

        # Log trimming (optional, bisa dinonaktifkan jika tidak perlu)
        local max_log_lines=1000 current_lines
        current_lines=$(wc -l < "$LOG_FILE")
        if [[ "$current_lines" =~ ^[0-9]+$ && "$current_lines" -gt "$max_log_lines" ]]; then
             log_message "INFO: Memangkas log ke $max_log_lines baris..."
             tail -n "$max_log_lines" "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
             if [ $? -ne 0 ]; then log_message "WARNING: Gagal memangkas file log."; fi
        fi
    done
}

# --- Fungsi Kontrol Listener ---

# Cek apakah listener sedang berjalan via PID file
is_listener_running() {
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE")
        # Cek apakah PID ada dan proses dengan PID tersebut masih berjalan
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            LISTENER_PID="$pid" # Update variabel global
            return 0 # Ya, sedang berjalan
        else
            log_message "INFO: File PID ($PID_FILE) ada tapi proses $pid tidak berjalan. Menghapus file PID basi."
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

    # Load konfigurasi (dan export variabel) sebelum memulai
    if ! load_config; then
        error_msg "Konfigurasi belum lengkap atau gagal dimuat. Tidak bisa memulai listener. Silakan cek 'Pengaturan'."
        return 1
    fi

    infobox_msg "Memulai listener di background..."
    log_message "Mencoba memulai listener di background..."

    # === PERUBAHAN KUNCI: REDIRECT OUTPUT BACKGROUND ===
    # Redirect stdout dan stderr ke /dev/null agar tidak mengganggu terminal utama
    # Logging HANYA dilakukan via fungsi log_message() di dalam listener_loop
    (listener_loop) >/dev/null 2>&1 &
    local pid=$!

    # Cek apakah proses background berhasil dimulai
    sleep 0.5 # Beri sedikit waktu untuk proses dimulai/gagal
    if ! kill -0 "$pid" 2>/dev/null; then
        log_message "ERROR: Gagal memulai proses listener di background."
        error_msg "Gagal memulai listener. Cek log ($LOG_FILE) untuk detail."
        rm -f "$PID_FILE" # Pastikan tidak ada file PID jika gagal start
        return 1
    fi

    # Simpan PID ke file
    echo "$pid" > "$PID_FILE"
    if [ $? -ne 0 ]; then
       log_message "ERROR: Gagal menyimpan PID $pid ke $PID_FILE. Menghentikan listener..."
       kill "$pid" 2>/dev/null # Coba hentikan proses yg mungkin terlanjur jalan
       error_msg "Gagal menyimpan file PID. Listener mungkin tidak berjalan dengan benar."
       return 1
    fi
    chmod 600 "$PID_FILE" # Amankan file PID

    LISTENER_PID="$pid"
    log_message "Listener berhasil dimulai (PID: $LISTENER_PID)."
    infobox_msg "Listener berhasil dimulai (PID: $LISTENER_PID)."
    return 0
}

# Menghentikan listener
stop_listener() {
    if ! is_listener_running; then
        error_msg "Listener tidak sedang berjalan."
        return 1
    fi

    infobox_msg "Menghentikan listener (PID: $LISTENER_PID)..."
    log_message "Mengirim sinyal TERM ke listener (PID: $LISTENER_PID)..."
    if kill -TERM "$LISTENER_PID" 2>/dev/null; then
        local count=0 wait_seconds=5 # Tunggu maksimal 5 detik
        echo -n "Menunggu listener berhenti: "
        while kill -0 "$LISTENER_PID" 2>/dev/null; do
            ((count++))
            if [ "$count" -gt $((wait_seconds * 2)) ]; then # Cek 2x per detik
                echo "[TIMEOUT]"
                log_message "WARNING: Listener (PID: $LISTENER_PID) tidak berhenti dengan TERM setelah ${wait_seconds} detik. Mengirim KILL."
                kill -KILL "$LISTENER_PID" 2>/dev/null
                sleep 0.5 # Beri waktu untuk KILL
                break
            fi
            echo -n "."
            sleep 0.5
        done
        echo # Newline setelah titik-titik

        if ! kill -0 "$LISTENER_PID" 2>/dev/null; then
            log_message "Listener (PID: $LISTENER_PID) berhasil dihentikan."
            info_msg "Listener (PID: $LISTENER_PID) berhasil dihentikan."
        else
            log_message "ERROR: Gagal menghentikan listener (PID: $LISTENER_PID) bahkan dengan KILL."
            error_msg "Gagal menghentikan listener (PID: $LISTENER_PID). Mungkin perlu kill manual."
        fi
    else
        log_message "WARNING: Gagal mengirim sinyal TERM ke PID $LISTENER_PID (mungkin sudah berhenti sebelumnya)."
        info_msg "Gagal mengirim sinyal ke listener (mungkin sudah berhenti)."
    fi

    # Hapus file PID setelah proses dipastikan berhenti atau gagal dihentikan
    rm -f "$PID_FILE"
    LISTENER_PID="" # Reset variabel global
    clear # Bersihkan layar setelah stop
    return 0
}

# Menampilkan log real-time (tanpa menghentikan listener)
show_live_log() {
    if ! is_listener_running; then
        error_msg "Listener tidak sedang berjalan. Tidak ada log real-time."
        return 1
    fi
     dialog --backtitle "$DIALOG_BACKTITLE" \
            --title "Log Listener Real-time (PID: $LISTENER_PID) - [Tekan Esc/Cancel untuk Kembali]" \
            --no-kill \
            --tailboxbg "$LOG_FILE" 25 90
     # Penting: Menutup window ini TIDAK menghentikan listener
     log_message "Menutup tampilan log real-time (listener tetap berjalan)."
     clear # Bersihkan layar setelah dialog log ditutup
}

# Fungsi Tampilkan Log Statis
view_static_log() {
    if [ ! -f "$LOG_FILE" ] || [ ! -s "$LOG_FILE" ]; then
         info_msg "File log ($LOG_FILE) belum ada atau kosong."
         return
    fi
    dialog --backtitle "$DIALOG_BACKTITLE" \
           --title "Log Aktivitas Statis ($LOG_FILE)" \
           --textbox "$LOG_FILE" 25 90
    clear # Bersihkan layar setelah dialog log ditutup
}

# --- Fungsi Menu Utama ---
main_menu() {
    while true; do
        # Selalu cek status listener di awal setiap loop menu
        is_listener_running

        local listener_status_msg menu_items CHOICE exit_status menu_height=6

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
             menu_height=5 # Sedikit lebih pendek jika menu lebih sedikit
        fi

        # Gunakan temporary file untuk output dialog agar tidak tercampur
        local choice_file
        choice_file=$(mktemp) || { echo "ERROR: Cannot create temp file for menu choice." >&2; exit 1; }
        trap 'rm -f "$choice_file"' RETURN

        dialog --backtitle "$DIALOG_BACKTITLE" --clear --stdout \
               --title "Menu Utama - Status: $listener_status_msg" \
               --cancel-label "Keluar" \
               --menu "Pilih tindakan:" 18 75 $menu_height "${menu_items[@]}" 2>"$choice_file"

        exit_status=$?
        CHOICE=$(cat "$choice_file")
        rm -f "$choice_file" # Hapus file temp

        # Handle Cancel/Esc (exit_status != 0) atau pilihan Keluar eksplisit
        if [[ $exit_status -ne 0 ]]; then
            # Jika listener aktif, beri konfirmasi sebelum keluar & stop
            if is_listener_running; then
                dialog --backtitle "$DIALOG_BACKTITLE" --yesno "Listener sedang aktif (PID: $LISTENER_PID).\n\nAnda yakin ingin keluar dan menghentikan listener?" 8 60
                if [ $? -eq 0 ]; then # User pilih Yes
                    CHOICE="Keluar"
                else
                    continue # Kembali ke loop menu
                fi
            else
                CHOICE="Keluar" # Langsung keluar jika listener tidak aktif
            fi
        fi

        # Proses pilihan berdasarkan status listener saat menu ditampilkan
        if [[ "$listener_status_msg" == *"AKTIF"* ]]; then # Cek status dari pesan
            case "$CHOICE" in
                1) show_live_log ;;
                2) stop_listener ;;
                3) error_msg "Listener harus dihentikan untuk masuk ke Pengaturan." ;;
                4) view_static_log ;;
                5|"Keluar")
                    stop_listener # Fungsi ini akan menangani pesan jika sudah berhenti
                    clear
                    echo "Script dihentikan."
                    log_message "--- Script Dihentikan via Menu Keluar (Listener Dimatikan) ---"
                    exit 0
                    ;;
                *) error_msg "Pilihan tidak valid." ;;
            esac
        else # Listener TIDAK AKTIF
             case "$CHOICE" in
                1)
                    start_listener
                    # Jika berhasil start, tawarkan untuk lihat log
                    if is_listener_running; then
                        dialog --backtitle "$DIALOG_BACKTITLE" --yesno "Listener berhasil dimulai (PID: $LISTENER_PID).\n\nLihat log real-time sekarang?" 8 60
                        if [ $? -eq 0 ]; then
                           show_live_log
                        fi
                    fi
                    ;;
                2) configure_settings ;;
                3) view_static_log ;;
                4|"Keluar")
                    clear
                    echo "Script dihentikan."
                    log_message "--- Script Dihentikan (Listener tidak aktif) ---"
                    exit 0
                    ;;
                *) error_msg "Pilihan tidak valid." ;;
            esac
        fi
        # Pause sebentar sebelum redraw menu (optional, bisa dihapus)
        # sleep 0.1
    done
}

# --- Main Program Execution ---

# Setup trap untuk exit bersih (dipanggil saat SIGINT, SIGTERM, atau EXIT normal)
cleanup() {
    local exit_code=$?
    # Pastikan kita tidak di dalam subshell atau fungsi trap lain
    # Hanya jalankan cleanup penuh dari proses utama
    if [[ "$$" == "$SCRIPT_MAIN_PID" ]]; then
        echo # Newline setelah potentially ^C
        log_message "--- Script (PID $$) selesai/dihentikan (Exit Code: $exit_code) ---"
        if is_listener_running; then
            echo " Membersihkan: Menghentikan listener (PID: $LISTENER_PID)..."
            # Kirim sinyal tanpa menunggu lama di trap
            kill -TERM "$LISTENER_PID" 2>/dev/null
            sleep 0.2
            kill -KILL "$LISTENER_PID" 2>/dev/null # Pastikan berhenti
            rm -f "$PID_FILE"
            echo " Listener dihentikan."
            log_message "Listener (PID: $LISTENER_PID) dihentikan paksa saat script exit."
        else
             rm -f "$PID_FILE" # Hapus file PID jika ada tapi proses tidak jalan
        fi
        echo " Pembersihan selesai."
        # Kembalikan terminal ke state normal jika dialog mengacau
        stty sane >/dev/null 2>&1
        clear
    fi
    # Keluar dengan kode yang sesuai
    # exit "$exit_code" # Ini bisa menyebabkan loop jika dipanggil dari trap EXIT
}
# Trap SIGINT (Ctrl+C) dan SIGTERM
trap 'cleanup; exit 130' SIGINT
trap 'cleanup; exit 143' SIGTERM
# Trap EXIT normal (tidak perlu exit di sini krn script akan exit setelahnya)
# trap cleanup EXIT # Hati-hati bisa menyebabkan double cleanup

# --- Start Script ---
clear
check_deps
log_message "--- Script Email Trader v1.5 Dimulai (PID: $$) ---"

# Cek status listener saat startup
if is_listener_running; then
    log_message "INFO: Script dimulai, listener dari sesi sebelumnya terdeteksi aktif (PID: $LISTENER_PID)."
    info_msg "Listener dari sesi sebelumnya terdeteksi aktif (PID: $LISTENER_PID)."
fi

# Coba load konfigurasi awal
if ! load_config; then
    # Hanya tampilkan setup awal jika listener tidak aktif
    if ! is_listener_running; then
        dialog --backtitle "$DIALOG_BACKTITLE" --title "Setup Awal Diperlukan" \
            --msgbox "File konfigurasi ($CONFIG_FILE) tidak ditemukan atau tidak lengkap.\n\nAnda akan diarahkan ke menu konfigurasi." 10 70
        if ! configure_settings; then
            clear
            echo "Konfigurasi awal dibatalkan atau gagal. Script tidak dapat dilanjutkan." >&2
            log_message "FATAL: Konfigurasi awal gagal. Script berhenti."
            cleanup # Panggil cleanup manual sebelum exit paksa
            exit 1
        fi
        # Coba load lagi setelah konfigurasi berhasil
        if ! load_config; then
            clear
            echo "Gagal memuat konfigurasi setelah setup awal. Script berhenti." >&2
            log_message "FATAL: Gagal memuat konfigurasi setelah setup. Script berhenti."
            cleanup # Panggil cleanup manual sebelum exit paksa
            exit 1
        fi
    else
        # Jika listener aktif tapi config gagal load, ini masalah
         log_message "CRITICAL: Listener aktif tapi konfigurasi gagal dimuat! Listener mungkin tidak berfungsi benar."
         error_msg " Listener aktif (PID: $LISTENER_PID), TAPI konfigurasi gagal dimuat!\n\n Listener mungkin tidak akan bisa trading.\n Hentikan listener dan perbaiki konfigurasi."
    fi
fi

# Masuk ke menu utama
main_menu

# Script seharusnya keluar via pilihan menu atau sinyal (ditangani trap)
# Baris ini seharusnya tidak tercapai, tapi sebagai fallback:
cleanup
exit 0
