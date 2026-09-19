# Denis Ignatenko — Backend / Fullstack / AI Engineer

## Location & Availability
- Based in: Aarhus, Denmark
- Open to: Aarhus (preferred), Copenhagen (open to relocation), remote
- Work authorization: Danish work permit (accompanying spouse of Aarhus University PhD researcher)
- Available: Immediately
- Working language: English (C1). Danish: A1, actively studying. Russian: native.

## Contact
- Email: denis.ignatenko.dev@gmail.com
- Phone: +45 91 47 44 16
- LinkedIn: linkedin.com/in/denisignatenko
- GitHub: github.com/denisIgnatenko

---

## Technical Skills

**Backend:** Java, Spring Boot, JUnit, TypeScript, Node.js, NestJS, Python, FastAPI, REST APIs, Microservices, Kafka, event-driven architecture, CQRS, Sagas, async/queue-based systems, idempotent processing

**Frontend:** React, TypeScript, Redux Toolkit, HTML5, SASS/SCSS

**Databases:** PostgreSQL, Redis, MongoDB, ClickHouse, pgvector (vector search), SQLite, MySQL

**Cloud & DevOps:** AWS (EC2, S3, ECS), Docker, CI/CD, GitHub Actions, Git, Terraform (familiar), Kubernetes (in progress, CKA)

**AI & LLM:** Claude API, Claude Code, LangChain4j, RAG pipelines, embeddings, vector search, AI agents, agentic loops, MCP servers, prompt orchestration, semantic search

**Architecture:** Domain-Driven Design (DDD), Clean Architecture, Ports and Adapters (Hexagonal), SOLID, API Design, Swagger/OpenAPI

**Testing:** Unit testing, integration testing, automated testing, test-driven development

---

## Experience

### Job Hunt Automation Platform (Personal Project) — Sep 2025 to Present
*Production job search automation system. Python, FastAPI, React/TypeScript, Claude API, SQLite, AWS EC2, GitHub Actions.*
- Multi-source scraper aggregating vacancies from 4 job boards (Jobindex, The Hub, Remotive, RSS feeds) using Python and asyncio
- AI scoring pipeline: keyword pre-filter before LLM call reduces token cost ~80%; ScoutAgent scores location fit, tech stack match, remote policy
- Human-in-the-loop Telegram bot: vacancy cards with accept/skip actions; ResearchAgent builds company dossier; LetterAgent generates cover letter drafts on demand
- Web dashboard (FastAPI + React/TypeScript): vacancy pipeline, status tracking, AI match analysis, personal notes
- Deployed on AWS EC2 with GitHub Actions CI/CD; two systemd services running independently
- 373+ vacancies processed to date

### Backend Software Engineer — CorporationX, Sep 2024 to Jun 2026 (remote)
*Java microservices platform for a software developers' social network.*
- Built ai-content-service: Spring Boot microservice with LangChain4j agent framework, pgvector RAG pipeline, Kafka-driven auto-embedding and SSE streaming
- Built real-time News Feed: Kafka fan-out, Redis caching, idempotent event processing, cache-warming and TTL strategies for high-throughput production use
- Designed RESTful APIs following Clean Architecture and SOLID; documented with Swagger/OpenAPI; covered with JUnit unit and integration tests
- Built URL Shortener Service: 50K+ unique links/month, concurrent request handling, efficient hash generation
- Used Claude Code throughout for code generation, debugging, QA; applied critical judgement to all AI output before merging

### Technical Due Diligence Audit — Fableau / KOT Platform, Jan 2026 to Apr 2026 (remote, freelance)
*Audit of 18 repositories (fableau.com + knigaotebe.ru) for a digital book/content platform.*
- Mapped third-party dependencies and integration points across the codebase
- Identified critical security gaps and data-handling risks
- Produced technical documentation and handover report for new engineering team

### Fullstack Software Developer — Texel, May 2023 to Sep 2024 (London, UK, remote)
*DeepTech SaaS startup in 3D scanning, ML and virtual fitting technologies.*
- Designed and implemented per-vendor custom product-feed integration services; AI-enrichment of feed data (description standardisation, unit conversion for size charts)
- Built Node.js backend API endpoints exposing garment and body-shape data to internal dashboards and client-facing applications
- Integrated ClickHouse for product analytics; built async telemetry pipeline across Smart Mirror installations
- Built reusable React + TypeScript UI components for virtual fitting room kiosks (Chrome kiosk mode) and Shopify plugin
- Worked directly with partner brands on API integrations: understood real needs, debugged production issues when external systems behaved unexpectedly

### Fullstack Web Developer — HSE Researchers Group, Jun 2022 to May 2023 (remote)
*Learning management system for online course delivery.*
- Delivered MVP LMS with role-based access and paid enrolment: Node.js/PostgreSQL backend with REST APIs and React/Redux Toolkit frontend
- Implemented JWT authentication and session management; designed database schema from scratch
- Wrote technical documentation covering API contracts and architecture decisions
- Mentored 3 junior developers in code quality, task breakdown and feature delivery

### Technical Product Owner — Lobotryasi Coffee Roasters, Jun 2020 to Jun 2022 (Moscow, Russia)
*Subscription e-commerce platform for specialty coffee roastery.*
- Managed end-to-end delivery of subscription platform; defined and prioritised requirements for backend (Node.js) and frontend (React) teams
- Facilitated cross-functional collaboration between backend, frontend, design and QA in Agile workflows
- Ran discovery with stakeholders before committing to build; translated user problems into actionable requirements

---

## Education
- Master's equivalent (5-year specialist degree), Computer Science / Mathematical Programming
- Moscow State University of Economics, Statistics and Information (MESI), 2002 to 2007
- GPA: 4.81 / 5.0

---

## Additional
- YouTube channel on software development, AI tooling and career transitions (1,300+ subscribers)
- Volunteer in cultural projects in Aarhus
