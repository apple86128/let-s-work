import os
import uuid
from datetime import datetime
from flask import render_template, request, flash, redirect, url_for, send_from_directory, abort
from flask_login import login_required, current_user

from app.blueprints.project import project_bp
from app.models import db
from app.models.user import User, Role
from app.models.bom import BOM
from app.models.project import (
    Project, ProjectMilestone, ProjectMember, ProjectAttachment,
    get_projects_for_user
)
from app.utils.permissions import permission_required

# 附件上傳目錄（相對於專案根目錄）
UPLOAD_FOLDER = os.path.join(
    os.path.abspath(os.path.dirname(__file__)),
    '..', '..', '..', 'uploads', 'project_attachments'
)
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
                      'png', 'jpg', 'jpeg', 'gif', 'zip', 'rar', 'txt', 'csv'}


# ---------------------------------------------------------------------------
# 工具函數
# ---------------------------------------------------------------------------

def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _get_engineers():
    """取得所有啟用中的工程師"""
    role = Role.query.filter_by(name='engineer').first()
    if not role:
        return []
    return [u for u in role.users if u.is_active]


def _get_project_managers():
    """取得所有啟用中的專案管理員"""
    role = Role.query.filter_by(name='project_manager').first()
    if not role:
        return []
    return [u for u in role.users if u.is_active]


def _get_approved_boms():
    """取得已批准且尚未建立專案的 BOM 列表"""
    used_bom_ids = [p.bom_id for p in Project.query.filter(
        Project.bom_id.isnot(None), Project.is_deleted == False
    ).all()]
    query = BOM.query.filter_by(status='approved', is_deleted=False)
    if used_bom_ids:
        query = query.filter(~BOM.id.in_(used_bom_ids))
    return query.order_by(BOM.created_at.desc()).all()


def _parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return None


def _ensure_upload_dir():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ---------------------------------------------------------------------------
# 列表
# ---------------------------------------------------------------------------

@project_bp.route('/')
@login_required
@permission_required('project_view_all')
def index():
    """專案列表"""
    status_filter = request.args.get('status', '')
    search_query  = request.args.get('search', '')
    page          = request.args.get('page', 1, type=int)
    per_page      = 20

    query = get_projects_for_user(current_user)

    if status_filter:
        query = query.filter(Project.status == status_filter)
    if search_query:
        query = query.filter(
            db.or_(
                Project.name.contains(search_query),
                Project.customer.contains(search_query),
            )
        )

    projects = query.paginate(page=page, per_page=per_page, error_out=False)

    # 各狀態數量統計
    base  = get_projects_for_user(current_user)
    stats = {s: base.filter(Project.status == s).count()
             for s in Project.STATUS_DISPLAY}

    return render_template('project/list.html',
                           projects=projects,
                           stats=stats,
                           status_filter=status_filter,
                           search_query=search_query,
                           status_display=Project.STATUS_DISPLAY,
                           now=datetime.utcnow())


# ---------------------------------------------------------------------------
# 詳情
# ---------------------------------------------------------------------------

@project_bp.route('/<int:project_id>')
@login_required
def detail(project_id):
    """專案詳情"""
    project = Project.query.get_or_404(project_id)

    if not project.can_be_viewed_by(current_user):
        flash('您沒有權限查看此專案', 'danger')
        return redirect(url_for('project.index'))

    engineers        = _get_engineers()
    project_managers = _get_project_managers()

    return render_template('project/detail.html',
                           project=project,
                           engineers=engineers,
                           project_managers=project_managers)


# ---------------------------------------------------------------------------
# 建立
# ---------------------------------------------------------------------------

@project_bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('project_create')
def create():
    """建立新專案"""
    approved_boms    = _get_approved_boms()
    project_managers = _get_project_managers()
    engineers        = _get_engineers()

    if request.method == 'GET':
        return render_template('project/form.html',
                               project=None,
                               approved_boms=approved_boms,
                               project_managers=project_managers,
                               engineers=engineers)

    # POST
    name               = request.form.get('name', '').strip()
    customer           = request.form.get('customer', '').strip()
    description        = request.form.get('description', '').strip() or None
    source_type        = request.form.get('source_type', 'direct')
    bom_id             = request.form.get('bom_id', type=int) or None
    project_manager_id = request.form.get('project_manager_id', type=int) or None
    start_date         = _parse_date(request.form.get('start_date'))
    expected_end       = _parse_date(request.form.get('expected_end'))
    member_ids         = request.form.getlist('member_ids')

    if not name or not customer:
        flash('請填寫專案名稱與客戶名稱', 'warning')
        return render_template('project/form.html',
                               project=None,
                               approved_boms=approved_boms,
                               project_managers=project_managers,
                               engineers=engineers)

    new_project = Project(
        name               = name,
        customer           = customer,
        description        = description,
        source_type        = source_type,
        bom_id             = bom_id if source_type == 'from_bom' else None,
        project_manager_id = project_manager_id,
        start_date         = start_date,
        expected_end       = expected_end,
        created_by_id      = current_user.id,
    )
    db.session.add(new_project)
    db.session.flush()

    for uid in member_ids:
        try:
            db.session.add(ProjectMember(project_id=new_project.id, user_id=int(uid)))
        except (ValueError, TypeError):
            continue

    db.session.commit()
    flash(f'成功建立專案：{name}', 'success')
    return redirect(url_for('project.detail', project_id=new_project.id))


# ---------------------------------------------------------------------------
# 編輯
# ---------------------------------------------------------------------------

@project_bp.route('/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(project_id):
    """編輯專案"""
    project = Project.query.get_or_404(project_id)

    if not project.can_be_edited_by(current_user):
        flash('您沒有權限編輯此專案', 'danger')
        return redirect(url_for('project.detail', project_id=project_id))

    project_managers = _get_project_managers()
    engineers        = _get_engineers()

    if request.method == 'GET':
        return render_template('project/form.html',
                               project=project,
                               approved_boms=[],
                               project_managers=project_managers,
                               engineers=engineers)

    # POST
    name               = request.form.get('name', '').strip()
    customer           = request.form.get('customer', '').strip()
    description        = request.form.get('description', '').strip() or None
    project_manager_id = request.form.get('project_manager_id', type=int) or None
    start_date         = _parse_date(request.form.get('start_date'))
    expected_end       = _parse_date(request.form.get('expected_end'))
    actual_end         = _parse_date(request.form.get('actual_end'))
    member_ids         = request.form.getlist('member_ids')

    if not name or not customer:
        flash('請填寫專案名稱與客戶名稱', 'warning')
        return render_template('project/form.html',
                               project=project,
                               approved_boms=[],
                               project_managers=project_managers,
                               engineers=engineers)

    project.name               = name
    project.customer           = customer
    project.description        = description
    project.project_manager_id = project_manager_id
    project.start_date         = start_date
    project.expected_end       = expected_end
    project.actual_end         = actual_end

    # 重建成員清單
    ProjectMember.query.filter_by(project_id=project.id).delete()
    for uid in member_ids:
        try:
            db.session.add(ProjectMember(project_id=project.id, user_id=int(uid)))
        except (ValueError, TypeError):
            continue

    db.session.commit()
    flash(f'成功更新專案：{name}', 'success')
    return redirect(url_for('project.detail', project_id=project_id))


# ---------------------------------------------------------------------------
# 更新狀態
# ---------------------------------------------------------------------------

@project_bp.route('/<int:project_id>/status', methods=['POST'])
@login_required
def update_status(project_id):
    """更新專案狀態"""
    project = Project.query.get_or_404(project_id)

    if not project.can_update_status_by(current_user):
        flash('您沒有權限更新此專案狀態', 'danger')
        return redirect(url_for('project.detail', project_id=project_id))

    new_status = request.form.get('status')
    if new_status not in Project.STATUS_DISPLAY:
        flash('無效的狀態值', 'warning')
        return redirect(url_for('project.detail', project_id=project_id))

    project.status = new_status
    db.session.commit()
    flash(f'專案狀態已更新為：{project.status_display}', 'success')
    return redirect(url_for('project.detail', project_id=project_id))


# ---------------------------------------------------------------------------
# 刪除
# ---------------------------------------------------------------------------

@project_bp.route('/<int:project_id>/delete', methods=['POST'])
@login_required
def delete(project_id):
    """軟刪除專案"""
    project = Project.query.get_or_404(project_id)

    if not project.can_be_deleted_by(current_user):
        flash('您沒有權限刪除此專案', 'danger')
        return redirect(url_for('project.detail', project_id=project_id))

    project.soft_delete(current_user.id)
    db.session.commit()
    flash(f'已刪除專案：{project.name}', 'success')
    return redirect(url_for('project.index'))


# ---------------------------------------------------------------------------
# 里程碑
# ---------------------------------------------------------------------------

@project_bp.route('/<int:project_id>/milestones/add', methods=['POST'])
@login_required
def add_milestone(project_id):
    """新增里程碑"""
    project = Project.query.get_or_404(project_id)

    if not project.can_be_edited_by(current_user):
        flash('您沒有權限新增里程碑', 'danger')
        return redirect(url_for('project.detail', project_id=project_id))

    name     = request.form.get('milestone_name', '').strip()
    due_date = _parse_date(request.form.get('milestone_due_date'))

    if not name:
        flash('請填寫里程碑名稱', 'warning')
        return redirect(url_for('project.detail', project_id=project_id))

    db.session.add(ProjectMilestone(
        project_id = project_id,
        name       = name,
        due_date   = due_date,
    ))
    db.session.commit()
    flash(f'已新增里程碑：{name}', 'success')
    return redirect(url_for('project.detail', project_id=project_id))


@project_bp.route('/milestones/<int:milestone_id>/update', methods=['POST'])
@login_required
def update_milestone(milestone_id):
    """更新里程碑狀態"""
    milestone = ProjectMilestone.query.get_or_404(milestone_id)
    project   = milestone.project

    if not project.can_be_edited_by(current_user):
        flash('您沒有權限更新里程碑', 'danger')
        return redirect(url_for('project.detail', project_id=project.id))

    new_status = request.form.get('status')
    if new_status in ProjectMilestone.STATUS_DISPLAY:
        milestone.status = new_status
        if new_status == 'completed' and not milestone.completed_at:
            from datetime import date
            milestone.completed_at = date.today()

    db.session.commit()
    flash('里程碑狀態已更新', 'success')
    return redirect(url_for('project.detail', project_id=project.id))


@project_bp.route('/milestones/<int:milestone_id>/delete', methods=['POST'])
@login_required
def delete_milestone(milestone_id):
    """刪除里程碑"""
    milestone = ProjectMilestone.query.get_or_404(milestone_id)
    project   = milestone.project

    if not project.can_be_edited_by(current_user):
        flash('您沒有權限刪除里程碑', 'danger')
        return redirect(url_for('project.detail', project_id=project.id))

    name = milestone.name
    db.session.delete(milestone)
    db.session.commit()
    flash(f'已刪除里程碑：{name}', 'success')
    return redirect(url_for('project.detail', project_id=project.id))


# ---------------------------------------------------------------------------
# 附件
# ---------------------------------------------------------------------------

@project_bp.route('/<int:project_id>/attachments/upload', methods=['POST'])
@login_required
def upload_attachment(project_id):
    """上傳附件"""
    project = Project.query.get_or_404(project_id)

    if not project.can_upload_attachment_by(current_user):
        flash('您沒有權限上傳附件', 'danger')
        return redirect(url_for('project.detail', project_id=project_id))

    file = request.files.get('attachment')
    if not file or file.filename == '':
        flash('請選擇要上傳的檔案', 'warning')
        return redirect(url_for('project.detail', project_id=project_id))

    if not _allowed_file(file.filename):
        flash('不支援的檔案格式', 'warning')
        return redirect(url_for('project.detail', project_id=project_id))

    _ensure_upload_dir()

    ext         = file.filename.rsplit('.', 1)[1].lower()
    stored_name = f'{uuid.uuid4().hex}.{ext}'
    save_path   = os.path.join(UPLOAD_FOLDER, stored_name)
    file.save(save_path)
    file_size = os.path.getsize(save_path)

    db.session.add(ProjectAttachment(
        project_id     = project_id,
        filename       = file.filename,
        stored_name    = stored_name,
        uploaded_by_id = current_user.id,
        file_size      = file_size,
    ))
    db.session.commit()
    flash(f'已上傳附件：{file.filename}', 'success')
    return redirect(url_for('project.detail', project_id=project_id))


@project_bp.route('/attachments/<int:attachment_id>/download')
@login_required
def download_attachment(attachment_id):
    """下載附件"""
    attachment = ProjectAttachment.query.get_or_404(attachment_id)
    project    = attachment.project

    if not project.can_be_viewed_by(current_user):
        abort(403)

    return send_from_directory(
        UPLOAD_FOLDER,
        attachment.stored_name,
        as_attachment=True,
        download_name=attachment.filename,
    )


@project_bp.route('/attachments/<int:attachment_id>/delete', methods=['POST'])
@login_required
def delete_attachment(attachment_id):
    """刪除附件"""
    attachment = ProjectAttachment.query.get_or_404(attachment_id)
    project    = attachment.project

    if not project.can_be_edited_by(current_user):
        flash('您沒有權限刪除附件', 'danger')
        return redirect(url_for('project.detail', project_id=project.id))

    file_path = os.path.join(UPLOAD_FOLDER, attachment.stored_name)
    if os.path.exists(file_path):
        os.remove(file_path)

    filename = attachment.filename
    db.session.delete(attachment)
    db.session.commit()
    flash(f'已刪除附件：{filename}', 'success')
    return redirect(url_for('project.detail', project_id=project.id))
