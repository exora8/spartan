#!/usr/bin/env bash

# Script Email Listener & Binance Trader
# Versi: 1.2 (Fix Dialog Overlap & Refined Redirection)
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
    # Clear screen before showing dialog to remove potential stray output
    clear
    dialog --title "Error" --msgbox "$1" 8 60
    log_message "ERROR_DIALOG: $1" # Catat error ke log juga
}

# Fungsi untuk menampilkan info dengan dialog
info_msg() {
    # Clear screen before showing dialog
    clear
    dialog --title "Info" --msgbox "$1" 8 60
}

# Fungsi cek dependensi (Tidak berubah signifikan, tapi pastikan semua ada)
check_deps() {
    local missing_deps=()
    # Tambahkan semua command yang dibutuhkan script
    for cmd in dialog neomutt curl openssl jq grep sed awk cut date mktemp tail wc kill sleep wait clear; do
        if ! command -v "$cmd" &> /dev/null; then
            missing_deps+=("$cmd")
        fi
    done

    # Cek mutt sebagai fallback neomutt
    if ! command -v neomutt &> /dev/null && ! command -v mutt &> /dev/null; then
         missing_deps+=("neomutt atau mutt")
    fi

    if [ ${#missing_deps[@]} -ne 0 ]; then
        # Tampilkan error tanpa dialog jika dialog belum tentu ada
        echo "ERROR: Dependensi berikut tidak ditemukan atau tidak ada di PATH:" >&2
        printf " - %s\n" "${missing_deps[@]}" >&2
        echo "Silakan install terlebih dahulu sebelum menjalankan script." >&2
        # Coba tampilkan dialog jika dialog ADA, sebagai tambahan
        if command -v dialog &> /dev/null; then
            # No clear here as dialog might not be fully functional yet
            dialog --title "Error Dependensi" --cr-wrap --msgbox "Dependensi berikut tidak ditemukan:\n\n$(printf -- '- %s\n' "${missing_deps[@]}")\n\nSilakan install terlebih dahulu." 15 70
        fi
        exit 1
    fi
    # Pilih email client yang tersedia
    EMAIL_CLIENT=$(command -v neomutt || command -v mutt)
    # Tidak perlu log message di sini karena mungkin terlalu awal
    # log_message "Dependensi terpenuhi. Menggunakan email client: $EMAIL_CLIENT"
}

# Fungsi load konfigurasi (Tetap sama, logging sudah ke file)
load_config() {
    if [ -f "$CONFIG_FILE" ]; then
        chmod 600 "$CONFIG_FILE" # Pastikan permission benar
        # Source dalam subshell untuk isolasi, cek variabel setelahnya
        # ( source "$CONFIG_FILE" ) # Source can pollute env, parse instead
        GMAIL_USER=$(grep -Po "^GMAIL_USER *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        GMAIL_APP_PASS=$(grep -Po "^GMAIL_APP_PASS *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        BINANCE_API_KEY=$(grep -Po "^BINANCE_API_KEY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        BINANCE_SECRET_KEY=$(grep -Po "^BINANCE_SECRET_KEY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        TRADE_SYMBOL=$(grep -Po "^TRADE_SYMBOL *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        TRADE_QUANTITY=$(grep -Po "^TRADE_QUANTITY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        CHECK_INTERVAL=$(grep -Po "^CHECK_INTERVAL *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)

        # Validasi variabel penting
        if [[ -z "$GMAIL_USER" || -z "$GMAIL_APP_PASS" || -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$TRADE_SYMBOL" || -z "$TRADE_QUANTITY" || -z "$CHECK_INTERVAL" ]]; then
            log_message "WARNING: File konfigurasi $CONFIG_FILE ada tapi tidak lengkap atau gagal parse."
            return 1 # Konfigurasi tidak lengkap
        fi
        log_message "Konfigurasi berhasil dimuat dari $CONFIG_FILE."
        CHECK_INTERVAL="${CHECK_INTERVAL:-60}" # Default jika ada tapi kosong
        return 0 # Sukses load
    else
        log_message "INFO: File konfigurasi $CONFIG_FILE tidak ditemukan."
        return 1 # File tidak ada
    fi
}

# Fungsi simpan konfigurasi (Tetap sama, info_msg akan clear screen)
save_config() {
    rm -f "$CONFIG_FILE"
    echo "# Konfigurasi Email Trader (v1.2)" > "$CONFIG_FILE"
    echo "GMAIL_USER='${GMAIL_USER}'" >> "$CONFIG_FILE"
    echo "GMAIL_APP_PASS='${GMAIL_APP_PASS}'" >> "$CONFIG_FILE"
    echo "BINANCE_API_KEY='${BINANCE_API_KEY}'" >> "$CONFIG_FILE"
    echo "BINANCE_SECRET_KEY='${BINANCE_SECRET_KEY}'" >> "$CONFIG_FILE"
    echo "TRADE_SYMBOL='${TRADE_SYMBOL}'" >> "$CONFIG_FILE"
    echo "TRADE_QUANTITY='${TRADE_QUANTITY}'" >> "$CONFIG_FILE"
    echo "CHECK_INTERVAL='${CHECK_INTERVAL}'" >> "$CONFIG_FILE"
    chmod 600 "$CONFIG_FILE"
    log_message "Konfigurasi berhasil disimpan di $CONFIG_FILE"
    info_msg "Konfigurasi berhasil disimpan di $CONFIG_FILE" # info_msg akan clear screen
}

# Fungsi konfigurasi interaktif (Menambahkan clear sebelum dialog)
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
    input_gmail_pass=$(dialog --stdout --title "Konfigurasi" --passwordbox "Gmail App Password Anda (Bukan Password Utama!):" 8 70 "$temp_gmail_pass")
    exit_status=$?
    [[ $exit_status -ne 0 ]] && { info_msg "Konfigurasi dibatalkan."; return 1; }

    clear
    input_api_key=$(dialog --stdout --title "Konfigurasi" --inputbox "Binance API Key Anda:" 8 70 "$temp_api_key")
    exit_status=$?
    [[ $exit_status -ne 0 ]] && { info_msg "Konfigurasi dibatalkan."; return 1; }

    clear
    input_secret_key=$(dialog --stdout --title "Konfigurasi" --passwordbox "Binance Secret Key Anda:" 8 70 "$temp_secret_key")
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
         error_msg "Semua field konfigurasi harus diisi." # error_msg akan clear screen
         return 1
    fi
    if ! [[ "$input_interval" =~ ^[1-9][0-9]*$ ]]; then
        error_msg "Interval cek email harus berupa angka positif (detik)."
        return 1
     fi
     if ! [[ "$input_quantity" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
        error_msg "Quantity trading harus berupa angka (misal: 0.001 atau 10)."
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

    save_config # Simpan konfigurasi (akan memanggil info_msg -> clear)
    return 0
}

# Fungsi untuk logging ke file (Tetap sama)
log_message() {
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] $1" >> "${LOG_FILE:-/tmp/email_trader_fallback.log}"
}

# --- Fungsi Background Listener dengan Redirection ---

# Fungsi cek email baru yang cocok (MODIFIED: Redirect stderr)
check_email() {
    log_message "Mencari email baru dari $GMAIL_USER dengan identifier: '$EMAIL_IDENTIFIER'"
    local email_body_file
    # Redirect stderr of mktemp to log file
    email_body_file=$(mktemp 2>>"$LOG_FILE") || { log_message "ERROR: Gagal membuat file temporary untuk email."; return 1; }

    # Neomutt command already redirects its own stdout/stderr
    # Pastikan tidak ada output yang tidak diinginkan dari neomutt/mutt
    "$EMAIL_CLIENT" \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail=""' \
        -e 'push "<limit>~N (~b \"'${EMAIL_IDENTIFIER}'\" | ~s \"'${EMAIL_IDENTIFIER}'\")\n<pipe-message>cat > '${email_body_file}'\n<exit>"' > /dev/null 2>&1
    local mutt_exit_code=$?
    # Log jika mutt/neomutt keluar dengan error, tapi jangan print ke terminal
    [ $mutt_exit_code -ne 0 ] && log_message "WARNING: Perintah $EMAIL_CLIENT keluar dengan kode $mutt_exit_code"


    if [ -s "$email_body_file" ]; then
        log_message "Email yang cocok ditemukan. Memproses..."
        parse_email_body "$email_body_file"
        local parse_status=$?
        rm "$email_body_file" # Tetap hapus file temp
        if [ $parse_status -eq 0 ]; then
             mark_email_as_read
        else
             log_message "Action tidak ditemukan atau gagal parse, email tidak ditandai dibaca."
        fi
        return 0
    else
        log_message "Tidak ada email baru yang cocok ditemukan."
        rm "$email_body_file"
        return 1
    fi
}

# Fungsi parsing body email (MODIFIED: Redirect grep stderr if any)
parse_email_body() {
    local body_file="$1"
    log_message "Parsing isi email dari $body_file"
    local action=""

    # Redirect stderr just in case grep fails unexpectedly
    if grep -qi "buy" "$body_file" 2>>"$LOG_FILE"; then
        action="BUY"
    elif grep -qi "sell" "$body_file" 2>>"$LOG_FILE"; then
        action="SELL"
    fi

    # Redirect stderr for the identifier check too
    if ! grep -q "$EMAIL_IDENTIFIER" "$body_file" 2>>"$LOG_FILE"; then
        log_message "WARNING: Action '$action' terdeteksi, tapi identifier '$EMAIL_IDENTIFIER' tidak ditemukan di body email ini. Mengabaikan."
        return 1
    fi

    if [[ "$action" == "BUY" ]]; then
        log_message "Action terdeteksi: BUY"
        execute_binance_order "BUY" # execute_binance_order handles its own logging/redirection
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

# Fungsi untuk menandai email sebagai sudah dibaca (MODIFIED: Log neomutt errors)
mark_email_as_read() {
    log_message "Menandai email sebagai sudah dibaca..."
    # Neomutt command already redirects its own stdout/stderr
    "$EMAIL_CLIENT" \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail=""' \
        -e 'push "<limit>~N (~b \"'${EMAIL_IDENTIFIER}'\" | ~s \"'${EMAIL_IDENTIFIER}'\")\n<clear-flag>N\n<sync-mailbox><exit>"' > /dev/null 2>&1
    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        log_message "Perintah untuk menandai email dibaca telah dikirim."
    else
        # Log the error, don't print to terminal
        log_message "WARNING: Perintah $EMAIL_CLIENT untuk menandai email dibaca mungkin gagal (exit code: $exit_code)."
    fi
}

# Fungsi generate signature Binance (MODIFIED: Redirect openssl stderr)
generate_binance_signature() {
    local query_string="$1"
    local secret="$2"
    # Redirect stderr of openssl to the log file
    echo -n "$query_string" | openssl dgst -sha256 -hmac "$secret" 2>>"$LOG_FILE" | sed 's/^.* //'
}

# Fungsi eksekusi order Binance (MODIFIED: Redirect curl stderr)
execute_binance_order() {
    local side="$1"
    local timestamp
    timestamp=$(date +%s%3N)
    if [[ -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$TRADE_SYMBOL" || -z "$TRADE_QUANTITY" ]]; then
        log_message "ERROR: Konfigurasi Binance tidak lengkap. Tidak bisa membuat order."
        # Don't call error_msg here as this runs in background
        return 1
    fi

    local api_endpoint="https://api.binance.com"
    local order_path="/api/v3/order"
    local params="symbol=${TRADE_SYMBOL}&side=${side}&type=MARKET&quantity=${TRADE_QUANTITY}×tamp=${timestamp}"
    local signature
    signature=$(generate_binance_signature "$params" "$BINANCE_SECRET_KEY")
    # Check if signature generation failed (e.g., openssl error)
    if [ -z "$signature" ]; then
        log_message "ERROR: Gagal menghasilkan signature Binance. Periksa error openssl di log."
        return 1
    fi

    local full_url="${api_endpoint}${order_path}?${params}&signature=${signature}"
    log_message "Mengirim order ke Binance: SIDE=$side SYMBOL=$TRADE_SYMBOL QTY=$TRADE_QUANTITY"

    local response curl_exit_code http_code body
    # Execute curl: silent (-s), write http_code (-w), redirect stderr (2>>) to log file
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
            # Consider it success if HTTP 2xx, even if parsing fails
            return 0
        fi
    else
        local err_code err_msg
        err_code=$(echo "$body" | jq -r '.code // "?"' 2>>"$LOG_FILE")
        err_msg=$(echo "$body" | jq -r '.msg // "Tidak ada pesan error spesifik"' 2>>"$LOG_FILE")
        log_message "ERROR: Gagal menempatkan order. Kode Error Binance: $err_code Pesan: $err_msg"
        return 1
    fi
}

# --- Fungsi untuk Loop Utama Listener (MODIFIED: Redirect stderr for log trim) ---
run_listener() {
    log_message "Memulai mode listening..."
    if ! [[ "$CHECK_INTERVAL" =~ ^[1-9][0-9]*$ ]]; then
        log_message "WARNING: Interval cek email tidak valid ($CHECK_INTERVAL). Menggunakan default 60 detik."
        # Don't use error_msg here
        CHECK_INTERVAL=60
    fi

    # Jalankan loop utama di background process
    (
        trap 'echo "[$(date "+%Y-%m-%d %H:%M:%S")] INFO: Listener loop (PID $$) dihentikan oleh sinyal."; exit 0' SIGTERM SIGINT
        while true; do
            log_message "[Loop PID $$] Memulai siklus pengecekan email..."
            check_email # Handles its own logging/redirection
            log_message "[Loop PID $$] Siklus selesai. Menunggu ${CHECK_INTERVAL} detik..."
            sleep "$CHECK_INTERVAL"

            # Batasi ukuran file log (redirect stderr of wc, tail, mv)
            local max_log_lines=1000
            local current_lines
            current_lines=$(wc -l < "$LOG_FILE" 2>>"$LOG_FILE") # Redirect wc error
            if [[ "$current_lines" =~ ^[0-9]+$ && "$current_lines" -gt "$max_log_lines" ]]; then
                 log_message "[Loop PID $$] INFO: File log dipangkas ke $max_log_lines baris terakhir."
                 # Redirect tail and mv stderr to log file
                 tail -n "$max_log_lines" "$LOG_FILE" > "${LOG_FILE}.tmp" 2>>"$LOG_FILE" && mv "${LOG_FILE}.tmp" "$LOG_FILE" 2>>"$LOG_FILE"
            elif ! [[ "$current_lines" =~ ^[0-9]+$ ]]; then
                 log_message "[Loop PID $$] WARNING: Gagal mendapatkan jumlah baris log (output wc: $current_lines)."
            fi
        done
    ) & # Run the subshell in the background
    LISTENER_PID=$!
    log_message "Listener berjalan di background (PID: $LISTENER_PID)."

    # Tampilkan log menggunakan dialog --tailboxbg
    # Clear screen before showing the tailbox
    clear
    dialog --title "Email Listener & Binance Trader - Log Aktivitas (PID: $LISTENER_PID)" \
           --no-kill \
           --tailboxbg "$LOG_FILE" 25 90

    # Setelah dialog ditutup
    log_message "Menutup tampilan log. Mengirim sinyal TERM ke listener background (PID: $LISTENER_PID)..."
    if kill -0 "$LISTENER_PID" 2>/dev/null; then
        kill -TERM "$LISTENER_PID" 2>/dev/null
        # Wait briefly for cleanup
        sleep 1
        # Check if it's still alive, force kill if needed (optional)
        if kill -0 "$LISTENER_PID" 2>/dev/null; then
            log_message "WARNING: Listener background (PID: $LISTENER_PID) tidak berhenti dengan TERM, mengirim KILL."
            kill -KILL "$LISTENER_PID" 2>/dev/null
        fi
    else
        log_message "INFO: Listener background (PID: $LISTENER_PID) sudah tidak berjalan."
    fi
    wait "$LISTENER_PID" 2>/dev/null # Clean up zombie process if any
    log_message "Listener background seharusnya sudah berhenti."
    clear
    echo "Listener dihentikan. Kembali ke menu utama."
    # Make sure LISTENER_PID is cleared so we know it's not running
    LISTENER_PID=""
}

# --- Fungsi Tampilkan Log (MODIFIED: Add clear) ---
view_log() {
    # Clear screen before showing log
    clear
    if [ -f "$LOG_FILE" ]; then
        dialog --title "Log Aktivitas ($LOG_FILE)" --cr-wrap --textbox "$LOG_FILE" 25 90
    else
        info_msg "File log ($LOG_FILE) belum ada atau kosong." # info_msg clears screen
    fi
}

# --- Fungsi Menu Utama (MODIFIED: Add clear before menu) ---
main_menu() {
    while true; do
        # Clear screen before showing the menu
        clear
        # Check if listener is running (useful info for the user)
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
            # Stop listener if running before exiting
            if [[ -n "$LISTENER_PID" ]] && kill -0 "$LISTENER_PID" 2>/dev/null; then
                echo "Menghentikan listener (PID: $LISTENER_PID) sebelum keluar..."
                kill -TERM "$LISTENER_PID" 2>/dev/null
                wait "$LISTENER_PID" 2>/dev/null
                echo "Listener dihentikan."
            fi
            echo "Script dihentikan oleh pengguna."
            exit 0
        fi

        case "$CHOICE" in
            1)
                # If listener is already running, just show the log again
                if [[ -n "$LISTENER_PID" ]] && kill -0 "$LISTENER_PID" 2>/dev/null; then
                     clear
                     dialog --title "Listener Sudah Aktif - Log Aktivitas (PID: $LISTENER_PID)" \
                            --no-kill \
                            --tailboxbg "$LOG_FILE" 25 90
                     # Logic after tailboxbg closes is the same as run_listener end
                     log_message "Menutup tampilan log (listener tetap jalan)."
                     # We don't kill it here, let user stop via Ctrl+C in tailbox or exit menu
                # If not running, start it
                elif load_config; then
                    run_listener # run_listener clears screen and handles its own dialog
                else
                    error_msg "Konfigurasi belum lengkap atau tidak valid. Silakan masuk ke 'Pengaturan' terlebih dahulu."
                fi
                ;;
            2)
                configure_settings # configure_settings clears screen for its inputs
                ;;
            3)
                view_log # view_log clears screen
                ;;
            4)
                clear
                 # Stop listener if running before exiting
                if [[ -n "$LISTENER_PID" ]] && kill -0 "$LISTENER_PID" 2>/dev/null; then
                    echo "Menghentikan listener (PID: $LISTENER_PID) sebelum keluar..."
                    kill -TERM "$LISTENER_PID" 2>/dev/null
                    wait "$LISTENER_PID" 2>/dev/null
                    echo "Listener dihentikan."
                fi
                echo "Script dihentikan."
                exit 0
                ;;
            *)
                error_msg "Pilihan tidak valid." # error_msg clears screen
                ;;
        esac
        # No need for sleep here, loop will redraw menu after action
    done
}

# --- Main Program Execution ---

# Make sure LISTENER_PID is initially empty
LISTENER_PID=""

# 0. Cek dependensi paling awal
check_deps

# Initialize log file header
log_message "--- Script Email Trader v1.2 Dimulai ---"

# 1. Load konfigurasi awal atau paksa setup jika belum ada
if ! load_config; then
    # Clear screen before showing setup message
    clear
    dialog --title "Setup Awal Diperlukan" \
           --msgbox "File konfigurasi ($CONFIG_FILE) tidak ditemukan atau tidak lengkap.\n\nAnda akan diarahkan ke menu konfigurasi." 10 70
    if ! configure_settings; then # configure_settings handles its own clear/dialogs
        clear
        echo "Konfigurasi awal dibatalkan atau gagal. Script tidak dapat dilanjutkan."
        log_message "FATAL: Konfigurasi awal gagal. Script berhenti."
        exit 1
    fi
    # Coba load lagi setelah konfigurasi
    if ! load_config; then
        clear
        echo "Gagal memuat konfigurasi setelah setup awal. Script berhenti."
        log_message "FATAL: Gagal memuat konfigurasi setelah setup. Script berhenti."
        exit 1
    fi
fi

# 2. Tampilkan Menu Utama
main_menu

# Should not be reached if main_menu exits properly
exit 0
