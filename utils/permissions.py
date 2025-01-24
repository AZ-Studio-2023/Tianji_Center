from models.user import Application
from flask_sqlalchemy import SQLAlchemy

def check_creative_permission(user):
    """检查用户是否有创造权限"""
    approved_applications = Application.query.filter_by(
        user_id=user.id,
        status='approved'
    ).all()
    
    for app in approved_applications:
        if app.content.get('permission') in ['仅创造', '创造者权限（OP2）']:
            return True
    return False 