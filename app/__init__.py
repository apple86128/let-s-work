from flask import Flask, redirect, url_for
from flask_login import LoginManager, current_user
from config import config_map


def create_app(config_name="default"):
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_map[config_name])
    _init_extensions(app)
    _register_template_globals(app)
    _register_root_route(app)
    _register_blueprints(app)
    _init_database(app)
    return app


def _init_extensions(app):
    from app.models import db
    db.init_app(app)
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "隢??餃蝟餌絞"
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id):
        from app.models.user import User
        return User.query.get(int(user_id))


def _register_template_globals(app):
    @app.context_processor
    def inject_globals():
        from app.utils.permissions import has_permission, get_user_menu_items
        from flask_login import current_user
        return dict(
            has_permission=has_permission,
            get_user_menu_items=get_user_menu_items,
        )


def _register_root_route(app):
    @app.route("/")
    def home():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard.index"))
        return redirect(url_for("auth.login"))


def _register_blueprints(app):
    from app.blueprints.auth      import auth_bp
    from app.blueprints.dashboard import dashboard_bp
    from app.blueprints.admin     import admin_bp
    from app.blueprints.booking   import booking_bp
    from app.blueprints.product   import product_bp
    from app.blueprints.bom       import bom_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(booking_bp)
    app.register_blueprint(product_bp)
    app.register_blueprint(bom_bp)


def _init_database(app):
    from app.models import db
    from app.models.user import create_default_roles, create_default_users
    with app.app_context():
        db.create_all()
        create_default_roles()
        create_default_users()
