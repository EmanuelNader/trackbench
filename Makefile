.PHONY: help demo up down migrate core core-test ingest-one eval-test api-install web-install lint demo-bundle demo-bootstrap eval-fixture demo-ui bench-latency

help:
	@echo "trackbench targets:"
	@echo "  make up             - start Postgres (docker-compose)"
	@echo "  make migrate        - apply Prisma schema"
	@echo "  make core           - build C++ tracker (Release)"
	@echo "  make core-test      - build + run GoogleTest"
	@echo "  make ingest-one     - ingest first mini scene (requires data)"
	@echo "  make eval-fixture   - CLEAR MOT + mine + gate on synthetic golden tracks"
	@echo "  make bench-latency  - dense synthetic timing (p50/p99 wall ms)"
	@echo "  make demo-bundle    - regenerate fixture demo_bundle.json"
	@echo "  make demo-bootstrap - migrate + load demo run into Postgres"
	@echo "  make demo-ui        - print curl bootstrap + web dev commands"
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

# Default matches docker-compose.yml; override with export DATABASE_URL=...
DATABASE_URL ?= postgresql://trackbench:trackbench@localhost:5432/trackbench?schema=public
export DATABASE_URL

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

# macOS has no nproc; fall back to sysctl / nproc / 4
NPROC := $(shell nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)

core:
	cmake -S core -B core/build -DCMAKE_BUILD_TYPE=Release
	cmake --build core/build -j$(NPROC)

core-test:
	cmake -S core -B core/build -DCMAKE_BUILD_TYPE=Debug -DTRACKBENCH_BUILD_TESTS=ON
	cmake --build core/build -j$(NPROC)
	cd core/build && ctest --output-on-failure

bench-latency: core
	python3 scripts/bench_latency.py --frames 100 --dets-per-frame 40

ingest-one:
	python3 -m ingest.nuscenes_ingest --limit 1

eval-fixture:
	PYTHONPATH=. python3 -m eval.run_eval \
		--gt data/fixtures/synthetic_scene_001/gt.jsonl \
		--tracks data/fixtures/synthetic_scene_001/tracks_expected.jsonl \
		--scene-meta data/fixtures/synthetic_scene_001/scene_meta.json \
		--scene-id synthetic_scene_001 \
		--mine
	PYTHONPATH=. python3 -m eval.gate

demo-ui:
	@echo ""
	@echo "=== trackbench triage UI ==="
	@echo "Prereqs: make up && make migrate   (Postgres)"
	@echo ""
	@echo "# API (from repo root)"
	@echo "cd api && npm ci && npx prisma migrate deploy && npm run build"
	@echo "DATABASE_URL=postgresql://trackbench:trackbench@localhost:5432/trackbench?schema=public \\"
	@echo "  FIXTURES_ROOT=\$$PWD/../data/fixtures node dist/index.js &"
	@echo "curl -s localhost:3001/demo/bootstrap"
	@echo "# or: make demo-bootstrap"
	@echo ""
	@echo "# Web"
	@echo "cd web && npm ci && npm run dev"
	@echo "# open http://localhost:5173"
	@echo ""

demo: core
	@echo ""
	@python3 -m ingest.nuscenes_ingest --synthetic --force
	@echo ""
	@echo "=== sample detections ==="
	@head -n 1 data/normalized/synthetic_scene_001/detections.jsonl
	@echo ""
	@echo "Postgres: make up && make migrate   (requires Docker)"
	@echo "Eval fixture: make eval-fixture"
	@echo "Triage UI: make demo-ui"
	@echo "Real data: see docs/data.md"

lint:
	@echo "noop for M0"
