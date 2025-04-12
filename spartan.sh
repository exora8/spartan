#!/usr/bin/env bash

# Script Email Listener & Binance Trader
# Versi: 1.0
# Author: [Nama Kamu/AI]

# --- Konfigurasi Awal ---
CONFIG_FILE="$HOME/.email_trader_rc"
LOG_FILE="/tmp/email_trader.log"
touch "$LOG_FILE" # Pastikan file log ada
chmod 600 "$LOG_FILE" # Amankan log jika perlu

# Identifier Email yang Dicari (Subject atau Body)
EMAIL_IDENTIFIER="Exora AI (V5 SPOT + SR Filter) (1M)"

# --- Fungsi ---

# Fungsi untuk menampilkan pesan error dengan dialog
error_msg() {
    dialog --title "Error" --msgbox "$1" 8 50
}

# Fungsi untuk menampilkan info dengan dialog
info_msg() {
    dialog --title "Info" --msgbox "$1" 8 50
}

# Fungsi cek dependensi
check_deps() {
    local missing_deps=()
    for cmd in dialog neomutt curl openssl jq grep sed awk cut; do
        if ! command -v "$cmd" &> /dev/null; then
            missing_deps+=("$cmd")
        fi
    done

    if [ ${#missing_deps[@]} -ne 0 ]; then
        error_msg "Dependensi berikut tidak ditemukan: ${missing_deps[*]}. Silakan install terlebih dahulu."
        exit 1
    fi
    # Coba juga cek mutt jika neomutt tidak ada (opsional fallback)
    if ! command -v neomutt &> /dev/null && ! command -v mutt &> /dev/null; then
         error_msg "Dependensi 'neomutt' atau 'mutt' tidak ditemukan. Install salah satu."
         exit 1
    fi
    # Pilih email client yang tersedia
    EMAIL_CLIENT=$(command -v neomutt || command -v mutt)
}

# Fungsi load konfigurasi
load_config() {
    if [ -f "$CONFIG_FILE" ]; then
        chmod 600 "$CONFIG_FILE" # Pastikan permission benar
        source "$CONFIG_FILE"
        # Validasi variabel penting
        if [[ -z "$GMAIL_USER" || -z "$GMAIL_APP_PASS" || -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$TRADE_SYMBOL" || -z "$TRADE_QUANTITY" || -z "$CHECK_INTERVAL" ]]; then
            return 1 # Konfigurasi tidak lengkap
        fi
        return 0 # Sukses load
    else
        return 1 # File tidak ada
    fi
}

# Fungsi simpan konfigurasi
save_config() {
    # Hapus file lama jika ada, untuk menulis ulang
    rm -f "$CONFIG_FILE"
    # Tulis konfigurasi baru
    echo "# Konfigurasi Email Trader" > "$CONFIG_FILE"
    echo "GMAIL_USER='${GMAIL_USER}'" >> "$CONFIG_FILE"
    echo "GMAIL_APP_PASS='${GMAIL_APP_PASS}'" >> "$CONFIG_FILE"
    echo "BINANCE_API_KEY='${BINANCE_API_KEY}'" >> "$CONFIG_FILE"
    echo "BINANCE_SECRET_KEY='${BINANCE_SECRET_KEY}'" >> "$CONFIG_FILE"
    echo "TRADE_SYMBOL='${TRADE_SYMBOL}'" >> "$CONFIG_FILE"
    echo "TRADE_QUANTITY='${TRADE_QUANTITY}'" >> "$CONFIG_FILE"
    echo "CHECK_INTERVAL='${CHECK_INTERVAL}'" >> "$CONFIG_FILE"
    # Set permission ketat
    chmod 600 "$CONFIG_FILE"
    info_msg "Konfigurasi berhasil disimpan di $CONFIG_FILE"
}

# Fungsi konfigurasi interaktif
configure_settings() {
    local temp_file
    temp_file=$(mktemp) || { error_msg "Gagal membuat file temporary"; exit 1; }

    GMAIL_USER=$(dialog --stdout --title "Konfigurasi" --inputbox "Masukkan Alamat Gmail Anda:" 8 50 "$GMAIL_USER") || { rm "$temp_file"; exit 1; }
    GMAIL_APP_PASS=$(dialog --stdout --title "Konfigurasi" --passwordbox "Masukkan Gmail App Password Anda (Bukan Password Utama!):" 8 70 "$GMAIL_APP_PASS") || { rm "$temp_file"; exit 1; }
    BINANCE_API_KEY=$(dialog --stdout --title "Konfigurasi" --inputbox "Masukkan Binance API Key Anda:" 8 70 "$BINANCE_API_KEY") || { rm "$temp_file"; exit 1; }
    BINANCE_SECRET_KEY=$(dialog --stdout --title "Konfigurasi" --passwordbox "Masukkan Binance Secret Key Anda:" 8 70 "$BINANCE_SECRET_KEY") || { rm "$temp_file"; exit 1; }
    TRADE_SYMBOL=$(dialog --stdout --title "Konfigurasi" --inputbox "Masukkan Simbol Trading (contoh: BTCUSDT):" 8 50 "$TRADE_SYMBOL") || { rm "$temp_file"; exit 1; }
    TRADE_QUANTITY=$(dialog --stdout --title "Konfigurasi" --inputbox "Masukkan Jumlah Quantity Trading (contoh: 0.001):" 8 50 "$TRADE_QUANTITY") || { rm "$temp_file"; exit 1; }
    CHECK_INTERVAL=$(dialog --stdout --title "Konfigurasi" --inputbox "Masukkan Interval Cek Email (detik, contoh: 60):" 8 50 "${CHECK_INTERVAL:-60}") || { rm "$temp_file"; exit 1; }

    # Validasi input dasar (bisa ditambahkan)
    if [[ -z "$GMAIL_USER" || -z "$GMAIL_APP_PASS" || -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$TRADE_SYMBOL" || -z "$TRADE_QUANTITY" || -z "$CHECK_INTERVAL" ]]; then
         error_msg "Semua field konfigurasi harus diisi."
         rm "$temp_file"
         return 1 # Gagal konfigurasi
    fi

    # Simpan konfigurasi
    save_config
    rm "$temp_file"
    return 0 # Sukses
}

# Fungsi untuk logging ke file dan console (jika perlu)
log_message() {
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] $1" >> "$LOG_FILE"
    # Jika ingin echo juga ke terminal utama (di luar dialog)
    # echo "[$timestamp] $1" >&2
}

# Fungsi cek email baru yang cocok
check_email() {
    log_message "Mencari email baru dari $GMAIL_USER..."
    local email_body_file
    email_body_file=$(mktemp) || { log_message "ERROR: Gagal membuat file temporary untuk email."; return 1; }

    # Perintah neomutt/mutt untuk mencari email UNREAD (~N) dengan Subject/Body tertentu
    # Perintah ini akan mencoba pipe body email PERTAMA yang cocok ke file temp
    # Gunakan -e 'set ssl_starttls=yes ssl_force_tls=yes' untuk keamanan
    # Gunakan 'set imap_check_subscribed=yes' jika hanya ingin cek folder subscribed
    "$EMAIL_CLIENT" \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no' \
        -e 'push "<limit>~N ~b \"'${EMAIL_IDENTIFIER}'\"\n<pipe-message>cat > '${email_body_file}'\n<exit>"' > /dev/null 2>&1

    # Cek apakah file body email berisi sesuatu (berarti ada email yang cocok)
    if [ -s "$email_body_file" ]; then
        log_message "Email yang cocok ditemukan. Memproses..."
        # Parsing email body
        parse_email_body "$email_body_file"
        local parse_status=$?
        # Hapus file temporary
        rm "$email_body_file"
        # Tandai email sebagai sudah dibaca setelah diproses (jika parsing berhasil)
        if [ $parse_status -eq 0 ]; then
             mark_email_as_read
        fi
        return 0 # Email ditemukan dan diproses (atau gagal parse)
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

    # Cari baris yang mengandung identifier, lalu cari 'order buy' atau 'order sell' setelahnya
    # Menggunakan grep -oP untuk ekstrak 'buy' atau 'sell' saja (case-insensitive)
    local action
    # Mencari pattern "order<spasi>buy" atau "order<spasi>sell" setelah identifier ada di file
    # Opsi -i untuk case-insensitive
    # Opsi -o untuk hanya print bagian yang match
    # Opsi -P untuk Perl-compatible regex (butuh \K untuk 'keep left part out')
    # head -n 1 untuk ambil match pertama jika ada banyak
    action=$(grep -i "$EMAIL_IDENTIFIER" "$body_file" | grep -ioP 'order\s+\K(buy|sell)' | head -n 1)

    if [[ "$action" == "buy" || "$action" == "BUY" ]]; then
        log_message "Action terdeteksi: BUY"
        execute_binance_order "BUY"
        return 0
    elif [[ "$action" == "sell" || "$action" == "SELL" ]]; then
        log_message "Action terdeteksi: SELL"
        execute_binance_order "SELL"
        return 0
    else
        log_message "WARNING: Identifier ditemukan, tapi tidak ada action 'order buy' atau 'order sell' yang valid."
        # Jika tidak ada action valid, email tidak ditandai sudah dibaca oleh check_email
        return 1 # Gagal parsing / action tidak ditemukan
    fi
}

# Fungsi untuk menandai email sebagai sudah dibaca
mark_email_as_read() {
    log_message "Menandai email sebagai sudah dibaca..."
    # Cari email UNREAD dengan identifier, tag, lalu hapus flag Unread (\Seen flag implicitly added)
    "$EMAIL_CLIENT" \
        -f "imaps://${GMAIL_USER}:${GMAIL_APP_PASS}@imap.gmail.com/INBOX" \
        -e 'set mail_check_stats=no wait_key=no' \
        -e 'push "<limit>~N ~b \"'${EMAIL_IDENTIFIER}'\"\n<tag-message><clear-flag>N\n<sync-mailbox><exit>"' > /dev/null 2>&1
    log_message "Email seharusnya sudah ditandai dibaca."
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
    local api_endpoint="https://api.binance.com" # Ganti ke api testnet jika perlu (https://testnet.binance.vision)
    local order_path="/api/v3/order"

    # Parameter order (MARKET order)
    local params="symbol=${TRADE_SYMBOL}&side=${side}&type=MARKET&quantity=${TRADE_QUANTITY}×tamp=${timestamp}"

    # Generate signature
    local signature
    signature=$(generate_binance_signature "$params" "$BINANCE_SECRET_KEY")

    local full_url="${api_endpoint}${order_path}?${params}&signature=${signature}"

    log_message "Mengirim order ke Binance: SIDE=$side SYMBOL=$TRADE_SYMBOL QTY=$TRADE_QUANTITY"

    # Eksekusi CURL
    local response
    response=$(curl -s -H "X-MBX-APIKEY: ${BINANCE_API_KEY}" -X POST "$full_url")

    # Log response dari Binance (bisa diparsing lebih lanjut dengan jq)
    log_message "Response Binance: $response"

    # Cek response sederhana (bisa lebih canggih dengan jq)
    if echo "$response" | grep -q '"orderId"'; then
        log_message "SUCCESS: Order berhasil ditempatkan."
        # Optional: Parse orderId dengan jq
        local orderId
        orderId=$(echo "$response" | jq -r '.orderId // empty')
        if [ -n "$orderId" ]; then
             log_message "Binance Order ID: $orderId"
        fi
        # Optional: Tambahkan notifikasi lain di sini jika perlu
    elif echo "$response" | grep -q '"code"'; then
        log_message "ERROR: Gagal menempatkan order. Kode Error: $(echo "$response" | jq -r '.code // "?"') Pesan: $(echo "$response" | jq -r '.msg // "Tidak diketahui"')"
        # Optional: Kirim notifikasi error
    else
        log_message "WARNING: Response dari Binance tidak dikenal atau request gagal."
    fi
}

# --- Main Program ---

# 0. Cek dependensi
check_deps

# 1. Load konfigurasi atau jalankan setup jika tidak ada/tidak lengkap
if ! load_config; then
    dialog --title "Setup Awal" --msgbox "File konfigurasi ($CONFIG_FILE) tidak ditemukan atau tidak lengkap. Mari lakukan konfigurasi awal." 10 60
    if ! configure_settings; then
        error_msg "Konfigurasi dibatalkan atau gagal. Script berhenti."
        exit 1
    fi
    # Coba load lagi setelah konfigurasi
    if ! load_config; then
        error_msg "Gagal memuat konfigurasi setelah setup. Script berhenti."
        exit 1
    fi
fi

# 2. Tampilkan UI Utama dan mulai loop
(
    # Loop utama untuk cek email dan update log
    while true; do
        log_message "Memulai siklus pengecekan..."
        check_email
        log_message "Siklus selesai. Menunggu ${CHECK_INTERVAL} detik..."
        sleep "$CHECK_INTERVAL"
        # Tambahkan baris kosong untuk pemisah di log
        echo "" >> "$LOG_FILE"
        # Batasi ukuran file log (opsional, hapus jika tidak perlu)
        if [ "$(wc -l < "$LOG_FILE")" -gt 500 ]; then
             echo "$(tail -n 300 "$LOG_FILE")" > "$LOG_FILE"
             log_message "INFO: File log dipangkas."
        fi
    done
) & # Jalankan loop di background process

# Tampilkan log menggunakan dialog --tailboxbg
# Ini akan terus berjalan menampilkan update dari LOG_FILE
dialog --title "Email Listener & Binance Trader - Log" \
       --no-kill \
       --tailboxbg "$LOG_FILE" 25 80

# Cleanup saat dialog ditutup (misal user tekan Ctrl+C)
# Matikan background process loop
kill $! 2>/dev/null
wait $! 2>/dev/null # Tunggu proses background selesai (opsional)
clear
echo "Script dihentikan."
# rm "$LOG_FILE" # Hapus file log jika sudah tidak diperlukan

exit 0
