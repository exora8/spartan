#!/usr/bin/env bash

# Script Email Listener & Binance Trader
# Versi: 1.6 (Log Trimming Otomatis)
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
MAX_LOG_LINES=20 # Jumlah baris log maksimum yang ingin disimpan

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
        GMAIL_USER=$(grep -Po "^GMAIL_USER *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        GMAIL_APP_PASS=$(grep -Po "^GMAIL_APP_PASS *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        BINANCE_API_KEY=$(grep -Po "^BINANCE_API_KEY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        BINANCE_SECRET_KEY=$(grep -Po "^BINANCE_SECRET_KEY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        TRADE_SYMBOL=$(grep -Po "^TRADE_SYMBOL *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        TRADE_QUANTITY=$(grep -Po "^TRADE_QUANTITY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        CHECK_INTERVAL=$(grep -Po "^CHECK_INTERVAL *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)

        if [[ -z "$GMAIL_USER" || -z "$GMAIL_APP_PASS" || -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$TRADE_SYMBOL" || -z "$TRADE_QUANTITY" ]]; then
            log_message "WARNING: File konfigurasi $CONFIG_FILE ada tapi tidak lengkap atau gagal parse (Variabel Wajib)."
            CHECK_INTERVAL="${CHECK_INTERVAL:-60}"
            return 1
        fi
        CHECK_INTERVAL="${CHECK_INTERVAL:-60}"
        log_message "Konfigurasi berhasil dimuat dari $CONFIG_FILE."
        return 0
    else
        log_message "INFO: File konfigurasi $CONFIG_FILE tidak ditemukan."
        return 1
    fi
}

# Fungsi simpan konfigurasi
save_config() {
    mkdir -p "$(dirname "$CONFIG_FILE")"
    rm -f "$CONFIG_FILE"
    {
        echo "# Konfigurasi Email Trader (v1.6)"
        echo "GMAIL_USER='${GMAIL_USER}'"
        echo "GMAIL_APP_PASS='${GMAIL_APP_PASS}'"
        echo "BINANCE_API_KEY='${BINANCE_API_KEY}'"
        echo "BINANCE_SECRET_KEY='${BINANCE_SECRET_KEY}'"
        echo "TRADE_SYMBOL='${TRADE_SYMBOL}'"
        echo "TRADE_QUANTITY='${TRADE_QUANTITY}'"
        echo "CHECK_INTERVAL='${CHECK_INTERVAL}'"
    } > "$CONFIG_FILE"
    chmod 600 "$CONFIG_FILE"
    log_message "Konfigurasi berhasil disimpan di $CONFIG_FILE"
    info_msg "Konfigurasi berhasil disimpan di $CONFIG_FILE"
}

# Fungsi konfigurasi interaktif
configure_settings() {
    if is_listener_running; then
        error_msg "Listener sedang aktif (PID: $LISTENER_PID). Hentikan listener terlebih dahulu sebelum mengubah konfigurasi."
        return 1
    fi
    load_config
    local temp_gmail_user="${GMAIL_USER}"
    local temp_gmail_pass="${GMAIL_APP_PASS}"
    local temp_api_key="${BINANCE_API_KEY}"
    local temp_secret_key="${BINANCE_SECRET_KEY}"
    local temp_symbol="${TRADE_SYMBOL}"
    local temp_quantity="${TRADE_QUANTITY}"
    local temp_interval="${CHECK_INTERVAL:-60}"
    local input_gmail_user input_gmail_pass input_api_key input_secret_key input_symbol input_quantity input_interval exit_status
    local temp_file
    temp_file=$(mktemp) || { error_msg "Gagal membuat file temporary untuk dialog."; return 1; }
    trap 'rm -f "$temp_file"' RETURN
    exec 3>&1
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
    exec 3>&-
    if [ $exit_status -ne 0 ]; then info_msg "Konfigurasi dibatalkan."; return 1; fi
    input_gmail_user=$(sed -n '1p' "$temp_file")
    input_gmail_pass=$(sed -n '2p' "$temp_file")
    input_api_key=$(sed -n '3p' "$temp_file")
    input_secret_key=$(sed -n '4p' "$temp_file")
    input_symbol=$(sed -n '5p' "$temp_file")
    input_quantity=$(sed -n '6p' "$temp_file")
    input_interval=$(sed -n '7p' "$temp_file")
    rm -f "$temp_file"
    if [[ -z "$input_gmail_user" || -z "$input_gmail_pass" || -z "$input_api_key" || -z "$input_secret_key" || -z "$input_symbol" || -z "$input_quantity" || -z "$input_interval" ]]; then error_msg "Semua field konfigurasi harus diisi."; return 1; fi
    if ! [[ "$input_interval" =~ ^[1-9][0-9]*$ ]]; then error_msg "Interval cek email harus berupa angka positif (detik)."; return 1; fi
    if ! [[ "$input_quantity" =~ ^[+]?([0-9]+(\.[0-9]*)?|\.[0-9]+)$ ]] || ! awk "BEGIN {exit !($input_quantity > 0)}"; then error_msg "Quantity trading harus berupa angka positif lebih besar dari 0 (misal: 0.001 atau 10)."; return 1; fi
    GMAIL_USER="$input_gmail_user"
    GMAIL_APP_PASS="$input_gmail_pass"
    BINANCE_API_KEY="$input_api_key"
    BINANCE_SECRET_KEY="$input_secret_key"
    TRADE_SYMBOL=$(echo "$input_symbol" | tr 'a-z' 'A-Z')
    TRADE_QUANTITY="$input_quantity"
    CHECK_INTERVAL="$input_interval"
    save_config
    return 0
}

# Fungsi untuk logging ke file
log_message() {
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local pid_info="[PID $$]"
    # Append ke log file
    echo "[$timestamp]$pid_info $1" >> "${LOG_FILE:-/tmp/email_trader_fallback.log}"
    # Logic trimming dipindahkan ke listener_loop
}

# --- Fungsi Background Listener ---

# Fungsi cek email baru yang cocok
check_email() {
    log_message "Mencari email baru dari $GMAIL_USER dengan identifier: '$EMAIL_IDENTIFIER'"
    local email_body_file
    email_body_file=$(mktemp --suffix=.eml) || { log_message "ERROR: Gagal membuat file temporary untuk email."; return 1; }
    trap 'rm -f "$email_body_file"' RETURN

    "$EMAIL_CLIENT" \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail="" query_command=""' \
        -e 'push "<limit>~U ~S \"'${EMAIL_IDENTIFIER}'\"\n<pipe-message>cat > '${email_body_file}'\n<exit>"' \
        > /dev/null 2>&1
    local mutt_exit_code=$?
    if [[ $mutt_exit_code -ne 0 && $mutt_exit_code -ne 1 ]]; then
        log_message "WARNING: Perintah $EMAIL_CLIENT keluar dengan kode $mutt_exit_code (Mungkin error koneksi/autentikasi)"
    fi

    if [ -s "$email_body_file" ]; then
        log_message "Email yang cocok ditemukan. Memproses..."
        if parse_email_body "$email_body_file"; then
             mark_email_as_read
        else
             log_message "Action tidak ditemukan atau gagal parse/eksekusi, email TIDAK ditandai dibaca."
        fi
        return 0
    else
        # log_message "Tidak ada email baru yang cocok ditemukan." # Opsional: bisa terlalu verbose
        return 1
    fi
}

# Fungsi parsing body email
parse_email_body() {
    local body_file="$1"
    log_message "Parsing isi email dari $body_file"
    local action=""
    if grep -qiw "BUY" "$body_file"; then
        action="BUY"
    elif grep -qiw "SELL" "$body_file"; then
        action="SELL"
    fi

    if [[ "$action" == "BUY" ]]; then
        log_message "Action terdeteksi: BUY"
        execute_binance_order "BUY" "$TRADE_SYMBOL" "$TRADE_QUANTITY"
        return $?
    elif [[ "$action" == "SELL" ]]; then
        log_message "Action terdeteksi: SELL"
        execute_binance_order "SELL" "$TRADE_SYMBOL" "$TRADE_QUANTITY"
        return $?
    else
        log_message "WARNING: Tidak ada action 'BUY' atau 'SELL' yang valid terdeteksi dalam email yang cocok."
        return 1
    fi
}

# Fungsi untuk menandai email sebagai sudah dibaca
mark_email_as_read() {
    log_message "Menandai email yang cocok sebagai sudah dibaca..."
    "$EMAIL_CLIENT" \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail="" query_command=""' \
        -e 'push "<limit>~U ~S \"'${EMAIL_IDENTIFIER}'\"\n<clear-flag>N\n<sync-mailbox><exit>"' > /dev/null 2>&1
    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        log_message "Perintah untuk menandai email dibaca telah dikirim (menargetkan email belum dibaca yang cocok)."
    else
        [[ $exit_code -ne 1 ]] && log_message "WARNING: Perintah $EMAIL_CLIENT untuk menandai email dibaca mungkin gagal (exit code: $exit_code)."
    fi
}

# Fungsi generate signature Binance
generate_binance_signature() {
    local query_string="$1"
    local secret="$2"
    echo -n "$query_string" | openssl dgst -sha256 -hmac "$secret" | sed 's/^.* //'
}

# Fungsi eksekusi order Binance
execute_binance_order() {
    local side="$1"
    local symbol="$2"
    local quantity="$3"
    local timestamp
    timestamp=$(date +%s%3N)

    if [[ -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$symbol" || -z "$quantity" ]]; then
        log_message "ERROR: Konfigurasi Binance tidak lengkap. Tidak bisa membuat order."
        return 1
    fi
    local api_endpoint="https://api.binance.com"
    local order_path="/api/v3/order"
    local params="symbol=${symbol}&side=${side}&type=MARKET&quantity=${quantity}×tamp=${timestamp}"
    local signature
    signature=$(generate_binance_signature "$params" "$BINANCE_SECRET_KEY")
    if [ -z "$signature" ]; then log_message "ERROR: Gagal menghasilkan signature Binance."; return 1; fi
    local full_url="${api_endpoint}${order_path}"
    local post_data="${params}&signature=${signature}"

    log_message "Mengirim order ke Binance: URL=$full_url DATA=$params"

    local response curl_exit_code http_code body
    response=$(curl --connect-timeout 10 --max-time 20 -s -w "\n%{http_code}" \
                  -H "X-MBX-APIKEY: ${BINANCE_API_KEY}" \
                  -X POST "$full_url" -d "$post_data" 2>>"$LOG_FILE")
    curl_exit_code=$?
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    if [ $curl_exit_code -ne 0 ]; then
        log_message "ERROR: curl gagal menghubungi Binance (Curl Exit code: $curl_exit_code)."
        return 1
    fi
    log_message "Response Binance (HTTP $http_code): $body"

    if [[ "$http_code" =~ ^2 ]]; then
        local orderId status clientOrderId
        orderId=$(echo "$body" | jq -r '.orderId // empty')
        status=$(echo "$body" | jq -r '.status // "UNKNOWN"')
        clientOrderId=$(echo "$body" | jq -r '.clientOrderId // empty')
        if [[ -n "$orderId" && "$status" != "UNKNOWN" ]]; then
            log_message "SUCCESS: Order $side $symbol $quantity berhasil. Order ID: $orderId, Client Order ID: $clientOrderId, Status: $status"
            return 0
        else
            log_message "WARNING: HTTP $http_code diterima tapi orderId/status tidak terparsir. Body: $body"
            return 0
        fi
    else
        local err_code err_msg
        err_code=$(echo "$body" | jq -r '.code // "?"')
        err_msg=$(echo "$body" | jq -r '.msg // "Tidak ada pesan error spesifik."')
        log_message "ERROR: Gagal menempatkan order $side $symbol. Kode Error: $err_code Pesan: $err_msg"
        return 1
    fi
}

# Fungsi Loop Utama Listener (untuk dijalankan di background)
listener_loop() {
    # Export variabel yang dibutuhkan
    export GMAIL_USER GMAIL_APP_PASS BINANCE_API_KEY BINANCE_SECRET_KEY TRADE_SYMBOL TRADE_QUANTITY EMAIL_IDENTIFIER EMAIL_CLIENT LOG_FILE CHECK_INTERVAL MAX_LOG_LINES

    local check_interval="${CHECK_INTERVAL:-60}"
    if ! [[ "$check_interval" =~ ^[1-9][0-9]*$ ]]; then
        log_message "ERROR_LISTENER: Interval cek email tidak valid ('$check_interval'). Menggunakan default 60 detik."
        check_interval=60
    fi

    trap 'log_message "Listener loop (PID $$) dihentikan oleh sinyal."; exit 0' SIGTERM SIGINT

    log_message "Listener loop dimulai (PID $$). Interval: ${check_interval} detik. Log: $LOG_FILE. Max Log Lines: $MAX_LOG_LINES"
    while true; do
        log_message "Memulai siklus pengecekan email..."
        check_email
        log_message "Siklus selesai. Menunggu ${check_interval} detik..."
        sleep "$check_interval"

        # --- Pemangkasan Log Otomatis ---
        local current_lines
        # Pastikan file log ada dan dapat dibaca sebelum dipangkas
        if [[ -r "$LOG_FILE" ]]; then
            current_lines=$(wc -l < "$LOG_FILE" 2>/dev/null)
            # Periksa apakah wc berhasil dan outputnya adalah angka
            if [[ "$current_lines" =~ ^[0-9]+$ ]]; then
                # Periksa apakah jumlah baris melebihi batas maksimum
                if [[ "$current_lines" -gt "$MAX_LOG_LINES" ]]; then
                     log_message "INFO_LISTENER: File log ($LOG_FILE) melebihi $MAX_LOG_LINES baris ($current_lines), memangkas..."
                     # Gunakan tail untuk mengambil N baris terakhir, timpa file asli (lebih aman dari mv sementara)
                     tail -n "$MAX_LOG_LINES" "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
                     if [ $? -ne 0 ]; then
                         log_message "WARNING_LISTENER: Gagal memangkas file log ($LOG_FILE)."
                     fi
                     # Tidak perlu log sukses pemangkasan untuk mengurangi noise log
                fi
            else
                 # Jika wc gagal (misal file hilang tiba-tiba), log warning
                 log_message "WARNING_LISTENER: Gagal mendapatkan jumlah baris log ($LOG_FILE) untuk pemangkasan (output wc: '$current_lines')."
            fi
        else
            # Jika file tidak ada atau tidak bisa dibaca
            log_message "WARNING_LISTENER: File log ($LOG_FILE) tidak ditemukan atau tidak dapat dibaca untuk pemangkasan."
        fi
        # --- Akhir Pemangkasan Log Otomatis ---
    done
}

# --- Fungsi Kontrol Listener ---

is_listener_running() {
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE")
        if [[ -n "$pid" ]] && ps -p "$pid" > /dev/null; then
            LISTENER_PID="$pid"
            return 0
        else
            log_message "INFO: File PID ($PID_FILE) ditemukan tapi proses $pid tidak berjalan. Menghapus file PID basi."
            rm -f "$PID_FILE"
            LISTENER_PID=""
            return 1
        fi
    else
        LISTENER_PID=""
        return 1
    fi
}

start_listener() {
    if is_listener_running; then error_msg "Listener sudah berjalan (PID: $LISTENER_PID)."; return 1; fi
    if ! load_config; then error_msg "Konfigurasi belum lengkap atau gagal dimuat. Tidak bisa memulai listener."; return 1; fi

    log_message "Memulai listener di background..."
    ( listener_loop ) >>"$LOG_FILE" 2>&1 &
    local pid=$!
    echo "$pid" > "$PID_FILE"
    if [ $? -ne 0 ]; then
       log_message "ERROR: Gagal menyimpan PID $pid ke $PID_FILE."
       kill "$pid" 2>/dev/null
       error_msg "Gagal menyimpan file PID. Listener tidak dimulai."
       LISTENER_PID=""
       return 1
    fi
    sleep 0.5
    if ! kill -0 "$pid" 2>/dev/null; then
        log_message "ERROR: Listener process (PID: $pid) tidak ditemukan setelah dimulai. Cek log."
        error_msg "Listener gagal dimulai atau langsung berhenti. Periksa log ($LOG_FILE)."
        rm -f "$PID_FILE"
        LISTENER_PID=""
        return 1
    fi
    LISTENER_PID="$pid"
    log_message "Listener berhasil dimulai (PID: $LISTENER_PID)."
    info_msg "Listener berhasil dimulai (PID: $LISTENER_PID). Log aktivitas bisa dilihat di menu."
    return 0
}

stop_listener() {
    if ! is_listener_running; then info_msg "Listener tidak sedang berjalan."; return 1; fi
    log_message "Mengirim sinyal TERM ke listener (PID: $LISTENER_PID)..."
    if kill -TERM "$LISTENER_PID" 2>/dev/null; then
        local count=0 max_wait=10
        while kill -0 "$LISTENER_PID" 2>/dev/null; do
            ((count++))
            if [ "$count" -gt "$max_wait" ]; then
                log_message "WARNING: Listener (PID: $LISTENER_PID) tidak berhenti. Mengirim KILL."
                kill -KILL "$LISTENER_PID" 2>/dev/null
                sleep 0.5
                break
            fi
            sleep 0.5
        done
        if ! kill -0 "$LISTENER_PID" 2>/dev/null; then
            log_message "Listener (PID: $LISTENER_PID) berhasil dihentikan."
            info_msg "Listener (PID: $LISTENER_PID) berhasil dihentikan."
        else
            log_message "ERROR: Gagal menghentikan listener (PID: $LISTENER_PID) dengan KILL."
            error_msg "Gagal menghentikan listener (PID: $LISTENER_PID) sepenuhnya."
            return 1
        fi
    else
        log_message "WARNING: Gagal mengirim sinyal TERM ke PID $LISTENER_PID."
        if ! kill -0 "$LISTENER_PID" 2>/dev/null; then
            info_msg "Listener (PID: $LISTENER_PID) sepertinya sudah berhenti."
        else
            error_msg "Gagal mengirim sinyal ke listener (PID: $LISTENER_PID)."
            return 1
        fi
    fi
    rm -f "$PID_FILE"
    LISTENER_PID=""
    return 0
}

show_live_log() {
    if ! is_listener_running; then error_msg "Listener tidak sedang berjalan."; return 1; fi
     if [[ ! -f "$LOG_FILE" ]]; then error_msg "File log ($LOG_FILE) tidak ditemukan."; return 1; fi
     clear
     dialog --title "Email Listener - Log Real-time (PID: $LISTENER_PID)" \
            --no-kill \
            --tailboxbg "$LOG_FILE" 25 90
     log_message "Menutup tampilan log real-time (listener tetap berjalan)."
     clear
}

view_static_log() {
    clear
    if [ -f "$LOG_FILE" ] && [ -s "$LOG_FILE" ]; then
        # Tampilkan N baris terakhir saja jika file terlalu besar (opsional)
        # local lines_to_show=500
        # tail -n "$lines_to_show" "$LOG_FILE" | dialog --title "Log Aktivitas Statis (Last $lines_to_show Lines - $LOG_FILE)" --cr-wrap --textbox /dev/stdin 25 90
        # Atau tampilkan semua:
        dialog --title "Log Aktivitas Statis ($LOG_FILE)" --cr-wrap --textbox "$LOG_FILE" 25 90
    else
        info_msg "File log ($LOG_FILE) belum ada atau kosong."
    fi
    clear
}

# --- Fungsi Menu Utama ---
main_menu() {
    while true; do
        clear
        is_listener_running
        local listener_status_msg=""
        local menu_items=()
        local menu_height list_height

        if [[ -n "$LISTENER_PID" ]]; then
            listener_status_msg=" (Listener Aktif - PID: $LISTENER_PID)"
            menu_items+=("1" "Lihat Log Listener (Real-time)"
                         "2" "Hentikan Listener"
                         "3" "Pengaturan (Nonaktif)"
                         "4" "Lihat Log Statis Keseluruhan"
                         "5" "Keluar")
            menu_height=18; list_height=5
        else
            listener_status_msg=" (Listener Tidak Aktif)"
            menu_items+=("1" "Mulai Listener"
                         "2" "Pengaturan"
                         "3" "Lihat Log Statis Keseluruhan"
                         "4" "Keluar")
            menu_height=17; list_height=4
        fi

        CHOICE=$(dialog --clear --stdout \
                        --title "Email Trader v1.6 - Menu Utama$listener_status_msg" \
                        --cancel-label "Keluar" \
                        --menu "Pilih tindakan:" $menu_height 75 $list_height "${menu_items[@]}")
        local exit_status=$?
        if [[ $exit_status -ne 0 ]]; then CHOICE="Keluar_Signal"; fi

        if [[ -n "$LISTENER_PID" ]]; then # === Listener Aktif ===
            case "$CHOICE" in
                1) show_live_log ;;
                2) stop_listener ;;
                3) error_msg "Listener harus dihentikan terlebih dahulu untuk mengakses Pengaturan." ;;
                4) view_static_log ;;
                5 | "Keluar_Signal")
                    clear; echo "Menghentikan listener sebelum keluar..."; stop_listener
                    echo "Script dihentikan."; log_message "--- Script Dihentikan via Menu Keluar (Listener Aktif) ---"
                    exit 0 ;;
                *) error_msg "Pilihan tidak valid." ;;
            esac
        else # === Listener Tidak Aktif ===
             case "$CHOICE" in
                1) start_listener ;;
                2) configure_settings ;;
                3) view_static_log ;;
                4 | "Keluar_Signal")
                    clear; echo "Script dihentikan."
                    log_message "--- Script Dihentikan (Listener tidak aktif) ---"
                    exit 0 ;;
                *) error_msg "Pilihan tidak valid." ;;
            esac
        fi
    done
}

# --- Main Program Execution ---

cleanup() {
    local exit_code=$?
    echo
    log_message "--- Script Menerima Sinyal Exit (Kode: $exit_code) ---"
    local current_pid=""
    if [ -f "$PID_FILE" ]; then current_pid=$(cat "$PID_FILE"); fi

    if [[ -n "$current_pid" ]] && kill -0 "$current_pid" 2>/dev/null; then
        echo " Membersihkan: Menghentikan listener (PID: $current_pid)..."
        kill -TERM "$current_pid" &> /dev/null; sleep 0.5; kill -KILL "$current_pid" &> /dev/null
        rm -f "$PID_FILE"
        echo " Membersihkan: Listener dihentikan."
        log_message "Listener (PID: $current_pid) dihentikan paksa saat script exit/cleanup."
    elif [[ -f "$PID_FILE" ]]; then
         rm -f "$PID_FILE"
         log_message "Membersihkan: Menghapus file PID basi ($PID_FILE)."
    fi
    echo " Script selesai."
    stty sane
    clear
    if [[ "$exit_code" == "0" ]]; then exit 0; else exit $((128 + exit_code)); fi
}
trap cleanup INT TERM EXIT

clear
echo "Memulai Email Trader v1.6..."
check_deps
log_message "--- Script Email Trader v1.6 Dimulai (PID: $SCRIPT_MAIN_PID) ---"

is_listener_running
if [[ -n "$LISTENER_PID" ]]; then
    log_message "INFO: Script dimulai, listener dari sesi sebelumnya aktif (PID: $LISTENER_PID)."
    info_msg "Listener dari sesi sebelumnya terdeteksi aktif (PID: $LISTENER_PID).\nAnda dapat menghentikannya dari menu."
    sleep 2
fi

if ! load_config; then
    if ! is_listener_running; then
        clear
        dialog --title "Setup Awal Diperlukan" \
            --yesno "File konfigurasi ($CONFIG_FILE) tidak ditemukan atau tidak lengkap.\n\nApakah Anda ingin melakukan konfigurasi sekarang?" 10 70
        response=$?
        case $response in
            0) if ! configure_settings; then clear; echo "Konfigurasi awal gagal. Script berhenti."; log_message "FATAL: Konfigurasi awal gagal. Script berhenti."; exit 1; fi
               if ! load_config; then clear; echo "Gagal memuat konfigurasi setelah setup. Script berhenti."; log_message "FATAL: Gagal memuat konfigurasi setelah setup. Script berhenti."; exit 1; fi ;;
            1|255) clear; echo "Konfigurasi awal dilewati. Script berhenti."; log_message "FATAL: Konfigurasi awal dilewati. Script berhenti."; exit 1 ;;
        esac
    else
        log_message "WARNING: Konfigurasi gagal dimuat, tapi listener aktif (PID: $LISTENER_PID)."
        error_msg "WARNING: Konfigurasi gagal dimuat ($CONFIG_FILE).\nListener mungkin berjalan dengan konfigurasi lama.\nHentikan listener dan perbaiki konfigurasi jika perlu."
        sleep 3
    fi
fi

main_menu
exit 0
