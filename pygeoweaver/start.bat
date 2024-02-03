@echo off

echo Stop running Geoweaver if any..
taskkill /f /im geoweaver.exe > nul

echo Check Java..

echo Start Geoweaver..
echo javaw -jar "%USERPROFILE%\geoweaver.jar"
start /b javaw -jar "%USERPROFILE%\geoweaver.jar"

set STATUS=0
set counter=0
:loop
ping -n 2 127.0.0.1 > nul
set /a counter+=1
curl -s -o NUL -w "%%{http_code}" "http://localhost:8070/Geoweaver" > response.txt
set /p STATUS=<response.txt
del response.txt
if "%STATUS%"=="302" (
    goto :success
)
if %counter%==20 (
    goto :error
)
goto :loop

:success
type "%USERPROFILE%\geoweaver.log"
echo Success: Geoweaver is up
exit /b 0

:error
echo Error: Geoweaver is not up
exit /b 1
