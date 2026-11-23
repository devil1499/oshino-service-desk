FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt
# PaddleOCR 引入的 OpenCV 在 slim 镜像中需要这些运行库。
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

COPY app ./app
COPY alembic.ini ./
COPY migrations/env.py migrations/script.py.mako ./migrations/
# 只包含当前已实现的迁移；后续章节完成后再加入。
COPY migrations/versions/321917cab056_用户与基础配置.py ./migrations/versions/
COPY migrations/versions/1368452a803a_工单与处理记录.py ./migrations/versions/
COPY migrations/versions/04_import_key.py ./migrations/versions/
COPY migrations/versions/06_knowledge.py ./migrations/versions/
COPY migrations/versions/07_assistance.py ./migrations/versions/
COPY migrations/versions/09_resolution_time.py ./migrations/versions/
COPY migrations/versions/10_basic_analysis.py ./migrations/versions/
COPY migrations/versions/11_email.py ./migrations/versions/
COPY migrations/versions/13_qa_conversations.py ./migrations/versions/
COPY migrations/versions/14_customer_service.py ./migrations/versions/
COPY migrations/versions/15_qa_observability.py ./migrations/versions/
COPY migrations/versions/16_web_search.py ./migrations/versions/

EXPOSE 8000

CMD ["sh", "-c", "python -m alembic upgrade head && exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]
