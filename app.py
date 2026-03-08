from app import create_app

# 建立應用程式實例，預設使用開發環境
# 正式部署時可改為 'production'
app = create_app('development')

if __name__ == '__main__':
    app.run(
        host='0.0.0.0',  # 允許區域網路存取，方便多裝置測試
        port=5000,
        debug=app.config['DEBUG']
    )
