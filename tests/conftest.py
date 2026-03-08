"""
conftest.py - pytest 核心 Fixtures
====================================
Flask-SQLAlchemy 3.x 相容版本

主要修正：
  - 移除 create_scoped_session（Flask-SQLAlchemy 3.x 已移除）
  - 改用「每次測試後刪除所有資料列」的隔離策略
"""

import pytest

from app import create_app
from app.models import db as _db
from app.models.user import User, Role
from app.models.booking import CustomerBooking
from app.models.bom import BOM, BOMItem
from app.models.product import Module, Function, PricingTier


# ---------------------------------------------------------------------------
# Flask App & DB Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope='session')
def app():
    """
    建立測試用 Flask app（session 級別，整個測試過程只建立一次）
    使用 TestingConfig：記憶體 SQLite + 關閉 CSRF
    """
    flask_app = create_app('testing')

    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.drop_all()


@pytest.fixture(scope='function')
def db(app):
    """
    每個測試函數取得 db，測試結束後刪除所有資料列保持乾淨。

    Flask-SQLAlchemy 3.x 移除了 create_scoped_session，
    改用逐表 DELETE 的方式清除資料，簡單可靠。
    """
    with app.app_context():
        yield _db

        # 測試結束：依 FK 反向順序刪除所有資料列
        _db.session.remove()
        for table in reversed(_db.metadata.sorted_tables):
            _db.session.execute(table.delete())
        _db.session.commit()


@pytest.fixture(scope='function')
def client(app, db):
    """Flask 測試用 HTTP Client（每個測試都是乾淨的 session）"""
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# 使用者建立工具
# ---------------------------------------------------------------------------

def _get_or_create_role(name, display_name=''):
    """取得或建立角色（避免重複）"""
    role = Role.query.filter_by(name=name).first()
    if not role:
        role = Role(name=name, display_name=display_name)
        _db.session.add(role)
        _db.session.flush()
    return role


def _make_user(email, name, password, role_name, role_display=''):
    """建立測試用使用者的工具函數"""
    role = _get_or_create_role(role_name, role_display)
    user = User(email=email, name=name, password=password)
    user.roles.append(role)
    _db.session.add(user)
    _db.session.flush()
    return user


# ---------------------------------------------------------------------------
# 使用者 Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_user(db):
    """測試用 admin 帳號"""
    return _make_user(
        email='admin@test.com', name='測試管理員',
        password='Test@1234',
        role_name='admin', role_display='管理層'
    )


@pytest.fixture
def pm_user(db):
    """測試用 pm 帳號"""
    return _make_user(
        email='pm@test.com', name='測試產品經理',
        password='Test@1234',
        role_name='pm', role_display='產品經理'
    )


@pytest.fixture
def sales_user(db):
    """測試用 sales 帳號"""
    return _make_user(
        email='sales@test.com', name='測試業務',
        password='Test@1234',
        role_name='sales', role_display='業務人員'
    )


@pytest.fixture
def engineer_user(db):
    """測試用 engineer 帳號"""
    return _make_user(
        email='engineer@test.com', name='測試工程師',
        password='Test@1234',
        role_name='engineer', role_display='工程師'
    )


@pytest.fixture
def inactive_user(db):
    """已停用帳號，測試停用後無法登入"""
    role = _get_or_create_role('sales', '業務人員')
    user = User(email='inactive@test.com', name='已停用帳號', password='Test@1234')
    user.roles.append(role)
    user.is_active = False
    _db.session.add(user)
    _db.session.flush()
    return user


# ---------------------------------------------------------------------------
# 登入工具 & 已登入 Client Fixtures
# ---------------------------------------------------------------------------

def _do_login(client, email, password):
    """執行登入 POST"""
    return client.post('/auth/login', data={
        'email':    email,
        'password': password,
    }, follow_redirects=True)


@pytest.fixture
def logged_in_admin(client, admin_user):
    """已登入 admin 的 test client"""
    _do_login(client, admin_user.email, 'Test@1234')
    return client


@pytest.fixture
def logged_in_pm(client, pm_user):
    """已登入 pm 的 test client"""
    _do_login(client, pm_user.email, 'Test@1234')
    return client


@pytest.fixture
def logged_in_sales(client, sales_user):
    """已登入 sales 的 test client"""
    _do_login(client, sales_user.email, 'Test@1234')
    return client


@pytest.fixture
def logged_in_engineer(client, engineer_user):
    """已登入 engineer 的 test client"""
    _do_login(client, engineer_user.email, 'Test@1234')
    return client


# ---------------------------------------------------------------------------
# 測試資料 Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_module(db):
    """測試用產品模組"""
    module = Module(
        name               = '測試模組',
        code               = 'TESTMOD',
        description        = '自動化測試用模組',
        base_price_onetime = 50000,
        base_price_yearly  = 240000,
        sort_order         = 0,
    )
    _db.session.add(module)
    _db.session.flush()
    return module


@pytest.fixture
def sample_function(db, sample_module):
    """測試用產品功能（依賴 sample_module）"""
    func = Function(
        module_id       = sample_module.id,
        name            = '測試功能A',
        code            = 'FUNC_A',
        points_per_unit = 10,
        unit_name       = '台',
        sort_order      = 0,
    )
    _db.session.add(func)
    _db.session.flush()
    return func


@pytest.fixture
def sample_pricing_tier(db):
    """測試用價格級距（買斷）"""
    tier = PricingTier(
        plan_type       = 'onetime',
        tier_name       = '標準級距',
        min_points      = 0,
        max_points      = None,
        price_per_point = 1000,
        is_default      = True,
    )
    _db.session.add(tier)
    _db.session.flush()
    return tier


@pytest.fixture
def sample_booking(db, sales_user):
    """測試用 Booking（待審核）"""
    booking = CustomerBooking(
        company_name          = '測試客戶公司',
        contact_person        = '測試聯絡人',
        contact_phone         = '0912-345-678',
        contact_email         = 'client@test.com',
        project_requirements  = '測試專案說明',
        budget_min            = 100000,
        budget_max            = 500000,
        created_by_id         = sales_user.id,
        assigned_sales_id     = sales_user.id,
    )
    _db.session.add(booking)
    _db.session.flush()
    return booking


@pytest.fixture
def approved_booking(db, sample_booking, admin_user):
    """已批准的 Booking"""
    sample_booking.status         = 'approved'
    sample_booking.reviewed_by_id = admin_user.id
    _db.session.flush()
    return sample_booking


@pytest.fixture
def sample_bom(db, sales_user, sample_function, sample_pricing_tier):
    """測試用 BOM（待審核，含一個 BOMItem）"""
    bom = BOM(
        customer_company  = '測試 BOM 客戶',
        project_name      = 'BOM 測試專案',
        customer_contact  = '測試聯絡人',
        plan_type         = 'onetime',
        plan_years        = 1,
        source_type       = 'direct_create',
        created_by_id     = sales_user.id,
        assigned_sales_id = sales_user.id,
        status            = 'pending',
    )
    _db.session.add(bom)
    _db.session.flush()

    item = BOMItem(
        bom_id      = bom.id,
        function_id = sample_function.id,
        quantity    = 3,
    )
    _db.session.add(item)
    bom.calculate_suggested_price()
    _db.session.flush()
    return bom


@pytest.fixture
def approved_bom(db, sample_bom, admin_user):
    """已批准的 BOM"""
    sample_bom.approve(
        reviewer_id = admin_user.id,
        notes       = '測試批准',
        final_price = 100000,
    )
    _db.session.flush()
    return sample_bom
