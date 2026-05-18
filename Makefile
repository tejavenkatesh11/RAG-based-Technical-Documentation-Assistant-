.PHONY: install ingest run ui clean

install:
	python -m pip install -r requirements.txt

ingest:
	python scripts/ingest_default.py

run:
	python -m uvicorn app.main:app --reload --port 8000

ui:
	streamlit run streamlit_app.py

clean:
	rm -rf data/chroma __pycache__ app/__pycache__ app/*/__pycache__
