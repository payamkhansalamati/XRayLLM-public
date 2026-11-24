FROM python:3.11.14-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/__init__.py src/protocol.py src/study_io.py src/evaluation.py src/study.py src/synthetic.py src/
COPY config/ config/
COPY data/study_manifest.csv data/study_manifest.csv
ENV PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["python", "-m", "src.study"]
CMD ["smoke"]
