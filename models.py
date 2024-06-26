import paho.mqtt.client as mqtt # type: ignore
from loguru import logger # type: ignore
from threading import Thread
from .crud import (create)
import asyncio
from http import HTTPStatus
import httpx # type: ignore
from fastapi.exceptions import HTTPException # type: ignore

class MQTTClient():
    def __init__(self, broker, port, wallet_topic, device_wallet_topic, app_host):
        self.broker = broker
        self.port = port
        self.wallet_topic = wallet_topic
        self.device_wallet_topic = device_wallet_topic
        self.app_host = app_host
        self.username = "rw"
        self.password = "readwrite"
        self.client = None

    def _ws_handlers(self):
            def on_connect(client, userdata, flags, rc):
                logger.info("Conectado com código de resultado: " + str(rc))
                client.subscribe(self.wallet_topic)

            async def handle_message(msg):
                msg_decoded = msg.payload.decode()
                try:
                    async with httpx.AsyncClient() as client:
                        scan = await client.get(
                            f"https://{self.app_host}.ngrok-free.app/api/v1/lnurlscan/marcelo@{self.app_host}.ngrok-free.app",
                            headers= {
                                "accept": "application/json, text/plain, */*", "x-api-key": "deedc1af97344b47a2b33005c96b6a3a"
                            }
                        )
                        scanJson = scan.json()
                        await client.post(
                            f"https://{self.app_host}.ngrok-free.app/api/v1/payments/lnurl",
                            headers = {
                                "accept": "application/json, text/plain, */*", "x-api-key": "deedc1af97344b47a2b33005c96b6a3a"
                            },
                            json = {
                                # "amount": scanJson['minSendable'],
                                "amount": 100000,
                                "callback": scanJson['callback'],
                                "comment": "",
                                "description": scanJson['description'],
                                "description_hash": scanJson['description_hash'],
                                "unit": 'sat'
                            }
                        )
                        await create(msg_decoded)
                        self.client.publish(self.device_wallet_topic, msg_decoded)
                except Exception as e:
                    raise HTTPException(
                        status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=str(e)
                    ) from e

            def on_message(client, userdata, msg):
                if msg.topic == self.wallet_topic:
                    message = f"Mensagem recebida: {msg.payload.decode()} no tópico {msg.topic}"
                    asyncio.run(handle_message(msg))
                    logger.info(message)

            return on_connect, on_message

    def connect_to_mqtt_broker(self):
        logger.info(f"Connecting to MQTT broker")
        on_connect, on_message = self._ws_handlers()
        self.client = mqtt.Client()
        self.client.on_connect = on_connect
        self.client.on_message = on_message
        self.client.username_pw_set(self.username, self.password)
        self.client.connect(self.broker, self.port, 60)
        self.connected = True
    
    def start_mqtt_client(self):
        wst = Thread(target=self.client.loop_start)
        wst.daemon = True
        wst.start()

    def disconnect_to_mqtt_broker(self):
        if self.connected is True:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
