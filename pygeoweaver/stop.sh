#!/bin/bash

echo "Stop running Geoweaver if any.."
pkill -f geoweaver.jar

GEOWEAVER_PORT="${GEOWEAVER_PORT:-8070}"
GEOWEAVER_URL="http://localhost:${GEOWEAVER_PORT}/Geoweaver"
STATUS=$(curl -s -o /dev/null -w "%{http_code}\n" "$GEOWEAVER_URL")

# Still answering with a normal front-door code means stop failed.
case "$STATUS" in
  200|301|302|303)
    echo "Error: unable to stop (still HTTP ${STATUS} on ${GEOWEAVER_URL})."
    exit 1
    ;;
  *)
    echo "Stopped."
    exit 0
    ;;
esac
