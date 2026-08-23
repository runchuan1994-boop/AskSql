FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖（使用清华镜像加速）
COPY pyproject.toml ./
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple ".[dev,sandbox]" uvicorn

# 预装常见数据库驱动（主进程也能直接连接常用数据库）
# 更少见的数据库仍然可以通过沙盒动态安装驱动
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    psycopg2-binary \
    mysql-connector-python \
    pymysql

# 复制代码
COPY nl2sql/ ./nl2sql/
COPY app/ ./app/
COPY sandbox/ ./sandbox/
COPY config/ ./config/
COPY tests/ ./tests/

# 确保数据目录存在
RUN mkdir -p /app/data /app/config/schemas /app/config/projects

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
