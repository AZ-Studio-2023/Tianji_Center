from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session, current_app, flash
from models.user import User, CoinRecord
from extensions import db, mail
from utils.email import generate_email_code, save_email_code, verify_email_code
from utils.oauth import qq_oauth, wechat_oauth, github_oauth, microsoft_oauth
from utils.cloudflare import verify_cloudflare
from flask_login import login_user, login_required, current_user, logout_user
from flask_mail import Message

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
        
    if request.method == 'POST':
        data = request.get_json()
        email = data.get('email')
        username = data.get('username')
        password = data.get('password')
        code = data.get('code')
        cf_token = data.get('cf-turnstile-response')
        
        # 验证Cloudflare人机验证
        if current_app.config['ENABLE_CLOUDFLARE'] and not verify_cloudflare(cf_token):
            return jsonify({'error': '人机验证失败'})
            
        # 验证邮箱验证码
        if not verify_email_code(email, code):
            return jsonify({'error': '验证码错误'})
            
        # 检查邮箱是否已被注册
        if User.query.filter_by(email=email).first():
            return jsonify({'error': '该邮箱已被注册'})
            
        # 检查用户名是否已被使用
        if User.query.filter_by(username=username).first():
            return jsonify({'error': '该用户名已被使用'})
            
        # 创建新用户
        try:
            user = User(
                email=email, 
                username=username,
                avatar_type='cravatar'  # 设置默认头像类型
            )
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            return jsonify({'message': '注册成功'})
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'注册失败: {str(e)}')
            return jsonify({'error': '注册失败，请重试'})
        
    return render_template('auth/register.html', active_page='register')
 
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
        
    if request.method == 'POST':
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            # 登录成功处理
            login_user(user)
            return jsonify({'message': '登录成功'})
            
        return jsonify({'error': '邮箱或密码错误'})
        
    return render_template('auth/login.html', active_page='login') 

@auth_bp.route('/send-code', methods=['POST'])
def send_code():
    data = request.get_json()
    email = data.get('email')
    if not email:
        return jsonify({'error': '请输入邮箱'})
        
    code = generate_email_code()
    save_email_code(email, code)
    
    try:
        # 发送邮件
        msg = Message(
            '验证码 - Tianji Center',
            sender=current_app.config['MAIL_USERNAME'],
            recipients=[email]
        )
        msg.body = f'您的验证码是：{code}，5分钟内有效。'
        mail.send(msg)
        
        return jsonify({'message': '验证码已发送'})
    except Exception as e:
        current_app.logger.error(f'发送验证码失败: {str(e)}')
        return jsonify({'error': '发送失败，请重试'})

@auth_bp.route('/oauth-login/<provider>')
def oauth_login(provider):
    # 生成回调地址
    redirect_uri = url_for('auth.oauth_callback', provider=provider, _external=True)
    
    if provider == 'qq':
        return redirect(qq_oauth.get_auth_url(redirect_uri))
    elif provider == 'wechat':
        return redirect(wechat_oauth.get_auth_url())
    elif provider == 'github':
        return redirect(github_oauth.get_auth_url())
    elif provider == 'microsoft':
        return redirect(microsoft_oauth.get_auth_url())
    else:
        return '不支持的登录方式'

@auth_bp.route('/oauth-callback/<provider>')
def oauth_callback(provider):
    code = request.args.get('code')
    if not code:
        return '授权失败'
        
    try:
        # 获取用户信息
        if provider == 'qq':
            user_info = qq_oauth.get_user_info(code)
            social_id = user_info['social_uid']
            
            # 检查是否已经绑定
            existing_user = User.query.filter_by(qq_id=social_id).first()
            if existing_user:
                if current_user.is_authenticated and current_user.id != existing_user.id:
                    flash('该QQ账号已被其他账号绑定', 'error')
                    return redirect(url_for('dashboard.oauth_accounts'))
                # 如果未登录，则登录已绑定的账号
                login_user(existing_user)
                return redirect(url_for('dashboard.index'))
            
            # 如果当前用户已登录，直接绑定
            if current_user.is_authenticated:
                try:
                    # 检查是否已经获得过QQ绑定奖励
                    if not current_user.qq_reward:
                        # 添加15个天际币奖励
                        current_user.coins += 15
                        # 记录天际币变动
                        record = CoinRecord(
                            user_id=current_user.id,
                            amount=15,
                            reason='绑定QQ账号奖励'
                        )
                        db.session.add(record)
                        current_user.qq_reward = True
                    
                    # 保存QQ信息
                    current_user.qq_id = social_id
                    current_user.qq_avatar = user_info['faceimg']
                    
                    db.session.commit()
                    flash('QQ账号绑定成功，获得15天际币奖励', 'success')
                    return redirect(url_for('dashboard.oauth_accounts'))
                except Exception as e:
                    db.session.rollback()
                    flash(f'绑定失败：{str(e)}', 'error')
                    return redirect(url_for('dashboard.oauth_accounts'))
            
            # 未登录用户，存储OAuth信息到session，跳转到绑定页面
            session['oauth_info'] = {
                'provider': 'QQ',
                'social_uid': social_id,
                'nickname': user_info['nickname'],
                'avatar': user_info['faceimg']
            }
            return redirect(url_for('auth.bind_account'))
        elif provider == 'wechat':
            user_info = wechat_oauth.get_user_info(code)
            social_id = user_info['social_uid']
            
            # 检查是否已经绑定
            existing_user = User.query.filter_by(wechat_id=social_id).first()
            if existing_user:
                if current_user.is_authenticated and current_user.id != existing_user.id:
                    flash('该微信账号已被其他账号绑定', 'error')
                    return redirect(url_for('dashboard.oauth_accounts'))
                # 如果未登录，则登录已绑定的账号
                login_user(existing_user)
                return redirect(url_for('dashboard.index'))
            
            # 如果当前用户已登录，直接绑定
            if current_user.is_authenticated:
                try:
                    current_user.wechat_id = social_id
                    # 检查是否已经获得过微信绑定奖励
                    if not current_user.wechat_reward:
                        current_user.wechat_reward = True
                        current_user.coins += 15
                        # 添加天际币记录
                        record = CoinRecord(
                            user_id=current_user.id,
                            amount=15,
                            reason='绑定微信账号奖励'
                        )
                        db.session.add(record)
                    db.session.commit()
                    flash('微信账号绑定成功', 'success')
                    return redirect(url_for('dashboard.oauth_accounts'))
                except Exception as e:
                    db.session.rollback()
                    flash(f'绑定失败：{str(e)}', 'error')
                    return redirect(url_for('dashboard.oauth_accounts'))
            
            # 未登录用户，存储OAuth信息到session，跳转到绑定页面
            session['oauth_info'] = {
                'provider': '微信',
                'social_uid': social_id,
                'nickname': user_info['nickname'],
                'avatar': user_info['faceimg']
            }
            return redirect(url_for('auth.bind_account'))
        elif provider == 'github':
            try:
                user_info = github_oauth.get_user_info(code)
                # 检查是否已有用户绑定了该GitHub账号
                existing_user = User.query.filter_by(github_id=user_info['social_uid']).first()
                if existing_user:
                    login_user(existing_user)
                    return redirect(url_for('dashboard.index'))
                    
                # 如果当前用户已登录，则绑定账号
                if current_user.is_authenticated:
                    current_user.github_id = user_info['social_uid']
                    # 首次绑定奖励
                    if not current_user.github_reward:
                        current_user.coins += 15
                        current_user.github_reward = True
                        db.session.add(CoinRecord(
                            user_id=current_user.id,
                            amount=15,
                            reason='绑定GitHub账号奖励'
                        ))
                    db.session.commit()
                    return redirect(url_for('dashboard.oauth_accounts'))
                    
                # 存储OAuth信息用于后续绑定
                session['oauth_info'] = {
                    'provider': 'Github',
                    'social_uid': user_info['social_uid'],
                    'nickname': user_info['nickname'],
                    'avatar_url': user_info['faceimg']
                }
                return redirect(url_for('auth.bind_account'))
            except Exception as e:
                current_app.logger.error(f'GitHub OAuth回调错误: {str(e)}')
                return jsonify({'error': 'GitHub登录失败，请重试'})

        elif provider == 'microsoft':
            try:
                user_info = microsoft_oauth.get_user_info(code)
                # 检查是否已有用户绑定了该微软账号
                existing_user = User.query.filter_by(microsoft_id=user_info['social_uid']).first()
                if existing_user:
                    login_user(existing_user)
                    return redirect(url_for('dashboard.index'))
                    
                # 如果当前用户已登录，则绑定账号
                if current_user.is_authenticated:
                    current_user.microsoft_id = user_info['social_uid']
                    # 首次绑定奖励
                    if not current_user.microsoft_reward:
                        current_user.coins += 15
                        current_user.microsoft_reward = True
                        db.session.add(CoinRecord(
                            user_id=current_user.id,
                            amount=15,
                            reason='绑定微软账号奖励'
                        ))
                    db.session.commit()
                    return redirect(url_for('dashboard.oauth_accounts'))
                    
                # 存储OAuth信息用于后续绑定
                session['oauth_info'] = {
                    'provider': '微软',
                    'social_uid': user_info['social_uid'],
                    'nickname': user_info['nickname'],
                    'avatar_url': user_info['faceimg']
                }
                return redirect(url_for('auth.bind_account'))
            except Exception as e:
                current_app.logger.error(f'微软OAuth回调错误: {str(e)}')
                return jsonify({'error': '微软登录失败，请重试'})

        else:
            return '不支持的登录方式'
    except Exception as e:
        flash(f'授权失败：{str(e)}', 'error')
        return redirect(url_for('auth.login'))

@auth_bp.route('/bind-account', methods=['GET', 'POST'])
def bind_account():
    if 'oauth_info' not in session:
        return redirect(url_for('auth.login'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        cf_token = request.form.get('cf-turnstile-response')
        
        # 验证Cloudflare人机验证
        if current_app.config['ENABLE_CLOUDFLARE'] and not verify_cloudflare(cf_token):
            return jsonify({'error': '人机验证失败'})
        
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            # 检查是否已经被其他账号绑定
            oauth_info = session['oauth_info']
            existing_user = None
            
            # 根据不同的提供商检查是否已绑定
            if oauth_info['provider'] == 'QQ':
                existing_user = User.query.filter_by(qq_id=oauth_info['social_uid']).first()
            elif oauth_info['provider'] == '微信':
                existing_user = User.query.filter_by(wechat_id=oauth_info['social_uid']).first()
            elif oauth_info['provider'] == 'Github':
                existing_user = User.query.filter_by(github_id=oauth_info['social_uid']).first()
            elif oauth_info['provider'] == '微软':
                existing_user = User.query.filter_by(microsoft_id=oauth_info['social_uid']).first()
                
            if existing_user and existing_user.id != user.id:
                return jsonify({'error': '该第三方账号已被其他账号绑定'})
            
            # 绑定账号
            if oauth_info['provider'] == 'QQ':
                user.qq_id = oauth_info['social_uid']
            elif oauth_info['provider'] == '微信':
                user.wechat_id = oauth_info['social_uid']
            elif oauth_info['provider'] == 'Github':
                user.github_id = oauth_info['social_uid']
            elif oauth_info['provider'] == '微软':
                user.microsoft_id = oauth_info['social_uid']
                
            try:
                db.session.commit()
                login_user(user)
                session.pop('oauth_info')
                return jsonify({'message': '绑定成功'})
            except Exception as e:
                db.session.rollback()
                return jsonify({'error': '绑定失败，请重试'})
            
        return jsonify({'error': '邮箱或密码错误'})
        
    return render_template('auth/bind_account.html')


@auth_bp.route('/update-avatar', methods=['POST'])
@login_required
def update_avatar():
    provider = request.json.get('provider')
    if not provider:
        return jsonify({'error': '参数错误'})
        
    try:
        if provider == 'qq' and current_user.qq_id:
            # 获取QQ头像
            user_info = qq_oauth.get_user_info_by_id(current_user.qq_id)
            current_user.avatar_url = user_info['faceimg']
        elif provider == 'wechat' and current_user.wechat_id:
            # 获取微信头像
            user_info = wechat_oauth.get_user_info_by_id(current_user.wechat_id)
            current_user.avatar_url = user_info['faceimg']
        elif provider == 'github' and current_user.github_id:
            # 获取GitHub头像
            user_info = github_oauth.get_user_info_by_id(current_user.github_id)
            current_user.avatar_url = user_info['faceimg']
        elif provider == 'microsoft' and current_user.microsoft_id:
            # 获取Microsoft头像
            user_info = microsoft_oauth.get_user_info_by_id(current_user.microsoft_id)
            current_user.avatar_url = user_info['faceimg']
            
        db.session.commit()
        return jsonify({'message': '更新成功'})
    except Exception as e:
        return jsonify({'error': str(e)})

@auth_bp.route('/unbind', methods=['POST'])
@login_required
def unbind():
    provider = request.json.get('provider')
    if not provider:
        return jsonify({'error': '参数错误'})
        
    # 检查是否已领取奖励
    reward_key = f'{provider}_reward'
    if getattr(current_user, reward_key, False):
        try:
            if provider == 'qq':
                current_user.qq_id = None
            elif provider == 'wechat':
                current_user.wechat_id = None
            elif provider == 'github':
                current_user.github_id = None
            elif provider == 'microsoft':
                current_user.microsoft_id = None
                
            db.session.commit()
            return jsonify({'message': '解绑成功'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)})
    else:
        return jsonify({'error': '未领取奖励的账号不能解绑'})

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login')) 