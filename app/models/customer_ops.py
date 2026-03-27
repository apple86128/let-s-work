from datetime import datetime, date, timedelta
from app.models import db


# =============================================================================
# ContractParent — 合約多對多續約關聯表
# 一張新合約可繼承多張舊合約（例如客戶多次下單後整合為一張新合約）
# =============================================================================

contract_parents = db.Table(
    'contract_parents',
    db.Column(
        'child_contract_id',
        db.Integer,
        db.ForeignKey('account_contracts.id'),
        primary_key=True
    ),
    db.Column(
        'parent_contract_id',
        db.Integer,
        db.ForeignKey('account_contracts.id'),
        primary_key=True
    ),
)


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
    # contracts_all：載入全部合約（含軟刪除），負責 ORM cascade / 寫入
    # contracts    ：property，對外永遠只回傳未軟刪除的合約
    contracts_all = db.relationship(
        'AccountContract',
        backref='account',
        lazy=True,
        foreign_keys='AccountContract.account_id',
        cascade='all, delete-orphan'
    )

    @property
    def contracts(self):
        """對外介面：只回傳未被軟刪除的合約"""
        return [c for c in self.contracts_all if not c.is_deleted]

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

    def _won_boms(self):
        """取得所有專案狀態為「已成案」且未刪除的關聯 BOM"""
        from app.models.bom import BOM
        return BOM.query.filter(
            BOM.customer_company == self.company_name,
            BOM.project_status   == 'won',
            BOM.is_deleted       == False
        ).all()

    @property
    def total_license_value(self):
        """授權金額總計（BOM final_price），僅計入已成案（won）的 BOM"""
        return sum(
            (b.final_price or b.suggested_price or 0)
            for b in self._won_boms()
        )

    @property
    def total_labor_value(self):
        """人力服務金額總計（BOM final_maintenance_price），僅計入已成案（won）的 BOM"""
        return sum(
            (b.final_maintenance_price or b.labor_suggested_price or 0)
            for b in self._won_boms()
        )

    @property
    def total_contribution(self):
        """累積貢獻總值（授權 + 人力）"""
        return self.total_license_value + self.total_labor_value

    @property
    def active_contracts(self):
        """有效合約列表（排除軟刪除）"""
        return [c for c in self.contracts if c.status == 'active']

    @property
    def expiring_soon_contracts(self):
        """
        30 天內即將到期的合約（排除軟刪除、排除已被 renew 的合約）
        已被新合約繼承的舊合約不列入到期警示，避免誤報
        """
        threshold = date.today() + timedelta(days=30)
        return [
            c for c in self.contracts
            if c.status == 'active'
            and c.end_date
            and c.end_date <= threshold
            and not c.has_renewal          # 已被續約的合約不列入
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

    # --- 關聯外鍵 ---
    account_id  = db.Column(db.Integer, db.ForeignKey('customer_accounts.id'), nullable=False)
    bom_id      = db.Column(db.Integer, db.ForeignKey('boms.id'),              nullable=True)

    # --- 合約識別 ---
    contract_number = db.Column(db.String(100), nullable=True)
    project_code    = db.Column(db.String(100), nullable=True)

    # --- 合約期間 ---
    start_date  = db.Column(db.Date, nullable=True)
    end_date    = db.Column(db.Date, nullable=True)

    # --- 授權 KEY（4096 bit 以上長字串，純文字儲存）---
    license_request_code = db.Column(db.Text, nullable=True)
    license_issue_code   = db.Column(db.Text, nullable=True)

    # --- 續約追蹤（舊版單一 FK，保留向後相容）---
    parent_contract_id = db.Column(
        db.Integer,
        db.ForeignKey('account_contracts.id'),
        nullable=True
    )
    contract_type = db.Column(db.String(20), default='new', nullable=False)

    # --- 狀態：active / expired / cancelled ---
    status = db.Column(db.String(20), default='active', nullable=False)

    # --- 時間戳記 ---
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # --- 軟刪除 ---
    is_deleted    = db.Column(db.Boolean,  default=False, nullable=False)
    deleted_at    = db.Column(db.DateTime, nullable=True)
    deleted_by_id = db.Column(db.Integer,  db.ForeignKey('users.id'), nullable=True)
    deleted_by    = db.relationship('User', foreign_keys=[deleted_by_id])

    # --- ORM 關聯 ---
    source_bom = db.relationship('BOM', foreign_keys=[bom_id], backref='contracts')

    # 舊版單張 parent（向後相容，保留不動）
    # child_contracts 不在 relationship 層過濾軟刪除，改在 renewal_chain property 內處理
    parent_contract = db.relationship(
        'AccountContract',
        foreign_keys=[parent_contract_id],
        remote_side='AccountContract.id',
        backref=db.backref('child_contracts', lazy='dynamic')
    )

    # 多對多：本合約繼承的多張舊合約（新架構）
    parent_contracts = db.relationship(
        'AccountContract',
        secondary=contract_parents,
        primaryjoin='AccountContract.id == contract_parents.c.child_contract_id',
        secondaryjoin='AccountContract.id == contract_parents.c.parent_contract_id',
        backref=db.backref('child_contracts_m2m', lazy='dynamic'),
        lazy='dynamic',
    )

    # --- 狀態對照表 ---
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
    # 狀態 property
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
    def has_renewal(self):
        """
        是否已被新合約繼承（已 renew）
        判斷邏輯：多對多 child_contracts_m2m 中有任何一張未軟刪除的子合約
        用於：合約列表顯示「已續約」badge、排除到期統計
        """
        return self.child_contracts_m2m.filter_by(is_deleted=False).count() > 0

    @property
    def active_parent_contracts(self):
        """
        本合約繼承的多張舊合約（排除軟刪除）
        供 template 顯示前一張合約列表使用
        """
        return [c for c in self.parent_contracts if not c.is_deleted]

    @property
    def renewal_chain(self):
        """
        從本合約出發，收集整條續約鏈（含本張）
        回傳由舊到新排列的合約列表。
        注意：多對多情況下鏈狀結構為簡化顯示，取第一個 parent 往上追溯。
        軟刪除的合約在往上找 root 與往下展開時都會被跳過。
        """
        # 往上找 root：優先使用多對多的第一個 parent；退回舊版單一 parent_contract
        def get_parent(contract):
            parents = [c for c in contract.parent_contracts if not c.is_deleted]
            if parents:
                return parents[0]
            if contract.parent_contract and not contract.parent_contract.is_deleted:
                return contract.parent_contract
            return None

        root = self
        visited = set()
        while True:
            p = get_parent(root)
            if p is None or p.id in visited:
                break
            visited.add(p.id)
            root = p

        # 往下走收集鏈：每一層優先取多對多 children
        chain = []
        current = root
        visited_down = set()
        while current and current.id not in visited_down:
            chain.append(current)
            visited_down.add(current.id)
            # 多對多 children
            m2m_children = [
                c for c in current.child_contracts_m2m
                if not c.is_deleted
            ]
            # 舊版 children（向後相容）
            legacy_children = [
                c for c in current.child_contracts
                if not c.is_deleted
            ]
            next_contracts = m2m_children or legacy_children
            current = next_contracts[0] if next_contracts else None

        return chain

    # -------------------------------------------------------------------------
    # 操作方法
    # -------------------------------------------------------------------------

    def set_parent_contracts(self, contract_ids):
        """
        設定本合約繼承的多張舊合約（多對多）
        同時更新舊版 parent_contract_id（取第一個，向後相容）
        contract_ids: list[int]，允許空列表（代表新合約無前身）
        """
        # 清除舊有多對多關聯
        for old_parent in list(self.parent_contracts):
            self.parent_contracts.remove(old_parent)

        if not contract_ids:
            self.parent_contract_id = None
            return

        for cid in contract_ids:
            parent = AccountContract.query.get(cid)
            if parent and not parent.is_deleted:
                self.parent_contracts.append(parent)

        # 舊版相容：取第一個 parent 的 id
        self.parent_contract_id = contract_ids[0]

    def auto_expire(self):
        """若已過到期日，自動更新狀態為 expired"""
        if self.end_date and self.end_date < date.today() and self.status == 'active':
            self.status = 'expired'

    def soft_delete(self, user_id):
        """軟刪除合約（退回用），保留歷史記錄"""
        self.is_deleted    = True
        self.deleted_at    = datetime.utcnow()
        self.deleted_by_id = user_id

    def __repr__(self):
        return f'<AccountContract {self.contract_number or "未填"} [{self.status}]>'
