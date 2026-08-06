.PHONY: help demo up down migrate core core-test ingest-one eval-test api-install web-install lint demo-bundle demo-bootstrap

help:
	@echo "trackbench targets:"
	@echo "  make up             - start Postgres (docker-compose)"
	@echo "  make migrate        - apply Prisma schema"
	@echo "  make core           - build C++ tracker (Release)"
	@echo "  make core-test      - build + run GoogleTest"
	@echo "  make ingest-one     - ingest first mini scene (requires data)"
	@echo "  make demo-bundle    - regenerate fixture demo_bundle.json"
	@echo "  make demo-bootstrap - migrate + load demo run into Postgres"
	@echo "  make demo           - up + migrate + core + print next steps"

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

demo-bundle:
	python3 -m eval.write_demo_run

demo-bootstrap: migrate
	cd api && npx tsx -e 'import { PrismaClient } from "@prisma/client"; import { bootstrapDemo } from "./src/demo.ts"; const p=new PrismaClient(); bootstrapDemo(p).then(r=>{console.log(JSON.stringify(r,null,2)); return p.$$disconnect();}).catch(e=>{console.error(e); process.exit(1);})'

core:
	cmake -S core -B core/build -DCMAKE_BUILD_TYPE=Release
	cmake --build core/build -j$$(nproc)

core-test:
	cmake -S core -B core/build -DCMAKE_BUILD_TYPE=Debug -DTRACKBENCH_BUILD_TESTS=ON
	cmake --build core/build -j$$(nproc)
	cd core/build && ctest --output-on-failure

ingest-one:
	python3 -m ingest.nuscenes_ingest --limit 1

demo: core
	@echo ""
	@python3 -m ingest.nuscenes_ingest --synthetic --force
	@echo ""
	@echo "=== sample detections ==="
	@head -n 1 data/normalized/synthetic_scene_001/detections.jsonl
	@echo ""
	@echo "Postgres: make up && make migrate   (requires Docker)"
	@echo "Real data: see docs/data.md"

lint:
	@echo "noop for M0"
