import requests
from flask import current_app
from models.user import Application
from models.user import User

def check_player_exists(lst, player_value):
    for d in lst:
        if "player" in d and d["player"] == player_value:
            return True
    return False

def get_time_by_player(lst, player_value):
    for d in lst:
        if "player" in d and d["player"] == player_value:
            return d.get("time", "")  
    return "" 

def update_time_by_player(lst, player_value, new_time):
    for d in lst:
        if "player" in d and d["player"] == player_value:
            d["time"] = new_time  
            return True  
    return False 

def format_time(minutes):
    if minutes >= 1440: 
        hours = round(minutes / 60, 1)
        return f"{hours}小时"
    return f"{minutes}分钟"

def get_all():
    url = current_app.config['ONLINE_TIME_API_URL'] + "/query"
    data = requests.get(url, {"type": "all", "time": "all"})
    r_data = []
    if data.status_code == 200:
        data = data.json()
        approved_apps = Application.query.filter_by(
            form_type='player',
            status='approved'
        ).all()
        for i in approved_apps:
            if check_player_exists(data, i.content.get('player_name')): 
                user = User.query.filter_by(id=i.user_id).first()
                if user:
                    username = user.username
                    if not check_player_exists(r_data, username):
                        r_data.append({
                            "player": username,
                            "time": get_time_by_player(data, i.content.get('player_name')) 
                        })
                    else:
                        update_time_by_player(r_data, username, get_time_by_player(r_data, username)  + get_time_by_player(data, i.content.get('player_name')))
                else:
                    pass
            else:
                pass
    else:
        return []
    return r_data

def get_user(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        return "0分钟"
    apps = Application.query.filter_by(
        form_type='player',
        status='approved',
        user_id=user.id
    ).all()
    if not apps:
        return "0分钟"
    t = 0
    for app in apps:
        if app.content.get('player_name'):
            player_name = app.content.get('player_name')
            url = current_app.config['ONLINE_TIME_API_URL'] + "/query"
            data = requests.get(url, {"type": "player", "time": "all", "player": str(player_name)})
            if data.status_code == 200:
                data = data.json()
                t = t + data.get("time", 0)
    return t
                

    


    