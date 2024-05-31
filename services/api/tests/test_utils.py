from jamaibase.protocol import Chunk
from owl.utils.kb import detect_consecutive_segments, remove_chunk_overlap


def test_detect_consecutive_segments():
    x = [(0, 0), (0, 2), (0, 1), (1, 3), (2, 4)]
    y = detect_consecutive_segments(x)
    assert y == [[(0, 0), (0, 1), (0, 2)]]


def test_remove_chunk_overlap():
    kwargs = dict(document_id="1", source="test.txt", title="title")
    documents = [
        Chunk(
            text="When the apple was ready she painted her face, and dressed herself up as a farmer’s wife,\n",
            chunk_id="0",
            **kwargs,
        ),
        Chunk(
            text="and dressed herself up as a farmer’s wife,\nand so she went over the seven mountains to the seven dwarfs.",
            chunk_id="1",
            **kwargs,
        ),
        Chunk(
            text="and dressed herself up as a farmer’s wife,\nand so she went over the seven mountains to the seven dwarfs.",
            chunk_id="2",
            **kwargs,
        ),
        Chunk(
            text="and so she went over the seven mountains to the seven dwarfs. She knocked at the door.",
            chunk_id="4",
            **kwargs,
        ),
    ]
    scores = [float(d.chunk_id) for d in documents]
    documents, scores = remove_chunk_overlap(documents, scores)
    assert documents[0].text == "When the apple was ready she painted her face, "
    assert documents[0].chunk_id == "0"
    assert scores[0] == 0.0
    # chunk ID 1 is filtered out
    assert (
        documents[1].text
        == "and dressed herself up as a farmer’s wife,\nand so she went over the seven mountains to the seven dwarfs."
    )
    assert documents[1].chunk_id == "2"
    assert scores[1] == 2.0
    assert (
        documents[2].text
        == "and so she went over the seven mountains to the seven dwarfs. She knocked at the door."
    )
    assert documents[2].chunk_id == "4"
    assert scores[2] == 4.0


if __name__ == "__main__":
    test_remove_chunk_overlap()
