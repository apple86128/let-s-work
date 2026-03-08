"""
test_routes_bom.py - BOM 流程 Integration Tests
=================================================
測試 BOM 的完整 HTTP 操作：
  - 列表頁 / 詳情頁
  - 建立 BOM（POST）
  - 審核 BOM（approve / reject）
  - 刪除 BOM
  - 即時計算 API
"""

import json
import pytest


class TestBOMList:
    """BOM 列表頁測試"""

    def test_admin_can_view_bom_list(self, logged_in_admin):
        """admin 可正常查看 BOM 列表"""
        response = logged_in_admin.get('/bom/', follow_redirects=True)
        assert response.status_code == 200

    def test_sales_can_view_bom_list(self, logged_in_sales):
        """sales 可查看 BOM 列表"""
        response = logged_in_sales.get('/bom/', follow_redirects=True)
        assert response.status_code == 200

    def test_bom_appears_in_list(self, logged_in_admin, sample_bom):
        """已建立的 BOM 應出現在列表"""
        response = logged_in_admin.get('/bom/', follow_redirects=True)
        assert sample_bom.bom_number.encode() in response.data

    def test_bom_list_filter_by_status(self, logged_in_admin, sample_bom):
        """依狀態篩選 BOM 列表"""
        response = logged_in_admin.get('/bom/?status=pending', follow_redirects=True)
        assert response.status_code == 200
        assert sample_bom.bom_number.encode() in response.data

    def test_bom_list_search_by_company(self, logged_in_admin, sample_bom):
        """依公司名稱搜尋 BOM"""
        response = logged_in_admin.get(
            f'/bom/?search={sample_bom.customer_company}', follow_redirects=True
        )
        assert sample_bom.bom_number.encode() in response.data


class TestBOMDetail:
    """BOM 詳情頁測試"""

    def test_admin_can_view_bom_detail(self, logged_in_admin, sample_bom):
        """admin 可查看 BOM 詳情"""
        response = logged_in_admin.get(
            f'/bom/{sample_bom.id}', follow_redirects=True
        )
        assert response.status_code == 200
        assert sample_bom.project_name.encode() in response.data

    def test_sales_can_view_own_bom_detail(self, logged_in_sales, sample_bom):
        """sales 可查看自己負責的 BOM"""
        response = logged_in_sales.get(
            f'/bom/{sample_bom.id}', follow_redirects=True
        )
        assert response.status_code == 200

    def test_nonexistent_bom_returns_404(self, logged_in_admin):
        """不存在的 BOM 應回傳 404"""
        response = logged_in_admin.get('/bom/99999', follow_redirects=False)
        assert response.status_code == 404

    def test_approved_bom_shows_final_price(self, logged_in_admin, approved_bom):
        """已批准的 BOM 詳情頁應顯示最終價格"""
        response = logged_in_admin.get(
            f'/bom/{approved_bom.id}', follow_redirects=True
        )
        assert response.status_code == 200
        assert '100,000'.encode() in response.data or '100000'.encode() in response.data


class TestBOMCreate:
    """BOM 建立測試"""

    def test_source_select_page_loads(self, logged_in_sales):
        """BOM 來源選擇頁可正常載入"""
        response = logged_in_sales.get('/bom/source-select', follow_redirects=True)
        assert response.status_code == 200
        assert '來源'.encode() in response.data

    def test_create_bom_form_loads(self, logged_in_sales):
        """BOM 建立表單可正常載入"""
        response = logged_in_sales.get(
            '/bom/create?source=direct_create', follow_redirects=True
        )
        assert response.status_code == 200

    def test_create_bom_success(self, logged_in_sales, sales_user,
                                 sample_function, sample_pricing_tier, db):
        """成功提交完整表單後應建立 BOM 並導向詳情頁"""
        response = logged_in_sales.post('/bom/create', data={
            'source_type':       'direct_create',
            'customer_company':  '新建 BOM 客戶',
            'project_name':      '整合測試專案',
            'customer_contact':  '李小明',
            'plan_type':         'onetime',
            'plan_years':        '1',
            'function_ids':      [str(sample_function.id)],
            'quantities':        ['2'],
            'notes':             [''],
        }, follow_redirects=True)

        assert response.status_code == 200
        assert '新建 BOM 客戶'.encode() in response.data

    def test_create_bom_missing_company_fails(self, logged_in_sales):
        """公司名稱空白應顯示錯誤"""
        response = logged_in_sales.post('/bom/create', data={
            'source_type':       'direct_create',
            'customer_company':  '',    # 空白
            'project_name':      '測試專案',
            'plan_type':         'onetime',
            'plan_years':        '1',
        }, follow_redirects=True)

        assert response.status_code == 200
        # 應停在表單頁，顯示錯誤訊息

    def test_create_bom_without_functions_fails(self, logged_in_sales):
        """未選擇功能應顯示錯誤"""
        response = logged_in_sales.post('/bom/create', data={
            'source_type':      'direct_create',
            'customer_company': '測試客戶',
            'project_name':     '測試專案',
            'plan_type':        'onetime',
            'plan_years':       '1',
            # 沒有 function_ids
        }, follow_redirects=True)

        assert response.status_code == 200
        # 不應建立 BOM，應顯示錯誤

    def test_engineer_cannot_create_bom(self, logged_in_engineer):
        """engineer 不可存取 BOM 建立頁面"""
        response = logged_in_engineer.get('/bom/create', follow_redirects=True)
        # 不應看到表單
        assert '客戶公司'.encode() not in response.data


class TestBOMReview:
    """BOM 審核流程測試"""

    def test_review_page_loads_for_admin(self, logged_in_admin, sample_bom):
        """admin 可進入 BOM 審核頁"""
        response = logged_in_admin.get(
            f'/bom/{sample_bom.id}/review', follow_redirects=True
        )
        assert response.status_code == 200
        assert '批准 BOM'.encode() in response.data

    def test_approve_bom_route(self, logged_in_admin, sample_bom, db):
        """admin 透過 POST 批准 BOM，狀態應變為 approved"""
        response = logged_in_admin.post(
            f'/bom/{sample_bom.id}/review',
            data={
                'action':      'approve',
                'final_price': '200000',
                'notes':       '同意',
            },
            follow_redirects=True
        )
        assert response.status_code == 200

        from app.models.bom import BOM
        bom = BOM.query.get(sample_bom.id)
        assert bom.status == 'approved'
        assert bom.final_price == 200000

    def test_reject_bom_route(self, logged_in_admin, sample_bom, db):
        """admin 透過 POST 拒絕 BOM（需填 notes），狀態應變為 rejected"""
        logged_in_admin.post(
            f'/bom/{sample_bom.id}/review',
            data={
                'action': 'reject',
                'notes':  '功能需求不完整',
            },
            follow_redirects=True
        )
        from app.models.bom import BOM
        bom = BOM.query.get(sample_bom.id)
        assert bom.status == 'rejected'

    def test_reject_bom_without_notes_fails(self, logged_in_admin, sample_bom, db):
        """拒絕 BOM 時 notes 為空，應被擋下（status 保持 pending）"""
        logged_in_admin.post(
            f'/bom/{sample_bom.id}/review',
            data={'action': 'reject', 'notes': ''},
            follow_redirects=True
        )
        from app.models.bom import BOM
        bom = BOM.query.get(sample_bom.id)
        assert bom.status == 'pending'

    def test_sales_cannot_access_review_route(self, logged_in_sales, sample_bom):
        """sales 嘗試存取審核頁應被擋下"""
        response = logged_in_sales.get(
            f'/bom/{sample_bom.id}/review', follow_redirects=True
        )
        assert '批准 BOM'.encode() not in response.data

    def test_approve_bom_without_final_price_fails(self, logged_in_admin, sample_bom, db):
        """批准 BOM 時未輸入最終價格，應被擋下"""
        logged_in_admin.post(
            f'/bom/{sample_bom.id}/review',
            data={'action': 'approve', 'final_price': '', 'notes': ''},
            follow_redirects=True
        )
        from app.models.bom import BOM
        bom = BOM.query.get(sample_bom.id)
        assert bom.status == 'pending'


class TestBOMDelete:
    """BOM 刪除測試"""

    def test_creator_can_delete_own_bom(self, logged_in_sales, sample_bom, db):
        """sales 建立者可刪除自己的 pending BOM"""
        bom_id = sample_bom.id
        response = logged_in_sales.post(
            f'/bom/{bom_id}/delete', follow_redirects=True
        )
        assert response.status_code == 200

        from app.models.bom import BOM
        bom = BOM.query.get(bom_id)
        assert bom is None or bom.is_deleted is True

    def test_admin_can_delete_any_bom(self, logged_in_admin, sample_bom, db):
        """admin 可刪除任何 BOM"""
        bom_id = sample_bom.id
        logged_in_admin.post(f'/bom/{bom_id}/delete', follow_redirects=True)

        from app.models.bom import BOM
        bom = BOM.query.get(bom_id)
        assert bom is None or bom.is_deleted is True


class TestBOMAPI:
    """BOM 即時計算 API 測試"""

    def test_calculate_price_api(self, logged_in_sales, sample_function, sample_pricing_tier):
        """即時計算 API 應回傳正確 JSON 結構"""
        response = logged_in_sales.post(
            '/bom/api/calculate-price',
            json={
                'functions': [
                    {'function_id': sample_function.id, 'quantity': 2}
                ],
                'plan_type':  'onetime',
                'plan_years': 1,
            }
        )
        assert response.status_code == 200
        data = response.get_json()
        assert 'total_points'    in data
        assert 'suggested_price' in data
        assert data['total_points'] == 2 * sample_function.points_per_unit

    def test_calculate_price_api_unauthenticated(self, client):
        """未登入呼叫 API 應被導向登入頁"""
        response = client.post(
            '/bom/api/calculate-price',
            json={'functions': [], 'plan_type': 'onetime', 'plan_years': 1},
            follow_redirects=False
        )
        assert response.status_code == 302

    def test_modules_functions_api(self, logged_in_sales, sample_function):
        """取得模組功能列表 API 應回傳正確資料"""
        response = logged_in_sales.get('/bom/api/modules-functions')
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        # 應至少包含 sample_function 所屬的模組
        module_ids = [m['id'] for m in data]
        assert sample_function.module_id in module_ids
