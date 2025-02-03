from extensions import db
from datetime import datetime
import pytz

def get_default_time():
    return datetime.now(pytz.timezone('Asia/Shanghai'))

class StructureSlot(db.Model):
    __tablename__ = 'structure_slots'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    size = db.Column(db.Integer, nullable=False)  # 槽大小,单位KB
    remaining_clears = db.Column(db.Integer, default=5)  # 剩余清空次数
    current_structure = db.Column(db.String(255))  # 当前存储的结构文件名
    created_at = db.Column(db.DateTime, default=get_default_time)

class StructureShare(db.Model):
    __tablename__ = 'structure_shares'
    
    id = db.Column(db.Integer, primary_key=True)
    slot_id = db.Column(db.Integer, db.ForeignKey('structure_slots.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    slot = db.relationship('StructureSlot', backref='shares')
    user = db.relationship('User', backref='structure_shares')

class SlotCard(db.Model):
    __tablename__ = 'slot_cards'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False)  # 兑换码
    size = db.Column(db.Integer, nullable=False)  # 槽大小
    count = db.Column(db.Integer, nullable=False)  # 每次兑换获得的槽数量
    remaining_uses = db.Column(db.Integer, nullable=False)  # 剩余可用次数
    created_at = db.Column(db.DateTime, default=get_default_time)

class SlotCardUsage(db.Model):
    __tablename__ = 'slot_card_usages'
    
    id = db.Column(db.Integer, primary_key=True)
    card_id = db.Column(db.Integer, db.ForeignKey('slot_cards.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    used_at = db.Column(db.DateTime, default=get_default_time)
    
    # 添加唯一约束确保每个用户只能使用一次
    __table_args__ = (db.UniqueConstraint('card_id', 'user_id', name='unique_card_usage'),)