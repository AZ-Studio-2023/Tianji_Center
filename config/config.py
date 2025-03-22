import os
from dotenv import load_dotenv
from urllib.parse import quote_plus

load_dotenv()

class Config:
    # Flask配置
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY')

    # MySQL配置
    MYSQL_HOST = os.getenv('MYSQL_HOST')
    MYSQL_USER = os.getenv('MYSQL_USER')
    MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', '')
    MYSQL_DB = os.getenv('MYSQL_DB')

    # SQLAlchemy配置
    SQLALCHEMY_DATABASE_URI = f'mysql+pymysql://{MYSQL_USER}:{quote_plus(MYSQL_PASSWORD)}@{MYSQL_HOST}/{MYSQL_DB}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Redis配置
    REDIS_HOST = os.getenv('REDIS_HOST')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    REDIS_DB = int(os.getenv('REDIS_DB', 0))

    # 邮件配置
    MAIL_SERVER = os.getenv('MAIL_SERVER')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USERNAME = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')

    # OAuth配置
    QQ_APP_ID = os.getenv('QQ_APP_ID')
    QQ_APP_KEY = os.getenv('QQ_APP_KEY')

    WECHAT_APP_ID = os.getenv('WECHAT_APP_ID')
    WECHAT_APP_KEY = os.getenv('WECHAT_APP_KEY')

    GITHUB_CLIENT_ID = os.getenv('GITHUB_CLIENT_ID')
    GITHUB_CLIENT_SECRET = os.getenv('GITHUB_CLIENT_SECRET')

    MICROSOFT_CLIENT_ID = os.getenv('MICROSOFT_CLIENT_ID')
    MICROSOFT_CLIENT_SECRET = os.getenv('MICROSOFT_CLIENT_SECRET')

    # Cloudflare配置
    ENABLE_GEETEST = os.getenv('ENABLE_GEETEST', 'True').lower() == 'true'
    GEETEST_ID = os.getenv('GEETEST_ID')
    GEETEST_SECRET_KEY = os.getenv('GEETEST_SECRET_KEY')

    # OAuth配置
    QQ_CLIENT_ID = os.getenv('QQ_CLIENT_ID')
    QQ_CLIENT_SECRET = os.getenv('QQ_CLIENT_SECRET')

    WECHAT_CLIENT_ID = os.getenv('WECHAT_CLIENT_ID')
    WECHAT_CLIENT_SECRET = os.getenv('WECHAT_CLIENT_SECRET')

    GITHUB_CLIENT_ID = os.getenv('GITHUB_CLIENT_ID')
    GITHUB_CLIENT_SECRET = os.getenv('GITHUB_CLIENT_SECRET')

    MICROSOFT_CLIENT_ID = os.getenv('MICROSOFT_CLIENT_ID')
    MICROSOFT_CLIENT_SECRET = os.getenv('MICROSOFT_CLIENT_SECRET')

    # 时区配置
    TIMEZONE = 'Asia/Shanghai'  # 设置为中国时区
    BABEL_DEFAULT_TIMEZONE = 'Asia/Shanghai'

    # 审核API配置
    KEY = os.getenv('KEY')

    # MCRCON配置
    MCRCON_HOST = os.getenv('MCRCON_HOST')
    MCRCON_PASSWORD = os.getenv('MCRCON_PASSWORD')
    MCRCON_PORT = int(os.getenv('MCRCON_PORT'))

    # 资源包配置
    RESOURCE_PACKS = eval(os.getenv('RESOURCE_PACKS', '[]'))

    # 结构文件配置
    STRUCTURE_STORAGE_PATH = os.getenv('STRUCTURE_STORAGE_PATH')  # 结构存储目录
    GAME_ROOT_PATH = os.getenv('GAME_ROOT_PATH')  # 游戏根目录

    # 论坛配置
    DISCOUESE_API_KEY = os.getenv('DISCOUESE_API_KEY') # API密钥
    DISCOUESE_SSO_KEY = os.getenv('DISCOUESE_SSO_KEY') # Discourse Connect

    # 开放性试题审核配置
    AI_KEY = os.getenv("AI_KEY") # AI密钥