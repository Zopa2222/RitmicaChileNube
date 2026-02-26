@echo off
setlocal EnableDelayedExpansion

echo =========================================
echo   Iniciando Ritmica Application
echo =========================================
echo Fecha: %date% - Hora: %time%
echo.

REM verificar Docker
docker --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Docker no esta disponible
    echo Iniciando Docker Desktop...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    echo Esperando 30 segundos a que Docker inicie...
    timeout /t 30 /nobreak
)

REM verificar compose
if exist "docker-compose-prod.yml" (
    set COMPOSE_FILE=docker-compose-prod.yml
) else if exist "docker-compose.yml" (
    set COMPOSE_FILE=docker-compose.yml
) else (
    echo ERROR: No se encontro archivo docker-compose
    pause
    exit /b 1
)

echo Deteniendo contenedores anteriores si existen...
docker compose -f %COMPOSE_FILE% down >nul 2>&1

echo.
echo Iniciando servicios...
docker compose -f %COMPOSE_FILE% up -d

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Fallo al iniciar los servicios
    pause
    exit /b 1
)

echo.
echo =========================================
echo   Aplicacion iniciada correctamente
echo =========================================
echo.
echo Abriendo Frontend: http://localhost:4200
echo.

REM start
timeout /t 3 /nobreak >nul
start http://localhost:4200
exit