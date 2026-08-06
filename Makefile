.PHONY: help demo up down migrate core core-test ingest-one eval-test api-install web-install lint

help:
	@echo "trackbench targets:"
	@echo "  make up           - start Postgres (docker-compose)"
	@echo "  make migrate      - apply Prisma schema"
	@echo "  make core         - build C++ tracker (Release)"
	@echo "  make core-test    - build + run GoogleTest"
	@echo "  make ingest-one   - ingest first mini scene (requires data)"
	@echo "  make demo         - up + migrate + core + print next steps"

up:
	docker compose up -d
	@echo "Waiting for Postgres..."
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		docker compose exec -T postgres pg_isready -U trackbench -d trackbench && break; \
		sleep 1; \
	done

down:
	docker compose down

migrate: api-install
	cd api && npx prisma migrate deploy

api-install:
	cd api && npm install

web-install:
	cd web && npm install

core:
	cmake -S core -B core/build -DCMAKE_BUILD_TYPE=Release
	cmake --build core/build -j$$(nproc)

core-test:
	cmake -S core -B core/build -DCMAKE_BUILD_TYPE=Debug -DTRACKBENCH_BUILD_TESTS=ON
	cmake --build core/build -j$$(nproc)
	cd core/build && ctest --output-on-failure

ingest-one:
	python3 -m ingest.nuscenes_ingest --limit 1

demo: up migrate core
	@echo ""
	@echo "Postgres is up. Prisma migrated. C++ binary built."
	@echo "Next: download nuScenes mini + Megvii detections (see docs/data.md),"
	@echo "then: make ingest-one && cat data/normalized/<scene>/detections.jsonl | head"

lint:
	@echo "noop for M0"
