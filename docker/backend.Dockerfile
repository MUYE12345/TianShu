# ── Intelligent Housekeeper 后端容器镜像 ──
FROM python:3.11-slim

WORKDIR /app

# 安装系统运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 60 -r requirements.txt

# 复制项目源码（仅后端运行所需）
COPY backend/ backend/
COPY agent/ agent/

# 创建运行时数据目录
RUN mkdir -p /app/data

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
