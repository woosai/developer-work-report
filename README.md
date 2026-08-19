# developer-work-report

여러 로컬 업무 폴더에서 개발 산출물을 수집하고 날짜와 종류별로 정리하여 여러 Google Drive 폴더에 동일하게 업로드하는 Codex 스킬입니다. 정기 수집이 실행되지 않았거나 일부 실패한 경우를 위한 복구 예약도 지원합니다.

## 주요 기능

- 여러 개의 로컬 업무 폴더 지정
- 소스 폴더별 수집 종류와 적용 기간 설정
- 여러 Google Drive 폴더에 동일한 결과물 업로드
- 정상 수집과 실패 복구의 요일·시간 개별 설정
- 문서, Git 변경 patch·요약, AI 세션 사용자 프롬프트 수집
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

## 다중 소스 및 업로드 대상 설정

설정 파일의 `sources`와 `destinations`는 배열이므로 필요한 만큼 항목을 추가할 수 있습니다.

- `sources`: 수집할 로컬 업무 폴더 목록
- `destinations`: 업로드할 Google Drive 폴더 목록
- `automations.collection`: 정상 수집 요일과 시간
- `automations.recovery`: 실패 복구 요일과 시간

각 소스에는 다음 항목을 지정할 수 있습니다.

- 수집할 절대경로
- 문서·코드·프롬프트·기타 중 수집 종류
- 수집 시작일
- 과거 전용 소스의 수집 종료일
- 활성화 여부

예제 설정에는 자리표시자만 들어 있습니다. 로컬 사용자명, 비공개 경로, 실제 Drive 폴더 ID가 포함된 개인 설정 파일은 Git에 커밋하지 마세요.

## GitHub 저장소에 직접 게시

GitHub에서 `developer-work-report`라는 빈 저장소를 만듭니다. 이 패키지에는 이미 README와 `.gitignore`가 있으므로 GitHub 저장소를 만들 때 README, 라이선스, `.gitignore`를 추가하지 않는 것이 좋습니다.

준비된 로컬 폴더에서 다음 명령을 실행합니다.

```bash
git remote add origin https://github.com/woosai/developer-work-report.git
git branch -M main
git push -u origin main
```

원격 저장소를 만들면서 GitHub README를 추가해 이력이 충돌한다면, 원격 내용을 확인한 후 다음과 같이 로컬 패키지로 교체할 수 있습니다.

```bash
git fetch origin main
git push --force-with-lease -u origin main
```

## 사용 방법

Codex에 다음과 같이 요청합니다.

```text
$developer-work-report를 사용해서 검증된 설정 파일 기준으로 정상 수집과 실패 복구 예약을 생성하거나 갱신해줘.
```

로컬 파일을 사용하는 예약 작업은 예약 시각에 컴퓨터가 켜져 있고 데스크톱 앱이 실행 중이어야 합니다. 복구 예약은 다음으로 실행 가능한 예약 시각에 누락 여부를 검사하며, 전원이 켜지는 즉시 실행되는 트리거는 아닙니다.
