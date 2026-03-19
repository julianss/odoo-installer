#!/bin/bash
# create_fullchain.sh - Build fullchain.pem and copy private key for Nginx/Odoo installer
#
# Combines a server certificate, intermediate certificate bundle (zip), and
# private key into a fullchain.pem suitable for Nginx/Odoo.

set -euo pipefail

usage() {
    cat <<EOF
Usage: $(basename "$0") -c CERT -i INTERMEDIATE_ZIP -k KEY [-o OUTPUT_DIR] [-p PREFIX]

Required:
  -c CERT               Path to the server certificate (.cer/.crt/.pem)
  -i INTERMEDIATE_ZIP   Path to the intermediate certificates zip file
  -k KEY                Path to the private key file (.key)

Optional:
  -o OUTPUT_DIR         Output directory (default: /etc/ssl)
  -p PREFIX             Filename prefix (e.g. "example.com" -> example.com_fullchain.pem)
  -h                    Show this help message

Examples:
  sudo ./$(basename "$0") -c server.cer -i intermediates.zip -k private.key
  sudo ./$(basename "$0") -c server.cer -i intermediates.zip -k private.key -o /etc/ssl -p example.com
EOF
    exit "${1:-0}"
}

CERT=""
INTERMEDIATE_ZIP=""
PRIVATE_KEY=""
OUTPUT_DIR="/etc/ssl"
PREFIX=""

while getopts "c:i:k:o:p:h" opt; do
    case "$opt" in
        c) CERT="$OPTARG" ;;
        i) INTERMEDIATE_ZIP="$OPTARG" ;;
        k) PRIVATE_KEY="$OPTARG" ;;
        o) OUTPUT_DIR="$OPTARG" ;;
        p) PREFIX="${OPTARG}_" ;;
        h) usage 0 ;;
        *) usage 1 ;;
    esac
done

# Validate required arguments
if [ -z "$CERT" ] || [ -z "$INTERMEDIATE_ZIP" ] || [ -z "$PRIVATE_KEY" ]; then
    echo "ERROR: -c, -i, and -k are required."
    echo
    usage 1
fi

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# Verify source files exist
for f in "$CERT" "$INTERMEDIATE_ZIP" "$PRIVATE_KEY"; do
    if [ ! -f "$f" ]; then
        echo "ERROR: File not found: $f"
        exit 1
    fi
done

# Extract intermediates
unzip -q "$INTERMEDIATE_ZIP" -d "$TMPDIR"

# Verify the server cert
echo "Server certificate:"
openssl x509 -in "$CERT" -noout -subject -issuer -dates
echo

# Build fullchain: server cert first, then intermediates in chain order
# Sectigo chain: server -> intermediate1 (signing CA) -> intermediate2 (root-signed)
cat "$CERT" > "$TMPDIR/fullchain.pem"

# Append intermediates in order (intermediate1 signs server, intermediate2 signs intermediate1)
for inter in "$TMPDIR"/intermediate1.cer "$TMPDIR"/intermediate2.cer; do
    if [ -f "$inter" ]; then
        echo "Adding intermediate: $(openssl x509 -in "$inter" -noout -subject)"
        cat "$inter" >> "$TMPDIR/fullchain.pem"
    fi
done

# Verify the chain
echo
echo "Verifying chain..."
if openssl verify -partial_chain "$TMPDIR/fullchain.pem" 2>/dev/null; then
    echo "Chain verification: OK"
else
    echo "WARNING: Chain could not be fully verified (may need system root CAs)"
fi

# Verify key matches cert
CERT_MOD=$(openssl x509 -in "$CERT" -noout -modulus | md5sum)
KEY_MOD=$(openssl rsa -in "$PRIVATE_KEY" -noout -modulus 2>/dev/null | md5sum)
if [ "$CERT_MOD" = "$KEY_MOD" ]; then
    echo "Key matches certificate: OK"
else
    echo "ERROR: Private key does NOT match the certificate!"
    exit 1
fi

# Copy to output directory
mkdir -p "$OUTPUT_DIR"
OUT_CERT="$OUTPUT_DIR/${PREFIX}fullchain.pem"
OUT_KEY="$OUTPUT_DIR/${PREFIX}private.key"
cp "$TMPDIR/fullchain.pem" "$OUT_CERT"
cp "$PRIVATE_KEY" "$OUT_KEY"
chmod 644 "$OUT_CERT"
chmod 600 "$OUT_KEY"

echo
echo "Files created:"
echo "  Certificate chain: $OUT_CERT ($(grep -c 'BEGIN CERTIFICATE' "$OUT_CERT") certs)"
echo "  Private key:       $OUT_KEY"
echo
echo "Use these paths in the Odoo CLI installer when prompted for SSL files."
