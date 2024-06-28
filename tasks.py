import asyncio
from lnbits.tasks import register_invoice_listener
from lnbits.helpers import get_current_extension_name
from lnbits.core.models import Payment
from loguru import logger # type: ignore

async def wait_for_paid_invoices():
    invoice_queue = asyncio.Queue()
    register_invoice_listener(invoice_queue, get_current_extension_name())
    while True:
        payment = await invoice_queue.get()
        await on_invoice_paid(payment)

async def on_invoice_paid(payment: Payment):
    logger.info(f"Pagamento realizado: {payment}")