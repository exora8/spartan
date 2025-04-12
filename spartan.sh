#!/usr/bin/env bash

# Script Email Listener & Binance Trader
# Versi: 1.3 (Visible Password Input & Bug Fixes)
# Author: [Nama Kamu/AI] & Kontributor

# --- Konfigurasi Awal ---
CONFIG_FILE="$HOME/.email_trader_rc"
LOG_FILE="/tmp/email_trader.log"
touch "$LOG_FILE" # Pastikan file log ada
chmod 600 "$LOG_FILE" # Amankan log jika perlu

# Identifier Email yang Dicari (Subject atau Body)
EMAIL_IDENTIFIER="Exora AI (V5 SPOT + SR Filter) (1M)" # Contoh, ganti sesuai kebutuhan

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
    for cmd in dialog neomutt curl openssl jq grep sed awk cut date mktemp tail wc kill sleep wait clear; do
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

# Fungsi simpan konfigurasi
save_config() {
    rm -f "$CONFIG_FILE"
    echo "# Konfigurasi Email Trader (v1.3)" > "$CONFIG_FILE"
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
    load_config # Muat nilai saat ini jika ada

    local temp_gmail_user="${GMAIL_USER}"
    local temp_gmail_pass="${GMAIL_APP_PASS}"
    local temp_api_key="${BINANCE_API_KEY}"
    local temp_secret_key="${BINANCE_SECRET_KEY}"
    local temp_symbol="${TRADE_SYMBOL}"
    local temp_quantity="${TRADE_QUANTITY}"
    local temp_interval="${CHECK_INTERVAL:-60}"

    local input_gmail_user input_gmail_pass input_api_key input_secret_key input_symbol input_quantity input_interval exit_status

    # --- Input Fields with Clear ---
    clear
    input_gmail_user=$(dialog --stdout --title "Konfigurasi" --inputbox "Alamat Gmail Anda:" 8 60 "$temp_gmail_user")
    exit_status=$?
    [[ $exit_status -ne 0 ]] && { info_msg "Konfigurasi dibatalkan."; return 1; }

    clear
    # --- PERUBAHAN DI SINI: Menggunakan --inputbox bukan --passwordbox ---
    input_gmail_pass=$(dialog --stdout --title "Konfigurasi" --inputbox "Gmail App Password Anda (Bukan Password Utama!):" 8 70 "$temp_gmail_pass")
    exit_status=$?
    [[ $exit_status -ne 0 ]] && { info_msg "Konfigurasi dibatalkan."; return 1; }

    clear
    input_api_key=$(dialog --stdout --title "Konfigurasi" --inputbox "Binance API Key Anda:" 8 70 "$temp_api_key")
    exit_status=$?
    [[ $exit_status -ne 0 ]] && { info_msg "Konfigurasi dibatalkan."; return 1; }

    clear
    # --- PERUBAHAN DI SINI: Menggunakan --inputbox bukan --passwordbox ---
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
     # Regex untuk angka positif, bisa integer atau desimal
     if ! [[ "$input_quantity" =~ ^[+]?([0-9]+(\.[0-9]*)?|\.[0-9]+)$ && "$input_quantity" != "0" && "$input_quantity" != "0.0" ]]; then
        error_msg "Quantity trading harus berupa angka positif (misal: 0.001 atau 10)."
        return 1
     fi

    # Update variabel global
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
    echo "[$timestamp] $1" >> "${LOG_FILE:-/tmp/email_trader_fallback.log}"
}

# --- Fungsi Background Listener dengan Redirection ---

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
    [ $mutt_exit_code -ne 0 ] && log_message "WARNING: Perintah $EMAIL_CLIENT keluar dengan kode $mutt_exit_code (Mungkin tidak ada email baru atau error koneksi)"

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
        return 0
    else
        # Jika exit code 0 tapi file kosong, berarti tidak ada email cocok
        [ $mutt_exit_code -eq 0 ] && log_message "Tidak ada email baru yang cocok ditemukan."
        rm "$email_body_file"
        return 1
    fi
}

# Fungsi parsing body email
parse_email_body() {
    local body_file="$1"
    log_message "Parsing isi email dari $body_file"
    local action=""

    if grep -qi "buy" "$body_file" 2>>"$LOG_FILE"; then
        action="BUY"
    elif grep -qi "sell" "$body_file" 2>>"$LOG_FILE"; then
        action="SELL"
    fi

    if ! grep -q "$EMAIL_IDENTIFIER" "$body_file" 2>>"$LOG_FILE"; then
        log_message "WARNING: Action '$action' terdeteksi, tapi identifier '$EMAIL_IDENTIFIER' tidak ditemukan di body email ini. Mengabaikan."
        return 1
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
        return 1
    fi
}

# Fungsi untuk menandai email sebagai sudah dibaca
mark_email_as_read() {
    log_message "Menandai email sebagai sudah dibaca..."
    "$EMAIL_CLIENT" \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail=""' \
        -e 'push "<limit>~N (~b \"'${EMAIL_IDENTIFIER}'\" | ~s \"'${EMAIL_IDENTIFIER}'\")\n<clear-flag>N\n<sync-mailbox><exit>"' > /dev/null 2>&1
    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        log_message "Perintah untuk menandai email dibaca telah dikirim."
    else
        log_message "WARNING: Perintah $EMAIL_CLIENT untuk menandai email dibaca mungkin gagal (exit code: $exit_code)."
    fi
}

# Fungsi generate signature Binance
generate_binance_signature() {
    local query_string="$1"
    local secret="$2"
    echo -n "$query_string" | openssl dgst -sha256 -hmac "$secret" 2>>"$LOG_FILE" | sed 's/^.* //'
}

# Fungsi eksekusi order Binance
execute_binance_order() {
    local side="$1"
    local timestamp
    timestamp=$(date +%s%3N)
    if [[ -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$TRADE_SYMBOL" || -z "$TRADE_QUANTITY" ]]; then
        log_message "ERROR: Konfigurasi Binance tidak lengkap. Tidak bisa membuat order."
        return 1
    fi

    local api_endpoint="https://api.binance.com"
    local order_path="/api/v3/order"
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
    response=$(curl -s -w "%{http_code}" -H "X-MBX-APIKEY: ${BINANCE_API_KEY}" -X POST "$full_url" 2>>"$LOG_FILE")
    curl_exit_code=$?
    http_code="${response: -3}"
    body="${response:0:${#response}-3}"

    if [ $curl_exit_code -ne 0 ]; then
        log_message "ERROR: curl gagal menghubungi Binance (Curl Exit code: $curl_exit_code). Cek log untuk detail stderr curl."
        return 1
    fi

    log_message "Response Binance (HTTP $http_code): $body"

    if [[ "$http_code" =~ ^2 ]]; then
        local orderId status
        orderId=$(echo "$body" | jq -r '.orderId // empty' 2>>"$LOG_FILE")
        status=$(echo "$body" | jq -r '.status // "UNKNOWN"' 2>>"$LOG_FILE")
        if [ -n "$orderId" ]; then
            log_message "SUCCESS: Order berhasil ditempatkan. Order ID: $orderId, Status: $status"
            return 0
        else
            log_message "WARNING: HTTP 2xx diterima tapi tidak ada Order ID di response JSON. Body: $body"
            return 0 # Consider success if HTTP 2xx
        fi
    else
        local err_code err_msg
        err_code=$(echo "$body" | jq -r '.code // "?"' 2>>"$LOG_FILE")
        err_msg=$(echo "$body" | jq -r '.msg // "Tidak ada pesan error spesifik"' 2>>"$LOG_FILE")
        log_message "ERROR: Gagal menempatkan order. Kode Error Binance: $err_code Pesan: $err_msg"
        # Optionally: Send notification about failed order here
        return 1
    fi
}

# Fungsi untuk Loop Utama Listener
run_listener() {
    log_message "Memulai mode listening..."
    if ! [[ "$CHECK_INTERVAL" =~ ^[1-9][0-9]*$ ]]; then
        log_message "WARNING: Interval cek email tidak valid ($CHECK_INTERVAL). Menggunakan default 60 detik."
        CHECK_INTERVAL=60
    fi

    (
        trap 'echo "[$(date "+%Y-%m-%d %H:%M:%S")] INFO: Listener loop (PID $$) dihentikan oleh sinyal."; exit 0' SIGTERM SIGINT
        while true; do
            log_message "[Loop PID $$] Memulai siklus pengecekan email..."
            check_email
            log_message "[Loop PID $$] Siklus selesai. Menunggu ${CHECK_INTERVAL} detik..."
            sleep "$CHECK_INTERVAL"

            local max_log_lines=1000
            local current_lines
            current_lines=$(wc -l < "$LOG_FILE" 2>>"$LOG_FILE")
            if [[ "$current_lines" =~ ^[0-9]+$ && "$current_lines" -gt "$max_log_lines" ]]; then
                 log_message "[Loop PID $$] INFO: File log dipangkas ke $max_log_lines baris terakhir."
                 tail -n "$max_log_lines" "$LOG_FILE" > "${LOG_FILE}.tmp" 2>>"$LOG_FILE" && mv "${LOG_FILE}.tmp" "$LOG_FILE" 2>>"$LOG_FILE"
            elif ! [[ "$current_lines" =~ ^[0-9]+$ ]]; then
                 log_message "[Loop PID $$] WARNING: Gagal mendapatkan jumlah baris log (output wc: $current_lines)."
            fi
        done
    ) &
    LISTENER_PID=$!
    log_message "Listener berjalan di background (PID: $LISTENER_PID)."

    clear
    dialog --title "Email Listener & Binance Trader - Log Aktivitas (PID: $LISTENER_PID)" \
           --no-kill \
           --tailboxbg "$LOG_FILE" 25 90

    log_message "Menutup tampilan log. Mengirim sinyal TERM ke listener background (PID: $LISTENER_PID)..."
    if kill -0 "$LISTENER_PID" 2>/dev/null; then
        kill -TERM "$LISTENER_PID" 2>/dev/null
        sleep 1
        if kill -0 "$LISTENER_PID" 2>/dev/null; then
            log_message "WARNING: Listener background (PID: $LISTENER_PID) tidak berhenti dengan TERM, mengirim KILL."
            kill -KILL "$LISTENER_PID" 2>/dev/null
        fi
    else
        log_message "INFO: Listener background (PID: $LISTENER_PID) sudah tidak berjalan."
    fi
    wait "$LISTENER_PID" 2>/dev/null
    log_message "Listener background seharusnya sudah berhenti."
    clear
    echo "Listener dihentikan. Kembali ke menu utama."
    LISTENER_PID=""
}

# Fungsi Tampilkan Log
view_log() {
    clear
    if [ -f "$LOG_FILE" ]; then
        dialog --title "Log Aktivitas ($LOG_FILE)" --cr-wrap --textbox "$LOG_FILE" 25 90
    else
        info_msg "File log ($LOG_FILE) belum ada atau kosong."
    fi
}

# Fungsi Menu Utama
main_menu() {
    while true; do
        clear
        local listener_status_msg=""
        if [[ -n "$LISTENER_PID" ]] && kill -0 "$LISTENER_PID" 2>/dev/null; then
            listener_status_msg=" (Listener Aktif - PID: $LISTENER_PID)"
        fi

        CHOICE=$(dialog --clear --stdout \
                        --title "Email Trader - Menu Utama$listener_status_msg" \
                        --cancel-label "Keluar" \
                        --menu "Pilih tindakan:" 15 60 4 \
                        1 "Mulai/Lihat Listening Email" \
                        2 "Pengaturan" \
                        3 "Lihat Log Statis" \
                        4 "Keluar dari Script")

        exit_status=$?

        if [ $exit_status -ne 0 ]; then
            clear
            if [[ -n "$LISTENER_PID" ]] && kill -0 "$LISTENER_PID" 2>/dev/null; then
                echo "Menghentikan listener (PID: $LISTENER_PID) sebelum keluar..."
                kill -TERM "$LISTENER_PID" 2>/dev/null
                wait "$LISTENER_PID" 2>/dev/null
                echo "Listener dihentikan."
            fi
            echo "Script dihentikan oleh pengguna."
            log_message "--- Script Dihentikan oleh Pengguna ---"
            exit 0
        fi

        case "$CHOICE" in
            1)
                if [[ -n "$LISTENER_PID" ]] && kill -0 "$LISTENER_PID" 2>/dev/null; then
                     clear
                     dialog --title "Listener Sudah Aktif - Log Aktivitas (PID: $LISTENER_PID)" \
                            --no-kill \
                            --tailboxbg "$LOG_FILE" 25 90
                     log_message "Menutup tampilan log (listener tetap jalan)."
                elif load_config; then
                    run_listener
                else
                    error_msg "Konfigurasi belum lengkap atau tidak valid. Silakan masuk ke 'Pengaturan' terlebih dahulu."
                fi
                ;;
            2)
                configure_settings
                ;;
            3)
                view_log
                ;;
            4)
                clear
                if [[ -n "$LISTENER_PID" ]] && kill -0 "$LISTENER_PID" 2>/dev/null; then
                    echo "Menghentikan listener (PID: $LISTENER_PID) sebelum keluar..."
                    kill -TERM "$LISTENER_PID" 2>/dev/null
                    wait "$LISTENER_PID" 2>/dev/null
                    echo "Listener dihentikan."
                fi
                echo "Script dihentikan."
                log_message "--- Script Dihentikan via Menu Keluar ---"
                exit 0
                ;;
            *)
                error_msg "Pilihan tidak valid."
                ;;
        esac
    done
}

# --- Main Program Execution ---

LISTENER_PID=""
trap '
  log_message "--- Script Menerima Sinyal Exit (SIGINT/SIGTERM) ---"
  if [[ -n "$LISTENER_PID" ]] && kill -0 "$LISTENER_PID" 2>/dev/null; then
    echo " Menghentikan listener (PID: $LISTENER_PID)..."
    kill -TERM "$LISTENER_PID" 2>/dev/null
    wait "$LISTENER_PID" 2>/dev/null
  fi
  echo " Script dihentikan."
  clear
  exit 130 # Standard exit code for Ctrl+C
' SIGINT SIGTERM

check_deps
log_message "--- Script Email Trader v1.3 Dimulai ---"

if ! load_config; then
    clear
    dialog --title "Setup Awal Diperlukan" \
           --msgbox "File konfigurasi ($CONFIG_FILE) tidak ditemukan atau tidak lengkap.\n\nAnda akan diarahkan ke menu konfigurasi." 10 70
    if ! configure_settings; then
        clear
        echo "Konfigurasi awal dibatalkan atau gagal. Script tidak dapat dilanjutkan."
        log_message "FATAL: Konfigurasi awal gagal. Script berhenti."
        exit 1
    fi
    if ! load_config; then
        clear
        echo "Gagal memuat konfigurasi setelah setup awal. Script berhenti."
        log_message "FATAL: Gagal memuat konfigurasi setelah setup. Script berhenti."
        exit 1
    fi
fi

main_menu

exit 0
