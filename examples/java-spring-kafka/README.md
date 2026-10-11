# Java Spring Kafka target example

Use an existing Git project, with Maven wrapper, installed Spec Kit skills and a feature such as `001-kafka-failover`. Plan acceptance criteria with explicit REQ IDs (active consumer switching, idempotency, concurrency and recovery). Commit and manually approve spec/plan/tasks before development.

An operator may configure offline Maven commands:

```json
{
  "quality": {
    "test": {"argv": ["./mvnw", "-o", "-B", "test"], "junit": "target/surefire-reports/TEST-*.xml"},
    "static": {"argv": ["./mvnw", "-o", "-B", "checkstyle:check"]},
    "coverage": {"argv": ["./mvnw", "-o", "-B", "verify"]},
    "timeout_seconds": 600,
    "readonly_roots": ["/opt/java", "/opt/cao-maven-cache"]
  }
}
```

These are configuration examples, not a claim that a Spring/Kafka service was executed in this repository. The target must define Checkstyle and a enforcing coverage threshold in its POM, and preinstall dependencies in a credential-free cache visible to its isolated wrapper. No external Kafka cluster or production data is accessed by validation.
