#!/usr/bin/env bash

# Script Email Listener & Binance Trader
# Versi: 1.1 (dengan Startup Menu)
# Author: [Nama Kamu/AI] & Kontributor

# --- Konfigurasi Awal ---
CONFIG_FILE="$HOME/.email_trader_rc"
LOG_FILE="/tmp/email_trader.log"
touch "$LOG_FILE" # Pastikan file log ada
chmod 600 "$LOG_FILE" # Amankan log jika perlu

# Identifier Email yang Dicari (Subject atau Body)
# Sesuaikan ini dengan subjek atau bagian body email yang unik dari sinyal trading
EMAIL_IDENTIFIER="Exora AI (V5 SPOT + SR Filter) (1M)" # Contoh, ganti sesuai kebutuhan

# --- Fungsi ---

# Fungsi untuk menampilkan pesan error dengan dialog
error_msg() {
    dialog --title "Error" --msgbox "$1" 8 60
    log_message "ERROR: $1" # Catat error ke log juga
}

# Fungsi untuk menampilkan info dengan dialog
info_msg() {
    dialog --title "Info" --msgbox "$1" 8 60
}

# Fungsi cek dependensi
check_deps() {
    local missing_deps=()
    # Tambahkan semua command yang dibutuhkan script
    for cmd in dialog neomutt curl openssl jq grep sed awk cut date mktemp tail wc kill sleep wait; do
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
            dialog --title "Error Dependensi" --msgbox "Dependensi berikut tidak ditemukan:\n\n$(printf -- '- %s\n' "${missing_deps[@]}")\n\nSilakan install terlebih dahulu." 15 70
        fi
        exit 1
    fi
    # Pilih email client yang tersedia
    EMAIL_CLIENT=$(command -v neomutt || command -v mutt)
    log_message "Dependensi terpenuhi. Menggunakan email client: $EMAIL_CLIENT"
}

# Fungsi load konfigurasi
load_config() {
    if [ -f "$CONFIG_FILE" ]; then
        chmod 600 "$CONFIG_FILE" # Pastikan permission benar
        # Source dalam subshell untuk isolasi, cek variabel setelahnya
        ( source "$CONFIG_FILE" )
        # Cek variabel penting langsung dari file dengan grep/sed untuk menghindari polusi variabel global jika source gagal
        GMAIL_USER=$(grep -Po "^GMAIL_USER *= *['\"]\K[^'\"]*" "$CONFIG_FILE")
        GMAIL_APP_PASS=$(grep -Po "^GMAIL_APP_PASS *= *['\"]\K[^'\"]*" "$CONFIG_FILE")
        BINANCE_API_KEY=$(grep -Po "^BINANCE_API_KEY *= *['\"]\K[^'\"]*" "$CONFIG_FILE")
        BINANCE_SECRET_KEY=$(grep -Po "^BINANCE_SECRET_KEY *= *['\"]\K[^'\"]*" "$CONFIG_FILE")
        TRADE_SYMBOL=$(grep -Po "^TRADE_SYMBOL *= *['\"]\K[^'\"]*" "$CONFIG_FILE")
        TRADE_QUANTITY=$(grep -Po "^TRADE_QUANTITY *= *['\"]\K[^'\"]*" "$CONFIG_FILE")
        CHECK_INTERVAL=$(grep -Po "^CHECK_INTERVAL *= *['\"]\K[^'\"]*" "$CONFIG_FILE")

        # Validasi variabel penting
        if [[ -z "$GMAIL_USER" || -z "$GMAIL_APP_PASS" || -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$TRADE_SYMBOL" || -z "$TRADE_QUANTITY" || -z "$CHECK_INTERVAL" ]]; then
            log_message "WARNING: File konfigurasi $CONFIG_FILE ada tapi tidak lengkap."
            return 1 # Konfigurasi tidak lengkap
        fi
        log_message "Konfigurasi berhasil dimuat dari $CONFIG_FILE."
        # Pastikan variabel interval di set (default jika tidak ada di file tapi file ada)
        CHECK_INTERVAL="${CHECK_INTERVAL:-60}"
        return 0 # Sukses load
    else
        log_message "INFO: File konfigurasi $CONFIG_FILE tidak ditemukan."
        return 1 # File tidak ada
    fi
}

# Fungsi simpan konfigurasi
save_config() {
    # Hapus file lama jika ada, untuk menulis ulang
    rm -f "$CONFIG_FILE"
    # Tulis konfigurasi baru (pastikan kutip variabel untuk keamanan)
    echo "# Konfigurasi Email Trader (v1.1)" > "$CONFIG_FILE"
    echo "GMAIL_USER='${GMAIL_USER}'" >> "$CONFIG_FILE"
    echo "GMAIL_APP_PASS='${GMAIL_APP_PASS}'" >> "$CONFIG_FILE"
    echo "BINANCE_API_KEY='${BINANCE_API_KEY}'" >> "$CONFIG_FILE"
    echo "BINANCE_SECRET_KEY='${BINANCE_SECRET_KEY}'" >> "$CONFIG_FILE"
    echo "TRADE_SYMBOL='${TRADE_SYMBOL}'" >> "$CONFIG_FILE"
    echo "TRADE_QUANTITY='${TRADE_QUANTITY}'" >> "$CONFIG_FILE"
    echo "CHECK_INTERVAL='${CHECK_INTERVAL}'" >> "$CONFIG_FILE"
    # Set permission ketat
    chmod 600 "$CONFIG_FILE"
    log_message "Konfigurasi berhasil disimpan di $CONFIG_FILE"
    info_msg "Konfigurasi berhasil disimpan di $CONFIG_FILE"
}

# Fungsi konfigurasi interaktif
configure_settings() {
    # Load nilai saat ini jika ada untuk ditampilkan di input box
    load_config # Tidak masalah jika gagal, variabel akan kosong

    local temp_gmail_user="${GMAIL_USER}"
    local temp_gmail_pass="${GMAIL_APP_PASS}"
    local temp_api_key="${BINANCE_API_KEY}"
    local temp_secret_key="${BINANCE_SECRET_KEY}"
    local temp_symbol="${TRADE_SYMBOL}"
    local temp_quantity="${TRADE_QUANTITY}"
    local temp_interval="${CHECK_INTERVAL:-60}" # Default 60 jika kosong

    # Gunakan --passwordbox untuk password/secret key agar tidak terlihat
    # Simpan output dialog ke variabel sementara
    local input_gmail_user input_gmail_pass input_api_key input_secret_key input_symbol input_quantity input_interval exit_status

    input_gmail_user=$(dialog --stdout --title "Konfigurasi" --inputbox "Alamat Gmail Anda:" 8 60 "$temp_gmail_user")
    exit_status=$?
    [[ $exit_status -ne 0 ]] && { info_msg "Konfigurasi dibatalkan."; return 1; }

    input_gmail_pass=$(dialog --stdout --title "Konfigurasi" --passwordbox "Gmail App Password Anda (Bukan Password Utama!):" 8 70 "$temp_gmail_pass")
    exit_status=$?
    [[ $exit_status -ne 0 ]] && { info_msg "Konfigurasi dibatalkan."; return 1; }

    input_api_key=$(dialog --stdout --title "Konfigurasi" --inputbox "Binance API Key Anda:" 8 70 "$temp_api_key")
    exit_status=$?
    [[ $exit_status -ne 0 ]] && { info_msg "Konfigurasi dibatalkan."; return 1; }

    input_secret_key=$(dialog --stdout --title "Konfigurasi" --passwordbox "Binance Secret Key Anda:" 8 70 "$temp_secret_key")
    exit_status=$?
    [[ $exit_status -ne 0 ]] && { info_msg "Konfigurasi dibatalkan."; return 1; }

    input_symbol=$(dialog --stdout --title "Konfigurasi" --inputbox "Simbol Trading (contoh: BTCUSDT):" 8 60 "$temp_symbol")
    exit_status=$?
    [[ $exit_status -ne 0 ]] && { info_msg "Konfigurasi dibatalkan."; return 1; }

    input_quantity=$(dialog --stdout --title "Konfigurasi" --inputbox "Jumlah Quantity Trading (contoh: 0.001):" 8 60 "$temp_quantity")
    exit_status=$?
    [[ $exit_status -ne 0 ]] && { info_msg "Konfigurasi dibatalkan."; return 1; }

    input_interval=$(dialog --stdout --title "Konfigurasi" --inputbox "Interval Cek Email (detik, contoh: 60):" 8 60 "$temp_interval")
    exit_status=$?
    [[ $exit_status -ne 0 ]] && { info_msg "Konfigurasi dibatalkan."; return 1; }

    # Validasi input dasar (tidak boleh kosong)
    if [[ -z "$input_gmail_user" || -z "$input_gmail_pass" || -z "$input_api_key" || -z "$input_secret_key" || -z "$input_symbol" || -z "$input_quantity" || -z "$input_interval" ]]; then
         error_msg "Semua field konfigurasi harus diisi."
         return 1 # Gagal konfigurasi
    fi

    # Validasi interval harus angka positif
     if ! [[ "$input_interval" =~ ^[1-9][0-9]*$ ]]; then
        error_msg "Interval cek email harus berupa angka positif (detik)."
        return 1
     fi

    # Validasi quantity harus angka (bisa desimal)
     if ! [[ "$input_quantity" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
        error_msg "Quantity trading harus berupa angka (misal: 0.001 atau 10)."
        return 1
     fi

    # Jika semua valid, update variabel global
    GMAIL_USER="$input_gmail_user"
    GMAIL_APP_PASS="$input_gmail_pass"
    BINANCE_API_KEY="$input_api_key"
    BINANCE_SECRET_KEY="$input_secret_key"
    TRADE_SYMBOL=$(echo "$input_symbol" | tr 'a-z' 'A-Z') # Pastikan uppercase
    TRADE_QUANTITY="$input_quantity"
    CHECK_INTERVAL="$input_interval"

    # Simpan konfigurasi ke file
    save_config
    return 0 # Sukses
}

# Fungsi untuk logging ke file
log_message() {
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    # Pastikan LOG_FILE sudah didefinisikan
    echo "[$timestamp] $1" >> "${LOG_FILE:-/tmp/email_trader_fallback.log}"
}

# Fungsi cek email baru yang cocok
check_email() {
    log_message "Mencari email baru dari $GMAIL_USER dengan identifier: '$EMAIL_IDENTIFIER'"
    local email_body_file
    email_body_file=$(mktemp) || { log_message "ERROR: Gagal membuat file temporary untuk email."; return 1; }

    # Perintah neomutt/mutt untuk mencari email UNREAD (~N) dengan Subject/Body tertentu
    # Menggunakan '-Q' untuk query tanpa masuk ke interface interaktif (jika didukung neomutt)
    # Mencari pesan tidak terbaca (~N) DAN mengandung identifier di body (~b) ATAU subject (~s)
    # Pipe message pertama yang cocok ke file temp
    "$EMAIL_CLIENT" \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no smtp_url="" sendmail=""' \
        -e 'push "<limit>~N (~b \"'${EMAIL_IDENTIFIER}'\" | ~s \"'${EMAIL_IDENTIFIER}'\")\n<pipe-message>cat > '${email_body_file}'\n<exit>"' > /dev/null 2>&1
    # Exit code mutt/neomutt tidak selalu bisa diandalkan untuk 'email ditemukan'

    # Cek apakah file body email berisi sesuatu (berarti ada email yang cocok)
    if [ -s "$email_body_file" ]; then
        log_message "Email yang cocok ditemukan. Memproses..."
        # Parsing email body
        parse_email_body "$email_body_file"
        local parse_status=$?
        # Hapus file temporary
        rm "$email_body_file"
        # Tandai email sebagai sudah dibaca HANYA jika parsing berhasil menemukan action
        if [ $parse_status -eq 0 ]; then
             mark_email_as_read
        else
             log_message "Action tidak ditemukan atau gagal parse, email tidak ditandai dibaca."
        fi
        return 0 # Email ditemukan (terlepas dari hasil parse)
    else
        log_message "Tidak ada email baru yang cocok ditemukan."
        rm "$email_body_file"
        return 1 # Tidak ada email yang cocok
    fi
}

# Fungsi parsing body email untuk action buy/sell
parse_email_body() {
    local body_file="$1"
    log_message "Parsing isi email dari $body_file"

    # Ekstrak action 'buy' atau 'sell' dari email. Lebih fleksibel: cari kata kunci action.
    # Contoh: cari baris yang mengandung 'Order Type:' lalu ambil kata setelahnya (BUY/SELL)
    # ATAU cari langsung 'ACTION: BUY' atau 'ACTION: SELL' (sesuaikan dengan format email Anda)

    # Contoh implementasi: Mencari kata "BUY" atau "SELL" setelah identifier ada di file
    # (Ini contoh sederhana, sesuaikan dengan format email sinyal Anda!)
    local action=""
    if grep -qi "buy" "$body_file"; then
        action="BUY"
    elif grep -qi "sell" "$body_file"; then
        action="SELL"
    fi

    # Filter tambahan: Pastikan identifier juga ada di body (double check)
    # Ini opsional tapi bisa mencegah salah deteksi jika kata 'buy'/'sell' muncul di email lain
    if ! grep -q "$EMAIL_IDENTIFIER" "$body_file"; then
        log_message "WARNING: Action '$action' terdeteksi, tapi identifier '$EMAIL_IDENTIFIER' tidak ditemukan di body email ini. Mengabaikan."
        return 1 # Identifier tidak cocok, abaikan
    fi


    if [[ "$action" == "BUY" ]]; then
        log_message "Action terdeteksi: BUY"
        execute_binance_order "BUY"
        return 0 # Sukses parse dan eksekusi (atau attempt eksekusi)
    elif [[ "$action" == "SELL" ]]; then
        log_message "Action terdeteksi: SELL"
        execute_binance_order "SELL"
        return 0 # Sukses parse dan eksekusi (atau attempt eksekusi)
    else
        log_message "WARNING: Tidak ada action 'BUY' atau 'SELL' yang valid terdeteksi dalam email yang cocok."
        return 1 # Gagal parsing / action tidak ditemukan
    fi
}

# Fungsi untuk menandai email sebagai sudah dibaca
mark_email_as_read() {
    log_message "Menandai email sebagai sudah dibaca..."
    # Cari email UNREAD dengan identifier, hapus flag Unread (\Seen flag implicitly added by IMAP server usually)
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


# Fungsi generate signature Binance
generate_binance_signature() {
    local query_string="$1"
    local secret="$2"
    echo -n "$query_string" | openssl dgst -sha256 -hmac "$secret" | sed 's/^.* //'
}

# Fungsi eksekusi order Binance
execute_binance_order() {
    local side="$1" # Harus "BUY" atau "SELL"
    local timestamp
    timestamp=$(date +%s%3N) # Timestamp dalam milliseconds
    # Pastikan variabel dari config sudah ada
    if [[ -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$TRADE_SYMBOL" || -z "$TRADE_QUANTITY" ]]; then
        log_message "ERROR: Konfigurasi Binance tidak lengkap. Tidak bisa membuat order."
        error_msg "Konfigurasi Binance tidak lengkap untuk membuat order."
        return 1
    fi

    local api_endpoint="https://api.binance.com" # Ganti ke api testnet jika perlu (https://testnet.binance.vision)
    local order_path="/api/v3/order"

    # Parameter order (MARKET order)
    # Pastikan nama parameter sesuai dokumentasi Binance API v3
    # recvWindow opsional, bisa ditambahkan jika ada masalah timestamp
    local params="symbol=${TRADE_SYMBOL}&side=${side}&type=MARKET&quantity=${TRADE_QUANTITY}×tamp=${timestamp}"
    # Jika menggunakan quoteOrderQty (misal beli 10 USDT senilai BTC):
    # local params="symbol=${TRADE_SYMBOL}&side=${side}&type=MARKET"eOrderQty=${QUOTE_QUANTITY}×tamp=${timestamp}"

    # Generate signature
    local signature
    signature=$(generate_binance_signature "$params" "$BINANCE_SECRET_KEY")

    local full_url="${api_endpoint}${order_path}?${params}&signature=${signature}"

    log_message "Mengirim order ke Binance: SIDE=$side SYMBOL=$TRADE_SYMBOL QTY=$TRADE_QUANTITY"

    # Eksekusi CURL
    local response curl_exit_code
    response=$(curl -s -w "%{http_code}" -H "X-MBX-APIKEY: ${BINANCE_API_KEY}" -X POST "$full_url")
    curl_exit_code=$?
    local http_code="${response: -3}" # Ambil 3 karakter terakhir (kode http)
    local body="${response:0:${#response}-3}" # Ambil sisanya (body response)

    if [ $curl_exit_code -ne 0 ]; then
        log_message "ERROR: curl gagal menghubungi Binance (Exit code: $curl_exit_code)."
        error_msg "Gagal menghubungi Binance. Cek koneksi internet atau endpoint API."
        return 1
    fi

    log_message "Response Binance (HTTP $http_code): $body"

    # Cek response berdasarkan HTTP Code dan isi body (JSON)
    if [[ "$http_code" =~ ^2 ]]; then # Kode 2xx berarti sukses
        # Coba parse dengan jq untuk info lebih detail
        local orderId clientOrderId status
        orderId=$(echo "$body" | jq -r '.orderId // empty')
        clientOrderId=$(echo "$body" | jq -r '.clientOrderId // empty')
        status=$(echo "$body" | jq -r '.status // "UNKNOWN"')

        if [ -n "$orderId" ]; then
            log_message "SUCCESS: Order berhasil ditempatkan. Order ID: $orderId, Status: $status"
            # Bisa tambahkan notifikasi sukses di sini jika mau
            # info_msg "Order $side $TRADE_QUANTITY $TRADE_SYMBOL berhasil (ID: $orderId)"
        else
            log_message "WARNING: HTTP 2xx diterima tapi tidak ada Order ID di response. Body: $body"
        fi
        return 0
    else # Gagal (HTTP non-2xx)
        local err_code err_msg
        err_code=$(echo "$body" | jq -r '.code // "?"')
        err_msg=$(echo "$body" | jq -r '.msg // "Tidak ada pesan error spesifik"')
        log_message "ERROR: Gagal menempatkan order. Kode Error Binance: $err_code Pesan: $err_msg"
        error_msg "Gagal Order Binance!\nKode: $err_code\nPesan: $err_msg"
        return 1
    fi
}

# --- Fungsi untuk Loop Utama Listener ---
run_listener() {
    log_message "Memulai mode listening..."
    # Pastikan interval valid sebelum loop
    if ! [[ "$CHECK_INTERVAL" =~ ^[1-9][0-9]*$ ]]; then
        error_msg "Interval cek email tidak valid ($CHECK_INTERVAL). Menggunakan default 60 detik."
        CHECK_INTERVAL=60
    fi

    # Jalankan loop utama di background process
    (
        trap 'echo "[$(date "+%Y-%m-%d %H:%M:%S")] INFO: Listener loop dihentikan."; exit 0' SIGTERM SIGINT
        while true; do
            log_message "Memulai siklus pengecekan email..."
            check_email
            log_message "Siklus selesai. Menunggu ${CHECK_INTERVAL} detik..."
            sleep "$CHECK_INTERVAL"

            # Batasi ukuran file log (misal, 1000 baris terakhir)
            local max_log_lines=1000
            local current_lines
            current_lines=$(wc -l < "$LOG_FILE")
            if [ "$current_lines" -gt "$max_log_lines" ]; then
                 log_message "INFO: File log dipangkas ke $max_log_lines baris terakhir."
                 tail -n "$max_log_lines" "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
            fi
        done
    ) &
    LISTENER_PID=$!
    log_message "Listener berjalan di background (PID: $LISTENER_PID)."

    # Tampilkan log menggunakan dialog --tailboxbg
    # Ini akan terus berjalan menampilkan update dari LOG_FILE
    # --no-kill mencegah dialog membunuh proses background jika dialog ditutup
    dialog --title "Email Listener & Binance Trader - Log Aktivitas" \
           --no-kill \
           --tailboxbg "$LOG_FILE" 25 90

    # Setelah dialog ditutup (misal user tekan Ctrl+C atau tombol 'Exit' jika ada)
    log_message "Menutup tampilan log. Menghentikan listener background (PID: $LISTENER_PID)..."
    # Kirim sinyal TERM ke proses background agar trap dieksekusi
    kill -TERM "$LISTENER_PID" 2>/dev/null
    # Tunggu sebentar agar proses bisa cleanup
    wait "$LISTENER_PID" 2>/dev/null
    log_message "Listener background seharusnya sudah berhenti."
    clear
    echo "Listener dihentikan."
}

# --- Fungsi Tampilkan Log ---
view_log() {
    if [ -f "$LOG_FILE" ]; then
        dialog --title "Log Aktivitas ($LOG_FILE)" --textbox "$LOG_FILE" 25 90
    else
        info_msg "File log ($LOG_FILE) belum ada atau kosong."
    fi
}

# --- Fungsi Menu Utama ---
main_menu() {
    while true; do
        CHOICE=$(dialog --clear --stdout \
                        --title "Email Trader - Menu Utama" \
                        --cancel-label "Keluar" \
                        --menu "Pilih tindakan:" 15 60 4 \
                        1 "Mulai Listening Email" \
                        2 "Pengaturan" \
                        3 "Lihat Log Aktivitas" \
                        4 "Keluar dari Script")

        exit_status=$?

        # Cek jika user menekan 'Keluar' atau Esc
        if [ $exit_status -ne 0 ]; then
            clear
            echo "Script dihentikan oleh pengguna."
            exit 0
        fi

        case "$CHOICE" in
            1)
                # Sebelum mulai, pastikan konfigurasi ada dan valid
                if load_config; then
                    run_listener # Jalankan fungsi listener
                    # Setelah listener selesai/dihentikan, loop menu akan lanjut
                    # Atau kita bisa keluar saja setelah listener selesai
                    # Jika ingin keluar setelah listener stop, uncomment baris berikut:
                    # clear
                    # echo "Listener selesai. Script berhenti."
                    # exit 0
                else
                    error_msg "Konfigurasi belum lengkap atau tidak valid. Silakan masuk ke 'Pengaturan' terlebih dahulu."
                fi
                ;;
            2)
                configure_settings
                # Setelah konfigurasi, kembali ke menu
                ;;
            3)
                view_log
                # Setelah lihat log, kembali ke menu
                ;;
            4)
                clear
                echo "Script dihentikan."
                exit 0
                ;;
            *)
                # Seharusnya tidak terjadi dengan --stdout, tapi sebagai fallback
                error_msg "Pilihan tidak valid."
                ;;
        esac
    done
}

# --- Main Program Execution ---

# 0. Cek dependensi paling awal
check_deps

# 1. Load konfigurasi awal atau paksa setup jika belum ada
if ! load_config; then
    dialog --title "Setup Awal Diperlukan" \
           --msgbox "File konfigurasi ($CONFIG_FILE) tidak ditemukan atau tidak lengkap.\n\nAnda akan diarahkan ke menu konfigurasi." 10 70
    if ! configure_settings; then
        clear
        echo "Konfigurasi awal dibatalkan atau gagal. Script tidak dapat dilanjutkan."
        exit 1
    fi
    # Coba load lagi setelah konfigurasi
    if ! load_config; then
        clear
        echo "Gagal memuat konfigurasi setelah setup awal. Script berhenti."
        exit 1
    fi
fi

# 2. Tampilkan Menu Utama
main_menu

# Seharusnya tidak pernah sampai sini jika main_menu loop benar
exit 0
