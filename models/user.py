from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db
from flask_login import UserMixin
from datetime import datetime
from flask import current_app
import pytz, json, requests, uuid, mcrcon

headers = {
    'User-Agent': 'tjb'
}

def get_default_time():
    """获取当前的UTC+8时间"""
    return datetime.now(pytz.timezone('Asia/Shanghai'))

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(512))
    role = db.Column(db.String(20), default='visitor')  # visitor, player, creator, admin
    coins = db.Column(db.Integer, default=0)
    
    # OAuth相关字段
    qq_id = db.Column(db.String(50), unique=True)
    qq_avatar = db.Column(db.String(200))  # QQ头像URL
    wechat_id = db.Column(db.String(50), unique=True)
    github_id = db.Column(db.String(50), unique=True)
    microsoft_id = db.Column(db.String(50), unique=True)
    
    # 头像类型：gravatar, qq
    avatar_type = db.Column(db.String(20), default='gravatar')
    
    # 关联
    applications = db.relationship('Application', backref='user', lazy=True)
    coin_records = db.relationship('CoinRecord', backref='user', lazy=True)
    checkins = db.relationship('CheckIn', backref='user', lazy=True)
    
    # 添加绑定奖励记录
    qq_reward = db.Column(db.Boolean, default=False)
    wechat_reward = db.Column(db.Boolean, default=False)
    github_reward = db.Column(db.Boolean, default=False)
    microsoft_reward = db.Column(db.Boolean, default=False)
    
    # QQ验证相关字段
    verified_qq = db.Column(db.String(20))  # 验证的QQ号
    qq_verified_at = db.Column(db.DateTime)  # QQ验证时间
    
    @property
    def role_name(self):
        roles = {
            'visitor': '游客',
            'player': '玩家',
            'creator': '创造者',
            'admin': '管理员'
        }
        return roles.get(self.role, '未知')
        
    @property
    def is_admin(self):
        return self.role == 'admin'
        
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
        
    def get_gravatar_url(self):
        import hashlib
        email_hash = hashlib.md5(self.email.lower().encode()).hexdigest()
        return f"https://www.gravatar.com/avatar/{email_hash}?d=identicon"
        
    @property
    def avatar_url(self):
        if self.avatar_type == 'qq' and self.qq_avatar:
            return self.qq_avatar
        else:
            return self.get_gravatar_url()

class Application(db.Model):
    __tablename__ = 'applications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    form_type = db.Column(db.String(50), nullable=False)  # 申请表单类型
    content = db.Column(db.JSON, nullable=False)  # 表单内容
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    remark = db.Column(db.Text)  # 审核备注
    created_at = db.Column(db.DateTime, default=get_default_time)
    updated_at = db.Column(db.DateTime, onupdate=get_default_time)

class CoinRecord(db.Model):
    __tablename__ = 'coin_records'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Integer, nullable=False)  # 正数表示增加，负数表示减少
    reason = db.Column(db.String(100), nullable=False)  # 变动原因
    created_at = db.Column(db.DateTime, default=get_default_time)

class CheckIn(db.Model):
    __tablename__ = 'checkins'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    coins = db.Column(db.Integer, nullable=False)  # 获得的天际币数量
    created_at = db.Column(db.DateTime, default=get_default_time)

class Activity(db.Model):
    __tablename__ = 'activities'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # lucky_red_packet, fixed_red_packet, lottery
    config = db.Column(db.JSON, nullable=False)  # 活动配置
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='active')  # active, ended
    created_at = db.Column(db.DateTime, default=get_default_time)
    
    participants = db.relationship('ActivityParticipant', backref='activity', lazy=True)
    
    def get_participant(self, user_id):
        """获取用户的参与记录"""
        return ActivityParticipant.query.filter_by(
            activity_id=self.id,
            user_id=user_id
        ).first()

class ActivityParticipant(db.Model):
    __tablename__ = 'activity_participants'
    
    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activities.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reward = db.Column(db.JSON)  # 获得的奖励
    created_at = db.Column(db.DateTime, default=get_default_time)

class Vote(db.Model):
    __tablename__ = 'votes'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='active')  # active, ended
    created_at = db.Column(db.DateTime, default=get_default_time)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # 添加创建者ID
    
    # 修改关系定义
    creator = db.relationship('User', backref='created_votes', foreign_keys=[user_id])
    vote_records = db.relationship('VoteRecord', backref='vote', lazy=True)
    
    @property
    def total_votes(self):
        return len(self.vote_records)
        
    @property
    def agree_votes(self):
        """获取同意票数"""
        return VoteRecord.query.filter_by(vote_id=self.id, agree=True).count()
        
    @property
    def disagree_votes(self):
        """获取反对票数"""
        return VoteRecord.query.filter_by(vote_id=self.id, agree=False).count()

class VoteRecord(db.Model):
    __tablename__ = 'vote_records'
    
    id = db.Column(db.Integer, primary_key=True)
    vote_id = db.Column(db.Integer, db.ForeignKey('votes.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    agree = db.Column(db.Boolean, nullable=False)
    created_at = db.Column(db.DateTime, default=get_default_time)
    
    # 添加关系定义
    voter = db.relationship('User', backref='vote_records') 

def add_whiteList(username, player_uuid, host, password, port):
    rcon = mcrcon.MCRcon(host, password, port)
    rcon.connect()
    response = rcon.command(f'whitelist add {username}')
    f = open("C:\\Users\\Administrator\\Desktop\\tjmtr\\whitelist.json", "r")
    d = json.loads(f.read())
    f.close()
    for item in d:
        if item["name"].lower() == username.lower():
            if item["uuid"] != player_uuid:
                item["uuid"] = player_uuid
                f = open("C:\\Users\\Administrator\\Desktop\\tjmtr\\whitelist.json", "w")
                f.write(json.dumps(d, indent=4))
                f.close()
                response_r = rcon.command(f'whitelist reload')
            rcon.disconnect()
            return

def is_valid_uuid(uuid_string):
    try:
        val = uuid.UUID(uuid_string)
    except ValueError:
        return False
    return str(val) == uuid_string
def check_username_exists(username):
    url = f"https://forum.tjmtr.world/u/{username}/summary"
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 404:
            return False
        else:
            return True
    except requests.RequestException as e:
        print(f"请求出错: {e}")
        return False
    
def auto_review_player_application(application, host, password, port):
    """
    自动审核玩家权限申请
    返回 (是否通过, 备注)
    """
    data = application.content
    # 检查必填字段
    required_fields = ['player_name', 'uuid', 'play_time', 'online_duration']
    if not all(field in data for field in required_fields):
        return False, "申请表信息不完整"
    
    if check_username_exists(data["forum_email"]) and data["permission"] != "创造者权限（OP2）":
        if is_valid_uuid(data["uuid"]):
            if data["play_time"] == "不足一个月":
                if data["permission"] != "仅旁观" or data["permission"] != "仅生存":
                    return False, "游玩MTR模组时间过短，申请权限过高"
                else: 
                    add_whiteList(data["player_name"], data["uuid"], host, password, port)
                    return True, "请查看群公告有关模式修改的说明"
            if data["permission"] != "创造者权限（OP2)":
                add_whiteList(data["player_name"], data["uuid"], host, password, port)
                return True, "请查看群公告有关模式修改的说明"
        else:
            return False, "UUID格式不正确"
    elif data["permission"] == "创造者权限（OP2）":
        if is_valid_uuid(data["uuid"]):
            if data["play_time"] == "大约三个月" or data["play_time"] == "不足一个月":
                return False, "游玩MTR模组时间过短，申请权限过高"
            else:
                return None, "请将您的建筑图片发送给管理员手动审核"
        else:
            return False, "UUID格式不正确"
    else:
        return False, "论坛用户名不存在或已被占用"

def schedule_auto_review(host, password, port):
    """定时自动审核任务"""
    from extensions import db
    
    # 获取所有待审核的玩家权限申请
    pending_apps = Application.query.filter_by(
        form_type='player',
        status='pending'
    ).all()
    
    for app in pending_apps:
        passed, notes = auto_review_player_application(app, host, password, port)
        if passed == None:
            app.status = 'pending'
        elif passed == False:
            app.status = 'rejected'
        else:
            app.status = 'approved'
        app.remark = notes
        app.reviewed_at = datetime.now(pytz.timezone('Asia/Shanghai'))
        app.reviewer_id = None  # 自动审核
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"自动审核出错: {str(e)}") 