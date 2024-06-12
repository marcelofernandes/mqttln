import asyncio

from fastapi import APIRouter
from lnbits.db import Database
from lnbits.tasks import create_permanent_unique_task
from loguru import logger

from .views import mqttln_ext_generic
from .views_api import mqttln_ext_api

db = Database("ext_mqttln")

from .mqtt_client import MQTTClient
mqtt_client: MQTTClient = MQTTClient()

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
        await asyncio.sleep(5)
        mqtt_client.connect_to_mqtt_broker()
        await asyncio.sleep(5)
        mqtt_client.start_mqtt_client()
    
    task = create_permanent_unique_task("ext_task_connect_mqtt", _start_mqtt_client)
    scheduled_tasks.append(task)
