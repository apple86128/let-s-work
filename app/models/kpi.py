from datetime import datetime
from app.models import db


class AnnualKpiTarget(db.Model):
    """
    年度 KPI 目標設定
    每一年只會有一筆目標記錄（由 year 唯一約束保證）
    產品目標與人力目標分開記錄
    """

    __tablename__ = 'annual_kpi_targets'

    id             = db.Column(db.Integer, primary_key=True)
    year           = db.Column(db.Integer, nullable=False, unique=True)  # 年份，如 2025
    product_target = db.Column(db.BigInteger, default=0, nullable=False) # 產品金額目標（元）
    labor_target   = db.Column(db.BigInteger, default=0, nullable=False) # 人力金額目標（元）
    notes          = db.Column(db.Text, nullable=True)                   # 備註
    created_by_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    updated_by_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at     = db.Column(db.DateTime, default=datetime.utcnow,
                               onupdate=datetime.utcnow, nullable=False)

    created_by = db.relationship('User', foreign_keys=[created_by_id])
    updated_by = db.relationship('User', foreign_keys=[updated_by_id])

    def __init__(self, year, product_target=0, labor_target=0,
                 notes=None, created_by_id=None):
        self.year           = year
        self.product_target = product_target
        self.labor_target   = labor_target
        self.notes          = notes
        self.created_by_id  = created_by_id
        self.updated_by_id  = created_by_id

    @property
    def total_target(self):
        """產品 + 人力的合計目標"""
        return self.product_target + self.labor_target

    def update(self, product_target, labor_target, updated_by_id, notes=None):
        """更新目標值"""
        self.product_target = product_target
        self.labor_target   = labor_target
        self.updated_by_id  = updated_by_id
        if notes is not None:
            self.notes = notes

    @classmethod
    def get_or_create(cls, year, created_by_id=None):
        """取得指定年份的目標，若不存在則建立空白目標"""
        target = cls.query.filter_by(year=year).first()
        if not target:
            target = cls(year=year, created_by_id=created_by_id)
            db.session.add(target)
            db.session.flush()
        return target

    def __repr__(self):
        return f'<AnnualKpiTarget {self.year} product={self.product_target} labor={self.labor_target}>'


# ---------------------------------------------------------------------------
# KPI 統計查詢工具函數
# ---------------------------------------------------------------------------

def get_kpi_statistics(year):
    """
    計算指定年度的 KPI 統計數據
    資料鏈：Project → BOM（bom_id）→ final_price / final_maintenance_price
    季度依據：BOM.reviewed_at（批准日期）

    回傳結構：
    {
        'planning': {件數, 產品金額, 人力金額},
        'billed':   {
            'total': {件數, 產品金額, 人力金額},
            'q1'~'q4': {件數, 產品金額, 人力金額}
        },
        'lost':     {件數, 產品金額, 人力金額},
    }
    """
    from app.models.project import Project
    from app.models.bom     import BOM

    # 計畫中狀態
    PLANNING_STATUSES = ('waiting',)
    # 已入帳狀態
    BILLED_STATUSES   = ('building', 'maintaining', 'ended')
    # 終結狀態
    LOST_STATUSES     = ('lost',)

    # 季度起迄月份對照
    QUARTERS = {
        'q1': (1,  3),
        'q2': (4,  6),
        'q3': (7,  9),
        'q4': (10, 12),
    }

    def _empty_bucket():
        return {'count': 0, 'product_amount': 0, 'labor_amount': 0}

    def _sum_projects(projects):
        """加總一批 Project 的金額"""
        result = _empty_bucket()
        for proj in projects:
            bom = BOM.query.filter_by(
                id=proj.bom_id, is_deleted=False
            ).first() if proj.bom_id else None

            result['count'] += 1
            result['product_amount'] += (bom.final_price             or 0) if bom else 0
            result['labor_amount']   += (bom.final_maintenance_price or 0) if bom else 0
        return result

    def _get_projects_by_status(statuses):
        """依狀態取得未刪除的專案列表"""
        return Project.query.filter(
            Project.status.in_(statuses),
            Project.is_deleted == False,
        ).all()

    def _filter_by_quarter(projects, q_start_month, q_end_month):
        """
        從 projects 清單中篩出 BOM 批准日期落在指定季度的項目
        只計算已入帳狀態（有 bom_id 且 BOM 已批准）
        """
        result = []
        for proj in projects:
            if not proj.bom_id:
                continue
            bom = BOM.query.filter_by(id=proj.bom_id, is_deleted=False).first()
            if not bom or not bom.reviewed_at:
                continue
            if bom.reviewed_at.year != year:
                continue
            if q_start_month <= bom.reviewed_at.month <= q_end_month:
                result.append(proj)
        return result

    # --- 計算各分類 ---

    planning_projects = _get_projects_by_status(PLANNING_STATUSES)
    billed_projects   = _get_projects_by_status(BILLED_STATUSES)
    lost_projects     = _get_projects_by_status(LOST_STATUSES)

    # 已入帳：先篩出年度內有 BOM 批准日期的專案
    billed_in_year = [
        p for p in billed_projects
        if p.bom_id and _has_bom_reviewed_in_year(p.bom_id, year)
    ]

    # 各季分組
    billed_quarters = {}
    for q_key, (start_m, end_m) in QUARTERS.items():
        q_projects = _filter_by_quarter(billed_projects, start_m, end_m)
        billed_quarters[q_key] = _sum_projects(q_projects)

    return {
        'planning': _sum_projects(planning_projects),
        'billed': {
            'total': _sum_projects(billed_in_year),
            **billed_quarters,
        },
        'lost': _sum_projects(lost_projects),
    }


def _has_bom_reviewed_in_year(bom_id, year):
    """確認此 BOM 的批准日期是否在指定年度內"""
    from app.models.bom import BOM
    bom = BOM.query.filter_by(id=bom_id, is_deleted=False).first()
    if not bom or not bom.reviewed_at:
        return False
    return bom.reviewed_at.year == year
