from flask import render_template
from flask_login import login_required, current_user

from app.blueprints.dashboard import dashboard_bp
from app.models.booking import get_pending_bookings_count, get_expiring_bookings
from app.models.bom import get_pending_boms_count


@dashboard_bp.route('/')
@login_required
def index():
    """
    儀表板首頁
    依角色提供不同的統計資料
    """
    stats = _build_stats(current_user)
    return render_template('dashboard/index.html', stats=stats)


# ---------------------------------------------------------------------------
# 統計資料組裝
# ---------------------------------------------------------------------------

def _build_stats(user):
    """
    依使用者角色組裝 Dashboard 統計資料

    回傳字典供 Template 使用，所有欄位皆有預設值，
    避免 Template 因資料缺失而報錯
    """
    stats = {
        'pending_bookings':  0,
        'expiring_bookings': 0,
        'pending_boms':      0,
    }

    # admin / pm 顯示全系統待審核數量
    if user.has_role('admin') or user.has_role('pm'):
        stats['pending_bookings']  = get_pending_bookings_count()
        stats['pending_boms']      = get_pending_boms_count()
        stats['expiring_bookings'] = len(get_expiring_bookings(days=7))

    # sales 顯示自己相關的待審核數量
    elif user.has_role('sales'):
        from app.models.booking import CustomerBooking
        from app.models.bom import BOM
        from app.models import db

        stats['pending_bookings'] = CustomerBooking.query.filter(
            CustomerBooking.created_by_id == user.id,
            CustomerBooking.status        == 'pending',
            CustomerBooking.is_deleted    == False
        ).count()

        stats['pending_boms'] = BOM.query.filter(
            BOM.assigned_sales_id == user.id,
            BOM.status            == 'pending',
            BOM.is_deleted        == False
        ).count()

    return stats
