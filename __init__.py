import asyncio

from fastapi import APIRouter
from lnbits.db import Database
from lnbits.tasks import create_permanent_unique_task
from loguru import logger

from .views import mqttln_ext_generic
from .views_api import mqttln_ext_api

# from lnbits.core.crud import create_wallet

db = Database("ext_mqttln")

from .models import MQTTClient

import os

# broker = "172.21.240.91"
# port = 1883

broker = "test.mosquitto.org"
port = 1884
wallet_topic = "wallet/+"
device_wallet_topic = "device/wallet"
# device_payment_topic = "device/payment"
app_host = os.environ.get("NGROK_HOST", "81ae-177-84-220-115")

mqtt_client: MQTTClient = MQTTClient(broker, port, wallet_topic, device_wallet_topic, app_host)

scheduled_tasks: list[asyncio.Task] = []

mqttln_ext: APIRouter = APIRouter(prefix="/mqttln", tags=["mqttln"])
mqttln_ext.include_router(mqttln_ext_generic)
mqttln_ext.include_router(mqttln_ext_api)

mqttln_static_files = [
    {
        "path": "/mqttln/static",
        "name": "mqttln_static",
    }
]

def mqttln_stop():
    for task in scheduled_tasks:
        try:
            task.cancel()
            mqtt_client.disconnect_to_mqtt_broker()
        except Exception as ex:
            logger.warning(ex)

def mqttln_start():
    async def _start_mqtt_client():
        database = Database("database")
        extension_active = await database.fetchone("SELECT * FROM extensions WHERE extension = 'mqttln' AND active = 1")
        if extension_active:
            await asyncio.sleep(3)
            mqtt_client.connect_to_mqtt_broker()
            await asyncio.sleep(3)
            mqtt_client.start_mqtt_client()
    
    task = create_permanent_unique_task("ext_task_connect_mqtt", _start_mqtt_client)
    scheduled_tasks.append(task)
