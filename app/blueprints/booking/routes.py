from datetime import datetime
from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user

from app.blueprints.booking import booking_bp
from app.models import db
from app.models.user import Role
from app.models.booking import (
    CustomerBooking,
    BookingExtensionRequest,
    get_bookings_for_user,
    get_expiring_bookings,
    update_expired_bookings,
)
from app.models.bom import BOM
from app.utils.permissions import has_permission, permission_required


# ---------------------------------------------------------------------------
# 工具函數
# ---------------------------------------------------------------------------

def _get_sales_users():
    """取得所有啟用中的業務人員（供指派下拉使用）"""
    sales_role = Role.query.filter_by(name='sales').first()
    if not sales_role:
        return []
    return [u for u in sales_role.users if u.is_active]


def _build_stats(query_base):
    """依傳入的 query 物件計算各狀態統計數量"""
    return {
        'total':    query_base.count(),
        'pending':  query_base.filter_by(status='pending').count(),
        'approved': query_base.filter_by(status='approved').count(),
        'rejected': query_base.filter_by(status='rejected').count(),
        'expired':  query_base.filter_by(status='expired').count(),
    }


def _parse_date(date_str):
    """安全解析日期字串，格式 YYYY-MM-DD，失敗回傳 None"""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# 列表
# ---------------------------------------------------------------------------

@booking_bp.route('/')
@login_required
@permission_required('booking_view_own')
def index():
    """Booking 列表頁面"""

    # 每次進入列表時更新過期狀態
    update_expired_bookings()

    page          = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    search_query  = request.args.get('search', '')
    per_page      = 20

    # 依角色取得可查看的 Booking
    bookings_query = get_bookings_for_user(current_user)

    if status_filter:
        bookings_query = bookings_query.filter(CustomerBooking.status == status_filter)

    if search_query:
        bookings_query = bookings_query.filter(
            db.or_(
                CustomerBooking.company_name.contains(search_query),
                CustomerBooking.contact_person.contains(search_query),
                CustomerBooking.project_requirements.contains(search_query),
            )
        )

    bookings = bookings_query.paginate(page=page, per_page=per_page, error_out=False)

    # 統計：全局（admin/pm）或個人（sales）
    if has_permission(current_user, 'booking_view_all'):
        stats_base       = CustomerBooking.query.filter_by(is_deleted=False)
        expiring         = get_expiring_bookings(days=7)
    else:
        stats_base       = get_bookings_for_user(current_user)
        expiring         = []

    stats = _build_stats(stats_base)

    return render_template('booking/list.html',
                           bookings=bookings,
                           stats=stats,
                           expiring_bookings=expiring,
                           status_filter=status_filter,
                           search_query=search_query)


# ---------------------------------------------------------------------------
# 詳情
# ---------------------------------------------------------------------------

@booking_bp.route('/<int:booking_id>')
@login_required
def detail(booking_id):
    """Booking 詳情頁面"""
    booking = CustomerBooking.query.get_or_404(booking_id)

    if not booking.can_be_viewed_by(current_user) \
            and not has_permission(current_user, 'booking_view_all'):
        flash('您沒有權限查看此 Booking', 'danger')
        return redirect(url_for('booking.index'))

    extension_requests = BookingExtensionRequest.query.filter_by(
        booking_id=booking_id
    ).order_by(BookingExtensionRequest.requested_at.desc()).all()

    related_boms = BOM.query.filter_by(
        booking_id=booking_id,
        is_deleted=False
    ).order_by(BOM.created_at.desc()).all()

    return render_template('booking/detail.html',
                           booking=booking,
                           extension_requests=extension_requests,
                           related_boms=related_boms)


# ---------------------------------------------------------------------------
# 建立
# ---------------------------------------------------------------------------

@booking_bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('booking_create')
def create():
    """建立新 Booking"""
    can_assign = has_permission(current_user, 'booking_view_all')
    sales_users = _get_sales_users() if can_assign else []

    if request.method == 'GET':
        return render_template('booking/form.html',
                               booking=None,
                               sales_users=sales_users)

    # POST：取得表單資料
    company_name    = request.form.get('company_name', '').strip()
    budget_max      = request.form.get('budget_max', type=int)
    budget_min      = request.form.get('budget_min', type=int) or budget_max
    project_req     = request.form.get('project_requirements', '').strip()
    start_date      = _parse_date(request.form.get('expected_start_date'))
    duration_months = request.form.get('project_duration_months', type=int)
    assigned_id     = request.form.get('assigned_sales_id', type=int) if can_assign else None

    # 欄位驗證
    if not company_name:
        flash('請輸入公司名稱', 'warning')
        return render_template('booking/form.html', booking=None, sales_users=sales_users)

    if not budget_max or budget_max <= 0:
        flash('請輸入有效的預算上限', 'warning')
        return render_template('booking/form.html', booking=None, sales_users=sales_users)

    if not project_req:
        flash('請輸入專案需求', 'warning')
        return render_template('booking/form.html', booking=None, sales_users=sales_users)

    new_booking = CustomerBooking(
        company_name             = company_name,
        company_tax_id           = request.form.get('company_tax_id', '').strip() or None,
        contact_person           = request.form.get('contact_person', '').strip() or None,
        contact_phone            = request.form.get('contact_phone', '').strip() or None,
        contact_email            = request.form.get('contact_email', '').strip() or None,
        budget_min               = budget_min,
        budget_max               = budget_max,
        project_requirements     = project_req,
        expected_start_date      = start_date,
        project_duration_months  = duration_months,
        created_by_id            = current_user.id,
        assigned_sales_id        = assigned_id or current_user.id,
    )

    db.session.add(new_booking)
    db.session.commit()
    flash(f'成功建立 Booking：{company_name}', 'success')
    return redirect(url_for('booking.detail', booking_id=new_booking.id))


# ---------------------------------------------------------------------------
# 編輯
# ---------------------------------------------------------------------------

@booking_bp.route('/<int:booking_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(booking_id):
    """編輯 Booking"""
    booking = CustomerBooking.query.get_or_404(booking_id)

    if not booking.can_be_edited_by(current_user):
        flash('您沒有權限編輯此 Booking', 'danger')
        return redirect(url_for('booking.detail', booking_id=booking_id))

    can_assign  = has_permission(current_user, 'booking_view_all')
    sales_users = _get_sales_users() if can_assign else []

    if request.method == 'GET':
        return render_template('booking/form.html',
                               booking=booking,
                               sales_users=sales_users)

    # POST：更新欄位
    company_name = request.form.get('company_name', '').strip()
    budget_max   = request.form.get('budget_max', type=int)
    budget_min   = request.form.get('budget_min', type=int) or budget_max
    project_req  = request.form.get('project_requirements', '').strip()

    if not company_name or not budget_max or not project_req:
        flash('請填寫所有必填欄位', 'warning')
        return render_template('booking/form.html', booking=booking, sales_users=sales_users)

    booking.company_name            = company_name
    booking.company_tax_id          = request.form.get('company_tax_id', '').strip() or None
    booking.contact_person          = request.form.get('contact_person', '').strip() or None
    booking.contact_phone           = request.form.get('contact_phone', '').strip() or None
    booking.contact_email           = request.form.get('contact_email', '').strip() or None
    booking.budget_min              = budget_min
    booking.budget_max              = budget_max
    booking.project_requirements    = project_req
    booking.expected_start_date     = _parse_date(request.form.get('expected_start_date'))
    booking.project_duration_months = request.form.get('project_duration_months', type=int)

    if can_assign:
        assigned_id = request.form.get('assigned_sales_id', type=int)
        if assigned_id:
            booking.assigned_sales_id = assigned_id

    # 業務人員修改後需重新審核
    if current_user.has_role('sales') and booking.status != 'pending':
        booking.status         = 'pending'
        booking.reviewed_by_id = None
        booking.reviewed_at    = None
        booking.review_notes   = None
        flash('Booking 已更新，需要重新審核', 'info')

    db.session.commit()
    flash(f'成功更新 Booking：{booking.company_name}', 'success')
    return redirect(url_for('booking.detail', booking_id=booking_id))


# ---------------------------------------------------------------------------
# 刪除
# ---------------------------------------------------------------------------

@booking_bp.route('/<int:booking_id>/delete', methods=['POST'])
@login_required
def delete(booking_id):
    """軟刪除 Booking"""
    booking = CustomerBooking.query.get_or_404(booking_id)

    if not (booking.created_by_id == current_user.id
            or has_permission(current_user, 'booking_delete')):
        flash('您沒有權限刪除此 Booking', 'danger')
        return redirect(url_for('booking.detail', booking_id=booking_id))

    booking.soft_delete(current_user.id)
    db.session.commit()
    flash(f'已刪除 Booking：{booking.company_name}', 'success')
    return redirect(url_for('booking.index'))


# ---------------------------------------------------------------------------
# 審核
# ---------------------------------------------------------------------------

@booking_bp.route('/<int:booking_id>/review', methods=['POST'])
@login_required
def review(booking_id):
    """審核 Booking（admin / pm 專用）"""
    booking = CustomerBooking.query.get_or_404(booking_id)

    if not booking.can_be_reviewed_by(current_user):
        flash('您沒有權限審核此 Booking', 'danger')
        return redirect(url_for('booking.detail', booking_id=booking_id))

    action = request.form.get('action')
    notes  = request.form.get('notes', '').strip()

    if action == 'approve':
        booking.approve(current_user.id, notes)
        flash(f'已批准 Booking：{booking.company_name}', 'success')
    elif action == 'reject':
        booking.reject(current_user.id, notes)
        flash(f'已拒絕 Booking：{booking.company_name}', 'info')
    else:
        flash('無效的審核操作', 'warning')
        return redirect(url_for('booking.detail', booking_id=booking_id))

    db.session.commit()
    return redirect(url_for('booking.detail', booking_id=booking_id))


# ---------------------------------------------------------------------------
# 展延申請
# ---------------------------------------------------------------------------

@booking_bp.route('/<int:booking_id>/extend', methods=['GET', 'POST'])
@login_required
def request_extension(booking_id):
    """申請 Booking 展延"""
    booking = CustomerBooking.query.get_or_404(booking_id)

    if not booking.can_request_extension():
        flash('此 Booking 目前無法申請展延', 'warning')
        return redirect(url_for('booking.detail', booking_id=booking_id))

    is_related = (
        booking.created_by_id    == current_user.id
        or booking.assigned_sales_id == current_user.id
        or current_user.has_role('admin')
        or current_user.has_role('pm')
    )
    if not is_related:
        flash('您沒有權限為此 Booking 申請展延', 'danger')
        return redirect(url_for('booking.detail', booking_id=booking_id))

    if request.method == 'GET':
        return render_template('booking/extend.html', booking=booking)

    # POST：建立展延申請
    requested_days = request.form.get('requested_days', type=int)
    reason         = request.form.get('reason', '').strip()

    if not requested_days or not (1 <= requested_days <= 90):
        flash('展延天數必須在 1–90 天之間', 'warning')
        return render_template('booking/extend.html', booking=booking)

    if not reason:
        flash('請填寫展延理由', 'warning')
        return render_template('booking/extend.html', booking=booking)

    ext_req = BookingExtensionRequest(
        booking_id      = booking_id,
        requested_days  = requested_days,
        reason          = reason,
        requested_by_id = current_user.id,
    )
    db.session.add(ext_req)
    db.session.commit()
    flash('展延申請已提交，等待審核', 'success')
    return redirect(url_for('booking.detail', booking_id=booking_id))


@booking_bp.route('/extension/<int:request_id>/review', methods=['POST'])
@login_required
def review_extension(request_id):
    """審核展延申請（admin / pm 專用）"""
    ext_req = BookingExtensionRequest.query.get_or_404(request_id)

    if not (current_user.has_role('admin') or current_user.has_role('pm')):
        flash('您沒有權限審核展延申請', 'danger')
        return redirect(url_for('booking.detail', booking_id=ext_req.booking_id))

    if ext_req.status != 'pending':
        flash('此展延申請已審核過', 'warning')
        return redirect(url_for('booking.detail', booking_id=ext_req.booking_id))

    action = request.form.get('action')
    notes  = request.form.get('notes', '').strip()

    if action == 'approve':
        ext_req.approve(current_user.id, notes)
        flash(f'已批准展延：延長 {ext_req.requested_days} 天', 'success')
    elif action == 'reject':
        ext_req.reject(current_user.id, notes)
        flash('已拒絕展延申請', 'info')
    else:
        flash('無效的審核操作', 'warning')
        return redirect(url_for('booking.detail', booking_id=ext_req.booking_id))

    db.session.commit()
    return redirect(url_for('booking.detail', booking_id=ext_req.booking_id))


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@booking_bp.route('/api/sales-users')
@login_required
def api_sales_users():
    """取得業務人員列表（admin / pm 專用）"""
    if not has_permission(current_user, 'booking_view_all'):
        return jsonify({'error': 'Permission denied'}), 403

    users = _get_sales_users()
    return jsonify([{
        'id':        u.id,
        'name':      u.name,
        'email':     u.email,
        'extension': u.extension,
    } for u in users])
