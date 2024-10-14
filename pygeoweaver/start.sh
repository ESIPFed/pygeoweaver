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

echo "Start Geoweaver.."
nohup ~/jdk/jdk-11.0.18+10/bin/java -jar ~/geoweaver.jar > ~/geoweaver.log &

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
