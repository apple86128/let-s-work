from flask import Blueprint

product_bp = Blueprint(
    "product",
    __name__,
    url_prefix="/admin/products",
    template_folder="../../templates"
)

from app.blueprints.product import routes  # noqa
