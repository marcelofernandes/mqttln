import asyncio

from fastapi import APIRouter
from lnbits.db import Database
from lnbits.tasks import create_permanent_unique_task
from loguru import logger

from .views import mysuperplugin_ext_generic
from .views_api import mysuperplugin_ext_api

db = Database("ext_mysuperplugin")

from .mqtt_client import MQTTClient
mqtt_client: MQTTClient = MQTTClient()

scheduled_tasks: list[asyncio.Task] = []

mysuperplugin_ext: APIRouter = APIRouter(prefix="/mysuperplugin", tags=["mysuperplugin"])
mysuperplugin_ext.include_router(mysuperplugin_ext_generic)
mysuperplugin_ext.include_router(mysuperplugin_ext_api)

mysuperplugin_static_files = [
    {
        "path": "/mysuperplugin/static",
        "name": "mysuperplugin_static",
    }
]

def mysuperplugin_stop():
    for task in scheduled_tasks:
        try:
            task.cancel()
            mqtt_client.disconnect_to_mqtt_broker()
        except Exception as ex:
            logger.warning(ex)

def mysuperplugin_start():
    async def _start_mqtt_client():
        await asyncio.sleep(5)
        mqtt_client.connect_to_mqtt_broker()
        await asyncio.sleep(5)
        mqtt_client.start_mqtt_client()
    
    task = create_permanent_unique_task("ext_task_connect_mqtt", _start_mqtt_client)
    scheduled_tasks.append(task)
