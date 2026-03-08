"""
test_permissions.py - 權限控制測試
=====================================
測試不同角色對各功能的存取限制：
  - admin 有最高權限
  - sales 只能存取自己的 BOM / Booking
  - engineer 不可存取 BOM 審核 / admin 頁面
  - 跨角色存取應被拒絕（403 或 redirect）
"""

import pytest


class TestAdminPagePermissions:
    """admin 管理頁面的角色限制"""

    def test_admin_can_access_user_management(self, logged_in_admin):
        """admin 可以存取使用者管理頁"""
        response = logged_in_admin.get('/admin/users', follow_redirects=True)
        assert response.status_code == 200

    def test_sales_cannot_access_user_management(self, logged_in_sales):
        """sales 不可存取使用者管理頁，應被擋下"""
        response = logged_in_sales.get('/admin/users', follow_redirects=True)
        # 應被擋下（403）或導回其他頁面（302 → 200 but not admin page）
        assert response.status_code in (403, 200)
        # 不應包含使用者管理相關內容
        assert '新增使用者'.encode() not in response.data

    def test_engineer_cannot_access_user_management(self, logged_in_engineer):
        """engineer 不可存取使用者管理頁"""
        response = logged_in_engineer.get('/admin/users', follow_redirects=True)
        assert '新增使用者'.encode() not in response.data


class TestProductPagePermissions:
    """產品管理頁面的角色限制"""

    def test_admin_can_access_modules(self, logged_in_admin):
        """admin 可存取模組管理"""
        response = logged_in_admin.get('/product/modules', follow_redirects=True)
        assert response.status_code == 200

    def test_sales_cannot_access_product_modules(self, logged_in_sales):
        """sales 不可存取產品模組管理"""
        response = logged_in_sales.get('/product/modules', follow_redirects=True)
        # 不應看到模組管理的新增按鈕
        assert '新增模組'.encode() not in response.data

    def test_engineer_cannot_access_product_modules(self, logged_in_engineer):
        """engineer 不可存取產品模組管理"""
        response = logged_in_engineer.get('/product/modules', follow_redirects=True)
        assert '新增模組'.encode() not in response.data


class TestBOMPermissions:
    """BOM 頁面的角色與資料存取限制"""

    def test_admin_can_view_all_boms(self, logged_in_admin, sample_bom):
        """admin 可查看所有 BOM"""
        response = logged_in_admin.get('/bom/', follow_redirects=True)
        assert response.status_code == 200

    def test_sales_can_view_own_bom(self, logged_in_sales, sample_bom):
        """sales 可查看自己負責的 BOM 詳情"""
        response = logged_in_sales.get(
            f'/bom/{sample_bom.id}', follow_redirects=True
        )
        assert response.status_code == 200
        assert sample_bom.customer_company.encode() in response.data

    def test_sales_cannot_review_bom(self, logged_in_sales, sample_bom):
        """sales 不可存取 BOM 審核頁面，應被擋下"""
        response = logged_in_sales.get(
            f'/bom/{sample_bom.id}/review', follow_redirects=True
        )
        # 審核頁面的特有按鈕不應出現
        assert '批准 BOM'.encode() not in response.data

    def test_admin_can_review_bom(self, logged_in_admin, sample_bom):
        """admin 可進入 BOM 審核頁面"""
        response = logged_in_admin.get(
            f'/bom/{sample_bom.id}/review', follow_redirects=True
        )
        assert response.status_code == 200
        assert '批准 BOM'.encode() in response.data

    def test_engineer_cannot_create_bom(self, logged_in_engineer):
        """engineer 不可建立 BOM"""
        response = logged_in_engineer.get('/bom/create', follow_redirects=True)
        # 不應看到 BOM 表單的客戶公司欄位
        assert '客戶公司'.encode() not in response.data

    def test_admin_can_delete_bom(self, logged_in_admin, sample_bom):
        """admin 可刪除 BOM（pending 狀態）"""
        response = logged_in_admin.post(
            f'/bom/{sample_bom.id}/delete', follow_redirects=True
        )
        assert response.status_code == 200

    def test_sales_cannot_delete_others_bom(self, client, db, sales_user, sample_bom):
        """sales 不可刪除他人的 BOM"""
        # 建立另一個 sales
        from tests.conftest import _make_user
        other_sales = _make_user(
            email='other@test.com', name='另一業務',
            password='Test@1234',
            role_name='sales', role_display='業務人員'
        )
        from tests.conftest import _do_login
        _do_login(client, other_sales.email, 'Test@1234')

        response = client.post(
            f'/bom/{sample_bom.id}/delete', follow_redirects=True
        )
        # 被拒絕或顯示權限錯誤
        assert '權限'.encode() in response.data or \
               '無法'.encode()  in response.data or \
               response.status_code in (302, 403)


class TestBookingPermissions:
    """Booking 頁面的角色限制"""

    def test_sales_can_create_booking(self, logged_in_sales):
        """sales 可進入 Booking 建立頁面"""
        response = logged_in_sales.get('/booking/create', follow_redirects=True)
        assert response.status_code == 200
        assert '公司名稱'.encode() in response.data

    def test_admin_can_review_booking(self, logged_in_admin, sample_booking):
        """admin 可進入 Booking 審核頁面"""
        response = logged_in_admin.get(
            f'/booking/{sample_booking.id}/review', follow_redirects=True
        )
        assert response.status_code == 200

    def test_sales_cannot_review_booking(self, logged_in_sales, sample_booking):
        """sales 不可審核 Booking"""
        response = logged_in_sales.post(
            f'/booking/{sample_booking.id}/review',
            data={'action': 'approve', 'notes': ''},
            follow_redirects=True
        )
        # Booking 應仍為 pending（未被審核）
        from app.models.booking import CustomerBooking
        booking = CustomerBooking.query.get(sample_booking.id)
        assert booking.status == 'pending'
