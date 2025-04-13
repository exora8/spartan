#!/usr/bin/env bash

# Script Email Listener & Binance Trader
# Versi: 1.9.1 (Fix: Ignore user mutt config with -F /dev/null)
# Author: [Nama Kamu/AI] & Kontributor

# --- Konfigurasi Awal ---
CONFIG_FILE="$HOME/.email_trader_rc"
LOG_FILE="$HOME/.email_trader.log"
MAX_LOG_LINES=50
PID_FILE="/tmp/email_trader.pid"

# Buat file log jika belum ada dan set permission
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"

# Identifier Email yang Dicari (WAJIB ADA di body email target)
EMAIL_IDENTIFIER="Exora AI (V5 SPOT + SR Filter) (1M)" # Pastikan ini persis

# --- Variabel Global ---
LISTENER_PID=""
SCRIPT_MAIN_PID=$$
DEFAULT_CHECK_INTERVAL=5

# --- Fungsi ---

# Fungsi untuk menampilkan pesan error dengan dialog
error_msg() {
    clear
    dialog --title "Error" --msgbox "$1" 8 70
    log_message "ERROR_DIALOG: $1"
}

# Fungsi untuk menampilkan info dengan dialog
info_msg() {
    clear
    dialog --title "Info" --msgbox "$1" 8 70
}

# Fungsi cek dependensi
check_deps() {
    local missing_deps=()
    for cmd in dialog neomutt curl openssl jq grep sed awk cut date mktemp tail wc kill sleep clear pgrep wc; do
        if ! command -v "$cmd" &> /dev/null; then
            missing_deps+=("$cmd")
        fi
    done
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
        chmod 600 "$CONFIG_FILE"
        GMAIL_USER=$(grep -Po "^GMAIL_USER *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        GMAIL_APP_PASS=$(grep -Po "^GMAIL_APP_PASS *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        BINANCE_API_KEY=$(grep -Po "^BINANCE_API_KEY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        BINANCE_SECRET_KEY=$(grep -Po "^BINANCE_SECRET_KEY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        TRADE_SYMBOL=$(grep -Po "^TRADE_SYMBOL *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        TRADE_QUANTITY=$(grep -Po "^TRADE_QUANTITY *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)
        CHECK_INTERVAL=$(grep -Po "^CHECK_INTERVAL *= *['\"]\K[^'\"]*" "$CONFIG_FILE" 2>/dev/null)

        if [[ -z "$GMAIL_USER" || -z "$GMAIL_APP_PASS" || -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$TRADE_SYMBOL" || -z "$TRADE_QUANTITY" ]]; then
            log_message "WARNING: File konfigurasi $CONFIG_FILE ada tapi tidak lengkap atau gagal parse."
            CHECK_INTERVAL="${CHECK_INTERVAL:-$DEFAULT_CHECK_INTERVAL}"
            return 1
        fi
        if ! [[ "$CHECK_INTERVAL" =~ ^[1-9][0-9]*$ ]]; then
            log_message "WARNING: Interval di config tidak valid ('$CHECK_INTERVAL'), pakai default $DEFAULT_CHECK_INTERVAL detik."
            CHECK_INTERVAL="$DEFAULT_CHECK_INTERVAL"
        fi
        log_message "Konfigurasi berhasil dimuat dari $CONFIG_FILE. Interval: $CHECK_INTERVAL detik."
        return 0
    else
        log_message "INFO: File konfigurasi $CONFIG_FILE tidak ditemukan."
        CHECK_INTERVAL="$DEFAULT_CHECK_INTERVAL"
        return 1
    fi
}

# Fungsi simpan konfigurasi
save_config() {
    mkdir -p "$(dirname "$CONFIG_FILE")"
    rm -f "$CONFIG_FILE"
    {
        echo "# Konfigurasi Email Trader (v1.9.1)" # Update versi di sini jika perlu
        echo "GMAIL_USER='${GMAIL_USER}'"
        echo "GMAIL_APP_PASS='${GMAIL_APP_PASS}'"
        echo "BINANCE_API_KEY='${BINANCE_API_KEY}'"
        echo "BINANCE_SECRET_KEY='${BINANCE_SECRET_KEY}'"
        echo "TRADE_SYMBOL='${TRADE_SYMBOL}'"
        echo "TRADE_QUANTITY='${TRADE_QUANTITY}'"
        echo "CHECK_INTERVAL='${CHECK_INTERVAL:-$DEFAULT_CHECK_INTERVAL}'"
    } > "$CONFIG_FILE"

    chmod 600 "$CONFIG_FILE"
    log_message "Konfigurasi berhasil disimpan di $CONFIG_FILE"
    info_msg "Konfigurasi berhasil disimpan di $CONFIG_FILE"
}

# Fungsi konfigurasi interaktif
configure_settings() {
    if is_listener_running; then
        error_msg "Listener sedang aktif (PID: $LISTENER_PID). Hentikan listener terlebih dahulu."
        return 1
    fi

    load_config

    local temp_gmail_user="${GMAIL_USER}"
    local temp_gmail_pass="${GMAIL_APP_PASS}"
    local temp_api_key="${BINANCE_API_KEY}"
    local temp_secret_key="${BINANCE_SECRET_KEY}"
    local temp_symbol="${TRADE_SYMBOL}"
    local temp_quantity="${TRADE_QUANTITY}"
    local temp_interval="${CHECK_INTERVAL:-$DEFAULT_CHECK_INTERVAL}"

    local input_gmail_user input_gmail_pass input_api_key input_secret_key input_symbol input_quantity input_interval exit_status
    local temp_file
    temp_file=$(mktemp) || { error_msg "Gagal membuat file temporary."; return 1; }
    trap 'rm -f "$temp_file"' RETURN

    exec 3>&1
    dialog --clear --title "Konfigurasi Email Trader" --form "\nMasukkan detail konfigurasi:" 20 70 0 \
        "Alamat Gmail:"          1 1 "$temp_gmail_user"      1 25 60 0 \
        "Gmail App Password:"    2 1 "$temp_gmail_pass"      2 25 60 0 \
        "Binance API Key:"       3 1 "$temp_api_key"       3 25 60 0 \
        "Binance Secret Key:"    4 1 "$temp_secret_key"    4 25 60 0 \
        "Simbol Trading (cth: BTCUSDT):" 5 1 "$temp_symbol"    5 25 60 0 \
        "Quantity Trading (cth: 0.001):" 6 1 "$temp_quantity"  6 25 60 0 \
        "Interval Cek (detik, min 1):" 7 1 "$temp_interval"  7 25 60 0 \
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
        error_msg "Interval cek email harus berupa angka positif minimal 1 (detik)."
        return 1
     fi
     if ! [[ "$input_quantity" =~ ^[+]?([0-9]+(\.[0-9]*)?|\.[0-9]+)$ ]] || ! awk "BEGIN {exit !($input_quantity > 0)}"; then
        error_msg "Quantity trading harus berupa angka positif lebih besar dari 0."
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

# Fungsi untuk logging
log_message() {
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local pid_info="[PID $$]"
    echo "[$timestamp]$pid_info $1" >> "$LOG_FILE"
}

# --- Fungsi Background Listener ---

# Fungsi cek SEMUA email baru, lalu parse jika identifier cocok
check_email() {
    local email_body_file
    email_body_file=$(mktemp --suffix=.eml) || { log_message "ERROR: Gagal membuat file temporary email."; return 1; }
    trap 'rm -f "$email_body_file"' RETURN

    # ===========================================================
    # MODIFIED: Added -F /dev/null to ignore user config file
    # ===========================================================
    "$EMAIL_CLIENT" -F /dev/null \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail="" query_command="" pager_stop=yes' \
        -e 'push "<limit>~U\n<pipe-message>cat > '${email_body_file}'\n<exit>"' \
        > /dev/null 2>> "$LOG_FILE"

    local mutt_exit_code=$?
    if [[ $mutt_exit_code -ne 0 && $mutt_exit_code -ne 1 ]]; then
        log_message "WARNING: Perintah $EMAIL_CLIENT cek email keluar dgn kode $mutt_exit_code (Mungkin error koneksi/auth?)"
    fi

    if [ -s "$email_body_file" ]; then
        log_message "Email baru (unread) terdeteksi. Memeriksa isi..."
        if parse_email_body "$email_body_file"; then
             mark_email_as_read
             return 0
        else
             log_message "Email baru diabaikan (identifier/action tidak cocok/ditemukan)."
             return 1
        fi
    else
        return 1
    fi
}

# Fungsi parsing body email: CEK IDENTIFIER DULU, baru action
parse_email_body() {
    local body_file="$1"
    local action=""

    # 1. Cek identifier
    if ! grep -qF "$EMAIL_IDENTIFIER" "$body_file"; then
        # log_message "DEBUG: Identifier '$EMAIL_IDENTIFIER' tidak ditemukan."
        return 1
    fi

    # 2. Jika identifier ada, cek action
    log_message "Identifier '$EMAIL_IDENTIFIER' ditemukan! Mencari action..."
    if grep -qim 1 "order buy" "$body_file"; then
        action="BUY"
    elif grep -qim 1 "order sell" "$body_file"; then
        action="SELL"
    fi

    # 3. Eksekusi
    if [[ "$action" == "BUY" ]]; then
        log_message "Action terdeteksi: BUY"
        execute_binance_order "BUY" "$TRADE_SYMBOL" "$TRADE_QUANTITY"
        return $?
    elif [[ "$action" == "SELL" ]]; then
        log_message "Action terdeteksi: SELL"
        execute_binance_order "SELL" "$TRADE_SYMBOL" "$TRADE_QUANTITY"
        return $?
    else
        log_message "WARNING: Identifier ditemukan, TAPI 'order buy'/'order sell' tidak valid terdeteksi."
        # log_message "DEBUG: Isi email (awal): $(head -n 10 "$body_file")"
        return 1
    fi
}

# Fungsi untuk menandai email sebagai sudah dibaca
mark_email_as_read() {
    log_message "Menandai email (yang cocok '$EMAIL_IDENTIFIER') sebagai sudah dibaca..."
    # ===========================================================
    # MODIFIED: Added -F /dev/null to ignore user config file
    # ===========================================================
    "$EMAIL_CLIENT" -F /dev/null \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail="" query_command=""' \
        -e 'push "<limit>~U ~S \"'${EMAIL_IDENTIFIER}'\"\n<clear-flag>N\n<sync-mailbox><exit>"' > /dev/null 2>> "$LOG_FILE"
    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        log_message "Perintah tandai dibaca untuk email '$EMAIL_IDENTIFIER' dikirim."
    else
        [[ $exit_code -ne 1 ]] && log_message "WARNING: Perintah tandai dibaca mungkin gagal (exit code: $exit_code)."
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
    local side="$1"; local symbol="$2"; local quantity="$3"
    local timestamp; timestamp=$(date +%s%3N)

    if [[ -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$symbol" || -z "$quantity" ]]; then
        log_message "ERROR: Konfigurasi Binance tidak lengkap. Order dibatalkan."; return 1
    fi

    local api_endpoint="https://api.binance.com"; local order_path="/api/v3/order"
    local params="symbol=${symbol}&side=${side}&type=MARKET&quantity=${quantity}×tamp=${timestamp}"
    local signature; signature=$(generate_binance_signature "$params" "$BINANCE_SECRET_KEY")
    if [ -z "$signature" ]; then log_message "ERROR: Gagal generate signature Binance."; return 1; fi

    local full_url="${api_endpoint}${order_path}"; local post_data="${params}&signature=${signature}"
    log_message "Mengirim order ke Binance: $side $symbol Qty:$quantity"
    # log_message "DEBUG: URL=$full_url DATA=$params" # JANGAN log signature

    local response curl_exit_code http_code body
    response=$(curl --connect-timeout 15 --max-time 25 -s -w "\n%{http_code}" \
                  -H "X-MBX-APIKEY: ${BINANCE_API_KEY}" -X POST "$full_url" -d "$post_data" 2>>"$LOG_FILE")
    curl_exit_code=$?
    http_code=$(echo "$response" | tail -n1); body=$(echo "$response" | sed '$d')

    if [ $curl_exit_code -ne 0 ]; then
        log_message "ERROR: curl gagal hubungi Binance (Exit: $curl_exit_code). Periksa koneksi."; return 1
    fi
    log_message "Response Binance (HTTP $http_code): $body"

    if [[ "$http_code" =~ ^2 ]]; then
        local orderId status; orderId=$(echo "$body" | jq -r '.orderId // empty'); status=$(echo "$body" | jq -r '.status // "UNKNOWN"')
        if [[ -n "$orderId" && "$status" != "UNKNOWN" ]]; then
            log_message "SUCCESS: Order $side $symbol $quantity berhasil. ID: $orderId, Status: $status"; return 0
        else
            log_message "WARNING: Order $side $symbol $quantity - HTTP $http_code OK tapi response aneh. Body: $body"; return 0
        fi
    else
        local err_code err_msg; err_code=$(echo "$body" | jq -r '.code // "?"'); err_msg=$(echo "$body" | jq -r '.msg // "Error tidak diketahui."')
        log_message "ERROR: Gagal order $side $symbol. Binance Err: $err_code Msg: $err_msg"; return 1
    fi
}

# Fungsi Loop Utama Listener
listener_loop() {
    export GMAIL_USER GMAIL_APP_PASS BINANCE_API_KEY BINANCE_SECRET_KEY TRADE_SYMBOL TRADE_QUANTITY EMAIL_IDENTIFIER EMAIL_CLIENT LOG_FILE CHECK_INTERVAL MAX_LOG_LINES

    local current_interval="${CHECK_INTERVAL:-$DEFAULT_CHECK_INTERVAL}"
    if ! [[ "$current_interval" =~ ^[1-9][0-9]*$ ]]; then
        log_message "ERROR_LISTENER: Interval '$current_interval' tidak valid. Pakai $DEFAULT_CHECK_INTERVAL dtk."
        current_interval=$DEFAULT_CHECK_INTERVAL
    fi

    trap 'log_message "Listener loop (PID $$) dihentikan sinyal."; exit 0' SIGTERM SIGINT
    log_message "Listener loop dimulai (PID $$). Interval: ${current_interval} dtk. Log max ${MAX_LOG_LINES} baris."

    while true; do
        check_email

        # --- Log Trimming ---
        if [[ -f "$LOG_FILE" && -s "$LOG_FILE" ]]; then
            local line_count; line_count=$(wc -l < "$LOG_FILE")
            if [[ "$line_count" -gt "$MAX_LOG_LINES" ]]; then
                local temp_log_file; temp_log_file=$(mktemp) || { log_message "ERROR_LOG_TRIM: Gagal temp file."; continue; }
                tail -n "$MAX_LOG_LINES" "$LOG_FILE" > "$temp_log_file"
                if [[ -s "$temp_log_file" ]]; then
                    mv "$temp_log_file" "$LOG_FILE"; chmod 600 "$LOG_FILE"
                else
                    log_message "ERROR_LOG_TRIM: Gagal pangkas (tail?)."; rm -f "$temp_log_file"
                fi
            fi
        fi
        # --- Akhir Log Trimming ---

        sleep "$current_interval"
    done
}

# --- Fungsi Kontrol Listener ---

is_listener_running() {
    if [ -f "$PID_FILE" ]; then
        local pid; pid=$(cat "$PID_FILE")
        if [[ -n "$pid" ]] && ps -p "$pid" > /dev/null; then LISTENER_PID="$pid"; return 0;
        else log_message "INFO: Hapus PID basi ($PID_FILE) proc $pid."; rm -f "$PID_FILE"; LISTENER_PID=""; return 1; fi
    else LISTENER_PID=""; return 1; fi
}

start_listener() {
    if is_listener_running; then error_msg "Listener sudah jalan (PID: $LISTENER_PID)."; return 1; fi
    if ! load_config; then
         if ! [[ -f "$CONFIG_FILE" ]]; then error_msg "Konfigurasi ($CONFIG_FILE) tidak ada. Buat via Pengaturan."; return 1;
         else error_msg "Konfigurasi ($CONFIG_FILE) error/tak lengkap. Perbaiki/jalankan Pengaturan."; return 1; fi
    fi
    if ! [[ "$CHECK_INTERVAL" =~ ^[1-9][0-9]*$ ]]; then error_msg "Interval ($CHECK_INTERVAL) tidak valid. Perbaiki di Pengaturan."; return 1; fi

    log_message "Memulai listener background... Interval: $CHECK_INTERVAL dtk."
    ( listener_loop ) >>"$LOG_FILE" 2>&1 &
    local pid=$!

    echo "$pid" > "$PID_FILE"
    if [ $? -ne 0 ]; then log_message "ERROR: Gagal simpan PID $pid ke $PID_FILE."; kill "$pid" 2>/dev/null; error_msg "Gagal simpan PID. Listener gagal."; LISTENER_PID=""; return 1; fi

    sleep 0.5
    if ! kill -0 "$pid" 2>/dev/null; then log_message "ERROR: Listener process $pid hilang setelah start. Cek $LOG_FILE."; error_msg "Listener gagal/berhenti. Cek log: $LOG_FILE"; rm -f "$PID_FILE"; LISTENER_PID=""; return 1; fi

    LISTENER_PID="$pid"
    log_message "Listener berhasil dimulai (PID: $LISTENER_PID)."
    info_msg "Listener mulai (PID: $LISTENER_PID).\nInterval: $CHECK_INTERVAL dtk.\nLog: $LOG_FILE (Max $MAX_LOG_LINES)."
    return 0
}

stop_listener() {
    if ! is_listener_running; then info_msg "Listener tidak sedang berjalan."; return 1; fi
    log_message "Mengirim TERM ke listener (PID: $LISTENER_PID)..."
    if kill -TERM "$LISTENER_PID" 2>/dev/null; then
        local count=0 max_wait=10
        while kill -0 "$LISTENER_PID" 2>/dev/null; do
            ((count++)); if [ "$count" -gt "$max_wait" ]; then log_message "WARNING: Listener $LISTENER_PID alot, kirim KILL."; kill -KILL "$LISTENER_PID" 2>/dev/null; sleep 0.5; break; fi; sleep 0.5
        done
        if ! kill -0 "$LISTENER_PID" 2>/dev/null; then log_message "Listener $LISTENER_PID berhasil dihentikan."; info_msg "Listener $LISTENER_PID berhasil dihentikan."
        else log_message "ERROR: Gagal hentikan listener $LISTENER_PID."; error_msg "Gagal hentikan listener $LISTENER_PID."; fi
    else
        log_message "WARNING: Gagal kirim TERM ke PID $LISTENER_PID (mungkin sudah berhenti?)."
        if ! kill -0 "$LISTENER_PID" 2>/dev/null; then info_msg "Listener $LISTENER_PID sepertinya sudah berhenti."
        else error_msg "Gagal kirim TERM ke listener $LISTENER_PID yg masih jalan."; return 1; fi
    fi
    rm -f "$PID_FILE"; LISTENER_PID=""; return 0
}

# Fungsi show_live_log (Tidak berubah)
show_live_log() {
    if ! is_listener_running; then clear; echo -e "==================\n ERROR: Listener Tidak Aktif\n==================\n\nListener tidak sedang berjalan.\n\nTekan Enter..."; read -r; log_message "Gagal lihat log: Listener off."; return 1; fi
    if [[ ! -f "$LOG_FILE" || ! -r "$LOG_FILE" ]]; then clear; echo -e "==================\n ERROR: Log Tidak Ada/Dibaca\n==================\n\nFile log ($LOG_FILE) tidak ada/dibaca.\n\nTekan Enter..."; read -r; log_message "Gagal lihat log: File $LOG_FILE error."; return 1; fi
    clear; echo -e "====================================================\n Menampilkan Log Real-time (PID: $LISTENER_PID)\n====================================================\n Log: $LOG_FILE (Max $MAX_LOG_LINES)\n Keluar: Ctrl+C\n----------------------------------------------------"
    if [[ -s "$LOG_FILE" ]]; then echo "[Menampilkan ${MAX_LOG_LINES} baris terakhir log...]"; tail -n "$MAX_LOG_LINES" "$LOG_FILE"; echo -e "----------------------------------------------------\n[Mengikuti log real-time...]" ; else echo "[Log kosong. Menunggu entri baru...]\n----------------------------------------------------"; fi
    tail -f "$LOG_FILE"; echo; echo -e "----------------------------------------------------\nBerhenti melihat log.\nTekan Enter untuk kembali ke menu..."; read -r
}

# Fungsi view_static_log (Tidak berubah)
view_static_log() {
    clear
    if [ -f "$LOG_FILE" ] && [ -s "$LOG_FILE" ]; then dialog --title "Log Statis ($LOG_FILE - Max $MAX_LOG_LINES)" --cr-wrap --textbox "$LOG_FILE" 25 90;
    else info_msg "File log ($LOG_FILE) belum ada atau kosong."; fi
    clear
}

# --- Fungsi Menu Utama ---
main_menu() {
    while true; do
        clear; is_listener_running
        local listener_status_msg="" menu_items=() menu_height list_height
        if [[ -n "$LISTENER_PID" ]]; then
            listener_status_msg=" (Aktif - PID: $LISTENER_PID - Int: ${CHECK_INTERVAL:-?}s)"
            menu_items+=("1" "Log Real-time" "2" "Hentikan Listener" "3" "Pengaturan (Nonaktif)" "4" "Log Statis" "5" "Keluar")
            menu_height=18; list_height=5
        else
            listener_status_msg=" (Tidak Aktif - Int: ${CHECK_INTERVAL:-$DEFAULT_CHECK_INTERVAL}s)"
            menu_items+=("1" "Mulai Listener" "2" "Pengaturan" "3" "Log Statis" "4" "Keluar")
            menu_height=17; list_height=4
        fi

        CHOICE=$(dialog --clear --stdout --title "Email Trader v1.9.1 - Menu$listener_status_msg" --cancel-label "Keluar" \
                        --menu "Pilih tindakan (Log: $LOG_FILE):" $menu_height 75 $list_height "${menu_items[@]}")
        local exit_status=$?; if [[ $exit_status -ne 0 ]]; then CHOICE="Keluar_Signal"; fi

        if [[ -n "$LISTENER_PID" ]]; then # === Listener Aktif ===
            case "$CHOICE" in
                1) show_live_log ;; 2) stop_listener ;; 3) error_msg "Hentikan Listener dulu." ;; 4) view_static_log ;;
                5|"Keluar_Signal") clear; echo "Menghentikan listener..."; stop_listener; echo "Script dihentikan."; log_message "--- Script Stop via Menu (Listener Aktif) ---"; exit 0 ;;
                *) error_msg "Pilihan tidak valid." ;;
            esac
        else # === Listener Tidak Aktif ===
             case "$CHOICE" in
                1) start_listener ;; 2) configure_settings; load_config ;; 3) view_static_log ;;
                4|"Keluar_Signal") clear; echo "Script dihentikan."; log_message "--- Script Stop (Listener tidak aktif) ---"; exit 0 ;;
                *) error_msg "Pilihan tidak valid." ;;
            esac
        fi
    done
}

# --- Main Program Execution ---

# Fungsi cleanup (Tidak berubah)
cleanup() {
    local exit_code=$?; echo; log_message "--- Script Terima Sinyal Exit ($exit_code) ---"
    local current_pid=""; if [ -f "$PID_FILE" ]; then current_pid=$(cat "$PID_FILE"); fi
    if [[ -n "$current_pid" ]] && kill -0 "$current_pid" 2>/dev/null; then
        echo " Membersihkan: Stop listener $current_pid..."; log_message "Cleanup: Kirim TERM ke listener $current_pid..."
        kill -TERM "$current_pid" &>/dev/null; sleep 0.2; if kill -0 "$current_pid" &>/dev/null; then log_message "Cleanup: KILL listener $current_pid."; kill -KILL "$current_pid" &>/dev/null; fi
        rm -f "$PID_FILE"; echo " Membersihkan: Listener stop."; log_message "Cleanup: Listener $current_pid stop saat script exit."
    elif [[ -f "$PID_FILE" ]]; then rm -f "$PID_FILE"; log_message "Cleanup: Hapus PID basi ($PID_FILE)."; fi
    echo " Script selesai."; stty sane; clear
    if [[ "$exit_code" == "0" || "$exit_code" == "130" ]]; then exit 0; else exit $exit_code; fi
}
trap cleanup INT TERM EXIT

# --- Inisialisasi ---
clear; echo "Memulai Email Trader v1.9.1 (Ignore Mutt Config)..."; log_message "--- Script Email Trader v1.9.1 Dimulai (PID: $SCRIPT_MAIN_PID) ---"
check_deps; log_message "Log: $LOG_FILE (Max $MAX_LOG_LINES)"

is_listener_running
if [[ -n "$LISTENER_PID" ]]; then log_message "INFO: Listener sesi lalu aktif (PID: $LISTENER_PID)."; info_msg "Listener sesi lalu aktif (PID: $LISTENER_PID).\nHentikan jika perlu."; sleep 2; fi

if ! load_config; then
    if ! is_listener_running; then
        if ! [[ -f "$CONFIG_FILE" ]]; then
            clear; dialog --title "Setup Awal" --yesno "Konfigurasi ($CONFIG_FILE) tidak ada.\n\nBuat sekarang?" 10 70
            response=$?; case $response in 0) if ! configure_settings || ! load_config; then clear; echo "Konfig gagal. Script stop."; log_message "FATAL: Konfig awal gagal."; exit 1; fi ;; *) clear; echo "Konfig dilewati. Script stop."; log_message "FATAL: Konfig awal dilewati."; exit 1 ;; esac
        else error_msg "Konfigurasi ($CONFIG_FILE) gagal load. Periksa file/jalankan Pengaturan."; sleep 3; fi
    else log_message "WARNING: Konfig gagal load, tapi listener $LISTENER_PID aktif."; error_msg "WARNING: Konfig gagal load ($CONFIG_FILE).\nListener mungkin pakai config lama.\nHentikan & perbaiki jika perlu."; sleep 3; fi
fi

main_menu
exit 0
