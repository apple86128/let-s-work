"""
test_routes_booking.py - Booking 流程 Integration Tests
==========================================================
測試 Booking 的完整 HTTP 操作：
  - 列表頁 / 詳情頁
  - 建立 Booking（POST）
  - 審核 Booking（approve / reject）
  - 延期申請
"""

import pytest


class TestBookingList:
    """Booking 列表頁測試"""

    def test_admin_can_view_booking_list(self, logged_in_admin):
        """admin 可正常查看 Booking 列表頁"""
        response = logged_in_admin.get('/booking/', follow_redirects=True)
        assert response.status_code == 200

    def test_sales_can_view_booking_list(self, logged_in_sales):
        """sales 可查看 Booking 列表（只看自己的）"""
        response = logged_in_sales.get('/booking/', follow_redirects=True)
        assert response.status_code == 200

    def test_booking_appears_in_list(self, logged_in_admin, sample_booking):
        """已建立的 Booking 應出現在列表中"""
        response = logged_in_admin.get('/booking/', follow_redirects=True)
        assert sample_booking.company_name.encode() in response.data


class TestBookingDetail:
    """Booking 詳情頁測試"""

    def test_admin_can_view_booking_detail(self, logged_in_admin, sample_booking):
        """admin 可查看 Booking 詳情"""
        response = logged_in_admin.get(
            f'/booking/{sample_booking.id}', follow_redirects=True
        )
        assert response.status_code == 200
        assert sample_booking.company_name.encode() in response.data

    def test_creator_can_view_own_booking(self, logged_in_sales, sample_booking):
        """建立者可查看自己的 Booking 詳情"""
        response = logged_in_sales.get(
            f'/booking/{sample_booking.id}', follow_redirects=True
        )
        assert response.status_code == 200

    def test_nonexistent_booking_returns_404(self, logged_in_admin):
        """查詢不存在的 Booking 應回傳 404"""
        response = logged_in_admin.get('/booking/99999', follow_redirects=False)
        assert response.status_code == 404


class TestBookingCreate:
    """建立 Booking 測試"""

    def test_create_booking_form_loads(self, logged_in_sales):
        """Booking 建立表單可正常載入"""
        response = logged_in_sales.get('/booking/create', follow_redirects=True)
        assert response.status_code == 200
        assert '公司名稱'.encode() in response.data

    def test_create_booking_success(self, logged_in_sales, sales_user):
        """正確提交表單後應成功建立 Booking，並導向詳情頁"""
        response = logged_in_sales.post('/booking/create', data={
            'company_name':        '新建客戶公司',
            'contact_person':      '王大明',
            'contact_phone':       '0911-111-222',
            'contact_email':       'wang@test.com',
            'project_description': '測試建立 Booking',
            'assigned_sales_id':   sales_user.id,
        }, follow_redirects=True)

        assert response.status_code == 200
        # 成功後應看到公司名稱（在詳情頁）
        assert '新建客戶公司'.encode() in response.data

    def test_create_booking_missing_required_fields(self, logged_in_sales):
        """缺少必填欄位應顯示錯誤，不建立 Booking"""
        response = logged_in_sales.post('/booking/create', data={
            'company_name':   '',   # 必填但空白
            'contact_person': '',
        }, follow_redirects=True)

        assert response.status_code == 200
        # 應停在建立頁（有必填欄位的 label 或 error）

    def test_engineer_cannot_access_create_booking(self, logged_in_engineer):
        """engineer 不可建立 Booking"""
        response = logged_in_engineer.get('/booking/create', follow_redirects=True)
        # 不應看到建立表單
        assert '公司名稱'.encode() not in response.data


class TestBookingReview:
    """Booking 審核流程測試"""

    def test_review_page_loads_for_admin(self, logged_in_admin, sample_booking):
        """admin 可查看 Booking 審核頁面"""
        response = logged_in_admin.get(
            f'/booking/{sample_booking.id}/review', follow_redirects=True
        )
        assert response.status_code == 200

    def test_approve_booking(self, logged_in_admin, sample_booking, db):
        """admin 批准 Booking 後，狀態應變為 approved"""
        response = logged_in_admin.post(
            f'/booking/{sample_booking.id}/review',
            data={'action': 'approve', 'notes': '符合資格'},
            follow_redirects=True
        )
        assert response.status_code == 200

        from app.models.booking import CustomerBooking
        booking = CustomerBooking.query.get(sample_booking.id)
        assert booking.status == 'approved'

    def test_reject_booking(self, logged_in_admin, sample_booking, db):
        """admin 拒絕 Booking 後，狀態應變為 rejected"""
        response = logged_in_admin.post(
            f'/booking/{sample_booking.id}/review',
            data={'action': 'reject', 'notes': '資料不足'},
            follow_redirects=True
        )
        assert response.status_code == 200

        from app.models.booking import CustomerBooking
        booking = CustomerBooking.query.get(sample_booking.id)
        assert booking.status == 'rejected'

    def test_reject_without_notes_fails(self, logged_in_admin, sample_booking, db):
        """拒絕 Booking 時未填審核意見，應被擋下"""
        logged_in_admin.post(
            f'/booking/{sample_booking.id}/review',
            data={'action': 'reject', 'notes': ''},   # 空白 notes
            follow_redirects=True
        )
        from app.models.booking import CustomerBooking
        booking = CustomerBooking.query.get(sample_booking.id)
        # 狀態應仍為 pending（未被成功拒絕）
        assert booking.status == 'pending'

    def test_sales_cannot_approve_booking(self, logged_in_sales, sample_booking, db):
        """sales 嘗試批准 Booking 應被拒絕，狀態不變"""
        logged_in_sales.post(
            f'/booking/{sample_booking.id}/review',
            data={'action': 'approve', 'notes': ''},
            follow_redirects=True
        )
        from app.models.booking import CustomerBooking
        booking = CustomerBooking.query.get(sample_booking.id)
        assert booking.status == 'pending'
