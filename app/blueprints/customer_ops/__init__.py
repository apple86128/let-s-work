from flask import Blueprint

customer_ops_bp = Blueprint(
    'customer_ops',
    __name__,
    url_prefix='/customer-ops',
)

from app.blueprints.customer_ops import routes  # noqa: E402, F401
