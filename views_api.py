from fastapi import (APIRouter, Depends) # type: ignore
from lnbits.core.models import (User) # type: ignore
from lnbits.decorators import (check_user_exists) # type: ignore
from lnbits.db import Database # type: ignore
from loguru import logger # type: ignore

mqttln_ext_api = APIRouter(
    prefix="/api/v1",
    tags=["mqttln"],
)

@mqttln_ext_api.get("/health-check", description="Health check")
async def api_get_health_check():
    return "Ok"

@mqttln_ext_api.get("/balance", description="Balance")
async def api_get_health_check(user: User = Depends(check_user_exists)):
    database = Database("database")
    balance = await database.fetchone(f"SELECT SUM(apipayments.amount - ABS(apipayments.fee)) AS balance FROM apipayments LEFT JOIN wallets ON apipayments.wallet = wallets.id WHERE wallets.user = ? and  (wallets.deleted = false OR wallets.deleted is NULL) AND ((apipayments.pending = false AND apipayments.amount > 0) OR apipayments.amount < 0)", (user.id))
    logger.info(f"Balance: {balance}")
    return f"Balance: {balance}"
