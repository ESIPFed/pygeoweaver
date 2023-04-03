#!/bin/bash

echo "Stop running Geoweaver if any.."
pkill -f geoweaver

FILE=~/geoweaver.jar
if [ -f "$FILE" ]; then
    echo "$FILE exists. Remove.."
    rm -f $FILE
fi

echo "Downloading the latest geoweaver.jar to user home directory"
cd ~ && curl -OL https://github.com/ESIPFed/Geoweaver/releases/download/latest/geoweaver.jar

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

cat ~/geoweaver.log
if [ $counter == 20 ] ; then
    echo "Error: Geoweaver is not up"
    exit 1
else
    echo "Success: Geoweaver is up"
    exit 0
fi