#!/bin/bash

# —------ user-specific creds/env file —------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/creds.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "[ERROR] $ENV_FILE not found" >&2
    exit 1
fi

# Read environment variables from the file
while IFS='=' read -r key value; do
    # Skip empty lines and comments
    [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
    # Remove any carriage return characters and leading/trailing whitespace
    key=$(echo "$key" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    value=$(echo "$value" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    # Export the variable
    export "$key"="$value"
done < "$ENV_FILE"

# --- fallbacks if a key is missing (optional) ---
if [ -z "$FB_SEARCH_TERM" ]; then
    FB_SEARCH_TERM="Toyota Prius"
fi

if [ -z "$RETRIES" ]; then
    RETRIES=2
fi

if [ -z "$WAIT" ]; then
    WAIT=20
fi

if [ -z "$SCROLLS" ]; then
    SCROLLS=5
fi

if [ -z "$USER_CITY" ]; then
    USER_CITY="Chicago, IL"
fi

# —--- resolve repo root regardless of location —---
REPO="$SCRIPT_DIR"
PY="$REPO/.venv/bin/python"
SCRIPT="$REPO/run_pipeline.py"

# Parse FB_SEARCH_TERM into items:
# - If it contains quotes, respect quoted phrases.
# - If it contains commas, split by commas.
# - Otherwise, treat the entire string as a single term.
BRANDS=()
if [[ "$FB_SEARCH_TERM" == *\"* ]]; then
  # respect quoted groups like: "Toyota Prius" "Honda Civic"
  eval "set -- $FB_SEARCH_TERM"
  for term in "$@"; do
    BRANDS+=("$term")
  done
elif [[ "$FB_SEARCH_TERM" == *","* ]]; then
  # comma-separated list: Toyota Prius,Honda Civic
  IFS=',' read -r -a BRANDS <<< "$FB_SEARCH_TERM"
else
  BRANDS=("$FB_SEARCH_TERM")
fi

for BRAND in "${BRANDS[@]}"; do
    BRAND_TRIMMED="$(echo "$BRAND" | sed 's/^\s\+//;s/\s\+$//')"
    if [[ -z "$BRAND_TRIMMED" ]]; then continue; fi
    echo "==== $BRAND_TRIMMED ===="
    "$PY" "$SCRIPT" --retries "$RETRIES" --wait "$WAIT" --scrolls "$SCROLLS" --search "$BRAND_TRIMMED" --user-city "$USER_CITY"
done

exit 0