from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from models.oauth import OAuthApp, OAuthCode, OAuthToken
from extensions import db
from datetime import datetime, timedelta
from urllib.parse import urlencode
import json
from models.user import User

oauth_bp = Blueprint('oauth', __name__)

# OAuth 授权范围定义
OAUTH_SCOPES = {
    'basic': '基本信息（用户名、邮箱）',
    'profile': '个人资料',
    'applications': '申请记录',
}

@oauth_bp.route('/authorize')
def authorize():
    """OAuth授权页面"""
    # 验证必需的参数
    client_id = request.args.get('client_id')
    redirect_uri = request.args.get('redirect_uri')
    response_type = request.args.get('response_type')  # 需要添加这个参数检查
    scope = request.args.get('scope', 'basic')
    state = request.args.get('state', '')
    
    # 验证必需参数
    if not all([client_id, redirect_uri, response_type]):
        return render_template('oauth/error.html', 
            error='invalid_request',
            description='缺少必要参数 client_id、redirect_uri 或 response_type')
    
    # 验证 response_type（OAuth2.0 要求）
    if response_type != 'code':
        return render_template('oauth/error.html',
            error='unsupported_response_type',
            description='仅支持 authorization code 授权方式')
    
    # 验证应用
    app = OAuthApp.query.filter_by(client_id=client_id).first()
    if not app:
        return render_template('oauth/error.html',
            error='无效的应用',
            description='找不到对应的应用')
    
    # 验证回调地址
    if redirect_uri not in app.redirect_uris.split(','):
        return render_template('oauth/error.html',
            error='无效的回调地址',
            description='该回调地址未在应用中注册')
    
    # 解析请求的权限范围
    requested_scopes = scope.split()
    scopes = []
    for s in requested_scopes:
        if s in OAUTH_SCOPES:
            scopes.append(OAUTH_SCOPES[s])
    
    # 如果用户未登录，重定向到登录页面
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login', next=request.url))
    
    return render_template('oauth/authorize.html',
        app=app,
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=scope,
        state=state,
        scopes=scopes)

@oauth_bp.route('/authorize', methods=['POST'])
@login_required
def handle_authorize():
    """处理授权请求"""
    client_id = request.form.get('client_id')
    redirect_uri = request.form.get('redirect_uri')
    scope = request.form.get('scope', 'basic')
    state = request.form.get('state', '')
    action = request.form.get('action')
    
    # 如果用户拒绝授权
    if action != 'allow':
        params = {
            'error': 'access_denied',
            'error_description': '用户拒绝授权'
        }
        if state:
            params['state'] = state
        return redirect(f'{redirect_uri}?{urlencode(params)}')
    
    try:
        # 生成授权码
        code = OAuthCode(
            code=OAuthCode.generate_code(),
            client_id=client_id,
            user_id=current_user.id,
            scope=scope,
            redirect_uri=redirect_uri,
            expires_at=datetime.utcnow() + timedelta(minutes=10)
        )
        db.session.add(code)
        db.session.commit()
        
        # 重定向回应用
        params = {'code': code.code}
        if state:
            params['state'] = state
        return redirect(f'{redirect_uri}?{urlencode(params)}')
        
    except Exception as e:
        db.session.rollback()
        params = {
            'error': 'server_error',
            'error_description': str(e)
        }
        if state:
            params['state'] = state
        return redirect(f'{redirect_uri}?{urlencode(params)}')

@oauth_bp.route('/token', methods=['POST'])
def token():
    """获取访问令牌"""
    # 验证 Content-Type
    if not request.headers.get('Content-Type', '').startswith('application/x-www-form-urlencoded'):
        return jsonify({
            'error': 'invalid_request',
            'error_description': '请求必须使用 application/x-www-form-urlencoded 格式'
        }), 400

    grant_type = request.form.get('grant_type')
    
    if grant_type == 'authorization_code':
        return handle_authorization_code()
    elif grant_type == 'refresh_token':
        return handle_refresh_token()
    else:
        return jsonify({
            'error': 'unsupported_grant_type',
            'error_description': '不支持的授权类型'
        }), 400

def handle_authorization_code():
    """处理授权码方式"""
    # 所有参数都应该从 form 中获取
    code = request.form.get('code')
    client_id = request.form.get('client_id')
    client_secret = request.form.get('client_secret')
    redirect_uri = request.form.get('redirect_uri')
    
    # 验证所有必需参数
    if not all([code, client_id, client_secret, redirect_uri]):
        return jsonify({
            'error': 'invalid_request',
            'error_description': '缺少必要参数'
        }), 400
    
    # 验证应用凭证
    app = OAuthApp.query.filter_by(
        client_id=client_id,
        client_secret=client_secret
    ).first()
    if not app:
        return jsonify({
            'error': 'invalid_client',
            'error_description': '无效的应用凭证'
        }), 401
    
    # 验证授权码
    auth_code = OAuthCode.query.filter_by(
        code=code,
        client_id=client_id,
        redirect_uri=redirect_uri
    ).first()
    
    if not auth_code or auth_code.expires_at < datetime.utcnow():
        return jsonify({
            'error': 'invalid_grant',
            'error_description': '无效或已过期的授权码'
        }), 400
    
    try:
        # 生成访问令牌
        token = OAuthToken(
            access_token=OAuthToken.generate_token(),
            refresh_token=OAuthToken.generate_token(),
            client_id=client_id,
            user_id=auth_code.user_id,
            scope=auth_code.scope,
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )
        db.session.add(token)
        
        # 删除使用过的授权码（安全要求）
        db.session.delete(auth_code)
        db.session.commit()
        
        # 标准的 OAuth2.0 响应格式
        return jsonify({
            'access_token': token.access_token,
            'token_type': 'Bearer',
            'expires_in': 86400,  # 24小时（秒）
            'refresh_token': token.refresh_token,
            'scope': token.scope or ''  # 确保返回空字符串而不是 None
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'server_error',
            'error_description': str(e)
        }), 500

def handle_refresh_token():
    """处理刷新令牌方式"""
    refresh_token = request.form.get('refresh_token')
    client_id = request.form.get('client_id')
    client_secret = request.form.get('client_secret')
    
    # 验证参数
    if not all([refresh_token, client_id, client_secret]):
        return jsonify({
            'error': 'invalid_request',
            'error_description': '缺少必要参数'
        }), 400
    
    # 验证应用凭证
    app = OAuthApp.query.filter_by(
        client_id=client_id,
        client_secret=client_secret
    ).first()
    if not app:
        return jsonify({
            'error': 'invalid_client',
            'error_description': '无效的应用凭证'
        }), 401
    
    # 验证刷新令牌
    old_token = OAuthToken.query.filter_by(
        refresh_token=refresh_token,
        client_id=client_id
    ).first()
    
    if not old_token:
        return jsonify({
            'error': 'invalid_grant',
            'error_description': '无效的刷新令牌'
        }), 400
    
    try:
        # 生成新的访问令牌
        new_token = OAuthToken(
            access_token=OAuthToken.generate_token(),
            refresh_token=OAuthToken.generate_token(),
            client_id=client_id,
            user_id=old_token.user_id,
            scope=old_token.scope,
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )
        db.session.add(new_token)
        
        # 删除旧的令牌
        db.session.delete(old_token)
        db.session.commit()
        
        return jsonify({
            'access_token': new_token.access_token,
            'token_type': 'Bearer',
            'expires_in': 86400,  # 24小时
            'refresh_token': new_token.refresh_token,
            'scope': new_token.scope
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'server_error',
            'error_description': str(e)
        }), 500

@oauth_bp.route('/api/user', methods=['GET'])
def get_user_info():
    """获取用户信息的API接口"""
    # 从请求头中获取访问令牌
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        # 按照 RFC 6750 规范返回错误
        response = jsonify({
            'error': 'invalid_request',
            'error_description': '缺少访问令牌'
        })
        response.headers['WWW-Authenticate'] = 'Bearer realm="User API"'
        return response, 401
    
    # 提取访问令牌
    access_token = auth_header.split(' ')[1]
    
    # 验证访问令牌
    token = OAuthToken.query.filter_by(access_token=access_token).first()
    if not token:
        response = jsonify({
            'error': 'invalid_token',
            'error_description': '无效的访问令牌'
        })
        response.headers['WWW-Authenticate'] = 'Bearer error="invalid_token"'
        return response, 401
    
    # 检查令牌是否过期
    if token.expires_at < datetime.utcnow():
        response = jsonify({
            'error': 'invalid_token',
            'error_description': '访问令牌已过期'
        })
        response.headers['WWW-Authenticate'] = 'Bearer error="invalid_token", error_description="The access token expired"'
        return response, 401
    
    # 获取用户信息
    user = User.query.get(token.user_id)
    if not user:
        return jsonify({
            'error': 'invalid_token',
            'error_description': '找不到对应的用户'
        }), 401
    
    # 根据授权范围返回用户信息
    scopes = token.scope.split() if token.scope else []
    
    # 基本信息（basic scope）
    response = {
        'id': user.id,
        'username': user.username,
        'email': user.email
    }
    
    return jsonify(response) 