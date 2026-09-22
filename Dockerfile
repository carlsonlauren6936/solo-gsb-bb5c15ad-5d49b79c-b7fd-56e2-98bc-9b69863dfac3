FROM python:3.12-slim

# 不生成 .pyc、不缓冲 stdout，便于容器内直接看到日志
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先单独安装依赖，利用 Docker 层缓存
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# 非 root 用户运行
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; \
        urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/health')" \
    || exit 1

# 默认端口 8000；启动时由 lifespan 初始化内置单位表
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
