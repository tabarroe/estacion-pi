# logger_config.py
import logging
import logging.handlers 
import sys


def setup_logging():
    """Configura el sistema de logging para todo el proyecto."""
    # El logger raíz será la base para todos los demás.
    # Capturará todos los mensajes de nivel INFO y superior.
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Prevenir que se añadan múltiples handlers si esta función se llama más de una vez.
    if logger.hasHandlers():
        logger.handlers.clear()

    # --- Formateador ---
    # Define el formato de los mensajes de log.
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # --- Handler para el Archivo ---
    # Guarda los logs en un archivo. 'a' significa 'append' (añadir).
    # maxBytes y backupCount hacen que el log "rote": cuando el archivo llega a 5MB,
    # se renombra a weather_station.log.1 y se crea uno nuevo. Guarda hasta 5 archivos viejos.
    file_handler = logging.handlers.RotatingFileHandler(
        'weather_station.log', mode='a', maxBytes=5*1024*1024, backupCount=5
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # --- Handler para la Consola ---
    # Muestra los logs en la terminal.
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    

    return logger