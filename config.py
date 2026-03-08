import os
from dotenv import load_dotenv

# 載入 .env 環境變數檔案
load_dotenv()

# 專案根目錄絕對路徑
BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class BaseConfig:
    """基礎配置 - 所有環境共用的設定"""

    # --- 系統資訊 ---
    SYSTEM_NAME = '綜合業務管理系統'
    COMPANY_NAME = os.getenv('COMPANY_NAME', 'Your Company')

    # --- 安全性 ---
    # 正式環境請務必透過環境變數覆寫此值
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-fallback-secret-key-change-in-production')

    # --- SQLAlchemy 共用設定 ---
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Session 設定 ---
    SESSION_COOKIE_HTTPONLY = True    # 防止 JavaScript 存取 Cookie
    SESSION_COOKIE_SAMESITE = 'Lax'  # 防止 CSRF 跨站請求


class DevelopmentConfig(BaseConfig):
    """開發環境配置"""

    DEBUG = True
    TESTING = False

    # SQLite 資料庫，存放於專案根目錄
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        'sqlite:///' + os.path.join(BASE_DIR, 'business_management.db')
    )

    # 開發環境顯示 SQL 查詢語句，方便除錯
    SQLALCHEMY_ECHO = False


class TestingConfig(BaseConfig):
    """測試環境配置"""

    DEBUG = True
    TESTING = True

    # 測試使用獨立的記憶體資料庫，不影響開發資料
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

    # 測試時關閉 CSRF 驗證
    WTF_CSRF_ENABLED = False


class ProductionConfig(BaseConfig):
    """正式環境配置"""

    DEBUG = False
    TESTING = False

    # 正式環境資料庫 URI 必須由環境變數提供
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')

    # 正式環境強制使用 HTTPS Cookie
    SESSION_COOKIE_SECURE = True


# 環境配置對應表，供 create_app() 使用字串選擇
config_map = {
    'development': DevelopmentConfig,
    'testing':     TestingConfig,
    'production':  ProductionConfig,
    'default':     DevelopmentConfig,
}
