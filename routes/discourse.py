from flask import Blueprint, render_template, request, redirect, url_for, jsonify, session
from flask_login import login_required, current_user
from flask import current_app
import hmac
import hashlib
import base64
import urllib.parse
from datetime import datetime
from models.user import User

discourse_bp = Blueprint('discourse', __name__)

DISCOURSE_SSO_URL = "https://forum.tjmtr.world/session/sso_login"

@discourse_bp.route('/login')
@login_required
def login():
    """处理 Discourse SSO 登录请求"""
    sso = request.args.get('sso')
    sig = request.args.get('sig')

    # 验证参数
    if not sso or not sig:
        return "错误: 缺少 SSO 参数", 400

    # 验证签名
    if not validate_signature(sso, sig):
        return "错误: 无效的 SSO 签名", 400

    # 解析 SSO 参数
    decoded_sso = base64.b64decode(sso).decode()
    params = dict(urllib.parse.parse_qsl(decoded_sso))
    session["nonce"] = params.get("nonce")  # 存储 nonce

    return render_template('oauth/forum_login.html', sso=sso, sig=sig)

def validate_signature(sso, sig):
    """验证 SSO 签名"""
    computed_sig = hmac.new(current_app.config['DISCOUESE_SSO_KEY'].encode(), sso.encode(), hashlib.sha256).hexdigest()
    return computed_sig == sig

@discourse_bp.route('/authenticate', methods=['POST'])
def authenticate():
    """用户提交的认证信息（用户名）"""
    username = current_user.username

    # 从数据库中查找用户
    user = User.query.filter_by(username=username).first()
    if not user:
        return "错误: 用户不存在", 400

    nonce = session.get("nonce")
    if not nonce:
        return "错误: 无效的请求", 400

    # 用户数据准备
    user_data = {
        "nonce": nonce,
        "external_id": user.id,
        "email": user.email,
        "username": user.username,
        "avatar_url": user.avatar_url,  # 用户头像 URL
    }

    # 编码用户数据为 URL 格式
    payload = urllib.parse.urlencode(user_data)
    encoded_payload = base64.b64encode(payload.encode()).decode()

    # 生成签名
    sig = hmac.new(current_app.config['DISCOUESE_SSO_KEY'].encode(), encoded_payload.encode(), hashlib.sha256).hexdigest()

    # 重定向回 Discourse 完成 SSO 登录
    discourse_redirect_url = f"{DISCOURSE_SSO_URL}?sso={encoded_payload}&sig={sig}"
    return redirect(discourse_redirect_url)
