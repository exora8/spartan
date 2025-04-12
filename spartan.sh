#!/bin/bash

# --- Nama File Konfigurasi & Log & PID ---
CONFIG_FILE="$HOME/.trading_config"
LOG_FILE="$HOME/tradingview_monitor.log"
PID_FILE="$HOME/.trading_monitor.pid"
MONITOR_OUTPUT_LOG="$HOME/trading_monitor_output.log" # Untuk stdout/stderr proses background

# --- Fungsi Logging ---
# Log ke file $LOG_FILE
log_message() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

# --- Fungsi Cek Dependency ---
check_dependencies() {
    local missing=""
    for cmd in curl jq openssl grep sed awk dialog; do
        if ! command -v $cmd &> /dev/null; then
            missing="$missing $cmd"
        fi
    done
    if [[ -n "$missing" ]]; then
        echo "ERROR: Dependency missing:$missing. Please install them."
        echo "Example (Debian/Ubuntu): sudo apt update && sudo apt install curl jq openssl grep sed awk dialog"
        echo "Example (CentOS/Fedora): sudo yum install curl jq openssl-devel grep sed gawk dialog"
        exit 1
    fi
}

# --- Fungsi Load Konfigurasi ---
load_config() {
  # Set default values
  GMAIL_USER=""
  GMAIL_APP_PASS=""
  BINANCE_API_KEY=""
  BINANCE_SECRET_KEY=""
  SENDER_EMAIL="noreply@tradingview.com"
  KEYWORD="[spartan]"
  DEFAULT_SYMBOL="BTCUSDT"
  ORDER_QUANTITY="0.001"
  CHECK_INTERVAL=60

  if [[ -f "$CONFIG_FILE" ]]; then
    # Load existing config, protect permissions
    chmod 600 "$CONFIG_FILE"
    source "$CONFIG_FILE"
    log_message "Configuration loaded from $CONFIG_FILE"
  else
    log_message "Configuration file $CONFIG_FILE not found. Will prompt for setup."
    # Jalankan konfigurasi jika file tidak ada
    configure_settings || exit 1 # Keluar jika konfigurasi dibatalkan
  fi
}

# --- Fungsi Konfigurasi dengan Dialog ---
configure_settings() {
    local temp_file=$(mktemp)
    exec 3>&1 # Save stdout
    dialog --clear --backtitle "TradingView Monitor Setup" \
      --title "Konfigurasi Akun & Trading" \
      --form "Masukkan detail konfigurasi (Password/Secret akan tersembunyi)" 20 70 0 \
        "Alamat Email Gmail:"       1 1 "$GMAIL_USER"        1 25 40 0 \
        "Gmail App Password:"       2 1 "$GMAIL_APP_PASS"    2 25 40 1 \
        "Binance API Key:"          3 1 "$BINANCE_API_KEY"   3 25 60 0 \
        "Binance Secret Key:"       4 1 "$BINANCE_SECRET_KEY" 4 25 60 1 \
        "Email Pengirim TV:"        5 1 "$SENDER_EMAIL"      5 25 40 0 \
        "Keyword Email ([spartan]):" 6 1 "$KEYWORD"         6 25 40 0 \
        "Simbol Binance (e.g. BTCUSDT):" 7 1 "$DEFAULT_SYMBOL"  7 25 40 0 \
        "Kuantitas per Order:"      8 1 "$ORDER_QUANTITY"    8 25 40 0 \
        "Interval Cek (detik):"    9 1 "$CHECK_INTERVAL"    9 25 40 0 \
    2>"$temp_file"
    local exit_status=$?
    exec 3>&- # Restore stdout

    if [[ $exit_status -eq 0 ]]; then # User pilih OK
        local i=1
        GMAIL_USER=$(sed -n "${i}p" "$temp_file"); ((i++))
        GMAIL_APP_PASS=$(sed -n "${i}p" "$temp_file"); ((i++))
        BINANCE_API_KEY=$(sed -n "${i}p" "$temp_file"); ((i++))
        BINANCE_SECRET_KEY=$(sed -n "${i}p" "$temp_file"); ((i++))
        SENDER_EMAIL=$(sed -n "${i}p" "$temp_file"); ((i++))
        KEYWORD=$(sed -n "${i}p" "$temp_file"); ((i++))
        DEFAULT_SYMBOL=$(sed -n "${i}p" "$temp_file"); ((i++))
        ORDER_QUANTITY=$(sed -n "${i}p" "$temp_file"); ((i++))
        CHECK_INTERVAL=$(sed -n "${i}p" "$temp_file"); ((i++))

        # Validasi sederhana (bisa diperkuat)
        if [[ -z "$GMAIL_USER" || -z "$GMAIL_APP_PASS" || -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" || -z "$DEFAULT_SYMBOL" || -z "$ORDER_QUANTITY" ]]; then
             dialog --msgbox "Error: Semua field (kecuali Pengirim TV & Keyword jika default) wajib diisi." 10 50
             rm "$temp_file"
             return 1 # Gagal
        fi

        # Simpan konfigurasi ke file
        > "$CONFIG_FILE" # Kosongkan file
        echo "GMAIL_USER='${GMAIL_USER}'" >> "$CONFIG_FILE"
        echo "GMAIL_APP_PASS='${GMAIL_APP_PASS}'" >> "$CONFIG_FILE"
        echo "BINANCE_API_KEY='${BINANCE_API_KEY}'" >> "$CONFIG_FILE"
        echo "BINANCE_SECRET_KEY='${BINANCE_SECRET_KEY}'" >> "$CONFIG_FILE"
        echo "SENDER_EMAIL='${SENDER_EMAIL}'" >> "$CONFIG_FILE"
        echo "KEYWORD='${KEYWORD}'" >> "$CONFIG_FILE"
        echo "DEFAULT_SYMBOL='${DEFAULT_SYMBOL}'" >> "$CONFIG_FILE"
        echo "ORDER_QUANTITY='${ORDER_QUANTITY}'" >> "$CONFIG_FILE"
        echo "CHECK_INTERVAL='${CHECK_INTERVAL}'" >> "$CONFIG_FILE"
        chmod 600 "$CONFIG_FILE" # Set permission
        dialog --msgbox "Konfigurasi berhasil disimpan di $CONFIG_FILE" 8 60
        log_message "Configuration saved/updated via dialog."
        rm "$temp_file"
        return 0 # Sukses
    else # User pilih Cancel atau Esc
        dialog --msgbox "Konfigurasi dibatalkan." 8 40
        rm "$temp_file"
        return 1 # Batal
    fi
}

# --- Fungsi Eksekusi Order Binance (Sama seperti sebelumnya) ---
execute_binance_order() {
  local side="$1"
  local symbol="$2"
  local quantity="$3"
  local timestamp=$(date +%s%3N)
  local params="symbol=${symbol}&side=${side}&type=MARKET&quantity=${quantity}×tamp=${timestamp}"
  local signature=$(echo -n "$params" | openssl dgst -sha256 -hmac "$BINANCE_SECRET_KEY" | sed 's/^.* //')
  local BINANCE_API_URL="https://api.binance.com" # Bisa juga ditaruh di config
  local api_endpoint="/api/v3/order"
  local request_url="${BINANCE_API_URL}${api_endpoint}?${params}&signature=${signature}"

  log_message "Executing Binance Order: Side=$side, Symbol=$symbol, Quantity=$quantity"
  local response=$(curl -s -H "X-MBX-APIKEY: ${BINANCE_API_KEY}" -X POST "$request_url")

  if [[ $(echo "$response" | jq -r '.orderId // empty') ]]; then
    log_message "SUCCESS: Binance order placed. OrderID: $(echo "$response" | jq -r '.orderId'). Response: $response"
    return 0 # Sukses
  else
    log_message "ERROR: Failed to place Binance order. Response: $response"
    return 1 # Gagal
  fi
}

# --- Fungsi Inti Monitoring Email (Untuk dijalankan di background) ---
run_monitor_logic() {
    # Pastikan config sudah di-load ke environment subshell ini
    # (seharusnya sudah karena di-source di load_config sebelum memanggil ini)

    # File untuk menyimpan UID yang sudah diproses sesi ini
    # Lebih baik daripada file global jika script restart
    processed_uids_file=$(mktemp)
    trap 'rm -f $processed_uids_file' EXIT # Hapus file temp saat keluar

    log_message "Background monitor process started (PID: $$)."

    while true; do
      # Gunakan nilai dari variabel global/config yang sudah di-load
      # log_message "Checking for new emails from $SENDER_EMAIL..." # Log ini mungkin terlalu ramai

      local search_command="UID SEARCH UNSEEN FROM \"${SENDER_EMAIL}\""
      local uids_raw=$(curl -k -s --user "${GMAIL_USER}:${GMAIL_APP_PASS}" --url "imaps://imap.gmail.com:993/INBOX" -X "${search_command}")
      local uids=$(echo "$uids_raw" | grep '\* SEARCH' | sed 's/\* SEARCH //')

      if [[ -z "$uids" ]]; then
        sleep "$CHECK_INTERVAL"
        continue
      fi

      log_message "Found potential email UIDs: $uids"

      for uid in $uids; do
        if grep -q "^${uid}$" "$processed_uids_file"; then
            # log_message "UID $uid already processed in this session, skipping."
            curl -k -s --user "${GMAIL_USER}:${GMAIL_APP_PASS}" --url "imaps://imap.gmail.com:993/INBOX" \
                 -X "UID STORE ${uid} +FLAGS \Seen" > /dev/null
            continue
        fi

        log_message "Processing UID $uid..."
        local fetch_command="UID FETCH ${uid} BODY[]"
        local email_content=$(curl -k -s --user "${GMAIL_USER}:${GMAIL_APP_PASS}" --url "imaps://imap.gmail.com:993/INBOX" -X "${fetch_command}")

        # Lakukan decode jika perlu (tergantung encoding email)
        # Contoh sederhana untuk quoted-printable (mungkin perlu lebih canggih)
        # email_content=$(echo "$email_content" | perl -MMIME::QuotedPrint -ne 'print decode_qp($_)')

        # Periksa keyword (case-insensitive)
        if echo "$email_content" | grep -q -i -F "$KEYWORD"; then
          log_message "Keyword '$KEYWORD' found in UID $uid."

          local order_line=$(echo "$email_content" | grep -i 'order')
          # Parsing lebih kuat: cari 'order buy' atau 'order sell' case-insensitive
          local action_match=$(echo "$order_line" | grep -o -i -E 'order[[:space:]]+(buy|sell)')
          local action=$(echo "$action_match" | awk '{print $2}' | tr '[:upper:]' '[:lower:]')

          local symbol_match=$(echo "$order_line" | grep -o -i -E '@[[:space:]]+[0-9.]+.*terisi pada[[:space:]]+([[:alnum:]]+)')
          # Coba parse simbol dari email jika formatnya konsisten
          local parsed_symbol=$(echo "$symbol_match" | sed -n 's/.*terisi pada[[:space:]]\+\([[:alnum:]]\+\)/\1/p')
          local symbol_to_use="${parsed_symbol:-$DEFAULT_SYMBOL}" # Gunakan simbol dari email jika ada, kalau tidak pakai default
          # Pastikan simbol yg diparse valid (misal hanya huruf/angka)
          if ! [[ "$symbol_to_use" =~ ^[A-Za-z0-9]+$ ]]; then
              log_message "WARNING: Parsed symbol '$parsed_symbol' from UID $uid seems invalid. Falling back to default: $DEFAULT_SYMBOL"
              symbol_to_use="$DEFAULT_SYMBOL"
          elif [[ -n "$parsed_symbol" ]]; then
              log_message "Parsed symbol '$symbol_to_use' from email UID $uid."
          fi


          if [[ "$action" == "buy" ]]; then
            log_message "Detected action: BUY for UID $uid, Symbol: $symbol_to_use"
            execute_binance_order "BUY" "$symbol_to_use" "$ORDER_QUANTITY"
            local exec_status=$?
          elif [[ "$action" == "sell" ]]; then
            log_message "Detected action: SELL for UID $uid, Symbol: $symbol_to_use"
            execute_binance_order "SELL" "$symbol_to_use" "$ORDER_QUANTITY"
            local exec_status=$?
          else
            log_message "WARNING: Keyword found in UID $uid, but could not parse 'buy' or 'sell' after 'order'. Action word found: '$action'. Email content snippet: $(echo "$order_line" | head -n 1 | tr -d '\r\n' | cut -c 1-100)"
            exec_status=1 # Anggap gagal parse
          fi

          # Tandai sudah dibaca hanya jika eksekusi berhasil atau parsing gagal (agar tidak retry terus)
          if [[ $exec_status -eq 0 || "$action" != "buy" && "$action" != "sell" ]]; then
              echo "$uid" >> "$processed_uids_file" # Catat UID yg diproses
              curl -k -s --user "${GMAIL_USER}:${GMAIL_APP_PASS}" --url "imaps://imap.gmail.com:993/INBOX" \
                   -X "UID STORE ${uid} +FLAGS \Seen" > /dev/null
              log_message "Marked UID $uid as processed/seen (Exec Status: $exec_status, Action: $action)."
          else
               log_message "Binance execution failed for UID $uid (Exec Status: $exec_status). Email will remain unseen for potential retry."
          fi

        else
          # Keyword tidak ditemukan, tandai sudah dibaca
          # log_message "Keyword '$KEYWORD' not found in UID $uid. Marking as seen." # Mungkin terlalu ramai
          curl -k -s --user "${GMAIL_USER}:${GMAIL_APP_PASS}" --url "imaps://imap.gmail.com:993/INBOX" \
               -X "UID STORE ${uid} +FLAGS \Seen" > /dev/null
        fi # End check keyword
      done # End loop UIDs

      # Tunggu sebelum cek lagi
      sleep "$CHECK_INTERVAL"

    done # End while true
}

# --- Fungsi Cek Status Monitor ---
is_monitor_running() {
    if [[ -f "$PID_FILE" ]]; then
        local pid=$(cat "$PID_FILE")
        # Cek apakah proses dengan PID tsb benar-benar ada
        if ps -p "$pid" > /dev/null; then
            return 0 # Running
        else
            # File PID ada tapi prosesnya tidak ada (stale)
            log_message "Stale PID file found ($PID_FILE). Removing it."
            rm -f "$PID_FILE"
            return 1 # Not running
        fi
    else
        return 1 # Not running (PID file does not exist)
    fi
}

# --- Fungsi Start Monitor di Background ---
start_monitor() {
    if is_monitor_running; then
        dialog --msgbox "Monitor sudah berjalan (PID: $(cat $PID_FILE))." 8 50
        return
    fi

    # Cek apakah konfigurasi valid sebelum start
    if [[ -z "$GMAIL_USER" || -z "$GMAIL_APP_PASS" || -z "$BINANCE_API_KEY" || -z "$BINANCE_SECRET_KEY" ]]; then
         dialog --msgbox "Error: Konfigurasi belum lengkap. Silakan jalankan 'Konfigurasi Ulang'." 10 60
         return
    fi

    dialog --infobox "Memulai monitor di background..." 5 40
    # Jalankan fungsi inti di subshell background
    ( run_monitor_logic ) >> "$MONITOR_OUTPUT_LOG" 2>&1 &
    local monitor_pid=$!
    echo "$monitor_pid" > "$PID_FILE"
    sleep 1 # Beri waktu sejenak

    if is_monitor_running; then
        log_message "Monitor started successfully in background with PID: $monitor_pid"
        dialog --msgbox "Monitor berhasil dimulai di background (PID: $monitor_pid).\nOutput dasar ada di: $MONITOR_OUTPUT_LOG\nLog detail ada di: $LOG_FILE" 12 70
    else
        log_message "ERROR: Failed to start monitor in background."
        dialog --msgbox "ERROR: Gagal memulai monitor di background.\nCek $MONITOR_OUTPUT_LOG dan $LOG_FILE untuk detail." 10 60
        rm -f "$PID_FILE" # Hapus file PID jika gagal start
    fi
}

# --- Fungsi Stop Monitor ---
stop_monitor() {
    if is_monitor_running; then
        local pid=$(cat "$PID_FILE")
        dialog --yesno "Hentikan monitor yang sedang berjalan (PID: $pid)?" 8 50
        local choice=$?
        if [[ $choice -eq 0 ]]; then # User pilih Yes
            dialog --infobox "Menghentikan monitor (PID: $pid)..." 5 40
            kill "$pid"
            sleep 2 # Beri waktu untuk berhenti

            # Verifikasi apakah sudah berhenti
            if ! ps -p "$pid" > /dev/null; then
                 rm -f "$PID_FILE"
                 log_message "Monitor stopped successfully (PID: $pid)."
                 dialog --msgbox "Monitor berhasil dihentikan." 8 40
            else
                 log_message "Warning: Failed to stop monitor (PID: $pid) gracefully. May need manual kill."
                 dialog --yesno "Gagal menghentikan proses secara normal.\nCoba paksa kill (kill -9 $pid)?" 10 60
                 if [[ $? -eq 0 ]]; then
                     kill -9 "$pid"
                     sleep 1
                     rm -f "$PID_FILE"
                     log_message "Monitor force-killed (PID: $pid)."
                     dialog --msgbox "Monitor dihentikan paksa." 8 40
                 else
                    dialog --msgbox "Monitor mungkin masih berjalan (PID: $pid). Hentikan manual jika perlu." 10 60
                 fi

            fi
        else
             dialog --infobox "Pembatalan penghentian monitor." 5 40
             sleep 1
        fi
    else
        dialog --msgbox "Monitor tidak sedang berjalan." 8 40
    fi
}

# --- Fungsi Lihat Log ---
view_log() {
    if [[ ! -f "$LOG_FILE" ]]; then
        touch "$LOG_FILE" # Buat file jika belum ada
    fi
    dialog --backtitle "TradingView Monitor Log" \
           --title "Log Aktivitas - $LOG_FILE" \
           --tailbox "$LOG_FILE" 25 80
}

# --- Fungsi Lihat Output Background ---
view_output_log() {
    if [[ ! -f "$MONITOR_OUTPUT_LOG" ]]; then
        touch "$MONITOR_OUTPUT_LOG" # Buat file jika belum ada
    fi
    dialog --backtitle "TradingView Monitor Background Output" \
           --title "Output Proses Background - $MONITOR_OUTPUT_LOG" \
           --tailbox "$MONITOR_OUTPUT_LOG" 25 80
}


# --- MAIN SCRIPT ---
check_dependencies
load_config # Load atau minta konfigurasi di awal

while true; do
    # Cek status monitor untuk ditampilkan di menu
    local monitor_status_text
    if is_monitor_running; then
        monitor_status_text="Berjalan (PID: $(cat $PID_FILE))"
    else
        monitor_status_text="Tidak Berjalan"
    fi

    local temp_file=$(mktemp)
    exec 3>&1
    dialog --clear --backtitle "TradingView Gmail Monitor to Binance" \
            --title "Menu Utama" \
            --cancel-label "Keluar" \
            --menu "Status Monitor: $monitor_status_text\nPilih Opsi:" 20 70 7 \
            "1" "Start Monitor (Background)" \
            "2" "Stop Monitor" \
            "3" "Lihat Log Aktivitas" \
            "4" "Lihat Output Background" \
            "5" "Konfigurasi Ulang" \
            "6" "Keluar" \
            2>"$temp_file"

    local choice=$?
    local menu_item=$(cat "$temp_file")
    exec 3>&-
    rm "$temp_file"

    case $choice in
        0) # User Pilih OK
            case $menu_item in
                1) start_monitor ;;
                2) stop_monitor ;;
                3) view_log ;;
                4) view_output_log ;;
                5) configure_settings && load_config ;; # Re-configure & reload
                6) break ;; # Keluar dari loop while
                *) dialog --msgbox "Pilihan tidak valid." 6 30 ;;
            esac
            ;;
        1 | 255) # User Pilih Cancel atau tekan Esc
            break # Keluar dari loop while
            ;;
    esac
done

# Cleanup sebelum keluar
clear # Bersihkan layar terminal
log_message "Monitor script exited."
echo "TradingView Monitor script stopped."
exit 0
