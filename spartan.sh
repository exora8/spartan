#!/bin/bash

# ==============================================================================
# Script Bash untuk Mendengarkan Email TradingView dan Eksekusi Order Binance
# PERINGATAN: GUNAKAN DENGAN RISIKO ANDA SENDIRI! UJI DI TESTNET DULU!
# Pastikan prasyarat (curl, openssl, jq) terinstall.
# ==============================================================================

### --- KONFIGURASI --- ###
# --- Email (IMAP) ---
IMAP_SERVER="imap.gmail.com" # Ganti dengan server IMAP provider email Anda
IMAP_PORT="993" # Port IMAP (biasanya 993 untuk SSL/TLS)
IMAP_USER="email_anda@gmail.com" # Alamat email Anda
IMAP_PASS="password_app_anda" # GUNAKAN APP PASSWORD, BUKAN PASSWORD UTAMA!
EMAIL_SENDER="noreply@tradingview.com" # Pastikan ini alamat email pengirim alert TradingView
EMAIL_SUBJECT_KEYWORD="Alert:" # Opsional: Kata kunci di subjek untuk filter tambahan

# --- Binance ---
# Ganti dengan URL API Testnet jika sedang menguji: https://testnet.binance.vision/api
BINANCE_API_URL="https://api.binance.com"
# !! SANGAT TIDAK AMAN MENYIMPAN KEY DI SINI !! Gunakan env variable atau cara lain!
# export BINANCE_API_KEY="your_api_key"
# export BINANCE_SECRET_KEY="your_secret_key"
API_KEY="${BINANCE_API_KEY}"
SECRET_KEY="${BINANCE_SECRET_KEY}"

# --- Trading ---
TRADING_SYMBOL="BTCUSDT" # Ganti dengan pair yang ingin di-trade
ORDER_QUANTITY="0.001" # Ganti dengan jumlah yang ingin di-trade (sesuaikan dengan minimum order size)
ORDER_TYPE="MARKET" # Tipe order (MARKET atau LIMIT) - MARKET lebih simpel untuk script ini

# --- Lain-lain ---
CHECK_INTERVAL_SECONDS=60 # Berapa detik sekali cek email baru
LOG_FILE="/var/log/tradingview_binance_bot.log" # File untuk logging
DEBUG=true # Set ke true untuk output lebih detail

### --- FUNGSI --- ###

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "${LOG_FILE}"
}

debug_message() {
    if [ "$DEBUG" = true ]; then
        log_message "DEBUG: $1"
    fi
}

# Fungsi untuk membuat signature HMAC-SHA256
create_signature() {
    local query_string="$1"
    echo -n "${query_string}" | openssl dgst -sha256 -hmac "${SECRET_KEY}" | sed 's/^.* //')
}

# Fungsi untuk mengirim order ke Binance
execute_binance_order() {
    local side="$1" # Harus "BUY" atau "SELL"
    local symbol="$2"
    local quantity="$3"
    local order_type="$4"

    if [ -z "$API_KEY" ] || [ -z "$SECRET_KEY" ]; then
        log_message "ERROR: API Key atau Secret Key Binance belum di-set."
        return 1
    fi

    local endpoint="/api/v3/order"
    local timestamp=$(($(date +%s%N)/1000000)) # Timestamp dalam milidetik
    local query_string="symbol=${symbol}&side=${side}&type=${order_type}&quantity=${quantity}×tamp=${timestamp}"
    local signature=$(create_signature "${query_string}")

    local full_url="${BINANCE_API_URL}${endpoint}"

    log_message "Mengirim order: SIDE=${side}, SYMBOL=${symbol}, QTY=${quantity}, TYPE=${order_type}"

    response=$(curl -s -H "X-MBX-APIKEY: ${API_KEY}" -X POST "${full_url}?${query_string}&signature=${signature}")

    debug_message "Binance Raw Response: ${response}"

    # Cek error dasar atau parse jika pakai jq
    if command -v jq > /dev/null; then
        order_id=$(echo "$response" | jq -r '.orderId // empty')
        error_code=$(echo "$response" | jq -r '.code // empty')
        error_msg=$(echo "$response" | jq -r '.msg // empty')

        if [ -n "$order_id" ]; then
            log_message "SUCCESS: Order berhasil dieksekusi. OrderID: ${order_id}"
            log_message "Detail: $(echo "$response" | jq -c .)" # Log detail JSON
            return 0
        elif [ -n "$error_code" ]; then
            log_message "ERROR: Gagal eksekusi order. Code: ${error_code}, Msg: ${error_msg}"
            return 1
        else
            log_message "WARNING: Respons Binance tidak dikenali: ${response}"
            return 1
        fi
    else
        # Fallback jika jq tidak ada (kurang ideal)
        if [[ "$response" == *"orderId"* ]]; then
             log_message "SUCCESS: Order sepertinya berhasil dieksekusi (jq tidak ditemukan untuk detail)."
             log_message "Raw Response: ${response}"
             return 0
        else
             log_message "ERROR: Gagal eksekusi order (jq tidak ditemukan untuk detail)."
             log_message "Raw Response: ${response}"
             return 1
        fi
    fi
}

# Fungsi untuk mengambil dan memproses email baru
check_and_process_emails() {
    log_message "Mengecek email baru..."

    # 1. Cari email UNSEEN dari sender yang ditentukan
    # Opsi Subject: SUBJECT \"${EMAIL_SUBJECT_KEYWORD}\"
    local search_command="SEARCH UNSEEN FROM \"${EMAIL_SENDER}\""
    debug_message "IMAP Command: ${search_command}"

    # Menggunakan curl untuk IMAP (pastikan curl dikompilasi dengan support IMAP/SSL)
    local email_ids=$(curl -s --url "imaps://${IMAP_SERVER}:${IMAP_PORT}/INBOX" --user "${IMAP_USER}:${IMAP_PASS}" -X "${search_command}")

    debug_message "IMAP Search Response: ${email_ids}"

    # Ekstrak ID email (angka setelah '* SEARCH ')
    local ids=$(echo "$email_ids" | grep '^* SEARCH' | sed 's/^* SEARCH //')

    if [ -z "$ids" ]; then
        log_message "Tidak ada email baru yang belum dibaca dari ${EMAIL_SENDER}."
        return
    fi

    log_message "Menemukan email baru dengan ID: ${ids}"

    # Proses setiap ID email
    for msg_id in $ids; do
        log_message "Memproses email ID: ${msg_id}..."

        # 2. Ambil konten email (Body)
        # Perhatian: Mengambil BODY[TEXT] mungkin lebih efisien, tapi perlu parsing lebih canggih
        # Untuk simpelnya, ambil seluruh message source dan grep
        local fetch_command="FETCH ${msg_id} BODY[]"
        debug_message "IMAP Fetch Command: ${fetch_command}"
        local email_content=$(curl -s --url "imaps://${IMAP_SERVER}:${IMAP_PORT}/INBOX" --user "${IMAP_USER}:${IMAP_PASS}" -X "${fetch_command}")

        # Simpan sementara konten email untuk debug jika perlu
        # echo "${email_content}" > "/tmp/email_${msg_id}.txt"
        # debug_message "Konten email mentah disimpan di /tmp/email_${msg_id}.txt"

        # 3. Parsing sinyal BUY/SELL (SANGAT SIMPLISTIK!)
        # Asumsi: Ada kata "BUY" atau "SELL" di body email dengan huruf besar.
        # Sesuaikan pola `grep` ini sesuai format email alert TradingView kamu!
        local signal="NONE"
        if echo "${email_content}" | grep -q -E '\bBUY\b'; then
            signal="BUY"
        elif echo "${email_content}" | grep -q -E '\bSELL\b'; then
            signal="SELL"
        fi

        # 4. Eksekusi order jika sinyal ditemukan
        if [ "$signal" != "NONE" ]; then
            log_message "Sinyal terdeteksi: ${signal} untuk ${TRADING_SYMBOL}"
            execute_binance_order "${signal}" "${TRADING_SYMBOL}" "${ORDER_QUANTITY}" "${ORDER_TYPE}"
            # Jika eksekusi berhasil atau gagal, kita tetap tandai email sudah diproses
            local mark_seen_command="STORE ${msg_id} +FLAGS (\Seen)"
            debug_message "IMAP Mark Seen Command: ${mark_seen_command}"
            curl -s --url "imaps://${IMAP_SERVER}:${IMAP_PORT}/INBOX" --user "${IMAP_USER}:${IMAP_PASS}" -X "${mark_seen_command}" > /dev/null
            log_message "Email ID ${msg_id} ditandai sebagai sudah dibaca."
        else
            log_message "Tidak ada sinyal BUY/SELL yang jelas terdeteksi di email ID ${msg_id}. Mungkin perlu penyesuaian parsing."
            # Pertimbangkan apakah email tanpa sinyal jelas harus ditandai SEEN atau tidak
             local mark_seen_command="STORE ${msg_id} +FLAGS (\Seen)"
             debug_message "IMAP Mark Seen Command: ${mark_seen_command}"
             curl -s --url "imaps://${IMAP_SERVER}:${IMAP_PORT}/INBOX" --user "${IMAP_USER}:${IMAP_PASS}" -X "${mark_seen_command}" > /dev/null
             log_message "Email ID ${msg_id} tanpa sinyal ditandai sebagai sudah dibaca."
        fi
         # Beri jeda sedikit antar pemrosesan email jika ada banyak
        sleep 2
    done
}

### --- MAIN LOOP --- ###

log_message "Memulai script listener email TradingView..."

if [ -z "$API_KEY" ] || [ -z "$SECRET_KEY" ]; then
    log_message "FATAL: Binance API Key atau Secret Key tidak ditemukan. Set environment variable BINANCE_API_KEY dan BINANCE_SECRET_KEY."
    exit 1
fi

# Cek konektivitas awal ke IMAP (opsional tapi bagus)
log_message "Mencoba koneksi awal ke IMAP ${IMAP_SERVER}..."
check_imap=$(curl -s --connect-timeout 10 --url "imaps://${IMAP_SERVER}:${IMAP_PORT}" --user "${IMAP_USER}:${IMAP_PASS}" -X "NOOP")
if [[ $check_imap != *"OK NOOP completed"* ]]; then
     log_message "FATAL: Gagal terhubung ke server IMAP atau login salah. Cek kredensial dan koneksi."
     debug_message "IMAP NOOP Response: ${check_imap}"
     exit 1
else
    log_message "Koneksi IMAP awal berhasil."
fi


while true; do
    check_and_process_emails
    log_message "Menunggu ${CHECK_INTERVAL_SECONDS} detik sebelum cek berikutnya..."
    sleep "${CHECK_INTERVAL_SECONDS}"
done

log_message "Script dihentikan." # Seharusnya tidak pernah sampai sini dalam mode normal

exit 0
