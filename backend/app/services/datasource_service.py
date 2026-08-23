"""数据源管理服务。"""
from __future__ import annotations

import base64
import hashlib
import os
import uuid

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import create_engine

from app.core.config import settings
from app.core.database import get_connection


def _get_fernet_key() -> bytes:
    """从 settings.secret_key 派生 Fernet 密钥 (sha256 + base64 urlsafe)。"""
    digest = hashlib.sha256(settings.secret_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_password(password: str) -> str:
    """加密密码。"""
    if not password:
        return ""
    f = Fernet(_get_fernet_key())
    return f.encrypt(password.encode()).decode()


def decrypt_password(encrypted: str) -> str:
    """解密密码。"""
    if not encrypted:
        return ""
    f = Fernet(_get_fernet_key())
    try:
        return f.decrypt(encrypted.encode()).decode()
    except InvalidToken:
        return ""


def build_db_url(datasource_dict: dict) -> str:
    """根据数据源信息构建 SQLAlchemy URL。"""
    ds_type = datasource_dict.get("type", "sqlite")
    host = datasource_dict.get("host", "")
    port = datasource_dict.get("port")
    database = datasource_dict.get("database", "")
    username = datasource_dict.get("username", "")
    password = datasource_dict.get("password", "") or datasource_dict.get("_password", "")

    if ds_type == "sqlite":
        if database == ":memory:":
            return "sqlite:///:memory:"
        return f"sqlite:///{database}"

    # 其他数据库类型 (mysql, postgresql 等)
    user_part = ""
    if username:
        if password:
            user_part = f"{username}:{password}@"
        else:
            user_part = f"{username}@"

    host_part = host or "localhost"
    if port:
        host_part = f"{host_part}:{port}"

    return f"{ds_type}://{user_part}{host_part}/{database}"


def _row_to_dict(row, include_password: bool = False) -> dict:
    result = {
        "id": row["id"],
        "project_id": row["project_id"],
        "name": row["name"],
        "type": row["type"],
        "host": row["host"] or "",
        "port": row["port"],
        "database": row["database"] or "",
        "username": row["username"] or "",
        "schema_file": row["schema_file"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if include_password:
        result["_password"] = decrypt_password(row["password_encrypted"] or "")
    return result


def _generate_short_id() -> str:
    return uuid.uuid4().hex[:8]


def list_datasources(project_id: str) -> list[dict]:
    """列出项目下的所有数据源（不含密码）。"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM datasources WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        )
        rows = cursor.fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_datasource(datasource_id: str, include_password: bool = False) -> dict | None:
    """根据 ID 获取数据源。"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM datasources WHERE id = ?", (datasource_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return _row_to_dict(row, include_password=include_password)
    finally:
        conn.close()


def create_datasource(
    project_id: str,
    name: str,
    ds_type: str,
    host: str = "",
    port: int | None = None,
    database: str = "",
    username: str = "",
    password: str = "",
) -> dict:
    """创建数据源。

    如果同一个项目下已存在完全相同的数据源
    （type/host/port/database/username/password 全部一致），
    则返回已有数据源，不重复创建。
    """
    # 先检查是否已存在相同的数据源
    existing = _find_duplicate_datasource(
        project_id=project_id,
        ds_type=ds_type,
        host=host,
        port=port,
        database=database,
        username=username,
        password=password,
    )
    if existing:
        return existing

    ds_id = _generate_short_id()
    encrypted_pw = encrypt_password(password)

    schema_file = os.path.join(settings.schemas_dir, project_id, f"{ds_id}.yaml")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO datasources
               (id, project_id, name, type, host, port, database, username, password_encrypted, schema_file)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ds_id,
                project_id,
                name,
                ds_type,
                host,
                port,
                database,
                username,
                encrypted_pw,
                schema_file,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    result = get_datasource(ds_id)
    assert result is not None
    return result


def _find_duplicate_datasource(
    project_id: str,
    ds_type: str,
    host: str = "",
    port: int | None = None,
    database: str = "",
    username: str = "",
    password: str = "",
) -> dict | None:
    """查找是否已有相同的数据源（所有连接参数一致）。

    通过逐条比对密码来判断（因为密码是加密存储的，不能直接 SQL 比较）。
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT * FROM datasources
               WHERE project_id = ?
                 AND type = ?
                 AND COALESCE(host, '') = ?
                 AND COALESCE(port, 0) = COALESCE(?, 0)
                 AND COALESCE(database, '') = ?
                 AND COALESCE(username, '') = ?
               ORDER BY created_at ASC
               LIMIT 10""",
            (project_id, ds_type, host, port, database, username),
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    # 逐条验证密码
    for row in rows:
        encrypted = row["password_encrypted"] or ""
        decrypted = decrypt_password(encrypted)
        if decrypted == password:
            return _row_to_dict(row)

    return None


def update_datasource(datasource_id: str, **kwargs) -> dict | None:
    """更新数据源信息。"""
    existing = get_datasource(datasource_id, include_password=True)
    if existing is None:
        return None

    # 收集需要更新的字段
    fields = {}
    if "name" in kwargs and kwargs["name"] is not None:
        fields["name"] = kwargs["name"]
    if "host" in kwargs and kwargs["host"] is not None:
        fields["host"] = kwargs["host"]
    if "port" in kwargs and kwargs["port"] is not None:
        fields["port"] = kwargs["port"]
    if "database" in kwargs and kwargs["database"] is not None:
        fields["database"] = kwargs["database"]
    if "username" in kwargs and kwargs["username"] is not None:
        fields["username"] = kwargs["username"]
    if "password" in kwargs and kwargs["password"] is not None:
        fields["password_encrypted"] = encrypt_password(kwargs["password"])

    if not fields:
        return existing

    set_clause = ", ".join([f"{k} = ?" for k in fields])
    set_clause += ", updated_at = CURRENT_TIMESTAMP"
    values = list(fields.values())
    values.append(datasource_id)

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE datasources SET {set_clause} WHERE id = ?",
            values,
        )
        conn.commit()
    finally:
        conn.close()

    return get_datasource(datasource_id)


def delete_datasource(datasource_id: str) -> bool:
    """删除数据源。"""
    existing = get_datasource(datasource_id)
    if existing is None:
        return False

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM datasources WHERE id = ?", (datasource_id,))
        conn.commit()
    finally:
        conn.close()

    return True


def test_connection_by_id(datasource_id: str) -> tuple[bool, str]:
    """测试数据源连接。"""
    ds = get_datasource(datasource_id, include_password=True)
    if ds is None:
        return False, "Datasource not found"

    db_url = build_db_url(ds)
    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            # 简单的 ping 查询
            conn.exec_driver_sql("SELECT 1")
        return True, "Connection successful"
    except Exception as e:
        return False, str(e)
