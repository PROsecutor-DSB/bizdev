CHANNEL ?= zamesin
ENGINE  ?= auto
MAX_POSTS ?=

.PHONY: help install scrape mvp full stats classify audit reports query demo test clean-db

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "};{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## install python dependencies
	pip install -r requirements.txt

scrape:  ## STEP 1 - collect the public history
	python -m src.scraper.tgweb --channel $(CHANNEL) $(if $(MAX_POSTS),--max-posts $(MAX_POSTS),)

stats:  ## STEP 2 - dataset statistics
	python -m src.parser.normalize --channel $(CHANNEL)
	python -m src.parser.threads --channel $(CHANNEL)
	python -m src.reports.dataset_stats --channel $(CHANNEL)

classify:  ## STEP 3 - classify posts
	python -m src.classifier.classify --channel $(CHANNEL) --engine $(ENGINE)

audit:  ## STEP 4 - draw 50 posts for manual review
	python -m src.classifier.audit sample --channel $(CHANNEL) --n 50

mvp:  ## end-to-end on the 200 newest posts (do this first)
	python run_pipeline.py --channel $(CHANNEL) --engine $(ENGINE) --stage all --max-posts 200

full:  ## end-to-end on the whole available history
	python run_pipeline.py --channel $(CHANNEL) --engine $(ENGINE) --stage all

reports:  ## regenerate the markdown reports from the database
	python -m src.reports.render --channel $(CHANNEL)

query:  ## interactive question answering
	python query.py --channel $(CHANNEL)

demo:  ## run the whole pipeline on the synthetic test corpus (no network needed)
	python tests/make_demo_corpus.py
	python run_pipeline.py --channel demo_channel --engine heuristic --skip-scrape \
		--stage normalize,threads,classify,stats,extract,ajtbd,embed,cluster,relations,patterns,antipatterns,evolution,opportunities,techjob,ideas,gems,reports \
		--out-dir output/_demo_synthetic

test:  ## run the test suite
	python tests/run_all.py

clean-db:  ## delete the database (raw data is kept)
	rm -f database/intelligence.sqlite*
