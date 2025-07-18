#!/bin/bash

# Redirigimos TODA la salida de este script a un archivo de log para depurar.
# Así, cualquier mensaje o error, por pequeño que sea, quedará registrado.
exec > /home/pizero/estacion_meteo/startup_log.txt 2>&1

echo "------------------------------------------"
echo "Script start.sh iniciado en: $(date)"
echo "------------------------------------------"

echo "Paso 1: Pausa inicial de 15 segundos..."
sleep 20
echo "Pausa completada."

echo "Paso 2: Navegando al directorio del script..."
cd "$(dirname "$0")"
echo "Directorio actual: $(pwd)"

echo "Paso 3: Exportando la variable de entorno DISPLAY..."
export DISPLAY=:0
echo "DISPLAY establecido a: $DISPLAY"

echo "Paso 4: Intentando lanzar main.py con el Python del sistema..."
# Usamos 'which python3' para ver qué ejecutable estamos usando.
echo "Ruta de Python 3: $(which python3)"

# Lanzamos el script.
python3 -u main.py

# Si el script de Python se cierra por cualquier razón, este mensaje se registrará.
echo "------------------------------------------"
echo "El script main.py ha terminado en: $(date)"
echo "------------------------------------------"
