import os
from datetime import datetime
from app.models import db


class Project(db.Model):
    """專案追蹤模型"""

    __tablename__ = 'projects'

    id          = db.Column(db.Integer, primary_key=True)

    # --- 基本資料 ---
    name        = db.Column(db.String(200), nullable=False)           # 專案名稱
    customer    = db.Column(db.String(200), nullable=False)           # 客戶名稱
    description = db.Column(db.Text,        nullable=True)            # 專案說明/備註

    # --- 來源 ---
    # from_bom: 從 BOM 轉換建立 | direct: 獨立建立
    source_type = db.Column(db.String(20), default='direct', nullable=False)
    bom_id      = db.Column(db.Integer, db.ForeignKey('boms.id'), nullable=True)

    # --- 進度狀態 ---
    # waiting: 等待中 | building: 建置中 | maintaining: 維運中
    # ended: 已結束  | lost: 未得標
    status = db.Column(db.String(20), default='waiting', nullable=False)

    # --- 日期 ---
    start_date    = db.Column(db.Date, nullable=True)   # 起始日期
    expected_end  = db.Column(db.Date, nullable=True)   # 預計結束日期
    actual_end    = db.Column(db.Date, nullable=True)   # 實際結束日期

    # --- 人員關聯 ---
    created_by_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    project_manager_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # --- 時間戳記 ---
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # --- 軟刪除 ---
    is_deleted    = db.Column(db.Boolean,  default=False, nullable=False)
    deleted_at    = db.Column(db.DateTime, nullable=True)
    deleted_by_id = db.Column(db.Integer,  db.ForeignKey('users.id'), nullable=True)

    # --- 關聯 ---
    created_by      = db.relationship('User', foreign_keys=[created_by_id],      backref='created_projects')
    project_manager = db.relationship('User', foreign_keys=[project_manager_id], backref='managed_projects')
    deleted_by      = db.relationship('User', foreign_keys=[deleted_by_id])
    source_bom      = db.relationship('BOM',  foreign_keys=[bom_id],             backref='projects')

    milestones  = db.relationship('ProjectMilestone',  backref='project', lazy=True,
                                  cascade='all, delete-orphan', order_by='ProjectMilestone.due_date')
    members     = db.relationship('ProjectMember',     backref='project', lazy=True,
                                  cascade='all, delete-orphan')
    attachments = db.relationship('ProjectAttachment', backref='project', lazy=True,
                                  cascade='all, delete-orphan', order_by='ProjectAttachment.uploaded_at.desc()')

    # --- 狀態顯示對照表 ---
    STATUS_DISPLAY = {
        'waiting':    ('等待中', 'secondary'),
        'building':   ('建置中', 'primary'),
        'maintaining':('維運中', 'success'),
        'ended':      ('已結束', 'dark'),
        'lost':       ('未得標', 'danger'),
    }

    def __init__(self, name, customer, created_by_id,
                 description=None, source_type='direct', bom_id=None,
                 project_manager_id=None, start_date=None, expected_end=None):
        self.name               = name
        self.customer           = customer
        self.description        = description
        self.source_type        = source_type
        self.bom_id             = bom_id
        self.project_manager_id = project_manager_id
        self.start_date         = start_date
        self.expected_end       = expected_end
        self.created_by_id      = created_by_id

    @property
    def status_display(self):
        return self.STATUS_DISPLAY.get(self.status, ('未知', 'secondary'))[0]

    @property
    def status_color(self):
        return self.STATUS_DISPLAY.get(self.status, ('未知', 'secondary'))[1]

    def get_status_display(self):
        """供 template 呼叫"""
        return self.status_display

    def get_status_color(self):
        """供 template 呼叫"""
        return self.status_color

    def get_member_users(self):
        """取得所有成員的 User 物件"""
        return [m.user for m in self.members if m.user]

    def is_member(self, user):
        """檢查 user 是否為專案成員"""
        return any(m.user_id == user.id for m in self.members)

    # --- 權限判斷 ---

    def _is_related(self, user):
        """user 是否為 PM 或成員"""
        return self.project_manager_id == user.id or self.is_member(user)

    def can_be_viewed_by(self, user):
        if not user or self.is_deleted:
            return False
        if user.has_role('admin') or user.has_role('pm'):
            return True
        if user.has_role('project_manager'):
            return self.project_manager_id == user.id
        if user.has_role('engineer'):
            return self.is_member(user)
        return False

    def can_be_edited_by(self, user):
        if not user or self.is_deleted:
            return False
        if user.has_role('admin') or user.has_role('pm'):
            return True
        return user.has_role('project_manager') and self.project_manager_id == user.id

    def can_update_status_by(self, user):
        """engineer 可更新進度，project_manager / admin / pm 也可"""
        if not user or self.is_deleted:
            return False
        if user.has_role('admin') or user.has_role('pm'):
            return True
        if user.has_role('project_manager') and self.project_manager_id == user.id:
            return True
        return user.has_role('engineer') and self.is_member(user)

    def can_upload_attachment_by(self, user):
        """與 can_update_status_by 邏輯相同"""
        return self.can_update_status_by(user)

    def can_be_deleted_by(self, user):
        if not user:
            return False
        return user.has_role('admin') or user.has_role('pm')

    def soft_delete(self, user_id):
        self.is_deleted    = True
        self.deleted_at    = datetime.utcnow()
        self.deleted_by_id = user_id

    def __repr__(self):
        return f'<Project {self.name} [{self.status}]>'


class ProjectMilestone(db.Model):
    """專案里程碑"""

    __tablename__ = 'project_milestones'

    id         = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)

    name         = db.Column(db.String(200), nullable=False)   # 里程碑名稱
    due_date     = db.Column(db.Date,        nullable=True)    # 預計日期
    completed_at = db.Column(db.Date,        nullable=True)    # 實際完成日期

    # pending: 未完成 | completed: 已完成 | delayed: 延遲
    status = db.Column(db.String(20), default='pending', nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    STATUS_DISPLAY = {
        'pending':   ('未完成', 'warning'),
        'completed': ('已完成', 'success'),
        'delayed':   ('延遲',   'danger'),
    }

    def __init__(self, project_id, name, due_date=None, status='pending'):
        self.project_id = project_id
        self.name       = name
        self.due_date   = due_date
        self.status     = status

    @property
    def status_display(self):
        return self.STATUS_DISPLAY.get(self.status, ('未知', 'secondary'))[0]

    @property
    def status_color(self):
        return self.STATUS_DISPLAY.get(self.status, ('未知', 'secondary'))[1]

    def __repr__(self):
        return f'<ProjectMilestone {self.name} [{self.status}]>'


class ProjectMember(db.Model):
    """專案成員（engineer）"""

    __tablename__ = 'project_members'

    id         = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'),    nullable=False)
    joined_at  = db.Column(db.DateTime, default=datetime.utcnow,    nullable=False)

    # 同一專案不重複加入同一成員
    __table_args__ = (
        db.UniqueConstraint('project_id', 'user_id', name='uq_project_member'),
    )

    user = db.relationship('User', backref='project_memberships')

    def __init__(self, project_id, user_id):
        self.project_id = project_id
        self.user_id    = user_id

    def __repr__(self):
        return f'<ProjectMember project={self.project_id} user={self.user_id}>'


class ProjectAttachment(db.Model):
    """專案附件"""

    __tablename__ = 'project_attachments'

    id         = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)

    filename      = db.Column(db.String(255), nullable=False)   # 原始檔名（顯示用）
    stored_name   = db.Column(db.String(255), nullable=False)   # 伺服器儲存的檔名（uuid）
    file_size     = db.Column(db.Integer,     nullable=True)    # 檔案大小（bytes）
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at   = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    uploaded_by = db.relationship('User', backref='project_attachments')

    def __init__(self, project_id, filename, stored_name, uploaded_by_id, file_size=None):
        self.project_id      = project_id
        self.filename        = filename
        self.stored_name     = stored_name
        self.uploaded_by_id  = uploaded_by_id
        self.file_size       = file_size

    @property
    def file_size_display(self):
        """人類可讀的檔案大小"""
        if not self.file_size:
            return '-'
        if self.file_size < 1024:
            return f'{self.file_size} B'
        if self.file_size < 1024 * 1024:
            return f'{self.file_size / 1024:.1f} KB'
        return f'{self.file_size / 1024 / 1024:.1f} MB'

    def __repr__(self):
        return f'<ProjectAttachment {self.filename}>'


# ---------------------------------------------------------------------------
# 查詢工具函數
# ---------------------------------------------------------------------------

def get_projects_for_user(user, include_deleted=False):
    """依角色取得可查看的專案列表"""
    query = Project.query

    if not include_deleted:
        query = query.filter_by(is_deleted=False)

    if user.has_role('admin') or user.has_role('pm'):
        return query.order_by(Project.created_at.desc())

    if user.has_role('project_manager'):
        return query.filter(
            Project.project_manager_id == user.id
        ).order_by(Project.created_at.desc())

    if user.has_role('engineer'):
        return query.join(ProjectMember).filter(
            ProjectMember.user_id == user.id
        ).order_by(Project.created_at.desc())

    return query.filter(Project.id == -1)
