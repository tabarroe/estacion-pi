# main.py - Versión 4.1 - Funcionalidad Completa

import paho.mqtt.client as mqtt
import time
import json
import logging
from datetime import datetime, timedelta
from collections import deque
import psutil
import subprocess
import math

from config import *
from hardware_manager import HardwareManager
from logger_config import setup_logging

class WeatherStation:
    def __init__(self):
        logger.info("--- Iniciando Estación Meteorológica v4.1 ---")
        self.hw_manager = HardwareManager()
        
        # Almacenes de datos
#---------------------------------------------------------------------
        self.data_store = {
            "interior": {
                "temperatura": None, "humedad": None, "presion": None, 
                "cpu_temp": None, "ram_usage": None, "uptime": None, 
                "wifi_signal": None, "temp_trend": "→",
                "dew_point": None
            },
            "exterior": {
                "temperatura": None, "humedad": None, "presion": None, 
                "estado": "Desconocido", "presion_tendencia": "---",
                "indice_calor": None, "temp_trend": "→",
                "dew_point": None, "temp_sum": 0.0, "reading_count": 0
            },
        }
#---------------------------------------------------------------------
        self.stats_data = {"interior": {"temp_max": None, "temp_min": None}, "exterior": {"temp_max": None, "temp_min": None}}
        self.last_stats_reset = time.time()
        self.pressure_history = deque(maxlen=30)
        self.temp_history_ext = deque(maxlen=60)
        self.temp_history_int = deque(maxlen=30)
        
        # Almacén para tendencia de presión y temperatura
        self.pressure_history = deque(maxlen=30)
        self.temp_history_ext = deque(maxlen=60)
        self.temp_history_int = deque(maxlen=30)
        # ---  ALARMA DE CAMBIO BRUSCO ---
        # Guardaremos tuplas de (timestamp, temperatura)
        self.temp_change_history = deque(maxlen=10) # Historial para los últimos ~10 minutos
        self.active_alert_change = False
        
        # Variables de estado
        self.last_exterior_msg_time = None
        self.mqtt_local_connected = False
        self.blink_state = False
        self.current_page = 0
        self.last_button_press_time = 0
        self.last_activity_time = time.time()
        self.is_backlight_on = True
        self.active_alert = None
        
        self.setup_mqtt_local()
        self.setup_mqtt_thingsboard()

    # --- Funciones de Cálculo ---
    def update_stats(self, location, temp):
        if temp is None: return
        current_max = self.stats_data[location]["temp_max"]
        current_min = self.stats_data[location]["temp_min"]
        if current_max is None or temp > current_max: self.stats_data[location]["temp_max"] = temp
        if current_min is None or temp < current_min: self.stats_data[location]["temp_min"] = temp
        
        # --- NUEVA LÓGICA PARA EL PROMEDIO ---
        self.stats_data[location]["temp_sum"] = self.stats_data[location].get("temp_sum", 0.0) + temp
        self.stats_data[location]["reading_count"] = self.stats_data[location].get("reading_count", 0) + 1
        # ------------------------------------

    def check_and_reset_stats(self):
        if time.time() - self.last_stats_reset > 86400:
            logger.info("Reseteando estadísticas de 24 horas.")
            self.stats_data = {"interior": {"temp_max": None, "temp_min": None}, "exterior": {"temp_max": None, "temp_min": None, "temp_sum": 0.0, "reading_count": 0}}
            self.last_stats_reset = time.time()
#------------------------------------------------------------
    def check_rapid_temp_change(self):
        """Comprueba si ha habido un cambio de temperatura brusco."""
        self.active_alert_change = False # Reseteamos la alerta en cada comprobación
        
        # Necesitamos al menos 10 minutos de datos para una comparación fiable
        if len(self.temp_change_history) < 10:
            return

        # Obtenemos la lectura más reciente y una de hace ~10 minutos
        now_ts, now_temp = self.temp_change_history[-1]
        past_ts, past_temp = self.temp_change_history[0]
        
        # Si los datos son muy viejos, no hacemos nada
        if now_ts - past_ts > 720: # 12 minutos, un margen de seguridad
            return
        
        temp_diff = abs(now_temp - past_temp)
        
        # UMBRAL DE ALERTA: más de 2 grados de cambio
        if temp_diff > 2.0:
            logger.warning(f"¡ALERTA DE CAMBIO BRUSCO DE TEMPERATURA! Diferencia: {temp_diff:.1f}C en ~10 min.")
            self.active_alert_change = True
#------------------------------------------------------------
    def calculate_pressure_trend(self):
        if len(self.pressure_history) < 10: self.data_store["exterior"]["presion_tendencia"] = "---"; return
        midpoint = len(self.pressure_history) // 2
        first_half_avg = sum(list(self.pressure_history)[:midpoint]) / midpoint
        second_half_avg = sum(list(self.pressure_history)[midpoint:]) / (len(self.pressure_history) - midpoint)
        diff = second_half_avg - first_half_avg
        trend = "→"
        if diff > 0.5: trend = "↑"
        elif diff < -0.5: trend = "↓"
        self.data_store["exterior"]["presion_tendencia"] = trend

#---------------------------------------------------------------------
    def calculate_heat_index(self, temp_c, humidity):
        """Calcula el índice de calor usando la fórmula de Steadman."""
        # La fórmula funciona mejor con temperaturas más altas
        if temp_c < 26.7:
            return None

        temp_f = temp_c * 1.8 + 32
        rh = float(humidity)
        
        # Fórmula simple, funciona bien para la mayoría de los casos
        heat_index_f = -42.379 + 2.04901523 * temp_f + 10.14333127 * rh - 0.22475541 * temp_f * rh \
                       - 0.00683783 * temp_f**2 - 0.05481717 * rh**2 + 0.00122874 * temp_f**2 * rh \
                       + 0.00085282 * temp_f * rh**2 - 0.00000199 * temp_f**2 * rh**2
                       
        # Convertir de nuevo a Celsius
        heat_index_c = (heat_index_f - 32) * 5/9
        return heat_index_c
#---------------------------------------------------------------------
    def calculate_temp_trend(self, location):
        history = self.temp_history_ext if location == "exterior" else self.temp_history_int
        if len(history) < 10: self.data_store[location]["temp_trend"] = "→"; return
        midpoint = len(history) // 2
        first_half_avg = sum(list(history)[:midpoint]) / midpoint
        second_half_avg = sum(list(history)[midpoint:]) / (len(history) - midpoint)
        diff = second_half_avg - first_half_avg
        trend = "→";
        if diff > 0.2: trend = "↗"
        elif diff < -0.2: trend = "↘"
        self.data_store[location]["temp_trend"] = trend
#---------------------------------------------------------------------
    def calculate_dew_point(self, temp_c, humidity):
        """Calcula el punto de rocío usando la fórmula de Magnus-Tetens."""
        if temp_c is None or humidity is None:
            return None
        a = 17.27
        b = 237.7
        gamma = (a * temp_c) / (b + temp_c) + math.log(humidity / 100.0)
        dew_point = (b * gamma) / (a - gamma)
        return dew_point
#---------------------------------------------------------------------
    # --- Funciones de Sistema ---
    def get_uptime(self):
        try:
            output = subprocess.check_output(['uptime', '-p']).decode('utf-8').strip()
            return output.replace("up ", "")
        except Exception as e:
            logger.error(f"No se pudo obtener el uptime: {e}"); return "N/A"
    def get_wifi_signal(self):
        try:
            output = subprocess.check_output(['iwconfig', 'wlan0']).decode('utf-8')
            for line in output.split('\n'):
                if 'Signal level' in line:
                    level_dbm = int(line.split('Signal level=')[1].split(' dBm')[0])
                    percentage = max(0, min(100, 2 * (level_dbm + 100)))
                    return percentage
            return None
        except Exception: return None

    # --- Lógica MQTT ---
    def setup_mqtt_local(self):
        local_client_id = f"pi_zero_gateway-{int(time.time())}"
        self.mqtt_local_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=local_client_id)
        self.mqtt_local_client.on_connect = self.on_mqtt_local_connect
        self.mqtt_local_client.on_message = self.on_mqtt_local_message
        self.mqtt_local_client.on_disconnect = self.on_mqtt_local_disconnect
        try:
            logger.info(f"Conectando al broker MQTT local en {MQTT_BROKER_IP}...")
            self.mqtt_local_client.connect(MQTT_BROKER_IP, MQTT_PORT, 60)
        except Exception as e:
            logger.error(f"No se pudo conectar al broker MQTT local: {e}", exc_info=True)

    def on_mqtt_local_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info("Conexión exitosa al Broker MQTT local.")
            client.subscribe(MQTT_TOPIC_EXTERIOR_LISTEN)
            self.mqtt_local_connected = True
        else:
            logger.error(f"Fallo al conectar al MQTT local, código: {reason_code}")

    def on_mqtt_local_disconnect(self, client, userdata, *args):
        logger.warning(f"Desconectado del Broker MQTT local.")
        self.mqtt_local_connected = False


#---------------------------------------------------------------------
    def on_mqtt_local_message(self, client, userdata, msg):
        try:
            topic_parts = msg.topic.split('/')
            sensor_type = topic_parts[-1]
            payload = msg.payload.decode('utf-8')
            self.last_exterior_msg_time = datetime.now()
            self.last_activity_time = time.time()

            if sensor_type == "estado":
                self.data_store["exterior"]["estado"] = payload; return
            
            if sensor_type in self.data_store["exterior"]:
                value = float(payload)
                self.data_store["exterior"][sensor_type] = value
                self.forward_to_thingsboard("Estacion Exterior", {sensor_type: value})
                
                if sensor_type == "temperatura":
                    self.update_stats("exterior", value)
                    self.temp_history_ext.append(value)
                    self.calculate_temp_trend("exterior")
                    self.temp_change_history.append((time.time(), value))
                    self.check_rapid_temp_change()
                    
                elif sensor_type == "humedad":
                    temp = self.data_store["exterior"].get("temperatura")
                    hum = self.data_store["exterior"].get("humedad")
                    if temp is not None and hum is not None:
                        dew_point_ext = self.calculate_dew_point(temp, hum)
                        heat_index = self.calculate_heat_index(temp, hum)
                        if heat_index is not None:
                            self.data_store["exterior"]["dew_point"] = round(dew_point_ext, 1)
                            self.forward_to_thingsboard("Estacion Exterior", {"dew_point": self.data_store["exterior"]["dew_point"]})
                                        
                            self.data_store["exterior"]["indice_calor"] = round(heat_index, 1)
                            self.forward_to_thingsboard("Estacion Exterior", {"indice_calor": self.data_store["exterior"]["indice_calor"]})
                elif sensor_type == "presion":
                    self.pressure_history.append(value)
                    self.calculate_pressure_trend()
        except Exception as e:
            logger.error(f"Error procesando mensaje MQTT: {e}", exc_info=True)
#------------------------------------------------------------------------

    def setup_mqtt_thingsboard(self):
        tb_client_id = f"rpi_gateway_tb-{int(time.time())}"
        self.tb_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=tb_client_id)
        self.tb_client.username_pw_set(username=THINGSBOARD_GATEWAY_TOKEN, password=None)
        self.tb_client.on_connect = self.on_mqtt_tb_connect
        self.tb_client.on_disconnect = self.on_mqtt_tb_disconnect
        try:
            logger.info(f"Conectando al gateway de ThingsBoard en {THINGSBOARD_HOST}...")
            self.tb_client.connect(THINGSBOARD_HOST, THINGSBOARD_PORT, 60)
        except Exception as e:
            logger.error(f"No se pudo conectar a ThingsBoard: {e}", exc_info=True)
 #---------------------------------------------------
 
    def on_mqtt_tb_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info("Conexión exitosa a ThingsBoard.")
        else:
            logger.error(f"Fallo al conectar a ThingsBoard, código: {reason_code}")
 #---------------------------------------------------
 
    def on_mqtt_tb_disconnect(self, client, userdata, *args):
        logger.warning(f"Desconectado de ThingsBoard.")
 #---------------------------------------------------
 
    def forward_to_thingsboard(self, device_name, data):
        if not self.tb_client.is_connected(): return
        timestamp = int(time.time() * 1000)
        payload = {device_name: [{"ts": timestamp, "values": data}]}
        self.tb_client.publish('v1/gateway/telemetry', json.dumps(payload))
        logger.info(f"Datos de '{device_name}' reenviados a ThingsBoard.")
 #---------------------------------------------------
 
    # --- Tareas Periódicas ---
    def task_read_local_sensor(self):
        logger.info("Iniciando lectura de sensores y sistema local...")
        local_data = self.hw_manager.read_local_bme280()
        if local_data:
            self.data_store["interior"]["temperatura"] = round(local_data["temperatura"], 2)
            self.data_store["interior"]["humedad"] = round(local_data["humedad"], 2)
            self.data_store["interior"]["presion"] = round(local_data["presion"], 2)
        dew_point_in = self.calculate_dew_point(local_data["temperatura"], local_data["humedad"])
        if dew_point_in is not None:
            self.data_store["interior"]["dew_point"] = round(dew_point_in, 1)
            
            self.temp_history_int.append(local_data["temperatura"])
            self.calculate_temp_trend("interior")
            self.update_stats("interior", local_data["temperatura"])
        else:
            logger.error("Fallo al leer el sensor BME280 local.")

        try:
            self.data_store["interior"]["cpu_temp"] = psutil.sensors_temperatures()['cpu_thermal'][0].current
            self.data_store["interior"]["ram_usage"] = psutil.virtual_memory().percent
            self.data_store["interior"]["uptime"] = self.get_uptime()
            self.data_store["interior"]["wifi_signal"] = self.get_wifi_signal()
        except Exception as e:
            logger.error(f"Fallo al leer datos del sistema: {e}")

        telemetry_to_forward = {k: v for k, v in self.data_store["interior"].items() if v is not None}
        self.forward_to_thingsboard("Estacion Interior", telemetry_to_forward)
 #---------------------------------------------------
 
    def task_update_leds_and_alerts(self):
        system_color = COLOR_OFF
        environment_color = COLOR_GRIS # Por defecto, gris si no hay datos
        
        # --- LÓGICA DEL LED 0 - ESTADO DEL SISTEMA ---
        if self.last_exterior_msg_time:
            minutes_since_last_msg = (datetime.now() - self.last_exterior_msg_time).total_seconds() / 60
            if minutes_since_last_msg < EXTERIOR_TIMEOUT_WARN1:
                system_color = COLOR_SYS_OK # Verde
            elif minutes_since_last_msg < EXTERIOR_TIMEOUT_WARN2:
                system_color = COLOR_SYS_WARN1 # Amarillo
            elif minutes_since_last_msg < EXTERIOR_TIMEOUT_OFFLINE:
                system_color = COLOR_SYS_WARN2 # Naranja
            else:
                system_color = COLOR_SYS_OFFLINE # Rojo
        else:
            # Si nunca hemos recibido un mensaje, está offline
            system_color = COLOR_SYS_OFFLINE # Rojo

        # --- LÓGICA DEL LED 1 - ESTADO CLIMÁTICO ---
        temp_ext = self.data_store["exterior"]["temperatura"]
        
        if temp_ext is not None:
            if temp_ext < UMBRAL_HELADA_EXTREMA_C:
                # Violeta parpadeante
                environment_color = COLOR_ENV_FROST_EXTREME if self.blink_state else COLOR_OFF
            elif temp_ext < UMBRAL_HELADA_C:
                # Azul parpadeante
                environment_color = COLOR_ENV_FROST if self.blink_state else COLOR_OFF
            elif temp_ext < UMBRAL_MUY_FRIO_C:
                environment_color = COLOR_ENV_VERY_COLD # Azul sólido
            elif temp_ext < UMBRAL_FRIO_C:
                environment_color = COLOR_ENV_COLD # Cian sólido
            elif temp_ext < UMBRAL_FRESCO_C:
                environment_color = COLOR_ENV_COOL # Verde claro
            elif temp_ext < UMBRAL_OPTIMO_C:
                environment_color = COLOR_ENV_NICE # Verde sólido
            elif temp_ext < UMBRAL_CALIDO_C:
                environment_color = COLOR_ENV_WARM # Amarillo sólido
            elif temp_ext < UMBRAL_CALUROSO_C:
                environment_color = COLOR_ENV_HOT # Naranja sólido
            else: # Mayor o igual a UMBRAL_CALUROSO_C (35°C)
                # Rojo parpadeante
                environment_color = COLOR_ENV_EXTREME if self.blink_state else COLOR_OFF

        # --- LÓGICA DE ALERTAS PARA LA PANTALLA ---
        previous_alert = self.active_alert
        self.active_alert = None
        if temp_ext is not None:
            if temp_ext < UMBRAL_HELADA_C: self.active_alert = "HELADA"
            elif temp_ext >= UMBRAL_CALOR_EXTREMO_C: self.active_alert = "CALOR_EXTREMO"
        
        if self.active_alert != previous_alert:
            logger.info(f"¡Cambio de estado de alerta! Nueva alerta: {self.active_alert}. Forzando redibujado.")
            self.task_draw_display()
        
        # --- ACTUALIZACIÓN FINAL DE LOS LEDS ---
        self.hw_manager.update_leds(system_color, environment_color)
#-------------------------------------------------------------------------
    
    def task_draw_display(self):
        """Decide qué página dibujar en la TFT."""
        if not self.is_backlight_on: return

        # --- CONSTRUIR EL DICCIONARIO DE ESTADO ---
        minutes_ago = None
        if self.last_exterior_msg_time:
            minutes_ago = (datetime.now() - self.last_exterior_msg_time).total_seconds() / 60

        status_info = {
            "exterior_online": minutes_ago is not None and minutes_ago < EXTERIOR_TIMEOUT_OFFLINE,
            "minutes_ago": minutes_ago
        }
        # -----------------------------------------

        if self.current_page == 0:
            self.hw_manager.draw_page_main(self.data_store, self.temp_history_ext, status_info, self.active_alert, self.blink_state)
        elif self.current_page == 1:
            self.hw_manager.draw_page_stats(self.stats_data, self.data_store["interior"])
#-------------------------------------------------------------------------------

    # --- Bucle Principal ---
    def run(self):
        self.mqtt_local_client.loop_start()
        self.tb_client.loop_start()

        last_local_read = 0
        last_display_draw = 0
        last_blink_toggle = 0

        try:
            while True:
                now = time.time()
                
                if self.hw_manager.is_button_pressed() and (now - self.last_button_press_time > 0.5):
                    
                    self.last_activity_time = now # Actualizamos el tiempo de la última actividad
                    if not self.is_backlight_on:
                        self.hw_manager.set_backlight(True)
                        self.is_backlight_on = True
                        logger.info("Botón presionado. Encendiendo pantalla.")
                        # Hacemos una pausa para que el usuario vea que la pantalla se ha encendido
                        # antes de procesar el cambio de página.
                        time.sleep(0.3)
                    
                    logger.info(f"Toque detectado. Cambiando a página {1 - self.current_page}")
                    self.current_page = 1 - self.current_page
                    self.task_draw_display()
                    self.last_button_press_time = now
                    
                    # --- LÓGICA DE GESTIÓN DE LA PANTALLA (MODIFICADA) ---
                    current_hour = datetime.now().hour
                    
                    # Comprobar si estamos en horario nocturno
                    is_night = False
                    if NIGHT_MODE_ENABLED:
                        if NIGHT_MODE_START_HOUR > NIGHT_MODE_END_HOUR: # Caso nocturno que cruza la medianoche (ej. 22:00 a 07:00)
                            if current_hour >= NIGHT_MODE_START_HOUR or current_hour < NIGHT_MODE_END_HOUR:
                                is_night = True
                        else: # Caso diurno (ej. 09:00 a 18:00)
                            if NIGHT_MODE_START_HOUR <= current_hour < NIGHT_MODE_END_HOUR:
                                is_night = True
                    
                    # Decidir si la pantalla debe estar encendida
                    # Condición 1: El backlight ya está encendido y no ha pasado el timeout de inactividad
                    should_be_on = self.is_backlight_on and (now - self.last_activity_time < TFT_BACKLIGHT_TIMEOUT_SECONDS)
                    
                    # Condición 2: Si es de día, forzamos que esté encendida (ignorando el timeout)
                    #if not is_night:
                    #    should_be_on = True

                    # Aplicar el cambio de estado si es necesario
                    if self.is_backlight_on != should_be_on:
                        logger.info(f"Cambiando estado del backlight a: {'ON' if should_be_on else 'OFF'}")
                        self.hw_manager.set_backlight(should_be_on)
                        self.is_backlight_on = should_be_on
    # --------------------------------------------------------- 
                    
                    

                if self.is_backlight_on and (now - self.last_activity_time > TFT_BACKLIGHT_TIMEOUT_SECONDS):
                    logger.info("Inactividad detectada. Apagando luz de fondo de la pantalla.")
                    self.hw_manager.set_backlight(False)
                    self.is_backlight_on = False
                                
                
                if now - last_local_read >= LOCAL_SENSOR_READ_RATE_SECONDS:
                    self.task_read_local_sensor()
                    last_local_read = now
                
                if now - last_blink_toggle >= 0.5:
                    self.blink_state = not self.blink_state
                    last_blink_toggle = now
                self.task_update_leds_and_alerts()

                if now - last_display_draw >= CONSOLE_REFRESH_RATE_SECONDS:
                    self.task_draw_display()
                    last_display_draw = now
                
                self.check_and_reset_stats()
                time.sleep(MAIN_LOOP_SLEEP_SECONDS)

        except KeyboardInterrupt:
            logger.info("Cerrando aplicación por interrupción de teclado...")
        finally:
            self.mqtt_local_client.loop_stop()
            self.tb_client.loop_stop()
            self.hw_manager.cleanup()
            logger.info("Aplicación cerrada limpiamente.")

# --- INICIALIZACIÓN DEL LOGGER Y DEL PROGRAMA ---
logger = setup_logging()

if __name__ == "__main__":
    station = WeatherStation()
    station.run()