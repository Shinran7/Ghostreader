"""Tests for embedding backends."""

from __future__ import annotations

from ghostreader.embed import OpenAIEmbedder, _OPENAI_DIMS, get_embedder


class TestOpenAIDimensions:
    def test_known_map_covers_large_and_small(self) -> None:
        assert _OPENAI_DIMS["text-embedding-3-small"] == 1536
        assert _OPENAI_DIMS["text-embedding-3-large"] == 3072

    def test_openai_embedder_uses_model_map(self, monkeypatch) -> None:  # noqa: ANN001
        class _FakeEmbeddings:
            def __init__(self, model: str) -> None:
                self.model = model

            def embed_documents(self, texts: list[str]) -> list[list[float]]:
                raise AssertionError("should not probe when model is known")

        monkeypatch.setattr(
            "langchain_openai.OpenAIEmbeddings",
            _FakeEmbeddings,
        )
        large = OpenAIEmbedder("text-embedding-3-large")
        small = OpenAIEmbedder("text-embedding-3-small")
        assert large.dimension == 3072
        assert small.dimension == 1536

    def test_unknown_model_derives_from_probe(self, monkeypatch) -> None:  # noqa: ANN001
        class _FakeEmbeddings:
            def __init__(self, model: str) -> None:
                self.model = model

            def embed_documents(self, texts: list[str]) -> list[list[float]]:
                return [[0.0] * 42 for _ in texts]

        monkeypatch.setattr(
            "langchain_openai.OpenAIEmbeddings",
            _FakeEmbeddings,
        )
        embedder = OpenAIEmbedder("custom-mystery-model")
        assert embedder.dimension == 42

    def test_stub_via_factory(self) -> None:
        assert get_embedder("stub").dimension == 384
