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
from lnbits.core.models import WalletTypeInfo, CreateLnurl # type: ignore
from lnbits.core.views.payment_api import api_payments_pay_lnurl, api_payment # type: ignore

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend

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
        self.main_loop = None

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
                database = Database("database")
                wallet = await database.fetchone(f"SELECT * FROM wallets WHERE name = ? AND deleted = 0", (code))
                logger.info(f"Wallet: {wallet}")
                payment_response = await pay_invoice(wallet_id=wallet.id, payment_request=invoice)
                logger.info(f"Payment response: {payment_response}")
                topic = f"device/receipt/{code}"
                payment = await api_payment(payment_response, wallet.adminkey)
                amount_paid = payment['details'].amount
                valor_absoluto = abs(amount_paid) / 1000
                logger.info(f"Amount paid: {valor_absoluto}")
                payload = json.dumps({"receipt": payment_response, "paid": True, "balance": valor_absoluto})
                self.client.publish(topic, payload=payload, qos=1, retain=False)
            
            async def handle_message_pay_invoice_lnurl(code, invoice, amount):
                database = Database("database")
                wallet = await database.fetchone(f"SELECT * FROM wallets WHERE name = ? AND deleted = 0", (code))
                wallet_info = WalletTypeInfo(1, wallet)
                lnurl_response = await api_lnurlscan(code=invoice, wallet=wallet_info)
                data = CreateLnurl(
                    description_hash=lnurl_response['description_hash'],
                    callback=lnurl_response['callback'],
                    amount=amount,
                    description=lnurl_response['description'])
                try:
                    payment_response = await api_payments_pay_lnurl(data, wallet_info)
                    logger.info(f"Payment response: {payment_response}")
                    topic = f"device/receipt/{code}"
                    payment = await api_payment(payment_response, wallet.adminkey)
                    amount_paid = payment['details'].amount
                    valor_absoluto = abs(amount_paid) / 10000
                    logger.info(f"Amount paid: {valor_absoluto}")
                    payload = json.dumps({"receipt": payment_response, "paid": True, "balance": valor_absoluto})
                    self.client.publish(topic, payload=payload, qos=1, retain=False)
                except Exception as e:
                    logger.info(str(e))
            
            def on_message(client, userdata, msg):
                if msg.topic.startswith("wallet/invoice"):
                    code = msg.topic.split("/")[2]
                    json_payload = msg.payload.decode()
                    payload = json.loads(json_payload)
                    invoice = payload['invoice']
                    pub_key = payload['pub_key']
                    signature = payload['signature']

                    public_key_pem = pub_key.encode()
                    invoice_bytes = invoice.encode()

                    signature_bytes = bytes.fromhex(signature)
                    # Carregar a chave pública
                    public_key = serialization.load_pem_public_key(
                        public_key_pem,
                        backend=default_backend()
                    )

                    # Concatenar a mensagem com a chave pública
                    # Serializar a chave pública em formato PEM
                    public_key_bytes = public_key.public_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PublicFormat.SubjectPublicKeyInfo
                    )

                    # Concatenar a mensagem com a chave pública
                    message_with_pubkey = invoice_bytes + public_key_bytes

                    # Verificar a assinatura
                    try:
                        public_key.verify(
                            signature_bytes,
                            message_with_pubkey,
                            ec.ECDSA(hashes.SHA256())
                        )
                        if 'amount' in payload:
                            # asyncio.create_task(handle_message_pay_invoice_lnurl(code, invoice, payload['amount']))
                            asyncio.run_coroutine_threadsafe(handle_message_pay_invoice_lnurl(code, invoice, payload['amount']), self.main_loop)
                            # asyncio.run(handle_message_pay_invoice_lnurl(code, invoice, payload['amount']))
                        else:
                            # asyncio.create_task(handle_message_pay_invoice_lnbc(code, invoice))
                            asyncio.run_coroutine_threadsafe(handle_message_pay_invoice_lnbc(code, invoice), self.main_loop)
                            # asyncio.run(handle_message_pay_invoice_lnbc(code, invoice))
                    except InvalidSignature:
                        logger.info("Invalid signature")
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
        self.main_loop = self.client.loop()
        wst.daemon = True
        wst.start()

    def disconnect_to_mqtt_broker(self):
        if self.connected is True:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
