import paho.mqtt.client as mqtt # type: ignore
from loguru import logger # type: ignore
from threading import Thread
import asyncio
from lnbits.core.crud import create_wallet, delete_wallet # type: ignore
from lnbits.db import Database # type: ignore
import json
import re
from lnbits.extensions.lnurlp.models import CreatePayLinkData # type: ignore
from lnbits.extensions.lnurlp.crud import create_pay_link, get_address_data # type: ignore

from lnbits.core.services import pay_invoice # type: ignore
from lnbits.core.views.api import api_lnurlscan # type: ignore
from lnbits.core.views.payment_api import api_payments_pay_lnurl # type: ignore

class MQTTClient():
    def __init__(self, broker, port, wallet_topic, device_wallet_topic, app_host):
        self.broker = broker
        self.port = port
        self.wallet_topic = wallet_topic
        self.device_wallet_topic = device_wallet_topic
        self.app_host = app_host
        self.username = "admin"
        self.password = "admin"
        self.client = None
        self.connected = False

    def _ws_handlers(self):
            def on_connect(client, userdata, flags, rc):
                logger.info("Conectado com código de resultado: " + str(rc))
                client.subscribe(self.wallet_topic)

            def on_disconnect(client, userdata, rc):
                logger.info("Desconectado do broker MQTT")
                self.connected = False
            
            async def exponencial_wait(value):
                time = 2 ** value
                await asyncio.sleep(time)
                
            async def create_new_wallet(user_id, code, attempt = 1):
                try:
                    wallet = await create_wallet(user_id = user_id, wallet_name = code)
                    return wallet
                except Exception as e:
                    if attempt <= 5:
                        await exponencial_wait(attempt)
                        await create_new_wallet(user_id, code, attempt + 1)
                    else:
                        raise e

            async def create_new_paylink(wallet, pay_link_data, attempt = 1):
                try:
                    await create_pay_link(wallet_id=wallet.id, data=pay_link_data)
                    return
                except Exception as e:
                    if attempt <= 5:
                        await exponencial_wait(attempt)
                        await create_new_paylink(wallet.id, pay_link_data, attempt + 1)
                    else:
                        raise e

            async def handle_message(code, user_id, device_id):
                try:
                    database = Database("database")
                    wallet = await database.fetchone(f"SELECT * FROM wallets WHERE name = ? AND user = ? AND deleted = 0", (code, user_id))
                    if not wallet:
                        try:  
                            wallet = await create_new_wallet(user_id = user_id, wallet_name = code)
                        except Exception as e:
                            logger.info(e)
                            payload = json.dumps({"message": "Falha ao criar carteira!"})
                            self.client.publish(topic, payload=payload, qos=1, retain=False)
                            return
                    
                    address = await get_address_data(code)
                    if address is None:
                        try:
                            pay_link_data = CreatePayLinkData(
                                wallet=wallet.id,
                                comment_chars=0,
                                description = f"Link de pagamento para o dispositivo: {device_id}",
                                min=1,
                                max=100000000,
                                username=code,
                                zaps=False
                            )
                            
                            await create_new_paylink(wallet_id=wallet.id, data=pay_link_data)
                        except Exception as e:
                            logger.info(e)
                            payload = json.dumps({"message": "Falha ao criar lnaddress!"})
                            await delete_wallet(user_id = user_id, wallet_id = wallet.id)
                            self.client.publish(topic, payload=payload, qos=1, retain=False)
                            return
                    topic = f"{self.device_wallet_topic}/{code}"
                    self.client.publish(topic, payload="", qos=1, retain=False)
                    logger.info(f"Código enviado: {code} no tópico: {topic}")
                    
                except Exception as e:
                    logger.info(str(e))

            async def handle_message_pay_invoice_lnbc(code, invoice):
                logger.info(f"Code: {code}")
                logger.info(f"Invoice: {invoice}")
                database = Database("database")
                wallet = await database.fetchone(f"SELECT * FROM wallets WHERE name = ? AND deleted = 0", (code))
                await pay_invoice(wallet_id=wallet.id, invoice=invoice)
            
            async def handle_message_pay_invoice_lnurl(code, invoice):
                lnurl_response = await api_lnurlscan(invoice)
            
            def on_message(client, userdata, msg):
                if msg.topic.startswith("wallet/invoice"):
                    code = msg.topic.split("/")[2]
                    json_payload = msg.payload.decode()
                    payload = json.loads(json_payload)
                    invoice = payload['invoice']
                    if re.match(r'[\w.+-~_]+@[\w.+-~_]', invoice):
                        asyncio.run(handle_message_pay_invoice_lnurl(code, invoice))
                    else:
                        asyncio.run(handle_message_pay_invoice_lnbc(code, invoice))
                elif msg.topic.startswith("wallet/"):
                    code = msg.topic.split("/", 1)[1]
                    json_payload = msg.payload.decode()
                    payload = json.loads(json_payload)
                    user_id = payload['id']
                    device_id = payload['device_id']
                    if len(code) > 0:
                        asyncio.run(handle_message(code, user_id, device_id))

            return on_connect, on_message, on_disconnect

    async def connect_to_mqtt_broker(self):
        logger.info("Conectando ao Broker MQTT")
        on_connect, on_message, on_disconnect = self._ws_handlers()
        self.client = mqtt.Client()
        self.client.on_connect = on_connect
        self.client.on_message = on_message
        self.client.on_disconnect = on_disconnect
        self.client.username_pw_set(self.username, self.password)
        while not self.connected:
            try:
                self.client.connect(self.broker, self.port, 60)
                self.connected = True
            except ConnectionRefusedError as e:
                logger.info(f"Erro de conexão: {e}. Tentando reconectar em 5 segundos...")
                await asyncio.sleep(5)

    def start_mqtt_client(self):
        wst = Thread(target=self.client.loop_start)
        wst.daemon = True
        wst.start()

    def disconnect_to_mqtt_broker(self):
        if self.connected is True:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
