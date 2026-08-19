# Phase 2: FastAPI 后端服务 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 nl2sql 核心库之上构建 FastAPI 后端服务，提供 REST API + SSE 流式接口，支持项目管理、数据源管理、Schema 自动导入、会话管理、生成日志。

**Architecture:** FastAPI 作为 Web 层，围绕 nl2sql 核心库做薄封装。每个项目对应一个 Agent 实例池，会话管理用内存存储（V1），生成日志用 SQLite。SSE 流式推送 Agent 每一步进展。

**Tech Stack:** FastAPI, Uvicorn, Pydantic, SQLite (生成日志), python-multipart

---

## 文件结构总览

```
backend/
├── app/
│   ├── main.py                    # FastAPI 入口
│   ├── core/
│   │   ├── config.py              # 应用配置
│   │   └── database.py            # SQLite 连接
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py                # 依赖注入
│   │   ├── projects.py            # 项目管理接口
│   │   ├── datasources.py         # 数据源管理接口
│   │   ├── schema.py              # Schema 接口
│   │   ├── sessions.py            # 会话管理接口
│   │   ├── chat.py                # 聊天接口
│   │   └── stream.py              # SSE 流
│   └── services/
│       ├── __init__.py
│       ├── project_service.py     # 项目服务
│       ├── datasource_service.py  # 数据源服务
│       ├── schema_service.py      # Schema 服务
│       ├── session_service.py     # 会话服务
│       ├── chat_service.py        # 聊天/Agent 运行服务
│       ├── generation_log.py      # 生成日志服务
│       └── schema_import.py       # Schema 自动导入服务
├── data/
│   └── nl2sql.db                  # SQLite 数据库
└── ... (核心库文件已在 Phase 1 创建)
```

---

## Task 1: FastAPI 项目脚手架 + 配置

**Files:**
- Modify: `backend/pyproject.toml` (加依赖)
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/core/database.py`
- Create: `backend/app/api/__init__.py`

- [ ] **Step 1: 更新 pyproject.toml 加 FastAPI 依赖**

在 `dependencies` 中添加：
```toml
dependencies = [
    # ... 已有依赖 ...
    "fastapi>=0.110",
    "uvicorn>=0.27",
    "python-multipart>=0.0.9",
    "aiosqlite>=0.20",
    "pydantic-settings>=2.0",
    "cryptography>=42.0",
]
```

- [ ] **Step 2: 创建 app/core/config.py**

```python
"""FastAPI 应用配置。"""
from __future__ import annotations

from pydantic_settings import BaseSettings


class AppSettings(BaseSettings):
    """应用级配置。"""
    app_name: str = "NL2SQL Agent"
    debug: bool = False

    # 数据目录
    data_dir: str = "data"
    projects_dir: str = "config/projects"
    schemas_dir: str = "config/schemas"

    # 数据库
    database_url: str = "sqlite:///data/nl2sql.db"

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Agent
    agent_max_iterations: int = 5
    agent_max_probe_iterations: int = 3
    agent_timeout_seconds: int = 300

    class Config:
        env_file = ".env"
        env_prefix = "APP_"


settings = AppSettings()
```

- [ ] **Step 3: 创建 app/core/database.py**

```python
"""SQLite 数据库连接与初始化。"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .config import settings


def get_db_path() -> str:
    """获取数据库文件路径。"""
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "nl2sql.db")


def init_db() -> None:
    """初始化数据库表结构。"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 生成日志表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS generation_logs (
            id TEXT PRIMARY KEY,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            project_id TEXT NOT NULL,
            datasource_id TEXT,
            session_id TEXT,
            user_query TEXT,
            generated_sql TEXT,
            intent_summary TEXT,
            execution_success INTEGER,
            execution_time_ms REAL,
            row_count INTEGER,
            error_message TEXT,
            iteration INTEGER,
            reflection_notes TEXT,
            user_feedback TEXT,
            model TEXT,
            final_selected INTEGER DEFAULT 0
        )
    """)

    # 会话表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            title TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 消息表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT,
            sql_text TEXT,
            result_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)

    # 数据源表（加密存储连接信息）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS datasources (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            host TEXT,
            port INTEGER,
            database TEXT,
            username TEXT,
            password_encrypted TEXT,
            connection_url_encrypted TEXT,
            schema_file TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 项目表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def get_connection() -> sqlite3.Connection:
    """获取数据库连接。"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn
```

- [ ] **Step 4: 创建 app/main.py**

```python
"""FastAPI 应用入口。"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings
from .core.database import init_db
from .api import router as api_router


def create_app() -> FastAPI:
    """创建 FastAPI 应用。"""
    app = FastAPI(
        title=settings.app_name,
        description="NL2SQL Agent API",
        version="0.1.0",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 初始化数据库
    init_db()

    # 注册路由
    app.include_router(api_router, prefix="/api")

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "app": settings.app_name}

    return app


app = create_app()
```

- [ ] **Step 5: 创建 app/api/__init__.py**

```python
"""API 路由聚合。"""
from fastapi import APIRouter

from .projects import router as projects_router
from .datasources import router as datasources_router
from .schema import router as schema_router
from .sessions import router as sessions_router
from .chat import router as chat_router

router = APIRouter()

router.include_router(projects_router, prefix="/projects", tags=["projects"])
router.include_router(datasources_router, prefix="/datasources", tags=["datasources"])
router.include_router(schema_router, prefix="/schema", tags=["schema"])
router.include_router(sessions_router, prefix="/sessions", tags=["sessions"])
router.include_router(chat_router, prefix="/chat", tags=["chat"])
```

注意：先导入占位，后续 task 会创建各个 router 文件。现在这些文件还不存在，所以先把 `__init__.py` 写得简单点——只声明 router，不导入子路由。等每个子路由创建好了再加。

改成：

```python
"""API 路由聚合。"""
from fastapi import APIRouter

router = APIRouter()

# 子路由在各自的 task 中注册
```

- [ ] **Step 6: 创建 app/__init__.py**

```python
"""FastAPI 后端应用。"""
```

- [ ] **Step 7: 验证启动**

Run: `cd backend && pip install fastapi uvicorn python-multipart aiosqlite cryptography`
Run: `cd backend && python -c "from app.main import app; print(app.title)"`
Expected: 输出 `NL2SQL Agent`

- [ ] **Step 8: Commit**

```bash
git add backend/pyproject.toml backend/app/__init__.py backend/app/main.py backend/app/core/config.py backend/app/core/database.py backend/app/api/__init__.py
git commit -m "feat: FastAPI backend scaffold with database init"
```

---

## Task 2: 项目管理 API

**Files:**
- Create: `backend/app/services/project_service.py`
- Create: `backend/app/api/projects.py`

- [ ] **Step 1: 实现项目服务**

```python
"""项目服务。"""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from ..core.database import get_connection
from ..core.config import settings


def _ensure_project_dir(project_id: str) -> None:
    """确保项目的配置目录存在。"""
    project_dir = Path(settings.schemas_dir) / project_id
    project_dir.mkdir(parents=True, exist_ok=True)


def list_projects() -> list[dict]:
    """获取所有项目列表。"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects ORDER BY updated_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_project(project_id: str) -> dict | None:
    """获取单个项目详情。"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def create_project(name: str, description: str = "") -> dict:
    """创建新项目。"""
    project_id = str(uuid.uuid4())[:8]  # 短 ID，方便使用
    now = datetime.now().isoformat()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO projects (id, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (project_id, name, description, now, now),
    )
    conn.commit()
    conn.close()

    # 创建项目目录
    _ensure_project_dir(project_id)

    return get_project(project_id)


def update_project(project_id: str, name: str | None = None, description: str | None = None) -> dict | None:
    """更新项目信息。"""
    project = get_project(project_id)
    if not project:
        return None

    new_name = name if name is not None else project["name"]
    new_desc = description if description is not None else project["description"]
    now = datetime.now().isoformat()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE projects SET name = ?, description = ?, updated_at = ? WHERE id = ?",
        (new_name, new_desc, now, project_id),
    )
    conn.commit()
    conn.close()

    return get_project(project_id)


def delete_project(project_id: str) -> bool:
    """删除项目。"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    cursor.execute("DELETE FROM datasources WHERE project_id = ?", (project_id,))
    cursor.execute("DELETE FROM sessions WHERE project_id = ?", (project_id,))
    conn.commit()
    affected = cursor.rowcount > 0
    conn.close()
    return affected
```

- [ ] **Step 2: 创建项目 API 路由**

```python
"""项目管理 API。"""
from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from ..services.project_service import (
    list_projects, get_project, create_project, update_project, delete_project,
)

router = APIRouter()


class ProjectCreate(BaseModel):
    name: str
    description: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


@router.get("")
async def get_projects():
    """获取项目列表。"""
    return {"projects": list_projects()}


@router.get("/{project_id}")
async def get_project_detail(project_id: str):
    """获取项目详情。"""
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("")
async def create_project_endpoint(data: ProjectCreate):
    """创建新项目。"""
    project = create_project(data.name, data.description)
    return project


@router.patch("/{project_id}")
async def update_project_endpoint(project_id: str, data: ProjectUpdate):
    """更新项目信息。"""
    project = update_project(project_id, data.name, data.description)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/{project_id}")
async def delete_project_endpoint(project_id: str):
    """删除项目。"""
    success = delete_project(project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"success": True}
```

- [ ] **Step 3: 注册项目路由到 api/__init__.py**

```python
"""API 路由聚合。"""
from fastapi import APIRouter

from .projects import router as projects_router

router = APIRouter()

router.include_router(projects_router, prefix="/projects", tags=["projects"])
```

- [ ] **Step 4: 验证 API**

Run: `cd backend && python -c "
from app.main import app
from fastapi.testclient import TestClient
client = TestClient(app)
r = client.post('/api/projects', json={'name': '测试项目', 'description': 'test'})
print('create:', r.status_code, r.json())
pid = r.json()['id']
r = client.get('/api/projects')
print('list:', r.status_code, len(r.json()['projects']))
r = client.get(f'/api/projects/{pid}')
print('get:', r.status_code, r.json()['name'])
"`
Expected: 全部 200，创建/列表/详情都正常

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/__init__.py backend/app/services/project_service.py backend/app/api/projects.py backend/app/api/__init__.py
git commit -m "feat: project management API"
```

注意：需要创建 `app/services/__init__.py`：
```python
"""业务服务层。"""
```

---

## Task 3: 数据源管理 + Schema 自动导入

**Files:**
- Create: `backend/app/services/datasource_service.py`
- Create: `backend/app/services/schema_import.py`
- Create: `backend/app/api/datasources.py`

- [ ] **Step 1: 实现数据源服务（含加密存储）**

```python
"""数据源服务。"""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from ..core.database import get_connection
from ..core.config import settings

# 简单的加密工具（V1 用 Fernet，后续可以升级）
from cryptography.fernet import Fernet
import base64
import hashlib


def _get_cipher() -> Fernet:
    """获取加密器（用 APP_SECRET_KEY 派生密钥）。"""
    # 从配置获取密钥，如果没有就用默认（V1 简化，生产环境应该配置）
    secret = getattr(settings, "secret_key", "nl2sql-default-secret-key-change-me")
    key = hashlib.sha256(secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_password(password: str) -> str:
    """加密密码。"""
    if not password:
        return ""
    cipher = _get_cipher()
    return cipher.encrypt(password.encode()).decode()


def decrypt_password(encrypted: str) -> str:
    """解密密码。"""
    if not encrypted:
        return ""
    try:
        cipher = _get_cipher()
        return cipher.decrypt(encrypted.encode()).decode()
    except Exception:
        return ""


def build_db_url(datasource: dict) -> str:
    """根据数据源信息构建数据库连接 URL。"""
    ds_type = datasource["type"]
    host = datasource.get("host", "localhost")
    port = datasource.get("port")
    database = datasource.get("database", "")
    username = datasource.get("username", "")
    password = decrypt_password(datasource.get("password_encrypted", ""))

    # 默认端口
    default_ports = {
        "mysql": 3306,
        "postgres": 5432,
        "clickhouse": 8123,
        "sqlite": 0,
    }
    if not port:
        port = default_ports.get(ds_type, 3306)

    if ds_type == "sqlite":
        return f"sqlite:///{database}"

    # SQLAlchemy 格式
    driver_map = {
        "mysql": "mysql+pymysql",
        "postgres": "postgresql",
        "clickhouse": "clickhouse+native",
    }
    driver = driver_map.get(ds_type, ds_type)

    auth = f"{username}:{password}@" if username else ""
    port_str = f":{port}" if port else ""
    return f"{driver}://{auth}{host}{port_str}/{database}"


def list_datasources(project_id: str) -> list[dict]:
    """获取项目的数据源列表（不含密码）。"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, project_id, name, type, host, port, database, username, schema_file, created_at, updated_at "
        "FROM datasources WHERE project_id = ? ORDER BY created_at",
        (project_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_datasource(datasource_id: str, include_password: bool = False) -> dict | None:
    """获取单个数据源。"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM datasources WHERE id = ?", (datasource_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    data = dict(row)
    if not include_password:
        data.pop("password_encrypted", None)
        data.pop("connection_url_encrypted", None)
    return data


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
    """创建数据源。"""
    ds_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()

    encrypted_pw = encrypt_password(password)
    schema_file = f"{settings.schemas_dir}/{project_id}/{ds_id}.yaml"

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO datasources
           (id, project_id, name, type, host, port, database, username, password_encrypted, schema_file, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ds_id, project_id, name, ds_type, host, port, database, username, encrypted_pw, schema_file, now, now),
    )
    conn.commit()
    conn.close()

    return get_datasource(ds_id)


def update_datasource(datasource_id: str, **kwargs) -> dict | None:
    """更新数据源。"""
    ds = get_datasource(datasource_id, include_password=True)
    if not ds:
        return None

    # 处理密码特殊字段
    if "password" in kwargs and kwargs["password"] is not None:
        kwargs["password_encrypted"] = encrypt_password(kwargs.pop("password"))

    now = datetime.now().isoformat()
    kwargs["updated_at"] = now

    set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
    values = list(kwargs.values()) + [datasource_id]

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE datasources SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()

    return get_datasource(datasource_id)


def delete_datasource(datasource_id: str) -> bool:
    """删除数据源。"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM datasources WHERE id = ?", (datasource_id,))
    conn.commit()
    affected = cursor.rowcount > 0
    conn.close()
    return affected


def test_connection_by_id(datasource_id: str) -> tuple[bool, str]:
    """测试数据源连接。"""
    ds = get_datasource(datasource_id, include_password=True)
    if not ds:
        return False, "数据源不存在"

    db_url = build_db_url(ds)
    try:
        from nl2sql.executor import create_executor
        executor = create_executor(
            datasource_id=ds["id"],
            datasource_type=ds["type"],
            db_url=db_url,
            timeout_seconds=10,
            max_rows=1,
        )
        success = executor.test_connection()
        return success, "" if success else "连接测试失败"
    except Exception as e:
        return False, str(e)
```

- [ ] **Step 2: 实现 Schema 自动导入服务**

```python
"""Schema 自动导入服务。

从实际数据库读取 schema 信息，生成 YAML 元数据文件。
"""
from __future__ import annotations

import yaml
from pathlib import Path
from sqlalchemy import create_engine, text, inspect

from ..core.config import settings
from .datasource_service import get_datasource, build_db_url, update_datasource


def import_schema_from_database(datasource_id: str, use_llm: bool = False) -> dict:
    """从数据库导入 schema，生成 YAML 文件。

    Args:
        datasource_id: 数据源 ID
        use_llm: 是否用 LLM 生成中文描述（V1 可选，默认关闭）

    Returns:
        导入结果 {success, table_count, tables: [...]}
    """
    ds = get_datasource(datasource_id, include_password=True)
    if not ds:
        return {"success": False, "error": "数据源不存在", "table_count": 0, "tables": []}

    db_url = build_db_url(ds)

    try:
        engine = create_engine(db_url)
        inspector = inspect(engine)
    except Exception as e:
        return {"success": False, "error": f"连接数据库失败: {e}", "table_count": 0, "tables": []}

    tables_data = []
    table_names = inspector.get_table_names()

    for table_name in table_names:
        # 获取列信息
        columns_info = inspector.get_columns(table_name)
        # 获取主键
        pk_info = inspector.get_pk_constraint(table_name)
        pk_columns = set(pk_info.get("constrained_columns", []))
        # 获取外键
        fk_info = inspector.get_foreign_keys(table_name)
        fk_map = {}
        for fk in fk_info:
            for col in fk.get("constrained_columns", []):
                fk_map[col] = {
                    "table": fk.get("referred_table", ""),
                    "column": fk.get("referred_columns", [""])[0] if fk.get("referred_columns") else "",
                }
        # 获取表注释
        try:
            table_comment = inspector.get_table_comment(table_name)
            table_desc = table_comment.get("text", "") or ""
        except Exception:
            table_desc = ""

        columns = []
        for col in columns_info:
            col_name = col["name"]
            col_type = str(col["type"])
            col_comment = col.get("comment", "") or ""
            is_pk = col_name in pk_columns
            is_fk = col_name in fk_map

            col_data = {
                "name": col_name,
                "type": col_type,
                "description": col_comment,
                "is_primary_key": is_pk,
            }
            if is_fk:
                col_data["is_foreign_key"] = True
                col_data["foreign_key_table"] = fk_map[col_name]["table"]
                col_data["foreign_key_column"] = fk_map[col_name]["column"]

            # 简单推断语义类型
            col_lower = col_name.lower()
            type_lower = col_type.lower()
            if "time" in col_lower or "date" in col_lower or "datetime" in type_lower or "timestamp" in type_lower:
                col_data["semantic_type"] = "timestamp"
            elif "id" == col_lower or col_lower.endswith("_id") or is_pk or is_fk:
                col_data["semantic_type"] = "id"
            elif "amount" in col_lower or "price" in col_lower or "total" in col_lower or "decimal" in type_lower:
                col_data["semantic_type"] = "amount"
            elif "status" in col_lower or "type" in col_lower or "gender" in col_lower:
                col_data["semantic_type"] = "category"

            columns.append(col_data)

        table_data = {
            "name": table_name,
            "description": table_desc or f"{table_name} 表",
            "columns": columns,
        }
        tables_data.append(table_data)

    # 生成 YAML
    yaml_data = {
        "datasource": {
            "id": ds["id"],
            "name": ds["name"],
            "type": ds["type"],
        },
        "tables": tables_data,
    }

    # 写入文件
    schema_file_path = Path(ds["schema_file"])
    schema_file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(schema_file_path, "w", encoding="utf-8") as f:
        yaml.dump(yaml_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # 更新数据源记录
    update_datasource(datasource_id, schema_file=str(schema_file_path))

    engine.dispose()

    return {
        "success": True,
        "table_count": len(tables_data),
        "tables": [{"name": t["name"], "column_count": len(t["columns"])} for t in tables_data],
    }
```

- [ ] **Step 3: 实现数据源 API 路由**

```python
"""数据源管理 API。"""
from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from ..services.datasource_service import (
    list_datasources, get_datasource, create_datasource,
    update_datasource, delete_datasource, test_connection_by_id,
)
from ..services.schema_import import import_schema_from_database

router = APIRouter()


class DatasourceCreate(BaseModel):
    project_id: str
    name: str
    type: str  # mysql / postgres / clickhouse / sqlite
    host: str = ""
    port: int | None = None
    database: str = ""
    username: str = ""
    password: str = ""


class DatasourceUpdate(BaseModel):
    name: str | None = None
    host: str | None = None
    port: int | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None


class TestConnectionRequest(BaseModel):
    type: str
    host: str = ""
    port: int | None = None
    database: str = ""
    username: str = ""
    password: str = ""


@router.get("")
async def get_datasources(project_id: str):
    """获取项目的数据源列表。"""
    return {"datasources": list_datasources(project_id)}


@router.get("/{datasource_id}")
async def get_datasource_detail(datasource_id: str):
    """获取数据源详情。"""
    ds = get_datasource(datasource_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Datasource not found")
    return ds


@router.post("")
async def create_datasource_endpoint(data: DatasourceCreate):
    """创建数据源。"""
    ds = create_datasource(
        project_id=data.project_id,
        name=data.name,
        ds_type=data.type,
        host=data.host,
        port=data.port,
        database=data.database,
        username=data.username,
        password=data.password,
    )
    return ds


@router.patch("/{datasource_id}")
async def update_datasource_endpoint(datasource_id: str, data: DatasourceUpdate):
    """更新数据源。"""
    update_data = data.model_dump(exclude_none=True)
    ds = update_datasource(datasource_id, **update_data)
    if not ds:
        raise HTTPException(status_code=404, detail="Datasource not found")
    return ds


@router.delete("/{datasource_id}")
async def delete_datasource_endpoint(datasource_id: str):
    """删除数据源。"""
    success = delete_datasource(datasource_id)
    if not success:
        raise HTTPException(status_code=404, detail="Datasource not found")
    return {"success": True}


@router.post("/{datasource_id}/test-connection")
async def test_connection(datasource_id: str):
    """测试数据源连接。"""
    success, error = test_connection_by_id(datasource_id)
    return {"success": success, "error": error}


@router.post("/{datasource_id}/import-schema")
async def import_schema(datasource_id: str, use_llm: bool = False):
    """从数据库导入 Schema。"""
    result = import_schema_from_database(datasource_id, use_llm=use_llm)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "导入失败"))
    return result
```

- [ ] **Step 4: 注册数据源路由**

在 `app/api/__init__.py` 中添加：
```python
from .datasources import router as datasources_router
router.include_router(datasources_router, prefix="/datasources", tags=["datasources"])
```

- [ ] **Step 5: 验证 API**

Run: `cd backend && python -c "
from app.main import app
from fastapi.testclient import TestClient
client = TestClient(app)
# 先创建项目
r = client.post('/api/projects', json={'name': '测试项目'})
pid = r.json()['id']
# 创建 SQLite 数据源
r = client.post('/api/datasources', json={
    'project_id': pid, 'name': 'SQLite测试', 'type': 'sqlite', 'database': ':memory:'
})
print('create ds:', r.status_code, r.json()['id'])
ds_id = r.json()['id']
# 测试连接
r = client.post(f'/api/datasources/{ds_id}/test-connection')
print('test conn:', r.json())
# 导入 schema
r = client.post(f'/api/datasources/{ds_id}/import-schema')
print('import:', r.json())
"`
Expected: 创建成功，连接测试成功，导入 0 张表（内存库没有表）

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/datasource_service.py backend/app/services/schema_import.py backend/app/api/datasources.py backend/app/api/__init__.py
git commit -m "feat: datasource management and schema auto-import"
```

---

## Task 4: Schema API + 会话管理

**Files:**
- Create: `backend/app/services/schema_service.py`
- Create: `backend/app/services/session_service.py`
- Create: `backend/app/api/schema.py`
- Create: `backend/app/api/sessions.py`

- [ ] **Step 1: Schema 服务**

```python
"""Schema 服务。"""
from __future__ import annotations

from pathlib import Path

from .datasource_service import list_datasources, get_datasource
from nl2sql.schema import SchemaLoader, DatasourceSchema


def get_project_schemas(project_id: str) -> list[dict]:
    """获取项目所有数据源的 Schema。"""
    datasources = list_datasources(project_id)
    loader = SchemaLoader()
    result = []

    for ds in datasources:
        schema_file = ds.get("schema_file", "")
        if schema_file and Path(schema_file).exists():
            try:
                ds_schema = loader.load_from_yaml(schema_file)
                result.append({
                    "datasource_id": ds["id"],
                    "datasource_name": ds["name"],
                    "datasource_type": ds["type"],
                    "tables": [
                        {"name": t.name, "description": t.description, "column_count": len(t.columns)}
                        for t in ds_schema.schema.tables
                    ],
                })
            except Exception as e:
                result.append({
                    "datasource_id": ds["id"],
                    "datasource_name": ds["name"],
                    "error": str(e),
                    "tables": [],
                })
        else:
            result.append({
                "datasource_id": ds["id"],
                "datasource_name": ds["name"],
                "tables": [],
                "note": "尚未导入 schema",
            })

    return result


def get_table_detail(datasource_id: str, table_name: str) -> dict | None:
    """获取单表详细信息。"""
    ds = get_datasource(datasource_id, include_password=False)
    if not ds:
        return None
    schema_file = ds.get("schema_file", "")
    if not schema_file or not Path(schema_file).exists():
        return None

    loader = SchemaLoader()
    ds_schema = loader.load_from_yaml(schema_file)
    table = ds_schema.schema.get_table(table_name)
    if not table:
        return None

    return {
        "name": table.name,
        "description": table.description,
        "columns": [
            {
                "name": c.name,
                "type": c.type,
                "description": c.description,
                "is_primary_key": c.is_primary_key,
                "is_foreign_key": c.is_foreign_key,
                "semantic_type": c.semantic_type,
                "enum_values": c.enum_values,
            }
            for c in table.columns
        ],
        "examples": table.examples,
    }


def load_datasource_schemas(project_id: str) -> list[DatasourceSchema]:
    """加载项目所有数据源的 Schema 对象（供 Agent 使用）。"""
    datasources = list_datasources(project_id)
    loader = SchemaLoader()
    result = []

    for ds in datasources:
        schema_file = ds.get("schema_file", "")
        if schema_file and Path(schema_file).exists():
            try:
                ds_schema = loader.load_from_yaml(schema_file)
                result.append(ds_schema)
            except Exception:
                pass

    return result
```

- [ ] **Step 2: 会话服务**

```python
"""会话服务。"""
from __future__ import annotations

import uuid
import json
from datetime import datetime

from ..core.database import get_connection


def list_sessions(project_id: str) -> list[dict]:
    """获取项目的会话列表。"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM sessions WHERE project_id = ? ORDER BY updated_at DESC",
        (project_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_session(session_id: str) -> dict | None:
    """获取会话详情。"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def create_session(project_id: str, title: str = "新对话") -> dict:
    """创建新会话。"""
    session_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO sessions (id, project_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, project_id, title, now, now),
    )
    conn.commit()
    conn.close()

    return get_session(session_id)


def update_session(session_id: str, title: str | None = None) -> dict | None:
    """更新会话。"""
    session = get_session(session_id)
    if not session:
        return None

    now = datetime.now().isoformat()
    new_title = title if title is not None else session["title"]

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
        (new_title, now, session_id),
    )
    conn.commit()
    conn.close()

    return get_session(session_id)


def delete_session(session_id: str) -> bool:
    """删除会话。"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    affected = cursor.rowcount > 0
    conn.close()
    return affected


def get_messages(session_id: str) -> list[dict]:
    """获取会话的所有消息。"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at",
        (session_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    messages = []
    for row in rows:
        msg = dict(row)
        # 解析 result_json
        if msg.get("result_json"):
            try:
                msg["result"] = json.loads(msg["result_json"])
            except json.JSONDecodeError:
                msg["result"] = None
        else:
            msg["result"] = None
        msg.pop("result_json", None)
        messages.append(msg)
    return messages


def add_message(
    session_id: str,
    role: str,
    content: str,
    sql_text: str | None = None,
    result: dict | None = None,
) -> dict:
    """添加消息。"""
    msg_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    result_json = json.dumps(result, ensure_ascii=False) if result else None

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO messages (id, session_id, role, content, sql_text, result_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (msg_id, session_id, role, content, sql_text, result_json, now),
    )
    # 更新会话的更新时间
    cursor.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
    conn.commit()
    conn.close()

    return {
        "id": msg_id,
        "session_id": session_id,
        "role": role,
        "content": content,
        "sql_text": sql_text,
        "result": result,
        "created_at": now,
    }


def update_session_title_from_query(session_id: str, query: str) -> None:
    """根据用户第一条消息自动生成会话标题。"""
    session = get_session(session_id)
    if not session:
        return
    # 如果还是默认标题，用查询的前 30 个字作为标题
    if session["title"] == "新对话" and query:
        title = query[:30] + ("..." if len(query) > 30 else "")
        update_session(session_id, title=title)
```

- [ ] **Step 3: Schema API**

```python
"""Schema API。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..services.schema_service import get_project_schemas, get_table_detail

router = APIRouter()


@router.get("")
async def get_schemas(project_id: str):
    """获取项目所有数据源的 Schema 概览。"""
    return {"datasources": get_project_schemas(project_id)}


@router.get("/table/{datasource_id}/{table_name}")
async def get_table(datasource_id: str, table_name: str):
    """获取单表详细信息。"""
    table = get_table_detail(datasource_id, table_name)
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    return table
```

- [ ] **Step 4: 会话 API**

```python
"""会话管理 API。"""
from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from ..services.session_service import (
    list_sessions, get_session, create_session, update_session, delete_session,
    get_messages,
)

router = APIRouter()


class SessionCreate(BaseModel):
    project_id: str
    title: str = "新对话"


class SessionUpdate(BaseModel):
    title: str | None = None


@router.get("")
async def get_sessions(project_id: str):
    """获取项目的会话列表。"""
    return {"sessions": list_sessions(project_id)}


@router.get("/{session_id}")
async def get_session_detail(session_id: str):
    """获取会话详情。"""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/{session_id}/messages")
async def get_session_messages(session_id: str):
    """获取会话的消息列表。"""
    messages = get_messages(session_id)
    return {"messages": messages}


@router.post("")
async def create_session_endpoint(data: SessionCreate):
    """创建新会话。"""
    session = create_session(data.project_id, data.title)
    return session


@router.patch("/{session_id}")
async def update_session_endpoint(session_id: str, data: SessionUpdate):
    """更新会话。"""
    session = update_session(session_id, data.title)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.delete("/{session_id}")
async def delete_session_endpoint(session_id: str):
    """删除会话。"""
    success = delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True}
```

- [ ] **Step 5: 注册路由**

更新 `app/api/__init__.py`，把 schema 和 sessions 路由加上。

- [ ] **Step 6: 验证**

Run: `cd backend && python -c "
from app.main import app
from fastapi.testclient import TestClient
client = TestClient(app)
r = client.post('/api/projects', json={'name': 'schema测试'})
pid = r.json()['id']
r = client.get(f'/api/schema?project_id={pid}')
print('schema list:', r.status_code)
r = client.post('/api/sessions', json={'project_id': pid, 'title': '测试会话'})
print('session:', r.status_code, r.json()['id'])
sid = r.json()['id']
r = client.get(f'/api/sessions/{sid}/messages')
print('messages:', r.status_code, len(r.json()['messages']))
"`
Expected: 全部 200

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/schema_service.py backend/app/services/session_service.py backend/app/api/schema.py backend/app/api/sessions.py backend/app/api/__init__.py
git commit -m "feat: schema API and session management"
```

---

## Task 5: 聊天服务 + SSE 流式接口

**Files:**
- Create: `backend/app/services/chat_service.py`
- Create: `backend/app/services/generation_log.py`
- Create: `backend/app/api/chat.py`

- [ ] **Step 1: 生成日志服务**

```python
"""生成日志服务。"""
from __future__ import annotations

import uuid
from datetime import datetime

from ..core.database import get_connection


def log_generation(
    project_id: str,
    datasource_id: str,
    session_id: str,
    user_query: str,
    generated_sql: str,
    intent_summary: str,
    execution_success: bool,
    execution_time_ms: float,
    row_count: int,
    error_message: str | None,
    iteration: int,
    reflection_notes: str,
    model: str,
    final_selected: bool = False,
) -> str:
    """记录一次 SQL 生成。"""
    log_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO generation_logs
           (id, timestamp, project_id, datasource_id, session_id, user_query,
            generated_sql, intent_summary, execution_success, execution_time_ms,
            row_count, error_message, iteration, reflection_notes, model, final_selected)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (log_id, now, project_id, datasource_id, session_id, user_query,
         generated_sql, intent_summary, 1 if execution_success else 0, execution_time_ms,
         row_count, error_message, iteration, reflection_notes, model, 1 if final_selected else 0),
    )
    conn.commit()
    conn.close()

    return log_id


def list_generation_logs(project_id: str, limit: int = 100) -> list[dict]:
    """获取项目的生成日志。"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM generation_logs WHERE project_id = ? ORDER BY timestamp DESC LIMIT ?",
        (project_id, limit),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]
```

- [ ] **Step 2: 聊天服务（核心：Agent 运行 + SSE 事件）**

```python
"""聊天服务。

负责管理 Agent 运行、事件收集、SSE 事件推送。
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator
from collections import defaultdict

from ..core.config import settings
from ..services.schema_service import load_datasource_schemas
from ..services.datasource_service import get_datasource, build_db_url
from ..services.session_service import (
    get_session, add_message, update_session_title_from_query,
)
from ..services.generation_log import log_generation
from nl2sql.agent import NL2SQLAgent
from nl2sql.executor import create_executor
from nl2sql.llm.message import Message, MessageRole


# 内存中的事件队列: {session_id: asyncio.Queue}
_event_queues: dict[str, asyncio.Queue] = {}
# 活跃的 Agent 任务
_active_tasks: dict[str, asyncio.Task] = {}


def _get_event_queue(session_id: str) -> asyncio.Queue:
    """获取会话的事件队列。"""
    if session_id not in _event_queues:
        _event_queues[session_id] = asyncio.Queue(maxsize=100)
    return _event_queues[session_id]


def _send_event(session_id: str, event_type: str, data: dict) -> None:
    """向会话的事件队列发送事件。"""
    queue = _get_event_queue(session_id)
    try:
        queue.put_nowait({"type": event_type, "data": data})
    except asyncio.QueueFull:
        pass  # 队列满了就丢，非关键事件


def _build_agent(project_id: str, session_id: str) -> NL2SQLAgent | None:
    """为项目构建 Agent 实例。"""
    # 加载 Schema
    datasource_schemas = load_datasource_schemas(project_id)
    if not datasource_schemas:
        return None

    # 构建执行器
    executors = {}
    for ds_schema in datasource_schemas:
        ds = get_datasource(ds_schema.datasource_id, include_password=True)
        if not ds:
            continue
        db_url = build_db_url(ds)
        try:
            executor = create_executor(
                datasource_id=ds["id"],
                datasource_type=ds["type"],
                db_url=db_url,
                timeout_seconds=settings.agent_timeout_seconds,
                max_rows=1000,
            )
            executors[ds["id"]] = executor
        except Exception:
            continue

    if not executors:
        return None

    def event_callback(event_type: str, data: dict) -> None:
        _send_event(session_id, event_type, data)

    agent = NL2SQLAgent(
        project_id=project_id,
        datasources=datasource_schemas,
        executors=executors,
        event_callback=event_callback,
        max_iterations=settings.agent_max_iterations,
        max_probe_iterations=settings.agent_max_probe_iterations,
    )

    return agent


def _load_history_messages(session_id: str) -> list[Message]:
    """加载历史消息为 LLM Message 格式。"""
    from ..services.session_service import get_messages
    messages_data = get_messages(session_id)
    messages = []
    for msg in messages_data[-20:]:  # 最近 20 条
        role_map = {"user": MessageRole.USER, "assistant": MessageRole.ASSISTANT}
        role = role_map.get(msg["role"])
        if role and msg.get("content"):
            messages.append(Message(role=role, content=msg["content"]))
    return messages


async def run_chat(session_id: str, user_query: str) -> None:
    """异步运行聊天流程。"""
    session = get_session(session_id)
    if not session:
        _send_event(session_id, "error", {"message": "会话不存在"})
        _send_event(session_id, "done", {})
        return

    project_id = session["project_id"]

    # 自动更新标题
    update_session_title_from_query(session_id, user_query)

    # 保存用户消息
    add_message(session_id, "user", user_query)

    # 构建 Agent
    agent = _build_agent(project_id, session_id)
    if not agent:
        _send_event(session_id, "error", {"message": "无法构建 Agent，请检查数据源配置"})
        _send_event(session_id, "done", {})
        return

    # 加载历史消息
    history = _load_history_messages(session_id)

    # 在线程池中运行同步的 Agent（避免阻塞事件循环）
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: agent.run(user_query, conversation_history=history),
        )

        # 保存助手消息
        answer = result.get("answer", "")
        sql = result.get("sql", "")
        exec_result = result.get("execution_result")
        result_dict = None
        if exec_result:
            result_dict = {
                "columns": exec_result.columns,
                "rows": [list(r) for r in exec_result.rows],
                "row_count": exec_result.row_count,
                "success": exec_result.success,
                "error": exec_result.error,
            }

        add_message(session_id, "assistant", answer, sql_text=sql, result=result_dict)

        # 记录生成日志
        intent = result.get("intent")
        intent_summary = intent.raw_analysis if intent else ""
        exec_success = exec_result.success if exec_result else False
        exec_time = exec_result.duration_ms if exec_result else 0
        row_count = exec_result.row_count if exec_result else 0
        error_msg = exec_result.error if exec_result and not exec_success else None

        thoughts = result.get("react_thoughts", [])
        reflection_notes = "\n".join(
            f"迭代 {i+1}: {t.thought}" for i, t in enumerate(thoughts)
        )

        log_generation(
            project_id=project_id,
            datasource_id=result.get("selected_datasource_id", "") or "",
            session_id=session_id,
            user_query=user_query,
            generated_sql=sql or "",
            intent_summary=intent_summary,
            execution_success=exec_success,
            execution_time_ms=exec_time,
            row_count=row_count,
            error_message=error_msg,
            iteration=result.get("iteration", 0),
            reflection_notes=reflection_notes,
            model="",  # 后续可以从 settings 读
            final_selected=True,
        )

    except Exception as e:
        _send_event(session_id, "error", {"message": f"执行出错: {str(e)}"})
    finally:
        _send_event(session_id, "done", {})
        # 清理任务
        _active_tasks.pop(session_id, None)


async def start_chat(session_id: str, user_query: str) -> str:
    """启动聊天任务，返回会话 ID。"""
    # 取消之前的任务（如果有）
    if session_id in _active_tasks:
        _active_tasks[session_id].cancel()

    # 创建新任务
    task = asyncio.create_task(run_chat(session_id, user_query))
    _active_tasks[session_id] = task

    return session_id


async def event_stream(session_id: str) -> AsyncGenerator[str, None]:
    """SSE 事件流生成器。"""
    queue = _get_event_queue(session_id)

    # 先发送一个开始事件
    yield f"event: start\ndata: {json.dumps({'session_id': session_id})}\n\n"

    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=60.0)
            event_type = event["type"]
            data = json.dumps(event["data"], ensure_ascii=False)
            yield f"event: {event_type}\ndata: {data}\n\n"

            if event_type == "done":
                # 发送完毕，清理队列
                break
        except asyncio.TimeoutError:
            # 心跳
            yield ": ping\n\n"
```

- [ ] **Step 3: 聊天 API**

```python
"""聊天 API（SSE 流式）。"""
from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..services.chat_service import start_chat, event_stream

router = APIRouter()


class ChatRequest(BaseModel):
    session_id: str
    message: str


@router.post("")
async def chat(data: ChatRequest):
    """发送消息，启动 Agent 处理。

    返回 session_id，通过 /api/chat/stream/{session_id} 接收流式事件。
    """
    if not data.session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    if not data.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    await start_chat(data.session_id, data.message)
    return {"session_id": data.session_id, "status": "started"}


@router.get("/stream/{session_id}")
async def stream(session_id: str):
    """SSE 事件流。"""
    return StreamingResponse(
        event_stream(session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 4: 注册聊天路由**

在 `app/api/__init__.py` 中添加 chat 路由。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/chat_service.py backend/app/services/generation_log.py backend/app/api/chat.py backend/app/api/__init__.py
git commit -m "feat: chat service with SSE streaming"
```

---

## Task 6: 后端集成测试 + README 更新

- [ ] **Step 1: 端到端测试（用 SQLite 内存库）**

创建 `backend/tests/test_api/test_chat_flow.py`，测试完整的 API 流程。

- [ ] **Step 2: 更新 backend/README.md**

加入 API 文档和启动方式：
```bash
# 启动开发服务器
cd backend
uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 3: 运行全量测试**

Run: `cd backend && pytest tests/ -v`
Expected: 全部通过

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_api/test_chat_flow.py backend/README.md
git commit -m "test: backend integration tests"
```

---

## Phase 2 完成清单

- [x] Task 1: FastAPI 脚手架 + 配置 + 数据库初始化
- [x] Task 2: 项目管理 API
- [x] Task 3: 数据源管理 + Schema 自动导入
- [x] Task 4: Schema API + 会话管理
- [x] Task 5: 聊天服务 + SSE 流式接口
- [x] Task 6: 集成测试 + README
