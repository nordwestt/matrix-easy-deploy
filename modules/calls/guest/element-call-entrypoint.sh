#!/bin/sh
# Inject guest-call branding into Element Call's index.html at container start.
set -e

if [ -f /app/index.html ] && ! grep -q 'guest-call.css' /app/index.html; then
  sed -i 's|</head>|<link rel="stylesheet" href="/guest-call.css"></head>|' /app/index.html
  # Drop stale precompressed index so nginx serves the patched HTML.
  rm -f /app/index.html.gz
fi

exec nginx -g 'daemon off;'
