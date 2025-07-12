# hardware_manager.py - Versión Final y Corregida

import threading
import logging
import time
import RPi.GPIO as GPIO
import board
import neopixel
import adafruit_bme280.basic as adafruit_bme280
from luma.core.interface.serial import spi
from luma.lcd.device import ili9341
from PIL import Image, ImageDraw, ImageFont, ImageOps
import os

from config import *

logger = logging.getLogger(__name__)
class HardwareManager:
    def __init__(self):
        self._lock = threading.Lock()
        
        # Configuración única de GPIO
        GPIO.setmode(GPIO.BCM)
        
        # Cargar los iconos desde el disco duro UNA SOLA VEZ
        self.icons = self._load_icons()
        # Posibles valores: None, "HELADA", "CALOR_EXTREMO"
        self.active_alert = None
        # Inicializar los componentes
        self._init_tft()
        self._init_neopixels()
        self._init_bme280()
        self._init_button()
        
        logger.info("Hardware Manager completamente inicializado.")

    def _init_tft(self):
        self.tft_device = None
        try:
            GPIO.setup(PIN_TFT_LED, GPIO.OUT)
            GPIO.output(PIN_TFT_LED, GPIO.HIGH)
            serial = spi(port=0, device=0, gpio_DC=PIN_TFT_DC, gpio_RST=PIN_TFT_RST, gpio=GPIO)
            self.tft_device = ili9341(serial, width=320, height=240)
            font_path_bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            font_path_regular = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            
            self.font_large = ImageFont.truetype(font_path_bold, 25) # Tamaño grande para datos
            self.font_medium = ImageFont.truetype(font_path_regular, 12) # Para títulos y datos secundarios
            self.font_small = ImageFont.truetype(font_path_regular, 10)  # Para la barra de estado
            logger.info("Fuentes DejaVu cargadas correctamente.")
        except IOError:
            logger.error("Fallo crítico: No se encontraron las fuentes DejaVu. Usando fuentes por defecto.")

    def _init_neopixels(self):
        self.pixels = None
        try:
            pin_obj = getattr(board, f"D{PIN_NEOPIXEL}")
            self.pixels = neopixel.NeoPixel(
                pin_obj, NEOPIXEL_COUNT, brightness=NEOPIXEL_BRIGHTNESS, auto_write=False
            )
            self.pixels.fill(COLOR_OFF)
            self.pixels.show()
            logging.info(f"NeoPixels en pin {PIN_NEOPIXEL} inicializados.")
        except Exception as e:
            logging.error(f"ERROR al inicializar NeoPixels: {e}")

    def _init_bme280(self):
        self.bme280 = None
        try:
            self.i2c = board.I2C()
            self.bme280 = adafruit_bme280.Adafruit_BME280_I2C(self.i2c, address=0x76)
            logging.info("Sensor BME280 inicializado.")
        except Exception as e:
            logging.error(f"ERROR al inicializar BME280: {e}")

    def _load_icons(self):
        """Carga todos los iconos desde la carpeta /icons."""
        logger.info("Cargando iconos...")
        icons = {}
        icon_path = "icons"
        icon_files = {
            "casa": "casa.png", "exterior": "exterior.png",
            "temp": "termometro.png", "hum": "humedad.png", "pres": "presion.png", "helada": "helada.png",
            "calor_extremo": "calor_extremo.png", "cambio_temp": "cambio_temp.png"
        }
        for name, filename in icon_files.items():
            try:
                path = os.path.join(icon_path, filename)
                # Abrir la imagen y asegurarse de que tiene un canal alfa (transparencia)
                icon_image = Image.open(path).convert("RGBA")
                icons[name] = icon_image
            except FileNotFoundError:
                logger.error(f"Icono no encontrado: {path}. Se usará un cuadrado de reemplazo.")
                # Crea un icono de reemplazo si no se encuentra el archivo
                placeholder = Image.new("RGBA", (24, 24))
                draw = ImageDraw.Draw(placeholder)
                draw.rectangle((2, 2, 22, 22), outline="white", fill="magenta")
                icons[name] = placeholder
        return icons

#---------------------------------------------------------------------
    def _init_button(self):
        """Inicializa el pin del botón."""
        try:
            # Usamos la configuración sin pull-up, ya que el módulo táctil
            # gestiona su propia salida.
            GPIO.setup(PIN_PAGE_BUTTON, GPIO.IN)
            logger.info(f"Botón configurado en pin GPIO {PIN_PAGE_BUTTON}.")
        except Exception as e:
            logger.error(f"Fallo al configurar el botón: {e}", exc_info=True)
#---------------------------------------------------------------------
 
   
    
    def is_button_pressed(self):
        return GPIO.input(PIN_PAGE_BUTTON) == GPIO.HIGH

    def set_backlight(self, status):
        if self.tft_device:
            GPIO.output(PIN_TFT_LED, GPIO.HIGH if status else GPIO.LOW)
#---------------------------------------------------------------------
    def draw_temp_chart(self, history, status_info, width, height):
        """
        Dibuja la tarjeta completa del gráfico, incluyendo título, estado y la línea de datos.
        """
        # 1. Crear el lienzo para el gráfico
        chart_canvas = Image.new("RGBA", (width, height))
        draw = ImageDraw.Draw(chart_canvas)

        # 2. Dibujar el recuadro de la tarjeta del gráfico
        draw.rectangle((0, 0, width - 1, height - 1), outline=UI_COLORS['border'])
        
        # 3. Dibujar el título del gráfico a la izquierda
        self._draw_text(draw, "Gráfico Temp. Exterior", self.font_medium, "white", (10, 5))
        
        # 4. Determinar y dibujar el estado de conexión a la derecha
        status_text = "OFFLINE"
        status_color = UI_COLORS['danger'] # Rojo por defecto

        if status_info.get("exterior_online"):
            minutes_ago = status_info.get("minutes_ago", 0)
            if minutes_ago < EXTERIOR_TIMEOUT_WARN1:
                status_text = "ONLINE"
                status_color = UI_COLORS['success'] # Verde
            else:
                status_text = "TIMEOUT"
                status_color = UI_COLORS['warning'] # Naranja/Amarillo
        
        # Usamos align="right" para que quede bien alineado al borde derecho
        text_width = self.font_medium.getlength(status_text)
        self._draw_text(draw, status_text, self.font_medium, status_color, (width - text_width - 10, 5))

        # 5. Dibujar la línea del gráfico
        if len(history) >= 2:
            # Encontrar min/max para escalar el gráfico
            min_val, max_val = min(history), max(history)
            val_range = max_val - min_val if max_val != min_val else 1.0

            points = []
            # Definimos el área real de dibujo para la línea, dejando márgenes
            graph_area_h = height - 40  # Altura disponible para la línea
            graph_y_start = 30          # Donde empieza el área del gráfico
            graph_x_start = 10
            graph_width = width - 20
            
            for i, val in enumerate(history):
                # Coordenada X
                px = graph_x_start + int((i / (len(history) - 1)) * graph_width)
                
                # Coordenada Y
                py_normalized = (val - min_val) / val_range
                py = graph_y_start + graph_area_h - int(py_normalized * (graph_area_h - 10)) # Margen superior/inferior
                points.append((px, py))
                
            if len(points) > 1:
                draw.line(points, fill=UI_COLORS['primary'], width=2)
        else:
            # Mensaje si no hay suficientes datos para dibujar
            self._draw_text(draw, "Esperando datos...", self.font_small, "grey", (width / 2, height / 2 + 10), align="center")

        return chart_canvas

# -------------------------------------------------------------------
    def _draw_text(self, draw, text, font, color, position, align="left"):
        """Función de ayuda para dibujar texto con diferentes alineaciones."""
        if align == "center":
            # getlength es la forma segura de obtener el ancho del texto
            text_width = font.getlength(text)
            # Calculamos la nueva posición x para centrar el texto
            position = (position[0] - text_width / 2, position[1])
        
        draw.text(position, str(text), font=font, fill=color)
 
#---------------------------------------------------------------------
    def draw_card(self, draw, rect, title, icon_name, color):
        """Dibuja el contenedor de una tarjeta con su título e icono."""
        draw.rectangle(rect, outline=UI_COLORS['border'])
        icon = self.icons.get(icon_name)
        if icon:
            # Dibuja el icono
           icon_canvas = Image.new("RGBA", self.tft_device.size)
           icon_canvas.paste(icon, (rect[0] + 8, rect[1] + 5), icon)
           draw.bitmap((0, 0), icon_canvas, fill=None)
        # Dibuja el título
        self._draw_text(draw, title, self.font_medium, color, (rect[0] + 40, rect[1] + 7))


#--------------------------------------------------------------------

    def draw_page_main(self, data_store, temp_history, status_info, active_alert, blink_state):
        """Dibuja el dashboard principal con el layout final corregido."""
        if not self.tft_device: return
        from luma.core.render import canvas
        with canvas(self.tft_device) as draw:
            # 1. Limpiar pantalla
            draw.rectangle(self.tft_device.bounding_box, fill="black")
            
            # --- Definir layout de la cuadrícula ---
            card_w, card_h = 150, 85
            gap = 5
            x1, y1 = gap, gap
            x2, y2 = gap * 2 + card_w, gap
            x3, y3 = gap, gap * 2 + card_h
            x4, y4 = gap * 2 + card_w, gap * 2 + card_h
            
            # --- Tarjeta 1: Temp. Interior ---
            rect1 = (x1, y1, x1 + card_w, y1 + card_h)
            self.draw_card(draw, rect1, "Temp. Interior", "temp", "yellow")
            t_in_str = f"{data_store['interior']['temperatura']:.1f}°C" if data_store['interior']['temperatura'] is not None else "--.-°"
            self._draw_text(draw, t_in_str, self.font_large, "white", (rect1[0] + card_w / 2, rect1[1] + 55), align="center")
            t_in_trend = data_store['interior']['temp_trend']
            self._draw_text(draw, t_in_trend, self.font_medium, "lightgrey", (rect1[0] + card_w - 20, rect1[1] + 8))
            

            # --- Tarjeta 2: Hum. Interior ---
            rect2 = (x2, y2, x2 + card_w, y2 + card_h)
            self.draw_card(draw, rect2, "Hum. Interior", "hum", "yellow")
            h_in_str = f"{data_store['interior']['humedad']:.0f}%" if data_store['interior']['humedad'] is not None else "--%"
            self._draw_text(draw, h_in_str, self.font_large, "white", (rect2[0] + card_w / 2, rect2[1] + 55), align="center")

            # --- Tarjeta 3: Temp. Exterior ---
            rect3 = (x3, y3, x3 + card_w, y3 + card_h)
            self.draw_card(draw, rect3, "Temp. Exterior", "temp", "cyan")
            t_ext_str = f"{data_store['exterior']['temperatura']:.1f}°C" if data_store['exterior']['temperatura'] is not None else "--.-°"
            ic_str = f"(IC: {data_store['exterior']['indice_calor']:.1f}°)" if data_store['exterior']['indice_calor'] is not None else ""
            self._draw_text(draw, t_ext_str, self.font_large, "white", (rect3[0] + card_w / 2, rect3[1] + 45), align="center")
            self._draw_text(draw, ic_str, self.font_small, "orange", (rect3[0] + card_w / 2, rect3[1] + 70), align="center")
            t_ext_trend = data_store['exterior']['temp_trend']
            self._draw_text(draw, t_ext_trend, self.font_medium, "lightgrey", (rect3[0] + card_w - 20, rect3[1] + 8))

            # --- Tarjeta 4: Datos Exterior ---
            rect4 = (x4, y4, x4 + card_w, y4 + card_h)
            self.draw_card(draw, rect4, "Datos Exterior", "exterior", "cyan")
            h_ext_str = f"H: {data_store['exterior']['humedad']:.0f}%" if data_store['exterior']['humedad'] is not None else "H: --%"
            p_ext_str = f"P: {data_store['exterior']['presion']:.0f}hPa" if data_store['exterior']['presion'] is not None else "P: ----"
            self._draw_text(draw, h_ext_str, self.font_medium, "white", (rect4[0] + 15, rect4[1] + 35))
            self._draw_text(draw, p_ext_str, self.font_medium, "white", (rect4[0] + 15, rect4[1] + 55))
            dew_ext_val = data_store['exterior']['dew_point']
            dew_ext_str = f"Rocío: {dew_ext_val:.1f}°C" if dew_ext_val is not None else ""
            self._draw_text(draw, dew_ext_str, self.font_small, "lightgrey", (rect4[0] + 15, rect4[1] + 70))
        
        # --- DIBUJAR ICONO DE ALERTA (SI HAY) ---
            alert_icon_to_draw = None
            if active_alert and blink_state: 
                icon_name = "helada" if active_alert == "HELADA" else "calor_extremo"
            
                alert_icon = self.icons.get(icon_name)
            if alert_icon:
                # Lo dibujamos en la esquina inferior derecha
                alert_canvas = Image.new("RGBA", self.tft_device.size)
                # La posición aquí es relativa al lienzo de la pantalla
                alert_canvas.paste(alert_icon, (280, 200), alert_icon) 
                draw.bitmap((0, 0), alert_canvas, fill=None)
                
            # La nueva alerta de cambio brusco tiene prioridad
            if active_alert_change and blink_state:
                alert_icon_to_draw = self.icons.get("cambio_temp")

            if alert_icon_to_draw:
                # Lo dibujamos en la esquina inferior derecha
                alert_canvas = Image.new("RGBA", self.tft_device.size)
                alert_canvas.paste(alert_icon_to_draw, (280, 200), alert_icon_to_draw)
                draw.bitmap((0, 0), alert_canvas, fill=None)
                    # ---------------------------------------------
                
                
                
            # --- GRÁFICO ---
            chart_x = gap
            chart_y = gap * 3 + card_h * 2
            chart_w = (card_w * 2) + gap
            chart_h = 240 - chart_y - gap
            
            chart_image = self.draw_temp_chart(temp_history, status_info, chart_w, chart_h)
            draw.bitmap((chart_x, chart_y), chart_image, fill=None)
#---------------------------------------------------------------------


    def draw_page_stats(self, stats_data, system_data):
        """Página 2: Dibuja las estadísticas con un layout de tarjetas corregido."""
        if not self.tft_device: return
        from luma.core.render import canvas
        with canvas(self.tft_device) as draw:
            # 1. Limpiar pantalla
            draw.rectangle(self.tft_device.bounding_box, fill="black")

            # --- Título de la página ---
            self._draw_text(draw, "Estadisticas y Sistema (2/2)", self.font_medium, "white", (160, 15), align="center")
            draw.line((10, 35, 310, 35), fill="yellow")

            # --- Definir layout de las tarjetas ---
            card_x1, card_y1, card_w, card_h = 10, 45, 145, 185
            card_x2 = 165
            
            # --- TARJETA IZQUIERDA: ESTADÍSTICAS 24H ---
            card_x1, card_y1, card_w, card_h = 10, 45, 145, 185
            self.draw_card(draw, (card_x1, card_y1, card_x1 + card_w, card_y1 + card_h), "Max/Min 24h", "temp", "orange")

            t_max_val = stats_data['exterior']['temp_max']
            t_min_val = stats_data['exterior']['temp_min']

            if stats_data['exterior'].get('reading_count', 0) > 0:
                t_avg_val = stats_data['exterior']['temp_sum'] / stats_data['exterior']['reading_count']
                t_avg_str = f"Prom: {t_avg_val:.1f}°C"
            else:
                t_avg_str = "Prom: --.-"
                
            # Calcular la variación
            if t_max_val is not None and t_min_val is not None:
                t_var_val = t_max_val - t_min_val
                t_var_str = f"Var:  {t_var_val:.1f}°C"
            else:
                t_var_str = "Var:  --.-"
            # ---------------------------------
            
            t_max_str = f"Max:  {t_max_val:.1f}°C" if t_max_val is not None else "Max:  --.-"
            t_min_str = f"Min:  {t_min_val:.1f}°C" if t_min_val is not None else "Min:  --.-"
            
            # Dibujar todos los datos en la tarjeta
            y_start = card_y1 + 40
            y_step = 30
            self._draw_text(draw, t_max_str, self.font_medium, "orange", (card_x1 + 15, y_start))
            self._draw_text(draw, t_min_str, self.font_medium, "cyan", (card_x1 + 15, y_start + y_step))
            self._draw_text(draw, t_avg_str, self.font_medium, "white", (card_x1 + 15, y_start + y_step * 2))
            self._draw_text(draw, t_var_str, self.font_medium, "violet", (card_x1 + 15, y_start + y_step * 3))

            
                      
                                # --- TARJETA DERECHA: SISTEMA PI ZERO ---
            card_x2 = 165
            self.draw_card(draw, (card_x2, card_y1, card_x2 + card_w, card_y1 + card_h), "Sistema Pi", "casa", "green")

            # --- Lógica y dibujo para Temperatura CPU ---
            cpu_temp = system_data['cpu_temp']
            cpu_temp_str = f"Temp CPU: {cpu_temp:.1f} C" if cpu_temp is not None else "Temp CPU: --.- C"
            cpu_color = UI_COLORS['success'] # Verde por defecto
            if cpu_temp is not None:
                if cpu_temp > CPU_TEMP_DANGER: cpu_color = UI_COLORS['danger'] # Rojo
                elif cpu_temp > CPU_TEMP_WARN: cpu_color = UI_COLORS['warning'] # Naranja/Amarillo
            self._draw_text(draw, cpu_temp_str, self.font_medium, cpu_color, (card_x2 + 15, card_y1 + 40))

            # --- Lógica y dibujo para Uso de RAM ---
            ram_usage = system_data['ram_usage']
            ram_str = f"Uso RAM:  {ram_usage:.0f} %" if ram_usage is not None else "Uso RAM:  -- %"
            ram_color = UI_COLORS['success']
            if ram_usage is not None:
                if ram_usage > RAM_USAGE_DANGER: ram_color = UI_COLORS['danger']
                elif ram_usage > RAM_USAGE_WARN: ram_color = UI_COLORS['warning']
            self._draw_text(draw, ram_str, self.font_medium, ram_color, (card_x2 + 15, card_y1 + 70))

            # --- Lógica y dibujo para Señal WiFi ---
            wifi_signal = system_data['wifi_signal']
            wifi_str = f"Senal WiFi: {wifi_signal:.0f} %" if wifi_signal is not None else "Senal WiFi: -- %"
            wifi_color = UI_COLORS['success']
            if wifi_signal is not None:
                if wifi_signal < WIFI_SIGNAL_DANGER: wifi_color = UI_COLORS['danger']
                elif wifi_signal < WIFI_SIGNAL_WARN: wifi_color = UI_COLORS['warning']
            self._draw_text(draw, wifi_str, self.font_medium, wifi_color, (card_x2 + 15, card_y1 + 100))

            # --- Lógica y dibujo para Uptime (sin cambio de color) ---
            self._draw_text(draw, "Activo:", self.font_medium, "white", (card_x2 + 15, card_y1 + 130))
            uptime_val = system_data['uptime'] if system_data['uptime'] is not None else "---"
            self._draw_text(draw, uptime_val, self.font_small, "lightgrey", (card_x2 + 15, card_y1 + 155))



# -------------------------------------------------------------------
    
    def read_local_bme280(self):
        """Lee el sensor BME280 local de forma segura y devuelve los datos."""
        if not self.bme280:
            logging.warning("Intento de leer BME280, pero no está inicializado.")
            return None

        with self._lock:
            try:
                return {
                    "temperatura": self.bme280.temperature,
                    "humedad": self.bme280.relative_humidity,
                    "presion": self.bme280.pressure
                }
            except Exception as e:
                logging.error(f"Error al leer el sensor BME280 local: {e}")
                return None

    def update_leds(self, system_color, environment_color):
        """Actualiza ambos LEDs NeoPixel a la vez."""
        if not self.pixels:
            return # No hacer nada si los NeoPixels no se inicializaron
        
        with self._lock:
            try:
                self.pixels[NEOPIXEL_INDEX_SYSTEM] = system_color
                self.pixels[NEOPIXEL_INDEX_ENVIRONMENT] = environment_color
                self.pixels.show()
            except Exception as e:
                logging.error(f"Error al actualizar los NeoPixels: {e}")
    
    def cleanup(self):
        logging.info("Limpiando hardware...")
        if self.pixels:
            self.pixels.fill(COLOR_OFF)
            self.pixels.show()
        GPIO.cleanup()
        logging.info("Hardware limpiado.")