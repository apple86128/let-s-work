from datetime import datetime, date
from app.models import db


class Module(db.Model):
    """產品模組模型"""

    __tablename__ = 'modules'

    id                  = db.Column(db.Integer, primary_key=True)
    name                = db.Column(db.String(100), nullable=False)
    code                = db.Column(db.String(20),  unique=True, nullable=False)  # 模組代碼，如 NCA-B
    description         = db.Column(db.Text,        nullable=True)
    base_price_onetime  = db.Column(db.Integer, default=50000,  nullable=False)  # 買斷基礎價格（台幣）
    base_price_yearly   = db.Column(db.Integer, default=240000, nullable=False)  # 訂閱年費（台幣）
    is_active           = db.Column(db.Boolean, default=True,   nullable=False)
    sort_order          = db.Column(db.Integer, default=0,       nullable=False)
    created_at          = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at          = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # 一對多：模組 → 功能
    functions  = db.relationship('Function', backref='module', lazy=True, cascade='all, delete-orphan')
    created_by = db.relationship('User', backref='created_modules')

    def __init__(self, name, code, description=None,
                 base_price_onetime=50000, base_price_yearly=240000,
                 sort_order=0, created_by_id=None):
        self.name               = name
        self.code               = code
        self.description        = description
        self.base_price_onetime = base_price_onetime
        self.base_price_yearly  = base_price_yearly
        self.sort_order         = sort_order
        self.created_by_id      = created_by_id

    def get_active_functions(self):
        """取得此模組下所有啟用的功能"""
        return [f for f in self.functions if f.is_active]

    def get_price(self, plan_type):
        """依方案類型取得模組基礎價格"""
        price_map = {
            'onetime': self.base_price_onetime,
            'yearly':  self.base_price_yearly,
        }
        return price_map.get(plan_type, 0)

    def __repr__(self):
        return f'<Module {self.code} - {self.name}>'


class Function(db.Model):
    """產品功能模型"""

    __tablename__ = 'functions'

    id              = db.Column(db.Integer, primary_key=True)
    module_id       = db.Column(db.Integer, db.ForeignKey('modules.id'), nullable=False)
    name            = db.Column(db.String(100), nullable=False)
    code            = db.Column(db.String(50),  nullable=False)      # 模組內唯一功能代碼
    description     = db.Column(db.Text,        nullable=True)
    points_per_unit = db.Column(db.Integer,     nullable=False)       # 每單位所需點數
    unit_name       = db.Column(db.String(20),  default='台', nullable=False)  # 計量單位
    billing_method  = db.Column(db.String(50),  nullable=True)        # 計費方式說明
    is_active       = db.Column(db.Boolean,     default=True, nullable=False)
    sort_order      = db.Column(db.Integer,     default=0,    nullable=False)
    created_at      = db.Column(db.DateTime,    default=datetime.utcnow, nullable=False)

    # 同一模組內功能代碼不可重複
    __table_args__ = (
        db.UniqueConstraint('module_id', 'code', name='uq_function_code_per_module'),
    )

    def __init__(self, module_id, name, code, points_per_unit,
                 unit_name='台', billing_method=None, description=None, sort_order=0):
        self.module_id       = module_id
        self.name            = name
        self.code            = code
        self.points_per_unit = points_per_unit
        self.unit_name       = unit_name
        self.billing_method  = billing_method
        self.description     = description
        self.sort_order      = sort_order

    def calculate_points(self, quantity):
        """計算指定數量所需的總點數"""
        return self.points_per_unit * quantity

    @property
    def display_name(self):
        """含點數資訊的顯示名稱"""
        return f'{self.name}（{self.points_per_unit} 點/{self.unit_name}）'

    def __repr__(self):
        return f'<Function {self.code} - {self.name}>'


class PricingTier(db.Model):
    """點數價格級距模型"""

    __tablename__ = 'pricing_tiers'

    id              = db.Column(db.Integer, primary_key=True)
    plan_type       = db.Column(db.String(20), nullable=False)        # onetime / yearly
    tier_name       = db.Column(db.String(50), nullable=False)
    min_points      = db.Column(db.Integer,    nullable=False)        # 最低點數
    max_points      = db.Column(db.Integer,    nullable=True)         # 最高點數（NULL 表示無上限）
    price_per_point = db.Column(db.Integer,    nullable=False)        # 每點單價（台幣）
    is_default      = db.Column(db.Boolean,    default=False, nullable=False)
    is_active       = db.Column(db.Boolean,    default=True,  nullable=False)
    effective_date  = db.Column(db.Date, default=date.today,  nullable=False)
    end_date        = db.Column(db.Date, nullable=True)               # NULL 表示目前有效
    created_at      = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_by_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    created_by = db.relationship('User', backref='created_pricing_tiers')

    def __init__(self, plan_type, tier_name, min_points, price_per_point,
                 max_points=None, is_default=False, effective_date=None, created_by_id=None):
        self.plan_type       = plan_type
        self.tier_name       = tier_name
        self.min_points      = min_points
        self.max_points      = max_points
        self.price_per_point = price_per_point
        self.is_default      = is_default
        self.effective_date  = effective_date or date.today()
        self.created_by_id   = created_by_id

    def is_valid_for_points(self, points):
        """檢查點數是否落在此級距範圍內"""
        if points < self.min_points:
            return False
        if self.max_points is not None and points > self.max_points:
            return False
        return True

    def calculate_total_price(self, points):
        """計算指定點數的總價格"""
        if not self.is_valid_for_points(points):
            return 0
        return points * self.price_per_point

    @property
    def range_display(self):
        """級距範圍顯示文字"""
        if self.max_points is None:
            return f'{self.min_points}+ 點'
        return f'{self.min_points}–{self.max_points} 點'

    @classmethod
    def get_effective_tier(cls, plan_type, points, effective_date=None):
        """
        依點數取得當前有效的價格級距
        找不到時 fallback 到預設級距
        """
        target_date = effective_date or date.today()

        tiers = cls.query.filter(
            cls.plan_type      == plan_type,
            cls.is_active      == True,
            cls.effective_date <= target_date,
            db.or_(cls.end_date == None, cls.end_date > target_date)
        ).order_by(cls.min_points.desc()).all()

        for tier in tiers:
            if tier.is_valid_for_points(points):
                return tier

        # fallback：回傳預設級距
        return cls.query.filter_by(
            plan_type=plan_type,
            is_default=True,
            is_active=True
        ).first()

    def __repr__(self):
        return f'<PricingTier {self.plan_type} {self.tier_name}>'


# ---------------------------------------------------------------------------
# 報價計算工具函數
# ---------------------------------------------------------------------------

def calculate_quote_summary(selected_functions):
    """
    計算報價摘要

    參數：
        selected_functions: [{'function_id': 1, 'quantity': 100}, ...]

    回傳：
        {
            'modules': [{'module': Module, 'functions': [...], 'total_points': int}],
            'total_points': int,
            'pricing': {'onetime': {...}, 'yearly': {...}}
        }
    """
    if not selected_functions:
        return {'modules': [], 'total_points': 0, 'pricing': {}}

    # 批次查詢所有相關功能
    function_ids = [item['function_id'] for item in selected_functions]
    function_dict = {
        f.id: f for f in Function.query.filter(Function.id.in_(function_ids)).all()
    }

    # 依模組累計使用情況
    module_usage = {}
    total_points = 0

    for item in selected_functions:
        func = function_dict.get(item['function_id'])
        if not func:
            continue

        quantity = item['quantity']
        points   = func.calculate_points(quantity)
        total_points += points

        if func.module_id not in module_usage:
            module_usage[func.module_id] = {
                'module':        func.module,
                'functions':     [],
                'total_points':  0,
            }

        module_usage[func.module_id]['functions'].append({
            'function': func,
            'quantity': quantity,
            'points':   points,
        })
        module_usage[func.module_id]['total_points'] += points

    # 計算各方案報價
    modules_list = list(module_usage.values())

    def build_plan(plan_type):
        tier         = PricingTier.get_effective_tier(plan_type, total_points)
        points_cost  = tier.calculate_total_price(total_points) if tier else 0
        modules_cost = sum(m['module'].get_price(plan_type) for m in modules_list)
        return {
            'tier':         tier,
            'points_cost':  points_cost,
            'modules_cost': modules_cost,
            'total_cost':   points_cost + modules_cost,
        }

    return {
        'modules':      modules_list,
        'total_points': total_points,
        'pricing': {
            'onetime': build_plan('onetime'),
            'yearly':  build_plan('yearly'),
        }
    }


# ---------------------------------------------------------------------------
# 資料庫初始化輔助函數
# ---------------------------------------------------------------------------

def create_default_modules_and_functions():
    """建立預設模組與功能資料（若已存在則略過）"""

    if Module.query.count() > 0:
        return

    modules_data = [
        {
            'name': '標準監控模組', 'code': 'NCA-B',
            'description': '提供 SNMP、ICMP、HTTP/S 等基礎網路設備監控功能',
            'functions': [
                {'name': 'SNMP 標準網路設備', 'code': 'SNMP_STANDARD', 'points': 10, 'unit': '台'},
                {'name': 'ICMP',              'code': 'ICMP',           'points': 1,  'unit': '台'},
                {'name': 'HTTP/S',            'code': 'HTTPS',          'points': 1,  'unit': '台'},
            ]
        },
        {
            'name': '虛擬化監控模組', 'code': 'NCA-VT',
            'description': '提供 VMware、Nutanix 等虛擬化平台監控功能',
            'functions': [
                {'name': 'VMware 主機監控',  'code': 'VMWARE_HOST',  'points': 10, 'unit': '台'},
                {'name': 'Nutanix 主機監控', 'code': 'NUTANIX_HOST', 'points': 10, 'unit': '台'},
                {'name': '虛擬機監控',       'code': 'VM_MONITOR',   'points': 5,  'unit': '台'},
            ]
        },
        {
            'name': '負載平衡器監控模組', 'code': 'NCA-SLB',
            'description': '提供 F5 等負載平衡器設備監控功能',
            'functions': [
                {'name': 'F5 效能整合監控', 'code': 'F5_MONITOR', 'points': 10, 'unit': '台'},
            ]
        },
        {
            'name': '命令與控制模組', 'code': 'NCA-CC',
            'description': '提供透過 Telnet/SSH 進行設備控制的功能',
            'functions': [
                {'name': 'Telnet/SSH 控制指令', 'code': 'SSH_CONTROL', 'points': 5, 'unit': '台'},
            ]
        },
    ]

    for module_data in modules_data:
        module = Module(
            name        = module_data['name'],
            code        = module_data['code'],
            description = module_data['description'],
        )
        db.session.add(module)
        db.session.flush()  # 取得 module.id

        for i, func_data in enumerate(module_data['functions']):
            db.session.add(Function(
                module_id       = module.id,
                name            = func_data['name'],
                code            = func_data['code'],
                points_per_unit = func_data['points'],
                unit_name       = func_data['unit'],
                sort_order      = i,
            ))

    db.session.commit()
    print('✅ Default modules and functions created')


def create_default_pricing_tiers():
    """建立預設價格級距（若已存在則略過）"""

    if PricingTier.query.count() > 0:
        return

    tiers_data = [
        {'plan_type': 'onetime', 'tier_name': '基礎方案（買斷）',
         'min_points': 0, 'max_points': 5000, 'price_per_point': 500, 'is_default': True},
        {'plan_type': 'yearly',  'tier_name': '基礎方案（訂閱）',
         'min_points': 0, 'max_points': 5000, 'price_per_point': 200, 'is_default': True},
    ]

    for data in tiers_data:
        db.session.add(PricingTier(**data))

    db.session.commit()
    print('✅ Default pricing tiers created')
