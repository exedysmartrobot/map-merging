"""
古いバックアップを削除するスクリプト（cronで毎日実行する想定）。
created_at から7日を過ぎた backups レコードを削除する。
方式2（画像もDB内）なので、レコードを消せば画像も一緒に消える。
"""

import os
import sqlite3
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_DB = os.path.join(BASE_DIR, "backups.db")

# 保持期間（日数）。7日より古いものを削除する。
RETENTION_DAYS = 7


def main():
    if not os.path.exists(BACKUP_DB):
        print(f"[cleanup] DBが見つかりません: {BACKUP_DB}")
        return

    cutoff = (datetime.now() - timedelta(days=RETENTION_DAYS)).isoformat(timespec="seconds")

    conn = sqlite3.connect(BACKUP_DB)
    # 消える件数を先に数える（ログ用）
    cur = conn.execute("SELECT COUNT(*) FROM backups WHERE created_at < ?", (cutoff,))
    count = cur.fetchone()[0]

    conn.execute("DELETE FROM backups WHERE created_at < ?", (cutoff,))
    conn.commit()

    # 削除で空いた領域を実際に解放してDBファイルを縮める
    conn.execute("VACUUM")
    conn.close()

    stamp = datetime.now().isoformat(timespec="seconds")
    print(f"[cleanup] {stamp} : {count}件のバックアップを削除しました（{cutoff} より古いもの）")


if __name__ == "__main__":
    main()
