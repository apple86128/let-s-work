"""
根目錄 conftest.py
==================
讓 pytest 能正確找到 app 模組。
此檔案必須放在專案根目錄（與 app.py、pytest.ini 同層）。

原理：pytest 啟動時會自動載入找到的所有 conftest.py，
根目錄的 conftest.py 最先被載入，此時將專案根目錄加入
sys.path，之後 tests/conftest.py 的 `from app import ...`
才能正確解析。
"""

import sys
import os

# 將專案根目錄加入 Python 路徑
# os.path.abspath(__file__) → 此 conftest.py 的絕對路徑
# os.path.dirname(...)      → 取得所在目錄（即專案根目錄）
project_root = os.path.dirname(os.path.abspath(__file__))

if project_root not in sys.path:
    sys.path.insert(0, project_root)
