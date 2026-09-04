"""
ロボットクラウドAPIクライアント（認証なし版）

これまでは暗号化プロキシ（ForwardCustom / ForwardCustomFiles）経由で
UserID/Password/TenantCD/OPKey を暗号化して送るやり方だったが、
そちらは使わず、ロボットAPI（https://exedy-robo.com）へ直接アクセスする。
認証は HTTPヘッダー "API-key" を付けるだけ。

app.py 側からの呼び出し方（api_get(robot_id, api_name) / api_post(robot_id, api_name, file, body)）
と戻り値の形（成功時: JSON文字列 / 失敗時: {"error": ...} の辞書）は変えていないので、
app.py 側の変更は不要。
"""

import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

# ロボットAPIの直接エンドポイント（swagger: servers: - url: https://exedy-robo.com）
DIRECT_API_HOST = os.getenv("DIRECT_API_HOST", "https://exedy-robo.com")
# 認証ヘッダー。.envで API_KEY を指定すればそちらを優先し、未指定ならこの値を使う。
API_KEY = os.getenv("API_KEY", "sumagi1007")
DIRECT_HEADERS = {"API-key": API_KEY}

DEFAULT_TIMEOUT = 10
DEFAULT_TIMEOUT_FILE = 600  # ファイルアップロードは大きくなり得るので長めに


def _handle_response(resp, tag):
    """レスポンスを共通処理する。成功時はテキスト（JSON文字列）、失敗時は{"error": ...}を返す。"""
    if resp.status_code >= 400:
        body = resp.text[:1000]
        print(f"[{tag}] {resp.status_code} url={resp.url} body={body}")
        return {"error": f"{resp.status_code}: {body}"}
    return resp.text


def api_get(robot_id, api_name):
    """GET /v1/robots/{robot_id}/{api_name} を直接実行する"""
    url = f"{DIRECT_API_HOST}/v1/robots/{robot_id}/{api_name}"
    try:
        resp = requests.get(url, headers=DIRECT_HEADERS, timeout=DEFAULT_TIMEOUT)
        return _handle_response(resp, "api_get")
    except requests.exceptions.RequestException as e:
        print(f"[api_get] 通信エラー: {e}")
        return {"error": str(e)}


def api_get_path(path):
    """/v1/robots/{robot_id}/... の形に当てはまらない任意のパスへGETする"""
    url = f"{DIRECT_API_HOST}{path}"
    try:
        resp = requests.get(url, headers=DIRECT_HEADERS, timeout=DEFAULT_TIMEOUT)
        return _handle_response(resp, "api_get_path")
    except requests.exceptions.RequestException as e:
        print(f"[api_get_path] 通信エラー: {e}")
        return {"error": str(e)}


def get_route_list(map_id):
    resp = api_get_path(f"/s/routelist?map_id={map_id}")
    return json.loads(resp) if isinstance(resp, str) else resp


def api_post(robot_id, api_name, file, body=None):
    """
    POST /v1/robots/{robot_id}/{api_name} をmultipartで直接実行する。
    file: requestsのfiles=形式の辞書（実ファイル）
    body: ファイル以外の付随フィールド（例: {'name': '工場A'}）。
          multipartの通常フォームフィールドとしてそのまま送る。
    """
    url = f"{DIRECT_API_HOST}/v1/robots/{robot_id}/{api_name}"
    try:
        resp = requests.post(
            url, headers=DIRECT_HEADERS, data=(body or {}), files=file,
            timeout=DEFAULT_TIMEOUT_FILE,
        )
        return _handle_response(resp, "api_post")
    except requests.exceptions.RequestException as e:
        print(f"[api_post] 通信エラー: {e}")
        return {"error": str(e)}
