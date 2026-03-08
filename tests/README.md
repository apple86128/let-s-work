# 自動化測試說明

## 目錄結構

```
tests/
├── conftest.py              # 共用 Fixtures（app、db、使用者、測試資料）
├── test_auth.py             # 登入 / 登出 / 認證流程
├── test_permissions.py      # 角色權限存取控制
├── test_models_bom.py       # BOM Model 單元測試
├── test_routes_booking.py   # Booking 流程整合測試
└── test_routes_bom.py       # BOM 建立 / 審核整合測試
```

---

## 安裝依賴

```powershell
pip install pytest pytest-flask
```

---

## 執行測試

```powershell
# 在專案根目錄（含 app.py 的那層）執行

# 執行全部測試
pytest

# 指定單一測試檔
pytest tests/test_auth.py

# 指定單一測試 class
pytest tests/test_permissions.py::TestSalesPermissions

# 指定單一測試 function
pytest tests/test_auth.py::TestLoginSuccess::test_admin_login_redirects_to_dashboard

# 顯示詳細輸出（已在 pytest.ini 預設開啟 -v）
pytest -v

# 遇到第一個失敗立即停止
pytest -x

# 顯示 print 輸出（除錯用）
pytest -s
```

---

## 測試設計原則

| 項目 | 說明 |
|------|------|
| 資料庫 | 每個 test 使用記憶體 SQLite，結束後 rollback |
| CSRF  | TestingConfig 已停用，不需送 token |
| 隔離  | 每個 test function 獨立，不互相污染 |
| Fixtures | conftest.py 提供共用 user / client / 資料 |

---

## Fixtures 速查

| Fixture | 說明 |
|---------|------|
| `client` | 未登入的 test client |
| `admin_client` | 已登入 admin 的 test client |
| `pm_client` | 已登入 pm 的 test client |
| `sales_client` | 已登入 sales 的 test client |
| `engineer_client` | 已登入 engineer 的 test client |
| `admin_user` | admin User 物件 |
| `sales_user` | sales User 物件 |
| `sample_booking` | pending 狀態的 CustomerBooking |
| `approved_booking` | approved 狀態的 CustomerBooking |
| `sample_module` | 測試用產品模組 |
| `sample_function` | 測試用產品功能（10 pts/台） |
| `sample_bom` | pending 狀態的 BOM（含 1 個 BOMItem）|

---

## 測試涵蓋範圍

### test_auth.py
- ✅ GET 登入頁面
- ✅ 正確帳密登入
- ✅ 錯誤密碼
- ✅ 不存在帳號
- ✅ 停用帳號
- ✅ 空白欄位
- ✅ 登出後 session 清除
- ✅ 未登入存取受保護路由（參數化測試）

### test_permissions.py
- ✅ admin 可存取全部管理功能
- ✅ sales 無法存取 admin 功能
- ✅ engineer 無法建立 Booking
- ✅ 只有 admin/pm 可存取 BOM 審核頁面
- ✅ 其他 sales 無法編輯別人的 BOM

### test_models_bom.py
- ✅ bom_number 自動產生
- ✅ 預設狀態為 pending
- ✅ total_points 正確計算
- ✅ can_be_viewed/edited/reviewed_by() 邏輯
- ✅ approve / reject / reset_to_pending 狀態流轉
- ✅ 折扣率計算

### test_routes_booking.py
- ✅ 列表存取
- ✅ 建立成功 / 失敗
- ✅ 詳情查看 / 404
- ✅ 批准 / 拒絕（含意見必填驗證）
- ✅ 延期申請

### test_routes_bom.py
- ✅ 列表存取
- ✅ 來源選擇頁
- ✅ 建立成功 / 失敗（缺欄位 / 缺功能）
- ✅ 詳情 / 404
- ✅ 審核批准 / 拒絕（含驗證）
- ✅ 僅更新價格
- ✅ 軟刪除
- ✅ 報價 API（結構 + 點數計算 + 未登入保護）
