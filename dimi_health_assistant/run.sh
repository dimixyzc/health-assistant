#!/usr/bin/with-contenv bashio

set -euo pipefail

export TELEGRAM_BOT_TOKEN
export TELEGRAM_CHAT_ID
export GARMIN_EMAIL
export GARMIN_PASSWORD
export RENPHO_EMAIL
export RENPHO_PASSWORD
export GOOGLE_CLIENT_ID
export GOOGLE_CLIENT_SECRET
export OPENAI_API_KEY
export OPENAI_MODEL
export RENPHO_REMINDER_DAYS
export TZ
export DATA_DIR

TELEGRAM_BOT_TOKEN="$(bashio::config 'telegram_bot_token')"
TELEGRAM_CHAT_ID="$(bashio::config 'telegram_chat_id')"
GARMIN_EMAIL="$(bashio::config 'garmin_email')"
GARMIN_PASSWORD="$(bashio::config 'garmin_password')"
RENPHO_EMAIL="$(bashio::config 'renpho_email')"
RENPHO_PASSWORD="$(bashio::config 'renpho_password')"
GOOGLE_CLIENT_ID="$(bashio::config 'google_client_id')"
GOOGLE_CLIENT_SECRET="$(bashio::config 'google_client_secret')"
OPENAI_API_KEY="$(bashio::config 'openai_api_key')"
OPENAI_MODEL="$(bashio::config 'openai_model' 'gpt-5.5')"
RENPHO_REMINDER_DAYS="$(bashio::config 'renpho_reminder_days' '5')"
TZ="$(bashio::config 'timezone' 'Europe/Berlin')"
DATA_DIR="/data"

bashio::log.info "Starting Dimi Health Assistant v1.0.0"
bashio::log.info "TZ: ${TZ} | Renpho reminder nach: ${RENPHO_REMINDER_DAYS} Tagen"

# Google Fit Token von /share nach /data kopieren falls vorhanden
if [ -f /share/google_fit_token.json ]; then
    cp /share/google_fit_token.json /data/google_fit_token.json
    bashio::log.info "Google Fit Token aus /share übernommen"
fi

exec python3 -u /opt/health-assistant/main.py
