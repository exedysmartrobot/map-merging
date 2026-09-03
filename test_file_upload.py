"""
/ForwardCustomFiles の切り分け用スタンドアロンスクリプト。
Flaskアプリを介さず、READMEの「Python --ファイル送信有り--」サンプルにほぼそのまま
実際のROBOT_ID/auth_config.jsonを差し込んで実行する。

使い方:
    python3 test_file_upload.py

期待する結果:
  - 200 が返り、復号後に media_id 等が確認できれば → ファイルAPI自体は正常に使える
    （このアプリ側のmaps保存の実装をさらに見直す）
  - 401 "Unauthorized"（本文が平文）が出れば → アプリのコードではなく、
    /ForwardCustomFiles 側のアクセス許可・契約設定の問題である可能性が高い
    （Exedy側にこのテナント/ロボットでファイルAPIが有効か確認してもらう）
"""
import os
import time
import traceback

import requests
from dotenv import load_dotenv

from common import load_json
from module.RobotControl import encrypt, decrypt

load_dotenv()

auth_config = load_json("auth_config.json")

CUSTOMER_HOST = os.getenv("CUSTOMER_HOST")
CUSTOMER_URL_FILES = os.getenv("CUSTOMER_URL_FILES") or (os.getenv("CUSTOMER_URL") + "Files")
ROBOT_ID = os.getenv("ROBOT_ID", "1")

# まずは maps より単純な /media（画像/動画登録）で切り分ける。
# 1x1の白いPNGをその場で作る。
import struct
import zlib


def _make_1x1_png() -> bytes:
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw = b"\x00\xff\xff\xff"  # filter byte + 1px RGB(white)
    idat = zlib.compress(raw)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def main():
    timestamp = int(time.time())
    api_url = f"/v1/robots/{ROBOT_ID}/media"

    data = {
        "UserID": auth_config["userID"],
        "Password": auth_config["password"],
        "TenantCD": auth_config["tenantCD"],
        "Timestamp": timestamp,
        "OPKey": auth_config["OPKey"],
        "APIRequestData": {
            "APIUrl": api_url,
            "Method": "POST",
            "APIBody": {},
        },
    }

    print(f"[test] CUSTOMER_HOST      = {CUSTOMER_HOST}")
    print(f"[test] CUSTOMER_URL_FILES = {CUSTOMER_URL_FILES}")
    print(f"[test] ROBOT_ID           = {ROBOT_ID}")
    print(f"[test] APIUrl             = {api_url}")

    try:
        encrypts: dict = encrypt(**data)
        if encrypts["Status"] != 0:
            print("[test] encrypt失敗:", encrypts)
            return
        encrypt_data: str = encrypts["Result"]

        post_url = CUSTOMER_HOST + CUSTOMER_URL_FILES
        form_data = {"formdata": encrypt_data}
        files = {"file": ("test.png", _make_1x1_png(), "image/png")}

        resp = requests.post(post_url, data=form_data, files=files, timeout=60)
        print(f"[test] HTTP status: {resp.status_code}")
        print(f"[test] body (先頭1000文字): {resp.text[:1000]}")

        if resp.status_code == 200:
            decrypts = decrypt(
                OPKey=auth_config["OPKey"],
                Timestamp=timestamp,
                EncryptedHttpPayload=resp.content,
            )
            print(f"[test] decrypt結果: {decrypts}")

    except Exception:
        print(traceback.format_exc())


if __name__ == "__main__":
    main()
