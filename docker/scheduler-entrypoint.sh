#!/bin/sh
set -eu

if [ -n "${GOOGLE_APPLICATION_CREDENTIALS_JSON:-}" ]; then
  credentials_path="${GOOGLE_APPLICATION_CREDENTIALS:-/app/credentials/google-service-account.json}"
  mkdir -p "$(dirname "$credentials_path")"
  printf '%s' "$GOOGLE_APPLICATION_CREDENTIALS_JSON" > "$credentials_path"
  chmod 0600 "$credentials_path"
  export GOOGLE_APPLICATION_CREDENTIALS="$credentials_path"
fi

exec "$@"
