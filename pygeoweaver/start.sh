#!/bin/bash

echo "Stop running Geoweaver if any.."
pkill -f geoweaver.jar 2>/dev/null || true

echo "Checking Java / Geoweaver jar channel..."

# Prefer the Python runtime resolver (bumps managed ~/jdk to 17, or
# selects legacy 2.1.x jar for unmanaged old system JDKs).
if command -v python3 >/dev/null 2>&1 && python3 -c "import pygeoweaver.jdk_utils" 2>/dev/null; then
    RESOLVED=$(python3 - <<'PY'
from pygeoweaver.jdk_utils import ensure_geoweaver_runtime
from pygeoweaver.utils import download_geoweaver_jar

runtime = ensure_geoweaver_runtime(force_recheck=True)
download_geoweaver_jar()
print(runtime.java_bin)
print(runtime.channel)
PY
)
    JAVA_BIN=$(echo "$RESOLVED" | sed -n '1p')
    CHANNEL=$(echo "$RESOLVED" | sed -n '2p')
    echo "Using Java: $JAVA_BIN (channel=$CHANNEL)"
else
    # Fallback without pygeoweaver import: prefer managed JDK 17, else legacy jar.
    MANAGED_JDK17="$HOME/jdk/jdk-17.0.13+11/bin/java"
    MANAGED_JDK11="$HOME/jdk/jdk-11.0.18+10/bin/java"
    JAR_URL_LATEST="https://github.com/ESIPFed/Geoweaver/releases/download/latest/geoweaver.jar"
    JAR_URL_LEGACY="https://github.com/ESIPFed/Geoweaver/releases/download/v2.1.7/geoweaver.jar"
    CHANNEL_MARKER="$HOME/geoweaver.jar.channel"
    JAR_PATH="$HOME/geoweaver.jar"

    JAVA_BIN="java"
    CHANNEL="latest"
    DOWNLOAD_URL="$JAR_URL_LATEST"

    if [ -x "$MANAGED_JDK17" ]; then
        JAVA_BIN="$MANAGED_JDK17"
    elif [ -x "$MANAGED_JDK11" ]; then
        JAVA_BIN="$MANAGED_JDK11"
    fi

    JAVA_MAJOR=$("$JAVA_BIN" -version 2>&1 | sed -n 's/.*version "\([0-9]*\).*/\1/p' | head -1)
    if [ -z "$JAVA_MAJOR" ]; then
        JAVA_MAJOR=$("$JAVA_BIN" -version 2>&1 | sed -n 's/.*version "1\.\([0-9]*\).*/\1/p' | head -1)
    fi

    if [ -n "$JAVA_MAJOR" ] && [ "$JAVA_MAJOR" -lt 17 ]; then
        echo "Java $JAVA_MAJOR detected; using Geoweaver 2.1.x legacy jar."
        echo "Install Java 17+ or run: gw installjdk / pip install pygeoweaver && gw start"
        CHANNEL="legacy"
        DOWNLOAD_URL="$JAR_URL_LEGACY"
    fi

    CURRENT_CHANNEL=""
    if [ -f "$CHANNEL_MARKER" ]; then
        CURRENT_CHANNEL=$(tr -d '[:space:]' < "$CHANNEL_MARKER")
    fi
    if [ ! -f "$JAR_PATH" ] || [ "$CURRENT_CHANNEL" != "$CHANNEL" ]; then
        echo "Downloading Geoweaver jar ($CHANNEL)..."
        if command -v curl >/dev/null 2>&1; then
            curl -fsSL -o "$JAR_PATH" "$DOWNLOAD_URL"
        else
            wget -q -O "$JAR_PATH" "$DOWNLOAD_URL"
        fi
        echo "$CHANNEL" > "$CHANNEL_MARKER"
    fi
fi

echo "Start Geoweaver.."
nohup "$JAVA_BIN" -jar ~/geoweaver.jar > ~/geoweaver.log &

STATUS=0
counter=0
until [ "$STATUS" = "302" ] || [ "$counter" = "20" ]
do
    sleep 2
    STATUS=$(curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8070/Geoweaver")
    ((counter++))
done

cat ~/geoweaver.log

if [ "$STATUS" = "302" ]; then
    echo "Success: Geoweaver is up"
else
    echo "Error: Geoweaver is not up"
    exit 1
fi
