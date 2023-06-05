#!/bin/bash

echo "Stop running Geoweaver if any.."
pkill -f geoweaver.jar
STATUS=$(curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8070/Geoweaver")
if [ $STATUS != 302 ]; then
    echo "Stopped."
    exit 0
else
    echo "Error: unable to stop."
    exit 1
fi

