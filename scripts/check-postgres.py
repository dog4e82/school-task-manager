"""Verify real PostgreSQL persistence in an isolated, disposable test schema."""

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from cryptography.fernet import Fernet
from dotenv import dotenv_values
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import postgres_storage
from postgres_storage import Connection, PostgresCache
from web_store import Store


def main():
    dsn = os.environ.get("MOA_TEST_DATABASE_URL") or dotenv_values(ROOT / ".env",encoding="utf-8-sig").get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL 미설정: 실제 PostgreSQL 검증은 아직 실행되지 않았습니다.")
        return 2
    schema = "moa_probe_"+uuid4().hex
    key = Fernet.generate_key()
    checks = []
    def check(name, passed):
        if not passed:
            raise AssertionError(name)
        checks.append(name)
    try:
        with patch.object(postgres_storage,"SCHEMA",schema), TemporaryDirectory() as directory:
            store = Store(Path(directory),key,dsn)
            user = store.save_user("probe-a","a@example.invalid","test a",{"token":"synthetic-probe-token"})
            other = store.save_user("probe-b","b@example.invalid","test b",{"token":"synthetic-probe-token-b"})
            token = store.create_session(user)
            check("session_owner",store.session(token)["user_id"]==user)
            with store.db() as db:
                raw = db.execute("SELECT credentials FROM users WHERE id=?",(user,)).fetchone()[0]
            check("credentials_encrypted",b"synthetic-probe-token" not in bytes(raw))
            store.save_snapshot(user,{"synthetic":True})
            check("snapshot_owner",store.snapshot(other) is None)
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(lambda patch:store.save_personal(user,"task",patch),[{"note":"test"},{"completed":True}]))
            check("concurrent_record_merge",store.personal(user)["task"]=={"note":"test","completed":True})
            state,binding = store.begin_oauth({"synthetic":True})
            with ThreadPoolExecutor(max_workers=2) as pool:
                values=list(pool.map(lambda _:store.consume_oauth(state,binding),range(2)))
            check("oauth_state_one_use",sum(value is not None for value in values)==1)
            def reserve(owner):
                try:
                    return store.new_job(owner,"analyze","2099-01-01",limit=2,daily_limit=3,global_limit=3)
                except ValueError as error:
                    if str(error)!="global_limit":
                        raise
                    return None
            with ThreadPoolExecutor(max_workers=2) as pool:
                reservations=list(pool.map(reserve,[user,other]))
            check("atomic_global_budget",sum(value is not None for value in reservations)==1)
            store.recover_jobs()
            cache=PostgresCache(dsn)
            job={"key":"synthetic-cache-key","post":{"course_id":"c","source":"announcement","id":"p"}}
            check("cache_claim_once",cache.claim(job,"test-model") and not cache.claim(job,"test-model"))
            cache.finish(job["key"],"success",{"items":[],"relations":[]})
            cache.close()
            reader=PostgresCache(dsn,readonly=True)
            reader.preload([job["key"]])
            check("persistent_analysis_cache",reader.get(job["key"])["status"]=="success")
            check("batch_cache_does_not_include_other_keys",reader.get("unrequested-key") is None)
            reader.close()
            reopened=Store(Path(directory)/"new-empty-instance",key,dsn)
            check("survives_empty_local_filesystem",reopened.snapshot(user)=={"synthetic":True} and reopened.personal(user)["task"]["completed"])
            reopened.delete_user(user)
            check("account_deletion",reopened.get_user(user) is None and reopened.snapshot(user) is None and not reopened.personal(user))
        print(json.dumps({"postgres_checks_passed":len(checks),"checks":checks,"real_google_login_verified":False},ensure_ascii=False))
        return 0
    except Exception as error:
        print("PostgreSQL 검증 실패: "+type(error).__name__+". 연결 문자열·응답 본문은 출력하지 않습니다.")
        return 1
    finally:
        try:
            cleanup = Connection(dsn)
            try:
                with cleanup:
                    cleanup.raw.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
            finally:
                cleanup.close()
        except Exception:
            print("임시 검증 스키마 정리가 완료되지 않았습니다: "+schema)


if __name__ == "__main__":
    raise SystemExit(main())
