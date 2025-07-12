# main.py - Cerebro de la Estación Meteorológica
# Versión: 3.1 - Versión completa y estable

import paho.mqtt.client as mqtt
import time
import json
import logging
from datetime import datetime, timedelta
from collections import deque
import psutil
from config import *  
from hardware_manager import HardwareManager
from logger_config import setup_logging
import subprocess

class WeatherStation:
    def __init__(self):
        """Inicializa la aplicación completa."""
        logger.info("--- Iniciando Servicio de Estación Meteorológica v3.1 ---")
        self.hw_manager = HardwareManager()
        
        self.data_store = {
        "interior": {
        "temperatura": None, "humedad": None, "presion": None,
        "cpu_temp": None, "ram_usage": None, "uptime": None, "wifi_signal": None},
        
        "exterior": {
            "temperatura": None, "humedad": None, "presion": None, 
            "estado": "Desconocido", "presion_tendencia": "---",
            "indice_calor": None},
        }
        self.stats_data = {
            "interior": {"temp_max": None, "temp_min": None},
            "exterior": {"temp_max": None, "temp_min": None}
        }
        self.last_stats_reset = time.time()
        self.pressure_history = deque(maxlen=18)
        self.temp_history = deque(maxlen=60)
        self.last_exterior_msg_time = None
        self.mqtt_local_connected = False
        self.blink_state = False
        self.current_page = 0
        self.last_button_press_time = 0
        self.last_activity_time = time.time() # <-- NUEVA LÍNEA. Se inicializa al arrancar.
        self.is_backlight_on = True 

        self.setup_mqtt_local()
        self.setup_mqtt_thingsboard()

    # --- Lógica de Estadísticas y Tendencias ---
    def update_stats(self, location, temp):
        if temp is None: return
        current_max = self.stats_data[location]["temp_max"]
        current_min = self.stats_data[location]["temp_min"]
        if current_max is None or temp > current_max: self.stats_data[location]["temp_max"] = temp
        if current_min is None or temp < current_min: self.stats_data[location]["temp_min"] = temp

    def check_and_reset_stats(self):
        if time.time() - self.last_stats_reset > 86400:
            logger.info("Reseteando estadísticas de 24 horas.")
            self.stats_data = {"interior": {"temp_max": None, "temp_min": None}, "exterior": {"temp_max": None, "temp_min": None}}
            self.last_stats_reset = time.time()

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

    def calculate_heat_index(self, T, RH):
        """
        Calcula el Índice de Calor usando la fórmula de la NOAA.
        T: Temperatura en grados Celsius.
        RH: Humedad Relativa en porcentaje (%).
        Devuelve el índice de calor en grados Celsius, o None si no es aplicable.
        """
        if T is None or RH is None:
            return None

# La fórmula solo se aplica bajo ciertas condiciones
        if T < 26.7 or RH < 40:
            return T # Por debajo de estos umbrales, el índice de calor es la propia temperatura

# --- Convertir a Fahrenheit para la fórmula ---
        T_f = (T * 9/5) + 32
        
# --- Fórmula de Steadman (versión simple) ---
        heat_index_f = 0.5 * (T_f + 61.0 + ((T_f - 68.0) * 1.2) + (RH * 0.094))
        
# --- Si es lo suficientemente alta, usar la fórmula de regresión completa ---
        if heat_index_f >= 80:
            c1 = -42.379
            c2 = 2.04901523
            c3 = 10.14333127
            c4 = -0.22475541
            c5 = -6.83783e-3
            c6 = -5.481717e-2
            c7 = 1.22874e-3
            c8 = 8.5282e-4
            c9 = -1.99e-6
            
            heat_index_f = (c1 +
                            (c2 * T_f) +
                            (c3 * RH) +
                            (c4 * T_f * RH) +
                            (c5 * T_f**2) +
                            (c6 * RH**2) +
                            (c7 * T_f**2 * RH) +
                            (c8 * T_f * RH**2) +
                            (c9 * T_f**2 * RH**2))
                            
# --- Convertir de nuevo a Celsius ---
        heat_index_c = (heat_index_f - 32) * 5/9
        
        return heat_index_c
#-------------------------------------------------------
    def get_uptime(self):
        """Obtiene el uptime del sistema y lo formatea."""
        try:
            # El comando 'uptime -p' devuelve un texto como "up 2 days, 14 hours, 32 minutes"
            output = subprocess.check_output(['uptime', '-p']).decode('utf-8').strip()
            # Quitamos el "up " del principio
            return output.replace("up ", "")
        except Exception as e:
            logger.error(f"No se pudo obtener el uptime: {e}")
            return "N/A"

    def get_wifi_signal(self):
        """Obtiene la fuerza de la señal WiFi en %."""
        try:
            # El comando 'iwconfig wlan0' da mucha información, buscamos la línea "Signal level"
            output = subprocess.check_output(['iwconfig', 'wlan0']).decode('utf-8')
            for line in output.split('\n'):
                if 'Signal level' in line:
                    # La línea es algo como "Signal level=-50 dBm"
                    level_dbm = int(line.split('Signal level=')[1].split(' dBm')[0])
                    # Convertimos dBm a un porcentaje aproximado (0-100)
                    # -30 dBm es excelente (100%), -90 dBm es el límite (0%)
                    # Es una aproximación, pero muy útil visualmente.
                    percentage = max(0, min(100, 2 * (level_dbm + 100)))
                    return percentage
            return None
        except Exception as e:
            logger.error(f"No se pudo obtener la señal WiFi: {e}")
            return None
#-------------------------------------------------------
# --- Configuración y Callbacks de MQTT Local ---
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
            
            # Actualizamos la marca de tiempo de la última comunicación
            self.last_exterior_msg_time = datetime.now()

            # 1. Procesar el mensaje de estado
            if sensor_type == "estado":
                self.data_store["exterior"]["estado"] = payload
                return # No hay más que hacer si es un mensaje de estado

            # 2. Procesar mensajes de telemetría (temp, hum, pres)
            if sensor_type in self.data_store["exterior"]:
                value = float(payload)
                
                # Guardar el valor en nuestro almacén de datos
                self.data_store["exterior"][sensor_type] = value
                
                # Enviar el dato individual a ThingsBoard
                self.forward_to_thingsboard("Estacion Exterior", {sensor_type: value})

                # 3. Realizar acciones específicas según el tipo de sensor
                if sensor_type == "temperatura":
                    self.update_stats("exterior", value)
                    self.temp_history.append(value)
                    
                elif sensor_type == "humedad":
                    # Si llega la humedad, recalculamos el índice de calor
                    # ya que necesitamos la temperatura y la humedad actuales.
                    temp = self.data_store["exterior"].get("temperatura")
                    hum = self.data_store["exterior"].get("humedad")
                    if temp is not None and hum is not None:
                        heat_index = self.calculate_heat_index(temp, hum)
                        if heat_index is not None:
                            self.data_store["exterior"]["indice_calor"] = round(heat_index, 1)
                            # Enviamos el nuevo dato calculado a ThingsBoard
                            self.forward_to_thingsboard("Estacion Exterior", {"indice_calor": self.data_store["exterior"]["indice_calor"]})
                
                elif sensor_type == "presion":
                    self.pressure_history.append(value)
                    self.calculate_pressure_trend()
                    
        except Exception as e:
            logger.error(f"Error procesando mensaje MQTT: {e}", exc_info=True)
#---------------------------------------------------------------------

    # --- Configuración y Callbacks de ThingsBoard ---
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

    def on_mqtt_tb_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info("Conexión exitosa a ThingsBoard.")
        else:
            logger.error(f"Fallo al conectar a ThingsBoard, código: {reason_code}")

    def on_mqtt_tb_disconnect(self, client, userdata, *args):
        logger.warning(f"Desconectado de ThingsBoard.")

    def forward_to_thingsboard(self, device_name, data):
        if not self.tb_client.is_connected(): return
        timestamp = int(time.time() * 1000)
        payload = {device_name: [{"ts": timestamp, "values": data}]}
        self.tb_client.publish('v1/gateway/telemetry', json.dumps(payload))
        logger.info(f"Datos de '{device_name}' reenviados a ThingsBoard.")

    # --- Tareas Periódicas del Sistema ---
    def task_read_local_sensor(self):
        logger.info("Iniciando lectura del sensor local...")
        local_data = self.hw_manager.read_local_bme280()
        if local_data:
            logger.info(f"Lectura local exitosa: T={local_data['temperatura']:.1f}C")
            self.data_store["interior"]["temperatura"] = round(local_data["temperatura"], 2)
            self.data_store["interior"]["humedad"] = round(local_data["humedad"], 2)
            self.data_store["interior"]["presion"] = round(local_data["presion"], 2)
            telemetry_to_forward = {k: v for k, v in self.data_store["interior"].items()}
            self.forward_to_thingsboard("Estacion Interior", telemetry_to_forward)
            self.update_stats("interior", self.data_store["interior"]["temperatura"])
        else:
            logger.error("Fallo al leer el sensor BME280 local.")

        try:
                self.data_store["interior"]["cpu_temp"] = psutil.sensors_temperatures()['cpu_thermal'][0].current
                self.data_store["interior"]["ram_usage"] = psutil.virtual_memory().percent
                self.data_store["interior"]["uptime"] = self.get_uptime()
                self.data_store["interior"]["wifi_signal"] = self.get_wifi_signal()
                logger.info(f"Lectura sistema: CPU={...}, RAM={...}, WiFi={self.data_store['interior']['wifi_signal']}%")
        except Exception as e:
                logger.error(f"Fallo al leer datos del sistema: {e}")
        if local_data:
                telemetry_to_forward = {k: v for k, v in self.data_store["interior"].items() if v is not None}
                self.forward_to_thingsboard("Estacion Interior", telemetry_to_forward)
            
        self.update_stats("interior", self.data_store["interior"]["temperatura"])
        
            

    def task_update_leds_and_alerts(self):
        is_exterior_offline = True
        if self.last_exterior_msg_time:
            if (datetime.now() - self.last_exterior_msg_time) <= timedelta(minutes=EXTERIOR_TIMEOUT_MINUTES):
                is_exterior_offline = False
        system_color = COLOR_SYS_OK
        if not self.mqtt_local_connected: system_color = COLOR_SYS_MQTT_DISC
        elif is_exterior_offline: system_color = COLOR_SYS_EXT_OFFLINE if self.blink_state else COLOR_OFF
        
        environment_color = COLOR_OFF
        temp_ext = self.data_store["exterior"]["temperatura"]
        if temp_ext is not None:
            if temp_ext < UMBRAL_HELADA_C: environment_color = COLOR_ENV_FROST if self.blink_state else (0, 0, 50)
            elif temp_ext >= UMBRAL_CALOR_EXTREMO_C: environment_color = COLOR_ENV_HOT if self.blink_state else COLOR_OFF
            elif temp_ext > UMBRAL_CALIDO_C: environment_color = COLOR_ENV_WARM
            elif temp_ext < UMBRAL_FRIO_C: environment_color = COLOR_ENV_COLD
            else: environment_color = COLOR_ENV_NICE
        self.hw_manager.update_leds(system_color, environment_color)

    def task_draw_display(self):
        """Decide qué página dibujar en la TFT."""
        if self.current_page == 0:
            # Llama a la función para dibujar la página principal
            self.hw_manager.draw_page_main(self.data_store)
        elif self.current_page == 1:
            # Llama a la función para dibujar la página de estadísticas
            # Le pasamos tanto las stats de 24h como los datos del sistema (que están en 'interior')
            self.hw_manager.draw_page_stats(self.stats_data, self.data_store["interior"])

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