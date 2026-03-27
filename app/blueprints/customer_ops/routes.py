from datetime import date
from flask import render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user

from app.blueprints.customer_ops import customer_ops_bp
from app.models import db
from app.models.customer_ops import CustomerAccount, AccountContract
from app.models.booking import CustomerBooking
from app.utils.permissions import permission_required, has_permission


# =============================================================================
# 工具函數
# =============================================================================

def _get_or_create_account(company_name, booking=None):
    """
    依公司名稱取得或建立 CustomerAccount
    若 booking 有傳入，則帶入聯絡資訊作為初始值
    """
    account = CustomerAccount.query.filter_by(company_name=company_name).first()
    if account:
        return account

    account = CustomerAccount(
        company_name   = company_name,
        company_tax_id = booking.company_tax_id  if booking else None,
        contact_person = booking.contact_person  if booking else None,
        contact_phone  = booking.contact_phone   if booking else None,
        contact_email  = booking.contact_email   if booking else None,
    )
    db.session.add(account)
    db.session.flush()
    return account


def _parse_date(value):
    """安全解析日期字串，失敗回傳 None"""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _get_parent_contract_ids(form):
    """
    從 form 取得多選的前一張合約 ID 列表
    checkbox 欄位名稱為 parent_contract_ids（複數）
    回傳 list[int]，可為空列表
    """
    raw = form.getlist('parent_contract_ids')
    result = []
    for v in raw:
        try:
            result.append(int(v))
        except (ValueError, TypeError):
            pass
    return result


# =============================================================================
# 客戶帳戶路由
# =============================================================================

@customer_ops_bp.route('/')
@login_required
@permission_required('customer_ops_view')
def index():
    """客戶帳戶列表"""
    accounts = CustomerAccount.query.order_by(CustomerAccount.company_name).all()
    return render_template('customer_ops/index.html', accounts=accounts)


@customer_ops_bp.route('/<int:account_id>')
@login_required
@permission_required('customer_ops_view')
def detail(account_id):
    """客戶帳戶 Dashboard"""
    account = CustomerAccount.query.get_or_404(account_id)

    # 自動更新已到期合約狀態
    for contract in account.contracts:
        contract.auto_expire()
    db.session.commit()

    return render_template('customer_ops/detail.html', account=account)


@customer_ops_bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('customer_ops_manage')
def create_account():
    """建立新客戶帳戶"""
    available_bookings = CustomerBooking.query.filter_by(
        status='approved', is_deleted=False
    ).order_by(CustomerBooking.created_at.desc()).all()

    if request.method == 'GET':
        return render_template('customer_ops/account_form.html',
                               account=None,
                               available_bookings=available_bookings)

    company_name = request.form.get('company_name', '').strip()
    if not company_name:
        flash('公司名稱為必填', 'danger')
        return render_template('customer_ops/account_form.html',
                               account=None,
                               available_bookings=available_bookings)

    if CustomerAccount.query.filter_by(company_name=company_name).first():
        flash(f'客戶帳戶「{company_name}」已存在', 'warning')
        return render_template('customer_ops/account_form.html',
                               account=None,
                               available_bookings=available_bookings)

    account = CustomerAccount(
        company_name   = company_name,
        company_tax_id = request.form.get('company_tax_id', '').strip() or None,
        contact_person = request.form.get('contact_person', '').strip() or None,
        contact_phone  = request.form.get('contact_phone',  '').strip() or None,
        contact_email  = request.form.get('contact_email',  '').strip() or None,
        notes          = request.form.get('notes',          '').strip() or None,
    )
    db.session.add(account)
    db.session.commit()

    flash(f'已建立客戶帳戶：{company_name}', 'success')
    return redirect(url_for('customer_ops.detail', account_id=account.id))


@customer_ops_bp.route('/<int:account_id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('customer_ops_manage')
def edit_account(account_id):
    """編輯客戶帳戶基本資料"""
    account = CustomerAccount.query.get_or_404(account_id)

    if request.method == 'GET':
        return render_template('customer_ops/account_form.html',
                               account=account,
                               available_bookings=[])

    account.company_tax_id = request.form.get('company_tax_id', '').strip() or None
    account.contact_person = request.form.get('contact_person', '').strip() or None
    account.contact_phone  = request.form.get('contact_phone',  '').strip() or None
    account.contact_email  = request.form.get('contact_email',  '').strip() or None
    account.notes          = request.form.get('notes',          '').strip() or None

    db.session.commit()
    flash(f'已更新客戶帳戶：{account.company_name}', 'success')
    return redirect(url_for('customer_ops.detail', account_id=account.id))


# =============================================================================
# 合約路由
# =============================================================================

@customer_ops_bp.route('/<int:account_id>/contracts/create', methods=['GET', 'POST'])
@login_required
@permission_required('customer_ops_manage')
def create_contract(account_id):
    """手動建立合約（通常由 BOM approved 自動觸發，此為補建用）"""
    account = CustomerAccount.query.get_or_404(account_id)

    from app.models.bom import BOM

    # 已被有效合約關聯的 BOM id 集合（排除軟刪除合約）
    linked_bom_ids = {c.bom_id for c in account.contracts if c.bom_id}

    # 可選 BOM：專案狀態為「已成案（won）」且未被有效合約關聯
    available_boms = BOM.query.filter(
        BOM.customer_company == account.company_name,
        BOM.project_status   == 'won',
        BOM.is_deleted       == False,
        BOM.id.notin_(linked_bom_ids)
    ).order_by(BOM.created_at.desc()).all()

    # 現有合約（供多選 checkbox：選擇被本次新合約繼承的舊合約）
    existing_contracts = AccountContract.query.filter(
        AccountContract.account_id == account_id,
        AccountContract.is_deleted == False
    ).order_by(AccountContract.created_at.desc()).all()

    if request.method == 'GET':
        return render_template('customer_ops/contract_form.html',
                               account=account,
                               contract=None,
                               available_boms=available_boms,
                               existing_contracts=existing_contracts,
                               selected_parent_ids=[])

    # ── POST 處理 ──
    bom_id        = request.form.get('bom_id', type=int)
    contract_type = request.form.get('contract_type', 'new')

    contract = AccountContract(
        account_id    = account_id,
        bom_id        = bom_id or None,
        contract_type = contract_type,
    )
    _fill_contract_fields(contract, request.form)
    db.session.add(contract)
    db.session.flush()   # 取得 contract.id，供多對多寫入

    # 寫入多對多前一張合約關聯
    parent_ids = _get_parent_contract_ids(request.form)
    contract.set_parent_contracts(parent_ids)

    db.session.commit()
    flash('合約已建立', 'success')
    return redirect(url_for('customer_ops.contract_detail',
                            account_id=account_id,
                            contract_id=contract.id))


@customer_ops_bp.route('/<int:account_id>/contracts/<int:contract_id>')
@login_required
@permission_required('customer_ops_view')
def contract_detail(account_id, contract_id):
    """合約詳情（含授權 KEY 顯示與複製）"""
    account  = CustomerAccount.query.get_or_404(account_id)
    contract = AccountContract.query.get_or_404(contract_id)

    if contract.account_id != account_id:
        flash('合約不屬於此客戶帳戶', 'danger')
        return redirect(url_for('customer_ops.detail', account_id=account_id))

    renewal_chain = contract.renewal_chain

    return render_template('customer_ops/contract_detail.html',
                           account=account,
                           contract=contract,
                           renewal_chain=renewal_chain)


@customer_ops_bp.route('/<int:account_id>/contracts/<int:contract_id>/edit',
                        methods=['GET', 'POST'])
@login_required
@permission_required('customer_ops_manage')
def edit_contract(account_id, contract_id):
    """編輯合約資訊（含授權 KEY 填寫）"""
    account  = CustomerAccount.query.get_or_404(account_id)
    contract = AccountContract.query.get_or_404(contract_id)

    if contract.account_id != account_id:
        flash('合約不屬於此客戶帳戶', 'danger')
        return redirect(url_for('customer_ops.detail', account_id=account_id))

    # 現有合約清單（排除本張自身，避免循環繼承）
    existing_contracts = AccountContract.query.filter(
        AccountContract.account_id == account_id,
        AccountContract.id         != contract_id,
        AccountContract.is_deleted == False
    ).order_by(AccountContract.created_at.desc()).all()

    # 目前已選的前一張合約 id 列表（供 template 預設勾選）
    selected_parent_ids = [c.id for c in contract.active_parent_contracts]

    if request.method == 'GET':
        return render_template('customer_ops/contract_form.html',
                               account=account,
                               contract=contract,
                               available_boms=[],
                               existing_contracts=existing_contracts,
                               selected_parent_ids=selected_parent_ids)

    # ── POST 處理 ──
    _fill_contract_fields(contract, request.form)

    # 狀態只允許 admin / pm 修改
    if has_permission(current_user, 'customer_ops_manage'):
        new_status = request.form.get('status')
        if new_status in ('active', 'expired', 'cancelled'):
            contract.status = new_status

    # 更新多對多前一張合約關聯
    parent_ids = _get_parent_contract_ids(request.form)
    contract.set_parent_contracts(parent_ids)

    # contract_type 同步更新（有選 parent 則視為 renewal）
    contract.contract_type = request.form.get('contract_type', 'new')

    db.session.commit()
    flash('合約已更新', 'success')
    return redirect(url_for('customer_ops.contract_detail',
                            account_id=account_id,
                            contract_id=contract_id))


@customer_ops_bp.route('/<int:account_id>/contracts/<int:contract_id>/return',
                        methods=['POST'])
@login_required
def return_contract(account_id, contract_id):
    """退回合約（軟刪除）— admin / pm 專用

    執行後合約記錄保留但標記為已刪除，
    讓同一張 BOM 可從客戶頁面手動重新建立合約。
    """
    if not (current_user.has_role('admin') or current_user.has_role('pm')):
        flash('您沒有權限退回合約', 'danger')
        return redirect(url_for('customer_ops.contract_detail',
                                account_id=account_id,
                                contract_id=contract_id))

    contract = AccountContract.query.get_or_404(contract_id)

    if contract.account_id != account_id:
        flash('合約不屬於此客戶帳戶', 'danger')
        return redirect(url_for('customer_ops.detail', account_id=account_id))

    if contract.is_deleted:
        flash('此合約已經退回，無法重複操作', 'warning')
        return redirect(url_for('customer_ops.detail', account_id=account_id))

    contract.soft_delete(current_user.id)
    db.session.commit()

    flash('合約已退回，可從客戶頁面重新建立合約並選擇對應 BOM', 'success')
    return redirect(url_for('customer_ops.detail', account_id=account_id))


@customer_ops_bp.route('/<int:account_id>/contracts/<int:contract_id>/unlink-bom',
                        methods=['POST'])
@login_required
def unlink_bom(account_id, contract_id):
    """解除合約與 BOM 的關聯（admin / pm 專用）"""
    if not (current_user.has_role('admin') or current_user.has_role('pm')):
        flash('您沒有權限執行此操作', 'danger')
        return redirect(url_for('customer_ops.contract_detail',
                                account_id=account_id,
                                contract_id=contract_id))

    contract = AccountContract.query.get_or_404(contract_id)

    if contract.account_id != account_id:
        flash('合約不屬於此客戶帳戶', 'danger')
        return redirect(url_for('customer_ops.detail', account_id=account_id))

    if not contract.bom_id:
        flash('此合約目前未關聯任何 BOM', 'warning')
        return redirect(url_for('customer_ops.contract_detail',
                                account_id=account_id,
                                contract_id=contract_id))

    bom_number      = contract.source_bom.bom_number if contract.source_bom else '（未知）'
    contract.bom_id = None
    db.session.commit()

    flash(f'已解除與 BOM {bom_number} 的關聯', 'success')
    return redirect(url_for('customer_ops.contract_detail',
                            account_id=account_id,
                            contract_id=contract_id))


# =============================================================================
# 工具：填入合約欄位（create / edit 共用）
# =============================================================================

def _fill_contract_fields(contract, form):
    """從 form 資料填入合約欄位（不含 parent 關聯，由呼叫端另行處理）"""
    contract.contract_number      = form.get('contract_number', '').strip() or None
    contract.project_code         = form.get('project_code',   '').strip() or None
    contract.start_date           = _parse_date(form.get('start_date'))
    contract.end_date             = _parse_date(form.get('end_date'))
    contract.license_request_code = form.get('license_request_code', '').strip() or None
    contract.license_issue_code   = form.get('license_issue_code',   '').strip() or None
