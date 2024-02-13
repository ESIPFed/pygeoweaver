@echo off

echo Stop running Geoweaver if any..
taskkill /f /im geoweaver.exe > nul 2>nul

rem Get the user's home directory
for /f "tokens=1,* delims==" %%A in ('wmic os get UserProfile /value') do (
    if not "%%A"=="UserProfile" (
        set "home_dir=%%B"
    )
)

rem Check if Java command exists in the system PATH
echo Check java exists..
where java > nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    rem Java command not found in PATH, check JDK folder in home directory
    set "jdk_home=%home_dir%\jdk\jdk-11.0.18+10"  REM Change this to your JDK installation directory
    echo Check jdk_home %jdk_home%
    if exist "%jdk_home%\bin\java.exe" (
        set "java_cmd=%jdk_home%\bin\java.exe"
        echo Java command found in JDK directory: %java_cmd%
    ) else (
        echo Java command not found.
    )
) else (
    rem Java command found in PATH
    echo Java command found: %JAVA_HOME%\bin\java.exe
    set "java_cmd=java"
)

echo Start Geoweaver..
echo "%java_cmd%" -jar "%USERPROFILE%\geoweaver.jar"
start /b "" "%java_cmd%" -jar "%USERPROFILE%\geoweaver.jar"

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
