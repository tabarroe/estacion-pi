import paho.mqtt.client as mqtt
import json
import config

_tb_client = None
_is_connected = False

def conectar_a_thingsboard():
    global _tb_client, _is_connected
    _tb_client = mqtt.Client(client_id=config.CLIENT_ID_TB)
    _tb_client.username_pw_set(config.THINGSBOARD_ACCESS_TOKEN)
    # ... (asignar callbacks on_connect_tb y on_disconnect_tb)
    try:
        _tb_client.connect(config.THINGSBOARD_HOST, config.THINGSBOARD_PORT, 60)
        _tb_client.loop_start()
        _is_connected = True
        return True
    except Exception as e:
        print(f"ThingsBoard: Fallo al conectar: {e}")
        _is_connected = False
        return False

def enviar_telemetria(datos_dict):
    if _is_connected:
        _tb_client.publish('v1/devices/me/telemetry', json.dumps(datos_dict))