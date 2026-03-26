from functools import wraps
from flask import abort, flash, redirect, url_for, request
from flask_login import current_user


# ---------------------------------------------------------------------------
# 角色預設權限對應表
# 新增或調整權限只需修改此處，不需要改動其他程式碼
# ---------------------------------------------------------------------------

PERMISSION_MAP = {

    # --- 系統管理 ---
    'system_admin':         ['admin'],
    'product_admin':        ['admin', 'pm'],
    'user_management':      ['admin'],
    'permission_management':['admin'],

    # --- 客戶 Booking 管理 ---
    'booking_create':       ['sales'],
    'booking_edit':         ['sales'],
    'booking_delete':       ['admin'],
    'booking_view_own':     ['sales'],
    'booking_view_all':     ['admin', 'pm', 'project_manager'],
    'booking_export':       ['admin', 'pm', 'sales'],

    # --- BOM 管理 ---
    'bom_create':           ['sales', 'admin', 'pm'],
    'bom_edit':             ['sales'],
    'bom_delete':           ['admin', 'pm'],
    'bom_review':           ['admin', 'pm'],
    'bom_approve':          ['admin', 'pm'],
    'bom_view':             ['sales', 'admin', 'pm'],
    'bom_view_all':         ['admin', 'pm'],
    'bom_reassign':         ['admin', 'pm'],
    'bom_export':           ['admin', 'pm'],

    # --- 報價管理 ---
    'pricing_create':       ['pm'],
    'pricing_review':       ['pm'],
    'pricing_approve':      ['pm'],
    'pricing_reject':       ['pm'],
    'pricing_view':         ['admin', 'pm', 'sales'],
    'pricing_history':      ['admin', 'pm'],
    'pricing_analysis':     ['admin', 'pm'],

    # --- 產品管理 ---
    'product_module_manage':  ['admin', 'pm'],
    'product_function_manage':['admin', 'pm'],
    'product_pricing_manage': ['admin', 'pm'],

    # --- 專案管理（專案追蹤模組） ---
    'project_create':         ['admin', 'pm'],
    'project_edit':           ['admin', 'pm', 'project_manager'],
    'project_delete':         ['admin', 'pm'],
    'project_view_own':       ['project_manager', 'engineer'],
    'project_view_all':       ['admin', 'pm', 'project_manager', 'engineer'],
    'project_manage':         ['project_manager'],
    'project_assign_members': ['admin', 'pm', 'project_manager'],
    'project_close':          ['admin', 'pm', 'project_manager'],
    'project_update_status':  ['admin', 'pm', 'project_manager', 'engineer'],
    'project_milestone_manage':['admin', 'pm', 'project_manager'],
    'project_attachment_upload':['admin', 'pm', 'project_manager', 'engineer'],

    # --- 工單系統 ---
    'workorder_create':     ['engineer'],
    'workorder_edit':       ['engineer'],
    'workorder_delete':     ['admin', 'project_manager'],
    'workorder_assign':     ['project_manager'],
    'workorder_manage':     ['project_manager'],
    'workorder_execute':    ['engineer'],
    'workorder_view_own':   ['engineer'],
    'workorder_view_all':   ['admin', 'pm', 'project_manager'],
    'workorder_close':      ['engineer', 'project_manager'],

    # --- 數據分析 ---
    'analytics_dashboard':  ['admin', 'pm', 'project_manager', 'sales'],
    'analytics_full':       ['admin'],
    'analytics_pricing':    ['admin', 'pm'],
    'analytics_sales':      ['admin', 'pm', 'sales'],
    'analytics_export':     ['admin', 'pm'],

    # --- 系統功能 ---
    'data_export':          ['admin'],
    'data_import':          ['admin'],
    'system_settings':      ['admin'],
    'audit_logs':           ['admin'],
    # --- KPI 績效統計 ---
    'kpi_view':             ['admin', 'pm'],
    'kpi_manage':           ['admin', 'pm'],
}


# ---------------------------------------------------------------------------
# 核心權限檢查函數
# ---------------------------------------------------------------------------

def has_permission(user, permission):
    """
    檢查使用者是否擁有指定權限

    優先級：
    1. 未登入 → False
    2. admin 角色 → 直接 True（最高權限）
    3. 個人客製化權限（UserPermission）→ 覆寫角色預設
    4. 角色預設權限（PERMISSION_MAP）→ 最終判斷
    """
    if not user or not user.is_authenticated:
        return False

    # admin 擁有所有權限
    if user.has_role('admin'):
        return True

    # 檢查個人客製化權限（優先於角色預設）
    if hasattr(user, 'custom_permissions'):
        for perm in user.custom_permissions:
            if perm.permission_name == permission:
                return perm.is_granted   # True=授予 / False=強制拒絕

    # 查詢角色預設權限表
    allowed_roles = PERMISSION_MAP.get(permission)
    if allowed_roles is None:
        return False   # 未定義的權限，預設拒絕

    user_roles = user.get_role_names()
    return any(role in allowed_roles for role in user_roles)


# ---------------------------------------------------------------------------
# 路由裝飾器
# ---------------------------------------------------------------------------

def login_required_with_message(f):
    """確保使用者已登入，否則導向登入頁並顯示提示"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('請先登入系統', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated


def permission_required(permission):
    """
    權限檢查裝飾器

    用法：
        @permission_required('bom_review')
        def my_route():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('請先登入系統', 'warning')
                return redirect(url_for('auth.login', next=request.url))
            if not has_permission(current_user, permission):
                flash('您沒有權限執行此操作', 'danger')
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator


def admin_required(f):
    """
    管理員專用裝飾器

    用法：
        @admin_required
        def my_route():
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('請先登入系統', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        if not current_user.has_role('admin'):
            flash('此功能需要管理員權限', 'danger')
            abort(403)
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    """
    角色檢查裝飾器（支援多角色，符合其中一個即可）

    用法：
        @role_required('admin', 'pm')
        def my_route():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('請先登入系統', 'warning')
                return redirect(url_for('auth.login', next=request.url))
            user_roles = current_user.get_role_names()
            if not any(role in user_roles for role in roles):
                flash('您沒有權限訪問此頁面', 'danger')
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator


# ---------------------------------------------------------------------------
# 導覽選單生成
# ---------------------------------------------------------------------------

def get_user_menu_items(user):
    """
    依使用者角色動態生成導覽選單

    回傳格式：
    [
        {
            'name':    '選單名稱',
            'url':     'blueprint.route_name',
            'icon':    'fas fa-icon',
            'submenu': [{'name': ..., 'url': ...}, ...]  # 選填
        },
        ...
    ]
    """
    if not user or not user.is_authenticated:
        return []

    menu = []

    # Dashboard - 所有角色皆可見
    menu.append({
        'name': 'Dashboard',
        'url':  'dashboard.index',
        'icon': 'fas fa-tachometer-alt',
    })

    # 業務管理 - admin / pm / sales
    if any([user.has_role('admin'), user.has_role('pm'), user.has_role('sales')]):
        kpi_submenu = []
        if user.has_role('admin') or user.has_role('pm'):
            kpi_submenu = [{'name': '年度績效統計', 'url': 'kpi.dashboard'}]

        menu.append({
            'name': '業務管理',
            'url':  'booking.index',
            'icon': 'fas fa-handshake',
            'submenu': [
                {'name': '商機報備', 'url': 'booking.index'},
                {'name': '商機管理', 'url': 'bom.index'},
                *kpi_submenu,
            ]
        })

    # 專案追蹤 - admin / pm / project_manager / engineer
    if any([
        user.has_role('admin'),
        user.has_role('pm'),
        user.has_role('project_manager'),
        user.has_role('engineer'),
    ]):
        menu.append({
            'name': '專案追蹤',
            'url':  'project.index',
            'icon': 'fas fa-project-diagram',
            'submenu': [
                {'name': '專案列表', 'url': 'project.index'},
            ]
        })

    # 產品管理 - admin / pm
    if user.has_role('admin') or user.has_role('pm'):
        menu.append({
            'name': '產品管理',
            'url':  'product.modules',
            'icon': 'fas fa-cubes',
            'submenu': [
                {'name': '模組管理', 'url': 'product.modules'},
                {'name': '功能管理', 'url': 'product.functions'},
                {'name': '價格管理', 'url': 'product.pricing'},
            ]
        })

    # 人員與權限管理 - admin only
    if user.has_role('admin'):
        menu.append({
            'name': '人員管理',
            'url':  'admin.users',
            'icon': 'fas fa-users-cog',
            'submenu': [
                {'name': '使用者管理', 'url': 'admin.users'},
            ]
        })

    return menu
