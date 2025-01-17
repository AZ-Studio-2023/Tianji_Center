from flask import current_app
import redis
import random

def get_redis_client():
    """获取Redis客户端实例"""
    return redis.Redis(
        host=current_app.config['REDIS_HOST'],
        port=current_app.config['REDIS_PORT'],
        db=current_app.config['REDIS_DB']
    )

def generate_email_code():
    """生成6位数字验证码"""
    return ''.join(random.choices('0123456789', k=6))

def save_email_code(email, code):
    """保存邮箱验证码"""
    key = f'email_code:{email}'
    redis_client = get_redis_client()
    redis_client.setex(key, 300, code)  # 5分钟有效期

def verify_email_code(email, code):
    """验证邮箱验证码"""
    key = f'email_code:{email}'
    redis_client = get_redis_client()
    saved_code = redis_client.get(key)
    if not saved_code:
        return False
    return saved_code.decode() == code 