"""
マップ合成アプリ サーバー（Flask）

役割:
  1. 今のHTMLアプリ(static/index.html)を配信
  2. 地図APIを app_client.py 経由で代理呼び出し（認証はサーバー内に隠す）
  3. 地図画像を「同一オリジン」で代理配信（canvas汚染の回避 & EXIF取得のため）
  4. 合体PNGにベースのEXIFを入れ直して返す（キャンバス書き出しでEXIFが消えるため）

前提:
  - 同じフォルダに app_client.py / common.py / module/RobotControl.py / auth_config.json があること
  - .env に CUSTOMER_HOST, CUSTOMER_URL, ROBOT_ID を設定すること
  - pip install flask pillow requests python-dotenv
"""

from app_client import api_get, api_post
import io
import os
import json
import requests
from flask import Flask, request, jsonify, render_template, send_file, send_from_directory, abort
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

# あなたの既存の認証クライアントをそのまま利用する
#   api_get(robot_id, api_name)         -> GET  を暗号化経由で実行し、復号済みResultを返す
#   api_post(robot_id, api_name, file)  -> POST(ファイル) を実行

app = Flask(__name__, static_folder=None)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
ROBOT_ID = os.getenv("ROBOT_ID", "1")


# ------------------------------------------------------------------
# 画面配信
# ------------------------------------------------------------------


@app.route("/")
def index():
    return render_template("index.html")


@app.get("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(STATIC_DIR, filename)


# ------------------------------------------------------------------
# 地図一覧: GET /api/maps?robot_id=1
#   app_client.api_get(robot_id, "maps") の戻りを整形して返す
# ------------------------------------------------------------------
@app.get("/api/maps")
def list_maps():
    robot_id = request.args.get("robot_id", ROBOT_ID)
    try:
        result = api_get(robot_id, "maps")
        # api_get は復号済みの文字列 or dict を返す実装なので両対応にしておく
        if isinstance(result, (bytes, str)):
            result = json.loads(result)
    except Exception as e:
        return jsonify({"error": f"地図一覧の取得に失敗: {e}"}), 502

    if not isinstance(result, dict):
        return jsonify({"error": "予期しない応答形式", "raw": str(result)[:500]}), 502

    maps = result.get("maps", [])
    # フロントで使いやすい形に絞って返す
    slim = [{
        "map_id": m.get("map_id"),
        "name": m.get("name"),
        "image": m.get("image"),               # 進入禁止エリア用PNGのURL
        "static_image": m.get("static_image"),  # 自己位置補正用PNGのURL
        "meta": m.get("map_meta_data"),
        "created_at": m.get("created_at"),
        "updated_at": m.get("updated_at"),
    } for m in maps]
    return jsonify({"robot_id": robot_id, "maps": slim})


def _find_map(robot_id, map_id):
    """一覧から1件を引く（画像URLを得るため）"""
    result = api_get(robot_id, "maps")
    if isinstance(result, (bytes, str)):
        result = json.loads(result)
    for m in result.get("maps", []):
        if str(m.get("map_id")) == str(map_id):
            return m
    return None


def _fetch_png_bytes(url):
    """画像URLをサーバー側で取得してPNGバイト列を返す。
    ※このURLに認証が要るかは環境依存。まずは素で取得を試し、
      ダメなら分かるようにエラーを返す（必要なら認証を足す）。"""
    resp = requests.get(url, timeout=30)
    if resp.status_code == 200:
        return resp.content
    raise RuntimeError(f"画像取得に失敗 status={resp.status_code} url={url}")


# ------------------------------------------------------------------
# 地図画像の代理配信: GET /api/maps/<map_id>/image?robot_id=1&kind=image|static
#   同一オリジンでPNGを返すので、ブラウザのcanvasが汚染されない
# ------------------------------------------------------------------
@app.get("/api/maps/<map_id>/image")
def map_image(map_id):
    robot_id = request.args.get("robot_id", ROBOT_ID)
    kind = request.args.get("kind", "image")  # "image"(既定) or "static"
    try:
        m = _find_map(robot_id, map_id)
        if not m:
            abort(404, description="map_id が見つかりません")
        url = m.get("static_image") if kind == "static" else m.get("image")
        if not url:
            abort(404, description="画像URLがありません")
        png = _fetch_png_bytes(url)
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    return send_file(io.BytesIO(png), mimetype="image/png",
                     download_name=f"{map_id}.png")


# ------------------------------------------------------------------
# ローカルアップロード取り込み: POST /api/upload  (multipart: file)
#   ブラウザから選んだPNGをそのまま返す（エディタに読み込む用）。
#   EXIF付きのまま返すので、あとでベースEXIFとして使える。
#   ※クラウドへ登録したい場合は register=1 を付けて robot cloud にも上げる。
# ------------------------------------------------------------------
@app.post("/api/upload")
def upload():
    if "file" not in request.files:
        return jsonify({"error": "file がありません"}), 400
    f = request.files["file"]
    data = f.read()

    register = request.form.get("register") == "1"
    if register:
        robot_id = request.form.get("robot_id", ROBOT_ID)
        try:
            # あなたの maps アップロードAPIへ（multipart）
            files = {"file": (f.filename, data, "image/png")}
            api_post(robot_id, "maps", files)
        except Exception as e:
            return jsonify({"error": f"クラウド登録に失敗: {e}"}), 502

    return send_file(io.BytesIO(data), mimetype="image/png",
                     download_name=f.filename or "upload.png")


# ------------------------------------------------------------------
# 合体 + EXIF注入: POST /api/merge
#   multipart:
#     merged        : キャンバスから書き出した合体PNG（必須）
#     base_map_id   : ベースがクラウド地図ならその map_id（EXIF元をサーバーが再取得）
#     base_original : ベースがローカルアップロードならその元PNG（EXIF元）
#     exif_kind     : "image"(既定, 進入禁止エリア用) or "static"(自己位置補正用)
#                     base_map_id からEXIF元を再取得する際、どちらの画像を使うか
#     robot_id      : 任意
#     reset_orientation : "1" なら Orientation を無回転(1)に上書き（回転編集した場合の安全策）
#   戻り: EXIFを入れ直した合体PNG
#
#   map.png と static_map.png を両方合成する場合は、この /api/merge を
#   2回呼ぶ想定（1回目 exif_kind=image、2回目 exif_kind=static）。
# ------------------------------------------------------------------
@app.post("/api/merge")
def merge():
    if "merged" not in request.files:
        return jsonify({"error": "merged がありません"}), 400
    merged_bytes = request.files["merged"].read()

    robot_id = request.form.get("robot_id", ROBOT_ID)
    base_map_id = request.form.get("base_map_id")
    exif_kind = request.form.get("exif_kind", "image")  # "image" or "static"
    reset_orientation = request.form.get("reset_orientation") == "1"

    # --- ベースのEXIFを入手（クラウド地図 or ローカル元画像のどちらか） ---
    # base_exif_bytes: 元画像が持っていた生のEXIFバイト列（無加工）。
    # base_exif_pil  : PILのExifオブジェクト（reset_orientationでタグを書き換える場合のみ使用）。
    #
    # 注意: PILの Image.getexif().tobytes() は、ExifIFDPointer（サブIFDへのオフセット参照）
    # を含むEXIFを正しく再構築できず、壊れたバイナリを生成することがある
    # （実機検証で、これが原因でクラウド保存APIから401が返る不具合を確認済み）。
    # そのため、タグ書き換えが不要な通常時は img.info["exif"] の生バイト列をそのまま使う。
    base_exif_bytes = None
    base_exif_pil = None
    try:
        if "base_original" in request.files:
            base_png = request.files["base_original"].read()
            base_img = Image.open(io.BytesIO(base_png))
            base_exif_bytes = base_img.info.get("exif")
            base_exif_pil = base_img.getexif()
        elif base_map_id:
            m = _find_map(robot_id, base_map_id)
            url = m.get("static_image") if exif_kind == "static" else m.get("image") if m else None
            if url:
                base_png = _fetch_png_bytes(url)
                base_img = Image.open(io.BytesIO(base_png))
                base_exif_bytes = base_img.info.get("exif")
                base_exif_pil = base_img.getexif()
    except Exception as e:
        # EXIFが取れなくても合体PNG自体は返す（メタ無しで）
        print(f"[merge] EXIF取得に失敗（メタ無しで続行）: {e}")

    # --- 合体PNGにEXIFを入れ直して出力 ---
    out = io.BytesIO()
    img = Image.open(io.BytesIO(merged_bytes))
    if reset_orientation and base_exif_pil is not None and len(base_exif_pil):
        # Orientationタグを上書きする必要がある場合だけ、PILの再構成経由にする
        base_exif_pil[0x0112] = 1  # Orientation=無回転（回転編集済みの場合の安全策）
        img.save(out, format="PNG", exif=base_exif_pil.tobytes())
    elif base_exif_bytes:
        img.save(out, format="PNG", exif=base_exif_bytes)
    else:
        img.save(out, format="PNG")
    out.seek(0)
    return send_file(out, mimetype="image/png", download_name="merged-map.png")


# ------------------------------------------------------------------
# 合体PNGをクラウドの地図としてAPI経由で保存: POST /api/maps/save
#   multipart:
#     mode          : "new"(新規) or "overwrite"(上書き)
#     name          : mode=new のとき必須（地図名）
#     map_id        : mode=overwrite のとき必須（上書き対象。ベースマップのmap_idを渡す）
#     image         : map.png（進入禁止エリア用）の合体PNG。あれば送る
#     static_image  : static_map.png（自己位置補正用）の合体PNG。あれば送る
#     robot_id      : 任意
#
#   実APIは POST /v1/robots/{robot_id}/maps （新規） /
#           POST /v1/robots/{robot_id}/maps/{map_id} （上書き）
#   にmultipartでフィールド名 file / static_file(新規) / statis_file(上書き ※原文ママの綴り) / name
#   を渡す仕様（swagger準拠）。
# ------------------------------------------------------------------
@app.post("/api/maps/save")
def save_map():
    mode = request.form.get("mode")
    if mode not in ("new", "overwrite"):
        return jsonify({"error": "mode は 'new' か 'overwrite' を指定してください"}), 400

    robot_id = request.form.get("robot_id", ROBOT_ID)

    files = {}
    if "image" in request.files:
        f = request.files["image"]
        files["file"] = (f.filename or "map.png", f.read(), "image/png")
    if "static_image" in request.files:
        f = request.files["static_image"]
        # swagger上は上書き側だけ "statis_file"(タイポ)になっているが、実機検証の結果
        # 実際のAPIは新規・上書きとも "static_file" を見ているため、常にこちらを使う。
        files["static_file"] = (f.filename or "static_map.png", f.read(), "image/png")

    if not files:
        return jsonify({"error": "保存する画像がありません"}), 400

    try:
        if mode == "new":
            name = (request.form.get("name") or "").strip()
            if not name:
                return jsonify({"error": "新規保存には地図名が必要です"}), 400
            # ファイル以外の値（name）はAPIBody側で渡す（READMEのファイルAPIサンプル準拠）
            result = api_post(robot_id, "maps", files, body={"name": name})
        else:
            map_id = (request.form.get("map_id") or "").strip()
            if not map_id:
                return jsonify({"error": "上書き保存には map_id が必要です"}), 400
            result = api_post(robot_id, f"maps/{map_id}", files)
    except Exception as e:
        return jsonify({"error": f"保存に失敗しました: {e}"}), 502

    if result is None:
        return jsonify({"error": "保存に失敗しました（クラウドAPIからの応答がありません）"}), 502
    if isinstance(result, (bytes, str)):
        try:
            result = json.loads(result)
        except Exception:
            pass
    if isinstance(result, dict) and result.get("error"):
        return jsonify({"error": result["error"]}), 502

    return jsonify({"ok": True, "result": result})


# if __name__ == "__main__":
#     # ローカル開発用。0.0.0.0 にすると同一LANの別端末からも見える
#     app.run(host="127.0.0.1", port=5000, debug=True)

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
