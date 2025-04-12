#!/bin/bash

# ==============================================================================
# Smart TradingView Email Monitor with TUI Settings (Revision 2)
# ==============================================================================
# Dependencies: dialog, curl, jq, openssl, procmail, coreutils, grep, sed, gawk
#
# WARNING: Automated trading based on email is inherently risky. Network delays,
#          parsing errors, API changes, or email format changes can lead to
#          significant financial loss. Use entirely at your own risk.
#
# SECURITY: The configuration file (~/.tradingview_monitor.conf) stores your
#           API keys. Ensure it has strict permissions (chmod 600).
#
# TESTNET: ALWAYS test this script thoroughly using Binance Testnet API keys
#          and URL before using it with a live account and real funds.
#
# CUSTOMIZATION: The email parsing logic within the 'run_monitor_loop'
#                function MUST be adapted to match the exact format of your
#                TradingView alert emails (Subject and/or Body).
# ==============================================================================

# --- Global Variables & Constants ---
CONFIG_FILE="$HOME/.tradingview_monitor.conf"
DIALOG_OK=0
DIALOG_CANCEL=1
DIALOG_ESC=255
MONITOR_PID_FILE="/tmp/tradingview_monitor.pid" # File to store PID of monitoring process

# --- Default Configuration (will be overridden by config file) ---
declare -A config=(
    [BINANCE_API_KEY]=""
    [BINANCE_SECRET_KEY]=""
    [BINANCE_API_URL]="https://testnet.binance.vision" # Default to Testnet!
    [MAIL_DIR]="$HOME/Mail/tradingview/new"
    [PROCESSED_DIR]="$HOME/Mail/tradingview/cur"
    [ERROR_DIR]="$HOME/Mail/tradingview/error"
    [LOG_FILE]="$HOME/trading_monitor.log"
    [EXPECTED_SENDER]="noreply@tradingview.com" # Adjust if needed
    [TRIGGER_PHRASE]="[spartan=true]"          # Adjust trigger text
    [PARSE_LOCATION]="Subject"                 # Where to look for trigger & details: Subject or Body
    [SYMBOL_REGEX]='[A-Z]{3,}(USDT|BTC|BUSD|ETH|BNB)\b' # Regex to find symbol
    [SIDE_BUY_REGEX]='\b(long|buy)\b'          # Regex for BUY signal (case insensitive)
    [SIDE_SELL_REGEX]='\b(short|sell)\b'         # Regex for SELL signal (case insensitive)
    [QUANTITY_REGEX]='(Q=|Quantity:?)\s*([0-9.]+)' # Regex to find quantity (captures value in group 2)
    [DEFAULT_QUANTITY]="0.001"                 # Default quantity if not parsed
    [CHECK_INTERVAL_SECONDS]=30                # Check interval
    [API_TIMEOUT_SECONDS]=10                   # Curl timeout for API calls
)

# --- Function: Load Configuration ---
load_config() {
    # Start with defaults
    for key in "${!config[@]}"; do
        declare "${key}"="${config[$key]}" # Make available as script variables
    done

    if [[ -f "$CONFIG_FILE" ]]; then
        # Source the config file carefully - avoid command injection
        # Use grep and eval for safer loading of VAR="VALUE" lines
        while IFS= read -r line; do
           # Remove comments and trim whitespace
           cleaned_line=$(echo "$line" | sed -e 's/#.*$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
           # Skip empty lines
           [[ -z "$cleaned_line" ]] && continue
           # Check if it looks like a variable assignment
           if [[ "$cleaned_line" =~ ^[a-zA-Z_][a-zA-Z0-9_]*=.*$ ]]; then
               # Check if it's one of our known config keys
               var_name=$(echo "$cleaned_line" | cut -d'=' -f1)
               if [[ -v "config[$var_name]" ]]; then
                   # Safely evaluate the assignment
                   eval "$cleaned_line"
                   # Update the main config array
                   config[$var_name]="${!var_name}"
               else
                   log_message "WARN: Ignoring unknown variable '$var_name' in config file."
               fi
           else
               log_message "WARN: Ignoring malformed line in config file: $line"
           fi
        done < <(grep -v '^#' "$CONFIG_FILE" | grep '=') # Process lines with '=' excluding comment lines

        log_message "INFO: Configuration loaded from $CONFIG_FILE"
    else
        log_message "INFO: Config file $CONFIG_FILE not found. Using default settings. Please configure via Settings menu."
    fi
    # Ensure essential dirs exist
    mkdir -p "${config[MAIL_DIR]}" "${config[PROCESSED_DIR]}" "${config[ERROR_DIR]}" || {
        dialog --msgbox "CRITICAL ERROR: Could not create necessary mail directories. Check permissions or paths.\nMail Dir: ${config[MAIL_DIR]}\nProcessed Dir: ${config[PROCESSED_DIR]}\nError Dir: ${config[ERROR_DIR]}" 15 70
        exit 1
    }
}

# --- Function: Save Configuration ---
save_config() {
    # Backup old config? Optional.
    # [[ -f "$CONFIG_FILE" ]] && cp "$CONFIG_FILE" "$CONFIG_FILE.bak.$(date +%s)"

    # Use temporary file for atomic write
    local temp_conf_file
    temp_conf_file=$(mktemp) || { log_message "ERROR: Could not create temp file for saving config."; return 1; }

    echo "# TradingView Monitor Configuration" > "$temp_conf_file"
    echo "# Saved on $(date)" >> "$temp_conf_file"
    echo "# WARNING: This file contains sensitive API keys. Protect it!" >> "$temp_conf_file"
    echo "" >> "$temp_conf_file"
    for key in "${!config[@]}"; do
        # Basic quoting for bash sourcing:
        # Escape backslashes, double quotes, dollar signs within the value
        local escaped_value
        escaped_value=$(printf '%s' "${config[$key]}" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/\$/\\$/g')
        echo "${key}=\"${escaped_value}\"" >> "$temp_conf_file"
    done

    # Move temp file to actual config file location
    if mv "$temp_conf_file" "$CONFIG_FILE"; then
        chmod 600 "$CONFIG_FILE" # Set secure permissions
        log_message "INFO: Configuration saved to $CONFIG_FILE"
        return 0
    else
        log_message "ERROR: Failed to move temp config file to $CONFIG_FILE"
        rm -f "$temp_conf_file" # Clean up temp file on failure
        return 1
    fi
}

# --- Function: Logging ---
log_message() {
    # Log to file if LOG_FILE is set
    if [[ -n "${config[LOG_FILE]}" ]]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "${config[LOG_FILE]}"
    fi
    # Also echo to stderr for immediate feedback if not running monitor loop (e.g., during setup)
    # Use carefully as it might interfere with dialog if used improperly.
    # echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >&2
}

# --- Function: Show Settings Page ---
show_settings() {
    local temp_secret="********" # Placeholder for display
    [[ -z "${config[BINANCE_SECRET_KEY]}" ]] && temp_secret="" # Show empty if not set

    # Create temporary file for dialog output
    local temp_file
    temp_file=$(mktemp) || { log_message "ERROR: Cannot create temp file for dialog."; return 1; }
    # Ensure temp file is removed on exit/interrupt
    trap 'rm -f "$temp_file"' RETURN INT TERM HUP

    dialog --backtitle "TradingView Monitor Settings" \
           --title "Configuration" \
           --ok-label "Save" \
           --cancel-label "Cancel" \
           --mixedform "Edit settings. Secret Key shows '********'. Use Arrow Keys, Tab, Enter." 24 78 16 \
        "Binance API Key:"          1 1 "${config[BINANCE_API_KEY]}"      1 25 64 0 0 \
        "Binance Secret Key:"       2 1 "$temp_secret"                    2 25 64 0 1 \
        "Binance API URL:"          3 1 "${config[BINANCE_API_URL]}"    3 25 64 0 0 \
        "Mail Dir (New):"           4 1 "${config[MAIL_DIR]}"           4 25 64 0 0 \
        "Mail Dir (Processed):"     5 1 "${config[PROCESSED_DIR]}"      5 25 64 0 0 \
        "Mail Dir (Error):"         6 1 "${config[ERROR_DIR]}"         6 25 64 0 0 \
        "Log File Path:"            7 1 "${config[LOG_FILE]}"           7 25 64 0 0 \
        "Expected Sender Addr:"     8 1 "${config[EXPECTED_SENDER]}"    8 25 64 0 0 \
        "Trigger Phrase:"           9 1 "${config[TRIGGER_PHRASE]}"     9 25 64 0 0 \
        "Parse Location (Subject/Body):" 10 1 "${config[PARSE_LOCATION]}" 10 30 10 0 0 \
        "Symbol Regex:"             11 1 "${config[SYMBOL_REGEX]}"       11 25 64 0 0 \
        "Buy Signal Regex:"         12 1 "${config[SIDE_BUY_REGEX]}"     12 25 64 0 0 \
        "Sell Signal Regex:"        13 1 "${config[SIDE_SELL_REGEX]}"    13 25 64 0 0 \
        "Quantity Regex (Group 2):" 14 1 "${config[QUANTITY_REGEX]}"     14 25 64 0 0 \
        "Default Quantity:"         15 1 "${config[DEFAULT_QUANTITY]}"  15 25 20 0 0 \
        "Check Interval (sec):"     16 1 "${config[CHECK_INTERVAL_SECONDS]}" 16 25 10 0 0 \
        "API Timeout (sec):"       17 1 "${config[API_TIMEOUT_SECONDS]}"  17 25 10 0 0 \
        2> "$temp_file"

    local retval=$?
    local form_output

    form_output=$(<"$temp_file")
    rm -f "$temp_file" # Clean up temp file immediately

    if [[ $retval -eq $DIALOG_OK ]]; then # OK button pressed
        local i=0
        local values=()
        while IFS= read -r line; do
            values+=("$line")
        done <<< "$form_output"

        # Update config array
        config[BINANCE_API_KEY]="${values[0]}"
        # Only update secret if user entered something new (not '********')
        if [[ "${values[1]}" != "$temp_secret" ]] || [[ -z "${config[BINANCE_SECRET_KEY]}" && -n "${values[1]}" ]]; then
             config[BINANCE_SECRET_KEY]="${values[1]}"
        fi
        config[BINANCE_API_URL]="${values[2]}"
        config[MAIL_DIR]="${values[3]}"
        config[PROCESSED_DIR]="${values[4]}"
        config[ERROR_DIR]="${values[5]}"
        config[LOG_FILE]="${values[6]}"
        config[EXPECTED_SENDER]="${values[7]}"
        config[TRIGGER_PHRASE]="${values[8]}"
        config[PARSE_LOCATION]="${values[9]}"
        config[SYMBOL_REGEX]="${values[10]}"
        config[SIDE_BUY_REGEX]="${values[11]}"
        config[SIDE_SELL_REGEX]="${values[12]}"
        config[QUANTITY_REGEX]="${values[13]}"
        config[DEFAULT_QUANTITY]="${values[14]}"
        config[CHECK_INTERVAL_SECONDS]="${values[15]}"
        config[API_TIMEOUT_SECONDS]="${values[16]}"

        # Basic Validation
        local validation_error=""
        if ! [[ "${config[CHECK_INTERVAL_SECONDS]}" =~ ^[1-9][0-9]*$ ]]; then
             validation_error+="Check Interval must be a positive integer.\n"
             config[CHECK_INTERVAL_SECONDS]=30 # Reset
        fi
         if ! [[ "${config[API_TIMEOUT_SECONDS]}" =~ ^[1-9][0-9]*$ ]]; then
             validation_error+="API Timeout must be a positive integer.\n"
             config[API_TIMEOUT_SECONDS]=10 # Reset
        fi
        if [[ "${config[PARSE_LOCATION]}" != "Subject" && "${config[PARSE_LOCATION]}" != "Body" ]]; then
             validation_error+="Parse Location must be 'Subject' or 'Body'.\n"
             config[PARSE_LOCATION]="Subject" # Reset
        fi

        if [[ -n "$validation_error" ]]; then
            dialog --msgbox "Validation Errors:\n\n$validation_error" 12 60
        else
            if save_config; then
                dialog --msgbox "Settings saved successfully to\n$CONFIG_FILE" 8 60
            else
                 dialog --msgbox "ERROR: Failed to save settings!" 8 50
            fi
        fi
    fi
    # No explicit reload needed here as 'config' array was updated directly
}

# --- Function: Execute Binance Order ---
execute_binance_order() {
  local symbol="$1"
  local side="$2"
  local quantity="$3"
  local type="MARKET" # Using Market Order

  # Use loaded config values
  local api_key="${config[BINANCE_API_KEY]}"
  local secret_key="${config[BINANCE_SECRET_KEY]}"
  local api_url="${config[BINANCE_API_URL]}"
  local timeout="${config[API_TIMEOUT_SECONDS]}"

  # Validate input
  if [[ -z "$symbol" || -z "$side" || -z "$quantity" ]]; then
    log_message "ERROR: Order parameters incomplete (Symbol: '$symbol', Side: '$side', Quantity: '$quantity')"
    return 1
  fi
   if [[ -z "$api_key" || -z "$secret_key" ]]; then
    log_message "ERROR: Binance API Key or Secret Key not configured in Settings!"
    # Consider adding a notification mechanism here if running unattended
    return 1
  fi

  local timestamp
  timestamp=$(date +%s%3N) # Milliseconds timestamp
  # Ensure quantity uses dot as decimal separator if needed (locale independent)
  quantity=$(printf "%.8f" "$quantity" | sed 's/,/./') # Adjust precision as needed

  local query_string="symbol=${symbol}&side=${side}&type=${type}&quantity=${quantity}×tamp=${timestamp}"

  log_message "INFO: Preparing Binance order: $query_string"

  local signature
  # Corrected signature generation line (removed extra ')
  signature=$(echo -n "${query_string}" | openssl dgst -sha256 -hmac "${secret_key}" | sed 's/^.* //')

  local api_endpoint="/api/v3/order"
  local url="${api_url}${api_endpoint}"

  local response
  local curl_exit_code
  response=$(curl --connect-timeout "$timeout" -m "$((timeout + 5))" -s -H "X-MBX-APIKEY: ${api_key}" -X POST "${url}?${query_string}&signature=${signature}")
  curl_exit_code=$?

  if [[ $curl_exit_code -ne 0 ]]; then
      log_message "ERROR: curl command failed (Code: $curl_exit_code). Could not reach Binance API ($url). Timeout: ${timeout}s."
      # Handle specific curl errors? (e.g., 6: Couldn't resolve host, 7: Couldn't connect, 28: Timeout)
      return 1
  fi

  log_message "DEBUG: Binance API Raw Response: $response"

  # Check response validity (basic JSON check)
  if ! echo "$response" | jq -e . > /dev/null 2>&1; then
      log_message "ERROR: Invalid JSON response received from Binance API: $response"
      return 1
  fi

  # Check for Binance API error structure first ({ "code": ..., "msg": ...})
  if echo "$response" | jq -e '.code' > /dev/null; then
      local error_code error_msg
      error_code=$(echo "$response" | jq -r '.code')
      error_msg=$(echo "$response" | jq -r '.msg // "Unknown Binance error"')
      log_message "ERROR: Binance API returned an error. Code: $error_code, Message: $error_msg"
      return 1
  # Check for successful order structure
  elif echo "$response" | jq -e '.orderId' > /dev/null; then
    local order_id client_order_id status fills
    order_id=$(echo "$response" | jq -r '.orderId')
    client_order_id=$(echo "$response" | jq -r '.clientOrderId')
    status=$(echo "$response" | jq -r '.status')
    fills=$(echo "$response" | jq -c '.fills // []') # Get fills info if available
    log_message "SUCCESS: Binance order placed! Symbol: $symbol, Side: $side, Qty: $quantity. OrderID: $order_id, Status: $status. Fills: $fills"
    # Optional: Further processing based on fills (average price, fees)
    return 0
  else
    log_message "ERROR: Unexpected response format from Binance API: $response"
    return 1
  fi
}

# --- Function: Monitoring Loop Core Logic (Runs in Background) ---
# This function performs the actual monitoring cycle.
# It needs to be run in a background process.
_monitor_process() {
    log_message "INFO: Monitoring process started (PID: $$). Watching '${config[MAIL_DIR]}'."
    log_message "INFO: Trigger: Sender='${config[EXPECTED_SENDER]}', Phrase='${config[TRIGGER_PHRASE]}', Location='${config[PARSE_LOCATION]}'"

    while true; do
        local found_mail=false
        # Use find with -print -quit to process one file at a time, preventing race conditions
        local email_file
        email_file=$(find "${config[MAIL_DIR]}" -maxdepth 1 -type f -print -quit)

        if [[ -n "$email_file" ]]; then
            found_mail=true
            log_message "DEBUG: Processing email file: $email_file"

            # Ensure file is readable before proceeding
            if [[ ! -r "$email_file" ]]; then
                log_message "ERROR: Cannot read email file: $email_file. Skipping."
                # Optionally move to error directory if unreadable after a short wait?
                sleep 1
                if [[ -f "$email_file" ]]; then # Check if it still exists
                   mv "$email_file" "${config[ERROR_DIR]}/" || log_message "ERROR: Failed to move unreadable file $email_file to ${config[ERROR_DIR]}"
                fi
                continue # Skip to next loop iteration
            fi

            # Extract headers and body safely using formail
            local subject from_header body
            subject=$(formail -cx Subject: < "$email_file" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | tr -d '\n\r' || echo "PARSE_ERROR_SUBJECT")
            from_header=$(formail -cx From: < "$email_file" | tr -d '\n\r' || echo "PARSE_ERROR_FROM")

            # Extract body (handle potential errors during extraction)
            # formail -c keeps headers, -k keeps body. Combine? No, just extract body.
            # Using sed to remove headers might be fragile. Let's try formail -b (removes headers).
            body=$(formail -b < "$email_file" || echo "PARSE_ERROR_BODY")

            log_message "DEBUG: From: $from_header"
            log_message "DEBUG: Subject: $subject"
            # log_message "DEBUG: Body: $body" # Log body only if necessary for debugging

            # Determine where to search based on config
            local search_content
            if [[ "${config[PARSE_LOCATION]}" == "Body" ]]; then
                search_content="$body"
                log_message "DEBUG: Searching in Email Body."
            else
                search_content="$subject"
                log_message "DEBUG: Searching in Email Subject."
            fi

            # Check Trigger Conditions
            # Use grep -q for quiet check. Use -F for fixed string trigger phrase.
            if echo "$from_header" | grep -qi "${config[EXPECTED_SENDER]}" && \
               echo "$search_content" | grep -qF "${config[TRIGGER_PHRASE]}"; then
                log_message ">>> TRIGGER FOUND in email: $email_file"

                # --- Parsing Logic (NEEDS USER CUSTOMIZATION based on REGEX settings) ---
                local symbol="" side="" quantity=""

                # Extract Symbol using configured regex
                if [[ "$search_content" =~ ${config[SYMBOL_REGEX]} ]]; then
                    symbol="${BASH_REMATCH[0]}"
                fi

                # Extract Side (BUY/SELL) using configured regex (case insensitive)
                if echo "$search_content" | grep -iqE "${config[SIDE_BUY_REGEX]}"; then
                    side="BUY"
                elif echo "$search_content" | grep -iqE "${config[SIDE_SELL_REGEX]}"; then
                    side="SELL"
                fi

                # Extract Quantity using configured regex (captures group 2)
                if [[ "$search_content" =~ ${config[QUANTITY_REGEX]} ]]; then
                     # BASH_REMATCH[0] is the whole match, [1] is group 1, [2] is group 2
                     quantity="${BASH_REMATCH[2]}"
                     # Remove potential leading/trailing spaces from regex capture
                     quantity=$(echo "$quantity" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
                fi

                # Use default quantity if not parsed or empty
                if [[ -z "$quantity" ]]; then
                    log_message "INFO: Quantity not found in '$search_content'. Using default: ${config[DEFAULT_QUANTITY]}"
                    quantity="${config[DEFAULT_QUANTITY]}"
                fi
                # --- End Parsing Logic ---

                log_message "INFO: Parsed Details: Symbol='$symbol', Side='$side', Quantity='$quantity'"

                # Validate parsed details before executing order
                if [[ -n "$symbol" && -n "$side" && -n "$quantity" ]]; then
                    # Execute Binance Order
                    if execute_binance_order "$symbol" "$side" "$quantity"; then
                        # Success: Move email to processed directory
                        mv "$email_file" "${config[PROCESSED_DIR]}/" || log_message "ERROR: Failed to move processed email $email_file to ${config[PROCESSED_DIR]}"
                        log_message "INFO: Email processed successfully, moved to '${config[PROCESSED_DIR]}'."
                    else
                        # Execution Failed: Move email to error directory
                        mv "$email_file" "${config[ERROR_DIR]}/" || log_message "ERROR: Failed to move error email $email_file (after execution failure) to ${config[ERROR_DIR]}"
                        log_message "ERROR: Email moved to '${config[ERROR_DIR]}' due to order execution failure."
                    fi
                else
                    # Parsing Failed: Move email to error directory
                    log_message "ERROR: Failed to parse required order details (Symbol, Side, Quantity) from content matching trigger."
                    log_message "ERROR: Search Content was: $search_content"
                    mv "$email_file" "${config[ERROR_DIR]}/" || log_message "ERROR: Failed to move error email $email_file (after parsing failure) to ${config[ERROR_DIR]}"
                    log_message "ERROR: Email moved to '${config[ERROR_DIR]}' due to parsing failure."
                fi
            else
                # Email doesn't match trigger conditions: Move to processed directory
                log_message "INFO: Email skipped (sender/trigger mismatch): $email_file"
                mv "$email_file" "${config[PROCESSED_DIR]}/" || log_message "ERROR: Failed to move skipped email $email_file to ${config[PROCESSED_DIR]}"
            fi # End trigger check

        fi # End if email_file found

        # Sleep logic
        if ! $found_mail; then
            # No mail found, sleep for the configured interval
            sleep "${config[CHECK_INTERVAL_SECONDS]}"
        else
            # Mail was processed, short sleep before checking again immediately
            sleep 1
        fi

    done # End while true loop

    # This part is unlikely to be reached unless loop is broken externally
    log_message "INFO: Monitoring process (PID: $$) is stopping."
}


# --- Function: Start Monitoring Page ---
start_monitoring() {
    # Check if already running
    if [[ -f "$MONITOR_PID_FILE" ]]; then
        local old_pid
        old_pid=$(cat "$MONITOR_PID_FILE")
        if ps -p "$old_pid" > /dev/null; then
            dialog --title "Already Running" --yesno "Monitoring process (PID $old_pid) seems to be running.\n\nStop the existing process and start a new one?" 10 60
            local choice=$?
            if [[ $choice -eq $DIALOG_OK ]]; then
                log_message "INFO: User requested stop of existing process PID $old_pid."
                kill "$old_pid"
                sleep 2 # Give it time to terminate
                if ps -p "$old_pid" > /dev/null; then
                   log_message "WARN: Failed to stop PID $old_pid gracefully, sending KILL signal."
                   kill -9 "$old_pid"
                   sleep 1
                fi
                rm -f "$MONITOR_PID_FILE"
                log_message "INFO: Existing process PID $old_pid stopped."
            else
                dialog --msgbox "Monitoring not started. Existing process PID $old_pid remains." 8 50
                return
            fi
        else
             log_message "INFO: Stale PID file found ($MONITOR_PID_FILE for PID $old_pid). Removing."
             rm -f "$MONITOR_PID_FILE"
        fi
    fi


    # Validate crucial settings before starting
    local errors=""
    [[ -z "${config[BINANCE_API_KEY]}" ]] && errors+="Binance API Key is not set.\n"
    [[ -z "${config[BINANCE_SECRET_KEY]}" ]] && errors+="Binance Secret Key is not set.\n"
    [[ ! -d "${config[MAIL_DIR]}" ]] && errors+="Mail Directory (New) '${config[MAIL_DIR]}' does not exist or is not a directory.\n"
    # Add checks for dependencies if needed (though done at start)

    if [[ -n "$errors" ]]; then
        dialog --msgbox "Cannot start monitoring due to configuration errors:\n\n$errors\nPlease check Settings." 15 70
        return
    fi

    # Clear the log file? Optional.
    # > "${config[LOG_FILE]}"
    log_message "INFO: Preparing to start monitoring..."

    # Run the _monitor_process function in the background
    ( _monitor_process ) &
    local monitor_pid=$!

    # Save the PID to a file
    echo "$monitor_pid" > "$MONITOR_PID_FILE"
    log_message "INFO: Monitoring process launched in background (PID: $monitor_pid)."

    # Display the log file using tailbox. User can exit tailbox without stopping the background process.
    # Provide instructions on how to stop it (via main menu).
    dialog --title "Monitoring Started (PID: $monitor_pid)" \
           --msgbox "Monitoring process is running in the background (PID: $monitor_pid).\nLogs are being written to:\n${config[LOG_FILE]}\n\nYou can view logs live using the 'View Log File' option or stop the monitor from the main menu.\n\nPress OK to return to the menu." 14 75

    # The background process continues to run after this msgbox is closed.
}

# --- Function: Stop Monitoring ---
stop_monitoring() {
    if [[ -f "$MONITOR_PID_FILE" ]]; then
        local pid_to_kill
        pid_to_kill=$(cat "$MONITOR_PID_FILE")
        if ps -p "$pid_to_kill" > /dev/null; then
             dialog --title "Stop Monitoring" --yesno "Stop the monitoring process (PID $pid_to_kill)?" 8 50
             local choice=$?
             if [[ $choice -eq $DIALOG_OK ]]; then
                 log_message "INFO: Attempting to stop monitoring process PID $pid_to_kill..."
                 kill "$pid_to_kill"
                 sleep 2
                 if ps -p "$pid_to_kill" > /dev/null; then
                      log_message "WARN: Process $pid_to_kill did not stop gracefully. Sending KILL signal."
                      kill -9 "$pid_to_kill"
                      sleep 1
                 fi
                 if ! ps -p "$pid_to_kill" > /dev/null; then
                      log_message "INFO: Monitoring process PID $pid_to_kill stopped successfully."
                      rm -f "$MONITOR_PID_FILE"
                      dialog --msgbox "Monitoring process (PID $pid_to_kill) stopped." 8 50
                 else
                      log_message "ERROR: Failed to stop monitoring process PID $pid_to_kill."
                      dialog --msgbox "ERROR: Could not stop monitoring process PID $pid_to_kill." 8 50
                 fi
             fi
        else
            log_message "INFO: Process PID $pid_to_kill from PID file not found. Removing stale file."
            rm -f "$MONITOR_PID_FILE"
            dialog --msgbox "Monitoring process was not running (stale PID file removed)." 8 60
        fi
    else
        dialog --msgbox "Monitoring process does not appear to be running (no PID file found)." 8 60
    fi
}

# --- Function: View Log File ---
view_log() {
     if [[ -f "${config[LOG_FILE]}" ]]; then
         # Use tailbox which allows scrolling. Ctrl+C or Esc usually exits.
         dialog --title "Log Viewer - ${config[LOG_FILE]}" --no-kill --tailbox "${config[LOG_FILE]}" 25 80
     else
         dialog --msgbox "Log file '${config[LOG_FILE]}' not found or not configured." 8 60
     fi
}


# --- Function: Main Menu ---
main_menu() {
    while true; do
        # Check monitor status for menu label
        local monitor_status="Not Running"
        local start_stop_option="Start Monitoring"
        local start_stop_choice="1"
        if [[ -f "$MONITOR_PID_FILE" ]]; then
             local current_pid=$(cat "$MONITOR_PID_FILE")
             if ps -p "$current_pid" > /dev/null; then
                 monitor_status="Running (PID $current_pid)"
                 start_stop_option="Stop Monitoring"
                 start_stop_choice="S" # Use 'S' for stop action
             else
                 # Stale PID file
                 monitor_status="Not Running (Stale PID)"
                 rm -f "$MONITOR_PID_FILE" # Clean up stale file
             fi
        fi

        local temp_file
        temp_file=$(mktemp) || { echo "ERROR: Cannot create temp file for main menu."; exit 1; }
        trap 'rm -f "$temp_file"' RETURN INT TERM HUP

        dialog --backtitle "TradingView Email Monitor - Status: $monitor_status" \
               --title "Main Menu" \
               --cancel-label "Exit" \
               --menu "Select an option:" 16 65 5 \
                "${start_stop_choice}"  "${start_stop_option}" \
                "2" "Settings" \
                "3" "View Log File" \
                "4" "Save Settings Now" \
                "5" "Reload Settings" \
                2> "$temp_file"

        local choice_retval=$?
        local choice
        choice=$(<"$temp_file")
        rm -f "$temp_file" # Clean up temp file

        # Handle dialog exit codes (Cancel/Esc for Exit)
        if [[ $choice_retval -eq $DIALOG_CANCEL || $choice_retval -eq $DIALOG_ESC ]]; then
            # Before exiting, check if monitor is running and ask to stop?
            if [[ -f "$MONITOR_PID_FILE" ]]; then
                 local running_pid=$(cat "$MONITOR_PID_FILE")
                 if ps -p "$running_pid" > /dev/null; then
                     dialog --title "Exit Confirmation" --yesno "The monitoring process (PID $running_pid) is still running.\n\nDo you want to stop it before exiting?" 10 60
                     if [[ $? -eq $DIALOG_OK ]]; then
                         stop_monitoring
                     fi
                 fi
            fi
            clear
            echo "Exiting TradingView Monitor."
            # Clean up PID file just in case, though stop_monitoring should handle it
            # rm -f "$MONITOR_PID_FILE"
            exit 0
        fi

        # Handle menu choices
        case "$choice" in
            1) clear; start_monitoring ;;   # Start
            S) clear; stop_monitoring ;;    # Stop (uses 'S' choice from menu)
            2) clear; show_settings ;;
            3) clear; view_log ;;
            4) clear; save_config && dialog --msgbox "Settings explicitly saved." 7 40 || dialog --msgbox "Failed to save settings!" 7 40 ;;
            5) clear; load_config && dialog --msgbox "Settings reloaded from\n$CONFIG_FILE" 8 50 ;;
            *) clear; dialog --msgbox "Invalid option selected." 6 40 ;;
        esac
    done
}

# --- Initial Checks and Execution ---

# Check for Dialog utility
if ! command -v dialog &> /dev/null; then
    echo "Error: 'dialog' utility not found. Please install it (e.g., 'sudo apt install dialog' or 'sudo yum install dialog')."
    exit 1
fi

# Check for other core dependencies
for cmd in curl jq openssl formail grep sed gawk find mv mkdir date ps kill printf sleep cat rm; do
    if ! command -v $cmd &> /dev/null; then
        # Can't use dialog here as it might be the missing one
        echo "Error: Required command '$cmd' not found. Please install the package providing it (often coreutils, procmail, jq, openssl-clients, curl)."
        exit 1
    fi
done

# Set trap for cleanup on unexpected exit
trap 'rm -f $(ls /tmp/dialog.* 2>/dev/null) "$MONITOR_PID_FILE" ; clear ; echo "Script interrupted." ; exit 1' INT TERM HUP

# Ensure clean state on start
rm -f /tmp/dialog.* 2>/dev/null

# Load initial configuration
load_config

# Start the main menu TUI
main_menu

# Final cleanup (should not be reached if main_menu exits properly)
clear
exit 0
