#!/bin/bash

# --- Konfigurasi ---
# Sesuaikan path ini ke direktori 'new' Maildir Anda
MAILDIR_NEW="$HOME/Maildir/new"
# Teks spesifik yang dicari di email
SEARCH_PHRASE="Exora AI"
# Interval pengecekan (dalam detik)
CHECK_INTERVAL=5
# Durasi beep total (dalam detik)
BEEP_DURATION=5
# Frekuensi beep (Hz) - opsional, sesuaikan jika perlu
BEEP_FREQ=1000
# Durasi satu kali beep (ms) - opsional
BEEP_LEN=200
# Durasi jeda antar beep (ms) - opsional
BEEP_DELAY=300
# --- Akhir Konfigurasi ---

# Periksa apakah direktori Maildir ada
if [ ! -d "$MAILDIR_NEW" ]; then
  echo "Error: Direktori Maildir '$MAILDIR_NEW' tidak ditemukan."
  echo "Pastikan path sudah benar dan Maildir sudah dikonfigurasi."
  exit 1
fi

# Periksa apakah command 'beep' ada
if ! command -v beep &> /dev/null; then
    echo "Error: Command 'beep' tidak ditemukan."
    echo "Silakan install 'beep' (contoh: sudo apt install beep)."
    # Fallback ke terminal bell jika beep tidak ada (kurang bisa dikontrol)
    USE_TERMINAL_BELL=true
    echo "Akan mencoba menggunakan terminal bell sebagai alternatif."
else
    USE_TERMINAL_BELL=false
fi

echo "Memulai monitoring email di '$MAILDIR_NEW' setiap $CHECK_INTERVAL detik..."
echo "Mencari teks: '$SEARCH_PHRASE'"
echo "Tekan Ctrl+C untuk berhenti."

# Fungsi untuk trigger beep
trigger_beep() {
  local action=$1
  echo "$(date '+%Y-%m-%d %H:%M:%S') - Aksi terdeteksi: $action. Memulai Beep..."

  if $USE_TERMINAL_BELL; then
      # Alternatif pakai terminal bell (kurang presisi durasinya)
      local end_time=$((SECONDS + BEEP_DURATION))
      while [ $SECONDS -lt $end_time ]; do
          echo -en '\a' # Bunyikan bell
          sleep 0.5     # Jeda singkat
      done
      echo # Newline setelah selesai
  else
      # Menggunakan command beep
      local cycles=$(( (BEEP_DURATION * 1000) / (BEEP_LEN + BEEP_DELAY) ))
      [ $cycles -eq 0 ] && cycles=1 # Pastikan minimal 1 cycle

      for (( i=0; i<$cycles; i++ )); do
          beep -f $BEEP_FREQ -l $BEEP_LEN
          # Jangan sleep setelah beep terakhir
          if (( i < cycles - 1 )); then
              sleep $(echo "$BEEP_DELAY / 1000" | bc -l) # Konversi ms ke detik
          fi
      done
  fi
  echo "$(date '+%Y-%m-%d %H:%M:%S') - Beep selesai."
}

# Loop utama
while true; do
  # Cari file baru di direktori 'new'
  # Menggunakan find untuk penanganan nama file yang aneh dan lebih aman
  find "$MAILDIR_NEW" -maxdepth 1 -type f -print0 | while IFS= read -r -d $'\0' email_file; do
    if [ -f "$email_file" ]; then # Double check jika file masih ada
      filename=$(basename "$email_file")
      echo "$(date '+%Y-%m-%d %H:%M:%S') - Memproses email baru: $filename"

      # Periksa apakah email mengandung frasa yang dicari
      # Menggunakan grep -i untuk case-insensitive jika diperlukan
      if grep -q "$SEARCH_PHRASE" "$email_file"; then
        echo "  -> Ditemukan '$SEARCH_PHRASE'."

        # Ekstraksi aksi (buy/sell) setelah kata 'order'
        # Menggunakan awk: cari baris dengan SEARCH_PHRASE, lalu cari kata 'order', print kata setelahnya
        action=$(awk -v phrase="$SEARCH_PHRASE" '
          $0 ~ phrase {
            for(i=1; i<=NF; i++) {
              if (tolower($i) == "order" && (i+1) <= NF) {
                print tolower($(i+1)) # Ambil kata setelah 'order' dan jadikan lowercase
                exit # Cukup temukan satu kali
              }
            }
          }' "$email_file")

        if [[ "$action" == "buy" || "$action" == "sell" ]]; then
          echo "  -> Terdeteksi Order: $action"
          trigger_beep "$action"
        else
          echo "  -> Tidak ditemukan 'buy' atau 'sell' valid setelah 'order'."
        fi
      else
         echo "  -> '$SEARCH_PHRASE' tidak ditemukan."
      fi

      # Pindahkan email dari 'new' ke 'cur' untuk menandainya sebagai sudah dibaca/diproses
      # Ini adalah cara standar Maildir agar email tidak diproses berulang kali
      new_path_cur="${MAILDIR_NEW%/*}/cur/${filename}:2,S" # Tambahkan flag :2,S (read)
      mv "$email_file" "$new_path_cur"
      echo "  -> Email dipindahkan ke direktori 'cur': $(basename "$new_path_cur")"

    fi # end if -f "$email_file"
  done # end find loop

  # Tunggu interval sebelum cek lagi
  sleep $CHECK_INTERVAL

done # end while true
