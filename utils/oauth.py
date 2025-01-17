import requests
from flask import current_app, url_for

class QQOAuth:
    def get_auth_url(self, redirect_uri=None):
        if redirect_uri is None:
            redirect_uri = url_for('auth.oauth_callback', provider='qq', _external=True)
            
        params = {
            'act': 'login',
            'appid': current_app.config['QQ_APP_ID'],
            'appkey': current_app.config['QQ_APP_KEY'],
            'type': 'qq',
            'redirect_uri': redirect_uri
        }
        try:
            response = requests.get('https://u.v8jisu.cn/connect.php', params=params)
            response_data = response.json()
            
            if 'url' not in response_data:
                error_msg = response_data.get('msg', '获取QQ登录地址失败')
                raise Exception(error_msg)
                
            return response_data['url']
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"请求QQ OAuth服务失败: {str(e)}")
        except ValueError as e:
            raise Exception(f"解析QQ OAuth响应失败: {str(e)}")
        except Exception as e:
            raise Exception(f"QQ OAuth错误: {str(e)}")

    def get_user_info(self, code):
        params = {
            'act': 'callback',
            'appid': current_app.config['QQ_APP_ID'],
            'appkey': current_app.config['QQ_APP_KEY'],
            'type': 'qq',
            'code': code
        }
        try:
            response = requests.get('https://u.v8jisu.cn/connect.php', params=params)
            response_data = response.json()

            if 'social_uid' not in response_data:
                error_msg = response_data.get('msg', '获取QQ用户信息失败')
                raise Exception(error_msg)
                
            return response_data
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"请求QQ用户信息失败: {str(e)}")
        except ValueError as e:
            raise Exception(f"解析QQ用户信息响应失败: {str(e)}")
        except Exception as e:
            raise Exception(f"获取QQ用户信息错误: {str(e)}")

class WeChatOAuth:
    def get_auth_url(self):
        params = {
            'act': 'login',
            'appid': current_app.config['WECHAT_APP_ID'],
            'appkey': current_app.config['WECHAT_APP_KEY'],
            'type': 'wx',
            'redirect_uri': url_for('auth.oauth_callback', provider='wechat', _external=True)
        }
        response = requests.get('https://u.v8jisu.cn/connect.php', params=params)
        return response.json()['url']

    def get_user_info(self, code):
        params = {
            'act': 'callback',
            'appid': current_app.config['WECHAT_APP_ID'],
            'appkey': current_app.config['WECHAT_APP_KEY'],
            'type': 'wx',
            'code': code
        }
        response = requests.get('https://u.v8jisu.cn/connect.php', params=params)
        return response.json()

class GithubOAuth:
    def get_auth_url(self):
        params = {
            'client_id': current_app.config['GITHUB_CLIENT_ID'],
            'redirect_uri': url_for('auth.oauth_callback', provider='github', _external=True),
            'scope': 'read:user user:email',
            'state': 'github'
        }
        return f"https://github.com/login/oauth/authorize?{'&'.join(f'{k}={v}' for k, v in params.items())}"

    def get_user_info(self, code):
        # 1. 获取访问令牌
        token_response = requests.post(
            'https://github.com/login/oauth/access_token',
            data={
                'client_id': current_app.config['GITHUB_CLIENT_ID'],
                'client_secret': current_app.config['GITHUB_CLIENT_SECRET'],
                'code': code
            },
            headers={'Accept': 'application/json'}
        )
        access_token = token_response.json()['access_token']
        
        # 2. 获取用户信息
        user_response = requests.get(
            'https://api.github.com/user',
            headers={
                'Authorization': f'token {access_token}',
                'Accept': 'application/json'
            }
        )
        user_info = user_response.json()
        
        # 3. 转换为统一格式
        return {
            'social_uid': str(user_info['id']),
            'nickname': user_info['login'],
            'faceimg': user_info['avatar_url']
        }

    def get_user_info_by_id(self, user_id):
        # GitHub的用户信息可以直接通过API获取
        user_response = requests.get(
            f'https://api.github.com/user/{user_id}',
            headers={
                'Accept': 'application/json',
                'Authorization': f'token {current_app.config["GITHUB_CLIENT_SECRET"]}'
            }
        )
        user_info = user_response.json()
        return {
            'social_uid': str(user_info['id']),
            'nickname': user_info['login'],
            'faceimg': user_info['avatar_url']
        }

class MicrosoftOAuth:
    def get_auth_url(self):
        params = {
            'client_id': current_app.config['MICROSOFT_CLIENT_ID'],
            'response_type': 'code',
            'redirect_uri': url_for('auth.oauth_callback', provider='microsoft', _external=True),
            'scope': 'User.Read',
            'response_mode': 'query'
        }
        return f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?{'&'.join(f'{k}={v}' for k, v in params.items())}"

    def get_user_info(self, code):
        # 1. 获取访问令牌
        token_response = requests.post(
            'https://login.microsoftonline.com/common/oauth2/v2.0/token',
            data={
                'client_id': current_app.config['MICROSOFT_CLIENT_ID'],
                'client_secret': current_app.config['MICROSOFT_CLIENT_SECRET'],
                'code': code,
                'redirect_uri': url_for('auth.oauth_callback', provider='microsoft', _external=True),
                'grant_type': 'authorization_code'
            }
        )
        access_token = token_response.json()['access_token']
        
        # 2. 获取用户信息
        user_response = requests.get(
            'https://graph.microsoft.com/v1.0/me',
            headers={
                'Authorization': f'Bearer {access_token}',
                'Accept': 'application/json'
            }
        )
        user_info = user_response.json()
        
        # 3. 转换为统一格式
        return {
            'social_uid': user_info['id'],
            'nickname': user_info['displayName'],
            'faceimg': f"https://graph.microsoft.com/v1.0/me/photo/$value"  # 需要单独请求
        }

    def get_user_info_by_id(self, user_id):
        # Microsoft需要先获取访问令牌
        token_response = requests.post(
            'https://login.microsoftonline.com/common/oauth2/v2.0/token',
            data={
                'client_id': current_app.config['MICROSOFT_CLIENT_ID'],
                'client_secret': current_app.config['MICROSOFT_CLIENT_SECRET'],
                'grant_type': 'client_credentials',
                'scope': 'https://graph.microsoft.com/.default'
            }
        )
        access_token = token_response.json()['access_token']
        
        # 然后获取用户信息
        user_response = requests.get(
            f'https://graph.microsoft.com/v1.0/users/{user_id}',
            headers={
                'Authorization': f'Bearer {access_token}',
                'Accept': 'application/json'
            }
        )
        user_info = user_response.json()
        return {
            'social_uid': user_info['id'],
            'nickname': user_info['displayName'],
            'faceimg': f"https://graph.microsoft.com/v1.0/users/{user_id}/photo/$value"
        }

# 初始化OAuth实例
qq_oauth = QQOAuth()
wechat_oauth = WeChatOAuth()
github_oauth = GithubOAuth()
microsoft_oauth = MicrosoftOAuth() 