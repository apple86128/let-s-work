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

    資料來源：BOM.project_status（取代原本的 Project.status）
    季度歸屬依據：BOM.won_at（狀態變更為 won 時自動記錄）
    金額來源：BOM.final_price（產品）/ BOM.final_maintenance_price（人力）

    狀態對應：
      規劃中 → project_status in ('none', 'poc', 'bidding')
      已入帳 → project_status = 'won'，且 won_at 落在指定年度
      已流失 → project_status = 'closed'

    回傳結構：
    {
        'planning': {count, product_amount, labor_amount},
        'billed':   {
            'total': {count, product_amount, labor_amount},
            'q1'~'q4': {count, product_amount, labor_amount}
        },
        'lost':     {count, product_amount, labor_amount},
    }
    """
    from app.models.bom import BOM

    PLANNING_STATUSES = ('none', 'poc', 'bidding')
    BILLED_STATUS     = 'won'
    LOST_STATUS       = 'closed'

    QUARTERS = {
        'q1': (1,  3),
        'q2': (4,  6),
        'q3': (7,  9),
        'q4': (10, 12),
    }

    def _empty_bucket():
        return {'count': 0, 'product_amount': 0, 'labor_amount': 0}

    def _sum_boms(boms):
        """加總一批 BOM 的件數與金額"""
        result = _empty_bucket()
        for bom in boms:
            result['count']          += 1
            result['product_amount'] += bom.final_price             or 0
            result['labor_amount']   += bom.final_maintenance_price or 0
        return result

    def _get_boms_by_status(statuses):
        """依 project_status 取得未刪除的 BOM 列表"""
        return BOM.query.filter(
            BOM.project_status.in_(statuses),
            BOM.is_deleted == False,
        ).all()

    def _get_won_boms_in_year():
        """取得 won_at 落在指定年度的已成案 BOM"""
        return BOM.query.filter(
            BOM.project_status == BILLED_STATUS,
            BOM.won_at.isnot(None),
            db.func.strftime('%Y', BOM.won_at) == str(year),
            BOM.is_deleted == False,
        ).all()

    def _filter_by_quarter(boms, q_start_month, q_end_month):
        """篩出 won_at 落在指定季度的 BOM"""
        result = []
        for bom in boms:
            if not bom.won_at or bom.won_at.year != year:
                continue
            if q_start_month <= bom.won_at.month <= q_end_month:
                result.append(bom)
        return result

    # --- 計算各分類 ---

    planning_boms = _get_boms_by_status(PLANNING_STATUSES)
    won_boms      = _get_won_boms_in_year()          # 已入帳：won_at 在本年度
    lost_boms     = _get_boms_by_status([LOST_STATUS])

    # Q1~Q4 季度分組（依 won_at）
    billed_quarters = {
        q_key: _sum_boms(_filter_by_quarter(won_boms, start_m, end_m))
        for q_key, (start_m, end_m) in QUARTERS.items()
    }

    return {
        'planning': _sum_boms(planning_boms),
        'billed': {
            'total': _sum_boms(won_boms),
            **billed_quarters,
        },
        'lost': _sum_boms(lost_boms),
    }
