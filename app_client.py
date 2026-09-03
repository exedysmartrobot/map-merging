import requests
import json
import time
import traceback
import os
from dotenv import load_dotenv
from common import load_json

from module.RobotControl import encrypt, decrypt

load_dotenv()


auth_config = load_json("auth_config.json")
# print(auth_config)

CUSTOMER_HOST = os.getenv("CUSTOMER_HOST")
CUSTOMER_URL = os.getenv("CUSTOMER_URL")
# ファイルアップロード時は /ForwardCustom ではなく /ForwardCustomFiles を使う
# （READMEのカスタムアプリファイルAPI仕様）。.envで明示指定できるようにしつつ、
# 未指定ならCUSTOMER_URLに "Files" を付けたものをデフォルトにする。
CUSTOMER_URL_FILES = os.getenv("CUSTOMER_URL_FILES") or ((CUSTOMER_URL + "Files") if CUSTOMER_URL else None)
customer_headers = {
    "Content-Type": "application/json"
}


def main_api_client(robot_id, api_name, post_data):
    print(robot_id, api_name, post_data)
    try:
        # POST
        post_response = api_client_post(robot_id, api_name, post_data)
        print(post_response)
        post_response_data = json.loads(post_response)

        # service_idを取得
        service_id = post_response_data.get('service_id', None)
        print(f"servie_id: {service_id}")

        while True:
            # GET
            get_response = api_client_get(robot_id, api_name, service_id)
            get_response_data = json.loads(get_response)
            status = get_response_data.get('status')
            print(f"status: {status}")

            if status == 'SUCCEEDED':
                return get_response_data
            elif status in ['PREEMPTING', 'ABORTED', 'REJECTED', 'PREEMPTED', 'TIMEOUT']:
                # raise RuntimeError(f"失敗しました 状態：{status}")
                return get_response_data
            else:
                time.sleep(0.05)

    except Exception as e:
        print(f"Error occurred during test: {e}")
        return {"status": "ERROR", "error": str(e)}


def api_client_post(robot_id, api_name, post_data):
    timestamp = int(time.time())
    data = {
        'UserID': auth_config['userID'],
        'Password': auth_config['password'],
        'TenantCD': auth_config['tenantCD'],
        'Timestamp': timestamp,
        'OPKey': auth_config['OPKey'],
        'APIRequestData': {
            'APIUrl': f"/v1/robots/{robot_id}/service/{api_name}",
            'Method': 'POST',
            'APIBody': post_data
        }
    }
    post_auth_data = auth(data, timestamp)
    return post_auth_data


def api_client_get(robot_id, api_name, service_id):
    timestamp = int(time.time())
    data = {
        'UserID': auth_config['userID'],
        'Password': auth_config['password'],
        'TenantCD': auth_config['tenantCD'],
        'Timestamp': timestamp,
        'OPKey': auth_config['OPKey'],
        'APIRequestData': {
            'APIUrl': f"/v1/robots/{robot_id}/service/{api_name}?service_id={service_id}",
            'Method': 'GET',
            'APIBody': {}
        }
    }
    get_auth_data = auth(data, timestamp)
    return get_auth_data


def api_get(robot_id, api_name):
    timestamp = int(time.time())
    data = {
        'UserID': auth_config['userID'],
        'Password': auth_config['password'],
        'TenantCD': auth_config['tenantCD'],
        'Timestamp': timestamp,
        'OPKey': auth_config['OPKey'],
        'APIRequestData': {
            'APIUrl': f"/v1/robots/{robot_id}/{api_name}",
            'Method': 'GET',
            'APIBody': {}
        }
    }
    get_auth_data = auth(data, timestamp)
    return get_auth_data


def api_get_path(path):
    """/v1/robots/{robot_id}/... の形に当てはまらない任意のパスへGETする"""
    timestamp = int(time.time())
    data = {
        'UserID': auth_config['userID'],
        'Password': auth_config['password'],
        'TenantCD': auth_config['tenantCD'],
        'Timestamp': timestamp,
        'OPKey': auth_config['OPKey'],
        'APIRequestData': {
            'APIUrl': path,
            'Method': 'GET',
            'APIBody': {}
        }
    }
    get_auth_data = auth(data, timestamp)
    return get_auth_data


def get_route_list(map_id):
    resp = api_get_path(f"/s/routelist?map_id={map_id}")
    return json.loads(resp) if isinstance(resp, str) else resp


def api_post(robot_id, api_name, file, body=None):
    """
    body: ファイル以外の付随フィールド（例: {'name': '工場A'}）。
    READMEのファイルAPIサンプル同様、APIBodyにファイル以外の値をそのまま渡す。
    実ファイルはfile（requestsのfiles=形式）で別途送る。
    """
    timestamp = int(time.time())
    data = {
        'UserID': auth_config['userID'],
        'Password': auth_config['password'],
        'TenantCD': auth_config['tenantCD'],
        'Timestamp': timestamp,
        'OPKey': auth_config['OPKey'],
        'APIRequestData': {
            'APIUrl': f"/v1/robots/{robot_id}/{api_name}",
            'Method': 'POST',
            'APIBody': body if body is not None else {}
        }
    }
    get_auth_data = auth_file(data, timestamp, file)
    print(get_auth_data)
    return get_auth_data

# def auth(data, timestamp):
#     try:
#         # APIリクエストペイロードの作成
#         encrypts: dict = encrypt(**data)
#         if encrypts['Status'] != 0:
#             # print (encrypts['Result'])
#             raise ValueError('The argument is invalid')

#         encrypt_data: str = encrypts['Result']

#         # カスタムアプリAPIへリクエスト送信
#         post_url = CUSTOMER_HOST + customer_url
#         post_json_data = encrypt_data
#         DEFAULT_TIMEOUT = 60

#         resp: requests.Response = requests.post(
#             post_url, headers=customer_headers, data=post_json_data, timeout=DEFAULT_TIMEOUT)

#         if resp.status_code == 500:
#             raise ValueError('Internal Server Error')

#         status = resp.status_code
#         response = resp.content
#         # print(f'Status:{status}, response:{response}')

#         if status == 401:
#             print(str(status)+' Unauthorized')
#             raise ValueError(str(status)+' Unauthorized')

#         # APIレスポンスペイロードの復号
#         decrypt_data = {
#             'OPKey': auth_config['OPKey'],
#             'Timestamp': timestamp,
#             'EncryptedHttpPayload': response
#         }
#         decrypts: dict = decrypt(**decrypt_data)
#         # print(f"Status: {decrypts['Status']}, Result: {decrypts['Result']}")
#         return decrypts['Result']

#     except Exception as e:
#         print(traceback.format_exc())


def auth(data, timestamp, max_retry=60, retry_wait=2):
    try:
        # APIリクエストペイロードの作成
        encrypts: dict = encrypt(**data)
        if encrypts['Status'] != 0:
            raise ValueError('The argument is invalid')

        encrypt_data: str = encrypts['Result']
        post_url = CUSTOMER_HOST + CUSTOMER_URL
        post_json_data = encrypt_data
        DEFAULT_TIMEOUT = 10

        retry_count = 0
        while True:
            try:
                resp: requests.Response = requests.post(
                    post_url, headers=customer_headers, data=post_json_data, timeout=DEFAULT_TIMEOUT)
                if resp.status_code == 500:
                    print(f"[auth] 500 Internal Server Error body: {resp.text[:1000]}")
                    raise ValueError('Internal Server Error')
                if resp.status_code == 401:
                    print(f"[auth] 401 Unauthorized body: {resp.text[:1000]}")
                    raise ValueError(str(resp.status_code)+' Unauthorized')
                # 成功時はループを抜ける
                break
            except requests.exceptions.RequestException as e:
                retry_count += 1
                print(f"[auth] 通信エラー発生。リトライ {retry_count}/{max_retry}: {e}")
                if retry_count >= max_retry:
                    print("[auth] リトライ上限に達しました。例外を投げます。")
                    raise
                time.sleep(retry_wait)  # リトライ前に待つ

        status = resp.status_code
        response = resp.content
        # print(f'Status:{status}, response:{response}')

        # APIレスポンスペイロードの復号
        decrypt_data = {
            'OPKey': auth_config['OPKey'],
            'Timestamp': timestamp,
            'EncryptedHttpPayload': response
        }
        decrypts: dict = decrypt(**decrypt_data)
        return decrypts['Result']

    except Exception as e:
        print(traceback.format_exc())
        return {"error": str(e)}


def auth_file(data, timestamp, file, max_retry=5, retry_wait=2):
    try:
        # APIリクエストペイロードの作成
        encrypts: dict = encrypt(**data)
        if encrypts['Status'] != 0:
            raise ValueError('The argument is invalid')

        encrypt_data: str = encrypts['Result']
        # ファイルAPI（/ForwardCustomFiles）は通常API（/ForwardCustom）と別エンドポイントで、
        # 暗号化ペイロードは 'formdata' というフィールド名でfilesと一緒にmultipart送信する
        # （README「カスタムアプリファイルAPI」仕様）。Content-Typeも自動生成させるため
        # customer_headers（application/json固定）は渡さない。
        post_url = CUSTOMER_HOST + CUSTOMER_URL_FILES
        post_json_data = {'formdata': encrypt_data}
        DEFAULT_TIMEOUT = 600

        retry_count = 0
        while True:
            try:
                resp: requests.Response = requests.post(
                    post_url, data=post_json_data, files=file, timeout=DEFAULT_TIMEOUT)
                if resp.status_code == 500:
                    print(f"[auth_file] 500 Internal Server Error body: {resp.text[:1000]}")
                    raise ValueError('Internal Server Error')
                if resp.status_code == 401:
                    print(f"[auth_file] 401 Unauthorized body: {resp.text[:1000]}")
                    print(f"[auth_file] request url: {post_url}")
                    raise ValueError(str(resp.status_code)+' Unauthorized')
                # 成功時はループを抜ける
                break
            except requests.exceptions.RequestException as e:
                retry_count += 1
                print(f"[auth] 通信エラー発生。リトライ {retry_count}/{max_retry}: {e}")
                if retry_count >= max_retry:
                    print("[auth] リトライ上限に達しました。例外を投げます。")
                    raise
                time.sleep(retry_wait)  # リトライ前に待つ

        status = resp.status_code
        response = resp.content
        # print(f'Status:{status}, response:{response}')

        # APIレスポンスペイロードの復号
        decrypt_data = {
            'OPKey': auth_config['OPKey'],
            'Timestamp': timestamp,
            'EncryptedHttpPayload': response
        }
        decrypts: dict = decrypt(**decrypt_data)
        return decrypts['Result']

    except Exception as e:
        print(traceback.format_exc())
        return {"error": str(e)}
