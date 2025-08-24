#!/bin/bash
exec > /home/pizero/estacion_meteo/startup_log.txt 2>&1

echo "--- start.sh iniciado por rc.local como ROOT a las $(date) ---"

sleep 20

# Nos movemos al directorio del proyecto del usuario pizero
cd /home/pizero/estacion_meteo
echo "Directorio de trabajo: $(pwd)"

export DISPLAY=:0

# Lanzamos el main.py usando el Python del ENTORNO VIRTUAL de pizero
echo "Lanzando main.py desde el venv de pizero..."
/home/pizero/estacion_meteo/env/bin/python -u main.py

echo "--- El script main.py ha terminado inesperadamente a las $(date) ---"
