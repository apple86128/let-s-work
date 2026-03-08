from flask import Blueprint

bom_bp = Blueprint(
    "bom",
    __name__,
    url_prefix="/bom",
    template_folder="../../templates"
)

from app.blueprints.bom import routes  # noqa
