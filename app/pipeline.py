from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from . import config
from .llm import NO_ANSWER

log = logging.getLogger("ul-chatbot")


QUICK_ACTIONS = [
    {
        "keywords": ["admiss", "apply", "dakhla", "how to apply", "registration", "form", "schedule", "eligib", "criteria", "program", "degree", "course"],
        "action": {
            "label": "Online Apply Portal",
            "url": "https://ul.edu.pk/page/How-to-Apply",
            "icon": "portal",
        },
    },
    {
        "keywords": ["program", "programs", "degree", "degrees", "faculty", "faculties", "department"],
        "action": {
            "label": "All Academic Programs",
            "url": "https://ul.edu.pk/admissions",
            "icon": "portal",
        },
    },
    {
        "keywords": ["fee", "fees", "challan", "dues", "voucher", "kharach", "charges", "paisa"],
        "action": {
            "label": "Generate Fee Challan",
            "url": "https://ul.edu.pk/challan",
            "icon": "document",
        },
    },
    {
        "keywords": ["fee", "fees", "structure", "per semester"],
        "action": {
            "label": "Fee Structure Page",
            "url": "https://ul.edu.pk/page/Fee-Structure",
            "icon": "document",
        },
    },
    {
        "keywords": ["merit", "list", "selection", "aggregate", "result", "ecat", "marks"],
        "action": {
            "label": "Check Merit Lists",
            "url": "https://ul.edu.pk/program_merit_list",
            "icon": "list",
        },
    },
    {
        "keywords": ["portal", "ums", "login", "student portal", "lms", "roll number", "attendance", "cgpa"],
        "action": {
            "label": "UMS Student Login",
            "url": "https://ul.edu.pk/login",
            "icon": "portal",
        },
    },
    {
        "keywords": ["contact", "rabta", "phone", "number", "email", "address", "call", "helpline", "location"],
        "action": {
            "label": "Call: 0606-920247",
            "url": "tel:0606920247",
            "icon": "phone",
        },
    },
    {
        "keywords": ["contact", "rabta", "whatsapp", "help", "admin", "office"],
        "action": {
            "label": "Official WhatsApp",
            "url": "https://wa.me/923078766389",
            "icon": "whatsapp",
        },
    },
    {
        "keywords": ["scholarship", "financial", "peef", "ehsaas", "hec need", "wazifa", "aid"],
        "action": {
            "label": "Scholarships Details",
            "url": "https://ul.edu.pk/page/Scholarships",
            "icon": "award",
        },
    },
    {
        "keywords": ["hostel", "accommodation", "rehaish", "room"],
        "action": {
            "label": "Hostel Facilities",
            "url": "https://ul.edu.pk/page/faculty-hostel",
            "icon": "home",
        },
    },
    {
        "keywords": ["transport", "bus", "route", "pick and drop"],
        "action": {
            "label": "Transport Routes",
            "url": "https://ul.edu.pk/page/Transport",
            "icon": "bus",
        },
    },
    {
        "keywords": ["enroll", "strength", "total student", "seat", "seats", "quota", "statistic"],
        "action": {
            "label": "Admissions & Merit Info",
            "url": "https://ul.edu.pk/admissions",
            "icon": "portal",
        },
    },
]


def detect_actions(message: str, search_query: str = "", is_no_answer: bool = False) -> list[dict]:
    if is_no_answer:
        return [
            {"label": "Call: 0606-920247", "url": "tel:0606920247", "icon": "phone"},
            {"label": "Official WhatsApp", "url": "https://wa.me/923078766389", "icon": "whatsapp"},
            {"label": "Contact Page", "url": "https://ul.edu.pk/contact", "icon": "portal"},
        ]

    combined = f"{message} {search_query}".lower()
    actions = []
    seen = set()

    for item in QUICK_ACTIONS:
        if any(kw in combined for kw in item["keywords"]):
            act = item["action"]
            if act["label"] not in seen:
                seen.add(act["label"])
                actions.append(act)
            if len(actions) == 3:
                break

    # If no specific keyword triggered, provide high-value university self-service actions
    if not actions:
        actions = [
            {"label": "Online Apply Portal", "url": "https://ul.edu.pk/page/How-to-Apply", "icon": "portal"},
            {"label": "Official WhatsApp", "url": "https://wa.me/923078766389", "icon": "whatsapp"},
            {"label": "Call: 0606-920247", "url": "tel:0606920247", "icon": "phone"},
        ]

    return actions


class RagPipeline:
    def __init__(self, index, embedder, llm):
        self.index, self.embedder, self.llm = index, embedder, llm

    @classmethod
    def from_disk(cls) -> "RagPipeline":
        import time

        from .embeddings import get_embedder
        from .llm import LLM
        from .store import Index

        t0 = time.time()
        log.info("Pipeline load: reading index files from %s", config.INDEX_DIR)
        index = Index.load(config.INDEX_DIR)
        log.info("Pipeline load: index read (%d chunks, %.1fs)", len(index.chunks), time.time() - t0)

        t1 = time.time()
        embedder = get_embedder()
        log.info("Pipeline load: embedder ready (%.1fs)", time.time() - t1)

        return cls(index, embedder, LLM())

    def _log_unanswered(self, question: str, search_query: str) -> None:
        try:
            config.UNANSWERED_LOG.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "question": question,
                "search_query": search_query,
            }
            with config.UNANSWERED_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            log.exception("Could not log unanswered query")

    def _retrieve(self, message: str, history: list[dict] | None = None):
        history = history or []
        search_query = self.llm.rewrite(message, history) if config.REWRITE_QUERY else message
        qvec = self.embedder.encode_query(search_query)
        hits = self.index.search(qvec, f"{search_query} {message}", top_k=config.TOP_K)
        sources, seen = [], set()
        for h in hits:
            url = h["chunk"]["url"]
            if url not in seen:
                seen.add(url)
                sources.append({"title": h["chunk"]["title"] or url, "url": url})
            if len(sources) == 3:
                break
        return search_query, hits, sources

    def chat(self, message: str, history: list[dict] | None = None) -> dict:
        history = history or []
        search_query, hits, sources = self._retrieve(message, history)

        if not hits:
            self._log_unanswered(message, search_query)
            actions = detect_actions(message, search_query, is_no_answer=True)
            return {
                "answer": "Mujhe is ka jawab nahi mila. Barah-e-karam info@ul.edu.pk ya 0606-920247 par rabta karein.",
                "sources": [],
                "actions": actions,
                "search_query": search_query,
            }

        raw = self.llm.answer(message, history, hits)
        if raw.startswith(NO_ANSWER):
            self._log_unanswered(message, search_query)
            text = raw[len(NO_ANSWER):].strip() or (
                "Mujhe is ka jawab nahi mila. Barah-e-karam info@ul.edu.pk ya 0606-920247 par rabta karein.")
            actions = detect_actions(message, search_query, is_no_answer=True)
            return {"answer": text, "sources": [], "actions": actions, "search_query": search_query}

        actions = detect_actions(message, search_query, is_no_answer=False)
        return {"answer": raw, "sources": sources, "actions": actions, "search_query": search_query}

    def chat_stream(self, message: str, history: list[dict] | None = None):
        history = history or []
        search_query, hits, sources = self._retrieve(message, history)

        if not hits:
            self._log_unanswered(message, search_query)
            fallback = "Mujhe is ka jawab nahi mila. Barah-e-karam info@ul.edu.pk ya 0606-920247 par rabta karein."
            yield {"type": "token", "token": fallback}
            yield {"type": "done", "sources": [], "actions": detect_actions(message, search_query, is_no_answer=True)}
            return

        buffer = ""
        is_no_answer = False
        prefix_checked = False
        prefix_len = len(NO_ANSWER)

        for token in self.llm.answer_stream(message, history, hits):
            if not prefix_checked:
                buffer += token
                if len(buffer) >= prefix_len:
                    prefix_checked = True
                    if buffer.startswith(NO_ANSWER):
                        is_no_answer = True
                        clean = buffer[prefix_len:].lstrip()
                        if clean:
                            yield {"type": "token", "token": clean}
                    else:
                        yield {"type": "token", "token": buffer}
                continue
            yield {"type": "token", "token": token}

        if not prefix_checked:
            if buffer.startswith(NO_ANSWER):
                self._log_unanswered(message, search_query)
                clean = buffer[prefix_len:].lstrip() or (
                    "Mujhe is ka jawab nahi mila. Barah-e-karam info@ul.edu.pk ya 0606-920247 par rabta karein."
                )
                yield {"type": "token", "token": clean}
                yield {"type": "done", "sources": [], "actions": detect_actions(message, search_query, is_no_answer=True)}
                return
            elif buffer:
                yield {"type": "token", "token": buffer}

        if is_no_answer:
            self._log_unanswered(message, search_query)

        actions = detect_actions(message, search_query, is_no_answer=is_no_answer)
        yield {"type": "done", "sources": [] if is_no_answer else sources, "actions": actions}
