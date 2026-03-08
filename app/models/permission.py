from datetime import datetime
from app.models import db


class UserPermission(db.Model):
    """
    使用者個人權限覆寫模型

    用於針對特定使用者追加或拒絕某項權限，
    優先級高於角色預設權限。
    - is_granted = True  → 強制授予（即使角色沒有此權限）
    - is_granted = False → 強制拒絕（即使角色擁有此權限）
    """

    __tablename__ = 'user_permissions'

    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    permission_name = db.Column(db.String(100), nullable=False)   # 對應 utils/permissions.py 的 key
    is_granted      = db.Column(db.Boolean, nullable=False)       # True=授予 / False=拒絕
    granted_by_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    granted_at      = db.Column(db.DateTime, default=datetime.utcnow)
    notes           = db.Column(db.Text, nullable=True)            # 授權備註

    # 授權者關聯（管理員操作紀錄用）
    granted_by = db.relationship('User', foreign_keys=[granted_by_id])

    # 每個使用者的每項權限只允許一筆記錄
    __table_args__ = (
        db.UniqueConstraint('user_id', 'permission_name', name='uq_user_permission'),
    )

    def __init__(self, user_id, permission_name, is_granted, granted_by_id=None, notes=None):
        self.user_id         = user_id
        self.permission_name = permission_name
        self.is_granted      = is_granted
        self.granted_by_id   = granted_by_id
        self.notes           = notes

    @property
    def status_display(self):
        """取得授權狀態中文顯示"""
        return '授予' if self.is_granted else '拒絕'

    @property
    def status_color(self):
        """取得狀態對應的 Bootstrap 顏色"""
        return 'success' if self.is_granted else 'danger'

    def __repr__(self):
        status = 'GRANTED' if self.is_granted else 'DENIED'
        return f'<UserPermission user_id={self.user_id} {self.permission_name} {status}>'
