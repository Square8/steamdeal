# GameDil 작업 지도

이 문서는 AI가 매 작업마다 저장소 전체를 다시 읽지 않도록 만든 짧은 기준 문서다.
먼저 이 문서와 `git status --short`를 확인하고, 관련 키워드를 `rg -n`으로 찾은 뒤 필요한 함수 주변만 읽는다.

## 서비스

- 공개 주소: `https://gamedil.com`
- 형태: Python이 SQLite 데이터를 정적 HTML로 생성하고 GitHub Pages가 배포한다.
- 데이터: Steam의 공개 상점 API를 사용하며 API 키는 없다.
- 자동화: `.github/workflows/update.yml`이 매일 두 번 수집·빌드·배포한다.
- 주의: 일반 push 실행은 수집을 건너뛰고 빌드만 한다. 영상·가격 데이터를 새로 채우려면 예약 실행 또는 Actions의 `Run workflow`가 필요하다.

## 파일 지도

| 파일 | 책임 |
|---|---|
| `config.py` | URL, 수집량, 지연시간, 추천 기준 등 설정 |
| `steam.py` | Steam 목록·상세·동접·리뷰·영상 파싱 |
| `store.py` | SQLite 스키마, 저장, 조회, 추천 점수 |
| `collect.py` | 수집 대상 계획 및 수집 실행 |
| `build.py` | 카드, 상세, SEO, JSON-LD, sitemap, 정적 HTML 생성 |
| `theme.py` | 전체 CSS 문자열 |
| `selftest.py` | 네트워크 없이 수행하는 회귀 테스트 |
| `CNAME` | GitHub Pages 커스텀 도메인 |

## 데이터 흐름

`Steam API -> steam.py -> collect.py -> data/steam.sqlite3 -> build.py + theme.py -> site/ -> GitHub Pages`

## 읽기·수정 규칙

1. 저장소 전체 파일을 통째로 읽지 않는다. 먼저 `rg -n "키워드" 대상파일`로 위치를 좁힌다.
2. `site/`, `data/`, `*.sqlite3`, 이미지와 빌드 산출물은 작업에 꼭 필요할 때만 읽는다.
3. 사용자가 만든 미커밋 변경을 보존한다. 시작과 종료에 `git status --short`와 `git diff --stat`을 확인한다.
4. 전체 파일 재작성보다 필요한 부분의 최소 diff를 선호한다.
5. 요청받지 않은 디자인·기능·데이터 구조 변경을 함께 넣지 않는다.
6. 공개 화면의 URL은 `SITE_URL`/`abs_url()`을 사용한다. 저장소 URL과 Steam 외부 URL은 임의로 바꾸지 않는다.
7. 비밀값을 코드에 넣지 않는다. 향후 키가 필요하면 GitHub Secrets를 사용한다.
8. 커밋과 push는 사용자가 명시적으로 요청한 경우에만 한다.

## 변경 후 검증

- 기본 회귀 테스트: `python3 selftest.py`
- 생성기 변경 시: `python3 build.py`
- 생성 결과 확인은 필요한 파일만 대상으로 `rg`를 사용한다.
- 영상 데이터 변경은 push 빌드만으로 DB에 반영되지 않는다. 배포 후 수동 workflow 실행이 필요하다.

## 유지해야 할 제품 원칙

- GameDil은 게임 할인·최저가·한국어 게임 탐색 서비스다.
- 첫 화면은 직관적이고 빠르게 유지한다.
- 홈 카드에서 영상을 자동재생하지 않는다. 트레일러는 상세페이지에서만 제공한다.
- 없는 가격·평점·댓글을 만들어내지 않는다.
- 익명 공개 댓글은 백엔드, 스팸 방지, 신고·삭제 체계가 준비된 뒤 도입한다.
- `localStorage` 키는 기존 이용자 데이터를 지우므로 마이그레이션 없이 변경하지 않는다.

## 현재 작업 시 주의

작업 트리가 깨끗하지 않을 수 있다. 특히 `build.py`, `selftest.py`, `test_related.py`는 관련 게임 추천 작업 중일 수 있으므로 임의로 되돌리거나 덮어쓰지 않는다.
