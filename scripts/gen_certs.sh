#!/usr/bin/env bash
# Generate a self-signed CA and a server TLS certificate with an IP Subject
# Alternative Name (SAN), so browsers trust the certificate when you access
# the dashboard directly by IP address (no domain name needed).
#
# Usage:
#   ./scripts/gen_certs.sh [IP_ADDRESS]
#
# The IP can also be provided via the SERVER_IP env variable.
# Defaults to 127.0.0.1 when neither is supplied.
#
# Output (written to ./certs/):
#   ca.crt       — CA root certificate  →  install this in your OS / browser
#   server.crt   — server certificate   →  used by nginx
#   server.key   — server private key   →  used by nginx
#
# Requirements: openssl (available in any standard Linux/macOS environment)

set -euo pipefail

IP="${1:-${SERVER_IP:-127.0.0.1}}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
CERTS_DIR="${REPO_ROOT}/certs"
DAYS=3650   # 10 years

mkdir -p "$CERTS_DIR"

echo "==> Generating CA key and root certificate..."
openssl genrsa -out "$CERTS_DIR/ca.key" 4096 2>/dev/null
openssl req -x509 -new -nodes \
  -key "$CERTS_DIR/ca.key" \
  -sha256 \
  -days "$DAYS" \
  -subj "/CN=bothr-local-CA/O=bothr/C=ES" \
  -out "$CERTS_DIR/ca.crt"

echo "==> Generating server private key..."
openssl genrsa -out "$CERTS_DIR/server.key" 2048 2>/dev/null

echo "==> Generating server certificate signing request (CSR)..."
openssl req -new \
  -key "$CERTS_DIR/server.key" \
  -subj "/CN=${IP}/O=bothr/C=ES" \
  -out "$CERTS_DIR/server.csr"

echo "==> Signing server certificate (SAN: IP:${IP})..."
cat > "$CERTS_DIR/server.ext" <<EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=IP:${IP}
EOF

openssl x509 -req \
  -in "$CERTS_DIR/server.csr" \
  -CA "$CERTS_DIR/ca.crt" \
  -CAkey "$CERTS_DIR/ca.key" \
  -CAcreateserial \
  -out "$CERTS_DIR/server.crt" \
  -days "$DAYS" \
  -sha256 \
  -extfile "$CERTS_DIR/server.ext"

# Clean up temporary files (ca.srl is kept to track issued serial numbers)
rm "$CERTS_DIR/server.csr" "$CERTS_DIR/server.ext" 2>/dev/null || true

# Set restrictive permissions on private keys
chmod 600 "$CERTS_DIR/ca.key" "$CERTS_DIR/server.key"

echo ""
echo "==> Certificates generated successfully in: ${CERTS_DIR}/"
echo ""
echo "    Files:"
echo "      ca.crt      — CA root certificate (install this once per device)"
echo "      server.crt  — server certificate  (used by nginx)"
echo "      server.key  — server private key  (used by nginx)"
echo ""
echo "==> Installing the CA root certificate:"
echo ""
echo "    macOS:"
echo "      sudo security add-trusted-cert -d -r trustRoot \\"
echo "        -k /Library/Keychains/System.keychain ${CERTS_DIR}/ca.crt"
echo ""
echo "    Linux (Ubuntu/Debian):"
echo "      sudo cp ${CERTS_DIR}/ca.crt /usr/local/share/ca-certificates/bothr-ca.crt"
echo "      sudo update-ca-certificates"
echo ""
echo "    Linux (RHEL/Fedora):"
echo "      sudo cp ${CERTS_DIR}/ca.crt /etc/pki/ca-trust/source/anchors/bothr-ca.crt"
echo "      sudo update-ca-trust"
echo ""
echo "    Windows:"
echo "      1. Open certlm.msc (certificate manager for Local Machine)"
echo "      2. Navigate to Trusted Root Certification Authorities > Certificates"
echo "      3. Right-click > All Tasks > Import"
echo "      4. Select: ${CERTS_DIR}/ca.crt"
echo ""
echo "    Android (Chrome):"
echo "      Settings > Security > Install a certificate > CA certificate"
echo "      Select the ca.crt file transferred to the device."
echo ""
echo "    iPhone / iPad (Safari):"
echo "      1. Transfer ca.crt to the device (AirDrop, email, etc.)"
echo "      2. Settings > General > VPN & Device Management > Install Profile"
echo "      3. Settings > General > About > Certificate Trust Settings > Enable full trust"
echo ""
echo "==> After installing the CA, start the stack with:"
echo "      docker-compose up --build -d"
echo "    Then open: https://${IP}"
