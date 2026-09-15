"""
Outreach agent: черновик LinkedIn connection-request сообщения (SRP).

Denis всегда отправляет вручную из LinkedIn UI — этот агент только готовит текст.
Формат принципиально другой, чем у LetterAgent: не письмо, а note к запросу на
подключение — жёсткий лимит символов у LinkedIn, без приветствия/подписи.
"""

from src.agents.base_agent import BaseAgent
from src.agents.voice import DENIS_VOICE, has_dash
from src.database.repository import OutreachContact, Vacancy

_INSTRUCTIONS = f"""
You are drafting a LinkedIn connection request note on behalf of Denis Ignatenko. This
is the short note that goes with a "Connect" request to someone he isn't connected to
yet — not an email, not a cover letter, not a message to an existing connection.

{DENIS_VOICE}

## Format, non-negotiable
LinkedIn hard-caps connection request notes at 300 characters. Target 200-260 characters
so there's margin. One or two short sentences. No "Hi [Name]," greeting, no "Best,
Denis" sign-off — those cost characters LinkedIn's own UI already spends on name and
identity. Just the note itself.

## What this note needs to do
- Give ONE concrete, specific reason Denis is reaching out to THIS person, tied to
  their role and this company. Not "I'd like to connect" with no reason.
- Make it clear, lightly, that he's curious about the company and whether they're
  hiring or know of relevant openings. Frame it as a genuine question, not a pitch or
  an ask for a referral.
- Read like one person messaging another he'd like to know, not a template a hundred
  other job-seekers are also sending this week. Recruiters and tech leads get a lot of
  these; the ones that land are specific and brief, not enthusiastic.

## What to avoid
- Asking for a job outright, or anything that reads like "please consider me" / "I'd
  love to be considered for this role"
- A resume recap or a list of skills, there's no room and it's not the point here
- Generic LinkedIn-speak: "I came across your profile", "I hope this message finds you
  well", "I'd love to pick your brain"
- Exclamation marks, or more than one question

Return only the note text. Nothing else.
""".strip()

_MAX_TOKENS = 150


class OutreachAgent(BaseAgent):
    def run(self, contact: OutreachContact, vacancy: Vacancy) -> str:
        prompt = self._build_prompt(contact, vacancy)
        system = self._system_with_resume(_INSTRUCTIONS)
        message = self._chat(system=system, user=prompt, max_tokens=_MAX_TOKENS).strip()

        # Defense in depth — the prompt bans dashes explicitly, but doesn't
        # guarantee compliance. One retry with a pointed reminder before giving up.
        if has_dash(message):
            retry_prompt = prompt + (
                "\n\nYour previous draft used a dash (— or –), which is not allowed. "
                "Rewrite it without one."
            )
            message = self._chat(system=system, user=retry_prompt, max_tokens=_MAX_TOKENS).strip()

        return message

    def _build_prompt(self, contact: OutreachContact, vacancy: Vacancy) -> str:
        lines = [
            f"Contact name: {contact.full_name}",
            f"Contact headline: {contact.headline or 'unknown'}",
            f"Contact role category: {contact.role_category}",
            f"Company: {contact.company}",
            f"Vacancy that prompted this outreach: {vacancy.title}",
        ]
        if vacancy.description:
            lines.append(f"Vacancy description (excerpt):\n{vacancy.description[:600]}")
        return "\n".join(lines)
