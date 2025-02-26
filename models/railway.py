from extensions import db
from datetime import datetime

class TrainNumber(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    prefix = db.Column(db.String(1), nullable=False)  # G/C/D/T/K/Z
    number = db.Column(db.String(4), nullable=False)  # 1-9999
    bureau = db.Column(db.String(50), nullable=False)  # xx铁路局
    start_station = db.Column(db.String(100), nullable=False)
    start_station_data = db.Column(db.JSON)  # 存储颜色、收费区、坐标等信息
    end_station = db.Column(db.String(100), nullable=False)
    end_station_data = db.Column(db.JSON)  # 存储颜色、收费区、坐标等信息
    is_return = db.Column(db.Boolean, default=False)  # 是否为折返线路
    return_to = db.Column(db.String(10))  # 关联的去程/折返车次号
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    @property
    def train_number(self):
        return f"{self.prefix}{self.number}"
        
    def get_station_name_parts(self, station_name):
        """分离站点的中英文名称"""
        if ' | ' in station_name:
            return station_name.split(' | ')
        return station_name, None

class TrainReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    train_number = db.Column(db.String(10), nullable=False)
    reporter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)
    processor_id = db.Column(db.Integer, db.ForeignKey('user.id')) 