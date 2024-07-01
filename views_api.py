from http import HTTPStatus

from fastapi import APIRouter # type: ignore

mqttln_ext_api = APIRouter(
    prefix="/api/v1",
    tags=["mqttln"],
)

@mqttln_ext_api.get("/health-check", description="Health check")
async def api_get_health_check():
    return "Ok"
