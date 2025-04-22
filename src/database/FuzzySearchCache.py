import time
from typing import Dict, List

from rapidfuzz import fuzz, process

from src.models import FuzzySearchResult, MailMessage


class FuzzySearchCache:
    def __init__(self):
        self._subjects: Dict[str, str] = {}  # message_id -> subject
        self._senders: Dict[str, str] = {}  # message_id -> sender
        self._last_update: float = 0.0

    def update(self, messages: List[MailMessage]) -> None:
        """Update the cache with new messages."""
        for msg in messages:
            if msg.subject:
                self._subjects[msg.message_id] = msg.subject
            if msg.sender:
                self._senders[msg.sender] = msg.sender
        self._last_update = time.time()

    def search(
        self, query: str, limit: int = 10, threshold: int = 60
    ) -> List[FuzzySearchResult]:
        """
        Search for messages using fuzzy matching across both subjects and senders.

        Args:
            query: The search query
            limit: Maximum number of results to return
            threshold: Minimum similarity score (0-100)

        Returns:
            List of (message_id, score, match_type) tuples sorted by score
        """
        if not query:
            return []

        # Search both subjects and senders
        subject_results = process.extract(
            query,
            self._subjects,
            scorer=fuzz.partial_ratio,
            limit=limit,
            score_cutoff=threshold,
        )

        sender_results = process.extract(
            query,
            self._senders,
            scorer=fuzz.partial_ratio,
            limit=limit,
            score_cutoff=threshold,
        )

        # Combine results

        all_results = []
        for text, score, msg_id in subject_results:
            all_results.append(
                FuzzySearchResult(
                    text=text, indentifier=msg_id, score=score, match_type="subject"
                )
            )
        for text, score, msg_id in sender_results:
            all_results.append(
                FuzzySearchResult(
                    text=text, indentifier=msg_id, score=score, match_type="sender"
                )
            )
        # Sort by score and take top results
        all_results.sort(key=lambda x: x.score, reverse=True)
        return all_results[:limit]

    def clear(self) -> None:
        """Clear the cache."""
        self._subjects.clear()
        self._senders.clear()
        self._last_update = 0.0

    @property
    def last_update(self) -> float:
        return self._last_update
