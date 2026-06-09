"""
Letter agent: generates a tailored cover letter draft (SRP).
Awaits human approval via Telegram before the letter is persisted as approved.
"""

from src.agents.base_agent import BaseAgent
from src.database.repository import (
 CoverLetter,
 CoverLetterRepository,
 Company,
 Vacancy,
)

_INSTRUCTIONS = """
You are writing a cover letter on behalf of Denis Ignatenko.

## Denis's personality — write in his voice, not yours
Denis is warm, open, and genuinely kind — the kind of person who shows up when someone needs help moving flats.
He's an introvert who communicates exceptionally well (it costs him energy, which makes it deliberate and real).
He has dry wit and enjoys a well-placed reference — a line from a film, a meme that fits perfectly, an observation
that makes someone smile. Not forced jokes. One moment of lightness that shows a real person wrote this.
He runs a YouTube channel (@midlifecode, 1300+ subscribers) about software, relocation, and career change —
he knows how to talk to people, not at them.
He is memorable. Not grey. The letter should feel like it came from someone you'd want on your team.

## Rules
- Use only facts from the resume — never invent skills or experience
- Show genuine curiosity about this specific company (use the dossier if provided)
- One natural moment of personality or light humour — integrated, not bolted on
- 250–320 words. Tight. Every sentence earns its place.
- Plain paragraphs. No bullet points.
- Structure: memorable opening → specific reason this company → what Denis brings → warm close
- Return only the letter body — no subject line, no salutation, no sign-off name
""".strip()


class LetterAgent(BaseAgent):
 def __init__(self, repo: CoverLetterRepository | None = None) -> None:
  super().__init__()
  self._repo = repo or CoverLetterRepository()
  self._system = self._system_with_resume(_INSTRUCTIONS)

 def run(
  self,
  vacancy: Vacancy,
  company: Company | None = None,
  user_comments: str | None = None,
 ) -> CoverLetter:
  """Generate a cover letter draft and persist it (unapproved)."""
  assert vacancy.id is not None, "Vacancy must be persisted before generating a letter"
  # version = последний номер + 1 (чтобы хранить историю итераций)
  existing = self._repo.get_by_vacancy(vacancy.id)
  version = (max(l.version for l in existing) + 1) if existing else 1
  body = self._generate(vacancy, company, user_comments)
  letter = CoverLetter(vacancy_id=vacancy.id, body=body, version=version)
  letter.id = self._repo.save(letter)
  return letter

 def _generate(
  self,
  vacancy: Vacancy,
  company: Company | None,
  user_comments: str | None = None,
 ) -> str:
  prompt = (
   f"Job title: {vacancy.title}\n"
   f"Company: {vacancy.company or 'unknown'}\n"
   f"Location: {vacancy.location or 'unknown'}\n"
   f"Job description:\n{vacancy.description or 'N/A'}\n"
  )
  if company and company.summary:
   prompt += f"\nCompany dossier:\n{company.summary}"
  if user_comments:
   prompt += (
    f"\n\n## Feedback on previous version\n"
    f"{user_comments}\n"
    f"Rewrite the letter incorporating this feedback. Keep the voice and structure."
   )
  return self._chat(system=self._system, user=prompt, max_tokens=700)
