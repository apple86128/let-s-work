from datetime import datetime
from app.models import db
from app.models.product import Module, Function


class BOM(db.Model):
    """BOM 資料模型 - 物料需求清單"""
    __tablename__ = 'boms'

    id               = db.Column(db.Integer, primary_key=True)
    source_type      = db.Column(db.String(20),  default='from_booking', nullable=False)
    booking_id       = db.Column(db.Integer, db.ForeignKey('customer_bookings.id'), nullable=True)
    bom_number       = db.Column(db.String(50),  unique=True, nullable=False)

    customer_company    = db.Column(db.String(200), nullable=False)
    customer_contact    = db.Column(db.String(100), nullable=True)
    customer_email      = db.Column(db.String(120), nullable=True)
    project_name        = db.Column(db.String(200), nullable=False)
    project_description = db.Column(db.Text,        nullable=True)

    plan_type  = db.Column(db.String(20),  nullable=False)
    plan_years = db.Column(db.Integer,     nullable=False)

    # 系統自動計算的參考點數（由 items 加總）
    total_points      = db.Column(db.Integer, default=0, nullable=False)
    # 使用者自訂的實際下單點數（None 表示未覆蓋，以 total_points 為準）
    custom_points     = db.Column(db.Integer, nullable=True)
    base_modules_cost = db.Column(db.Integer, default=0, nullable=False)
    points_cost       = db.Column(db.Integer, default=0, nullable=False)
    suggested_price   = db.Column(db.Integer, default=0, nullable=False)

    final_price   = db.Column(db.Integer, nullable=True)
    discount_rate = db.Column(db.Float,   nullable=True)

    labor_suggested_price     = db.Column(db.Integer, default=0, nullable=False)
    final_maintenance_price   = db.Column(db.Integer, nullable=True)
    maintenance_discount_rate = db.Column(db.Float,   nullable=True)

    status         = db.Column(db.String(20), default='pending', nullable=False)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_at    = db.Column(db.DateTime, nullable=True)
    review_notes   = db.Column(db.Text,     nullable=True)

    created_at    = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at    = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    assigned_sales_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    is_deleted    = db.Column(db.Boolean,  default=False, nullable=False)
    deleted_at    = db.Column(db.DateTime, nullable=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    booking        = db.relationship('CustomerBooking', backref='boms')
    created_by     = db.relationship('User', foreign_keys=[created_by_id],     backref='created_boms')
    reviewed_by    = db.relationship('User', foreign_keys=[reviewed_by_id],    backref='reviewed_boms')
    deleted_by     = db.relationship('User', foreign_keys=[deleted_by_id])
    assigned_sales = db.relationship('User', foreign_keys=[assigned_sales_id], backref='assigned_boms')
    items          = db.relationship('BOMItem', backref='bom', lazy=True, cascade='all, delete-orphan')

    STATUS_DISPLAY = {'pending': '待審核', 'approved': '已批准', 'rejected': '已拒絕'}

    def __init__(self, customer_company, project_name, plan_type, plan_years,
                 created_by_id, source_type='from_booking', booking_id=None,
                 customer_contact=None, customer_email=None, project_description=None,
                 assigned_sales_id=None):
        self.customer_company    = customer_company
        self.project_name        = project_name
        self.plan_type           = plan_type
        self.plan_years          = plan_years
        self.created_by_id       = created_by_id
        self.source_type         = source_type
        self.booking_id          = booking_id
        self.customer_contact    = customer_contact
        self.customer_email      = customer_email
        self.project_description = project_description
        self.assigned_sales_id   = assigned_sales_id if assigned_sales_id else created_by_id
        self.bom_number          = self._generate_bom_number()

    def _generate_bom_number(self):
        date_part = datetime.now().strftime('%Y%m%d')
        count     = BOM.query.filter(BOM.bom_number.like(f'BOM-{date_part}-%')).count()
        return f'BOM-{date_part}-{count + 1:03d}'

    def get_status_display(self):
        return self.STATUS_DISPLAY.get(self.status, '未知狀態')

    def get_status_color(self):
        return {'pending': 'warning', 'approved': 'success', 'rejected': 'danger'}.get(self.status, 'secondary')

    def get_plan_type_display(self):
        if self.plan_type == 'onetime':
            return f'買斷方案（{self.plan_years} 年維護）'
        return f'訂閱方案（{self.plan_years} 年）'

    def is_protected(self):
        return self.source_type == 'from_booking' and self.booking_id is not None

    def get_assigned_sales_info(self):
        if self.assigned_sales:
            return {
                'name':      self.assigned_sales.name,
                'email':     self.assigned_sales.email,
                'extension': getattr(self.assigned_sales, 'extension', None),
            }
        return None

    def get_creator_info(self):
        if self.created_by:
            return {'name': self.created_by.name, 'email': self.created_by.email}
        return None

    def is_cross_created(self):
        return self.created_by_id != self.assigned_sales_id and self.assigned_sales_id is not None

    def update_assigned_sales(self, new_sales_id, updated_by_id):
        self.assigned_sales_id = new_sales_id
        self.updated_at        = datetime.utcnow()

    def _is_related_sales(self, user):
        return (self.created_by_id == user.id or self.assigned_sales_id == user.id) and not self.is_deleted

    def can_be_viewed_by(self, user):
        if not user:
            return False
        if user.has_role('admin') or user.has_role('pm'):
            return True
        return user.has_role('sales') and self._is_related_sales(user)

    def can_be_edited_by(self, user):
        if not user:
            return False
        if user.has_role('admin') or user.has_role('pm'):
            return True
        return (user.has_role('sales') and
                self._is_related_sales(user) and
                self.status in ('pending', 'rejected'))

    def can_be_deleted_by(self, user):
        if not user:
            return False
        if user.has_role('admin') or user.has_role('pm'):
            return True
        return user.has_role('sales') and self._is_related_sales(user)

    def can_be_reviewed_by(self, user):
        if not user:
            return False
        return ((user.has_role('admin') or user.has_role('pm')) and
                self.status == 'pending' and not self.is_deleted)

    def can_view_pricing(self, user):
        if not user:
            return False
        if user.has_role('admin') or user.has_role('pm'):
            return True
        return (user.has_role('sales') and
                self._is_related_sales(user) and
                self.status == 'approved')

    def get_effective_points(self):
        """
        取得實際計價用點數：
        custom_points 不為 None 時使用自訂值，否則回傳 items 自動加總
        """
        if self.custom_points is not None:
            return self.custom_points
        return sum(item.total_points for item in self.items)

    def calculate_suggested_price(self):
        # total_points 永遠儲存 items 加總（作為建議參考）
        self.total_points = sum(item.total_points for item in self.items)

        # 計價點數：優先使用 custom_points，否則用 total_points
        billing_points = self.get_effective_points()

        used_ids = {item.function.module_id for item in self.items if item.function}
        self.base_modules_cost = sum(
            m.get_current_price(self.plan_type)
            for m in Module.query.filter(Module.id.in_(used_ids)).all()
        )
        from app.models.product import PricingTier
        tier             = PricingTier.get_effective_tier(self.plan_type, billing_points)
        self.points_cost = tier.calculate_total_price(billing_points) if tier else 0
        base             = self.base_modules_cost + self.points_cost
        self.suggested_price = int(base * self.plan_years if self.plan_type == 'yearly' else base)
        return self.suggested_price

    def calculate_labor_suggested_price(self):
        if not self.final_price:
            self.labor_suggested_price = 0
            return 0
        self.labor_suggested_price = int(self.final_price * 0.1 + self.final_price * 0.05 * self.plan_years)
        if not self.final_maintenance_price:
            self.final_maintenance_price = self.labor_suggested_price
            self._recalc_maintenance_discount()
        return self.labor_suggested_price

    def _recalc_maintenance_discount(self):
        if self.labor_suggested_price > 0 and self.final_maintenance_price is not None:
            self.maintenance_discount_rate = self.final_maintenance_price / self.labor_suggested_price
        else:
            self.maintenance_discount_rate = None

    def update_final_price(self, final_price, user_id):
        self.final_price    = final_price
        self.discount_rate  = final_price / self.suggested_price if self.suggested_price else 1.0
        self.calculate_labor_suggested_price()
        self.reviewed_by_id = user_id
        self.reviewed_at    = datetime.utcnow()

    def update_price_only(self, user_id, final_price=None, discount_rate=None,
                          final_maintenance_price=None, maintenance_discount_rate=None, notes=None):
        if final_price is not None:
            self.update_final_price(final_price, user_id)
        elif discount_rate is not None:
            self.discount_rate = max(0.0, min(2.0, discount_rate))
            self.final_price   = int(self.suggested_price * self.discount_rate)
            self.calculate_labor_suggested_price()
        if final_maintenance_price is not None:
            self.final_maintenance_price = final_maintenance_price
            self._recalc_maintenance_discount()
        elif maintenance_discount_rate is not None:
            self.maintenance_discount_rate = max(0.0, min(2.0, maintenance_discount_rate))
            if self.labor_suggested_price:
                self.final_maintenance_price = int(self.labor_suggested_price * self.maintenance_discount_rate)
        db.session.add(BOMReviewHistory(
            bom_id=self.id, action='update_price',
            previous_status=self.status, new_status=self.status,
            reviewed_by_id=user_id, notes=notes,
            final_price=self.final_price, discount_rate=self.discount_rate,
            final_maintenance_price=self.final_maintenance_price,
            maintenance_discount_rate=self.maintenance_discount_rate,
        ))

    def approve(self, user_id, notes=None, final_price=None, final_maintenance_price=None):
        prev              = self.status
        self.status       = 'approved'
        self.reviewed_by_id = user_id
        self.reviewed_at  = datetime.utcnow()
        if notes:
            self.review_notes = notes
        if final_price is not None:
            self.update_final_price(final_price, user_id)
        if final_maintenance_price is not None:
            self.final_maintenance_price = final_maintenance_price
            self._recalc_maintenance_discount()
        db.session.add(BOMReviewHistory(
            bom_id=self.id, action='approve',
            previous_status=prev, new_status='approved',
            reviewed_by_id=user_id, notes=notes,
            final_price=self.final_price, discount_rate=self.discount_rate,
            final_maintenance_price=self.final_maintenance_price,
            maintenance_discount_rate=self.maintenance_discount_rate,
        ))

    def reject(self, user_id, notes=None):
        prev              = self.status
        self.status       = 'rejected'
        self.reviewed_by_id = user_id
        self.reviewed_at  = datetime.utcnow()
        if notes:
            self.review_notes = notes
        db.session.add(BOMReviewHistory(
            bom_id=self.id, action='reject',
            previous_status=prev, new_status='rejected',
            reviewed_by_id=user_id, notes=notes,
        ))

    def reset_to_pending(self, reset_reason=None, user_id=None):
        prev                = self.status
        self.status         = 'pending'
        self.reviewed_by_id = None
        self.reviewed_at    = None
        self.review_notes   = reset_reason
        self.updated_at     = datetime.utcnow()
        if user_id:
            db.session.add(BOMReviewHistory(
                bom_id=self.id, action='reset',
                previous_status=prev, new_status='pending',
                reviewed_by_id=user_id, notes=reset_reason,
            ))

    def soft_delete(self, user_id):
        self.is_deleted    = True
        self.deleted_at    = datetime.utcnow()
        self.deleted_by_id = user_id

    def __repr__(self):
        return f'<BOM {self.bom_number} - {self.customer_company}>'


class BOMItem(db.Model):
    __tablename__ = 'bom_items'

    id           = db.Column(db.Integer, primary_key=True)
    bom_id       = db.Column(db.Integer, db.ForeignKey('boms.id'),      nullable=False)
    function_id  = db.Column(db.Integer, db.ForeignKey('functions.id'), nullable=False)
    quantity     = db.Column(db.Integer, nullable=False)
    unit_points  = db.Column(db.Integer, nullable=False)
    total_points = db.Column(db.Integer, nullable=False)
    notes        = db.Column(db.Text,    nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    function = db.relationship('Function', backref='bom_items')

    def __init__(self, bom_id, function_id, quantity, notes=None):
        self.bom_id      = bom_id
        self.function_id = function_id
        self.quantity    = quantity
        self.notes       = notes
        func = Function.query.get(function_id)
        if func:
            self.unit_points  = func.points_per_unit
            self.total_points = func.points_per_unit * quantity
        else:
            self.unit_points  = 0
            self.total_points = 0

    def update_quantity(self, new_quantity):
        self.quantity     = new_quantity
        self.total_points = self.unit_points * new_quantity

    def __repr__(self):
        name = self.function.name if self.function else 'Unknown'
        return f'<BOMItem {name} x{self.quantity}>'


class BOMReviewHistory(db.Model):
    __tablename__ = 'bom_review_history'

    id              = db.Column(db.Integer, primary_key=True)
    bom_id          = db.Column(db.Integer, db.ForeignKey('boms.id'),  nullable=False)
    action          = db.Column(db.String(20), nullable=False)
    previous_status = db.Column(db.String(20), nullable=True)
    new_status      = db.Column(db.String(20), nullable=False)
    reviewed_by_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reviewed_at     = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    notes           = db.Column(db.Text,    nullable=True)
    final_price     = db.Column(db.Integer, nullable=True)
    discount_rate   = db.Column(db.Float,   nullable=True)
    final_maintenance_price   = db.Column(db.Integer, nullable=True)
    maintenance_discount_rate = db.Column(db.Float,   nullable=True)

    bom_ref     = db.relationship('BOM',  backref='review_history')
    reviewed_by = db.relationship('User', backref='bom_reviews')

    def __init__(self, bom_id, action, new_status, reviewed_by_id,
                 notes=None, previous_status=None, final_price=None,
                 discount_rate=None, final_maintenance_price=None,
                 maintenance_discount_rate=None):
        self.bom_id                   = bom_id
        self.action                   = action
        self.previous_status          = previous_status
        self.new_status               = new_status
        self.reviewed_by_id           = reviewed_by_id
        self.notes                    = notes
        self.final_price              = final_price
        self.discount_rate            = discount_rate
        self.final_maintenance_price  = final_maintenance_price
        self.maintenance_discount_rate = maintenance_discount_rate

    def get_action_display(self):
        return {'approve': '批准', 'reject': '拒絕', 'update_price': '更新價格', 'reset': '重置狀態'}.get(self.action, self.action)

    def __repr__(self):
        return f'<BOMReviewHistory {self.bom_id} - {self.action}>'


# ── 模組層級工具函數 ──────────────────────────────────────────────────────────

def get_boms_for_user(user, include_deleted=False):
    query = BOM.query
    if not include_deleted:
        query = query.filter_by(is_deleted=False)
    if user.has_role('admin') or user.has_role('pm'):
        return query.order_by(BOM.created_at.desc())
    if user.has_role('sales'):
        return query.filter(
            db.or_(BOM.created_by_id == user.id, BOM.assigned_sales_id == user.id)
        ).order_by(BOM.created_at.desc())
    return query.filter(BOM.id == -1)


def get_bom_statistics_for_user(user):
    if user.has_role('admin') or user.has_role('pm'):
        base = BOM.query.filter_by(is_deleted=False)
    else:
        base = BOM.query.filter(
            db.or_(BOM.created_by_id == user.id, BOM.assigned_sales_id == user.id),
            BOM.is_deleted == False,
        )
    return {
        'total':    base.count(),
        'pending':  base.filter_by(status='pending').count(),
        'approved': base.filter_by(status='approved').count(),
        'rejected': base.filter_by(status='rejected').count(),
    }


def get_pending_boms_count():
    return BOM.query.filter_by(status='pending', is_deleted=False).count()
