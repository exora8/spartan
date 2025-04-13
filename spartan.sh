#!/usr/bin/env bash

# Script Email Listener & Binance Trader
# Versi: 1.7 (Logging Aktif - Limit 15 Baris)
# Author: [Nama Kamu/AI] & Kontributor

# --- Konfigurasi Awal ---
CONFIG_FILE="$HOME/.email_trader_rc"
# Arahkan LOG_FILE ke file log yang diinginkan
LOG_FILE="$HOME/.email_trader.log"
MAX_LOG_LINES=15 # Batas jumlah baris log
PID_FILE="/tmp/email_trader.pid" # File untuk menyimpan PID listener

# Buat file log jika belum ada dan set permission
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"

# Identifier Email yang Dicari (Subject atau Body)
EMAIL_IDENTIFIER="Exora AI (V5 SPOT + SR Filter) (1M)" # Contoh, ganti sesuai kebutuhan

# --- Variabel Global ---
LISTENER_PID="" # Akan diisi dari PID_FILE saat script start
SCRIPT_MAIN_PID=$$ # Simpan PID script utama

# --- Fungsi ---

# Fungsi untuk menampilkan pesan error dengan dialog
error_msg() {
    clear
    dialog --title "Error" --msgbox "$1" 8 60
    log_message "ERROR_DIALOG: $1" # Tetap log pesan error
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
    for cmd in dialog neomutt curl openssl jq grep sed awk cut date mktemp tail wc kill sleep clear pgrep wc; do # Tambahkan 'wc'
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
        echo "# Konfigurasi Email Trader (v1.7 - Log Aktif)"
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

    if [ $exit_status -ne 0 ]; then
        info_msg "Konfigurasi dibatalkan."
        return 1
    fi

    input_gmail_user=$(sed -n '1p' "$temp_file")
    input_gmail_pass=$(sed -n '2p' "$temp_file")
    input_api_key=$(sed -n '3p' "$temp_file")
    input_secret_key=$(sed -n '4p' "$temp_file")
    input_symbol=$(sed -n '5p' "$temp_file")
    input_quantity=$(sed -n '6p' "$temp_file")
    input_interval=$(sed -n '7p' "$temp_file")
    rm -f "$temp_file"

    if [[ -z "$input_gmail_user" || -z "$input_gmail_pass" || -z "$input_api_key" || -z "$input_secret_key" || -z "$input_symbol" || -z "$input_quantity" || -z "$input_interval" ]]; then
         error_msg "Semua field konfigurasi harus diisi."
         return 1
    fi
    if ! [[ "$input_interval" =~ ^[1-9][0-9]*$ ]]; then
        error_msg "Interval cek email harus berupa angka positif (detik)."
        return 1
     fi
     if ! [[ "$input_quantity" =~ ^[+]?([0-9]+(\.[0-9]*)?|\.[0-9]+)$ ]] || ! awk "BEGIN {exit !($input_quantity > 0)}"; then
        error_msg "Quantity trading harus berupa angka positif lebih besar dari 0 (misal: 0.001 atau 10)."
        return 1
     fi

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


# Fungsi untuk logging (output akan ditulis ke $LOG_FILE)
log_message() {
    # Fungsi ini sekarang akan menulis ke file log yang sebenarnya
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local pid_info="[PID $$]"
    # Append ke log file
    echo "[$timestamp]$pid_info $1" >> "$LOG_FILE"
    # Logika trimming dipindahkan ke listener_loop agar tidak dijalankan setiap kali log
}

# --- Fungsi Background Listener ---

# Fungsi cek email baru yang cocok
check_email() {
    log_message "Mencari email baru dari $GMAIL_USER dengan identifier: '$EMAIL_IDENTIFIER'"
    local email_body_file
    email_body_file=$(mktemp --suffix=.eml) || { log_message "ERROR: Gagal membuat file temporary untuk email."; return 1; }
    trap 'rm -f "$email_body_file"' RETURN

    # Redirect stderr neomutt ke file log jika diinginkan, atau biarkan ke /dev/null
    "$EMAIL_CLIENT" \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail="" query_command=""' \
        -e 'push "<limit>~U ~S \"'${EMAIL_IDENTIFIER}'\"\n<pipe-message>cat > '${email_body_file}'\n<exit>"' \
        > /dev/null 2>> "$LOG_FILE" # Arahkan error neomutt ke log file juga

    local mutt_exit_code=$?
    if [[ $mutt_exit_code -ne 0 && $mutt_exit_code -ne 1 ]]; then
        # Kode 1 biasanya berarti tidak ada pesan atau kondisi normal lain, jangan log sebagai warning
        log_message "WARNING: Perintah $EMAIL_CLIENT keluar dengan kode $mutt_exit_code (Mungkin error koneksi/autentikasi atau lainnya)"
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
        # log_message "Tidak ada email baru yang cocok ditemukan." # Tidak perlu log jika tidak ada email
        return 1
    fi
}

# Fungsi parsing body email
parse_email_body() {
    local body_file="$1"
    log_message "Parsing isi email dari $body_file"
    local action=""

    # Gunakan opsi -i untuk case-insensitive, -m 1 untuk berhenti setelah match pertama
    if grep -qim 1 "BUY" "$body_file"; then
        action="BUY"
    elif grep -qim 1 "SELL" "$body_file"; then
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
        # Kita mungkin ingin melihat isi body jika parsing gagal
        log_message "DEBUG: Isi email (awal): $(head -n 5 "$body_file")" # Log beberapa baris awal
        return 1
    fi
}

# Fungsi untuk menandai email sebagai sudah dibaca
mark_email_as_read() {
    log_message "Menandai email yang cocok sebagai sudah dibaca..."
    "$EMAIL_CLIENT" \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail="" query_command=""' \
        -e 'push "<limit>~U ~S \"'${EMAIL_IDENTIFIER}'\"\n<clear-flag>N\n<sync-mailbox><exit>"' > /dev/null 2>> "$LOG_FILE" # Log error
    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        log_message "Perintah untuk menandai email dibaca telah dikirim."
    else
        # Kode 1 biasanya normal jika tidak ada yang ditandai, jadi abaikan
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
    # Pastikan parameter timestamp ditulis dengan benar (sebelumnya ada typo 'Ã—tamp')
    local params="symbol=${symbol}&side=${side}&type=MARKET&quantity=${quantity}×tamp=${timestamp}"
    local signature
    signature=$(generate_binance_signature "$params" "$BINANCE_SECRET_KEY")
    if [ -z "$signature" ]; then
        log_message "ERROR: Gagal menghasilkan signature Binance."
        return 1
    fi

    local full_url="${api_endpoint}${order_path}"
    local post_data="${params}&signature=${signature}"

    log_message "Mengirim order ke Binance: URL=$full_url DATA=$params" # Jangan log signature

    local response curl_exit_code http_code body
    # Kirim stderr curl ke file log juga
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
        local orderId status clientOrderId msg code
        # Gunakan jq untuk parsing yang lebih robust
        orderId=$(echo "$body" | jq -r '.orderId // empty')
        status=$(echo "$body" | jq -r '.status // "UNKNOWN"')
        clientOrderId=$(echo "$body" | jq -r '.clientOrderId // empty')

        if [[ -n "$orderId" && "$status" != "UNKNOWN" ]]; then
            log_message "SUCCESS: Order $side $symbol $quantity berhasil. Order ID: $orderId, Client Order ID: $clientOrderId, Status: $status"
            return 0
        else
            # Mungkin sukses tapi response tidak standar? Tetap log sebagai sukses sementara.
            log_message "WARNING: HTTP $http_code OK diterima tapi orderId/status tidak terparsir dengan baik. Body: $body"
            return 0 # Anggap sukses jika http code 2xx
        fi
    else
        # Gagal, coba parse error dari Binance
        local err_code err_msg
        err_code=$(echo "$body" | jq -r '.code // "?"')
        err_msg=$(echo "$body" | jq -r '.msg // "Tidak ada pesan error spesifik dari Binance."')
        log_message "ERROR: Gagal menempatkan order $side $symbol. Kode Error Binance: $err_code Pesan: $err_msg"
        return 1
    fi
}


# Fungsi Loop Utama Listener (untuk dijalankan di background)
listener_loop() {
    # Ekspor variabel yang dibutuhkan oleh fungsi-fungsi di dalam subshell/background process
    export GMAIL_USER GMAIL_APP_PASS BINANCE_API_KEY BINANCE_SECRET_KEY TRADE_SYMBOL TRADE_QUANTITY EMAIL_IDENTIFIER EMAIL_CLIENT LOG_FILE CHECK_INTERVAL MAX_LOG_LINES

    local check_interval="${CHECK_INTERVAL:-60}"
    if ! [[ "$check_interval" =~ ^[1-9][0-9]*$ ]]; then
        log_message "ERROR_LISTENER: Interval cek email tidak valid ('$check_interval'). Menggunakan default 60 detik."
        check_interval=60
    fi

    trap 'log_message "Listener loop (PID $$) dihentikan oleh sinyal."; exit 0' SIGTERM SIGINT

    log_message "Listener loop dimulai (PID $$). Interval: ${check_interval} detik. Log dibatasi ${MAX_LOG_LINES} baris."
    while true; do
        # log_message "Memulai siklus pengecekan email..." # Kurangi pesan verbose
        check_email
        # log_message "Siklus selesai. Menunggu ${check_interval} detik..." # Kurangi pesan verbose
        sleep "$check_interval"

        # --- Log Trimming ---
        # Cek hanya jika file log ada dan punya isi
        if [[ -f "$LOG_FILE" && -s "$LOG_FILE" ]]; then
            local line_count
            # Hitung baris (lebih efisien dari cat | wc -l)
            line_count=$(wc -l < "$LOG_FILE")

            # Jika jumlah baris melebihi batas
            if [[ "$line_count" -gt "$MAX_LOG_LINES" ]]; then
                log_message "LOG_TRIM: Log melebihi $MAX_LOG_LINES baris ($line_count). Memangkas..."
                local temp_log_file
                # Buat file temporary
                temp_log_file=$(mktemp) || {
                    log_message "ERROR_LOG_TRIM: Gagal membuat file log temporary."
                    continue # Lewati pemangkasan kali ini
                }
                # Ambil N baris terakhir dan simpan ke file temporary
                tail -n "$MAX_LOG_LINES" "$LOG_FILE" > "$temp_log_file"

                # Pastikan tail berhasil dan file temp tidak kosong sebelum menimpa
                if [[ -s "$temp_log_file" ]]; then
                    # Timpa file log asli dengan file temporary
                    mv "$temp_log_file" "$LOG_FILE"
                    # Setel ulang permission (mv mungkin mengubahnya)
                    chmod 600 "$LOG_FILE"
                    log_message "LOG_TRIM: Log berhasil dipangkas menjadi ${MAX_LOG_LINES} baris."
                else
                    log_message "ERROR_LOG_TRIM: Gagal memangkas log (tail menghasilkan file kosong?). File asli tidak diubah."
                    rm -f "$temp_log_file" # Hapus file temp yang gagal/kosong
                fi
            fi
        fi
        # --- Akhir Log Trimming ---
    done
}

# --- Fungsi Kontrol Listener ---

is_listener_running() {
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE")
        if [[ -n "$pid" ]] && ps -p "$pid" > /dev/null; then
            LISTENER_PID="$pid"
            return 0 # Listener berjalan
        else
            # File PID ada tapi proses tidak jalan -> file basi
            log_message "INFO: File PID ($PID_FILE) ditemukan tapi proses $pid tidak berjalan. Menghapus file PID basi."
            rm -f "$PID_FILE"
            LISTENER_PID=""
            return 1 # Listener tidak berjalan
        fi
    else
        LISTENER_PID=""
        return 1 # Listener tidak berjalan
    fi
}

start_listener() {
    if is_listener_running; then
        error_msg "Listener sudah berjalan (PID: $LISTENER_PID)."
        return 1
    fi

    if ! load_config; then
        error_msg "Konfigurasi belum lengkap atau gagal dimuat. Tidak bisa memulai listener."
        # Tawarkan konfigurasi jika belum ada
        if ! [[ -f "$CONFIG_FILE" ]]; then
             info_msg "Silakan jalankan 'Pengaturan' dari menu utama terlebih dahulu."
        fi
        return 1
    fi

    log_message "Memulai listener di background..."
    # Redirect stdout & stderr listener ke $LOG_FILE
    # Jalankan listener_loop dalam subshell agar variabel diekspor
    ( listener_loop ) >>"$LOG_FILE" 2>&1 &
    local pid=$!

    # Simpan PID ke file
    echo "$pid" > "$PID_FILE"
    if [ $? -ne 0 ]; then
       log_message "ERROR: Gagal menyimpan PID $pid ke $PID_FILE."
       # Coba bunuh proses yang mungkin sudah jalan
       kill "$pid" 2>/dev/null
       error_msg "Gagal menyimpan file PID. Listener tidak dimulai."
       LISTENER_PID=""
       return 1
    fi

    # Beri waktu sejenak untuk proses dimulai
    sleep 0.5
    # Verifikasi apakah proses benar-benar berjalan
    if ! kill -0 "$pid" 2>/dev/null; then
        log_message "ERROR: Listener process (PID: $pid) tidak ditemukan setelah dimulai. Cek $LOG_FILE untuk error."
        error_msg "Listener gagal dimulai atau langsung berhenti. Cek log di $LOG_FILE."
        rm -f "$PID_FILE" # Hapus file PID jika proses gagal
        LISTENER_PID=""
        return 1
    fi

    LISTENER_PID="$pid"
    log_message "Listener berhasil dimulai di background (PID: $LISTENER_PID)."
    info_msg "Listener berhasil dimulai (PID: $LISTENER_PID).\nLog disimpan di: $LOG_FILE (Max $MAX_LOG_LINES baris)."
    return 0
}

stop_listener() {
    if ! is_listener_running; then
        info_msg "Listener tidak sedang berjalan."
        return 1
    fi

    log_message "Mengirim sinyal TERM ke listener (PID: $LISTENER_PID)..."
    # Kirim sinyal TERM (graceful shutdown)
    if kill -TERM "$LISTENER_PID" 2>/dev/null; then
        local count=0
        local max_wait=10 # Tunggu maksimal 5 detik (10 * 0.5s)
        # Tunggu proses berhenti
        while kill -0 "$LISTENER_PID" 2>/dev/null; do
            ((count++))
            if [ "$count" -gt "$max_wait" ]; then
                log_message "WARNING: Listener (PID: $LISTENER_PID) tidak berhenti setelah ${max_wait} setengah detik. Mengirim sinyal KILL."
                # Paksa berhenti jika tidak mau berhenti baik-baik
                kill -KILL "$LISTENER_PID" 2>/dev/null
                sleep 0.5 # Beri waktu sedikit setelah KILL
                break
            fi
            sleep 0.5
        done

        # Cek lagi apakah sudah berhenti
        if ! kill -0 "$LISTENER_PID" 2>/dev/null; then
            log_message "Listener (PID: $LISTENER_PID) berhasil dihentikan."
            info_msg "Listener (PID: $LISTENER_PID) berhasil dihentikan."
        else
            log_message "ERROR: Gagal menghentikan listener (PID: $LISTENER_PID) sepenuhnya bahkan setelah KILL."
            error_msg "Gagal menghentikan listener (PID: $LISTENER_PID) sepenuhnya."
            # Jangan hapus PID file jika gagal stop total? Mungkin lebih baik tetap dihapus.
            # return 1 # Mungkin tidak perlu return error jika sudah di-KILL
        fi
    else
        log_message "WARNING: Gagal mengirim sinyal TERM ke PID $LISTENER_PID (mungkin sudah berhenti?)."
        # Cek apakah memang sudah berhenti
        if ! kill -0 "$LISTENER_PID" 2>/dev/null; then
            info_msg "Listener (PID: $LISTENER_PID) sepertinya sudah berhenti."
        else
            error_msg "Gagal mengirim sinyal TERM ke listener (PID: $LISTENER_PID) yang masih berjalan."
            return 1
        fi
    fi

    # Hapus file PID setelah proses berhenti atau dipastikan tidak berjalan
    rm -f "$PID_FILE"
    LISTENER_PID=""
    return 0
}

# Menampilkan log real-time (jika listener berjalan)
show_live_log() {
    if ! is_listener_running; then
        error_msg "Listener tidak sedang berjalan. Tidak ada log real-time untuk ditampilkan."
        return 1
    fi
     if [[ ! -f "$LOG_FILE" ]]; then
        error_msg "File log ($LOG_FILE) tidak ditemukan."
        return 1
     fi
     clear
     dialog --title "Email Listener - Log Real-time (PID: $LISTENER_PID)" \
            --no-kill \
            --cr-wrap \
            --tailboxbg "$LOG_FILE" 25 90
     log_message "Menutup tampilan log real-time (listener tetap berjalan)."
     clear
}

# Menampilkan isi file log statis
view_static_log() {
    clear
    if [ -f "$LOG_FILE" ] && [ -s "$LOG_FILE" ]; then
        dialog --title "Log Aktivitas Statis ($LOG_FILE - Max $MAX_LOG_LINES Baris)" \
               --cr-wrap \
               --textbox "$LOG_FILE" 25 90
    else
        info_msg "File log ($LOG_FILE) belum ada atau kosong."
    fi
    clear
}

# --- Fungsi Menu Utama ---
main_menu() {
    while true; do
        clear
        is_listener_running # Update status LISTENER_PID
        local listener_status_msg=""
        local menu_items=()

        if [[ -n "$LISTENER_PID" ]]; then
            # Listener Aktif
            listener_status_msg=" (Listener Aktif - PID: $LISTENER_PID)"
            menu_items+=("1" "Lihat Log Listener Real-time"
                         "2" "Hentikan Listener"
                         "3" "Pengaturan (Nonaktif)" # Pengaturan dinonaktifkan saat listener jalan
                         "4" "Lihat Log Statis"
                         "5" "Keluar")
            local menu_height=18
            local list_height=5
        else
            # Listener Tidak Aktif
            listener_status_msg=" (Listener Tidak Aktif)"
            menu_items+=("1" "Mulai Listener"
                         "2" "Pengaturan"
                         "3" "Lihat Log Statis"
                         "4" "Keluar")
            local menu_height=17
            local list_height=4
        fi

        CHOICE=$(dialog --clear --stdout \
                        --title "Email Trader v1.7 - Menu Utama$listener_status_msg" \
                        --cancel-label "Keluar" \
                        --menu "Pilih tindakan (Log: $LOG_FILE):" $menu_height 75 $list_height "${menu_items[@]}")

        local exit_status=$?
        # Jika user menekan ESC atau Cancel
        if [[ $exit_status -ne 0 ]]; then
            CHOICE="Keluar_Signal"
        fi

        if [[ -n "$LISTENER_PID" ]]; then # === Listener Aktif ===
            case "$CHOICE" in
                1) show_live_log ;;
                2) stop_listener ;;
                3) error_msg "Listener harus dihentikan terlebih dahulu untuk mengakses Pengaturan." ;;
                4) view_static_log ;;
                5 | "Keluar_Signal")
                    clear
                    echo "Menghentikan listener sebelum keluar..."
                    stop_listener # Coba hentikan listener sebelum keluar
                    echo "Script dihentikan."
                    log_message "--- Script Dihentikan via Menu Keluar (Listener Aktif) ---"
                    exit 0
                    ;;
                *) error_msg "Pilihan tidak valid." ;;
            esac
        else # === Listener Tidak Aktif ===
             case "$CHOICE" in
                1) start_listener ;;
                2) configure_settings ;;
                3) view_static_log ;;
                4 | "Keluar_Signal")
                    clear
                    echo "Script dihentikan."
                    log_message "--- Script Dihentikan (Listener tidak aktif) ---"
                    exit 0
                    ;;
                *) error_msg "Pilihan tidak valid." ;;
            esac
        fi
        # Beri jeda sedikit sebelum menampilkan menu lagi, kecuali jika keluar
        [[ "$CHOICE" != "Keluar_Signal" ]] && sleep 0.1
    done
}

# --- Main Program Execution ---

# Fungsi cleanup saat script dihentikan paksa (Ctrl+C, kill)
cleanup() {
    local exit_code=$?
    echo
    log_message "--- Script Menerima Sinyal Exit (Kode: $exit_code) ---"
    local current_pid=""
    # Cek apakah listener sedang berjalan berdasarkan PID file
    if [ -f "$PID_FILE" ]; then current_pid=$(cat "$PID_FILE"); fi

    # Jika PID ada dan prosesnya masih berjalan
    if [[ -n "$current_pid" ]] && kill -0 "$current_pid" 2>/dev/null; then
        echo " Membersihkan: Menghentikan listener (PID: $current_pid) sebelum keluar..."
        log_message "Cleanup: Mengirim TERM ke listener PID $current_pid..."
        kill -TERM "$current_pid" &> /dev/null
        sleep 0.5 # Beri waktu sedikit
        # Jika masih jalan, paksa KILL
        if kill -0 "$current_pid" &> /dev/null; then
           log_message "Cleanup: Listener PID $current_pid tidak berhenti, mengirim KILL."
           kill -KILL "$current_pid" &> /dev/null
        fi
        rm -f "$PID_FILE" # Hapus file PID
        echo " Membersihkan: Listener dihentikan."
        log_message "Cleanup: Listener (PID: $current_pid) dihentikan paksa saat script exit."
    elif [[ -f "$PID_FILE" ]]; then
         # Jika file PID ada tapi proses tidak jalan
         rm -f "$PID_FILE"
         log_message "Cleanup: Menghapus file PID basi ($PID_FILE)."
    fi
    echo " Script selesai."
    stty sane # Kembalikan terminal ke state normal jika dialog mengacaukannya
    clear
    # Keluar dengan kode yang sesuai
    if [[ "$exit_code" == "0" ]]; then exit 0; else exit $((128 + exit_code)); fi
}
# Pasang trap untuk sinyal INT (Ctrl+C) dan TERM (kill)
trap cleanup INT TERM EXIT # EXIT juga akan trigger cleanup pada akhir normal

# --- Inisialisasi ---
clear
echo "Memulai Email Trader v1.7 (Logging Aktif - Max $MAX_LOG_LINES baris)..."
check_deps # Cek dependensi dulu
log_message "--- Script Email Trader v1.7 Dimulai (PID: $SCRIPT_MAIN_PID) ---"
log_message "Log disimpan di: $LOG_FILE"

# Cek apakah ada listener dari sesi sebelumnya yang masih jalan
is_listener_running
if [[ -n "$LISTENER_PID" ]]; then
    log_message "INFO: Script dimulai, listener dari sesi sebelumnya terdeteksi aktif (PID: $LISTENER_PID)."
    info_msg "Listener dari sesi sebelumnya terdeteksi aktif (PID: $LISTENER_PID).\nLog disimpan di $LOG_FILE.\nAnda dapat menghentikannya dari menu."
    sleep 2
fi

# Cek konfigurasi, tawarkan setup jika belum ada DAN listener tidak aktif
if ! load_config; then
    if ! is_listener_running; then # Hanya tawarkan setup jika listener TIDAK aktif
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
                # Coba load lagi setelah konfigurasi
                if ! load_config; then
                    clear
                    echo "Gagal memuat konfigurasi bahkan setelah setup awal. Script berhenti."
                    log_message "FATAL: Gagal memuat konfigurasi setelah setup. Script berhenti."
                    exit 1
                fi
                ;;
            1|255) # No atau ESC/Cancel
                clear
                echo "Konfigurasi awal dilewati. Script tidak dapat berfungsi tanpa konfigurasi."
                log_message "FATAL: Konfigurasi awal dilewati. Script berhenti."
                exit 1
                ;;
        esac
    else
        # Konfigurasi gagal load TAPI listener aktif (dari sesi lalu)
        log_message "WARNING: Konfigurasi gagal dimuat, tapi listener (PID: $LISTENER_PID) aktif."
        error_msg "WARNING: Konfigurasi gagal dimuat ($CONFIG_FILE).\nListener dari sesi sebelumnya mungkin berjalan dengan konfigurasi lama.\nHentikan listener dan perbaiki/buat konfigurasi jika perlu."
        sleep 3
    fi
fi

# Masuk ke menu utama
main_menu

exit 0
