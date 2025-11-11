from dataclasses import dataclass
from itertools import chain, pairwise
from typing import Any

from owl.types import Chunk


def detect_consecutive_segments(lst: list[tuple[Any, Any]]) -> list[tuple[Any, Any]]:
    """
    Returns a list of consecutive elements.

    Example:
        Input: [(0, 0), (0, 2), (0, 1), (1, 3), (2, 4)]
        Output: [[(0, 0), (0, 1), (0, 2)]]

    Args:
        lst (list[tuple[Any, Any]]): List of elements.

    Returns:
        segments (list[tuple[Any, Any]]): List of consecutive elements.
    """
    if len(lst) == 0:
        return []
    lst = sorted(lst)
    segments = []
    current_segment = [lst[0]]

    for i in range(1, len(lst)):
        if lst[i][0] == lst[i - 1][0] and lst[i][1] == lst[i - 1][1] + 1:
            current_segment.append(lst[i])
        else:
            segments.append(current_segment)
            current_segment = [lst[i]]
    segments.append(current_segment)

    segments = [s for s in segments if len(s) > 1]
    return segments


@dataclass(slots=True)
class Match:
    a: int
    b: int


def match_end(a: str, b: str):
    matches = []
    for i in range(1, len(a) + 1):
        if a[-i:] == b[:i]:
            matches.append(i)
    if len(matches) > 0:
        match = max(matches)
        match = Match(a=len(a) - match, b=match)
    else:
        match = None
    return match


def remove_chunk_overlap(
    documents: list[Chunk], scores: list[float]
) -> tuple[list[Chunk], list[float]]:
    segments = detect_consecutive_segments([(d.document_id, int(d.chunk_id)) for d in documents])
    id2doc = {(d.document_id, int(d.chunk_id)): (i, d.text) for i, d in enumerate(documents)}
    segments = [list(pairwise(s)) for s in segments]
    segments = list(chain(*segments))
    for s in segments:
        i, text = id2doc[s[0]]
        match = match_end(text, id2doc[s[1]][1])
        if match is None:
            continue
        documents[i].text = text[: match.a]
    documents_scores = [(c, s) for c, s in zip(documents, scores, strict=True) if len(c.text) > 0]
    if len(documents_scores) == 0:
        documents, scores = [], []
    else:
        documents, scores = zip(*documents_scores, strict=True)
    return documents, scores
