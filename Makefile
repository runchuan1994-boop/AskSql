.PHONY: help dev up down build build-backend build-frontend backend frontend test test-backend clean logs langfuse-up langfuse-down langfuse-logs

# 默认目标：显示帮助
help:
	@echo "NL2SQL Agent - 一键启动命令"
	@echo ""
	@echo "用法:"
	@echo "  make dev          启动开发环境（后端 + 前端）"
	@echo "  make up           Docker 方式启动所有服务"
	@echo "  make down         停止所有 Docker 服务"
	@echo "  make build        构建所有 Docker 镜像"
	@echo "  make backend      只启动后端（开发模式）"
	@echo "  make frontend     只启动前端（开发模式）"
	@echo "  make test         运行所有测试"
	@echo "  make test-backend 运行后端测试"
	@echo "  make clean        清理数据和构建产物"
	@echo "  make logs         查看 Docker 日志"

# ============ Docker 方式 ============

up:
	docker compose up -d

down:
	docker compose down

build: build-backend build-frontend

build-backend:
	docker compose build backend

build-frontend:
	docker compose build frontend

logs:
	docker compose logs -f

# ============ Langfuse 可观测性 ============

langfuse-up:
	@echo "启动 Langfuse 服务..."
	docker compose up -d langfuse
	@echo "Langfuse UI: http://localhost:3030"
	@echo "默认账号: 自行注册（首次访问创建管理员）"

langfuse-down:
	@echo "停止 Langfuse 服务..."
	docker compose stop langfuse langfuse-db

langfuse-logs:
	docker compose logs -f langfuse

# ============ 开发模式 ============

backend:
	@echo "启动后端服务..."
	cd backend && uvicorn app.main:app --reload --port 8000

frontend:
	@echo "启动前端服务..."
	cd frontend && npm run dev

# 同时启动前后端（需要两个终端，这里只做后端，前端请另开终端）
dev: backend

# ============ 测试 ============

test: test-backend

test-backend:
	cd backend && pytest tests/ -v

# ============ 清理 ============

clean:
	docker compose down -v
	rm -rf backend/data/*.db
	rm -rf backend/__pycache__ backend/nl2sql/__pycache__
	rm -rf frontend/dist
