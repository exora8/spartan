#!/usr/bin/env bash

# Script Email Listener & Binance Trader
# Versi: 1.2 (Improved CLI & Bug Fix)
# Author: [Nama Kamu/AI] & Kontributor

# --- Konfigurasi Awal ---
CONFIG_FILE="$HOME/.email_trader_rc"
LOG_FILE="/tmp/email_trader.log"
touch "$LOG_FILE" # Pastikan file log ada
chmod 600 "$LOG_FILE" # Amankan log jika perlu

# Identifier Email yang Dicari (Subject atau Body)
EMAIL_IDENTIFIER="Exora AI (V5 SPOT + SR Filter) (1M)" # Contoh, ganti sesuai kebutuhan

# Variabel Global untuk Status Listener
LISTENER_PID="" # Akan diisi saat listener berjalan

# --- Fungsi Utility & UI ---

# Fungsi untuk menampilkan pesan error dengan dialog
error_msg() {
    log_message "ERROR: $1" # Catat error ke log juga
    dialog --title "Error" --msgbox "\n[ERROR]\n\n$1" 10 70
}

# Fungsi untuk menampilkan info dengan dialog
info_msg() {
    dialog --title "Info" --msgbox "\n$1" 10 70
}

# Fungsi untuk menampilkan pesan singkat (hilang otomatis)
infobox_msg() {
    dialog --title "Info" --infobox "\n$1" 5 60
    sleep 2 # Tampilkan selama 2 detik
}

# Fungsi untuk membersihkan layar
clear_screen() {
    clear
}

# Fungsi cek dependensi (dialog dicek pertama)
check_deps() {
    if ! command -v dialog &> /dev/null; then
        echo "FATAL: Dependensi krusial 'dialog' tidak ditemukan." >&2
        echo "Silakan install 'dialog' (misal: sudo apt install dialog atau sudo yum install dialog)." >&2
        exit 1
    fi

    local missing_deps=()
    # Cek dependensi lainnya
    for cmd in neomutt curl openssl jq grep sed awk cut date mktemp tail wc kill sleep wait ps; do
        if ! command -v "$cmd" &> /dev/null; then
            missing_deps+=("$cmd")
        fi
    done

    # Cek mutt sebagai fallback neomutt
    if ! command -v neomutt &> /dev/null && ! command -v mutt &> /dev/null; then
         missing_deps+=("neomutt atau mutt")
    fi

    if [ ${#missing_deps[@]} -ne 0 ]; then
        error_msg "Dependensi berikut tidak ditemukan:\n\n$(printf -- '- %s\n' "${missing_deps[@]}")\n\nSilakan install terlebih dahulu."
        exit 1
    fi

    EMAIL_CLIENT=$(command -v neomutt || command -v mutt)
    log_message "Dependensi terpenuhi. Menggunakan email client: $EMAIL_CLIENT"
}

# Fungsi untuk logging ke file
log_message() {
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    # Pastikan LOG_FILE sudah didefinisikan
    echo "[$timestamp] $1" >> "${LOG_FILE:-/tmp/email_trader_fallback.log}"
}

# Fungsi cleanup (dipanggil saat script keluar)
cleanup() {
    log_message "--- Script Shutdown ---"
    if [[ -n "$LISTENER_PID" && -e /proc/$LISTENER_PID ]]; then
        log_message "Menghentikan listener process (PID: $LISTENER_PID)..."
        kill -TERM "$LISTENER_PID" 2>/dev/null
        wait "$LISTENER_PID" 2>/dev/null
        log_message "Listener process dihentikan."
    fi
    clear_screen
    echo "Email Trader dihentikan."
}
# Trap sinyal exit, interrupt, terminate untuk cleanup
trap cleanup EXIT SIGINT SIGTERM

# --- Fungsi Konfigurasi ---

load_config() {
    # Sama seperti versi sebelumnya, tapi log message lebih jelas
    if [ -f "$CONFIG_FILE" ]; then
        chmod 600 "$CONFIG_FILE";
        ( source "$CONFIG_FILE" ) # Coba source di subshell

        GMAIL_USER=$(grep -Po "^GMAIL_USER *= *['\"]\K[^'\"]*" "$CONFIG_FILE")
        GMAIL_APP_PASS=$(grep -Po "^GMAIL_APP_PASS *= *['\"]\K[^'\"]*" "$CONFIG_FILE")
        BINANCE_API_KEY=$(grep -Po "^BINANCE_API_KEY *= *['\"]\K[^'\"]*" "$CONFIG_FILE")
        BINANCE_SECRET_KEY=$(grep -Po "^BINANCE_SECRET_KEY *= *['\"]\K[^'\"]*" "$CONFIG_FILE")
        TRADE_SYMBOL=$(grep -Po "^TRADE_SYMBOL *= *['\"]\K[^'\"]*" "$CONFIG_FILE")
        TRADE_QUANTITY=$(grep -Po "^TRADE_QUANTITY *= *['\"]\K[^'\"]*" "$CONFIG_FILE")
        CHECK_INTERVAL=$(grep -Po "^CHECK_INTERVAL *= *['\"]\K[^'\"]*" "$CONFIG_FILE")

        if [[ -z "$GMAIL_USER" || -z "$GMAIL_APP_PASS" || -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$TRADE_SYMBOL" || -z "$TRADE_QUANTITY" || -z "$CHECK_INTERVAL" ]]; then
            log_message "WARNING: File konfigurasi $CONFIG_FILE ada tapi tidak lengkap."
            # Kosongkan variabel jika tidak lengkap untuk memicu rekonfigurasi
            GMAIL_USER="" GMAIL_APP_PASS="" BINANCE_API_KEY="" BINANCE_SECRET_KEY="" TRADE_SYMBOL="" TRADE_QUANTITY="" CHECK_INTERVAL=""
            return 1
        fi
        log_message "Konfigurasi berhasil dimuat dari $CONFIG_FILE."
        CHECK_INTERVAL="${CHECK_INTERVAL:-60}" # Default jika kosong setelah load
        EMAIL_IDENTIFIER="${EMAIL_IDENTIFIER:-"Trading Signal"}" # Default jika belum diset
        return 0
    else
        log_message "INFO: File konfigurasi $CONFIG_FILE tidak ditemukan."
        return 1
    fi
}

save_config() {
    # Sama seperti versi sebelumnya
    rm -f "$CONFIG_FILE"
    echo "# Konfigurasi Email Trader (v1.2)" > "$CONFIG_FILE"
    echo "GMAIL_USER='${GMAIL_USER}'" >> "$CONFIG_FILE"
    echo "GMAIL_APP_PASS='${GMAIL_APP_PASS}'" >> "$CONFIG_FILE"
    echo "BINANCE_API_KEY='${BINANCE_API_KEY}'" >> "$CONFIG_FILE"
    echo "BINANCE_SECRET_KEY='${BINANCE_SECRET_KEY}'" >> "$CONFIG_FILE"
    echo "TRADE_SYMBOL='${TRADE_SYMBOL}'" >> "$CONFIG_FILE"
    echo "TRADE_QUANTITY='${TRADE_QUANTITY}'" >> "$CONFIG_FILE"
    echo "CHECK_INTERVAL='${CHECK_INTERVAL}'" >> "$CONFIG_FILE"
    echo "# Identifier email bisa diedit manual jika perlu:" >> "$CONFIG_FILE"
    echo "# EMAIL_IDENTIFIER='${EMAIL_IDENTIFIER}'" >> "$CONFIG_FILE"
    chmod 600 "$CONFIG_FILE"
    log_message "Konfigurasi berhasil disimpan di $CONFIG_FILE"
}

configure_settings() {
    clear_screen
    load_config # Muat nilai saat ini untuk default

    local temp_gmail_user="${GMAIL_USER}"
    local temp_gmail_pass="${GMAIL_APP_PASS}"
    local temp_api_key="${BINANCE_API_KEY}"
    local temp_secret_key="${BINANCE_SECRET_KEY}"
    local temp_symbol="${TRADE_SYMBOL}"
    local temp_quantity="${TRADE_QUANTITY}"
    local temp_interval="${CHECK_INTERVAL:-60}"
    local temp_identifier="${EMAIL_IDENTIFIER:-"Exora AI (V5 SPOT + SR Filter) (1M)"}"

    # Gunakan temporary file untuk menampung input form
    local temp_form_output
    temp_form_output=$(mktemp)

    dialog --title "Konfigurasi Email Trader" --clear \
           --cancel-label "Batal" \
           --form "\nMasukkan detail konfigurasi:" 20 75 0 \
           "Alamat Gmail:"          1 1 "$temp_gmail_user"    1 25 50 0 \
           "Gmail App Password:"    2 1 "$temp_gmail_pass"    2 25 50 1 \
           "Binance API Key:"       3 1 "$temp_api_key"       3 25 70 0 \
           "Binance Secret Key:"    4 1 "$temp_secret_key"    4 25 70 1 \
           "Simbol Trading (cth: BTCUSDT):" 5 1 "$temp_symbol" 5 25 20 0 \
           "Quantity per Trade (cth: 0.01):" 6 1 "$temp_quantity" 6 25 20 0 \
           "Interval Cek Email (detik):"   7 1 "$temp_interval" 7 25 10 0 \
           "Identifier Email (Subject/Body):" 8 1 "$temp_identifier" 8 25 60 0 \
           2> "$temp_form_output"

    local exit_status=$?
    local form_data
    form_data=$(<"$temp_form_output")
    rm "$temp_form_output"

    if [ $exit_status -ne 0 ]; then
        info_msg "Konfigurasi dibatalkan."
        return 1
    fi

    # Parse form data (setiap baris adalah satu field)
    local input_gmail_user input_gmail_pass input_api_key input_secret_key input_symbol input_quantity input_interval input_identifier
    {
        read -r input_gmail_user
        read -r input_gmail_pass
        read -r input_api_key
        read -r input_secret_key
        read -r input_symbol
        read -r input_quantity
        read -r input_interval
        read -r input_identifier
    } <<< "$form_data"

    # Validasi (contoh sederhana)
    if [[ -z "$input_gmail_user" || -z "$input_gmail_pass" || -z "$input_api_key" || -z "$input_secret_key" || -z "$input_symbol" || -z "$input_quantity" || -z "$input_interval" || -z "$input_identifier" ]]; then
        error_msg "Semua field konfigurasi harus diisi."
        return 1
    fi
    if ! [[ "$input_interval" =~ ^[1-9][0-9]*$ ]]; then
        error_msg "Interval cek email harus berupa angka positif (detik)."
        return 1
    fi
    if ! [[ "$input_quantity" =~ ^[0-9]+(\.[0-9]+)?$ && $(echo "$input_quantity > 0" | bc -l) -eq 1 ]]; then
        error_msg "Quantity trading harus berupa angka positif (misal: 0.001 atau 10)."
        return 1
    fi

    # Update variabel global & simpan
    GMAIL_USER="$input_gmail_user"
    GMAIL_APP_PASS="$input_gmail_pass"
    BINANCE_API_KEY="$input_api_key"
    BINANCE_SECRET_KEY="$input_secret_key"
    TRADE_SYMBOL=$(echo "$input_symbol" | tr 'a-z' 'A-Z')
    TRADE_QUANTITY="$input_quantity"
    CHECK_INTERVAL="$input_interval"
    EMAIL_IDENTIFIER="$input_identifier"

    save_config
    info_msg "Konfigurasi berhasil disimpan!"
    return 0
}

# --- Fungsi Inti Trading ---

# Fungsi cek email, parsing, mark as read (sama seperti sebelumnya, log lebih detail)
check_email() {
    # ... (Kode check_email dari versi sebelumnya, pastikan log_message digunakan) ...
    log_message "Mencari email baru dari $GMAIL_USER dengan identifier: '$EMAIL_IDENTIFIER'"
    local email_body_file
    email_body_file=$(mktemp) || { log_message "ERROR: Gagal membuat file temporary untuk email."; return 1; }

    "$EMAIL_CLIENT" \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail=""' \
        -e 'push "<limit>~N (~b \"'${EMAIL_IDENTIFIER}'\" | ~s \"'${EMAIL_IDENTIFIER}'\")\n<pipe-message>cat > '${email_body_file}'\n<exit>"' > /dev/null 2>&1

    if [ -s "$email_body_file" ]; then
        log_message "Email yang cocok ditemukan. Memproses..."
        parse_email_body "$email_body_file"
        local parse_status=$?
        rm "$email_body_file"
        if [ $parse_status -eq 0 ]; then
             mark_email_as_read
        else
             log_message "Action tidak valid atau gagal parse, email TIDAK ditandai dibaca."
        fi
        return 0
    else
        log_message "Tidak ada email baru yang cocok ditemukan."
        rm "$email_body_file"
        return 1
    fi
}

parse_email_body() {
    # ... (Kode parse_email_body dari versi sebelumnya, sesuaikan jika perlu) ...
    local body_file="$1"
    log_message "Parsing isi email dari $body_file"
    local action=""
    # Implementasi parsing yang lebih kuat mungkin diperlukan tergantung format email
    # Contoh sederhana: cari kata kunci BUY atau SELL (case insensitive)
    if grep -qi "buy" "$body_file"; then
        action="BUY"
    elif grep -qi "sell" "$body_file"; then
        action="SELL"
    fi

    # Double check identifier ada di body (opsional tapi aman)
    # if ! grep -q "$EMAIL_IDENTIFIER" "$body_file"; then
    #     log_message "WARNING: Action '$action' terdeteksi, tapi identifier '$EMAIL_IDENTIFIER' tidak ada di body. Abaikan."
    #     return 1
    # fi

    if [[ "$action" == "BUY" ]]; then
        log_message "Action terdeteksi: BUY untuk $TRADE_SYMBOL"
        execute_binance_order "BUY"
        return 0
    elif [[ "$action" == "SELL" ]]; then
        log_message "Action terdeteksi: SELL untuk $TRADE_SYMBOL"
        execute_binance_order "SELL"
        return 0
    else
        log_message "WARNING: Tidak ada action 'BUY' atau 'SELL' yang valid terdeteksi dalam email yang cocok."
        return 1
    fi
}

mark_email_as_read() {
    # ... (Kode mark_email_as_read dari versi sebelumnya) ...
    log_message "Menandai email sebagai sudah dibaca..."
    "$EMAIL_CLIENT" \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail=""' \
        -e 'push "<limit>~N (~b \"'${EMAIL_IDENTIFIER}'\" | ~s \"'${EMAIL_IDENTIFIER}'\")\n<clear-flag>N\n<sync-mailbox><exit>"' > /dev/null 2>&1
    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        log_message "Perintah untuk menandai email dibaca telah dikirim."
    else
        log_message "WARNING: Perintah untuk menandai email dibaca mungkin gagal (exit code: $exit_code)."
    fi
}

# Fungsi generate signature & execute order (sama seperti sebelumnya, error handling via dialog)
generate_binance_signature() {
    # ... (Kode generate_binance_signature) ...
    local query_string="$1"
    local secret="$2"
    echo -n "$query_string" | openssl dgst -sha256 -hmac "$secret" | sed 's/^.* //'
}

execute_binance_order() {
    # ... (Kode execute_binance_order, tapi error_msg dipakai untuk notifikasi) ...
    local side="$1"
    local timestamp=$(date +%s%3N)
    if [[ -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$TRADE_SYMBOL" || -z "$TRADE_QUANTITY" ]]; then
        error_msg "Konfigurasi Binance tidak lengkap. Order dibatalkan."
        return 1
    fi

    local api_endpoint="https://api.binance.com"
    local order_path="/api/v3/order"
    local params="symbol=${TRADE_SYMBOL}&side=${side}&type=MARKET&quantity=${TRADE_QUANTITY}×tamp=${timestamp}"
    local signature=$(generate_binance_signature "$params" "$BINANCE_SECRET_KEY")
    local full_url="${api_endpoint}${order_path}?${params}&signature=${signature}"

    log_message "Mengirim order ke Binance: SIDE=$side SYMBOL=$TRADE_SYMBOL QTY=$TRADE_QUANTITY"
    infobox_msg "Mengirim order $side $TRADE_SYMBOL..." # Feedback cepat

    local response curl_exit_code http_code body
    response=$(curl -s -w "%{http_code}" -H "X-MBX-APIKEY: ${BINANCE_API_KEY}" -X POST "$full_url")
    curl_exit_code=$?
    http_code="${response: -3}"
    body="${response:0:${#response}-3}"

    if [ $curl_exit_code -ne 0 ]; then
        error_msg "Curl gagal menghubungi Binance (Code: $curl_exit_code). Cek koneksi / log."
        return 1
    fi

    log_message "Response Binance (HTTP $http_code): $body"

    if [[ "$http_code" =~ ^2 ]]; then
        local orderId=$(echo "$body" | jq -r '.orderId // empty')
        local status=$(echo "$body" | jq -r '.status // "UNKNOWN"')
        log_message "SUCCESS: Order berhasil. ID: $orderId, Status: $status"
        info_msg "Order $side $TRADE_SYMBOL berhasil!\nID: $orderId\nStatus: $status" # Notif sukses
        return 0
    else
        local err_code=$(echo "$body" | jq -r '.code // "?"')
        local err_msg=$(echo "$body" | jq -r '.msg // "Unknown Error"')
        error_msg "Gagal Order Binance!\nHTTP Code: $http_code\nBinance Code: $err_code\nPesan: $err_msg" # Notif Gagal
        return 1
    fi
}

# --- Fungsi Listener ---

# Loop utama yang berjalan di background
listener_loop() {
    # Trap SIGTERM untuk exit bersih dari loop
    trap 'log_message "[listener_loop] SIGTERM diterima, keluar."; exit 0' SIGTERM

    log_message "[listener_loop] Dimulai. Interval: $CHECK_INTERVAL detik."
    while true; do
        log_message "[listener_loop] Memulai siklus cek email..."
        check_email
        log_message "[listener_loop] Siklus selesai. Tidur selama $CHECK_INTERVAL detik..."
        sleep "$CHECK_INTERVAL"

        # Pangkas log jika terlalu besar
        local max_log_lines=1000
        local current_lines=$(wc -l < "$LOG_FILE")
        if [ "$current_lines" -gt "$max_log_lines" ]; then
            log_message "[listener_loop] INFO: File log dipangkas ke $max_log_lines baris terakhir."
            tail -n "$max_log_lines" "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
        fi
    done
}

# Fungsi untuk menjalankan listener dan menampilkan log viewer
run_listener() {
    clear_screen
    if [[ -n "$LISTENER_PID" && -e /proc/$LISTENER_PID ]]; then
        info_msg "Listener sudah berjalan (PID: $LISTENER_PID)."
        return
    fi

    # Validasi interval sebelum mulai
    if ! [[ "$CHECK_INTERVAL" =~ ^[1-9][0-9]*$ ]]; then
        error_msg "Interval cek email tidak valid ($CHECK_INTERVAL). Silakan perbaiki di Pengaturan."
        return
    fi

    infobox_msg "Memulai listener email..."

    # Jalankan loop di background
    listener_loop &
    LISTENER_PID=$!
    log_message "Listener utama dimulai (PID: $LISTENER_PID)."

    # Cek apakah proses background berhasil start
    sleep 1 # Beri waktu sedikit untuk proses start/exit jika gagal
    if ! ps -p $LISTENER_PID > /dev/null; then
        error_msg "Gagal memulai proses listener background. Cek log untuk detail."
        LISTENER_PID=""
        return
    fi

    # Tampilkan log viewer dengan tombol Stop
    dialog --title "Log Aktivitas Listener (PID: $LISTENER_PID) - Tekan 'Stop' atau Esc untuk kembali" \
           --ok-label "Stop & Kembali" \
           --tailboxbg "$LOG_FILE" 25 90

    # Setelah dialog ditutup (user tekan Stop/Esc)
    log_message "Log viewer ditutup. Menghentikan listener (PID: $LISTENER_PID)..."
    infobox_msg "Menghentikan listener..."

    # Kirim sinyal TERM ke proses background
    kill -TERM "$LISTENER_PID" 2>/dev/null
    # Tunggu proses background selesai
    wait "$LISTENER_PID" 2>/dev/null
    log_message "Listener (PID: $LISTENER_PID) seharusnya sudah berhenti."
    LISTENER_PID="" # Reset PID
    clear_screen
}

# --- Fungsi Tampilkan Log Statis ---
view_log() {
    clear_screen
    if [ -s "$LOG_FILE" ]; then # -s cek file ada dan tidak kosong
        dialog --title "Tampilkan Log ($LOG_FILE)" --exit-label "Kembali" --textbox "$LOG_FILE" 25 90
    else
        info_msg "File log ($LOG_FILE) belum ada atau kosong."
    fi
    clear_screen
}

# --- Fungsi Menu Utama ---
main_menu() {
    while true; do
        clear_screen
        # Siapkan info status untuk judul/subtitle
        local status_info="Email: ${GMAIL_USER:-'Belum diatur'} | Pair: ${TRADE_SYMBOL:-'N/A'} | Interval: ${CHECK_INTERVAL:-'N/A'}s"
        local listener_status="Status: ${LISTENER_PID:+'BERJALAN (PID: $LISTENER_PID')':-'TIDAK AKTIF'}"

        CHOICE=$(dialog --clear --stdout \
                        --title "Email Trader v1.2 - Menu Utama" \
                        --cancel-label "Keluar" \
                        --extra-button --extra-label "Lihat Log" \
                        --menu "$status_info\n$listener_status\n\nPilih tindakan:" \
                        18 80 5 \
                        1 "Mulai/Stop Listener Email" \
                        2 "Pengaturan" \
                        3 "Keluar dari Script")

        local exit_status=$?

        case $exit_status in
            0) # Pilihan OK (Menu dipilih)
                case "$CHOICE" in
                    1)
                        if [[ -n "$LISTENER_PID" && -e /proc/$LISTENER_PID ]]; then
                            # Jika sedang berjalan, konfirmasi untuk stop
                            dialog --yesno "Listener sedang berjalan (PID: $LISTENER_PID).\n\nAnda yakin ingin menghentikannya?" 8 60
                            if [ $? -eq 0 ]; then
                                log_message "User meminta stop listener dari menu."
                                infobox_msg "Menghentikan listener..."
                                kill -TERM "$LISTENER_PID" 2>/dev/null
                                wait "$LISTENER_PID" 2>/dev/null
                                log_message "Listener dihentikan via menu."
                                LISTENER_PID=""
                            fi
                        else
                            # Jika tidak berjalan, mulai listener
                            if load_config; then # Pastikan config valid sebelum mulai
                                run_listener
                            else
                                error_msg "Konfigurasi belum lengkap atau tidak valid. Silakan masuk ke 'Pengaturan'."
                            fi
                        fi
                        ;;
                    2)
                        configure_settings
                        load_config # Muat ulang config jika ada perubahan
                        ;;
                    3)
                        exit 0 # Keluar (akan ditangani oleh trap)
                        ;;
                esac
                ;;
            1) # Cancel/Keluar
                exit 0 # Keluar (akan ditangani oleh trap)
                ;;
            3) # Tombol Extra (Lihat Log)
                view_log
                ;;
            *) # Error atau Esc ditekan di tempat lain?
                exit 1 # Keluar dengan error status
                ;;
        esac
    done
}

# --- Eksekusi Utama ---

log_message "--- Script Start ---"

# 1. Cek dependensi
check_deps

# 2. Load konfigurasi awal, paksa setup jika perlu
if ! load_config; then
    clear_screen
    dialog --title "Setup Awal Diperlukan" \
           --msgbox "Konfigurasi awal tidak ditemukan atau tidak lengkap.\n\nAnda akan diarahkan ke menu konfigurasi." 10 70
    if ! configure_settings; then
        clear_screen
        echo "Konfigurasi awal dibatalkan atau gagal. Script tidak dapat dilanjutkan."
        exit 1
    fi
    # Coba load lagi setelah setup
    if ! load_config; then
        clear_screen
        echo "Gagal memuat konfigurasi setelah setup awal. Script berhenti."
        exit 1
    fi
fi

# 3. Tampilkan Menu Utama
main_menu

# Cleanup akan otomatis terpanggil saat exit
exit 0
