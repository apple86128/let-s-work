from datetime import datetime
from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user

from app.blueprints.kpi import kpi_bp
from app.models import db
from app.models.kpi import AnnualKpiTarget, get_kpi_statistics
from app.utils.permissions import permission_required


# ---------------------------------------------------------------------------
# 工具函數
# ---------------------------------------------------------------------------

def _current_year():
    """取得當前年份"""
    return datetime.utcnow().year


def _available_years():
    """
    產生可選擇的年份清單
    範圍：系統最早有 BOM 批准記錄的年份 ~ 明年
    若查無記錄則預設從今年開始
    """
    from app.models.bom import BOM

    earliest = db.session.query(
        db.func.min(db.func.strftime('%Y', BOM.reviewed_at))
    ).filter(BOM.reviewed_at.isnot(None)).scalar()

    start_year = int(earliest) if earliest else _current_year()
    end_year   = _current_year() + 1

    return list(range(start_year, end_year + 1))


def _calc_rate(actual, target):
    """安全計算達成率（%），target 為 0 時回傳 0"""
    if not target:
        return 0
    return round(actual / target * 100, 1)


# ---------------------------------------------------------------------------
# KPI 總覽
# ---------------------------------------------------------------------------

@kpi_bp.route('/')
@login_required
@permission_required('kpi_view')
def dashboard():
    """年度 KPI 統計總覽頁"""
    year           = request.args.get('year', _current_year(), type=int)
    available_years = _available_years()

    # 確保選擇的年份在合法範圍內
    if year not in available_years:
        year = _current_year()

    # 取得（或建立）年度目標
    target = AnnualKpiTarget.get_or_create(year, created_by_id=current_user.id)
    db.session.commit()

    # 計算統計數據
    stats = get_kpi_statistics(year)

    # 計算達成率（以「已入帳」為分子）
    billed_product = stats['billed']['total']['product_amount']
    billed_labor   = stats['billed']['total']['labor_amount']

    rates = {
        'product': _calc_rate(billed_product, target.product_target),
        'labor':   _calc_rate(billed_labor,   target.labor_target),
        'total':   _calc_rate(
            billed_product + billed_labor,
            target.product_target + target.labor_target
        ),
    }

    return render_template(
        'kpi/dashboard.html',
        year            = year,
        available_years = available_years,
        target          = target,
        stats           = stats,
        rates           = rates,
    )


# ---------------------------------------------------------------------------
# 目標設定（POST only）
# ---------------------------------------------------------------------------

@kpi_bp.route('/target/save', methods=['POST'])
@login_required
@permission_required('kpi_manage')
def save_target():
    """儲存年度 KPI 目標值"""
    year           = request.form.get('year', type=int)
    product_target = request.form.get('product_target', type=int) or 0
    labor_target   = request.form.get('labor_target',   type=int) or 0
    notes          = request.form.get('notes', '').strip() or None

    if not year:
        flash('年份參數錯誤', 'warning')
        return redirect(url_for('kpi.dashboard'))

    if product_target < 0 or labor_target < 0:
        flash('目標金額不可為負數', 'warning')
        return redirect(url_for('kpi.dashboard', year=year))

    target = AnnualKpiTarget.get_or_create(year, created_by_id=current_user.id)
    target.update(
        product_target = product_target,
        labor_target   = labor_target,
        updated_by_id  = current_user.id,
        notes          = notes,
    )
    db.session.commit()

    flash(f'{year} 年度目標已儲存', 'success')
    return redirect(url_for('kpi.dashboard', year=year))


# ---------------------------------------------------------------------------
# API：取得指定年度統計資料（供前端 AJAX 使用）
# ---------------------------------------------------------------------------

@kpi_bp.route('/api/stats')
@login_required
@permission_required('kpi_view')
def api_stats():
    """回傳指定年度 KPI 統計 JSON"""
    year   = request.args.get('year', _current_year(), type=int)
    stats  = get_kpi_statistics(year)
    target = AnnualKpiTarget.query.filter_by(year=year).first()

    product_target = target.product_target if target else 0
    labor_target   = target.labor_target   if target else 0

    billed_product = stats['billed']['total']['product_amount']
    billed_labor   = stats['billed']['total']['labor_amount']

    return jsonify({
        'year':   year,
        'target': {
            'product': product_target,
            'labor':   labor_target,
        },
        'rates': {
            'product': _calc_rate(billed_product, product_target),
            'labor':   _calc_rate(billed_labor,   labor_target),
        },
        'stats': stats,
    })
