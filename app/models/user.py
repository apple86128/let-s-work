from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.models import db


# 使用者與角色的多對多關聯表
user_roles = db.Table(
    'user_roles',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id'), primary_key=True)
)


class User(UserMixin, db.Model):
    """使用者模型"""

    __tablename__ = 'users'

    id           = db.Column(db.Integer, primary_key=True)
    email        = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    name         = db.Column(db.String(100), nullable=False)
    extension    = db.Column(db.String(20), nullable=True)   # 分機號碼，業務人員專用
    is_active    = db.Column(db.Boolean, default=True, nullable=False)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    last_login   = db.Column(db.DateTime, nullable=True)

    # 多對多：使用者 ↔ 角色
    roles = db.relationship(
        'Role',
        secondary=user_roles,
        lazy='subquery',
        backref=db.backref('users', lazy=True)
    )

    # 一對多：使用者 → 自訂權限（定義於 permission.py）
    custom_permissions = db.relationship(
        'UserPermission',
        foreign_keys='UserPermission.user_id',
        backref='user',
        lazy=True,
        cascade='all, delete-orphan'
    )

    def __init__(self, email, name, password=None, extension=None):
        self.email = email
        self.name = name
        self.extension = extension
        if password:
            self.set_password(password)

    # --- 密碼管理 ---

    def set_password(self, password):
        """設定密碼（自動雜湊加密）"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """驗證密碼是否正確"""
        return check_password_hash(self.password_hash, password)

    # --- 角色查詢 ---

    def has_role(self, role_name):
        """檢查使用者是否擁有指定角色"""
        return any(role.name == role_name for role in self.roles)

    def get_role_names(self):
        """取得所有角色名稱列表"""
        return [role.name for role in self.roles]

    def get_primary_role(self):
        """取得主要角色（列表中第一個）"""
        return self.roles[0] if self.roles else None

    # --- 登入記錄 ---

    def update_last_login(self):
        """更新最後登入時間"""
        self.last_login = datetime.utcnow()
        db.session.commit()

    def __repr__(self):
        return f'<User {self.email}>'


class Role(db.Model):
    """角色模型"""

    __tablename__ = 'roles'

    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(50), unique=True, nullable=False)
    display_name = db.Column(db.String(100), nullable=False)   # 中文顯示名稱
    description  = db.Column(db.Text, nullable=True)
    is_active    = db.Column(db.Boolean, default=True, nullable=False)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, name, display_name, description=None):
        self.name = name
        self.display_name = display_name
        self.description = description

    def __repr__(self):
        return f'<Role {self.name}>'


class UserSession(db.Model):
    """使用者登入 Session 記錄，用於追蹤登入歷史"""

    __tablename__ = 'user_sessions'

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    login_time  = db.Column(db.DateTime, default=datetime.utcnow)
    logout_time = db.Column(db.DateTime, nullable=True)
    ip_address  = db.Column(db.String(45), nullable=True)   # 支援 IPv6 長度
    user_agent  = db.Column(db.Text, nullable=True)
    is_active   = db.Column(db.Boolean, default=True)

    user = db.relationship('User', backref=db.backref('sessions', lazy=True))

    def __repr__(self):
        return f'<UserSession user_id={self.user_id} login={self.login_time}>'


# ---------------------------------------------------------------------------
# 資料庫初始化輔助函數
# ---------------------------------------------------------------------------

def create_default_roles():
    """建立系統預設角色（若已存在則略過）"""

    default_roles = [
        ('admin',           '管理層',     '系統管理員，擁有全部權限'),
        ('pm',              '產品經理',   '負責 BOM 審查與報價批核'),
        ('project_manager', '專案管理員', '負責專案成員指派與派工管理'),
        ('engineer',        '工程師',     '負責工單執行與產品報告'),
        ('sales',           '業務人員',   '負責客戶 Booking 與 BOM 提交'),
    ]

    for name, display_name, description in default_roles:
        if not Role.query.filter_by(name=name).first():
            db.session.add(Role(name=name, display_name=display_name, description=description))

    db.session.commit()
    print("✅ Default roles created")


def create_default_users():
    """建立系統預設使用者帳號（若已存在則略過）"""

    default_users = [
        ('admin@company.com',   '系統管理員', 'admin123',   'admin'),
        ('pm@company.com',      '產品經理',   'pm123',      'pm'),
        ('project@company.com', '專案管理員', 'project123', 'project_manager'),
        ('engineer@company.com','工程師',     'engineer123','engineer'),
    ]

    for email, name, password, role_name in default_users:
        if User.query.filter_by(email=email).first():
            continue

        user = User(email=email, name=name, password=password)
        role = Role.query.filter_by(name=role_name).first()
        if role:
            user.roles.append(role)
        db.session.add(user)

    db.session.commit()
    print("✅ Default users created")
