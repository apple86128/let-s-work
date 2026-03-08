# 綜合業務管理系統
> Business Management System

一套基於 Flask 的企業內部業務管理平台，支援客戶預約、BOM 報價、產品管理與多角色權限控制。

---

## 📋 目錄

- [技術架構](#技術架構)
- [專案結構](#專案結構)
- [功能模組](#功能模組)
- [角色與權限](#角色與權限)
- [本地安裝與啟動](#本地安裝與啟動)
- [預設帳號](#預設帳號)
- [開發規範](#開發規範)

---

## 技術架構

| 層級 | 技術 |
|------|------|
| Web Framework | Flask 2.3.3 |
| ORM | Flask-SQLAlchemy 3.0.5 |
| 認證 | Flask-Login 0.6.3 |
| 表單驗證 | Flask-WTF 1.1.1 |
| 資料庫 | SQLite（開發）|
| 前端樣式 | Bootstrap 5 |
| 圖示 | Font Awesome |
| 架構模式 | MVC + Blueprint |

### 架構設計原則

- **MVC 分層**：Model（資料）/ Blueprint Route（控制）/ Template（視圖）明確分離
- **Blueprint 模組化**：每個功能域獨立 Blueprint，方便維護與擴展
- **Permission-based 權限控制**：透過 `utils/permissions.py` 統一管理，支援角色預設與個人客製化覆寫

---

## 專案結構

```
project/
├── app.py                        # 應用程式入口點
├── config.py                     # 環境配置（development / production）
├── requirements.txt              # Python 套件清單
├── .gitignore
├── README.md
│
└── app/
    ├── __init__.py               # create_app() 工廠函數
    │
    ├── models/                   # M - 資料模型層
    │   ├── __init__.py
    │   ├── user.py               # 使用者、角色、Session
    │   ├── booking.py            # 客戶預約、延期申請
    │   ├── product.py            # 產品模組、功能、定價
    │   ├── bom.py                # BOM 報價單
    │   └── permission.py        # 自訂權限
    │
    ├── blueprints/               # C - 控制器層
    │   ├── auth/                 # 認證（登入/登出）
    │   ├── dashboard/            # 儀表板
    │   ├── admin/                # 使用者與系統管理
    │   ├── booking/              # 客戶預約管理
    │   ├── product/              # 產品模組管理
    │   └── bom/                  # BOM 報價系統
    │
    ├── templates/                # V - 視圖層
    │   ├── base.html             # 共用基礎模板
    │   ├── auth/
    │   ├── admin/
    │   ├── booking/
    │   ├── product/
    │   └── bom/
    │
    ├── static/
    │   ├── css/
    │   └── js/
    │
    └── utils/
        ├── permissions.py        # 權限檢查工具函數
        └── helpers.py            # 通用輔助函數
```

---

## 功能模組

### 🔐 認證模組（Auth）
- 系統內部帳號登入 / 登出
- Sales 外部入口（獨立登入頁）
- Session 管理

### 📊 儀表板（Dashboard）
- 依角色顯示不同資訊摘要
- 待辦事項、最新記錄快速入口

### ⚙️ 系統管理（Admin）
- 使用者帳號建立 / 編輯 / 停用
- 角色指派
- 個人客製化權限覆寫

### 📅 客戶預約（Booking）
- 新增 / 編輯客戶預約記錄
- 延期申請與審核
- 業務人員只能查看自己的記錄

### 📦 產品管理（Product）
- 產品模組 CRUD
- 模組功能 CRUD
- 定價方案管理
- Sales Kit 文件輸出（點數報價）

### 📝 BOM 報價系統（BOM）
- 從 Booking 建立 / 直接建立 BOM
- 功能需求勾選
- 審查 / 批准 / 退回流程
- BOM 明細輸出

---

## 角色與權限

系統共有 **5 種角色**，以 Permission-based 方式控制功能存取。

| 角色 | 名稱 | 主要職責 |
|------|------|---------|
| `admin` | 管理層 | 全系統最高權限，使用者管理、所有記錄查看 |
| `pm` | 產品經理 | BOM 審查與批核、報價管理、產品模組維護 |
| `project_manager` | 專案管理員 | 專案指派、工單派工管理 |
| `engineer` | 工程師 | 工單執行、產品報告建立 |
| `sales` | 業務人員 | 客戶 Booking 建立、BOM 提交、Sales Kit 查看 |

### 權限控制說明

- **角色預設權限**：定義於 `utils/permissions.py` 的 `permission_mapping`
- **個人客製化**：Admin 可針對特定使用者追加或拒絕某項權限（覆寫角色預設）
- **模板層**：Jinja2 中可使用 `has_permission(user, 'permission_name')` 控制 UI 顯示

---

## 本地安裝與啟動

### 1. Clone 專案

```bash
git clone https://github.com/your-username/business-management.git
cd business-management
```

### 2. 建立虛擬環境

```bash
python -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. 安裝相依套件

```bash
pip install -r requirements.txt
```

### 4. 建立環境變數

複製範本並填入設定：

```bash
cp .env.example .env
```

`.env` 內容範例：

```env
FLASK_ENV=development
SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///business_management.db
```

### 5. 初始化資料庫

```bash
flask db-init
# 或直接啟動，首次啟動會自動建立資料庫與預設帳號
```

### 6. 啟動開發伺服器

```bash
flask run
# 或
python app.py
```

瀏覽器開啟：[http://localhost:5000](http://localhost:5000)

---

## 預設帳號

> ⚠️ 正式環境部署前請務必修改所有預設密碼

| 角色 | Email | 密碼 |
|------|-------|------|
| 管理層 | admin@company.com | admin123 |
| 產品經理 | pm@company.com | pm123 |
| 專案管理員 | project@company.com | project123 |
| 工程師 | engineer@company.com | engineer123 |

業務人員帳號請由管理員於系統內建立。

---

## 開發規範

### Branch 策略

```
main          # 穩定版本，對應正式環境
develop       # 開發整合分支
feature/xxx   # 功能開發分支
fix/xxx       # Bug 修復分支
```

### Commit 訊息格式

```
feat: 新增 BOM 審查流程
fix: 修正 Booking 日期驗證錯誤
refactor: 整理 permission utils 結構
docs: 更新 README 安裝說明
```

### 程式碼規範

- 避免巢狀 `if` 結構，善用 early return
- 路由函數保持簡潔，業務邏輯移至 model 或 utils
- 所有 HTML 模板放置於對應 Blueprint 子目錄下
- 中文註解說明業務邏輯，英文命名變數與函數

---

## 版本記錄

| 版本 | 說明 |
|------|------|
| v1.0.0 | 初始版本，完成核心 MVC 架構重建 |

---

> 本專案持續開發中，功能會隨業務需求逐步迭代。
