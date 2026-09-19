import os
import glob
import sqlite3

def check_tiktok_session():
    cookie_files = glob.glob('video-output/tiktok_session/**/Cookies', recursive=True)
    print("Found cookie files:", cookie_files)
    for cp in cookie_files:
        try:
            conn = sqlite3.connect(f"file:{os.path.abspath(cp)}?immutable=1", uri=True)
            cur = conn.cursor()
            cur.execute("SELECT name, host_key FROM cookies WHERE host_key LIKE '%tiktok.com%'")
            rows = cur.fetchall()
            print(f"Total tiktok cookies in {cp}: {len(rows)}")
            names = [r[0] for r in rows]
            print("Cookie names:", names[:20])
            conn.close()
        except Exception as exc:
            print(f"Error {cp}: {exc}")

if __name__ == '__main__':
    check_tiktok_session()
