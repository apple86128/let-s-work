from datetime import datetime, timedelta
from app.models import db


class CustomerBooking(db.Model):
    """客戶預約（Booking）模型 - 商機管理"""

    __tablename__ = 'customer_bookings'

    id = db.Column(db.Integer, primary_key=True)

    # --- 客戶資訊 ---
    company_name    = db.Column(db.String(200), nullable=False)
    company_tax_id  = db.Column(db.String(20),  nullable=True)   # 統一編號（選填）
    contact_person  = db.Column(db.String(100), nullable=True)
    contact_phone   = db.Column(db.String(50),  nullable=True)
    contact_email   = db.Column(db.String(120), nullable=True)

    # --- 專案資訊 ---
    budget_min               = db.Column(db.Integer, nullable=False)
    budget_max               = db.Column(db.Integer, nullable=False)
    project_requirements     = db.Column(db.Text,    nullable=False)
    expected_start_date      = db.Column(db.Date,    nullable=True)
    project_duration_months  = db.Column(db.Integer, nullable=True)

    # --- 狀態管理 ---
    # pending: 審核中 | approved: 已保留 | rejected: 已拒絕 | expired: 已過期
    status = db.Column(db.String(20), default='pending', nullable=False)

    # --- 時間管理 ---
    created_at  = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    valid_until = db.Column(db.DateTime, nullable=False)          # 有效期限

    # --- 使用者關聯 ID ---
    created_by_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigned_sales_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_by_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_at        = db.Column(db.DateTime, nullable=True)
    review_notes       = db.Column(db.Text, nullable=True)

    # --- 軟刪除 ---
    is_deleted     = db.Column(db.Boolean,  default=False, nullable=False)
    deleted_at     = db.Column(db.DateTime, nullable=True)
    deleted_by_id  = db.Column(db.Integer,  db.ForeignKey('users.id'), nullable=True)

    # --- 關聯關係 ---
    created_by     = db.relationship('User', foreign_keys=[created_by_id],     backref='created_bookings')
    assigned_sales = db.relationship('User', foreign_keys=[assigned_sales_id], backref='assigned_bookings')
    reviewed_by    = db.relationship('User', foreign_keys=[reviewed_by_id],    backref='reviewed_bookings')
    deleted_by     = db.relationship('User', foreign_keys=[deleted_by_id])

    extension_requests = db.relationship(
        'BookingExtensionRequest',
        backref='booking',
        lazy=True,
        cascade='all, delete-orphan'
    )

    def __init__(self, company_name, budget_min, budget_max, project_requirements,
                 created_by_id, company_tax_id=None, contact_person=None,
                 contact_phone=None, contact_email=None, expected_start_date=None,
                 project_duration_months=None, assigned_sales_id=None):

        self.company_name           = company_name
        self.company_tax_id         = company_tax_id
        self.contact_person         = contact_person
        self.contact_phone          = contact_phone
        self.contact_email          = contact_email
        self.budget_min             = budget_min
        self.budget_max             = budget_max
        self.project_requirements   = project_requirements
        self.expected_start_date    = expected_start_date
        self.project_duration_months = project_duration_months
        self.created_by_id          = created_by_id
        self.assigned_sales_id      = assigned_sales_id or created_by_id  # 預設指派給建立者
        self.valid_until            = datetime.utcnow() + timedelta(days=90)  # 預設 90 天有效期

    # --- 狀態顯示 Property ---

    STATUS_DISPLAY = {
        'pending':  ('審核中', 'warning'),
        'approved': ('已保留', 'success'),
        'rejected': ('已拒絕', 'danger'),
        'expired':  ('已過期', 'secondary'),
    }

    @property
    def status_display(self):
        """取得狀態中文顯示"""
        return self.STATUS_DISPLAY.get(self.status, ('未知狀態', 'secondary'))[0]

    @property
    def status_color(self):
        """取得狀態對應的 Bootstrap 顏色"""
        return self.STATUS_DISPLAY.get(self.status, ('未知狀態', 'secondary'))[1]

    @property
    def budget_display(self):
        """取得預算上限顯示文字"""
        return f'NT$ {self.budget_max:,}'

    # --- 期限計算 ---

    def is_expired(self):
        """檢查是否已過期"""
        return datetime.utcnow() > self.valid_until

    def days_until_expiry(self):
        """距離過期還有幾天（已過期回傳 0）"""
        if self.is_expired():
            return 0
        return (self.valid_until - datetime.utcnow()).days

    def can_request_extension(self):
        """檢查是否可以申請展延（已保留且 100 天內到期）"""
        return (
            self.status == 'approved'
            and self.days_until_expiry() <= 100
            and not self.is_deleted
        )

    # --- 權限判斷 ---

    def can_be_edited_by(self, user):
        """檢查指定使用者是否可編輯此 Booking"""
        if not user or self.is_deleted:
            return False

        if user.has_role('admin') or user.has_role('pm'):
            return True

        if not user.has_role('sales'):
            return False

        is_creator  = self.created_by_id     == user.id
        is_assigned = self.assigned_sales_id == user.id

        if not (is_creator or is_assigned):
            return False

        # pending 狀態皆可編輯；approved 狀態僅指派業務可編輯
        if self.status == 'pending':
            return True
        if self.status == 'approved' and is_assigned:
            return True

        return False

    def can_be_reviewed_by(self, user):
        """檢查指定使用者是否可審核此 Booking"""
        return (
            user is not None
            and (user.has_role('admin') or user.has_role('pm'))
            and self.status == 'pending'
        )

    # --- 狀態操作 ---

    def approve(self, user_id, notes=None):
        """批准 Booking"""
        self.status        = 'approved'
        self.reviewed_by_id = user_id
        self.reviewed_at   = datetime.utcnow()
        if notes:
            self.review_notes = notes

    def reject(self, user_id, notes=None):
        """拒絕 Booking"""
        self.status        = 'rejected'
        self.reviewed_by_id = user_id
        self.reviewed_at   = datetime.utcnow()
        if notes:
            self.review_notes = notes

    def extend_validity(self, days, user_id):
        """延長有效期"""
        self.valid_until   = self.valid_until + timedelta(days=days)
        self.reviewed_by_id = user_id
        self.reviewed_at   = datetime.utcnow()

    def soft_delete(self, user_id):
        """軟刪除"""
        self.is_deleted    = True
        self.deleted_at    = datetime.utcnow()
        self.deleted_by_id = user_id

    def __repr__(self):
        return f'<CustomerBooking {self.company_name} [{self.status}]>'


class BookingExtensionRequest(db.Model):
    """Booking 展延申請模型"""

    __tablename__ = 'booking_extension_requests'

    id         = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('customer_bookings.id'), nullable=False)

    # --- 申請資訊 ---
    requested_days = db.Column(db.Integer, nullable=False)
    reason         = db.Column(db.Text,    nullable=False)

    # --- 申請者 ---
    requested_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    requested_at    = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # --- 審核狀態 ---
    # pending: 待審核 | approved: 已批准 | rejected: 已拒絕
    status          = db.Column(db.String(20), default='pending', nullable=False)
    reviewed_by_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_at     = db.Column(db.DateTime, nullable=True)
    review_notes    = db.Column(db.Text, nullable=True)

    # --- 關聯關係 ---
    requested_by = db.relationship('User', foreign_keys=[requested_by_id])
    reviewed_by  = db.relationship('User', foreign_keys=[reviewed_by_id])

    def __init__(self, booking_id, requested_days, reason, requested_by_id):
        self.booking_id      = booking_id
        self.requested_days  = requested_days
        self.reason          = reason
        self.requested_by_id = requested_by_id

    STATUS_DISPLAY = {
        'pending':  ('待審核', 'warning'),
        'approved': ('已批准', 'success'),
        'rejected': ('已拒絕', 'danger'),
    }

    @property
    def status_display(self):
        return self.STATUS_DISPLAY.get(self.status, ('未知狀態', 'secondary'))[0]

    @property
    def status_color(self):
        return self.STATUS_DISPLAY.get(self.status, ('未知狀態', 'secondary'))[1]

    def approve(self, user_id, notes=None):
        """批准展延申請，同步延長 Booking 有效期"""
        self.status        = 'approved'
        self.reviewed_by_id = user_id
        self.reviewed_at   = datetime.utcnow()
        if notes:
            self.review_notes = notes
        self.booking.extend_validity(self.requested_days, user_id)

    def reject(self, user_id, notes=None):
        """拒絕展延申請"""
        self.status        = 'rejected'
        self.reviewed_by_id = user_id
        self.reviewed_at   = datetime.utcnow()
        if notes:
            self.review_notes = notes

    def __repr__(self):
        return f'<BookingExtensionRequest booking_id={self.booking_id} days={self.requested_days}>'


# ---------------------------------------------------------------------------
# 查詢工具函數
# ---------------------------------------------------------------------------

def get_bookings_for_user(user, include_deleted=False):
    """依使用者角色取得可查看的 Booking 列表"""
    query = CustomerBooking.query

    if not include_deleted:
        query = query.filter_by(is_deleted=False)

    if user.has_role('admin') or user.has_role('pm'):
        return query.order_by(CustomerBooking.created_at.desc())

    if user.has_role('sales'):
        return query.filter(
            db.or_(
                CustomerBooking.created_by_id     == user.id,
                CustomerBooking.assigned_sales_id == user.id
            )
        ).order_by(CustomerBooking.created_at.desc())

    # 其他角色無查看權限，回傳空結果
    return query.filter(CustomerBooking.id == -1)


def get_pending_bookings_count():
    """取得待審核 Booking 數量（供 Dashboard 顯示）"""
    return CustomerBooking.query.filter_by(status='pending', is_deleted=False).count()


def get_expiring_bookings(days=7):
    """取得即將在指定天數內過期的 Booking"""
    expiry_threshold = datetime.utcnow() + timedelta(days=days)
    return CustomerBooking.query.filter(
        CustomerBooking.status     == 'approved',
        CustomerBooking.is_deleted == False,
        CustomerBooking.valid_until <= expiry_threshold,
        CustomerBooking.valid_until >  datetime.utcnow()
    ).all()


def update_expired_bookings():
    """將已過期的 Booking 狀態更新為 expired，回傳更新筆數"""
    expired = CustomerBooking.query.filter(
        CustomerBooking.status     == 'approved',
        CustomerBooking.valid_until < datetime.utcnow()
    ).all()

    for booking in expired:
        booking.status = 'expired'

    if expired:
        db.session.commit()

    return len(expired)
