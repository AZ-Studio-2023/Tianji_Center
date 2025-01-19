import requests
from flask import current_app
import hmac

def verify_geetest(data):
    if not data:
        return False
    api_server = 'http://gcaptcha4.geetest.com'
    lot_number = data["lot_number"]
    captcha_output = data["captcha_output"]
    pass_token = data["pass_token"]
    gen_time = data["gen_time"]
    captcha_id = current_app.config['GEETEST_ID']
    captcha_key = current_app.config['GEETEST_SECRET_KEY']
    lotnumber_bytes = lot_number.encode()
    prikey_bytes = captcha_key.encode()
    sign_token = hmac.new(prikey_bytes, lotnumber_bytes, digestmod='SHA256').hexdigest()

    query = {
        "lot_number": lot_number,
        "captcha_output": captcha_output,
        "pass_token": pass_token,
        "gen_time": gen_time,
        "sign_token": sign_token,
    }
    print(query)
    url = api_server + '/validate' + '?captcha_id={}'.format(captcha_id)
    try:
        response = requests.post(url, query)
        print(response.json())
    except requests.RequestException:
        return False
    try:
        if response.json()["result"] == "success":
            return True
    except:
        return False
    return False