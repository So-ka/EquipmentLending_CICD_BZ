IMAGE := equipment-lending

.PHONY: build run shell

build:
	docker build -t $(IMAGE) .

# Ensures lending.db exists on the host *before* it's bind-mounted into
# the container. Without this, Docker creates a directory in its place
# (since the mount target doesn't exist yet) and sqlite3 fails to open it.
lending.db:
	touch lending.db

# Usage: make run ARGS="equipment list"
run: build lending.db
	docker run --rm -v "$(CURDIR)/lending.db:/app/lending.db" $(IMAGE) $(ARGS)
