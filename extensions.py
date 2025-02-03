from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
from flask_login import LoginManager
from redis import Redis

db = SQLAlchemy()
mail = Mail()
login_manager = LoginManager()

# 创建 Redis 客户端实例
redis = Redis(
    host='localhost',  # 将从配置中获取
    port=6379,
    db=0,
    decode_responses=True  # 自动将字节解码为字符串
) 