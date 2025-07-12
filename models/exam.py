from extensions import db
from flask_login import UserMixin
from datetime import datetime

class Exam(db.Model):
    __tablename__ = 'exams'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text)
    duration = db.Column(db.Integer)  # 单位：分钟
    auto_submit_limit = db.Column(db.Integer, default=0)  # 切屏次数限制
    must_exam = db.Column(db.Boolean, default=False)  # 是否为必考试卷
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    instant_score = db.Column(db.Boolean, default=True)  # 是否即时显示分数
    hidden = db.Column(db.Boolean, default=False)
    pinned = db.Column(db.Boolean, default=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    graders = db.relationship('User', secondary='exam_graders', backref='grading_exams')

class ExamGrader(db.Model):
    __tablename__ = 'exam_graders'
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)

class ExamQuestion(db.Model):
    __tablename__ = 'exam_questions'
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'))
    type = db.Column(db.String(16))  # single, multiple, blank
    content = db.Column(db.Text)
    options = db.Column(db.Text)  # JSON字符串，选择题选项
    answer = db.Column(db.Text)   # JSON字符串，标准答案
    blank_length = db.Column(db.Integer)  # 填空框长度
    score = db.Column(db.Integer, default=1)

class ExamPaper(db.Model):
    __tablename__ = 'exam_papers'
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    answers = db.Column(db.Text)  # JSON字符串，用户答案
    score = db.Column(db.Integer)
    graded = db.Column(db.Boolean, default=False)
    grader_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

# 你可以根据需要扩展模型字段
