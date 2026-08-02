UID := $(shell id -u)
GID := $(shell id -g)
export UID GID

.PHONY: images
images: server-image client-image			## Build all images

.PHONY: server-image
server-image:								## Build the server image
	$(MAKE) -C server image

.PHONY: client-image
client-image:								## Build the server image
	$(MAKE) -C client image

.PHONY: dev
dev:            ## Launch a dev container. Just type 'mushroomd' in it.
	docker compose -f compose-dev.yaml up -d \
		&& docker exec -it mushroom-mushroomd-dev-1 uv run sh

.PHONY: help
help:           ## Show this help
	@echo Noteworthy targets:
	@egrep '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
.DEFAULT_GOAL := help
