from extensions import db
from datetime import datetime
import secrets
import pytz

def get_default_time():
    """获取当前的UTC+8时间"""
    return datetime.now(pytz.timezone('Asia/Shanghai'))

class OAuthApp(db.Model):
    __tablename__ = 'oauth_apps'
    
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.String(64), unique=True, nullable=False)
    client_secret = db.Column(db.String(64), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    redirect_uris = db.Column(db.Text, nullable=False)  # 以逗号分隔的白名单URL
    created_at = db.Column(db.DateTime, default=get_default_time())
    updated_at = db.Column(db.DateTime, default=get_default_time(), onupdate=get_default_time())
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    @staticmethod
    def generate_client_id():
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def generate_client_secret():
        return secrets.token_urlsafe(48)

class OAuthCode(db.Model):
    __tablename__ = 'oauth_codes'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(128), unique=True, nullable=False)
    client_id = db.Column(db.String(64), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    scope = db.Column(db.String(256))  # 授权范围
    redirect_uri = db.Column(db.String(512), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=get_default_time())
    
    @staticmethod
    def generate_code():
        return secrets.token_urlsafe(48)

class OAuthToken(db.Model):
    __tablename__ = 'oauth_tokens'
    
    id = db.Column(db.Integer, primary_key=True)
    access_token = db.Column(db.String(128), unique=True, nullable=False)
    refresh_token = db.Column(db.String(128), unique=True, nullable=False)
    client_id = db.Column(db.String(64), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    scope = db.Column(db.String(256))
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=get_default_time())
    
    @staticmethod
    def generate_token():
        return secrets.token_urlsafe(48) 