# receptor.py - v16 - Versión Estable con LEDs y Dashboard de Consola

import paho.mqtt.client as mqtt
import time, json, threading
from datetime import datetime

# Importar nuestros propios módulos
import config
import hardware_manager

# === ESTRUCTURA DE DATOS CENTRAL ===
estado_sistema = {
    "exterior": {"temperatura": None, "humedad": None, "presion": None, "estado": "offline", "ultimo_update": 0},
    "interior": {"temperatura": None, "humedad": None, "presion": None},
    "mqtt_local":{"conectado": False},
    "mqtt_tb":{"conectado": False},
    "alertas":{"helada": False, "calor": False, "desconexion_ext": False}
}
class Colores: RESET='\033[0m'; BOLD='\033[1m'; CYAN='\033[96m'; GREEN='\033[92m'; YELLOW='\033[93m'; RED='\033[91m'; MAGENTA='\033[95m'

# === CALLBACKS Y FUNCIONES ===
def on_local_connect(client, userdata, flags, rc, properties=None):
    if rc == 0: print(f"{Colores.GREEN}MQTT Local: Conectado.{Colores.RESET}"); client.subscribe(config.TOPIC_SUBSCRIBE); estado_sistema["mqtt_local"]["conectado"] = True
    else: print(f"{Colores.RED}MQTT Local: Fallo, código: {rc}{Colores.RESET}"); estado_sistema["mqtt_local"]["conectado"] = False
def on_local_disconnect(client, userdata, rc, properties=None):
    print(f"{Colores.YELLOW}MQTT Local: Desconectado.{Colores.RESET}"); estado_sistema["mqtt_local"]["conectado"] = False
def on_tb_connect(client, userdata, flags, rc, properties=None):
    if rc == 0: print(f"{Colores.GREEN}ThingsBoard: Conectado.{Colores.RESET}"); estado_sistema["mqtt_tb"]["conectado"] = True
    else: print(f"{Colores.RED}ThingsBoard: Fallo, código: {rc}{Colores.RESET}"); estado_sistema["mqtt_tb"]["conectado"] = False
def on_tb_disconnect(client, userdata, rc, properties=None):
    print(f"{Colores.YELLOW}ThingsBoard: Desconectado.{Colores.RESET}"); estado_sistema["mqtt_tb"]["conectado"] = False
def on_local_message(client, userdata, msg):
    tb_client = userdata['tb_client']
    topic = msg.topic; payload = msg.payload.decode('utf-8'); telemetry = {}
    try:
        valor = float(payload)
        if "temperatura" in topic: estado_sistema["exterior"]["temperatura"] = valor; telemetry['temperatura_exterior'] = valor
        elif "humedad" in topic: estado_sistema["exterior"]["humedad"] = valor; telemetry['humedad_exterior'] = valor
        elif "presion" in topic: estado_sistema["exterior"]["presion"] = valor; telemetry['presion_exterior'] = valor
    except ValueError:
        if "estado" in topic: estado_sistema["exterior"]["estado"] = payload; telemetry['estado_exterior'] = payload
    estado_sistema["exterior"]["ultimo_update"] = time.time()
    if telemetry and tb_client.is_connected(): tb_client.publish('v1/devices/me/telemetry', json.dumps(telemetry))

def bucle_principal(tb_client):
    last_local_read = 0; last_dashboard_update = 0
    while True:
        now = time.time()
        if (now - last_local_read) > config.READ_INTERVAL_SEC:
            last_local_read = now
            datos_locales = hardware_manager.leer_sensor_local()
            if datos_locales:
                estado_sistema["interior"].update(datos_locales)
                telemetry_int = {'temperatura_interior': datos_locales['temperatura'], 'humedad_interior': datos_locales['humedad']}
                if tb_client.is_connected(): tb_client.publish('v1/devices/me/telemetry', json.dumps(telemetry_int))
        
        estado_sistema["alertas"]["desconexion_ext"] = (now - estado_sistema["exterior"]["ultimo_update"]) > config.TIMEOUT_ALERTA_DESCONEXION_SEC if estado_sistema["exterior"]["ultimo_update"] != 0 else False
        if estado_sistema["exterior"]["temperatura"] is not None:
            estado_sistema["alertas"]["helada"] = estado_sistema["exterior"]["temperatura"] < config.UMBRAL_ALERTA_HELADA
            estado_sistema["alertas"]["calor"] = estado_sistema["exterior"]["temperatura"] > config.UMBRAL_ALERTA_CALOR
        
        hardware_manager.gestionar_leds(estado_sistema)

        if (now - last_dashboard_update) > config.DASHBOARD_REFRESH_SEC:
            last_dashboard_update = now
            mostrar_dashboard_consola()
            
        time.sleep(0.2)

def mostrar_dashboard_consola():
    print("\033[2J\033[H", end="") # Limpiar consola
    # ... (el resto de la función es la misma que ya tenías)

# === ARRANQUE DEL SISTEMA ===
if __name__ == "__main__":
    hardware_manager.inicializar_todo()
    
    cliente_tb = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, config.CLIENT_ID_TB); cliente_tb.username_pw_set(config.THINGSBOARD_ACCESS_TOKEN)
    cliente_tb.on_connect = on_tb_connect; cliente_tb.on_disconnect = on_tb_disconnect
    
    cliente_local = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, config.CLIENT_ID_LOCAL); cliente_local.on_connect = on_local_connect
    cliente_local.on_disconnect = on_local_disconnect
    cliente_local.user_data_set({'tb_client': cliente_tb}); cliente_local.on_message = on_local_message
    
    print("Conectando a brokers..."); cliente_tb.connect_async(config.THINGSBOARD_HOST, config.THINGSBOARD_PORT, 60); cliente_local.connect_async(config.MQTT_BROKER_IP, config.MQTT_PORT, 60)
    cliente_tb.loop_start(); cliente_local.loop_start()

    try:
        bucle_principal(cliente_tb)
    except KeyboardInterrupt:
        print("\nCerrando programa...")
    finally:
        hardware_manager.limpiar_gpio()
        cliente_local.loop_stop(); cliente_local.disconnect()
        cliente_tb.loop_stop(); cliente_tb.disconnect()
        print("Recursos liberados.")