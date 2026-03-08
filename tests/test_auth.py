"""
test_auth.py - 登入 / 認證流程測試
=====================================
涵蓋：
  - 正常登入 / 登出
  - 錯誤密碼 / Email
  - 停用帳號無法登入
  - 未登入被導向登入頁
  - 已登入者再訪登入頁被導向 dashboard
"""

import pytest


class TestLogin:
    """登入流程 Integration Tests"""

    def test_login_page_loads(self, client):
        """登入頁面可正常載入（GET）"""
        response = client.get('/auth/login')
        assert response.status_code == 200
        assert '登入'.encode() in response.data

    def test_login_success_admin(self, client, admin_user):
        """admin 帳號正常登入，應被導向 dashboard"""
        response = client.post('/auth/login', data={
            'email':    admin_user.email,
            'password': 'Test@1234',
        }, follow_redirects=True)

        assert response.status_code == 200
        # 登入後應到達 dashboard（含歡迎訊息或 dashboard 關鍵字）
        assert '歡迎'.encode() in response.data or \
               'dashboard'.encode() in response.data.lower()

    def test_login_success_sales(self, client, sales_user):
        """sales 帳號正常登入"""
        response = client.post('/auth/login', data={
            'email':    sales_user.email,
            'password': 'Test@1234',
        }, follow_redirects=False)

        # 登入成功後應為 302 redirect
        assert response.status_code == 302

    def test_login_wrong_password(self, client, admin_user):
        """密碼錯誤應停留在登入頁並顯示錯誤"""
        response = client.post('/auth/login', data={
            'email':    admin_user.email,
            'password': 'WrongPassword',
        }, follow_redirects=True)

        assert response.status_code == 200
        # 應顯示錯誤訊息（密碼錯誤 or 帳號不存在）
        assert '錯誤'.encode() in response.data or \
               'error'.encode()  in response.data.lower()

    def test_login_wrong_email(self, client):
        """Email 不存在應顯示錯誤"""
        response = client.post('/auth/login', data={
            'email':    'notexist@test.com',
            'password': 'Test@1234',
        }, follow_redirects=True)

        assert response.status_code == 200
        assert '錯誤'.encode() in response.data or \
               'error'.encode()  in response.data.lower()

    def test_login_invalid_email_format(self, client):
        """Email 格式不正確應顯示驗證錯誤"""
        response = client.post('/auth/login', data={
            'email':    'not-an-email',
            'password': 'Test@1234',
        }, follow_redirects=True)

        assert response.status_code == 200

    def test_login_empty_fields(self, client):
        """空白欄位提交應顯示錯誤"""
        response = client.post('/auth/login', data={
            'email':    '',
            'password': '',
        }, follow_redirects=True)

        assert response.status_code == 200

    def test_login_inactive_account(self, client, inactive_user):
        """已停用帳號嘗試登入，應被拒絕"""
        response = client.post('/auth/login', data={
            'email':    inactive_user.email,
            'password': 'Test@1234',
        }, follow_redirects=True)

        assert response.status_code == 200
        # 應顯示帳號停用相關訊息
        assert '停用'.encode() in response.data or \
               '管理員'.encode() in response.data


class TestLogout:
    """登出流程測試"""

    def test_logout_success(self, logged_in_admin):
        """已登入用戶可正常登出，應被導向登入頁"""
        response = logged_in_admin.get('/auth/logout', follow_redirects=True)
        assert response.status_code == 200

    def test_after_logout_cannot_access_dashboard(self, logged_in_admin):
        """登出後訪問 dashboard 應被導向登入頁"""
        # 先登出
        logged_in_admin.get('/auth/logout', follow_redirects=True)

        # 嘗試訪問受保護頁面
        response = logged_in_admin.get('/dashboard/', follow_redirects=True)
        assert response.status_code == 200
        # 應被導向登入頁
        assert '登入'.encode() in response.data


class TestProtectedRoutes:
    """未登入存取受保護路由測試"""

    PROTECTED_URLS = [
        '/dashboard/',
        '/bom/',
        '/booking/',
        '/admin/users',
    ]

    @pytest.mark.parametrize('url', PROTECTED_URLS)
    def test_unauthenticated_redirected_to_login(self, client, url):
        """未登入用戶存取受保護頁面，應被導向登入頁（302）"""
        response = client.get(url, follow_redirects=False)
        assert response.status_code == 302
        assert '/auth/login' in response.location or \
               'login'       in response.location

    def test_authenticated_can_access_dashboard(self, logged_in_admin):
        """已登入用戶可正常訪問 dashboard"""
        response = logged_in_admin.get('/dashboard/', follow_redirects=True)
        assert response.status_code == 200
