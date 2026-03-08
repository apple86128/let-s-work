from flask import render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user

from app.blueprints.admin import admin_bp
from app.models import db
from app.models.user import User, Role
from app.models.permission import UserPermission
from app.utils.permissions import admin_required


# ---------------------------------------------------------------------------
# 使用者管理
# ---------------------------------------------------------------------------

@admin_bp.route('/users')
@admin_required
def users():
    """使用者管理列表"""
    page     = request.args.get('page', 1, type=int)
    per_page = 20

    users_pagination = User.query.order_by(
        User.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    stats = {
        'total':  User.query.count(),
        'active': User.query.filter_by(is_active=True).count(),
        'admin':  User.query.join(User.roles).filter(Role.name == 'admin').count(),
        'sales':  User.query.join(User.roles).filter(Role.name == 'sales').count(),
    }

    return render_template('admin/users.html',
                           users=users_pagination,
                           stats=stats)


@admin_bp.route('/users/create', methods=['GET', 'POST'])
@admin_required
def create_user():
    """建立新使用者"""
    roles = Role.query.order_by(Role.name).all()

    if request.method == 'GET':
        return render_template('admin/user_create.html', roles=roles)

    # POST：處理表單
    email     = request.form.get('email', '').strip().lower()
    name      = request.form.get('name', '').strip()
    password  = request.form.get('password', '')
    extension = request.form.get('extension', '').strip()
    role_ids  = request.form.getlist('roles')

    if not email or not name or not password:
        flash('請填寫所有必填欄位', 'warning')
        return render_template('admin/user_create.html', roles=roles)

    if User.query.filter_by(email=email).first():
        flash('此 Email 已被使用', 'warning')
        return render_template('admin/user_create.html', roles=roles)

    new_user = User(email=email, name=name, password=password, extension=extension)

    for role_id in role_ids:
        role = Role.query.get(role_id)
        if role:
            new_user.roles.append(role)

    db.session.add(new_user)
    db.session.commit()
    flash(f'成功建立使用者：{name}', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    """編輯使用者資訊"""
    user  = User.query.get_or_404(user_id)
    roles = Role.query.order_by(Role.name).all()

    # 防止管理員編輯自己的帳號
    if user.id == current_user.id:
        flash('請至個人設定修改自己的帳號', 'warning')
        return redirect(url_for('admin.users'))

    if request.method == 'GET':
        return render_template('admin/user_edit.html', user=user, roles=roles)

    # POST：處理表單
    name      = request.form.get('name', '').strip()
    extension = request.form.get('extension', '').strip()
    role_ids  = request.form.getlist('roles')
    is_active = request.form.get('is_active') == 'on'

    if not name:
        flash('請填寫使用者姓名', 'warning')
        return render_template('admin/user_edit.html', user=user, roles=roles)

    user.name      = name
    user.extension = extension
    user.is_active = is_active

    # 更新角色（先清除再重新指派）
    user.roles.clear()
    for role_id in role_ids:
        role = Role.query.get(role_id)
        if role:
            user.roles.append(role)

    db.session.commit()
    flash(f'成功更新使用者：{user.name}', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@admin_required
def toggle_user_status(user_id):
    """切換使用者啟用 / 停用狀態"""
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('無法停用自己的帳號', 'warning')
        return redirect(url_for('admin.users'))

    user.is_active = not user.is_active
    db.session.commit()

    status = '啟用' if user.is_active else '停用'
    flash(f'已{status}使用者：{user.name}', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/reset_password', methods=['POST'])
@admin_required
def reset_password(user_id):
    """重設使用者密碼"""
    user         = User.query.get_or_404(user_id)
    new_password = request.form.get('new_password', '')

    if not new_password or len(new_password) < 6:
        flash('新密碼長度至少需要 6 個字元', 'warning')
        return redirect(url_for('admin.edit_user', user_id=user_id))

    user.set_password(new_password)
    db.session.commit()
    flash(f'已重設 {user.name} 的密碼', 'success')
    return redirect(url_for('admin.edit_user', user_id=user_id))


# ---------------------------------------------------------------------------
# 個人客製化權限管理
# ---------------------------------------------------------------------------

@admin_bp.route('/users/<int:user_id>/permissions')
@admin_required
def user_permissions(user_id):
    """查看使用者個人客製化權限"""
    user = User.query.get_or_404(user_id)

    from app.utils.permissions import PERMISSION_MAP
    return render_template('admin/user_permissions.html',
                           user=user,
                           permission_map=PERMISSION_MAP)


@admin_bp.route('/users/<int:user_id>/permissions/set', methods=['POST'])
@admin_required
def set_user_permission(user_id):
    """新增或更新使用者個人權限"""
    user            = User.query.get_or_404(user_id)
    permission_name = request.form.get('permission_name', '')
    is_granted      = request.form.get('is_granted') == 'true'
    notes           = request.form.get('notes', '').strip()

    if not permission_name:
        flash('請選擇權限項目', 'warning')
        return redirect(url_for('admin.user_permissions', user_id=user_id))

    # 已存在則更新，否則新增
    existing = UserPermission.query.filter_by(
        user_id=user_id,
        permission_name=permission_name
    ).first()

    if existing:
        existing.is_granted    = is_granted
        existing.granted_by_id = current_user.id
        existing.notes         = notes
    else:
        perm = UserPermission(
            user_id         = user_id,
            permission_name = permission_name,
            is_granted      = is_granted,
            granted_by_id   = current_user.id,
            notes           = notes,
        )
        db.session.add(perm)

    db.session.commit()
    action = '授予' if is_granted else '拒絕'
    flash(f'已{action}權限：{permission_name}', 'success')
    return redirect(url_for('admin.user_permissions', user_id=user_id))


@admin_bp.route('/users/<int:user_id>/permissions/<int:perm_id>/delete', methods=['POST'])
@admin_required
def delete_user_permission(user_id, perm_id):
    """刪除使用者個人客製化權限（恢復為角色預設）"""
    perm = UserPermission.query.get_or_404(perm_id)

    if perm.user_id != user_id:
        flash('權限記錄不符', 'danger')
        return redirect(url_for('admin.user_permissions', user_id=user_id))

    db.session.delete(perm)
    db.session.commit()
    flash('已移除客製化權限，恢復為角色預設', 'success')
    return redirect(url_for('admin.user_permissions', user_id=user_id))
