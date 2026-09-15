"""
Outreach contact finder: ищет людей (техлиды, HR) в конкретной компании для аутрича (SRP).

Не наследует BaseScraper — возвращает сырые search results, не Vacancy
(та же причина, что у EventScraper: контракт другой, OCP не расширяем).

Два источника, оба нормализуются в один и тот же {"title","body","href"} формат
как у EventScraper, чтобы дальше их обрабатывал один и тот же LLM-шаг:
  1. ddgs — публичный веб-поиск LinkedIn-профилей (сначала, безопаснее)
  2. linkedin_api.search_people() — fallback, только если ddgs не нашёл ничего
     (LinkedIn активно детектит автоматизацию; используем по минимуму)
"""

import logging

from ddgs import DDGS  # пакет переименован из duckduckgo_search → ddgs
from linkedin_api import Linkedin

from src.config import config

log = logging.getLogger(__name__)

_TIMEOUT_SEC = 15
_MAX_RESULTS_PER_QUERY = 6

# site:linkedin.com/in — таргетируем именно публичные профили, не company pages
_ROLE_QUERY_GROUPS = [
    '"tech lead" OR "engineering manager" OR "CTO" OR "head of engineering"',
    '"HR" OR "talent acquisition" OR "recruiter" OR "people team"',
]


class OutreachFinder:
    _session: Linkedin | None = None

    def find(self, company: str) -> tuple[list[dict[str, str]], str]:
        """
        Возвращает (results, source). results в формате EventScraper.fetch():
        [{"title": ..., "body": ..., "href": ...}, ...].
        source — "web" или "linkedin", для записи в БД.
        """
        web_results = self._search_web(company)
        if web_results:
            return web_results, "web"

        log.info("OutreachFinder: ddgs пусто для '%s', пробую LinkedIn fallback", company)
        linkedin_results = self._search_linkedin(company)
        return linkedin_results, "linkedin"

    def _search_web(self, company: str) -> list[dict[str, str]]:
        queries = [
            f'site:linkedin.com/in "{company}" ({roles})'
            for roles in _ROLE_QUERY_GROUPS
        ]
        seen_urls: set[str] = set()
        results: list[dict[str, str]] = []

        try:
            with DDGS(timeout=_TIMEOUT_SEC) as ddgs:
                for query in queries:
                    try:
                        for r in ddgs.text(query, max_results=_MAX_RESULTS_PER_QUERY):
                            url = r.get("href", "")
                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                results.append({
                                    "title": r.get("title", ""),
                                    "body":  r.get("body", "")[:400],
                                    "href":  url,
                                })
                    except Exception:
                        log.warning("OutreachFinder: web query failed: '%s'", query)
                        continue
        except Exception:
            log.exception("OutreachFinder: DDGS session failed for '%s'", company)

        log.info("OutreachFinder: %d web results for '%s'", len(results), company)
        return results

    def _search_linkedin(self, company: str) -> list[dict[str, str]]:
        try:
            api = self._get_session()
            hits = api.search_people(keyword_company=company, include_private_profiles=False)
        except Exception:
            log.exception("OutreachFinder: LinkedIn search_people failed for '%s'", company)
            return []

        results: list[dict[str, str]] = []
        for h in hits[:10]:
            public_id = h.get("public_id") or h.get("publicIdentifier")
            if not public_id:
                continue
            name = h.get("name") or f"{h.get('firstName', '')} {h.get('lastName', '')}".strip()
            headline = h.get("jobtitle") or h.get("headline") or ""
            results.append({
                "title": f"{name} - {headline} - {company} | LinkedIn",
                "body":  headline,
                "href":  f"https://www.linkedin.com/in/{public_id}/",
            })

        log.info("OutreachFinder: %d LinkedIn results for '%s'", len(results), company)
        return results

    def _get_session(self) -> Linkedin:
        """Отдельная сессия от LinkedInScraper — та же cookie-auth, но find() дёргается
        по клику из дашборда (не по расписанию), так что не делим стейт с job scraping."""
        if OutreachFinder._session is None:
            if config.linkedin_cookie and config.linkedin_jsessionid:
                import requests as req_lib
                jar = req_lib.cookies.RequestsCookieJar()
                jar.set("li_at", config.linkedin_cookie, domain=".linkedin.com", path="/")
                jar.set("JSESSIONID", config.linkedin_jsessionid, domain=".linkedin.com", path="/")
                OutreachFinder._session = Linkedin("", "", cookies=jar)
            else:
                OutreachFinder._session = Linkedin(config.linkedin_email, config.linkedin_password)
        return OutreachFinder._session
