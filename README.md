# developer-work-report

여러 로컬 업무 폴더에서 개발 산출물을 수집하고 날짜와 종류별로 정리하여 여러 Google Drive 폴더에 동일하게 업로드하는 Codex 스킬입니다. 정기 수집이 실행되지 않았거나 일부 실패한 경우를 위한 복구 예약도 지원합니다.

## 주요 기능

- 여러 개의 로컬 업무 폴더 지정
- 본인 Git 작성자 이메일을 하나 이상 지정해 팀원 커밋 제외
- 소스 폴더별 수집 종류와 적용 기간 설정
- 여러 Google Drive 폴더에 동일한 결과물 업로드
- 정상 수집과 실패 복구의 요일·시간 개별 설정
- 문서, Git 변경 patch·요약, AI 세션 사용자 프롬프트 수집
- 모든 브랜치·태그(`git log --all`)를 대상으로 날짜별 전체 커밋 누적
- 커밋 해시·개수·SHA-256 대조 실패 시 업로드 중단
- 프롬프트의 개인정보와 자격증명 강제 마스킹
- 이미 성공한 파일을 중복 업로드하지 않고 전날까지 누락분 복구

## GitHub에서 설치

Codex에 이 저장소의 스킬을 설치해 달라고 요청하거나, 기본 제공 스킬 설치 도구를 사용합니다.

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo woosai/developer-work-report \
  --path . \
  --name developer-work-report
```

설치가 끝나면 다음 Codex 대화부터 `$developer-work-report`로 사용할 수 있습니다.

## 설정 파일 생성

실제 업무 경로와 Drive 주소가 담긴 개인 설정 파일은 설치된 스킬 외부에 생성됩니다.

```bash
python3 ~/.codex/skills/developer-work-report/scripts/developer_work_report_config.py init
```

생성되는 설정 파일:

```text
~/.config/developer-work-report/config.json
```

설정 파일을 수정한 후 경로와 구성값을 검증하고, 생성될 예약 정보와 프롬프트를 미리 확인합니다.

```bash
python3 ~/.codex/skills/developer-work-report/scripts/developer_work_report_config.py validate --check-paths
python3 ~/.codex/skills/developer-work-report/scripts/developer_work_report_config.py render
```

전체 Git 이력을 날짜별로 다시 수집하거나 업로드 전 결과를 검증할 때는 다음 명령을 사용합니다.

```bash
python3 ~/.codex/skills/developer-work-report/scripts/collect_git_history.py \
  --config ~/.config/developer-work-report/config.json \
  --output /private/tmp/developer-work-report-output \
  --from 2025-12-18 \
  --until 2026-08-18
```

수집기는 중첩 Git 저장소를 찾고 모든 브랜치와 태그의 고유 커밋을 날짜별로 먼저 누적한 다음 patch와 요약을 각각 한 번만 기록합니다. 생성된 `git-collection-manifest.json`의 커밋 수·해시·파일 해시가 일치하지 않으면 업로드를 진행하면 안 됩니다.

## 다중 소스 및 업로드 대상 설정

설정 파일의 `sources`와 `destinations`는 배열이므로 필요한 만큼 항목을 추가할 수 있습니다.

- `sources`: 수집할 로컬 업무 폴더 목록
- `destinations`: 업로드할 Google Drive 폴더 목록
- `automations.collection`: 정상 수집 요일과 시간
- `automations.recovery`: 실패 복구 요일과 시간
- `git.author_emails`: 보고서에 포함할 본인 Git 작성자 이메일 목록

각 소스에는 다음 항목을 지정할 수 있습니다.

- 수집할 절대경로
- 문서·코드·프롬프트·기타 중 수집 종류
- 수집 시작일
- 과거 전용 소스의 수집 종료일
- 활성화 여부

예제 설정에는 자리표시자만 들어 있습니다. 로컬 사용자명, 비공개 경로, 실제 Drive 폴더 ID가 포함된 개인 설정 파일은 Git에 커밋하지 마세요.

## 사용 방법

Codex에 다음과 같이 요청합니다.

```text
$developer-work-report를 사용해서 검증된 설정 파일 기준으로 정상 수집과 실패 복구 예약을 생성하거나 갱신해줘.
```

로컬 파일을 사용하는 예약 작업은 예약 시각에 컴퓨터가 켜져 있고 데스크톱 앱이 실행 중이어야 합니다. 복구 예약은 다음으로 실행 가능한 예약 시각에 누락 여부를 검사하며, 전원이 켜지는 즉시 실행되는 트리거는 아닙니다.
