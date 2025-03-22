from flask import Blueprint, render_template, jsonify, request, current_app, flash, url_for, redirect
from flask_login import login_required, current_user
from models.user import (
    User, Application, CoinRecord, CheckIn,
    Activity, ActivityParticipant, Vote, VoteRecord
)
from models.railway import TrainNumber, TrainReport
from utils.oauth import qq_oauth, wechat_oauth, github_oauth, microsoft_oauth
from utils.email import verify_email_code, get_redis_client
from extensions import db
from datetime import datetime, timedelta, timezone
import random
from utils.email import verify_email_code
import json
import pytz
import random
import string
from models.oauth import OAuthApp
from models.user import auto_review_player_application
import hashlib
import uuid
import requests, mcrcon
from utils.geetest import verify_geetest
from sqlalchemy.orm import scoped_session, sessionmaker
from models.user import schedule_auto_review
from flask_mail import Message
from extensions import db, mail



dashboard_bp = Blueprint('dashboard', __name__)

APPLICATION_FEES = {
    'player': 1,
    'line': 166,
    'city': 666
}

# 表单类型的中文映射
FORM_TYPE_NAMES = {
    'player': '玩家权限',
    'line': '线路',
    'city': '城市'
}

# 表单字段的中文映射
FORM_FIELD_NAMES = {
    'nickname': '昵称',
    'forum_username': '论坛用户名',
    'forum_email': '论坛账号',
    'qq_number': 'QQ号',
    "open_question": "开放性问题",
    'game_account_type': '游戏账号类型',
    'player_name': '玩家名',
    'uuid': 'UUID',
    'play_time': '游玩时长',
    'online_duration': '在线时长',
    'permission': '申请权限',
    'line_name_cn': '线路名称(中文)',
    'line_name_en': '线路名称(英文)',
    'line_type': '线路类型',
    'line_color': '线路颜色',
    'line_description': '线路描述',
    'city_name_cn': '城市名称(中文)',
    'city_name_en': '城市名称(英文)',
    'district_cn': '区县名称(中文)',
    'district_en': '区县名称(英文)',
    'city_description': '城市描述',
    'up_stations': "上行站点",
    'down_stations': "下行站点",
    "formation": "编组",
    "max_speed": "最高时速",
    "plan_image": "规划图"

}

def get_current_time():
    """获取当前UTC+8时间"""
    return datetime.now(pytz.timezone('Asia/Shanghai'))

def localize_time(dt):
    """为时间添加时区信息"""
    if dt.tzinfo is None:
        return pytz.timezone(current_app.config['TIMEZONE']).localize(dt)
    return dt

def ensure_timezone(dt):
    """确保时间有时区信息"""
    if dt.tzinfo is None:
        return pytz.timezone('Asia/Shanghai').localize(dt)
    return dt

def check_creative_permission():
    """检查是否有创造权限"""
    approved_applications = Application.query.filter_by(
        user_id=current_user.id,
        status='approved'
    ).all()

    for app in approved_applications:
        if app.content.get('permission') in ['仅创造', '创造者权限（OP2）']:
            return True
    return False

@dashboard_bp.route('/')
@login_required
def index():
    # 获取申请统计
    stats = {
        'pending': Application.query.filter_by(user_id=current_user.id, status='pending').count(),
        'approved': Application.query.filter_by(user_id=current_user.id, status='approved').count(),
        'rejected': Application.query.filter_by(user_id=current_user.id, status='rejected').count()
    }

    # 检查今日是否已签到
    today = datetime.utcnow().date()
    today_checkin = CheckIn.query.filter(
        CheckIn.user_id == current_user.id,
        db.func.date(CheckIn.created_at) == today
    ).first()

    # 获取当前有效的投票
    now = get_current_time()
    current_votes = Vote.query.filter(
        db.or_(
            # 已开始且未结束的投票
            db.and_(
                Vote.start_time <= now,
                Vote.end_time > now,
                Vote.status == 'active'
            ),
            # 即将开始的投票（24小时内）
            db.and_(
                Vote.start_time > now,
                Vote.start_time <= now + timedelta(days=1),
                Vote.status == 'active'
            )
        )
    ).order_by(Vote.start_time).all()

    # 检查用户是否已对每个投票进行投票
    for vote in current_votes:
        vote.has_voted = VoteRecord.query.filter_by(
            vote_id=vote.id,
            user_id=current_user.id
        ).first() is not None
        # 添加投票状态，确保时间都有时区信息
        vote.is_active = now >= localize_time(vote.start_time) and now <= localize_time(vote.end_time)
        # 为模板中的显示转换时区
        vote.start_time = localize_time(vote.start_time)
        vote.end_time = localize_time(vote.end_time)

    return render_template('dashboard/index.html',
        stats=stats,
        today_checkin=today_checkin,
        today_checkin_coins=today_checkin.coins if today_checkin else None,
        current_votes=current_votes,
        current_time=now
    )

@dashboard_bp.route('/checkin', methods=['POST'])
@login_required
def checkin():
    # 检查是否已签到
    today = get_current_time().date()
    if CheckIn.query.filter(
        CheckIn.user_id == current_user.id,
        db.func.date(CheckIn.created_at) == today
    ).first():
        return jsonify({'error': '今日已签到'})

    # 随机获得8-15天际币
    coins = random.randint(8, 15)

    try:
        # 创建签到记录
        checkin = CheckIn(user_id=current_user.id, coins=coins)
        db.session.add(checkin)

        # 添加天际币记录
        record = CoinRecord(
            user_id=current_user.id,
            amount=coins,
            reason='每日签到'
        )
        db.session.add(record)

        # 更新用户天际币
        current_user.coins += coins

        db.session.commit()

        flash(f'签到成功，获得{coins}天际币', 'success')
        return jsonify({
            'message': '签到成功',
            'coins': coins
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': '签到失败，请重试'})

@dashboard_bp.route('/vote', methods=['POST'])
@login_required
def vote():
    vote_id = request.json.get('vote_id')
    agree = request.json.get('agree')

    vote = Vote.query.get_or_404(vote_id)

    # 检查投票是否在有效期内
    now = get_current_time()  # 使用 UTC+8 时间
    if now < localize_time(vote.start_time) or now > localize_time(vote.end_time):
        return jsonify({'error': '投票已结束或未开始'})

    # 检查是否已投票
    if VoteRecord.query.filter_by(vote_id=vote_id, user_id=current_user.id).first():
        return jsonify({'error': '已参与投票'})

    try:
        # 记录投票
        record = VoteRecord(
            vote_id=vote_id,
            user_id=current_user.id,
            agree=agree
        )
        db.session.add(record)
        db.session.commit()

        return jsonify({'message': '投票成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)})

# 申请相关路由
@dashboard_bp.route('/applications')
@login_required
def applications():
    applications = Application.query.filter_by(user_id=current_user.id)\
        .order_by(Application.created_at.desc()).all()
    for app in applications:
        app.type_name = FORM_TYPE_NAMES.get(app.form_type, app.form_type)
    return render_template('dashboard/applications.html', applications=applications)

@dashboard_bp.route('/submit-player-application', methods=['GET'])
@login_required
def submit_player_application():
    if not current_user.verified_qq:
        return render_template('dashboard/error.html',
            message='请先在个人资料中完成QQ验证',
            redirect_url=url_for('dashboard.profile'))
    if current_user.coins < APPLICATION_FEES['player']:
        return render_template('dashboard/error.html',
            message=f'天际币不足，提交玩家权限申请需要{APPLICATION_FEES["player"]}天际币',
            redirect_url=url_for('dashboard.coin_tasks'))
    return render_template('dashboard/forms/player_application.html', fee=APPLICATION_FEES['player'])

@dashboard_bp.route('/submit-line-application', methods=['GET'])
@login_required
def submit_line_application():
    if not current_user.verified_qq:
        return render_template('dashboard/error.html',
            message='请先在个人资料中完成QQ验证',
            redirect_url=url_for('dashboard.profile'))
    if not check_creative_permission():
        return render_template('dashboard/error.html',
            message='需要通过创造或创造者权限申请',
            redirect_url=url_for('dashboard.applications'))
    if current_user.coins < APPLICATION_FEES['line']:
        return render_template('dashboard/error.html',
            message=f'天际币不足，提交线路申请需要{APPLICATION_FEES["line"]}天际币',
            redirect_url=url_for('dashboard.coin_tasks'))
    return render_template('dashboard/forms/line_application.html', fee=APPLICATION_FEES['line'])

@dashboard_bp.route('/submit-city-application', methods=['GET'])
@login_required
def submit_city_application():
    if not current_user.verified_qq:
        return render_template('dashboard/error.html',
            message='请先在个人资料中完成QQ验证',
            redirect_url=url_for('dashboard.profile'))
    if not check_creative_permission():
        return render_template('dashboard/error.html',
            message='需要通过创造或创造者权限申请',
            redirect_url=url_for('dashboard.applications'))
    if current_user.coins < APPLICATION_FEES['city']:
        return render_template('dashboard/error.html',
            message=f'天际币不足，提交城市申请需要{APPLICATION_FEES["city"]}天际币',
            redirect_url=url_for('dashboard.coin_tasks'))
    return render_template('dashboard/forms/city_application.html', fee=APPLICATION_FEES['city'])

@dashboard_bp.route('/submit-application/<form_type>', methods=['POST'])
@login_required
def submit_application(form_type):
    data = request.get_json()
    # 验证人机验证
    if current_app.config['ENABLE_GEETEST'] and not verify_geetest(data):
        return jsonify({'error': '人机验证失败'})
    if not current_user.verified_qq:
        return jsonify({'error': '请先完成QQ验证'})

    if form_type not in APPLICATION_FEES:
        return jsonify({'error': '无效的申请类型'})

    if current_user.coins < APPLICATION_FEES[form_type]:
        return jsonify({'error': f'天际币不足，需要{APPLICATION_FEES[form_type]}天际币'})

    # 验证提交的QQ号是否与验证的QQ号一致
    if data.get('qq_number') != current_user.verified_qq:
        return jsonify({'error': 'QQ号与验证的QQ号不一致'})

    if form_type in ['line', 'city'] and not check_creative_permission():
        return jsonify({'error': '需要通过创造或创造者权限申请'})

    # 删除captcha数据
    if current_app.config['ENABLE_GEETEST']:
        data.pop("captcha_id")
        data.pop("captcha_output")
        data.pop("lot_number")
        data.pop("pass_token")
        data.pop("gen_time")

    try:
        # 扣除天际币
        current_user.coins -= APPLICATION_FEES[form_type]

        # 添加天际币记录，使用中文名称
        record = CoinRecord(
            user_id=current_user.id,
            amount=-APPLICATION_FEES[form_type],
            reason=f'提交{FORM_TYPE_NAMES[form_type]}申请'
        )
        db.session.add(record)
        remark = None
        if form_type == "player" and data["permission"] == "创造者权限（OP2）":
            remark = "请联系管理员手动审核"
        # 创建申请记录
        application = Application(
            user_id=current_user.id,
            form_type=form_type,
            content=data,
            remark = remark
        )
        db.session.add(application)
        db.session.commit()

        return jsonify({'message': '申请提交成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)})

# 天际币相关路由
@dashboard_bp.route('/coin-history')
@login_required
def coin_history():
    records = CoinRecord.query.filter_by(user_id=current_user.id)\
        .order_by(CoinRecord.created_at.desc()).limit(30).all()
    return render_template('dashboard/coin_history.html', records=records)

@dashboard_bp.route('/coin-tasks')
@login_required
def coin_tasks():
    tasks = [
        {
            'name': 'QQ账号绑定',
            'provider': 'qq',
            'coins': 15,
            'completed': current_user.qq_reward
        },
        {
            'name': '微信账号绑定',
            'provider': 'wechat',
            'coins': 15,
            'completed': current_user.wechat_reward
        },
        {
            'name': 'GitHub账号绑定',
            'provider': 'github',
            'coins': 15,
            'completed': current_user.github_reward
        },
        {
            'name': '微软账号绑定',
            'provider': 'microsoft',
            'coins': 15,
            'completed': current_user.microsoft_reward
        }
    ]
    return render_template('dashboard/coin_tasks.html', tasks=tasks)

# 活动相关路由
@dashboard_bp.route('/activities')
@login_required
def activities():
    now = get_current_time()
    activities = Activity.query.filter(
        Activity.end_time > now,
        Activity.status == 'active'
    ).all()

    # 确保所有活动时间都有时区信息
    for activity in activities:
        activity.start_time = ensure_timezone(activity.start_time)
        activity.end_time = ensure_timezone(activity.end_time)

    return render_template('dashboard/activities.html', activities=activities)

@dashboard_bp.route('/join-activity/<int:activity_id>', methods=['POST'])
@login_required
def join_activity(activity_id):
    try:
        activity = Activity.query.get_or_404(activity_id)
        now = get_current_time()

        # 确保活动时间有时区信息
        activity.start_time = ensure_timezone(activity.start_time)
        activity.end_time = ensure_timezone(activity.end_time)

        if now < activity.start_time:
            return jsonify({'error': '活动还未开始'})
        if now > activity.end_time or activity.status != 'active':
            return jsonify({'error': '活动已结束'})

        # 检查是否已参与
        if activity.get_participant(current_user.id):
            return jsonify({'error': '您已参与过此活动'})

        # 根据活动类型处理
        if activity.type == 'lottery':
            # 创建参与记录
            participant = ActivityParticipant(
                activity_id=activity_id,
                user_id=current_user.id
            )
            db.session.add(participant)
            db.session.flush()  # 先保存参与记录以获取ID

            # 获取奖项配置并随机抽取
            prizes = activity.config.get('prizes', [])
            total_prizes = []
            for prize in prizes:
                for _ in range(prize['count']):
                    total_prizes.append(prize)

            if total_prizes:
                # 随机抽取一个奖项
                prize = random.choice(total_prizes)
                participant.reward = prize

                # 如果是天际币奖励，立即发放
                if prize['type'] == 'coins':
                    current_user.coins += prize['amount']
                    record = CoinRecord(
                        user_id=current_user.id,
                        amount=prize['amount'],
                        reason=f'抽奖活动"{activity.title}"中奖'
                    )
                    db.session.add(record)
                    message = f'恭喜获得 {prize["amount"]} 天际币！'
                else:
                    message = f'恭喜获得 {prize["name"]}！'
            else:
                participant.reward = {'type': 'none'}
                message = '很遗憾未中奖'

        elif activity.type in ['lucky_red_packet', 'fixed_red_packet']:
            # 红包逻辑保持不变
            if len(activity.participants) >= activity.config['count']:
                return jsonify({'error': '红包已被领完'})
            amount = activity.config['amount']
            if activity.type == 'lucky_red_packet':
                # 拼手气红包逻辑
                total_coins = activity.config['total_coins']
                count = activity.config['count']
                remaining_count = count - len(activity.participants)
                if remaining_count == 1:
                    # 最后一个红包，直接给出剩余金额
                    coins = amount
                else:
                    # 随机分配金额
                    while True:
                        coins = random.randint(1, int(amount / remaining_count)*2)
                        if coins <= amount - remaining_count:
                            break
                amount -= coins
                activity.config = {
                    'amount': amount,
                    'count': count,
                    'total_coins': total_coins
                }
            else:
                # 普通红包，固定金额
                coins = activity.config['coins']

            # 创建参与记录
            participant = ActivityParticipant(
                activity_id=activity_id,
                user_id=current_user.id,
                reward={'type': 'coins', 'amount': coins}
            )
            db.session.add(participant)

            # 发放天际币
            current_user.coins += coins
            record = CoinRecord(
                user_id=current_user.id,
                amount=coins,
                reason=f'参与活动"{activity.title}"'
            )
            db.session.add(record)
            message = f'获得 {coins} 天际币'

        db.session.commit()
        return jsonify({
            'message': message,
            'reward': participant.reward
        })

    except ZeroDivisionError as e:
        db.session.rollback()
        return jsonify({'error': str(e)})

@dashboard_bp.route('/draw-activity/<int:activity_id>', methods=['POST'])
@login_required
def draw_activity(activity_id):
    if not current_user.is_admin:
        return jsonify({'error': '无权限'})

    activity = Activity.query.get_or_404(activity_id)
    if activity.type != 'metro_quiz' or activity.status != 'active':
        return jsonify({'error': '无效的操作'})

    try:
        # 更新活动状态
        activity.status = 'drawing'

        # 检查所有参与者的答案
        for participant in activity.participants:
            correct_count = 0
            answers = participant.answers or {}

            # 检查每个答案
            if activity.config['city_answer'].lower() in answers.get('city', '').lower():
                correct_count += 1
            if activity.config['line_answer'].lower() in answers.get('line', '').lower():
                correct_count += 1
            if activity.config['direction_answer'].lower() in answers.get('direction', '').lower():
                correct_count += 1
            if activity.config['station_answer'].lower() in answers.get('station', '').lower():
                correct_count += 1

            # 计算奖励
            reward_amount = correct_count * activity.config['coins_per_answer']

            # 更新参与记录
            participant.reward = {
                'amount': reward_amount,
                'correct_count': correct_count
            }

            # 发放奖励
            if reward_amount > 0:
                user = User.query.get(participant.user_id)
                user.coins += reward_amount
                record = CoinRecord(
                    user_id=user.id,
                    amount=reward_amount,
                    reason=f'地铁竞猜活动"{activity.title}"奖励'
                )
                db.session.add(record)

        db.session.commit()
        return jsonify({'message': '开奖成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'开奖出错: {str(e)}'})

# 账号设置相关路由
@dashboard_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_avatar':
            avatar_type = request.form.get('avatar_type')
            try:
                if avatar_type in ['cravatar', 'qq']:
                    # 验证是否有QQ头像
                    if avatar_type == 'qq' and not current_user.qq_avatar:
                        return jsonify({'error': '未绑定QQ账号或无QQ头像'})

                    current_user.avatar_type = avatar_type
                    db.session.commit()
                    return jsonify({'message': '头像更新成功'})
                else:
                    return jsonify({'error': '不支持的头像类型'})
            except Exception as e:
                return jsonify({'error': str(e)})

        elif action == 'update_email':
            old_code = request.form.get('old_code')
            new_email = request.form.get('new_email')
            new_code = request.form.get('new_code')

            # 验证原邮箱验证码
            if not verify_email_code(current_user.email, old_code):
                return jsonify({'error': '原邮箱验证码错误'})

            # 验证新邮箱验证码
            if not verify_email_code(new_email, new_code):
                return jsonify({'error': '新邮箱验证码错误'})

            # 检查新邮箱是否已被使用
            if User.query.filter_by(email=new_email).first():
                return jsonify({'error': '该邮箱已被使用'})

            try:
                current_user.email = new_email
                db.session.commit()
                return jsonify({'message': '邮箱更新成功'})
            except Exception as e:
                db.session.rollback()
                return jsonify({'error': str(e)})

    # 计算已绑定的第三方账号数量
    bound_accounts = sum(1 for x in [
        current_user.qq_id,
        current_user.wechat_id,
        current_user.github_id,
        current_user.microsoft_id
    ] if x is not None)

    # 获取QQ验证码信息
    redis_client = get_redis_client()
    key = f'qq_code:{current_user.id}'
    qq_code = redis_client.get(key)
    qq_code_expires_at = None

    if qq_code:
        ttl = redis_client.ttl(key)
        if ttl > 0:
            qq_code = qq_code.decode()
            qq_code_expires_at = datetime.now() + timedelta(seconds=ttl)

    return render_template('dashboard/profile.html',
        bound_accounts=bound_accounts,
        qq_code=qq_code,
        qq_code_expires_at=qq_code_expires_at
    )

@dashboard_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        email = current_user.email
        data = request.get_json()
        code = data.get('code')
        new_password = data.get('new_password')

        if not verify_email_code(email, code):
            return jsonify({'error': '验证码错误'})

        current_user.set_password(new_password)
        db.session.commit()
        return jsonify({'message': '密码修改成功'})

    return render_template('dashboard/change_password.html')

@dashboard_bp.route('/oauth-accounts')
@login_required
def oauth_accounts():
    return render_template('dashboard/oauth_accounts.html')

# 管理员路由
@dashboard_bp.route('/admin/users')
@login_required
def admin_user_management():
    if not current_user.is_admin:
        return redirect(url_for('dashboard.index'))
    users = User.query.all()
    return render_template('dashboard/admin/user_management.html', users=users)

@dashboard_bp.route('/admin/applications')
@login_required
def admin_application_review():
    if not current_user.is_admin:
        return redirect(url_for('dashboard.index'))
    applications = Application.query.all()
    for app in applications:
        app.type_name = FORM_TYPE_NAMES.get(app.form_type, app.form_type)
    return render_template('dashboard/admin/application_review.html', applications=applications)

@dashboard_bp.route('/admin/activities')
@login_required
def admin_activity_management():
    if not current_user.is_admin:
        return redirect(url_for('dashboard.index'))
    activities = Activity.query.all()
    return render_template('dashboard/admin/activity_management.html', activities=activities)

@dashboard_bp.route('/admin/votes')
@login_required
def admin_vote_management():
    if not current_user.is_admin:
        return redirect(url_for('dashboard.index'))
    votes = Vote.query.all()
    return render_template('dashboard/admin/vote_management.html', votes=votes)

@dashboard_bp.route('/update-user/<int:user_id>', methods=['POST'])
@login_required
def update_user(user_id):
    if not current_user.is_admin:
        return jsonify({'error': '无权限'}), 403

    user = User.query.get_or_404(user_id)
    action = request.form.get('action')

    if action == 'update_coins':
        amount = int(request.form.get('amount'))
        reason = request.form.get('reason')

        user.coins += amount
        record = CoinRecord(
            user_id=user.id,
            amount=amount,
            reason=reason
        )
        db.session.add(record)

    elif action == 'update_role':
        role = request.form.get('role')
        if role in ['visitor', 'player', 'creator', 'admin']:
            user.role = role

    db.session.commit()
    return jsonify({'message': '更新成功'})

@dashboard_bp.route('/create-activity', methods=['POST'])
@login_required
def create_activity():
    if not current_user.is_admin:
        return jsonify({'error': '无权限'}), 403

    try:
        title = request.form.get('title')
        type = request.form.get('type')

        # 处理时间时添加时区信息
        start_time = localize_time(datetime.strptime(request.form.get('start_time'), '%Y-%m-%dT%H:%M'))
        end_time = localize_time(datetime.strptime(request.form.get('end_time'), '%Y-%m-%dT%H:%M'))

        if start_time >= end_time:
            return jsonify({'error': '结束时间必须晚于开始时间'})

        config = {}
        if type == 'lucky_red_packet':
            config = {
                'total_coins': int(request.form.get('lucky_total_coins')),
                'count': int(request.form.get('lucky_count')),
                'amount': int(request.form.get('lucky_total_coins'))
            }
        elif type == 'fixed_red_packet':
            config = {
                'coins': int(request.form.get('fixed_coins')),
                'count': int(request.form.get('fixed_count')),
                'amount': int(request.form.get('fixed_coins')) * int(request.form.get('fixed_count'))
            }
        elif type == 'lottery':
            prizes = json.loads(request.form.get('prizes', '[]'))
            config = {
                'prizes': prizes,
                'empty_count': int(request.form.get('empty_count', 0))
            }
        elif type == 'metro_quiz':
            config = {
                'image_url': request.form.get('image_url'),
                'coins_per_answer': int(request.form.get('coins_per_answer')),
                'city_answer': request.form.get('city_answer'),
                'line_answer': request.form.get('line_answer'),
                'direction_answer': request.form.get('direction_answer'),
                'station_answer': request.form.get('station_answer')
            }

        activity = Activity(
            title=title,
            type=type,
            config=config,
            start_time=start_time,
            end_time=end_time,
            status='active'
        )
        db.session.add(activity)
        db.session.commit()

        flash('活动创建成功', 'success')
        return jsonify({'message': '活动创建成功'})

    except ValueError as e:
        return jsonify({'error': '请检查输入的数值是否正确'})
    except json.JSONDecodeError:
        return jsonify({'error': '奖品数据格式错误'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)})

@dashboard_bp.route('/create-vote', methods=['POST'])
@login_required
def create_vote():
    if not current_user.is_admin:
        return jsonify({'error': '无权限'}), 403

    title = request.form.get('title')

    # 直接使用前端传来的本地时间（UTC+8）并添加时区信息
    tz = timezone(timedelta(hours=8))
    start_time = datetime.strptime(request.form.get('start_time'), '%Y-%m-%d %H:%M').replace(tzinfo=tz)
    end_time = datetime.strptime(request.form.get('end_time'), '%Y-%m-%d %H:%M').replace(tzinfo=tz)

    # 验证时间
    if start_time >= end_time:
        return jsonify({'error': '结束时间必须晚于开始时间'})

    try:
        vote = Vote(
            title=title,
            start_time=start_time,
            end_time=end_time,
            status='active',
            user_id=current_user.id
        )
        db.session.add(vote)
        db.session.commit()
        return jsonify({'message': '投票创建成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)})

@dashboard_bp.route('/end-vote/<int:vote_id>', methods=['POST'])
@login_required
def end_vote(vote_id):
    if not current_user.is_admin:
        return jsonify({'error': '无权限'}), 403

    vote = Vote.query.get_or_404(vote_id)

    try:
        vote.status = 'ended'
        vote.end_time = get_current_time()  # 立即结束
        db.session.commit()
        return jsonify({'message': '投票已结束'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)})

@dashboard_bp.route('/get-qq-code')
@login_required
def get_qq_code():
    # 检查是否已有未过期的验证码
    redis_client = get_redis_client()
    key = f'qq_code:{current_user.id}'
    existing_code = redis_client.get(key)

    if existing_code:
        # 如果有未过期的验证码，返回相同的代码
        return jsonify({'message': '验证码已生成'})

    # 生成12位随机验证码
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
    # 设置20分钟过期
    redis_client.setex(key, 1200, code)

    return jsonify({'message': '验证码已生成'})

@dashboard_bp.route('/verify-qq', methods=['POST'])
def verify_qq():
    qq_number = request.json.get('qq')
    verify_code = request.json.get('code')
    ctrl_key = request.json.get('key')

    if not qq_number or not verify_code:
        return jsonify({'error': '参数不完整'})

    if ctrl_key != current_app.config['KEY']:
        return jsonify({'error': '密钥错误'})

    # 在 Redis 中查找所有匹配的验证码
    redis_client = get_redis_client()
    all_keys = redis_client.keys('qq_code:*')
    target_user = None

    # 遍历所有验证码，找到匹配的用户
    for key in all_keys:
        stored_code = redis_client.get(key)
        if stored_code and stored_code.decode() == verify_code:
            # 从 key 中提取用户 ID
            user_id = int(key.decode().split(':')[1])
            target_user = User.query.get(user_id)
            break

    if not target_user:
        return jsonify({'error': '验证码错误或已过期'})

    try:
        # 更新用户的 QQ 验证信息
        target_user.verified_qq = qq_number
        target_user.qq_verified_at = get_current_time()
        db.session.commit()

        # 删除验证码
        redis_client.delete(f'qq_code:{target_user.id}')

        return jsonify({
            'message': 'QQ验证成功',
            'qq_number': qq_number,
            'verified_at': target_user.qq_verified_at.strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)})

@dashboard_bp.route('/auto')
def auto_review():
    KEY = request.json.get('key')
    if KEY != current_app.config['KEY']:
        return jsonify({'error': '密钥错误'})
    schedule_auto_review(current_app.config['MCRCON_HOST'], current_app.config['MCRCON_PASSWORD'], current_app.config['MCRCON_PORT'])
    return jsonify({'code': 200, "msg": "OK"})

@dashboard_bp.route('/activity-participants/<int:activity_id>')
@login_required
def activity_participants(activity_id):
    if not current_user.is_admin:
        return jsonify({'error': '无权限查看'})

    activity = Activity.query.get_or_404(activity_id)
    participants = []

    for p in activity.participants:
        user = User.query.get(p.user_id)
        if user:
            participants.append({
                'username': user.username,
                'created_at': p.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'reward': p.reward
            })

    return jsonify({
        'participants': participants
    })

@dashboard_bp.route('/application-review')
@login_required
def application_review():
    if not current_user.is_admin:
        return render_template('dashboard/error.html',
            message='无权访问此页面',
            redirect_url=url_for('dashboard.index'))

    # 获取筛选参数
    form_type = request.args.get('type')
    status = request.args.get('status')

    # 构建查询
    query = Application.query
    if form_type:
        query = query.filter_by(form_type=form_type)
    if status:
        query = query.filter_by(status=status)

    # 获取申请列表
    applications = query.order_by(Application.created_at.desc()).all()

    # 添加中文类型名称
    for app in applications:
        app.type_name = FORM_TYPE_NAMES.get(app.form_type, app.form_type)
        app.user = User.query.get(app.user_id)

    return render_template('dashboard/admin/application_review.html', applications=applications)

@dashboard_bp.route('/application/<int:id>')
@login_required
def get_application(id):
    """获取申请详情"""
    application = Application.query.get_or_404(id)

    # 检查是否是自己的申请
    if application.user_id != current_user.id and not current_user.is_admin:
        return jsonify({'error': '无权访问'}), 403

    # 将内容的键转换为中文
    formatted_content = {}
    for key, value in application.content.items():
        formatted_content[FORM_FIELD_NAMES.get(key, key)] = value

    return jsonify({
        'id': application.id,
        'type': FORM_TYPE_NAMES.get(application.form_type, application.form_type),
        'content': formatted_content,
        'status': application.status,
        'created_at': application.created_at.strftime('%Y-%m-%d %H:%M:%S')
    })

@dashboard_bp.route('/review-application', methods=['POST'])
@login_required
def review_application():
    if not current_user.is_admin:
        return jsonify({'error': '无权操作'}), 403

    data = request.get_json()
    application_id = data.get('application_id')
    status = data.get('status')
    remark = data.get('remark')

    if not application_id or not status:
        return jsonify({'error': '参数不完整'})

    application = Application.query.get_or_404(application_id)
    if application.status != 'pending':
        return jsonify({'error': '该申请已被处理'})

    if status == "approved" and remark == "auto" and application.form_type != "player":
        current_year = str(datetime.now().year)
        apps = Application.query.filter_by(form_type=application.form_type, status="approved").all()
        existing = []
        for i in apps:
            if i.remark[10:14] == current_year:
                existing.append(i.remark[15:19])
        existing = sorted(set(existing))
        for i in range(1, 10000):
            next_num = f"{i:04d}"
            if next_num not in existing:
                number = next_num
                break
        if application.form_type == "city":
            remark = f"批准文号：际城审字[{current_year}]{number}号"
        else:
            remark = f"批准文号：际交审字[{current_year}]{number}号"

    try:
        application.status = status
        application.remark = remark
        application.reviewed_at = get_current_time()
        application.reviewer_id = current_user.id
        if status == "approved" and application.form_type == "player":
            user = User.query.filter_by(id=application.user_id).first()
            if application.content['permission'] == '创造者权限（OP2）' and user.role != 'admin':
                user.role = 'creator'
                headers = {
                'User-Agent': 'tjb',
                "Api-Key": current_app.config["DISCOUESE_API_KEY"],
                "Api-Username": "system"
                }
                requests.put("https://forum.tjmtr.world/groups/41/members.json", headers=headers, json={"usernames": application.content["forum_email"]})
            elif application.content['permission'] == '仅旁观' and user.role != 'admin' and user.role != 'creator' and user.role != 'player':
                user.role = 'visitor'
            elif application.content['permission'] == '仅生存' or application.content['permission'] == '仅创造' and user.role != 'admin' and user.role != 'creator':
                user.role = 'player'
        db.session.commit()

        return jsonify({'message': f'审核成功，{remark}'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)})

@dashboard_bp.context_processor
def inject_permissions():
    def has_creative_permission():
        return check_creative_permission()
    return dict(has_creative_permission=has_creative_permission)

@dashboard_bp.route('/oauth-management')
@login_required
def oauth_management():
    """OAuth应用管理页面"""
    if not current_user.is_admin:
        return render_template('dashboard/error.html',
            message='无权访问此页面',
            redirect_url=url_for('dashboard.index'))

    oauth_apps = OAuthApp.query.order_by(OAuthApp.created_at.desc()).all()
    return render_template('dashboard/admin/oauth_management.html',
        oauth_apps=oauth_apps)

@dashboard_bp.route('/oauth/create-app', methods=['POST'])
@login_required
def create_oauth_app():
    """创建OAuth应用"""
    if not current_user.is_admin:
        return jsonify({'error': '无权操作'}), 403

    data = request.get_json()
    name = data.get('name')
    description = data.get('description')
    redirect_uris = data.get('redirect_uris')

    if not all([name, description, redirect_uris]):
        return jsonify({'error': '缺少必要参数'})

    try:
        app = OAuthApp(
            client_id=OAuthApp.generate_client_id(),
            client_secret=OAuthApp.generate_client_secret(),
            name=name,
            description=description,
            redirect_uris=redirect_uris,
            created_by=current_user.id
        )
        db.session.add(app)
        db.session.commit()

        return jsonify({'message': '应用创建成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)})

@dashboard_bp.route('/oauth/app/<int:id>')
@login_required
def get_oauth_app(id):
    """获取OAuth应用详情"""
    if not current_user.is_admin:
        return jsonify({'error': '无权访问'}), 403

    app = OAuthApp.query.get_or_404(id)
    return jsonify({
        'id': app.id,
        'name': app.name,
        'description': app.description,
        'client_id': app.client_id,
        'client_secret': app.client_secret,
        'redirect_uris': app.redirect_uris
    })

@dashboard_bp.route('/oauth/regenerate-secret/<int:id>', methods=['POST'])
@login_required
def regenerate_oauth_secret(id):
    """重新生成Client Secret"""
    if not current_user.is_admin:
        return jsonify({'error': '无权操作'}), 403

    app = OAuthApp.query.get_or_404(id)
    try:
        app.client_secret = OAuthApp.generate_client_secret()
        db.session.commit()
        return jsonify({'message': '密钥已重置'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)})

@dashboard_bp.route('/oauth/delete-app/<int:id>', methods=['POST'])
@login_required
def delete_oauth_app(id):
    """删除OAuth应用"""
    if not current_user.is_admin:
        return jsonify({'error': '无权操作'}), 403

    app = OAuthApp.query.get_or_404(id)
    try:
        db.session.delete(app)
        db.session.commit()
        return jsonify({'message': '应用已删除'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)})


def background_review(application_id, user_id, config, Session):
    """后台审核任务"""
    with current_app.app_context():
        db_session = Session()
        try:
            application = db_session.query(Application).get(application_id)
            user = db_session.query(User).get(user_id)

            # 进行审核
            passed, notes = auto_review_player_application(application, config['MCRCON_HOST'], config['MCRCON_PASSWORD'], config['MCRCON_PORT'])

            if passed == None:
                application.status = 'pending'
            elif passed == False:
                application.status = 'rejected'
            else:
                application.status = 'approved'

            application.remark = notes
            application.reviewed_at = datetime.now(pytz.timezone('Asia/Shanghai'))
            application.reviewer_id = None  # 自动审核

            if passed == True:
                if application.content['permission'] == '创造者权限（OP2）' and user.role != 'admin':
                    user.role = 'creator'
                elif application.content['permission'] == '仅旁观' and user.role != 'admin' and user.role != 'creator' and user.role != 'player':
                    user.role = 'visitor'
                elif application.content['permission'] == '仅生存' or application.content['permission'] == '仅创造' and user.role != 'admin' and user.role != 'creator':
                    user.role = 'player'

            db_session.commit()

        except Exception as e:
            db_session.rollback()
            current_app.logger.error(f"后台审核任务失败: {str(e)}")
        finally:
            db_session.close()



@dashboard_bp.route('/quick-review/<int:id>', methods=['POST'])
@login_required
def quick_review(id):
    """快速审核(花费30天际币)"""
    # 检查天际币余额
    if current_user.coins < 30:
        return jsonify({'error': '天际币余额不足'})

    # 获取申请
    application = Application.query.get_or_404(id)

    # 检查是否是自己的申请
    if application.user_id != current_user.id:
        return jsonify({'error': '只能快速审核自己的申请'})

    # 检查是否是待审核状态
    if application.status != 'pending':
        return jsonify({'error': '该申请已被处理'})

    # 检查是否是玩家权限申请
    if application.form_type != 'player':
        return jsonify({'error': '只能快速审核玩家权限申请'})

    # 克隆必要的配置参数
    config = {
        'MCRCON_HOST': current_app.config['MCRCON_HOST'],
        'MCRCON_PASSWORD': current_app.config['MCRCON_PASSWORD'],
        'MCRCON_PORT': current_app.config['MCRCON_PORT']
    }

    # 扣除天际币
    current_user.coins -= 30

    # 记录天际币消费
    coin_record = CoinRecord(
        user_id=current_user.id,
        amount=-30,
        reason='快速审核申请'
    )
    db.session.add(coin_record)
    application.remark = "已提交请求，请稍后"

    try:
        db.session.commit()
        Session = scoped_session(sessionmaker(bind=db.engine))
        background_review(application.id, current_user.id, config, Session)
        return jsonify({'message': '审核完毕'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)})

def to_hex_string(byte_array):
    return ''.join([f'{byte:02x}' for byte in byte_array])


def splitted_uuid(uuid):
    return '-'.join([uuid[:8], uuid[8:12], uuid[12:16], uuid[16:20], uuid[20:32]])

@dashboard_bp.route('/get-uuid', methods=['POST'])
@login_required
def get_uuid():
    """获取玩家UUID"""
    data = request.get_json()
    account_type = data.get('account_type')
    player_name = data.get('player_name')

    if not player_name:
        return jsonify({'error': '请输入玩家名'})

    if account_type == 'microsoft':
        try:
            response = requests.get(f'https://api.mojang.com/users/profiles/minecraft/{player_name}')
            data = response.json()
            if 'errorMessage' in data:
                return jsonify({'error': '玩家不存在'})
            # 格式化UUID
            raw_uuid = data['id']
            formatted_uuid = f"{raw_uuid[:8]}-{raw_uuid[8:12]}-{raw_uuid[12:16]}-{raw_uuid[16:20]}-{raw_uuid[20:]}"
            return jsonify({'uuid': formatted_uuid})
        except Exception as e:
            return jsonify({'error': '获取UUID失败，请重试'})

    elif account_type == 'offline':
        # 按照 Minecraft 离线模式的 UUID 规则生成
        input_data = f"OfflinePlayer:{player_name}"
        hash_bytes = hashlib.md5(input_data.encode('utf-8')).digest()

        # 将哈希值转换为字节数组
        byte_array = list(hash_bytes)

        # 根据 RFC 4122 修改 UUID 的特定位
        byte_array[6] = (byte_array[6] & 0x0f) | 0x30  # 设置 UUID 的版本号为 3 (基于名字的 UUID)
        byte_array[8] = (byte_array[8] & 0x3f) | 0x80  # 设置 UUID 的变种为 RFC 4122

        # 将字节数组转换为 UUID 的十六进制字符串
        uuid_hex = ''.join(f'{byte:02x}' for byte in byte_array)

        # 返回 UUID
        return jsonify({'uuid': splitted_uuid(to_hex_string(byte_array))})

    return jsonify({'error': '不支持的账号类型'})

@dashboard_bp.route('/game-accounts')
@login_required
def game_accounts():
    """游戏内账号管理"""
    # 获取所有已通过的玩家申请
    approved_apps = Application.query.filter_by(
        user_id=current_user.id,
        form_type='player',
        status='approved'
    ).all()

    # 用集合去重，只保留最新的申请
    accounts = {}
    for app in approved_apps:
        player_name = app.content.get('player_name')
        if player_name and player_name not in accounts:
            accounts[player_name] = {
                'player_name': player_name,
                'uuid': app.content.get('uuid'),
                'account_type': app.content.get('game_account_type'),
                'avatar_url': f'https://minotar.net/avatar/{player_name}'
            }

    return render_template('dashboard/game_accounts.html', accounts=accounts.values())

@dashboard_bp.route('/game-account/<player_name>/manage')
@login_required
def manage_game_account(player_name):
    """游戏账号管理面板"""
    # 获取该玩家最新的已通过申请
    application = Application.query.filter_by(
        user_id=current_user.id,
        form_type='player',
        status='approved'
    ).order_by(Application.created_at.desc()).all()
    l = []
    player_permissions = {}  # 使用字典存储玩家名和对应的权限
    for i in application:
        player_name_in_application = i.content.get("player_name")
        if player_name_in_application not in l:
            l.append(player_name_in_application)
        if player_name_in_application not in player_permissions:
            player_permissions[player_name_in_application] = []
        player_permissions[player_name_in_application].append(i.content.get("permission"))

    if not application or player_name not in l:
        return jsonify({'error': '未找到该账号或无权限'}), 404

    permissions_l = player_permissions.get(player_name, [])
    # 获取权限等级
    permissions = {
        '仅旁观': 0,
        '仅生存': 1,
        '仅创造': 2,
        '创造者权限（OP2）': 3
    }

    # 获取该玩家名的权限等级
    permissions_l = [permissions.get(permission, 0) for permission in permissions_l]
    permission_level = max(permissions_l)  # 选择该玩家的最大权限等级

    # 获取可用的游戏模式
    available_modes = ['旁观']
    if permission_level >= 1:
        available_modes.append('生存')
    if permission_level >= 2:
        available_modes.append('创造')

    # 获取可用的资源包
    available_resource_packs = []
    for pack in current_app.config['RESOURCE_PACKS']:
        if permission_level in pack['permissions']:
            available_resource_packs.append(pack)

    account_info = {
        'player_name': player_name,
        'permission_level': permission_level,
        'permission': {v: k for k, v in permissions.items()}[permission_level],
        'available_modes': available_modes,
        'can_use_op2': permission_level == 3,
        'can_teleport': permission_level >= 2,
        'can_use_effects': permission_level >= 1,
        'can_spawn': permission_level >= 1,
        'available_resource_packs': available_resource_packs
    }

    return render_template('dashboard/game_account_manage.html', account=account_info)

def change_mode(username, mode_t, host, password, port):
    rcon = mcrcon.MCRcon(host, password, port)
    rcon.connect()
    if "创造" in mode_t:
        mode = "creative"
    elif "生存" in mode_t:
        mode = "survival"
    else:
        mode = "spectator"
    response = rcon.command(f'gamemode {mode} {username}')
    rcon.disconnect()

def send_cmd(cmd, host, password, port):
    rcon = mcrcon.MCRcon(host, password, port)
    rcon.connect()
    response = rcon.command(cmd)
    rcon.disconnect()

@dashboard_bp.route('/game-account/action', methods=['POST'])
@login_required
def game_account_action():
    """处理游戏账号管理操作"""
    data = request.get_json()
    action = data.get('action')
    player_name = data.get('player_name')

    # 验证权限
    application = Application.query.filter_by(
        user_id=current_user.id,
        form_type='player',
        status='approved'
    ).order_by(Application.created_at.desc()).all()
    l = []
    player_permissions = {}
    for i in application:
        player_name_in_application = i.content.get("player_name")
        if player_name_in_application not in l:
            l.append(player_name_in_application)
        if player_name_in_application not in player_permissions:
            player_permissions[player_name_in_application] = []
        player_permissions[player_name_in_application].append(i.content.get("permission"))

    if not application or player_name not in l:
        return jsonify({'error': '无权限操作'}), 404

    permissions_l = player_permissions.get(player_name, [])
    # 获取权限等级
    permissions = {
        '仅旁观': 0,
        '仅生存': 1,
        '仅创造': 2,
        '创造者权限（OP2）': 3
    }

    # 获取该玩家名的权限等级
    permissions_l = [permissions.get(permission, 0) for permission in permissions_l]
    permission_level = max(permissions_l)  # 选择该玩家的最大权限等级

    # 获取可用的游戏模式
    available_modes = ['旁观']
    if permission_level >= 1:
        available_modes.append('生存')
    if permission_level >= 2:
        available_modes.append('创造')

    try:
        if action == 'change_mode':
            mode = data.get('mode')
            if permission_level < 2 and "创造" in mode:
                return jsonify({'error': '无权限操作'}), 404
            if permission_level < 1 and "生存" in mode:
                return jsonify({'error': '无权限操作'}), 404
            change_mode(player_name, mode, current_app.config['MCRCON_HOST'], current_app.config['MCRCON_PASSWORD'], current_app.config['MCRCON_PORT'])
        elif action == 'grant_op2':
            if permission_level  != 3:
                return jsonify({'error': '无权限操作'}), 404
            send_cmd(f'op {player_name}', current_app.config['MCRCON_HOST'], current_app.config['MCRCON_PASSWORD'], current_app.config['MCRCON_PORT'])
        elif action == 'teleport':
            x = data.get('x')
            y = data.get('y')
            z = data.get('z')
            if permission_level < 2:
                return jsonify({'error': '无权限操作'}), 404
            send_cmd(f'tp {player_name} {x} {y} {z}', current_app.config['MCRCON_HOST'], current_app.config['MCRCON_PASSWORD'], current_app.config['MCRCON_PORT'])
        elif action == 'spawn':
            if permission_level == 0:
                return jsonify({'error': '无权限操作'}), 404
            send_cmd(f'kill {player_name}', current_app.config['MCRCON_HOST'], current_app.config['MCRCON_PASSWORD'], current_app.config['MCRCON_PORT'])
        elif action == 'effect':
            effect = data.get('effect')
            if permission_level == 0:
                return jsonify({'error': '无权限操作'}), 404
            if "night_vision" in effect:
                send_cmd(f'effect give {player_name} night_vision infinite 2 true', current_app.config['MCRCON_HOST'], current_app.config['MCRCON_PASSWORD'], current_app.config['MCRCON_PORT'])
            else:
                send_cmd(f'effect give {player_name} speed infinite 2 true', current_app.config['MCRCON_HOST'], current_app.config['MCRCON_PASSWORD'], current_app.config['MCRCON_PORT'])
        else:
            return jsonify({'error': '未知操作'}), 400

        return jsonify({'message': '操作成功'})
    except ValueError as e:
        return jsonify({'error': str(e)}), 500

@dashboard_bp.route('/activity-answers/<int:activity_id>')
@login_required
def activity_answers(activity_id):

    if not current_user.is_admin:
        return jsonify({'error': '无权限'})

    activity = Activity.query.get_or_404(activity_id)
    if activity.type != 'metro_quiz':
        return jsonify({'error': '不支持的活动类型'})

    # 如果活动未开奖，不允许查看答题记录
    if activity.status == 'active':
        return jsonify({'error': '活动尚未开奖'})

    answers = []
    for participant in activity.participants:
        user = User.query.get(participant.user_id)
        answers.append({
            'username': user.username,
            'answers': participant.answers,
            'reward': participant.reward,
            'created_at': participant.created_at.strftime('%Y-%m-%d %H:%M:%S')
        })

    return jsonify({
        'answers': answers
    })

@dashboard_bp.context_processor
def utility_processor():
    return dict(get_current_time=get_current_time)

@dashboard_bp.route('/railway-section')
@login_required
def railway_section():
    # 从申请提交中获取已通过的城市申请
    approved_cities = Application.query.filter_by(
        form_type='city',
        status='approved'
    ).all()

    # 构建铁路局列表
    bureaus = ['天际铁路局']  # 确保天际铁路局始终在最上方
    for app in approved_cities:
        bureau = f"{app.content.get('city_name_cn')}铁路局"
        if bureau not in bureaus:
            bureaus.append(bureau)

    return render_template('dashboard/railway_section.html', bureaus=bureaus)

@dashboard_bp.route('/api/train-numbers', methods=['POST'])
@login_required
def submit_train_numbers():
    data = request.json
    applications = data.get('applications', [])

    # 计算总费用
    total_cost = len(applications) * 2

    # 检查天际币是否足够
    if current_user.coins < total_cost:
        return jsonify({'error': f'天际币不足，需要{total_cost}天际币'})

    try:
        for app in applications:
            train_number = TrainNumber(
                user_id=current_user.id,
                prefix=app['prefix'],
                number=app['number'],
                bureau=app['bureau'],
                start_station=app['startStation'],
                start_station_data=app.get('startStationData'),
                end_station=app['endStation'],
                end_station_data=app.get('endStationData'),
                is_return=app.get('isReturn', False),
                return_to=app.get('linkedTo')
            )
            db.session.add(train_number)

        # 扣除天际币
        current_user.coins -= total_cost

        # 添加天际币记录
        record = CoinRecord(
            user_id=current_user.id,
            amount=-total_cost,
            reason='申请国铁号段'
        )
        db.session.add(record)

        db.session.commit()
        return jsonify({'message': '申请成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)})

@dashboard_bp.route('/api/check-train-number/<train_number>')
@login_required
def check_train_number(train_number):
    """检查车次是否已被占用"""
    if len(train_number) < 2:
        return jsonify({'error': '无效的车次号'})
        
    prefix = train_number[0]
    number = train_number[1:]
    
    if prefix not in ['G', 'C', 'D', 'T', 'K', 'Z']:
        return jsonify({'error': '无效的车次前缀'})
        
    try:
        number_int = int(number)
        if not (1 <= number_int <= 9999):
            return jsonify({'error': '车次号必须在1-9999之间'})
    except ValueError:
        return jsonify({'error': '无效的车次号'})
    
    existing = TrainNumber.query.filter_by(
        prefix=prefix,
        number=number
    ).first()
    
    return jsonify({
        'available': not bool(existing),
        'message': '车次可用' if not existing else '车次已被占用'
    })

@dashboard_bp.route('/api/train-number/<train_number>')
@login_required
def get_train_number(train_number):
    """查询车次信息"""
    train = TrainNumber.query.filter_by(
        prefix=train_number[0],
        number=train_number[1:]
    ).first()

    if not train:
        return jsonify({'error': '未找到该车次'})

    # 获取关联的折返/去程车次
    related_train = None
    if train.is_return:
        related_train = TrainNumber.query.filter_by(
            prefix=train.return_to[0],
            number=train.return_to[1:]
        ).first()
    else:
        related_train = TrainNumber.query.filter_by(
            return_to=train.train_number
        ).first()

    return jsonify({
        'train_number': train.train_number,
        'bureau': train.bureau,
        'start_station': train.start_station,
        'start_station_data': train.start_station_data,
        'end_station': train.end_station,
        'end_station_data': train.end_station_data,
        'is_return': train.is_return,
        'related_train': related_train.train_number if related_train else None
    })

@dashboard_bp.route('/api/report-train', methods=['POST'])
@login_required
def report_train():
    """举报车次滥用"""
    data = request.json
    train_number = data.get('train_number')
    message = data.get('message')

    if not train_number or not message:
        return jsonify({'error': '参数不完整'})

    try:
        report = TrainReport(
            train_number=train_number,
            reporter_id=current_user.id,
            message=message
        )
        db.session.add(report)
        db.session.commit()

        return jsonify({'message': '举报成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)})

@dashboard_bp.route('/api/my-train-numbers')
@login_required
def get_my_train_numbers():
    """获取用户的车次申请记录"""
    trains = TrainNumber.query.filter_by(user_id=current_user.id).all()
    return jsonify([{
        'train_number': train.train_number,
        'bureau': train.bureau,
        'start_station': train.start_station,
        'end_station': train.end_station,
        'is_return': train.is_return,
        'return_to': train.return_to
    } for train in trains])

@dashboard_bp.route('/api/train-number/<train_number>', methods=['DELETE'])
@login_required
def delete_train_number(train_number):
    """删除车次申请"""
    train = TrainNumber.query.filter_by(
        prefix=train_number[0],
        number=train_number[1:]
    ).first()

    if not train or train.user_id != current_user.id:
        return jsonify({'error': '未找到该车次或无权限删除'})

    try:
        # 如果是去程车次，同时删除折返车次
        if not train.is_return:
            return_train = TrainNumber.query.filter_by(
                return_to=train_number
            ).first()
            if return_train:
                db.session.delete(return_train)
        else:
            # 如果是折返车次，同时删除去程车次
            original_train = TrainNumber.query.filter_by(
                prefix=train.return_to[0],
                number=train.return_to[1:]
            ).first()
            if original_train:
                db.session.delete(original_train)
        db.session.delete(train)
        db.session.commit()
        return jsonify({'message': '删除成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)})

@dashboard_bp.route('/api/train-number/<train_number>', methods=['PUT'])
@login_required
def update_train_number(train_number):
    """修改车次信息"""
    data = request.json
    train = TrainNumber.query.filter_by(
        prefix=train_number[0],
        number=train_number[1:],
        user_id=current_user.id
    ).first()

    if not train:
        return jsonify({'error': '未找到该车次或无权限修改'})

    try:
        train.bureau = data.get('bureau', train.bureau)
        train.start_station = data.get('startStation', train.start_station)
        train.start_station_data = data.get('startStationData', train.start_station_data)
        train.end_station = data.get('endStation', train.end_station)
        train.end_station_data = data.get('endStationData', train.end_station_data)

        # 如果有关联的折返车次，同步更新
        if not train.is_return:
            return_train = TrainNumber.query.filter_by(
                return_to=train_number
            ).first()
            if return_train:
                return_train.bureau = train.bureau
                return_train.start_station = train.end_station
                return_train.start_station_data = train.end_station_data
                return_train.end_station = train.start_station
                return_train.end_station_data = train.start_station_data

        db.session.commit()
        return jsonify({'message': '修改成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)})

@dashboard_bp.route('/api/reports')
@login_required
def get_reports():
    """获取举报列表"""
    if not current_user.is_admin:
        return jsonify({'error': '无权限'}), 403

    reports = TrainReport.query.filter_by(status='pending').all()
    return jsonify([{
        'id': report.id,
        'train_number': report.train_number,
        'reporter': User.query.get(report.reporter_id).username,
        'message': report.message,
        'created_at': report.created_at.strftime('%Y-%m-%d %H:%M:%S')
    } for report in reports])

@dashboard_bp.route('/api/report/<int:report_id>', methods=['POST'])
@login_required
def process_report(report_id):
    """处理举报"""
    if not current_user.is_admin:
        return jsonify({'error': '无权限'}), 403

    data = request.json
    action = data.get('action')  # 'approve' or 'reject'

    report = TrainReport.query.get_or_404(report_id)
    if report.status != 'pending':
        return jsonify({'error': '该举报已被处理'})

    try:
        if action == 'approve':
            # 删除被举报的车次及其关联车次
            train = TrainNumber.query.filter_by(
                prefix=report.train_number[0],
                number=report.train_number[1:]
            ).first()

            if train:
                if not train.is_return:
                    return_train = TrainNumber.query.filter_by(
                        return_to=report.train_number
                    ).first()
                    if return_train:
                        db.session.delete(return_train)
                else:
                    original_train = TrainNumber.query.filter_by(
                        prefix=train.return_to[0],
                        number=train.return_to[1:]
                    ).first()
                    if original_train:
                        db.session.delete(original_train)

                db.session.delete(train)

        report.status = 'approved' if action == 'approve' else 'rejected'
        report.processed_at = datetime.now(pytz.timezone('Asia/Shanghai'))
        report.processor_id = current_user.id

        db.session.commit()
        return jsonify({'message': '处理成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)})

@dashboard_bp.route('/reset-password/<int:userID>', methods=['POST'])
@login_required
def resetPassword(userID):
    if not current_user.is_admin:
        return jsonify({'error': '无权限'}), 403
    user = User.query.filter_by(id=userID).first()
    if not user:
        return "用户不存在", 400
    pw = ''.join(''.join(random.choices(string.ascii_letters + string.digits, k=12)))
    user.set_password(pw)
    db.session.commit()
    email = user.email
    try:
        # 发送邮件
        msg = Message(
            '密码重置 - Tianji Center',
            sender=current_app.config['MAIL_USERNAME'],
            recipients=[email]
        )
        msg.body = f'您的新密码是：{pw}。请尽快修改！若非本人要求，请立即联系我们！'
        mail.send(msg)
        
        return jsonify({'message': '已发送'})
    except Exception as e:
        current_app.logger.error(f'发送失败: {str(e)}')
        return jsonify({'error': '发送失败，请重试'})
