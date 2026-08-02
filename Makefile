UID := $(shell id -u)
GID := $(shell id -g)
export UID GID

.PHONY: images
images: server-image webproxy-image			## Build all images

.PHONY: server-image
server-image:								## Build the server image
	$(MAKE) -C server image

.PHONY: webproxy-image
webproxy-image:								## Build the webproxy image
	$(MAKE) -C webproxy image

.PHONY: dev
dev: dev-up            ## Launch a dev container. Just type 'mushroomd' in it.
	docker exec -it mushroom-mushroomd-dev-1 sh -c "cd server && uv run bash"

.PHONY: dev-up
dev-up:   									## Start the dev stack
	docker compose -f compose-dev.yaml up -d

.PHONY: dev-down
dev-down:   								## Stop the dev stack
	docker compose -f compose-dev.yaml down


.PHONY: help
help:           ## Show this help
	@echo Noteworthy targets:
	@egrep '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
.DEFAULT_GOAL := help
