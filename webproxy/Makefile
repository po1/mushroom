version = $(shell git describe --tags --always --dirty)
image-name = pol/mushroom-webproxy:$(version)

.PHONY: image
image:			## Build the mushroom server image
	docker build -t $(image-name) .

.PHONY: help
help:           ## Show this help
	@echo Noteworthy targets:
	@egrep '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
.DEFAULT_GOAL := help
