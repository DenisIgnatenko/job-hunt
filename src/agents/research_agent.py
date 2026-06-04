"""
Research agent: builds a company dossier from web search + job description (SRP).
Web search via DuckDuckGo — no API key needed, free.
"""

import logging
from datetime import datetime, timezone

from duckduckgo_search import DDGS

from src.agents.base_agent import BaseAgent
from src.database.repository import Company, CompanyRepository, Vacancy

log = logging.getLogger(__name__)

_SYSTEM = """
You are a research assistant preparing a company dossier for Denis Ignatenko,
a backend software engineer applying for a job.

Using the web search results and job description provided, write a concise dossier covering:
1. What the company does (2-3 sentences, current and specific)
2. Engineering culture, tech stack, team size (if known)
3. Company stage: startup / scale-up / enterprise
4. Anything that makes this company interesting or worth mentioning in a cover letter
   (a product detail, a recent milestone, a stated value, something human)
5. Any red flags relevant to a backend engineer

Under 350 words. Be specific — avoid generic phrases like "innovative company".
If information is missing, say so rather than guessing.
""".strip()

_MAX_SEARCH_RESULTS = 5
_SNIPPET_CHARS = 300


class ResearchAgent(BaseAgent):
    def __init__(self, repo: CompanyRepository | None = None) -> None:
        super().__init__()
        self._repo = repo or CompanyRepository()

    def run(self, vacancy: Vacancy) -> Company:
        company_name = vacancy.company or "Unknown company"

        existing = self._repo.get_by_name(company_name)
        if existing and existing.researched_at:
            log.info("Research: using cached dossier for '%s'", company_name)
            return existing

        web_context = self._search(company_name)
        summary = self._research(company_name, vacancy.description, web_context)

        company = Company(
            name=company_name,
            summary=summary,
            researched_at=datetime.now(timezone.utc).isoformat(),
        )
        self._repo.upsert(company)
        return company

    def _search(self, company_name: str) -> str:
        """Fetch fresh web snippets about the company via DuckDuckGo."""
        queries = [
            f"{company_name} Denmark software engineering team",
            f"{company_name} tech blog culture values",
        ]
        snippets: list[str] = []
        try:
            with DDGS() as ddgs:
                for query in queries:
                    results = ddgs.text(query, max_results=_MAX_SEARCH_RESULTS)
                    for r in results:
                        title = r.get("title", "")
                        body = r.get("body", "")[:_SNIPPET_CHARS]
                        url = r.get("href", "")
                        snippets.append(f"[{title}] {body} ({url})")
        except Exception:
            log.warning("Research: web search failed for '%s', continuing without it", company_name)

        if not snippets:
            return "No web results found."
        return "\n\n".join(snippets)

    def _research(
        self, company_name: str, description: str | None, web_context: str
    ) -> str:
        prompt = (
            f"Company: {company_name}\n\n"
            f"## Web search results\n{web_context}\n\n"
            f"## Job description\n{description[:1500] if description else 'N/A'}"
        )
        return self._chat(system=_SYSTEM, user=prompt, max_tokens=600)
