import os
import base64
import json
import requests
import boto3
from datetime import datetime
from PIL import Image

LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
GYAZO_ACCESS_TOKEN = os.getenv('GYAZO_ACCESS_TOKEN')
table = boto3.resource('dynamodb').Table('dalle3-test')

def dalle3_create(prompt):
    api_url = 'https://api.openai.com/v1/images/generations'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {OPENAI_API_KEY}'
    }
    data = {
        'prompt': prompt,
        'model': 'dall-e-3',
        'n': 1,
        'quality': 'standard',
        'response_format': 'b64_json',
        'size': '1024x1024',
        'style': 'vivid'
    }
    res = requests.post(api_url, headers=headers, data=json.dumps(data))
    res = json.loads(res.text)
    return res

def userName(userId):
    url = f'https://api.line.me/v2/bot/profile/{userId}'
    headers = {'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}'}
    res = requests.get(url, headers=headers)
    user_name = json.loads(res.text)['displayName']
    return user_name

def bytes2image(res, userId, text):
    origin_name = '/tmp/'+str(res['created'])+'.webp'
    data = res['data'][0]['b64_json']
    prompt = res['data'][0]['revised_prompt']
    img = base64.b64decode(data.encode())
    with open(origin_name, 'wb') as f:
        f.write(img)
    img = Image.open(origin_name).convert('RGB')
    name = '/tmp/'+str(res['created'])+'.png'
    img.save(name, 'png')
    os.remove(origin_name)
    user_name = userName(userId)
    table.put_item(
        Item={
            'user_id': userId,
            'user_name': user_name,
            'timestamp': res['created'],
            'user_prompt': text,
            'revised_prompt': prompt
        }
    )
    return name

def gyazo_upload(origin_name):
    api_url = 'https://upload.gyazo.com/api/upload'
    data = {
        'access_token': GYAZO_ACCESS_TOKEN,
        'app': 'Gyazo',
        'title': os.path.basename(origin_name)
    }
    files = {
        'imagedata': open(origin_name, 'rb')
    }
    res = requests.post(api_url, data=data, files=files)
    url = json.loads(res.text)['url']
    return url

def send_image(userId, img, t):
    api_url = 'https://api.line.me/v2/bot/message/push'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}'
    }
    data = {
        'to': userId,
        'messages': [
            {
                'type': 'text',
                'text': '生成に掛かった時間: ' + str(t) +'秒'
            },
            {
                'type': 'image',
                'originalContentUrl': img,
                'previewImageUrl': img
            }
        ]
    }
    requests.post(api_url, headers=headers, data=json.dumps(data))

def send_message(userId, text):
    api_url = 'https://api.line.me/v2/bot/message/push'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}'
    }
    data = {
        'to': userId,
        'messages': [
            {
                'type': 'text',
                'text': text
            }
        ]
    }
    requests.post(api_url, headers=headers, data=json.dumps(data))

def lambda_handler(event, context):
    event = json.loads(event['body'])
    text = event['events'][0]['message']['text']
    userId = event['events'][0]['source']['userId']
    print(userId)
    try:
        send_message(userId, text='〜生成中〜')
        s = datetime.now().timestamp()
        res = dalle3_create(text)
        print(res)
        ok_json = {"isBase64Encoded": False,
                "statusCode": 200,
                "headers": {},
                "body": ""}
        if 'data' in res:
            name = bytes2image(res, userId, text)
            url = gyazo_upload(name)
            e = datetime.now().timestamp()
            t = e - s
            send_image(userId, url, int(t))
            os.remove(name)
            return ok_json
        elif 'error' in res:
            text = '安全性の低い指示文を検出したためエラーが発生しました。\n指示文を変えて送り直してください。'
            send_message(userId, text)
            return ok_json
    except Exception as e:
        error_json = {"isBase64Encoded": False,
                    "statusCode": 500,
                    "headers": {},
                    "body": "Error"}
        send_message(userId, text='エラーが発生しました。')
        print(f'{e.__class__.__name__}: {e}')
        return error_json