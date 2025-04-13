#!/bin/bash

# --- Konfigurasi ---
CHECK_INTERVAL=5 # Detik
EMAIL_SOURCE_FILE="simulated_emails.txt" # File untuk simulasi email masuk
BEEP_DURATION=5 # Detik total durasi bip alert

# --- Warna ANSI ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# --- Status ---
listening_active=false
last_signal="-"
last_check_time="-"
processed_lines=0 # Melacak baris yang sudah diproses di file (simulasi sederhana 'unread')

# --- Fungsi ---

# Cek apakah 'beep' terinstall
has_beep_command() {
    command -v beep &> /dev/null
}

# Fungsi untuk memainkan alert bip
play_alert_beep() {
    local start_time=$(date +%s)
    echo -e "${YELLOW}>>> ALERT! Signal detected! Playing sound... <<<${NC}"
    if has_beep_command; then
        # Pola bip on/off dengan command 'beep' (membutuhkan tuning)
        # Coba 5 kali bip dengan jeda
        count=0
        while [[ $(($(date +%s) - start_time)) -lt $BEEP_DURATION && $count -lt 5 ]]; do
             beep -f 600 -l 400 # Frekuensi 600Hz, durasi 400ms
             sleep 0.6          # Jeda antar bip
             ((count++))
        done
    else
        # Fallback jika 'beep' tidak ada: Gunakan bell terminal standar (\a)
        count=0
        while [[ $(($(date +%s) - start_time)) -lt $BEEP_DURATION && $count -lt 10 ]]; do
            echo -ne "\a" # Bunyi bell
            sleep 0.25    # Jeda singkat 'on'
            sleep 0.25    # Jeda 'off'
             ((count++))
        done
        echo # Newline setelah selesai bip
    fi
    echo -e "${YELLOW}>>> Alert sound finished <<<${NC}"
}

# Fungsi untuk memeriksa email (dari file simulasi)
check_emails() {
    last_check_time=$(date +"%Y-%m-%d %H:%M:%S")
    local new_signal_found=false

    # Hanya proses baris baru sejak pengecekan terakhir (simulasi sederhana)
    local current_line_count=$(wc -l < "$EMAIL_SOURCE_FILE" 2>/dev/null || echo 0)
    if [[ $current_line_count -gt $processed_lines ]]; then
        # Ada baris baru, proses dari baris setelah processed_lines
        tail -n +"$(($processed_lines + 1))" "$EMAIL_SOURCE_FILE" | while IFS= read -r line; do
            ((processed_lines++)) # Tandai baris ini sebagai diproses

            # 1. Cek apakah ada 'Exora AI'
            if [[ "$line" == *"Exora AI"* ]]; then
                # 2. Cek apakah ada 'order buy' atau 'order sell'
                if echo "$line" | grep -q -o 'order buy'; then
                    last_signal="${GREEN}BUY${NC}"
                    echo -e "$(date +"%H:%M:%S") - ${GREEN}BUY Signal Detected!${NC} Content: $line"
                    new_signal_found=true
                elif echo "$line" | grep -q -o 'order sell'; then
                    last_signal="${RED}SELL${NC}"
                    echo -e "$(date +"%H:%M:%S") - ${RED}SELL Signal Detected!${NC} Content: $line"
                    new_signal_found=true
                fi
            fi
        done

        if $new_signal_found; then
            play_alert_beep
        fi
    fi
    # Update jumlah baris yang diproses jika file menyusut (misal dihapus manual)
     processed_lines=$current_line_count
}


# Fungsi untuk menampilkan status
display_status() {
    local status_text
    if $listening_active; then
        status_text="${GREEN}LISTENING${NC}"
    else
        status_text="${RED}IDLE${NC}"
    fi
    echo -e "+----------------------------------------------------------+"
    echo -e "| ${CYAN}Exora AI Signal Listener (Simulation)${NC}"
    echo -e "+----------------------------------------------------------+"
    echo -e "| Status         : $status_text"
    echo -e "| Last Check     : ${YELLOW}$last_check_time${NC}"
    echo -e "| Last Signal    : $last_signal"
    echo -e "| Check Interval : ${YELLOW}${CHECK_INTERVAL}s${NC}"
    echo -e "| Source File    : ${YELLOW}${EMAIL_SOURCE_FILE}${NC}"
    echo -e "+----------------------------------------------------------+"
}

# Fungsi untuk menampilkan menu
display_menu() {
    echo -e "| ${BLUE}MENU:${NC}"
    echo -e "| 1. ${GREEN}Start Listening${NC}"
    echo -e "| 2. ${RED}Stop Listening${NC}"
    echo -e "| 3. Settings (Not Implemented)"
    echo -e "| 4. ${YELLOW}Exit${NC}"
    echo -e "+----------------------------------------------------------+"
    echo -en "Pilih opsi [1-4]: "
}

# --- Main Loop ---
while true; do
    clear
    display_status

    if $listening_active; then
        echo "| ${CYAN}Checking for signals... (Press Ctrl+C to stop immediate check)${NC}"
        echo -e "+----------------------------------------------------------+"
        # Lakukan pengecekan non-blokir jika bisa, atau blokir saja
        check_emails
        # Tampilkan menu lagi setelah check jika user belum input
        display_menu & # Jalankan di background agar tidak menunggu input
        menu_pid=$!
        # Tunggu interval atau sampai user menekan tombol (dengan timeout)
        read -t $CHECK_INTERVAL -n 1 -s user_input # -n 1 -s: baca 1 char tanpa echo
        # Jika user menekan sesuatu, kill proses menu background
        if [[ $? -eq 0 ]]; then
             kill $menu_pid &>/dev/null
             wait $menu_pid &>/dev/null
        else
            # Timeout tercapai (tidak ada input), lanjutkan loop check
            kill $menu_pid &>/dev/null
            wait $menu_pid &>/dev/null
            continue
        fi
    else
         display_menu
         read user_input
    fi


    case $user_input in
        1)
            if ! $listening_active; then
                # Reset state saat mulai listening
                last_signal="-"
                # Cek jumlah baris awal di file agar tidak memproses yang lama
                processed_lines=$(wc -l < "$EMAIL_SOURCE_FILE" 2>/dev/null || echo 0)
                listening_active=true
                echo -e "\n${GREEN}Starting listener...${NC}"
                sleep 1
            else
                echo -e "\n${YELLOW}Already listening.${NC}"
                sleep 1
            fi
            ;;
        2)
            if $listening_active; then
                listening_active=false
                echo -e "\n${RED}Stopping listener...${NC}"
                sleep 1
            else
                echo -e "\n${YELLOW}Already stopped.${NC}"
                sleep 1
            fi
            ;;
        3)
            echo -e "\n${YELLOW}Settings menu is not implemented yet.${NC}"
            sleep 2
            ;;
        4)
            echo -e "\n${YELLOW}Exiting... Goodbye!${NC}"
            exit 0
            ;;
        *)
            # Jika input didapat dari read -t saat listening, mungkin kosong atau aneh
            if [[ -n "$user_input" ]]; then
                 echo -e "\n${RED}Pilihan tidak valid: [$user_input]. Coba lagi.${NC}"
                 sleep 1
            fi
            ;;
    esac
done

# --- End of Script ---
