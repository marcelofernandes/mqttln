import asyncio
from lnbits.tasks import register_invoice_listener
from lnbits.helpers import get_current_extension_name
from lnbits.core.models import Payment
from loguru import logger # type: ignore
import json

async def wait_for_paid_invoices(mqttClient):
    invoice_queue = asyncio.Queue()
    register_invoice_listener(invoice_queue, get_current_extension_name())
    while True:
        payment = await invoice_queue.get()
        await on_invoice_paid(payment, mqttClient)

async def on_invoice_paid(payment: Payment, mqttClient):
    if (payment.pending == True or len(payment.checking_id) == 0 
        or payment.extra.get("tag") != "lnurlp" or payment.extra.get("lnaddress") == 0):
        return
    code = payment.extra.get("lnaddress").split("@")[0]
    balance = payment.amount / 1000
    device_payment_topic = f"device/payment/{code}"
    payload = json.dumps({"balance": balance})
    mqttClient.client.publish(device_payment_topic, payload=payload, qos=2, retain=False)
    logger.info("Mensagem enviada.")
