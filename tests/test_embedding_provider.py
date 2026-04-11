"""Tests for embedding provider factory and implementations."""

import pytest


class TestHashingEmbeddingProvider:
    def test_embed_texts_returns_correct_dimensions(self):
        from mempalace.infrastructure.vector.hashing import HashingEmbeddingProvider

        provider = HashingEmbeddingProvider(dimensions=128)
        result = provider.embed_texts(["hello world"])
        assert len(result) == 1
        assert len(result[0]) == 128

    def test_embed_texts_is_deterministic(self):
        from mempalace.infrastructure.vector.hashing import HashingEmbeddingProvider

        provider = HashingEmbeddingProvider()
        r1 = provider.embed_texts(["hello world"])
        r2 = provider.embed_texts(["hello world"])
        assert r1 == r2

    def test_different_texts_produce_different_embeddings(self):
        from mempalace.infrastructure.vector.hashing import HashingEmbeddingProvider

        provider = HashingEmbeddingProvider()
        results = provider.embed_texts(["hello world", "goodbye moon"])
        assert results[0] != results[1]

    def test_name_property(self):
        from mempalace.infrastructure.vector.hashing import HashingEmbeddingProvider

        provider = HashingEmbeddingProvider(dimensions=256)
        assert provider.name == "hashing-v1-256"

    def test_empty_text_returns_zero_vector(self):
        from mempalace.infrastructure.vector.hashing import HashingEmbeddingProvider

        provider = HashingEmbeddingProvider(dimensions=64)
        result = provider.embed_texts([""])
        assert all(v == 0.0 for v in result[0])


class TestEmbeddingProviderFactory:
    def test_hashing_provider(self):
        from mempalace.infrastructure.settings import StorageSettings
        from mempalace.infrastructure.vector.factory import create_embedding_provider
        from mempalace.infrastructure.vector.hashing import HashingEmbeddingProvider

        settings = StorageSettings(embedding_provider="hashing")
        provider = create_embedding_provider(settings)
        assert isinstance(provider, HashingEmbeddingProvider)

    def test_auto_without_sentence_transformers(self, monkeypatch):
        """Auto mode should fall back to hashing when sentence-transformers is not installed."""
        from mempalace.infrastructure.settings import StorageSettings
        from mempalace.infrastructure.vector.factory import create_embedding_provider
        from mempalace.infrastructure.vector.hashing import HashingEmbeddingProvider

        # Simulate missing sentence-transformers
        import mempalace.infrastructure.vector.factory as factory_module

        original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

        def mock_import(name, *args, **kwargs):
            if "sentence_transformer" in name:
                raise ImportError("mocked")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        settings = StorageSettings(embedding_provider="auto")
        provider = create_embedding_provider(settings)
        assert isinstance(provider, HashingEmbeddingProvider)

    def test_unknown_provider_raises(self):
        from mempalace.infrastructure.settings import StorageSettings
        from mempalace.infrastructure.vector.factory import create_embedding_provider

        settings = StorageSettings(embedding_provider="imaginary")
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            create_embedding_provider(settings)

    def test_default_settings_produce_provider(self):
        """Default settings should always produce a working provider."""
        from mempalace.infrastructure.vector.factory import create_embedding_provider

        provider = create_embedding_provider()
        assert hasattr(provider, "embed_texts")
        assert hasattr(provider, "name")
        result = provider.embed_texts(["test"])
        assert len(result) == 1
        assert len(result[0]) > 0


class TestSentenceTransformerProvider:
    """Tests that only run when sentence-transformers is installed."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_st(self):
        try:
            import sentence_transformers  # noqa: F401
        except ImportError:
            pytest.skip("sentence-transformers not installed")

    def test_embed_texts_returns_384_dim(self):
        from mempalace.infrastructure.vector.sentence_transformer import (
            SentenceTransformerEmbeddingProvider,
        )

        provider = SentenceTransformerEmbeddingProvider()
        result = provider.embed_texts(["hello world"])
        assert len(result) == 1
        assert len(result[0]) == 384

    def test_semantic_similarity(self):
        """Similar texts should have higher cosine similarity than dissimilar ones."""
        from mempalace.infrastructure.vector.sentence_transformer import (
            SentenceTransformerEmbeddingProvider,
        )

        provider = SentenceTransformerEmbeddingProvider()
        embeddings = provider.embed_texts([
            "JWT authentication tokens for session management",
            "OAuth2 bearer tokens for API authorization",
            "The weather forecast for tomorrow is sunny",
        ])

        def cosine_sim(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = sum(x * x for x in a) ** 0.5
            norm_b = sum(x * x for x in b) ** 0.5
            return dot / (norm_a * norm_b)

        # auth-related texts should be more similar to each other than to weather
        sim_auth = cosine_sim(embeddings[0], embeddings[1])
        sim_unrelated = cosine_sim(embeddings[0], embeddings[2])
        assert sim_auth > sim_unrelated, (
            f"Auth texts similarity ({sim_auth:.3f}) should be greater than "
            f"unrelated similarity ({sim_unrelated:.3f})"
        )

    def test_name_property(self):
        from mempalace.infrastructure.vector.sentence_transformer import (
            SentenceTransformerEmbeddingProvider,
        )

        provider = SentenceTransformerEmbeddingProvider()
        assert provider.name == "sentence-transformer-all-MiniLM-L6-v2"

    def test_factory_creates_sentence_transformer(self):
        from mempalace.infrastructure.settings import StorageSettings
        from mempalace.infrastructure.vector.factory import create_embedding_provider
        from mempalace.infrastructure.vector.sentence_transformer import (
            SentenceTransformerEmbeddingProvider,
        )

        settings = StorageSettings(embedding_provider="sentence-transformer")
        provider = create_embedding_provider(settings)
        assert isinstance(provider, SentenceTransformerEmbeddingProvider)
