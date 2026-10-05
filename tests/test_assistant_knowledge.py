"""Knowledge manifest, chunking and rank fusion contracts."""
from uuid import uuid4

from app.assistant import knowledge, retrieval


def test_manifest_only_approved_current_documents():
    sources = knowledge._approved_sources()
    paths = {source.path for source in sources}
    assert paths == {"docs/SYSTEM_GUIDE.md", "docs/PLANNER_SPEC.md",
                     "docs/ASSISTANT_RULES.md", "docs/DECISIONS.md"}
    decisions = next(source for source in sources if source.path.endswith("DECISIONS.md"))
    assert "ADR-028" in decisions.text and "ADR-032" in decisions.text
    assert "ADR-000" not in decisions.text
    assert all(source.metadata["access"] == "viewer" for source in sources)


def test_heading_aware_chunks_and_small_table():
    text = "# План\n\n## KPI\n\n| Код | Значение |\n|---|---|\n| say_do_ratio | факт/план |\n\nПояснение."
    chunks = knowledge.chunk_markdown(text, target=200, maximum=400)
    assert any("KPI" in chunk.heading and "say_do_ratio" in chunk.text for chunk in chunks)
    assert all(len(chunk.text) <= 400 for chunk in chunks)


def test_rrf_rewards_agreement_between_text_and_vector():
    first, second, third = uuid4(), uuid4(), uuid4()

    def row(chunk_id):
        return {"chunk_id": chunk_id, "document_id": uuid4(), "path": "docs/SYSTEM_GUIDE.md",
                "version": "v1", "heading_path": "Guide", "content": "text", "metadata": {}}

    lexical = [row(first), row(second)]
    vector = [row(third), row(second)]
    hits = retrieval._fuse(lexical, vector, 3)
    assert hits[0].chunk_id == second
    assert {hit.chunk_id for hit in hits} == {first, second, third}


def test_vector_literal_is_finite_numeric_text():
    assert knowledge._vector_literal([0.1, -2.5]) == "[0.1,-2.5]"
