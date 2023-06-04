@echo off

set "FILE=%USERPROFILE%\geoweaver.jar"
if exist "%FILE%" (
    echo %FILE% exists. Removing...
    del "%FILE%"
)

echo Downloading the latest geoweaver.jar to user home directory
cd %USERPROFILE% && curl -OL https://github.com/ESIPFed/Geoweaver/releases/download/latest/geoweaver.jar
