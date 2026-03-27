from datetime import datetime, date, timedelta
from app.models import db


# =============================================================================
# CustomerAccount — 客戶帳戶（以公司為主體）
# 資料來源引用自 CustomerBooking，不重複儲存公司基本資料
# =============================================================================

class CustomerAccount(db.Model):
    """客戶帳戶模型 — 客戶營運管理的頂層主體"""

    __tablename__ = 'customer_accounts'

    id              = db.Column(db.Integer, primary_key=True)

    # --- 公司基本資料（首次從 Booking 帶入，可後續修改）---
    company_name    = db.Column(db.String(200), nullable=False, unique=True)
    company_tax_id  = db.Column(db.String(20),  nullable=True)
    contact_person  = db.Column(db.String(100), nullable=True)
    contact_phone   = db.Column(db.String(50),  nullable=True)
    contact_email   = db.Column(db.String(120), nullable=True)
    notes           = db.Column(db.Text,        nullable=True)

    # --- 時間戳記 ---
    created_at      = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at      = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # --- 關聯 ---
    contracts       = db.relationship(
        'AccountContract',
        backref='account',
        lazy=True,
        foreign_keys='AccountContract.account_id',
        cascade='all, delete-orphan'
    )

    def __init__(self, company_name, company_tax_id=None,
                 contact_person=None, contact_phone=None,
                 contact_email=None, notes=None):
        self.company_name   = company_name
        self.company_tax_id = company_tax_id
        self.contact_person = contact_person
        self.contact_phone  = contact_phone
        self.contact_email  = contact_email
        self.notes          = notes

    # -------------------------------------------------------------------------
    # Dashboard 統計：授權金額 / 人力金額（從關聯 BOM 加總）
    # -------------------------------------------------------------------------

    def _approved_boms(self):
        """取得所有已批准且未刪除的關聯 BOM"""
        from app.models.bom import BOM
        return BOM.query.filter(
            BOM.customer_company == self.company_name,
            BOM.status == 'approved',
            BOM.is_deleted == False
        ).all()

    @property
    def total_license_value(self):
        """授權金額總計（BOM final_price，不含人力）"""
        return sum(
            (b.final_price or b.suggested_price or 0)
            for b in self._approved_boms()
        )

    @property
    def total_labor_value(self):
        """人力服務金額總計（BOM final_maintenance_price）"""
        return sum(
            (b.final_maintenance_price or b.labor_suggested_price or 0)
            for b in self._approved_boms()
        )

    @property
    def total_contribution(self):
        """累積貢獻總值"""
        return self.total_license_value + self.total_labor_value

    @property
    def active_contracts(self):
        """有效合約列表"""
        return [c for c in self.contracts if c.status == 'active']

    @property
    def expiring_soon_contracts(self):
        """30 天內即將到期的合約"""
        threshold = date.today() + timedelta(days=30)
        return [
            c for c in self.contracts
            if c.status == 'active'
            and c.end_date
            and c.end_date <= threshold
        ]

    def __repr__(self):
        return f'<CustomerAccount {self.company_name}>'


# =============================================================================
# AccountContract — 合約記錄單
# BOM 狀態變更為 won 時自動建立空白合約，等待填寫授權資訊
# =============================================================================

class AccountContract(db.Model):
    """合約記錄單 — 每個成案對應一張，含授權 KEY 與續約追蹤"""

    __tablename__ = 'account_contracts'

    id          = db.Column(db.Integer, primary_key=True)

    # --- 關聯 ---
    account_id  = db.Column(db.Integer, db.ForeignKey('customer_accounts.id'), nullable=False)
    bom_id      = db.Column(db.Integer, db.ForeignKey('boms.id'),              nullable=True)

    # --- 合約識別 ---
    contract_number = db.Column(db.String(100), nullable=True)   # 手動輸入合約代號
    project_code    = db.Column(db.String(100), nullable=True)   # 手動輸入專案代號

    # --- 合約期間 ---
    start_date  = db.Column(db.Date, nullable=True)
    end_date    = db.Column(db.Date, nullable=True)

    # --- 授權 KEY（4096 bit 以上長字串，純文字儲存）---
    license_request_code = db.Column(db.Text, nullable=True)   # 授權請求 CODE
    license_issue_code   = db.Column(db.Text, nullable=True)   # 開立的授權 CODE

    # --- 續約追蹤 ---
    parent_contract_id = db.Column(
        db.Integer,
        db.ForeignKey('account_contracts.id'),
        nullable=True
    )
    # new: 新合約 | renewal: 續約
    contract_type = db.Column(db.String(20), default='new', nullable=False)

    # --- 狀態 ---
    # active: 有效 | expired: 已到期 | cancelled: 已取消
    status = db.Column(db.String(20), default='active', nullable=False)

    # --- 時間戳記 ---
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # --- 關聯 ---
    source_bom = db.relationship('BOM', foreign_keys=[bom_id], backref='contracts')

    # 續約鏈：parent（上一張）← 本張 → children（後續合約）
    parent_contract  = db.relationship(
        'AccountContract',
        foreign_keys=[parent_contract_id],
        remote_side='AccountContract.id',
        backref=db.backref('child_contracts', lazy='dynamic')
    )

    # 狀態對照表
    STATUS_DISPLAY = {
        'active':    ('有效', 'success'),
        'expired':   ('已到期', 'secondary'),
        'cancelled': ('已取消', 'danger'),
    }

    CONTRACT_TYPE_DISPLAY = {
        'new':     '新合約',
        'renewal': '續約',
    }

    def __init__(self, account_id, bom_id=None, contract_type='new',
                 parent_contract_id=None):
        self.account_id         = account_id
        self.bom_id             = bom_id
        self.contract_type      = contract_type
        self.parent_contract_id = parent_contract_id

    # -------------------------------------------------------------------------
    # 狀態判斷
    # -------------------------------------------------------------------------

    @property
    def status_label(self):
        return self.STATUS_DISPLAY.get(self.status, ('未知', 'secondary'))[0]

    @property
    def status_color(self):
        return self.STATUS_DISPLAY.get(self.status, ('未知', 'secondary'))[1]

    @property
    def contract_type_label(self):
        return self.CONTRACT_TYPE_DISPLAY.get(self.contract_type, self.contract_type)

    @property
    def is_expiring_soon(self):
        """是否在 30 天內到期"""
        if not self.end_date or self.status != 'active':
            return False
        return self.end_date <= date.today() + timedelta(days=30)

    @property
    def days_until_expiry(self):
        """距離到期還有幾天（負數表示已過期）"""
        if not self.end_date:
            return None
        return (self.end_date - date.today()).days

    @property
    def has_license_info(self):
        """是否已填入授權資訊"""
        return bool(self.contract_number and self.start_date and self.end_date)

    @property
    def renewal_chain(self):
        """
        從本合約出發，收集整條續約鏈（含本張）
        回傳由舊到新排列的合約列表
        """
        # 先找到最頂層（root）合約
        root = self
        while root.parent_contract:
            root = root.parent_contract

        # 從 root 往下走，收集所有後續合約
        chain = []
        current = root
        while current:
            chain.append(current)
            children = list(current.child_contracts)
            # 每張合約只對應一張後續合約（線性鏈）
            current = children[0] if children else None
        return chain

    def auto_expire(self):
        """若已過到期日，自動更新狀態為 expired"""
        if self.end_date and self.end_date < date.today() and self.status == 'active':
            self.status = 'expired'

    def __repr__(self):
        return f'<AccountContract {self.contract_number or "未填"} [{self.status}]>'
