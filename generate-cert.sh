#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"

DOMAINS_FILE="domains.txt"
CERT_FILE="certs/local-cert.pem"
KEY_FILE="certs/local-key.pem"
BASE_DOMAINS=(dashboard.localhost)

if [[ ! -f "$DOMAINS_FILE" ]]; then
    printf 'File domini non trovato: %s\n' "$DOMAINS_FILE" >&2
    exit 1
fi

mapfile -t DOMAINS < <(
    {
        printf '%s\n' "${BASE_DOMAINS[@]}"
        sed 's/#.*//; s/|.*//' "$DOMAINS_FILE"
    } |
        sed '/^[[:space:]]*$/d; s/^[[:space:]]*//; s/[[:space:]]*$//' |
        awk '!seen[$0]++'
)

mkdir -p certs

mkcert \
    -cert-file "$CERT_FILE" \
    -key-file "$KEY_FILE" \
    "${DOMAINS[@]}"

printf '\nCertificato generato con %d domini.\n' "${#DOMAINS[@]}"

printf '\nRiavvio di Traefik...\n'
docker compose restart traefik

printf '\nCertificato aggiornato e Traefik riavviato correttamente.\n'
