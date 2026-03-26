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

    # BOM 審核狀態（既有）
    status         = db.Column(db.String(20), default='pending', nullable=False)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_at    = db.Column(db.DateTime, nullable=True)
    review_notes   = db.Column(db.Text,     nullable=True)

    # ── 專案狀態（新增）────────────────────────────────────────────────────────
    # 獨立於審核流程，由 PM/Admin 用來追蹤案件進度
    project_status       = db.Column(db.String(20), default='none', nullable=False)
    project_close_reason = db.Column(db.Text, nullable=True)  # 終結時的原因備註（選填）
    won_at               = db.Column(db.DateTime, nullable=True)  # 狀態變更為 won 時自動記錄，供 KPI 季度歸屬使用
    # ──────────────────────────────────────────────────────────────────────────

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

    # 審核狀態對照表
    STATUS_DISPLAY = {
        'pending':  '待審核',
        'approved': '已批准',
        'rejected': '已拒絕',
    }

    # 專案狀態對照表
    PROJECT_STATUS_DISPLAY = {
        'none':    '未設定',
        'poc':     'POC 進行中',
        'bidding': '備標中',
        'won':     '已成案',
        'closed':  '已終結',
    }

    # 專案狀態對應 Bootstrap 顏色
    PROJECT_STATUS_COLOR = {
        'none':    'secondary',
        'poc':     'info',
        'bidding': 'warning',
        'won':     'success',
        'closed':  'dark',
    }

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

    # ── 審核狀態方法（既有）──────────────────────────────────────────────────

    def get_status_display(self):
        return self.STATUS_DISPLAY.get(self.status, '未知狀態')

    def get_status_color(self):
        return {'pending': 'warning', 'approved': 'success', 'rejected': 'danger'}.get(self.status, 'secondary')

    # ── 專案狀態方法（新增）──────────────────────────────────────────────────

    def get_project_status_display(self):
        """回傳專案狀態的中文名稱"""
        return self.PROJECT_STATUS_DISPLAY.get(self.project_status, '未知')

    def get_project_status_color(self):
        """回傳專案狀態對應的 Bootstrap 顏色字串"""
        return self.PROJECT_STATUS_COLOR.get(self.project_status, 'secondary')

    def update_project_status(self, new_status, close_reason=None):
        """
        更新專案狀態。
        - 變更為 won 時自動記錄 won_at（供 KPI 季度歸屬使用）
        - 從 won 切換到其他狀態時清除 won_at
        - 變更為 closed 時可附帶原因備註；其他狀態自動清除備註
        """
        self.project_status       = new_status
        self.project_close_reason = close_reason if new_status == 'closed' else None
        self.won_at               = datetime.utcnow() if new_status == 'won' else None

    # ── 其他既有方法 ─────────────────────────────────────────────────────────

    def get_plan_type_display(self):
        if self.plan_type == 'onetime':
            return f'買斷方案（{self.plan_years} 年維護）'
        return f'訂閱方案（{self.plan_years} 年）'

    def is_protected(self):
        return self.source_type == 'from_booking' and self.booking_id is not None

    def get_assigned_sales_info(self):
        if self.assigned_sales:
            return {
                'name':  self.assigned_sales.name,
                'email': self.assigned_sales.email,
            }
        return None

    def get_effective_points(self):
        """取得計價點數：優先使用 custom_points，否則用 total_points"""
        return self.custom_points if self.custom_points is not None else self.total_points

    def calculate_suggested_price(self):
        """重新計算建議售價並寫回欄位"""
        from app.models.product import PricingTier

        modules_used = {
            item.function.module
            for item in self.items
            if item.function and item.function.module
        }

        self.total_points = sum(item.total_points for item in self.items)

        modules_cost = sum(
            m.base_price_onetime if self.plan_type == 'onetime' else (m.base_price_yearly or 0)
            for m in modules_used
        )

        billing_points = self.get_effective_points()
        tier           = PricingTier.get_effective_tier(self.plan_type, billing_points)
        points_cost    = tier.calculate_total_price(billing_points) if tier else billing_points * 1000
        base_price     = modules_cost + points_cost

        self.base_modules_cost = modules_cost
        self.points_cost       = points_cost
        self.suggested_price   = base_price * self.plan_years if self.plan_type == 'yearly' else base_price

    def can_be_edited_by(self, user):
        """判斷使用者是否可以編輯此 BOM"""
        if user.has_role('admin') or user.has_role('pm'):
            return True
        if self.status != 'pending':
            return False
        return self.created_by_id == user.id or self.assigned_sales_id == user.id

    def can_be_viewed_by(self, user):
        """判斷使用者是否可以查看此 BOM"""
        if user.has_role('admin') or user.has_role('pm'):
            return True
        return self.created_by_id == user.id or self.assigned_sales_id == user.id

    def can_be_reviewed_by(self, user):
        """判斷使用者是否可以審核此 BOM"""
        return user.has_role('admin') or user.has_role('pm')

    def approve(self, reviewer_id, notes=None, final_price=None,
                discount_rate=None, final_maintenance_price=None,
                maintenance_discount_rate=None):
        self.status         = 'approved'
        self.reviewed_by_id = reviewer_id
        self.reviewed_at    = datetime.utcnow()
        self.review_notes   = notes
        if final_price is not None:
            self.final_price  = final_price
        if discount_rate is not None:
            self.discount_rate = discount_rate
        if final_maintenance_price is not None:
            self.final_maintenance_price = final_maintenance_price
        if maintenance_discount_rate is not None:
            self.maintenance_discount_rate = maintenance_discount_rate

        from app.models.bom import BOMReviewHistory
        db.session.add(BOMReviewHistory(
            bom_id=self.id, action='approve', previous_status='pending',
            new_status='approved', reviewed_by_id=reviewer_id, notes=notes,
            final_price=final_price, discount_rate=discount_rate,
            final_maintenance_price=final_maintenance_price,
            maintenance_discount_rate=maintenance_discount_rate,
        ))

    def reject(self, reviewer_id, notes=None):
        self.status         = 'rejected'
        self.reviewed_by_id = reviewer_id
        self.reviewed_at    = datetime.utcnow()
        self.review_notes   = notes

        from app.models.bom import BOMReviewHistory
        db.session.add(BOMReviewHistory(
            bom_id=self.id, action='reject', previous_status='pending',
            new_status='rejected', reviewed_by_id=reviewer_id, notes=notes,
        ))

    def reset_to_pending(self, reason=None, user_id=None):
        prev             = self.status
        self.status      = 'pending'
        self.reviewed_by_id = None
        self.reviewed_at    = None
        self.review_notes   = None
        self.final_price    = None
        self.discount_rate  = None
        self.final_maintenance_price   = None
        self.maintenance_discount_rate = None

        if user_id:
            from app.models.bom import BOMReviewHistory
            db.session.add(BOMReviewHistory(
                bom_id=self.id, action='reset', previous_status=prev,
                new_status='pending', reviewed_by_id=user_id, notes=reason,
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
        self.bom_id                    = bom_id
        self.action                    = action
        self.previous_status           = previous_status
        self.new_status                = new_status
        self.reviewed_by_id            = reviewed_by_id
        self.notes                     = notes
        self.final_price               = final_price
        self.discount_rate             = discount_rate
        self.final_maintenance_price   = final_maintenance_price
        self.maintenance_discount_rate = maintenance_discount_rate

    def get_action_display(self):
        return {
            'approve':      '批准',
            'reject':       '拒絕',
            'update_price': '更新價格',
            'reset':        '重置狀態',
        }.get(self.action, self.action)

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
