import paho.mqtt.client as mqtt # type: ignore
from loguru import logger # type: ignore
from threading import Thread
import asyncio
from http import HTTPStatus
from fastapi.exceptions import HTTPException # type: ignore
from lnbits.core.crud import create_wallet # type: ignore
from lnbits.db import Database # type: ignore
import json
from lnbits.extensions.lnurlp.models import CreatePayLinkData
from lnbits.extensions.lnurlp.crud import create_pay_link

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

            async def handle_message(code, user_id):
                try:
                    database = Database("database")
                    wallet = await database.fetchone(f"SELECT * FROM wallets WHERE name = ? AND user = ? AND deleted = 0", (code, user_id))
                    if not wallet:
                        wallet = await create_wallet(user_id = user_id, wallet_name = code)
                        print(wallet)
                    
                    pay_link_data = CreatePayLinkData(
                        wallet=wallet.id,
                        comment_chars=0,
                        description="Link de pagamento",
                        min=1,
                        max=100,
                        username=code,
                        zaps=False
                    )
                    await create_pay_link(
                        wallet_id=wallet.id,
                        data=pay_link_data
                    )
                    # Create LNaddress for Wallet created
                    # Publish LNaddress to Supplier
                    # self.client.publish(self.device_wallet_topic, msg)
                    logger.info(f"Código recebido: {code}")
                except Exception as e:
                    raise HTTPException(
                        status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=str(e)
                    ) from e

            def on_message(client, userdata, msg):
                if msg.topic.startswith("wallet/"):
                    code = msg.topic.split("/", 1)[1]
                    json_payload = msg.payload.decode()
                    payload = json.loads(json_payload)
                    user_id = payload['id']
                    if len(code) > 0:
                        asyncio.run(handle_message(code, user_id))

            return on_connect, on_message

    def connect_to_mqtt_broker(self):
        logger.info("Conectando ao Broker MQTT")
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
