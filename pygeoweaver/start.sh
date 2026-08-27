#!/bin/bash

echo "Stop running Geoweaver if any.."
pkill -f geoweaver.jar

echo "Checking Java..."

# Detect the user's shell
USER_SHELL=$(basename "$SHELL")

# Set the appropriate rc file based on the detected shell
if [ "$USER_SHELL" = "bash" ]; then
    RC_FILE=~/.bashrc
elif [ "$USER_SHELL" = "zsh" ]; then
    RC_FILE=~/.zshrc
elif [ "$USER_SHELL" = "fish" ]; then
    RC_FILE=~/.config/fish/config.fish
else
    # Default to .bashrc if unknown shell
    RC_FILE=~/.bashrc
fi

# Check if the rc file exists, if not, create it
if [ ! -f "$RC_FILE" ]; then
    echo "$RC_FILE does not exist. Creating it..."
    mkdir -p "$(dirname "$RC_FILE")"
    touch "$RC_FILE"
fi

# Source the rc file
if [ "$USER_SHELL" = "fish" ]; then
    echo "Sourcing $RC_FILE with fish..."
    fish -c "source $RC_FILE"
else
    echo "Sourcing $RC_FILE..."
    source "$RC_FILE"
fi

JAVA_BIN="java"
if [ -x "$HOME/jdk/jdk-17.0.13+11/bin/java" ]; then
    JAVA_BIN="$HOME/jdk/jdk-17.0.13+11/bin/java"
elif [ -x "$HOME/jdk/jdk-11.0.18+10/bin/java" ]; then
    JAVA_BIN="$HOME/jdk/jdk-11.0.18+10/bin/java"
fi

JAVA_MAJOR=$("$JAVA_BIN" -version 2>&1 | sed -n 's/.*version "\([0-9]*\).*/\1/p' | head -1)
if [ -z "$JAVA_MAJOR" ]; then
    # Legacy 1.8 style
    JAVA_MAJOR=$("$JAVA_BIN" -version 2>&1 | sed -n 's/.*version "1\.\([0-9]*\).*/\1/p' | head -1)
fi

if [ -n "$JAVA_MAJOR" ] && [ "$JAVA_MAJOR" -lt 17 ]; then
    echo "========================================================================"
    echo "  Geoweaver WARNING: Unsupported Java version"
    echo "========================================================================"
    echo "  Detected Java major version: $JAVA_MAJOR"
    echo "  Latest Geoweaver (2.2+ / Spring Boot 3) requires Java 17 or newer."
    echo "  JDK versions older than 17 are no longer supported."
    echo
    echo "  If you cannot bump your JDK, use an older Geoweaver release instead:"
    echo "    - Stay on Geoweaver 2.1.x (Java 11 compatible)"
    echo "    - Releases: https://github.com/ESIPFed/Geoweaver/releases"
    echo "    - Example jar: https://github.com/ESIPFed/Geoweaver/releases/download/v2.1.7/geoweaver.jar"
    echo "========================================================================"
    exit 1
fi

echo "Start Geoweaver.."
nohup "$JAVA_BIN" -jar ~/geoweaver.jar > ~/geoweaver.log &

STATUS=0
counter=0
until [ $STATUS == 302 ] || [ $counter == 20 ]
do
    sleep 2
    STATUS=$(curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8070/Geoweaver")
    ((counter++))
done

cat ~/geoweaver.log
if [ $counter == 20 ] ; then
    echo "Error: Geoweaver is not up"
    exit 1
else
    echo "Success: Geoweaver is up"
    exit 0
fi
