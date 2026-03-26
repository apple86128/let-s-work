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
    year            = request.args.get('year', _current_year(), type=int)
    available_years = _available_years()

    if year not in available_years:
        year = _current_year()

    # 取得（或建立）年度目標
    target = AnnualKpiTarget.get_or_create(year, created_by_id=current_user.id)
    db.session.commit()

    # 計算統計數據（季度依據：Project.start_date）
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
# API：取得指定區塊的 BOM 明細（供 Modal 使用）
# ---------------------------------------------------------------------------

@kpi_bp.route('/api/detail')
@login_required
@permission_required('kpi_view')
def api_detail():
    """
    回傳指定年度、指定區塊的 BOM 明細列表
    segment 參數：planning / billed_total / billed_q1~q4 / lost
    """
    year    = request.args.get('year',    _current_year(), type=int)
    segment = request.args.get('segment', 'planning')

    boms = _get_segment_boms(year, segment)

    return jsonify({
        'year':    year,
        'segment': segment,
        'count':   len(boms),
        'items': [{
            'bom_number':      b.bom_number,
            'bom_id':          b.id,
            'customer_company': b.customer_company,
            'project_name':    b.project_name,
            'final_price':     b.final_price or 0,
            'final_maintenance_price': b.final_maintenance_price or 0,
            'total':           (b.final_price or 0) + (b.final_maintenance_price or 0),
            'sales_name':      b.assigned_sales.name if b.assigned_sales else '-',
            'project_status':  b.get_project_status_display(),
            'won_at':          b.won_at.strftime('%Y-%m-%d') if b.won_at else '-',
        } for b in boms],
    })


# ---------------------------------------------------------------------------
# API：下載指定區塊的 CSV 報表
# ---------------------------------------------------------------------------

@kpi_bp.route('/api/export')
@login_required
@permission_required('kpi_view')
def api_export():
    """
    下載指定年度、指定區塊的 BOM 明細 CSV
    """
    import csv, io
    from flask import Response

    year    = request.args.get('year',    _current_year(), type=int)
    segment = request.args.get('segment', 'planning')

    SEGMENT_LABELS = {
        'planning':     'planning',
        'billed_total': 'billed_all',
        'billed_q1':    'billed_Q1',
        'billed_q2':    'billed_Q2',
        'billed_q3':    'billed_Q3',
        'billed_q4':    'billed_Q4',
        'lost':         'lost',
    }

    boms  = _get_segment_boms(year, segment)
    label = SEGMENT_LABELS.get(segment, segment)

    output = io.StringIO()
    # 加上 BOM header 讓 Excel 正確辨識 UTF-8
    output.write('\ufeff')
    writer = csv.writer(output)

    writer.writerow(['BOM 編號', '客戶公司', '專案名稱', '產品金額', '人力金額',
                     '合計金額', '負責業務', '專案狀態', '入帳日期'])

    for b in boms:
        writer.writerow([
            b.bom_number,
            b.customer_company,
            b.project_name,
            b.final_price or 0,
            b.final_maintenance_price or 0,
            (b.final_price or 0) + (b.final_maintenance_price or 0),
            b.assigned_sales.name if b.assigned_sales else '-',
            b.get_project_status_display(),
            b.won_at.strftime('%Y-%m-%d') if b.won_at else '-',
        ])

    filename = f'KPI_{year}_{label}.csv'
    return Response(
        output.getvalue(),
        mimetype='text/csv; charset=utf-8-sig',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


# ---------------------------------------------------------------------------
# 工具：依 segment 取得對應 BOM 列表
# ---------------------------------------------------------------------------

def _get_segment_boms(year, segment):
    """依 segment 參數回傳對應的 BOM 物件列表"""
    from app.models.bom import BOM

    PLANNING_STATUSES = ('none', 'poc', 'bidding')

    QUARTER_MONTHS = {
        'billed_q1': (1,  3),
        'billed_q2': (4,  6),
        'billed_q3': (7,  9),
        'billed_q4': (10, 12),
    }

    if segment == 'planning':
        return BOM.query.filter(
            BOM.project_status.in_(PLANNING_STATUSES),
            BOM.is_deleted == False,
        ).order_by(BOM.created_at.desc()).all()

    if segment == 'lost':
        return BOM.query.filter(
            BOM.project_status == 'closed',
            BOM.is_deleted == False,
        ).order_by(BOM.created_at.desc()).all()

    # billed_total 或 billed_q1~q4
    base_query = BOM.query.filter(
        BOM.project_status == 'won',
        BOM.won_at.isnot(None),
        db.func.strftime('%Y', BOM.won_at) == str(year),
        BOM.is_deleted == False,
    )

    if segment == 'billed_total':
        return base_query.order_by(BOM.won_at.desc()).all()

    if segment in QUARTER_MONTHS:
        start_m, end_m = QUARTER_MONTHS[segment]
        all_won = base_query.all()
        return [
            b for b in all_won
            if b.won_at and start_m <= b.won_at.month <= end_m
        ]

    return []
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
