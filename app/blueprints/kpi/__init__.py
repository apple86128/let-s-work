from flask import Blueprint

kpi_bp = Blueprint(
    'kpi',
    __name__,
    url_prefix='/kpi',
)

from app.blueprints.kpi import routes  # noqa: E402, F401
