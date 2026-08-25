.PHONY: validate index all

validate:
	python3 tools/validate.py

index:
	python3 tools/build_index.py

all: validate index
