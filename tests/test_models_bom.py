"""
test_models_bom.py - BOM Model Unit Tests
==========================================
測試 BOM model 的各種方法邏輯（不透過 HTTP）：
  - 狀態流轉（pending → approved / rejected）
  - 點數計算
  - 權限方法（can_be_edited_by / can_be_reviewed_by）
  - 軟刪除
"""

import pytest
from app.models.bom import BOM, BOMItem


class TestBOMStatus:
    """BOM 狀態流轉測試"""

    def test_new_bom_is_pending(self, sample_bom):
        """新建立的 BOM 預設為 pending"""
        assert sample_bom.status == 'pending'

    def test_approve_bom(self, sample_bom, admin_user):
        """admin 批准 BOM 後狀態應變為 approved"""
        sample_bom.approve(
            reviewer_id = admin_user.id,
            notes       = '通過審核',
            final_price = 150000,
        )
        assert sample_bom.status == 'approved'
        assert sample_bom.final_price == 150000
        assert sample_bom.reviewed_by_id == admin_user.id

    def test_reject_bom(self, sample_bom, admin_user):
        """admin 拒絕 BOM 後狀態應變為 rejected"""
        sample_bom.reject(
            reviewer_id = admin_user.id,
            notes       = '資料不完整',
        )
        assert sample_bom.status == 'rejected'
        assert sample_bom.review_notes == '資料不完整'

    def test_reset_approved_bom_to_pending(self, approved_bom):
        """編輯已批准的 BOM 後，應重置為 pending"""
        approved_bom.reset_to_pending(reason='編輯內容變更', user_id=1)
        assert approved_bom.status == 'pending'
        assert approved_bom.final_price is None

    def test_get_status_display(self, sample_bom):
        """get_status_display 應回傳中文狀態名稱"""
        sample_bom.status = 'pending'
        assert sample_bom.get_status_display() == '待審核'

        sample_bom.status = 'approved'
        assert sample_bom.get_status_display() == '已批准'

        sample_bom.status = 'rejected'
        assert sample_bom.get_status_display() == '已拒絕'

    def test_get_status_color(self, sample_bom):
        """get_status_color 應回傳對應 Bootstrap 顏色字串"""
        sample_bom.status = 'pending'
        assert sample_bom.get_status_color() == 'warning'

        sample_bom.status = 'approved'
        assert sample_bom.get_status_color() == 'success'

        sample_bom.status = 'rejected'
        assert sample_bom.get_status_color() == 'danger'


class TestBOMPoints:
    """BOM 點數計算測試"""

    def test_total_points_calculated(self, sample_bom, sample_function):
        """BOM 總點數 = Σ (quantity × points_per_unit)"""
        expected = 3 * sample_function.points_per_unit  # quantity=3, points=10 → 30
        assert sample_bom.total_points == expected

    def test_bom_item_total_points(self, sample_bom):
        """BOMItem.total_points 屬性應正確計算"""
        item = sample_bom.items[0]
        assert item.total_points == item.quantity * item.unit_points

    def test_suggested_price_calculated(self, sample_bom, sample_pricing_tier):
        """suggested_price 在 calculate_suggested_price 後應大於 0"""
        sample_bom.calculate_suggested_price()
        assert sample_bom.suggested_price is not None
        assert sample_bom.suggested_price > 0


class TestBOMEditPermissions:
    """BOM 編輯權限方法測試"""

    def test_creator_can_edit_pending_bom(self, sample_bom, sales_user):
        """BOM 建立者可編輯 pending 狀態的 BOM"""
        assert sample_bom.can_be_edited_by(sales_user) is True

    def test_creator_cannot_edit_approved_bom(self, approved_bom, sales_user):
        """BOM 建立者不可編輯已批准的 BOM"""
        assert approved_bom.can_be_edited_by(sales_user) is False

    def test_admin_can_edit_any_bom(self, sample_bom, admin_user):
        """admin 可編輯任何狀態的 BOM"""
        assert sample_bom.can_be_edited_by(admin_user) is True


class TestBOMReviewPermissions:
    """BOM 審核權限方法測試"""

    def test_admin_can_review_pending_bom(self, sample_bom, admin_user):
        """admin 可審核 pending 狀態的 BOM"""
        assert sample_bom.can_be_reviewed_by(admin_user) is True

    def test_sales_cannot_review_bom(self, sample_bom, sales_user):
        """sales 不可審核 BOM"""
        assert sample_bom.can_be_reviewed_by(sales_user) is False

    def test_engineer_cannot_review_bom(self, sample_bom, engineer_user):
        """engineer 不可審核 BOM"""
        assert sample_bom.can_be_reviewed_by(engineer_user) is False


class TestBOMDeletePermissions:
    """BOM 刪除權限方法測試"""

    def test_creator_can_delete_pending_bom(self, sample_bom, sales_user):
        """BOM 建立者可刪除 pending 狀態的 BOM"""
        assert sample_bom.can_be_deleted_by(sales_user) is True

    def test_non_creator_cannot_delete_bom(self, sample_bom, engineer_user):
        """非建立者（engineer）不可刪除 BOM"""
        assert sample_bom.can_be_deleted_by(engineer_user) is False

    def test_other_sales_cannot_view_bom(self, sample_bom, db):
        """其他業務人員不可查看非自己負責的 BOM"""
        from tests.conftest import _make_user
        other = _make_user(
            email='other2@test.com', name='其他業務',
            password='Test@1234',
            role_name='sales', role_display='業務人員'
        )
        assert sample_bom.can_be_viewed_by(other) is False


class TestBOMSoftDelete:
    """BOM 軟刪除測試"""

    def test_soft_delete_sets_flag(self, sample_bom, sales_user):
        """軟刪除後 is_deleted 應為 True"""
        sample_bom.soft_delete(sales_user.id)
        assert sample_bom.is_deleted is True

    def test_soft_deleted_bom_excluded_from_query(self, db, sample_bom, sales_user):
        """軟刪除後的 BOM 不應出現在正常查詢結果"""
        from app.models.bom import get_boms_for_user
        bom_id = sample_bom.id
        sample_bom.soft_delete(sales_user.id)
        db.session.flush()

        ids = [b.id for b in get_boms_for_user(sales_user).all()]
        assert bom_id not in ids


class TestBOMCrossCreate:
    """BOM 跨角色建立標記測試"""

    def test_is_cross_created_when_different_users(self, sample_bom, admin_user):
        """建立者與負責業務不同時，is_cross_created 為 True"""
        sample_bom.created_by_id     = admin_user.id
        sample_bom.assigned_sales_id = admin_user.id + 999  # 故意不同
        assert sample_bom.is_cross_created() is True

    def test_is_not_cross_created_when_same_user(self, sample_bom, sales_user):
        """建立者與負責業務相同時，is_cross_created 為 False"""
        sample_bom.created_by_id     = sales_user.id
        sample_bom.assigned_sales_id = sales_user.id
        assert sample_bom.is_cross_created() is False
