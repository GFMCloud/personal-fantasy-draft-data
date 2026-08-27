.PHONY: refresh validate test query lint $(addprefix refresh-,nflverse ffc espn sleeper harris dynastyprocess borischen ffopportunity ffc_boards)

refresh:
	uv run draft-data refresh

refresh-%:
	uv run draft-data refresh --source $*

validate:
	uv run draft-data validate

query:
	uv run draft-data query "$(SQL)"

test:
	uv run pytest -q

lint:
	uv run ruff check src tests
