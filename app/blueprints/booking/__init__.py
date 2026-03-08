from flask import Blueprint

booking_bp = Blueprint(
    "booking",
    __name__,
    url_prefix="/booking",
    template_folder="../../templates"
)

from app.blueprints.booking import routes  # noqa
