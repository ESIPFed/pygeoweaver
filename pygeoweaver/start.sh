#!/bin/bash

FILE=~/geoweaver.jar
if [ -f "$FILE" ]; then
    echo "$FILE exists. Skip downloading.."
else
    echo "Downloading the latest geoweaver.jar to user home directory"
    cd ~ && curl -OL https://github.com/ESIPFed/Geoweaver/releases/download/latest/geoweaver.jar
fi

echo "Stop running Geoweaver if any.."
kill $(ps aux | grep 'geoweaver.jar' | awk '{print $2}')

echo "Start Geoweaver.."
nohup java -jar ~/geoweaver.jar > ~/geoweaver.log &

STATUS=0
counter=0
until [ $STATUS == 302 ] || [ $counter == 20 ]
do
    sleep 2
    STATUS=$(curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8070/Geoweaver")
    ((counter++))
done

if [ $counter == 20 ] ; then
    echo "Error: Geoweaver is not up"
    exit 1
else
    echo "Success: Geoweaver is up"
    exit 0
fi