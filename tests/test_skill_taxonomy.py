from etl.load import canonical_skills


def test_confirmed_aliases_and_composites_have_distinct_canonical_skills() -> None:
    assert canonical_skills("Apache Kafka") == ("Kafka",)
    assert canonical_skills("Core Spring") == ("Spring Core",)
    assert canonical_skills("REST/gRPC") == ("REST", "gRPC")
    assert canonical_skills("CI/CD (GitLab, Jenkins)") == ("CI/CD", "GitLab", "Jenkins")
    assert canonical_skills("Java") != canonical_skills("JavaScript")
    assert canonical_skills("Microservices Архитектура") != canonical_skills("Microservices")
