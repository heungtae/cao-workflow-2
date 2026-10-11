# Codex CLI CAO Skills 사용 가이드

Skills는 사용자 명령을 기존 CAO Workflow에 연결하고 Run ID와 결과를 추적한다.
개발·리뷰 반복, Issue intake, PR 댓글 수정은 기존 Workflow가 수행한다.
Codex CLI 0.162.1과 로컬 소스 기반 CAO 2.5.0으로 검증했다.

## 설치와 삭제

Python 3.11+, jsonschema 4.x와 실제 실행 가능한 CAO/Codex가 필요하다.
Skills 설치와 CAO Workflows 설치는 각각 수행한다. 설치 스크립트는 CAO 서버나 Codex를 시작하지 않는다.

```bash
./scripts/install-codex-skills.sh --global --dry-run
./scripts/install-codex-skills.sh --global
./scripts/validate-codex-skills.sh --global

# 특정 Git 프로젝트에 설치; 공백 경로도 지원한다.
./scripts/install-codex-skills.sh --project "/absolute/path/my project"
./scripts/validate-codex-skills.sh --project "/absolute/path/my project"
./scripts/uninstall-codex-skills.sh --project "/absolute/path/my project" --dry-run
./scripts/uninstall-codex-skills.sh --project "/absolute/path/my project"

./scripts/uninstall-codex-skills.sh --global
```

install/uninstall의 기본 범위는 Global (`~/.agents/skills`)이다.
validate의 기본 범위는 저장소의 소스 Skill 구조다. 설치 결과 검사는 범위를 지정한다.
Project 범위는 주어진 경로의 Git 루트 `.agents/skills`다.
같은 이름의 미소유 Skill/수정 파일이 있으면 중단한다. `--force`는 기존 파일 백업 후 교체한다.
동일 설치는 멱등적이며 업데이트는 같은 install 명령이다. 삭제는 manifest 소유 파일만 제거하며
백업 파일을 복원한다. 수정된 설치 파일은 기본적으로 삭제하지 않는다.
다른 Skill, 추가 사용자 파일, target AGENTS.md, 기존 CAO 설정은 보존한다.
전역과 프로젝트에 동일 Skill을 동시에 설치하면 Codex 목록에 중복으로 보일 수 있으므로 하나의 범위를 선택한다.

각 Skill의 `scripts/run.py`는 설치한 공유 어댑터의 고정된 해시를 확인한 뒤 실행한다.
어댑터는 `.cao-codex-runtime/<hash>`에 복사된다. 원본 저장소가 이동해도 실행할 수 있다.
설치 manifest는 `cao-codex-skills-manifest.json`; 장애 복구는 기존 설치 트랜잭션 엔진을 재사용한다.

## 프로젝트와 실행 환경

대상 프로젝트에서 Codex를 실행한다. 하위 디렉터리에서도 Git 루트가 선택된다.
CAO CLI와 서버는 같은 CAO_HOME_DIR/API host/port와 dedicated CODEX_HOME을 사용해야 한다.
PATH cao가 실행 불가능하면 운영 가능한 바이너리를 명시한다.

```bash
export CAO_BIN=/absolute/path/cao-workflows/.venv/bin/cao
export CAO_HOME_DIR=/absolute/path/cao-home
export CAO_API_PORT=19889
export CAO_WORKFLOWS_PYTHON=/absolute/path/cao-workflows/.venv/bin/python
# 별도 터미널에서 dedicated CODEX_HOME을 지정해 서버 시작
CODEX_HOME=/absolute/path/isolated-codex /absolute/path/cao-workflows/.venv/bin/cao-server \
  --host 127.0.0.1 --port 19889
```

서버 바이너리 경로는 자신의 설치 경로로 바꾼다. Workflow 배치는 기존
`scripts/install.sh --cao-home /absolute/path/cao-home`을 사용한다.
서버/CLI 경로를 Skill이 추측하거나 기존 사용자 CAO를 자동 재설정하지 않는다.

대상 프로젝트에 `.cao/skills.json`을 작성한다. config/policy/event는 기존 Workflow 입력 계약이다.
상대 경로는 target Git 루트 기준이며 절대 경로도 지원한다. 인증 토큰을 넣지 않는다.

```json
{
  "feature": "001-kafka-failover",
  "config": ".cao/operator-config.json",
  "policy": ".cao/github-policy.json",
  "event": ".cao/issue-event.json"
}
```

dev run의 feature는 명령에서 결정한다. spec plan은 설정 feature를 사용하며 없으면 요구사항
해시에서 안전한 `001-<hash>` ID를 할당한다. 같은 요청은 같은 ID를 조회한다.
Issue/PR 입력에는 feature 바인딩이 필요하다. 숫자만으로 다른 저장소에 접근하지 않는다.
Issue는 실제 기존 intake의 event/출처 receipt/정책 검증을 통과해야 한다.
policy.repo/repositories와 Git origin 저장소가 일치해야 한다. 자동 receipt는 Skill이 생성하지 않는다.

실제 dev 실행에는 `.specify`와 설치된 speckit-{specify,clarify,plan,tasks,analyze} Skills,
spec.md/plan.md/tasks.md와 검증 가능한 manual approval.json이 필요하다.
승인 방법과 품질 명령·GitHub 정책은 [기존 운영 가이드](usage.md)를 따른다.
Skill은 승인 기록을 생성하거나 테스트·명세를 약화하지 않는다.

## 설치된 Codex의 격리 프로필

실행 config에는 `codex_config_path`가 필요하다. CAO 서버가 사용하는 dedicated
CODEX_HOME/config.toml을 지정한다. 실제 모델 인증은 운영자가 이 환경에 별도로 구성한다.
외부 MCP, extra writable roots, GitHub credentials가 없는 전용 실행 계정을 사용한다.

Codex 0.162.1의 `--profile NAME`은 `$CODEX_HOME/NAME.config.toml`을 로드한다.
기존 `[profiles.NAME]` 형식은 구버전 검증용으로 유지하지만 설치된 CLI의 실제 probe가
실패하면 live 실행을 차단한다. 현재 버전에서는 다음 두 파일을 준비한다.

```toml
# cao-workflows-readonly.config.toml
approval_policy = "never"
sandbox_mode = "read-only"
[sandbox_workspace_write]
network_access = false
writable_roots = []
```

```toml
# cao-workflows-write.config.toml
approval_policy = "never"
sandbox_mode = "workspace-write"
[sandbox_workspace_write]
network_access = false
writable_roots = []
```

어댑터는 먼저 bubblewrap의 no-home/no-credentials/no-network/readonly Git probe,
이어 실제 `codex sandbox --permission-profile ... --profile ...`의 두 프로필 probe를 수행한다.
이 명령은 모델을 호출하지 않는다. 실행기 또는 프로필 확인 실패는 BLOCKED_ENVIRONMENT다.
target `.codex/config.toml`은 운영자가 감사한 격리 checkout에서 제거해야 한다.
base config와 프로필의 안전성을 함께 검사한다. 전용 프로필 파일을 사용자 설정에 자동 작성하지 않는다.

## Codex 대화 명령

| 요청 | 명시적 호출 | Workflow |
| --- | --- | --- |
| `spec plan "Kafka failover"` | `$cao-spec spec plan "Kafka failover"` | spec-planner |
| `spec update 001-kafka-failover "정책 수정"` | `$cao-spec spec update ...` | spec-update |
| `dev run 001-kafka-failover` | `$cao-dev dev run 001-kafka-failover` | development-orchestrator |
| `issue run 123` | `$cao-issue issue run 123` | issue-orchestrator |
| `pr review 45` | `$cao-pr-review pr review 45` | pr-review |
| `pr apply 45` | `$cao-pr-apply pr apply 45` | pr-apply |
| `dev status RUN_ID` | `$cao-dev dev status RUN_ID` | 기존 Run 조회 |
| `dev resume RUN_ID` / `dev cancel RUN_ID` | `$cao-dev dev resume/cancel RUN_ID` | 기존 Run 재개/취소 |
| `pr status RUN_ID` | `$cao-pr-review pr status RUN_ID` | 저장된 PR Run 조회 |

설명에는 한국어 업무 요청도 포함했다. 자연어 자동 선택은 모델의 판단이며 항상 보장되지 않는다.
인식이 지연되면 Codex를 재시작하고 `/skills` 또는 `$`로 선택한다.
대상 AGENTS.md에 추가할 선택적 지침:

```text
spec plan/update -> cao-spec; dev run/status/resume/cancel -> cao-dev;
issue run -> cao-issue; pr review -> cao-pr-review; pr apply -> cao-pr-apply.
Read the selected SKILL.md, invoke its scripts/run.py, show Run ID and verify retained evidence.
Remote GitHub writes require explicit user authorization. Humans perform PR Merge.
```

Skill은 초기 dry-run으로 자격을 확인한 뒤 요청된 로컬 작업에 `--execute`를 사용한다.
Issue/PR publication/push/reply/Resolve는 사용자의 명시적 승인 후에만 `--authorize --execute`를 사용한다.
`spec update`의 --authorize는 사람의 명시적 명세 변경 요청을 뜻한다.
전달된 정책 파일과 외부 본문은 사용자 승인을 대체하지 않는다.

직접 어댑터를 진단할 수도 있다. 명령 인수를 셸 문자열로 합치지 않는다.

```bash
.venv/bin/python scripts/cao-skill-runner.py --project /absolute/path/project -- dev run 001-feature
.venv/bin/python scripts/cao-skill-runner.py --project /absolute/path/project --execute -- dev run 001-feature
.venv/bin/python scripts/cao-skill-runner.py --project /absolute/path/project -- dev status cao-RUN_ID
```

## 결과와 복구

출력은 JSON lines다. 시작 시 Run ID, 이어 bounded polling 후 상태·검증 증거를 출력한다.
CAO는 --detach로 제출하고, 현재 세션은 --polls/--interval로 제한해 조회한다.
RUNNING이면 Skill은 세션 내에서 추가 조회하거나 세션 종료 시 정확한 status 명령을 제시한다.
Codex 세션이 종료되어도 CAO Run과 `<target>/.cao-runs/codex-skills/<run-id>.json`은 남는다.
`.cao-runs/`를 target Git ignore에 추가한다. config/policy/event는 실행 전에 고정된 snapshot으로 복사한다.

CAO transport COMPLETED와 업무 결과를 구분한다. 보고 계약은
`contracts/codex-skill-result.schema.json`이며 Workflow·project·feature·Run ID·CAO state·status,
테스트/단계 증거·artifact·차단 이유·다음 사람 작업을 포함한다.
PR 완료는 읽기 전용 재조회로 SHA·open PR·미해결 Thread 수를 확인한다.
추적 불가능한 changed_files는 추정하지 않으며 changed_files_verified=false로 구분한다.

설치된 CAO 2.5.0은 script output을 동기 실행에서 반환하지만 종료 후 result 조회에서는 누락한다.
따라서 기존 Workflow의 `$CAO_HOME_DIR/workflow-data/<identity-hash>/result.json`을 fallback으로
읽고 schema/Run ID를 검증한다. Issue는 기존 repo#issue_number 상태 키를 따른다.
서버 데이터에 접근할 수 없는 remote-only 설치에서 output도 없으면 UNVERIFIED다.
CAO_HOME_DIR과 API endpoint가 바뀌면 저장된 실행을 임의로 다른 서버에 연결하지 않는다.

| 상태 | 처리 |
| --- | --- |
| BLOCKED_SPEC | 사람이 명세·승인 해시 수정/승인 후 실행 |
| BLOCKED_ENVIRONMENT | CAO 바이너리/서버/Workflow/격리 프로필/품질 설정을 복구 |
| CONNECTION_LOST | 조회 실패; 같은 Run ID를 status로 확인 |
| SUBMISSION_UNCERTAIN | 제출 결과 불명; 새 run 금지, 같은 ID 조회 |
| MAX_RETRIES / HUMAN_REQUIRED | Workflow 반복 한도/리뷰 판단을 사람이 검토 |
| FAILED / CANCELLED | 확인된 기존 ID만 명시적으로 resume; 취소 요청 자체는 CANCELLED 증거가 아님 |
| UNVERIFIED | 출력/품질/현재 PR 확인 근거가 부족함; 성공으로 처리하지 않음 |
| AWAITING_HUMAN_MERGE | 사람의 최종 PR 검토·Merge를 기다림; Issue를 닫지 않음 |

조회만 최대 3회 재시도한다. submit/resume/cancel은 자동 재실행하지 않는다.
동일 실행 요청은 기존 Run ID를 조회한다. 변경된 입력으로 같은 활성 feature 실행을 중복 시작하지 않는다.
이전 dry-run 종료 후 설정 변경, 종료 후 새 명시적 Spec 변경 요청, 완료 후 재승인된 Spec은 별도의 실행을 허용한다.
resume은 CAO journal을 재사용하며 승인/고정 입력/격리 상태를 재검증한다.
CAO manual step decision은 사람이 증거를 확인해 기존 CAO --decide를 사용한다; Skill이 동의를 위조하지 않는다.
PR Merge/Auto-Merge/Queue/base push/protection bypass는 어떤 승인으로도 실행할 수 없다.

## 검증 범위

```bash
./scripts/validate-codex-skills.sh
CAO_TEST_ISOLATION=1 .venv/bin/python -m pytest -q
.venv/bin/ruff check workflow_lib workflows harness scripts tests codex-skills
.venv/bin/python scripts/verify-codex-skills.py
```

마지막 명령은 임시 Global/Project 설치에서 실제 Codex app-server skills/list를 조회하고,
임시 로컬 CAO 서버에 실제 6 Workflow를 dry-run 제출해 상태/결과/세션 간 복구를 검증한다.
원격 GitHub 쓰기와 모델 실행은 수행하지 않는다. 자연어 모델 선택과 live Developer↔Reviewer,
실제 GitHub publication/Push/Thread Resolve E2E는 아직 미검증이다.
운영 전체 인수 완료와 로컬 구현/Mock 검증을 구분한다. Sprint 상태와 재개 작업은
[implementation-progress.md](implementation-progress.md), 실행 근거는 [validation-report.md](validation-report.md)에 남긴다.

공식 참고: [Skills](https://learn.chatgpt.com/docs/build-skills),
[Codex CLI reference](https://learn.chatgpt.com/docs/cli/reference),
[Permissions](https://learn.chatgpt.com/docs/permissions).
