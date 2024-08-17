UID := $(shell id -u)
GID := $(shell id -g)

.PHONY: dev
dev:            ## Launch a dev container. Just type 'mushroomd' in it.
	docker compose -f compose-dev.yaml up -d \
		&& docker exec -it --user "$(UID):$(GID)" mushroom-mushroomd-dev-1 sh

.PHONY: help
help:           ## Show this help
	@echo Noteworthy targets:
	@egrep '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
.DEFAULT_GOAL := help
