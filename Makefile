.PHONY: help install test lint fix daily site whatif backfill validate clean

PY ?= python

help:
	@echo "Targets:"
	@echo "  install   - install runtime + dev deps"
	@echo "  test      - run pytest"
	@echo "  lint      - run ruff check"
	@echo "  fix       - run ruff check --fix"
	@echo "  daily     - run daily update locally for tickers in stocks.txt"
	@echo "  site      - build the static site under ./site"
	@echo "  whatif    - run MA strategy backtest / write site/what-if.html"
	@echo "  validate  - run the data-quality validator (exit non-zero on issues)"
	@echo "  backfill  - re-fetch full history (TICKERS=NVDA,AAPL or 'all')"
	@echo "  clean     - remove generated artifacts"

install:
	$(PY) -m pip install -r requirements.txt
	$(PY) -m pip install pytest ruff

test:
	$(PY) -m pytest tests/ -q

lint:
	$(PY) -m ruff check .

fix:
	$(PY) -m ruff check --fix .

daily:
	@TICKERS=$$(grep -v '^#' stocks.txt | grep -v '^$$' | tr '\n' ' '); \
	echo "Daily update: $$TICKERS"; \
	$(PY) main.py daily -s $$TICKERS

site:
	$(PY) build_site.py

whatif:
	$(PY) what_if.py --site

validate:
	$(PY) validate_data.py

TICKERS ?= all
backfill:
	@if [ "$(TICKERS)" = "all" ]; then \
	  TICK=$$(grep -v '^#' stocks.txt | grep -v '^$$' | tr '\n' ' '); \
	else \
	  TICK="$(TICKERS)"; \
	fi; \
	echo "Backfilling: $$TICK"; \
	$(PY) main.py initial --force -s $$TICK

clean:
	rm -rf site __pycache__ .pytest_cache .ruff_cache
	find . -name '*.pyc' -delete
