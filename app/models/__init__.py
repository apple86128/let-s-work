from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

from app.models.user       import User, Role, UserSession
from app.models.permission import UserPermission
from app.models.booking    import CustomerBooking, BookingExtensionRequest
from app.models.product    import Module, Function, PricingTier
from app.models.bom        import BOM, BOMItem, BOMReviewHistory
from app.models.customer_ops import CustomerAccount, AccountContract
