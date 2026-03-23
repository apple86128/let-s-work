from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user

from app.blueprints.bom import bom_bp
from app.models import db
from app.models.user import User, Role
from app.models.booking import CustomerBooking
from app.models.product import Module, Function, PricingTier
from app.models.bom import BOM, BOMItem, get_boms_for_user, get_bom_statistics_for_user
from app.utils.permissions import has_permission, permission_required


# ---------------------------------------------------------------------------
# 工具函數
# ---------------------------------------------------------------------------

def _get_sales_users():
    """取得所有啟用中的業務人員"""
    sales_role = Role.query.filter_by(name='sales').first()
    if not sales_role:
        return []
    return [u for u in sales_role.users if u.is_active]


def _load_modules_with_functions():
    """載入所有啟用模組及其功能（供表單使用）"""
    modules = Module.query.filter_by(is_active=True).order_by(Module.sort_order.asc()).all()
    for module in modules:
        module.function_list = Function.query.filter_by(
            module_id=module.id,
            is_active=True
        ).order_by(Function.sort_order.asc()).all()
    return modules


def _group_items_by_module(bom):
    """將 BOM 項目依模組分組，回傳 dict {module_id: {'module': ..., 'item_list': [...]}}"""
    result = {}
    for item in bom.items:
        if not item.function or not item.function.module:
            continue
        module = item.function.module
        result.setdefault(module.id, {'module': module, 'item_list': []})
        result[module.id]['item_list'].append(item)
    return result


def _calculate_bom_pricing(bom):
    """重新計算 BOM 建議價格，回傳 dict"""
    modules_used = {
        item.function.module
        for item in bom.items
        if item.function and item.function.module
    }

    modules_cost = sum(
        m.base_price_onetime if bom.plan_type == 'onetime' else (m.base_price_yearly or 0)
        for m in modules_used
    )

    tier        = PricingTier.get_effective_tier(bom.plan_type, bom.total_points)
    points_cost = tier.calculate_total_price(bom.total_points) if tier else bom.total_points * 1000
    base_price  = modules_cost + points_cost
    suggested   = base_price * bom.plan_years if bom.plan_type == 'yearly' else base_price

    return {
        'modules_cost':    modules_cost,
        'points_cost':     points_cost,
        'suggested_price': int(suggested),
    }


# ---------------------------------------------------------------------------
# 列表
# ---------------------------------------------------------------------------

@bom_bp.route('/')
@login_required
@permission_required('bom_view')
def index():
    """BOM 列表頁面"""
    page          = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    source_filter = request.args.get('source', '')
    search_query  = request.args.get('search', '')
    per_page      = 20

    query = get_boms_for_user(current_user)

    if status_filter:
        query = query.filter(BOM.status == status_filter)
    if source_filter:
        query = query.filter(BOM.source_type == source_filter)
    if search_query:
        query = query.filter(
            db.or_(
                BOM.bom_number.contains(search_query),
                BOM.customer_company.contains(search_query),
                BOM.project_name.contains(search_query),
            )
        )

    boms  = query.paginate(page=page, per_page=per_page, error_out=False)
    stats = get_bom_statistics_for_user(current_user)

    return render_template('bom/list.html',
                           boms=boms,
                           stats=stats,
                           status_filter=status_filter,
                           source_filter=source_filter,
                           search_query=search_query)


# ---------------------------------------------------------------------------
# 來源選擇（from_booking / direct_create）
# ---------------------------------------------------------------------------

@bom_bp.route('/source-select')
@login_required
@permission_required('bom_create')
def source_select():
    """BOM 來源選擇頁面"""
    used_ids = [
        b.booking_id for b in
        BOM.query.filter(BOM.booking_id.isnot(None), BOM.is_deleted == False).all()
    ]

    available_query = CustomerBooking.query.filter_by(
        status='approved', is_deleted=False
    )

    # 業務人員只能看自己的 Booking
    if current_user.has_role('sales') and not (
        current_user.has_role('admin') or current_user.has_role('pm')
    ):
        available_query = available_query.filter(
            db.or_(
                CustomerBooking.created_by_id     == current_user.id,
                CustomerBooking.assigned_sales_id == current_user.id,
            )
        )

    if used_ids:
        available_query = available_query.filter(
            ~CustomerBooking.id.in_(used_ids)
        )

    available_bookings = available_query.order_by(
        CustomerBooking.created_at.desc()
    ).all()

    return render_template('bom/source_select.html',
                           available_bookings=available_bookings)


# ---------------------------------------------------------------------------
# 建立
# ---------------------------------------------------------------------------

@bom_bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('bom_create')
def create():
    """建立新 BOM"""
    source_type = request.args.get('source', 'direct_create')
    booking_id  = request.args.get('booking_id', type=int)
    can_assign  = current_user.has_role('admin') or current_user.has_role('pm')
    sales_users = _get_sales_users() if can_assign else []
    modules     = _load_modules_with_functions()
    booking     = CustomerBooking.query.get(booking_id) if booking_id else None

    if request.method == 'GET':
        return render_template('bom/form.html',
                               bom=None,
                               source_type=source_type,
                               booking=booking,
                               modules=modules,
                               sales_users=sales_users)

    # POST：取得表單資料
    source_type  = request.form.get('source_type', 'direct_create')
    booking_id   = request.form.get('booking_id', type=int) or None
    company      = request.form.get('customer_company', '').strip()
    project_name = request.form.get('project_name', '').strip()
    plan_type    = request.form.get('plan_type')
    plan_years   = request.form.get('plan_years', type=int)
    function_ids = request.form.getlist('function_ids')
    quantities   = request.form.getlist('quantities')
    notes_list   = request.form.getlist('notes')

    # 決定業務指派
    if source_type == 'from_booking' and booking_id:
        bk = CustomerBooking.query.get(booking_id)
        assigned_id = bk.assigned_sales_id if bk else current_user.id
    elif can_assign:
        assigned_id = request.form.get('assigned_sales_id', type=int) or current_user.id
    else:
        assigned_id = current_user.id

    # 驗證
    errors = []
    if not company:      errors.append('請輸入客戶公司名稱')
    if not project_name: errors.append('請輸入專案名稱')
    if plan_type not in ('onetime', 'yearly'): errors.append('請選擇有效的方案類型')
    if not plan_years or not (1 <= plan_years <= 7): errors.append('請選擇 1-7 年的方案年數')
    if not function_ids: errors.append('請至少選擇一個功能項目')

    for i, qty_str in enumerate(quantities):
        try:
            if int(qty_str) <= 0:
                errors.append(f'第 {i+1} 個功能的數量必須大於 0')
        except (ValueError, TypeError):
            errors.append(f'第 {i+1} 個功能的數量格式不正確')

    if errors:
        for msg in errors:
            flash(msg, 'warning')
        return render_template('bom/form.html',
                               bom=None,
                               source_type=source_type,
                               booking=booking,
                               modules=modules,
                               sales_users=sales_users)

    # 建立 BOM
    new_bom = BOM(
        customer_company    = company,
        project_name        = project_name,
        customer_contact    = request.form.get('customer_contact', '').strip() or None,
        customer_email      = request.form.get('customer_email', '').strip() or None,
        project_description = request.form.get('project_description', '').strip() or None,
        plan_type           = plan_type,
        plan_years          = plan_years,
        source_type         = source_type,
        booking_id          = booking_id,
        created_by_id       = current_user.id,
        assigned_sales_id   = assigned_id,
    )
    db.session.add(new_bom)
    db.session.flush()  # 取得 new_bom.id

    # 建立 BOM 項目
    for i, function_id in enumerate(function_ids):
        try:
            qty   = int(quantities[i])
            notes = notes_list[i].strip() if i < len(notes_list) else None
            db.session.add(BOMItem(
                bom_id      = new_bom.id,
                function_id = int(function_id),
                quantity    = qty,
                notes       = notes or None,
            ))
        except (ValueError, IndexError):
            continue

    new_bom.calculate_suggested_price()
    db.session.commit()
    flash(f'成功建立 BOM：{new_bom.bom_number}', 'success')
    return redirect(url_for('bom.detail', bom_id=new_bom.id))


# ---------------------------------------------------------------------------
# 詳情
# ---------------------------------------------------------------------------

@bom_bp.route('/<int:bom_id>')
@login_required
def detail(bom_id):
    """BOM 詳情頁面"""
    bom = BOM.query.get_or_404(bom_id)

    if not bom.can_be_viewed_by(current_user):
        flash('您沒有權限查看此 BOM', 'danger')
        return redirect(url_for('bom.index'))

    bom_items_by_module = _group_items_by_module(bom)
    bom_items_list      = list(bom.items)

    # admin / pm 才需要業務指派下拉選單
    can_assign  = current_user.has_role('admin') or current_user.has_role('pm')
    sales_users = _get_sales_users() if can_assign else []

    return render_template('bom/detail.html',
                           bom=bom,
                           bom_items_by_module=bom_items_by_module,
                           bom_items_list=bom_items_list,
                           sales_users=sales_users)          # ← 補上此行


# ---------------------------------------------------------------------------
# 編輯
# ---------------------------------------------------------------------------

@bom_bp.route('/<int:bom_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(bom_id):
    """編輯 BOM"""
    bom = BOM.query.get_or_404(bom_id)

    if not bom.can_be_edited_by(current_user):
        flash('您沒有權限編輯此 BOM', 'danger')
        return redirect(url_for('bom.detail', bom_id=bom_id))

    can_assign  = current_user.has_role('admin') or current_user.has_role('pm')
    sales_users = _get_sales_users() if can_assign else []
    modules     = _load_modules_with_functions()
    booking     = CustomerBooking.query.get(bom.booking_id) if bom.booking_id else None

    # 提醒：已批准 / 拒絕的 BOM 編輯後會重置狀態
    if bom.status in ('approved', 'rejected'):
        flash(f'注意：此 BOM 目前狀態為「{bom.STATUS_DISPLAY.get(bom.status)}」，'
              f'編輯後將重置為「待審核」狀態', 'warning')

    if request.method == 'GET':
        return render_template('bom/form.html',
                               bom=bom,
                               source_type=bom.source_type,
                               booking=booking,
                               modules=modules,
                               sales_users=sales_users)

    # POST：取得表單資料
    company      = request.form.get('customer_company', '').strip()
    project_name = request.form.get('project_name', '').strip()
    plan_type    = request.form.get('plan_type')
    plan_years   = request.form.get('plan_years', type=int)
    function_ids = request.form.getlist('function_ids')
    quantities   = request.form.getlist('quantities')
    notes_list   = request.form.getlist('notes')

    if not company or not project_name or not plan_type or not plan_years or not function_ids:
        flash('請填寫所有必填欄位並至少選擇一個功能', 'warning')
        return render_template('bom/form.html',
                               bom=bom,
                               source_type=bom.source_type,
                               booking=booking,
                               modules=modules,
                               sales_users=sales_users)

    # 狀態重置（若原為已批准 / 拒絕）
    if bom.status in ('approved', 'rejected'):
        bom.reset_to_pending('因編輯內容變更', current_user.id)

    # 更新基本欄位
    bom.customer_company    = company
    bom.project_name        = project_name
    bom.customer_contact    = request.form.get('customer_contact', '').strip() or None
    bom.customer_email      = request.form.get('customer_email', '').strip() or None
    bom.project_description = request.form.get('project_description', '').strip() or None
    bom.plan_type           = plan_type
    bom.plan_years          = plan_years

    if can_assign:
        new_sales_id = request.form.get('assigned_sales_id', type=int)
        if new_sales_id and new_sales_id != bom.assigned_sales_id:
            bom.assigned_sales_id = new_sales_id

    # 重建 BOM 項目
    BOMItem.query.filter_by(bom_id=bom.id).delete()
    for i, function_id in enumerate(function_ids):
        try:
            qty   = int(quantities[i])
            notes = notes_list[i].strip() if i < len(notes_list) else None
            db.session.add(BOMItem(
                bom_id      = bom.id,
                function_id = int(function_id),
                quantity    = qty,
                notes       = notes or None,
            ))
        except (ValueError, IndexError):
            continue

    # 重新計算價格
    pricing = _calculate_bom_pricing(bom)
    bom.base_modules_cost = pricing['modules_cost']
    bom.points_cost       = pricing['points_cost']
    bom.suggested_price   = pricing['suggested_price']

    db.session.commit()
    flash(f'BOM {bom.bom_number} 已成功更新，產品建議價格已重新計算', 'success')
    return redirect(url_for('bom.detail', bom_id=bom.id))


# ---------------------------------------------------------------------------
# 審核
# ---------------------------------------------------------------------------

@bom_bp.route('/<int:bom_id>/review', methods=['GET', 'POST'])
@login_required
def review(bom_id):
    """審核 BOM（admin / pm 專用）"""
    bom = BOM.query.get_or_404(bom_id)

    if not bom.can_be_reviewed_by(current_user):
        flash('您沒有權限審核此 BOM', 'danger')
        return redirect(url_for('bom.detail', bom_id=bom_id))

    # 預先準備 template 所需變數（GET 與 POST 驗證失敗都會用到）
    bom_items_by_module = _group_items_by_module(bom)
    bom_items_list      = list(bom.items)

    def _render_review():
        return render_template('bom/review.html',
                               bom=bom,
                               bom_items_by_module=bom_items_by_module,
                               bom_items_list=bom_items_list)

    if request.method == 'GET':
        return _render_review()

    action      = request.form.get('action')
    notes       = request.form.get('notes', '').strip()
    final_price = request.form.get('final_price', type=int)

    final_maintenance_price = request.form.get('final_maintenance_price', type=int)

    if action == 'approve':
        if not final_price or final_price <= 0:
            flash('批准時請輸入有效的最終價格', 'warning')
            return _render_review()
        bom.approve(
            current_user.id,
            notes                   = notes or None,
            final_price             = final_price,
            final_maintenance_price = final_maintenance_price if final_maintenance_price and final_maintenance_price > 0 else None,
        )
        flash(f'BOM {bom.bom_number} 已批准', 'success')

    elif action == 'reject':
        if not notes:
            flash('拒絕時請填寫審核意見', 'warning')
            return _render_review()
        bom.reject(current_user.id, notes=notes)
        flash(f'BOM {bom.bom_number} 已拒絕', 'warning')

    elif action == 'update_price':
        # 僅更新價格，不改變審核狀態
        bom.update_price_only(
            user_id                 = current_user.id,
            final_price             = final_price if final_price and final_price > 0 else None,
            final_maintenance_price = final_maintenance_price if final_maintenance_price and final_maintenance_price > 0 else None,
            notes                   = notes or None,
        )
        flash(f'BOM {bom.bom_number} 價格已更新', 'success')

    else:
        flash('無效的操作', 'danger')
        return _render_review()

    db.session.commit()
    return redirect(url_for('bom.detail', bom_id=bom_id))


# ---------------------------------------------------------------------------
# 刪除
# ---------------------------------------------------------------------------

@bom_bp.route('/<int:bom_id>/delete', methods=['POST'])
@login_required
def delete(bom_id):
    """刪除 BOM"""
    bom = BOM.query.get_or_404(bom_id)

    if not bom.can_be_deleted_by(current_user):
        flash('您沒有權限刪除此 BOM', 'danger')
        return redirect(url_for('bom.detail', bom_id=bom_id))

    bom.soft_delete(current_user.id)
    db.session.commit()
    flash(f'已刪除 BOM：{bom.bom_number}', 'success')
    return redirect(url_for('bom.index'))


# ---------------------------------------------------------------------------
# 重新指派業務
# ---------------------------------------------------------------------------

@bom_bp.route('/<int:bom_id>/reassign', methods=['POST'])
@login_required
def reassign_sales(bom_id):
    """重新指派 BOM 負責業務（admin / pm 專用）"""
    if not (current_user.has_role('admin') or current_user.has_role('pm')):
        flash('您沒有權限重新指派業務', 'danger')
        return redirect(url_for('bom.detail', bom_id=bom_id))

    bom          = BOM.query.get_or_404(bom_id)
    new_sales_id = request.form.get('new_sales_id', type=int)

    if not new_sales_id:
        flash('請選擇要指派的業務人員', 'warning')
        return redirect(url_for('bom.detail', bom_id=bom_id))

    new_sales = User.query.get(new_sales_id)
    if not new_sales or not new_sales.has_role('sales'):
        flash('指派的業務人員無效', 'warning')
        return redirect(url_for('bom.detail', bom_id=bom_id))

    bom.assigned_sales_id = new_sales_id
    db.session.commit()
    flash(f'BOM {bom.bom_number} 已重新指派給：{new_sales.name}', 'success')
    return redirect(url_for('bom.detail', bom_id=bom_id))


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@bom_bp.route('/api/modules-functions')
@login_required
def api_modules_functions():
    """取得模組與功能列表（供 BOM 表單使用）"""
    modules = Module.query.filter_by(is_active=True).order_by(Module.sort_order.asc()).all()
    return jsonify([{
        'id':          m.id,
        'name':        m.name,
        'code':        m.code,
        'description': m.description,
        'functions':   [{
            'id':              f.id,
            'name':            f.name,
            'code':            f.code,
            'points_per_unit': f.points_per_unit,
            'unit_name':       f.unit_name,
            'description':     f.description,
        } for f in Function.query.filter_by(module_id=m.id, is_active=True)
                                  .order_by(Function.sort_order.asc()).all()]
    } for m in modules])


@bom_bp.route('/api/sales-users')
@login_required
def api_sales_users():
    """取得業務人員列表（admin / pm 專用）"""
    if not (current_user.has_role('admin') or current_user.has_role('pm')):
        return jsonify({'error': 'Permission denied'}), 403
    users = _get_sales_users()
    return jsonify([{
        'id':        u.id,
        'name':      u.name,
        'email':     u.email,
        'extension': u.extension,
    } for u in users])


@bom_bp.route('/api/calculate-price', methods=['POST'])
@login_required
def api_calculate_price():
    """即時計算 BOM 價格"""
    data           = request.get_json() or {}
    function_items = data.get('functions', [])
    plan_type      = data.get('plan_type', 'onetime')
    plan_years     = data.get('plan_years', 1)

    total_points = 0
    used_modules = set()

    for item in function_items:
        func = Function.query.get(item.get('function_id'))
        if func:
            total_points += func.points_per_unit * item.get('quantity', 1)
            used_modules.add(func.module_id)

    modules_cost = sum(
        Module.query.get(mid).base_price_onetime
        if plan_type == 'onetime'
        else (Module.query.get(mid).base_price_yearly or 0)
        for mid in used_modules
        if Module.query.get(mid)
    )

    tier        = PricingTier.get_effective_tier(plan_type, total_points)
    points_cost = tier.calculate_total_price(total_points) if tier else total_points * 1000
    base_price  = modules_cost + points_cost
    suggested   = base_price * plan_years if plan_type == 'yearly' else base_price

    return jsonify({
        'total_points':    total_points,
        'modules_cost':    modules_cost,
        'points_cost':     points_cost,
        'suggested_price': int(suggested),
        'tier_info': {
            'name':            tier.tier_name,
            'price_per_point': tier.price_per_point,
        } if tier else None,
    })


@bom_bp.route('/api/calculate-labor-price', methods=['POST'])
@login_required
def api_calculate_labor_price():
    """計算人力建議價格（產品最終價格 × 10% + 5% × 年數）"""
    data        = request.get_json() or {}
    final_price = data.get('final_price', 0)
    plan_years  = data.get('plan_years', 1)

    if not final_price or final_price <= 0:
        return jsonify({'labor_suggested_price': 0, 'error': '產品最終價格必須大於 0'})

    labor = int(final_price * 0.1 + final_price * 0.05 * plan_years)
    return jsonify({
        'labor_suggested_price': labor,
        'detail': {
            'base_rate':    final_price * 0.1,
            'annual_rate':  final_price * 0.05,
            'years':        plan_years,
            'total_annual': final_price * 0.05 * plan_years,
        },
    })
