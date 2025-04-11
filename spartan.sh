#!/bin/bash

# --- Konfigurasi (Sama seperti di atas) ---
# Ambil API Keys dari environment variable
API_KEY="${BINANCE_API_KEY}"
SECRET_KEY="${BINANCE_SECRET_KEY}"
BINANCE_API_URL="https://api.binance.com" # Atau testnet

DEFAULT_QUANTITY_USDT=11
LOG_FILE="/path/to/your/trading_bot_polling.log"
TRADINGVIEW_SENDER="tradingview.com" # Atau alamat email lengkap jika lebih spesifik

# Konfigurasi Email (untuk Mutt)
EMAIL_USER="your_email@example.com"
EMAIL_PASSWORD="YOUR_EMAIL_APP_PASSWORD" # Gunakan App Password!
IMAP_SERVER="imaps://imap.your_email_provider.com/" # Format imaps://...
EMAIL_FOLDER="INBOX" # Folder yang dicek
CHECK_INTERVAL=60 # Detik (misal 1 menit)

# --- Fungsi Logging (Sama seperti di atas) ---
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

# --- Fungsi Eksekusi Order Binance (Sama seperti di atas) ---
execute_binance_order() {
    # ... (Salin fungsi execute_binance_order dari pendekatan 1 ke sini) ...
    local side=$1
    local symbol=$2
    local quantity=$DEFAULT_QUANTITY_USDT # Menggunakan Quote Order Quantity

    if [[ -z "$API_KEY" || -z "$SECRET_KEY" ]]; then log_message "ERROR: API Key/Secret kosong."; return 1; fi
    if [[ -z "$side" || -z "$symbol" ]]; then log_message "ERROR: Side/Symbol kosong."; return 1; fi

    log_message "INFO: Mempersiapkan order $side $symbol sejumlah ~$quantity USDT."
    local endpoint="/api/v3/order"
    local timestamp=$(date +%s%3N)
    local query_string="symbol=${symbol}&side=${side}&type=MARKET"eOrderQty=${quantity}×tamp=${timestamp}"
    local signature=$(echo -n "$query_string" | openssl dgst -sha256 -hmac "$SECRET_KEY" | sed 's/^.* //')
    local full_url="${BINANCE_API_URL}${endpoint}?${query_string}&signature=${signature}"

    log_message "INFO: Mengirim request ke Binance..."
    response=$(curl -s -H "X-MBX-APIKEY: ${API_KEY}" -X POST "$full_url")
    log_message "INFO: Respons Binance: $(echo "$response" | jq .)"

    if echo "$response" | jq -e '.code' > /dev/null; then
        local error_code=$(echo "$response" | jq -r '.code')
        local error_msg=$(echo "$response" | jq -r '.msg')
        log_message "ERROR: Binance API Error! Code: $error_code, Msg: $error_msg"
        return 1
    elif echo "$response" | jq -e '.orderId' > /dev/null; then
        local order_id=$(echo "$response" | jq -r '.orderId')
        log_message "SUCCESS: Order $side $symbol berhasil! OrderID: $order_id"
        return 0
    else
        log_message "ERROR: Respons tidak dikenal dari Binance API."
        return 1
    fi
}


# --- Fungsi Memproses Email ---
process_email_content() {
    local email_content="$1"
    log_message "INFO: Memulai parsing email..."

    # Ekstrak sinyal - **SESUAIKAN DENGAN FORMAT EMAIL ANDA**
    signal_line=$(echo "$email_content" | grep -i '^SIGNAL:' | head -n 1)
    symbol_line=$(echo "$email_content" | grep -i '^SYMBOL:' | head -n 1)

    side=$(echo "$signal_line" | awk -F': *' '{print $2}' | tr '[:lower:]' '[:upper:]' | tr -d '\r')
    symbol=$(echo "$symbol_line" | awk -F': *' '{print $2}' | tr -d '\r')

    log_message "DEBUG: Ditemukan Side='$side', Symbol='$symbol'"

    if [[ "$side" == "BUY" || "$side" == "SELL" ]] && [[ -n "$symbol" ]]; then
        log_message "INFO: Sinyal valid: $side $symbol. Mencoba eksekusi..."
        execute_binance_order "$side" "$symbol"
        # Tandai email sebagai sudah dibaca atau hapus di server (jika diperlukan/diinginkan)
        # Ini bagian yang lebih kompleks dengan mutt, mungkin perlu ID email
    else
        log_message "WARN: Sinyal tidak valid/ditemukan. Side='$side', Symbol='$symbol'."
    fi
}

# --- Main Loop ---
log_message "INFO: Memulai bot polling email..."

while true; do
    log_message "DEBUG: Mengecek email baru..."

    # Gunakan mutt untuk mencari email baru dari TradingView dan mencetak bodynya
    # Perintah mutt bisa kompleks dan rapuh. Ini contoh dasar:
    # -f : mailbox
    # -e 'set mail_check=0' : Non-aktifkan pemeriksaan interaktif
    # -e 'set timeout=10' : Timeout
    # -e 'set confirmappend=no delete=yes' : Untuk otomatis hapus setelah proses (HATI-HATI!) -> Lebih aman pakai 'set delete=ask-yes' atau flag N
    # push 'l ~N ~f tradingview.com\n' : Batasi ke email baru (N) dari sender (f)
    # push 'p\n' : Cetak email pertama yang cocok
    # push 'q\n' : Keluar
    # Perlu diuji secara ekstensif!

    # Alternatif lebih aman: Dapatkan daftar ID email baru, lalu fetch satu per satu
    # Ini contoh SANGAT DASAR untuk mendapatkan body email baru pertama dari pengirim tertentu
    # Mungkin perlu penyesuaian besar tergantung versi mutt dan konfigurasi server
    new_email=$(mutt -f "${IMAP_SERVER}${EMAIL_FOLDER}" \
                     -e "set user=${EMAIL_USER} pass=${EMAIL_PASSWORD}" \
                     -e "set mail_check=0 timeout=15 confirmappend=no delete=no" \
                     -e "push 'l ~N ~f ${TRADINGVIEW_SENDER}\n'" \
                     -e "push 'p\n'" \
                     -e "push 'q\n'" 2>/dev/null | sed -n '/^Content-Type:/,$p' | sed '1d') # Coba ekstrak body

    if [[ -n "$new_email" ]]; then
        log_message "INFO: Email baru terdeteksi dari ${TRADINGVIEW_SENDER}."
        echo "$new_email" >> /path/to/your/last_email_polled.log # Simpan salinan
        process_email_content "$new_email"
        # Di sini perlu logika untuk menandai email sebagai sudah diproses/dibaca
        # agar tidak diproses lagi di iterasi berikutnya. Ini bagian sulit dengan mutt
        # tanpa interaksi. Mungkin perlu memindahkan email ke folder lain.
        log_message "INFO: Selesai memproses email yang terdeteksi."

        # Beri jeda sedikit setelah memproses email
        sleep 5
    else
        log_message "DEBUG: Tidak ada email baru dari ${TRADINGVIEW_SENDER}."
    fi

    log_message "DEBUG: Tidur selama ${CHECK_INTERVAL} detik..."
    sleep "$CHECK_INTERVAL"
done
