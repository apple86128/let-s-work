from flask import Blueprint

project_bp = Blueprint(
    'project',
    __name__,
    url_prefix='/project',
)

from app.blueprints.project import routes  # noqa: E402, F401
