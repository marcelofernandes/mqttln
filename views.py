from fastapi import APIRouter, Depends, Request # type: ignore
from fastapi.responses import HTMLResponse # type: ignore
from lnbits.core.models import User # type: ignore
from lnbits.decorators import check_user_exists # type: ignore
from lnbits.helpers import template_renderer # type: ignore

mqttln_ext_generic = APIRouter(tags=["mqttln"])


@mqttln_ext_generic.get(
    "/", description="Example generic endpoint", response_class=HTMLResponse
)
async def index(
    request: Request,
    user: User = Depends(check_user_exists),
):
    return template_renderer(["mqttln/templates"]).TemplateResponse(
        request, "mqttln/index.html", {"user": user.dict()}
    )
