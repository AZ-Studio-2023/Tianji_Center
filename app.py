from flask import Flask, redirect, url_for
from config.config import Config
from extensions import db, mail, login_manager, redis
from models.user import User
from models.oauth import OAuthApp, OAuthCode, OAuthToken
import pymysql
from flask_migrate import Migrate
from flask_login import current_user
from datetime import datetime
import pytz
from flask_babel import Babel
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from models.user import schedule_auto_review

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # 初始化扩展
    db.init_app(app)
    mail.init_app(app)
    login_manager.init_app(app)
    migrate = Migrate(app, db)
    babel = Babel(app)
    
    # 配置 Redis
    redis.connection_pool.connection_kwargs.update({
        'host': app.config['REDIS_HOST'],
        'port': app.config['REDIS_PORT'],
        'db': app.config['REDIS_DB']
    })
    
    # 配置 login_manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = '请先登录'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    with app.app_context():
        db.create_all()

    # 注册蓝图
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.oauth import oauth_bp
    from routes.structure import structure_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
    app.register_blueprint(oauth_bp, url_prefix='/oauth')
    app.register_blueprint(structure_bp, url_prefix='/structure')

    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard.index'))
        return redirect(url_for('auth.login'))

    # 设置默认时区
    @app.template_filter('datetime')
    def format_datetime(value, format='%Y-%m-%d %H:%M'):
        if value is None:
            return ''
        # 确保时间有时区信息
        if value.tzinfo is None:
            value = pytz.timezone(app.config['TIMEZONE']).localize(value)
        return value.strftime(format)

    # 添加模板全局函数
    @app.context_processor
    def utility_processor():
        from models.user import Application
        def has_creative_permission():
            approved_applications = Application.query.filter_by(
                user_id=current_user.id,
                status='approved'
            ).all()
            
            for app in approved_applications:
                if app.content.get('permission') in ['仅创造', '创造者权限（OP2）']:
                    return True
            return False
        
        return {
            'has_creative_permission': has_creative_permission
        }

    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True) 