import re
from urllib.parse import urlparse
from flask import render_template, request, flash, redirect, url_for, session
from flask_login import login_user, logout_user, login_required, current_user

from app.blueprints.auth import auth_bp
from app.models import db
from app.models.user import User, Role


# ---------------------------------------------------------------------------
# 工具函數
# ---------------------------------------------------------------------------

def _is_valid_email(email):
    """驗證 Email 格式"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def _safe_next_url(next_url):
    """驗證 next 參數安全性，防止開放重定向攻擊"""
    if not next_url or urlparse(next_url).netloc != '':
        return url_for('dashboard.index')
    return next_url


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """系統內部帳號登入"""

    # 已登入直接導向 dashboard
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'GET':
        return render_template('auth/login.html')

    # POST：處理登入表單
    email       = request.form.get('email', '').strip().lower()
    password    = request.form.get('password', '')
    remember_me = request.form.get('remember_me') == 'on'

    if not email or not password:
        flash('請輸入 Email 和密碼', 'warning')
        return render_template('auth/login.html')

    if not _is_valid_email(email):
        flash('Email 格式不正確', 'warning')
        return render_template('auth/login.html')

    user = User.query.filter_by(email=email).first()

    if not user or not user.check_password(password):
        flash('Email 或密碼錯誤', 'danger')
        return render_template('auth/login.html')

    if not user.is_active:
        flash('帳號已停用，請聯絡管理員', 'danger')
        return render_template('auth/login.html')

    # 登入成功
    login_user(user, remember=remember_me)
    user.update_last_login()
    flash(f'歡迎回來，{user.name}！', 'success')

    return redirect(_safe_next_url(request.args.get('next')))


@auth_bp.route('/logout')
@login_required
def logout():
    """登出並清除 Session"""
    user_name = current_user.name
    logout_user()
    session.pop('sales_email', None)
    flash(f'再見，{user_name}！', 'info')
    return redirect(url_for('auth.login'))


# ---------------------------------------------------------------------------
# Sales 外部入口（三步驟：入口 → 登入 or 註冊）
# ---------------------------------------------------------------------------

@auth_bp.route('/sales', methods=['GET', 'POST'])
def sales_entry():
    """
    業務人員專用入口
    輸入 Email 後自動判斷：已有帳號 → 登入頁 / 新帳號 → 註冊頁
    """
    if request.method == 'GET':
        return render_template('auth/sales_entry.html')

    email = request.form.get('email', '').strip().lower()

    if not email:
        flash('請輸入 Email', 'warning')
        return render_template('auth/sales_entry.html')

    if not _is_valid_email(email):
        flash('Email 格式不正確', 'warning')
        return render_template('auth/sales_entry.html')

    session['sales_email'] = email
    user = User.query.filter_by(email=email).first()

    if user:
        return redirect(url_for('auth.sales_login'))
    return redirect(url_for('auth.sales_register'))


@auth_bp.route('/sales/login', methods=['GET', 'POST'])
def sales_login():
    """業務人員登入頁面"""

    email = session.get('sales_email')
    if not email:
        flash('請重新輸入 Email', 'warning')
        return redirect(url_for('auth.sales_entry'))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash('帳號不存在，請重新確認', 'warning')
        return redirect(url_for('auth.sales_entry'))

    if request.method == 'GET':
        return render_template('auth/sales_login.html', email=email)

    # POST：處理登入
    password    = request.form.get('password', '')
    remember_me = request.form.get('remember_me') == 'on'

    if not password:
        flash('請輸入密碼', 'warning')
        return render_template('auth/sales_login.html', email=email)

    if not user.check_password(password):
        flash('密碼錯誤，請重新輸入', 'danger')
        return render_template('auth/sales_login.html', email=email)

    if not user.is_active:
        flash('帳號已停用，請聯絡管理員', 'danger')
        return render_template('auth/sales_login.html', email=email)

    login_user(user, remember=remember_me)
    user.update_last_login()
    session.pop('sales_email', None)
    flash(f'歡迎回來，{user.name}！', 'success')
    return redirect(url_for('dashboard.index'))


@auth_bp.route('/sales/register', methods=['GET', 'POST'])
def sales_register():
    """業務人員註冊頁面"""

    email = session.get('sales_email')
    if not email:
        flash('請重新輸入 Email', 'warning')
        return redirect(url_for('auth.sales_entry'))

    # 若帳號已存在則導向登入
    if User.query.filter_by(email=email).first():
        flash('此 Email 已註冊，請直接登入', 'info')
        return redirect(url_for('auth.sales_login'))

    if request.method == 'GET':
        return render_template('auth/sales_register.html', email=email)

    # POST：處理註冊表單
    name             = request.form.get('name', '').strip()
    password         = request.form.get('password', '')
    confirm_password = request.form.get('confirm_password', '')
    extension        = request.form.get('extension', '').strip()

    # 欄位驗證
    if not name or len(name) < 2:
        flash('請輸入姓名（至少 2 個字元）', 'warning')
        return render_template('auth/sales_register.html', email=email)

    if not password or len(password) < 6:
        flash('密碼長度至少需要 6 個字元', 'warning')
        return render_template('auth/sales_register.html', email=email)

    if password != confirm_password:
        flash('密碼確認不一致', 'warning')
        return render_template('auth/sales_register.html', email=email)

    # 建立新業務帳號
    new_user = User(email=email, name=name, password=password, extension=extension)

    sales_role = Role.query.filter_by(name='sales').first()
    if sales_role:
        new_user.roles.append(sales_role)
    else:
        flash('角色設定異常，請聯絡管理員', 'warning')

    db.session.add(new_user)
    db.session.commit()

    # 註冊後自動登入
    login_user(new_user)
    new_user.update_last_login()
    session.pop('sales_email', None)
    flash(f'註冊成功！歡迎加入，{new_user.name}！', 'success')
    return redirect(url_for('dashboard.index'))
