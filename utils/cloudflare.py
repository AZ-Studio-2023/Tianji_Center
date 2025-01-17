import requests
from flask import current_app

def verify_cloudflare(token):
    if not token:
        return False
        
    response = requests.post(
        'https://challenges.cloudflare.com/turnstile/v0/siteverify',
        data={
            'secret': current_app.config['CLOUDFLARE_SECRET_KEY'],
            'response': token
        }
    )
    
    return response.json()['success'] 