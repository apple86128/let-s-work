import json
from datetime import datetime, date
from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user

from app.blueprints.product import product_bp
from app.models import db
from app.models.product import Module, Function, PricingTier, calculate_quote_summary
from app.utils.permissions import permission_required


# ---------------------------------------------------------------------------
# 工具函數
# ---------------------------------------------------------------------------

def _parse_date(date_str, default=None):
    """安全解析日期字串，失敗回傳 default"""
    if not date_str:
        return default
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return None


def _clear_other_defaults(plan_type, exclude_id=None):
    """將同方案類型的其他預設級距取消設定"""
    query = PricingTier.query.filter_by(plan_type=plan_type, is_default=True, is_active=True)
    if exclude_id:
        query = query.filter(PricingTier.id != exclude_id)
    for tier in query.all():
        tier.is_default = False


# ---------------------------------------------------------------------------
# 模組管理
# ---------------------------------------------------------------------------

@product_bp.route('/modules')
@permission_required('product_module_manage')
def modules():
    """模組管理列表"""
    all_modules = Module.query.order_by(
        Module.sort_order.asc(), Module.created_at.desc()
    ).all()

    stats = {
        'total_modules':    len(all_modules),
        'active_modules':   sum(1 for m in all_modules if m.is_active),
        'inactive_modules': sum(1 for m in all_modules if not m.is_active),
        'total_functions':  sum(len(m.functions) for m in all_modules),
    }

    return render_template('product/modules.html', modules=all_modules, stats=stats)


@product_bp.route('/modules/<int:module_id>')
@permission_required('product_module_manage')
def module_detail(module_id):
    """模組詳情頁面"""
    module    = Module.query.get_or_404(module_id)
    functions = Function.query.filter_by(module_id=module_id).order_by(
        Function.sort_order.asc(), Function.created_at.asc()
    ).all()

    stats = {
        'total_functions':  len(functions),
        'active_functions': sum(1 for f in functions if f.is_active),
        'total_points':     sum(f.points_per_unit for f in functions if f.is_active),
    }

    return render_template('product/module_detail.html',
                           module=module, functions=functions, stats=stats)


@product_bp.route('/modules/create', methods=['GET', 'POST'])
@permission_required('product_module_manage')
def create_module():
    """建立新模組"""
    if request.method == 'GET':
        return render_template('product/module_form.html', module=None)

    name       = request.form.get('name', '').strip()
    code       = request.form.get('code', '').strip().upper()
    desc       = request.form.get('description', '').strip()
    # 使用 None 作為預設值，避免 0 被 `or` 視為 falsy 而套用預設價格
    price_one  = request.form.get('base_price_onetime', type=int)
    price_yr   = request.form.get('base_price_yearly',  type=int)
    sort_order = request.form.get('sort_order', type=int) or 0

    if not name or not code:
        flash('請輸入模組名稱與代碼', 'warning')
        return render_template('product/module_form.html', module=None)

    # 允許價格為 0（免費附加模組），只擋未填寫（None）或負數
    if price_one is None or price_yr is None or price_one < 0 or price_yr < 0:
        flash('請填寫模組價格（可設為 0）', 'warning')
        return render_template('product/module_form.html', module=None)

    if Module.query.filter_by(code=code).first():
        flash(f'模組代碼 {code} 已存在', 'warning')
        return render_template('product/module_form.html', module=None)

    new_module = Module(
        name               = name,
        code               = code,
        description        = desc or None,
        base_price_onetime = price_one,
        base_price_yearly  = price_yr,
        sort_order         = sort_order,
        created_by_id      = current_user.id,
    )
    db.session.add(new_module)
    db.session.commit()
    flash(f'成功建立模組：{name} ({code})', 'success')
    return redirect(url_for('product.module_detail', module_id=new_module.id))


@product_bp.route('/modules/<int:module_id>/edit', methods=['GET', 'POST'])
@permission_required('product_module_manage')
def edit_module(module_id):
    """編輯模組"""
    module = Module.query.get_or_404(module_id)

    if request.method == 'GET':
        return render_template('product/module_form.html', module=module)

    name = request.form.get('name', '').strip()
    if not name:
        flash('請輸入模組名稱', 'warning')
        return render_template('product/module_form.html', module=module)

    # 允許價格為 0，使用 None 判斷未填寫，避免 `or 50000` 覆蓋合法的 0 值
    price_one = request.form.get('base_price_onetime', type=int)
    price_yr  = request.form.get('base_price_yearly',  type=int)

    if price_one is None or price_yr is None or price_one < 0 or price_yr < 0:
        flash('請填寫模組價格（可設為 0）', 'warning')
        return render_template('product/module_form.html', module=module)

    module.name               = name
    module.description        = request.form.get('description', '').strip() or None
    module.base_price_onetime = price_one
    module.base_price_yearly  = price_yr
    module.sort_order         = request.form.get('sort_order', type=int) or 0
    module.is_active          = request.form.get('is_active') == 'on'

    db.session.commit()
    flash(f'成功更新模組：{module.name}', 'success')
    return redirect(url_for('product.module_detail', module_id=module_id))


@product_bp.route('/modules/<int:module_id>/toggle', methods=['POST'])
@permission_required('product_module_manage')
def toggle_module_status(module_id):
    """切換模組啟用 / 停用"""
    module           = Module.query.get_or_404(module_id)
    module.is_active = not module.is_active
    db.session.commit()
    status = '啟用' if module.is_active else '停用'
    flash(f'已{status}模組：{module.name}', 'success')
    return redirect(url_for('product.modules'))


# ---------------------------------------------------------------------------
# 功能管理
# ---------------------------------------------------------------------------

@product_bp.route('/functions')
@permission_required('product_function_manage')
def functions():
    """功能管理頁面（依模組分組顯示）"""
    all_modules = Module.query.filter_by(is_active=True).order_by(Module.sort_order.asc()).all()

    for module in all_modules:
        module.function_list = Function.query.filter_by(module_id=module.id).order_by(
            Function.sort_order.asc(), Function.created_at.asc()
        ).all()

    total     = Function.query.count()
    active    = Function.query.filter_by(is_active=True).count()
    stats = {
        'total_functions':    total,
        'active_functions':   active,
        'inactive_functions': total - active,
    }

    return render_template('product/functions.html', modules=all_modules, stats=stats)


@product_bp.route('/modules/<int:module_id>/functions/create', methods=['GET', 'POST'])
@permission_required('product_function_manage')
def create_function(module_id):
    """建立新功能"""
    module = Module.query.get_or_404(module_id)

    if request.method == 'GET':
        return render_template('product/function_form.html', module=module, function=None)

    name            = request.form.get('name', '').strip()
    code            = request.form.get('code', '').strip().upper()
    points_per_unit = request.form.get('points_per_unit', type=int)
    unit_name       = request.form.get('unit_name', '').strip() or '台'
    sort_order      = request.form.get('sort_order', type=int) or 0

    if not name or not code:
        flash('請輸入功能名稱與代碼', 'warning')
        return render_template('product/function_form.html', module=module, function=None)

    if not points_per_unit or points_per_unit <= 0:
        flash('點數必須大於 0', 'warning')
        return render_template('product/function_form.html', module=module, function=None)

    if Function.query.filter_by(module_id=module_id, code=code).first():
        flash(f'功能代碼 {code} 在此模組內已存在', 'warning')
        return render_template('product/function_form.html', module=module, function=None)

    new_func = Function(
        module_id       = module_id,
        name            = name,
        code            = code,
        points_per_unit = points_per_unit,
        unit_name       = unit_name,
        description     = request.form.get('description', '').strip() or None,
        sort_order      = sort_order,
    )
    db.session.add(new_func)
    db.session.commit()
    flash(f'成功建立功能：{name}', 'success')
    return redirect(url_for('product.module_detail', module_id=module_id))


@product_bp.route('/functions/<int:function_id>/edit', methods=['GET', 'POST'])
@permission_required('product_function_manage')
def edit_function(function_id):
    """編輯功能"""
    func   = Function.query.get_or_404(function_id)
    module = func.module

    if request.method == 'GET':
        return render_template('product/function_form.html', module=module, function=func)

    name            = request.form.get('name', '').strip()
    points_per_unit = request.form.get('points_per_unit', type=int) or 1

    if not name:
        flash('請輸入功能名稱', 'warning')
        return render_template('product/function_form.html', module=module, function=func)

    if points_per_unit <= 0:
        flash('點數必須大於 0', 'warning')
        return render_template('product/function_form.html', module=module, function=func)

    func.name            = name
    func.description     = request.form.get('description', '').strip() or None
    func.points_per_unit = points_per_unit
    func.unit_name       = request.form.get('unit_name', '').strip() or '台'
    func.sort_order      = request.form.get('sort_order', type=int) or 0
    func.is_active       = request.form.get('is_active') == 'on'

    db.session.commit()
    flash(f'成功更新功能：{func.name}', 'success')
    return redirect(url_for('product.module_detail', module_id=module.id))


@product_bp.route('/functions/<int:function_id>/toggle', methods=['POST'])
@permission_required('product_function_manage')
def toggle_function_status(function_id):
    """切換功能啟用 / 停用"""
    func           = Function.query.get_or_404(function_id)
    func.is_active = not func.is_active
    db.session.commit()
    status = '啟用' if func.is_active else '停用'
    flash(f'已{status}功能：{func.name}', 'success')
    return redirect(url_for('product.module_detail', module_id=func.module_id))


# ---------------------------------------------------------------------------
# Sales Kit 生成
# ---------------------------------------------------------------------------

@product_bp.route('/functions/saleskit', methods=['POST'])
@permission_required('product_function_manage')
def generate_saleskit():
    """生成 Sales Kit 文件"""
    try:
        function_ids = json.loads(request.form.get('function_ids', '[]'))
    except json.JSONDecodeError:
        flash('資料格式錯誤', 'warning')
        return redirect(url_for('product.functions'))

    if not function_ids:
        flash('請至少選擇一個功能', 'warning')
        return redirect(url_for('product.functions'))

    selected = Function.query.filter(Function.id.in_(function_ids)).all()
    if not selected:
        flash('找不到選中的功能', 'warning')
        return redirect(url_for('product.functions'))

    # 依模組分組並排序
    modules_dict = {}
    for func in selected:
        modules_dict.setdefault(func.module_id, {
            'module':    func.module,
            'functions': [],
        })['functions'].append(func)

    modules_data = sorted(
        modules_dict.values(),
        key=lambda m: m['module'].code
    )
    for item in modules_data:
        item['functions'].sort(key=lambda f: f.sort_order)

    return render_template('product/saleskit.html',
                           modules_data=modules_data,
                           total_functions=len(selected),
                           total_modules=len(modules_data),
                           generated_at=datetime.now())


# ---------------------------------------------------------------------------
# 價格管理
# ---------------------------------------------------------------------------

@product_bp.route('/pricing')
@permission_required('product_pricing_manage')
def pricing():
    """價格管理頁面"""
    tiers = PricingTier.query.filter_by(is_active=True).order_by(
        PricingTier.plan_type.asc(), PricingTier.min_points.asc()
    ).all()

    onetime_tiers = [t for t in tiers if t.plan_type == 'onetime']
    yearly_tiers  = [t for t in tiers if t.plan_type == 'yearly']

    stats = {
        'total_tiers':   len(tiers),
        'onetime_tiers': len(onetime_tiers),
        'yearly_tiers':  len(yearly_tiers),
    }

    return render_template('product/pricing.html',
                           onetime_tiers=onetime_tiers,
                           yearly_tiers=yearly_tiers,
                           stats=stats)


@product_bp.route('/pricing/create', methods=['GET', 'POST'])
@permission_required('product_pricing_manage')
def create_pricing_tier():
    """建立新價格級距"""
    if request.method == 'GET':
        return render_template('product/pricing_form.html', tier=None)

    plan_type       = request.form.get('plan_type')
    tier_name       = request.form.get('tier_name', '').strip()
    min_points      = request.form.get('min_points', type=int)
    max_points      = request.form.get('max_points', type=int) or None
    price_per_point = request.form.get('price_per_point', type=int)
    is_default      = request.form.get('is_default') == 'on'
    effective_date  = _parse_date(request.form.get('effective_date'), default=date.today())
    end_date        = _parse_date(request.form.get('end_date'))

    # 驗證
    if plan_type not in ('onetime', 'yearly'):
        flash('請選擇方案類型', 'warning')
        return render_template('product/pricing_form.html', tier=None)

    if not tier_name or min_points is None or min_points < 0 \
            or not price_per_point or price_per_point <= 0:
        flash('請填寫所有必填欄位，且數值必須大於 0', 'warning')
        return render_template('product/pricing_form.html', tier=None)

    if max_points is not None and max_points <= min_points:
        flash('最高點數必須大於最低點數', 'warning')
        return render_template('product/pricing_form.html', tier=None)

    if effective_date is None:
        flash('生效日期格式不正確', 'warning')
        return render_template('product/pricing_form.html', tier=None)

    if end_date and end_date <= effective_date:
        flash('結束日期必須晚於生效日期', 'warning')
        return render_template('product/pricing_form.html', tier=None)

    if is_default:
        _clear_other_defaults(plan_type)

    new_tier = PricingTier(
        plan_type       = plan_type,
        tier_name       = tier_name,
        min_points      = min_points,
        max_points      = max_points,
        price_per_point = price_per_point,
        effective_date  = effective_date,
        end_date        = end_date,
        is_default      = is_default,
        created_by_id   = current_user.id,
    )
    db.session.add(new_tier)
    db.session.commit()
    flash(f'成功建立價格級距：{tier_name}', 'success')
    return redirect(url_for('product.pricing'))


@product_bp.route('/pricing/<int:tier_id>/edit', methods=['GET', 'POST'])
@permission_required('product_pricing_manage')
def edit_pricing_tier(tier_id):
    """編輯價格級距"""
    tier = PricingTier.query.get_or_404(tier_id)

    if request.method == 'GET':
        return render_template('product/pricing_form.html', tier=tier)

    tier_name       = request.form.get('tier_name', '').strip()
    min_points      = request.form.get('min_points', type=int) or 0
    max_points      = request.form.get('max_points', type=int) or None
    price_per_point = request.form.get('price_per_point', type=int) or 1
    is_default      = request.form.get('is_default') == 'on'
    is_active       = request.form.get('is_active') == 'on'
    effective_date  = _parse_date(request.form.get('effective_date'))
    end_date        = _parse_date(request.form.get('end_date'))

    if not tier_name or price_per_point <= 0:
        flash('請填寫級距名稱，且每點價格必須大於 0', 'warning')
        return render_template('product/pricing_form.html', tier=tier)

    if max_points is not None and max_points <= min_points:
        flash('最高點數必須大於最低點數', 'warning')
        return render_template('product/pricing_form.html', tier=tier)

    if effective_date and end_date and end_date <= effective_date:
        flash('結束日期必須晚於生效日期', 'warning')
        return render_template('product/pricing_form.html', tier=tier)

    # 若設為預設，先清除其他同類型預設
    if is_default and not tier.is_default:
        _clear_other_defaults(tier.plan_type, exclude_id=tier.id)

    tier.tier_name       = tier_name
    tier.min_points      = min_points
    tier.max_points      = max_points
    tier.price_per_point = price_per_point
    tier.is_default      = is_default
    tier.is_active       = is_active
    if effective_date:
        tier.effective_date = effective_date
    tier.end_date = end_date

    db.session.commit()
    flash(f'成功更新價格級距：{tier.tier_name}', 'success')
    return redirect(url_for('product.pricing'))


@product_bp.route('/pricing/<int:tier_id>/toggle', methods=['POST'])
@permission_required('product_pricing_manage')
def toggle_pricing_tier_status(tier_id):
    """切換價格級距啟用 / 停用"""
    tier = PricingTier.query.get_or_404(tier_id)

    # 唯一啟用的預設級距不可停用
    if tier.is_default and tier.is_active:
        other_active = PricingTier.query.filter(
            PricingTier.plan_type == tier.plan_type,
            PricingTier.is_active == True,
            PricingTier.id != tier.id,
        ).count()
        if other_active == 0:
            flash(f'無法停用唯一的 {tier.plan_type} 方案級距', 'warning')
            return redirect(url_for('product.pricing'))

    tier.is_active = not tier.is_active
    db.session.commit()
    status = '啟用' if tier.is_active else '停用'
    flash(f'已{status}價格級距：{tier.tier_name}', 'success')
    return redirect(url_for('product.pricing'))


@product_bp.route('/pricing/<int:tier_id>/delete', methods=['POST'])
@permission_required('product_pricing_manage')
def delete_pricing_tier(tier_id):
    """刪除價格級距"""
    tier = PricingTier.query.get_or_404(tier_id)

    # 刪除預設級距前，自動指定新預設
    if tier.is_default:
        other_count = PricingTier.query.filter(
            PricingTier.plan_type == tier.plan_type,
            PricingTier.id != tier.id,
        ).count()
        if other_count == 0:
            flash(f'無法刪除唯一的 {tier.plan_type} 方案級距', 'warning')
            return redirect(url_for('product.pricing'))

        new_default = PricingTier.query.filter(
            PricingTier.plan_type == tier.plan_type,
            PricingTier.is_active == True,
            PricingTier.id != tier.id,
        ).first()
        if new_default:
            new_default.is_default = True
            flash(f'已將「{new_default.tier_name}」設為新的預設級距', 'info')

    tier_name = tier.tier_name
    db.session.delete(tier)
    db.session.commit()
    flash(f'成功刪除價格級距：{tier_name}', 'success')
    return redirect(url_for('product.pricing'))


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@product_bp.route('/api/modules')
@login_required
def api_modules():
    """取得啟用中模組列表"""
    modules = Module.query.filter_by(is_active=True).order_by(Module.sort_order.asc()).all()
    return jsonify([{
        'id':             m.id,
        'name':           m.name,
        'code':           m.code,
        'description':    m.description,
        'function_count': len(m.get_active_functions()),
    } for m in modules])


@product_bp.route('/api/modules/<int:module_id>/functions')
@login_required
def api_module_functions(module_id):
    """取得指定模組的啟用功能列表"""
    module    = Module.query.get_or_404(module_id)
    functions = module.get_active_functions()
    return jsonify([{
        'id':             f.id,
        'name':           f.name,
        'code':           f.code,
        'points_per_unit': f.points_per_unit,
        'unit_name':      f.unit_name,
        'description':    f.description,
    } for f in functions])


@product_bp.route('/api/quote/calculate', methods=['POST'])
@login_required
def api_calculate_quote():
    """計算報價 API（JSON）"""
    data               = request.get_json() or {}
    selected_functions = data.get('functions', [])

    for item in selected_functions:
        if 'function_id' not in item or 'quantity' not in item:
            return jsonify({'error': '資料格式不正確'}), 400

    return jsonify(calculate_quote_summary(selected_functions))
