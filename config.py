# config.py

# --- Configuración MQTT ---
MQTT_BROKER_IP = "127.0.0.1"  # El broker corre en la misma Pi (localhost)
MQTT_PORT = 1883
MQTT_TOPIC_EXTERIOR_LISTEN = "estacion/exterior/#"

# --- Configuración Hardware (Pines en modo BCM) ---
PIN_NEOPIXEL = 21          # Pin GPIO18 (PWM0)
NEOPIXEL_COUNT = 2         # Dos LEDs en la tira
NEOPIXEL_BRIGHTNESS = 0.3  # Brillo de 0.0 a 1.0

# --- Configuración de Pantalla TFT ---
PIN_TFT_RST = 25
PIN_TFT_DC = 24
PIN_TFT_LED = 13
PIN_PAGE_BUTTON = 6

# Índices para cada LED, para que el código sea más legible
NEOPIXEL_INDEX_SYSTEM = 0      # El primer LED es para el estado del sistema
NEOPIXEL_INDEX_ENVIRONMENT = 1 # El segundo LED es para el estado del clima

# --- Paleta de Colores para los LEDs (R, G, B) ---
COLOR_OFF = (0, 0, 0)
COLOR_GRIS = (40, 40, 40)
# Colores de Estado del Sistema
COLOR_SYS_OK = (0, 150, 0)         # Verde
COLOR_SYS_WARN1 = (255, 255, 0)    # Amarillo
COLOR_SYS_WARN2 = (255, 165, 0)    # Naranja
COLOR_SYS_OFFLINE = (200, 0, 0)    # Rojo
# Colores de Estado Climático
COLOR_ENV_FROST_EXTREME = (139, 0, 255) # Violeta
COLOR_ENV_FROST = (0, 0, 255)         # Azul
COLOR_ENV_VERY_COLD = (0, 100, 255)   # Azul sólido
COLOR_ENV_COLD = (0, 150, 150)        # Cian
COLOR_ENV_COOL = (0, 200, 100)        # Verde claro
COLOR_ENV_NICE = (0, 200, 0)          # Verde
COLOR_ENV_WARM = (255, 255, 0)        # Amarillo
COLOR_ENV_HOT = (255, 165, 0)         # Naranja
COLOR_ENV_EXTREME = (255, 0, 0)       # Rojo

# --- Lógica de Alertas y Comportamiento ---
# Tiempos de timeout para el estado del módulo exterior (en minutos)
EXTERIOR_TIMEOUT_WARN1 = 5
EXTERIOR_TIMEOUT_WARN2 = 10
EXTERIOR_TIMEOUT_OFFLINE = 15 # Considerado offline después de 15 min

# Nuevos umbrales de temperatura exterior, más granulares
UMBRAL_HELADA_EXTREMA_C = -5.0
UMBRAL_HELADA_C = 0.0
UMBRAL_MUY_FRIO_C = 10.0
UMBRAL_FRIO_C = 18.0
UMBRAL_FRESCO_C = 23.0
UMBRAL_OPTIMO_C = 26.0
UMBRAL_CALIDO_C = 30.0
UMBRAL_CALUROSO_C = 35.0
UMBRAL_CALOR_EXTREMO_C = 40.0

# --- UMBRALES DE ALERTA DEL SISTEMA ---
CPU_TEMP_WARN = 65.0
CPU_TEMP_DANGER = 75.0
CPU_USAGE_WARN = 70.0
CPU_USAGE_DANGER = 85.0
RAM_USAGE_WARN = 70.0
RAM_USAGE_DANGER = 85.0
WIFI_SIGNAL_WARN = 50.0
WIFI_SIGNAL_DANGER = 30.0

# --- Gateway a la Nube (ThingsBoard) ---
THINGSBOARD_HOST = 'thingsboard.cloud'  # O tu instancia de ThingsBoard

THINGSBOARD_PORT = 1883
THINGSBOARD_GATEWAY_TOKEN = '6ckjxmrdcedf2hh1vxir'

# --- Frecuencias de Actualización ---
CONSOLE_REFRESH_RATE_SECONDS = 10
LOCAL_SENSOR_READ_RATE_SECONDS = 60
MAIN_LOOP_SLEEP_SECONDS = 0.2 # Tiempo de refresco del bucle principal (para parpadeos)

# --- Configuración de Interfaz de Usuario ---
TFT_BACKLIGHT_TIMEOUT_SECONDS = 300 # 300 segundos = 5 minutos


# ---------------------------------------------------
UI_COLORS = {
    'bg': (15, 23, 42), 
    'primary': (6, 182, 212),
    'secondary': (245, 158, 11), 
    'accent': (139, 92, 246),
    'success': (16, 185, 129), 
    'danger': (239, 68, 68),
    'text': (241, 245, 249), 
    'text_secondary': (203, 213, 225),
    'card_bg': (30, 41, 59), 
    'border': (71, 85, 105)
}
# ---------------------------------------------------