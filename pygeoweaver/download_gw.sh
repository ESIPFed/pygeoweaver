#!/bin/bash
FILE=~/geoweaver.jar
if [ -f "$FILE" ]; then
    echo "$FILE exists. Remove.."
    rm -f $FILE
fi

echo "Downloading the latest geoweaver.jar to user home directory"
cd ~ && curl -OL https://github.com/ESIPFed/Geoweaver/releases/download/latest/geoweaver.jar