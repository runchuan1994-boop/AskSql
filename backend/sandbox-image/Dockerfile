# NL2SQL 沙盒执行器镜像
# 这个镜像跑在 gVisor (runsc) 沙盒里，负责执行 SQL 查询和动态安装驱动

FROM python:3.12-slim

WORKDIR /sandbox

# 预装 SQLAlchemy（所有数据库都需要）
RUN pip install --no-cache-dir sqlalchemy

# 预装常见数据库驱动，减少动态安装的需要
# SQLite 是 Python 内置的，不用装
RUN pip install --no-cache-dir \
    psycopg2-binary \
    mysql-connector-python \
    pymysql

# 复制执行器脚本
COPY executor.py /sandbox/executor.py
RUN chmod +x /sandbox/executor.py

# 创建一个非 root 用户运行，减少攻击面
RUN useradd -m -u 1000 sandbox
USER sandbox

CMD ["python", "-u", "/sandbox/executor.py"]
