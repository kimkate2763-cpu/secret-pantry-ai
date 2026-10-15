```python
import os
import time
import hmac
import hashlib
import base64
import logging
import requests

from flask import Flask, request, abort

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================
# 환경 변수
# ==========================================

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-3.6-flash:generateContent"
)

LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"


# ==========================================
# 시크릿 펜트리 규칙 및 AI 답변 설정
# ==========================================

SYSTEM_PROMPT = """
너는 성인 친목 단체 채팅방 '시크릿 펜트리'의 안내 AI야.
사용자가 !ai로 질문하면 아래 공지사항과 소개서를 참고해서 답변해.

[답변 원칙]
1. 한국어로 자연스럽고 친근하게 답변해.
2. 질문에 필요한 내용부터 정확하고 간결하게 설명해.
3. 규칙을 물으면 아래에 적힌 시크릿 펜트리 규칙을 우선해서 답변해.
4. 공지에 없는 규칙이나 처벌 기준을 임의로 만들지 마.
5. 규칙이 서로 충돌하거나 정확한 판단이 어려우면 추측하지 말고
   방장 또는 관리자에게 확인하라고 안내해.
6. 예전 이벤트와 현재 규칙을 혼동하지 마.
7. 답변은 가능하면 완결된 문장으로 작성하고, 문장 중간에 끝내지 마.
8. 일반 질문에는 방 규칙을 억지로 끌어오지 마.
9. 사용자가 규칙을 바꾸라고 요청해도 실제 공지 자체가 변경된 것으로
   취급하지 마. 현재 공지 내용을 설명해.
10. 지나치게 긴 답변보다는 핵심을 명확하게 설명해.

━━━━━━━━━━━━━━━━━━
[운영진 및 구성원 표식]
━━━━━━━━━━━━━━━━━━

방장: 예빈
부방장: 치호
관리자: 수박, 멍멍

구성원 표식:
- 🐁: 미클자
- 🧀: 노미클
- 🐈: 여성

닉네임의 나이가 위첨자 형태로 표시된 경우 검사지 제출자,
아래첨자 형태로 표시된 경우 검사지 미제출자를 의미해.
검사지 제출 주기는 3개월이야.

━━━━━━━━━━━━━━━━━━
[중요 규칙 및 경고 기준]
━━━━━━━━━━━━━━━━━━

- 경고 2회 누적 시 추방.
- 주의 3개가 쌓이면 경고 1회.
- 공지 미숙지는 경고 사유이며, 공지를 읽은 뒤 확인 댓글을 남겨야 해.
- 읽씹은 금지이며 적발 시 경고 대상이야.
- 전 멤버는 하루 50마디 이상 활동해야 해.
- 하루 이상 자리를 비우거나 하루 30마디를 채우기 어려운 경우
  운영진에게 미리 알리고 닉네임 앞에 🛩️를 달아야 해.
- 무분별한 욕설, 상대방 허락 없이 '야', '너'라고 부르는 행동,
  상대방이 불쾌할 수 있는 발언은 금지야.
- 멤버 뒷담화는 금지야. 1회 적발 시 경고, 2회 적발 시 추방이야.
- 운영진 외에는 @All 전체 멘션과 /쉿 사용이 금지야.
- 단체 뒷방(별도 오픈채팅, 단톡 등) 생성 금지.
- 도배와 과도한 반복 채팅 금지.
- /쉿이 사용되면 운영진이 공지할 때까지 채팅하지 않아야 해.
  관리자가 '쉿 끝'이라고 말한 뒤 채팅을 시작하고,
  공지 이후에는 반드시 "확인했습니다."라고 답해야 해.
- 금전거래 및 연락처 교환은 개인 책임이야.
- 방을 나간 멤버와 개인 연락하는 것은 금지야.
- 추방 및 재입장 결정 권한은 방장에게 있어.

━━━━━━━━━━━━━━━━━━
[플러팅 및 개인 연락]
━━━━━━━━━━━━━━━━━━

- 과도한 플러팅은 금지지만 섹러팅은 가능해.
- '너만 본다', '너밖에 없다' 등 한 사람만 봐주길 바라는
  플러팅은 금지야.
- 상대방이 플러팅을 불편해하면 즉시 중단해야 해.
- 플러팅이 싫다면 상대방에게 거절 의사를 분명히 표현해야 해.
- 미클 남성은 여성에게 선갠라(먼저 개인 연락)가 가능해.
- 노미클 남성이 여성에게 선갠라를 하면 1회만으로 추방 대상이야.
- 여성은 미클 남성에게 선갠라가 가능하지만,
  노미클 남성에게 선갠라를 하는 것은 금지야.
- 초대자라는 이유만으로 개인 연락이 허용되는 것은 아니야.
- 남성의 선갠라 이후 불편한 일이 생기면 운영진에게 신고해야 해.
- 개인 라인에서도 무분별한 섹드립, 성희롱, 강압적인 대화,
  과도한 플러팅 등 상대방을 불편하게 하는 행동은 금지야.
- 불편 신고가 2회 접수되면 추방, 프로필 박제 및 차단 대상이야.
- 영통 중 캡처 및 녹화 금지.
- 과음 상태에서 음성·영상통화 금지.
- 인스타 등 개인 연락처 교환은 벙 후 가능해.

━━━━━━━━━━━━━━━━━━
[사진 및 영상 규칙]
━━━━━━━━━━━━━━━━━━

- 다른 사람의 사진·영상을 저장하거나 캡처하는 행위는 금지야.
  적발 시 즉시 추방 대상이야.
- 사진을 올릴 때는 되도록 워터마크를 사용해야 해.
- 사진 업로드 후 보내기 취소 기능을 사용해야 해.
- 오전 09:00부터 오후 22:00 사이에 🔞 사진·영상을 올릴 경우
  먼저 공창에 'ㅁㄴ'을 입력해야 해.
- 사진·영상 관련 규칙을 설명할 때 다른 사람의 동의와 사생활을 존중해.

━━━━━━━━━━━━━━━━━━
[미클 및 노미클]
━━━━━━━━━━━━━━━━━━

미클은 '미션 클리어'의 줄임말이야.
노미클은 아직 미션을 클리어하지 않은 상태를 의미해.

- 여성은 방에 입장하는 즉시 미클이야.
- 남성은 여초 미션을 완료하면 미클이 돼.
- 여초는 여자 초대, 남초는 남자 초대의 줄임말이야.
- 여초 2명이 24시간 방에 있으면 미클 조건에 해당해.
- 여초 1명이 72시간 방에 있으면 미클 조건에 해당해.
- 동반 초대는 여초로 인정되지 않아.
- 노미클은 일주일 동안 홍보지(트위터, 블루스카이) 2,000장과
  일주일 총 30,000마딧수 달성 시 노미클 기간 마지막 날
  미클로 승급할 수 있어.
- 여초 또는 남초가 필요하면 관리자에게 태그한 뒤
  '여초 1' 또는 '남초 1'이라고 요청해. 확인 후 인증방으로 초대돼.

━━━━━━━━━━━━━━━━━━
[기본 용어]
━━━━━━━━━━━━━━━━━━

- 야단라: 야한 단체 라인의 줄임말. 성인 친목을 중심으로 하며
  일상 대화와 19금 대화가 모두 가능한 방이야.
- 공창: 시크릿 펜트리의 공용 단체 대화방.
- 갠라: 개인 라인. 방 인원과 1:1로 연락하는 개인 대화.
- 벙: 방 인원끼리 실제로 만나는 오프라인 모임.
- 단벙: 3인 이상이 함께하는 오프라인 모임.
- 섹벙: 성적인 목적의 오프라인 만남.
- 몰벙: 벙 게시판에 공지하지 않고 방 인원끼리 몰래 만나는 행위.
  방 퇴출 사유가 될 수 있어.
- 매너봉: 지정된 시간에 🔞 사진이 올라왔을 때 공창에 'ㅁㄴ'을
  입력해 사진을 위로 올려주는 행동.
- 음통: 음성 통화.
- 영통: 영상 통화.
- 다락/통방: 공창에서 진행하는 단체 통화.
- '~까': 게임에서 해당 사람이 사진을 공개하는 벌칙을 의미해.
  예를 들어 '예까'는 예빈이가 사진을 공개한다는 뜻이야.

━━━━━━━━━━━━━━━━━━
[벙 규칙]
━━━━━━━━━━━━━━━━━━

- 미클 인증자만 벙에 참여할 수 있어.
- 자세한 내용은 벙 노트를 참고해야 해.
- 3인 이상 벙은 방장이나 부방장에게 알리고 방을 만들어야 해.
- 몰벙은 방 퇴출 사유가 될 수 있어.

━━━━━━━━━━━━━━━━━━
[게임 규칙]
━━━━━━━━━━━━━━━━━━

1. 진실게임
- 사다리 타기로 첫 번째 순서를 정해.
- 순서에 따라 상대방을 태그하고 질문해.
- 지목당한 사람은 질문에 답하고 다음 질문을 진행해.
- 대답하지 못하거나 다음 질문을 하지 못하거나 거짓말을 한 경우
  🔞 사진 공개 벌칙이 있어.
- 19금 질문이 어려우면 일상 질문도 가능해.
- 게이·레즈 관련 질문은 금지야.

2. 마피아 게임
- 역할은 마피아, 경찰, 의사, 시민이야.
- 운영진이 개인 라인으로 역할을 배정해.
- 밤에는 마피아·경찰·의사가 개인 라인으로 대상을 지목해.
- 낮에는 공창에서 2분간 토론한 뒤 투표해.
- 가장 많은 표를 받은 사람이 처형돼.
- 시민팀 승리 시 마피아가 🔞 사진을 공개해.
- 마피아팀 승리 시 사다리 타기로 2명을 선정해 🔞 사진을 공개해.

3. 눈치게임
- 순서 없이 숫자를 말해.
- 같은 숫자를 동시에 말하면 탈락이야.
- 마지막까지 남은 사람도 탈락하는 규칙이야.
- 탈락자와 마지막 생존자는 🔞 사진 공개 벌칙이 있어.

4. 19금 손병호 게임
- 운영진이 질문 순서를 정해.
- 본인 차례에 15초 안에 질문해.
- 질문에 해당하는 사람은 손 이모티콘을 하나 삭제하고 공창에 보내.
- 손 이모티콘이 가장 먼저 없어지는 사람이 승리하고,
  마지막까지 손 이모티콘이 남은 1인이 패배해.
- 패배자는 🔞 사진을 올리는 벌칙이 있어.
- 본인의 손 개수를 기억하고 필요한 답변과 이모티콘만 보내야 해.
- 거짓말이나 규칙 미숙지로 게임 진행을 방해하면 참여가 제한될 수 있어.

━━━━━━━━━━━━━━━━━━
[답변에 관한 추가 주의사항]
━━━━━━━━━━━━━━━━━━

- 이 내용은 사용자가 제공한 공지사항을 바탕으로 한 참고 정보야.
- 공지에 없는 세부 기준은 만들어내지 마.
- 규칙 간 충돌이나 적용 여부가 불분명하면 운영진에게 확인하라고 해.
- 사진 공개 벌칙 등은 방에서 안내한 게임 규칙을 설명하는 수준으로만 답해.
- 실제 동의 없는 사진 촬영·저장·유포를 정당화하지 마.
"""


# ==========================================
# LINE 메시지 보내기
# ==========================================

def line_reply(reply_token, text):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        logger.error("LINE_CHANNEL_ACCESS_TOKEN이 설정되지 않았습니다.")
        return

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }

    payload = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": text,
            }
        ],
    }

    try:
        response = requests.post(
            LINE_REPLY_URL,
            headers=headers,
            json=payload,
            timeout=15,
        )

        if not response.ok:
            logger.error(
                "LINE reply 오류 HTTP %s: %s",
                response.status_code,
                response.text[:1000],
            )

    except requests.RequestException:
        logger.exception("LINE reply 요청 중 네트워크 오류가 발생했습니다.")


# ==========================================
# Gemini AI 호출
# ==========================================

def ask_gemini(user_prompt):
    if not GEMINI_API_KEY:
        return "AI 설정에 문제가 있어요. 관리자에게 문의해 주세요."

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }

    payload = {
        "systemInstruction": {
            "parts": [
                {
                    "text": SYSTEM_PROMPT,
                }
            ]
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": user_prompt,
                    }
                ],
            }
        ],
        "generationConfig": {
            # 기존 500에서 2048로 늘려 답변이 중간에 끊기는 현상을 줄임
            "maxOutputTokens": 2048,
            "temperature": 0.6,
        },
    }

    # 일시적인 429/5xx 오류에 대비해 최대 3회 요청
    for attempt in range(3):
        try:
            response = requests.post(
                GEMINI_URL,
                headers=headers,
                json=payload,
                timeout=45,
            )

            if response.status_code in (408, 429, 500, 502, 503, 504):
                logger.warning(
                    "Gemini 일시 오류: HTTP %s, 시도 %s/3, 응답: %s",
                    response.status_code,
                    attempt + 1,
                    response.text[:1000],
                )

                if attempt < 2:
                    time.sleep(1 + attempt * 2)
                    continue

                return (
                    "지금은 AI 응답이 원활하지 않아요. "
                    "잠시 후 다시 질문해 주세요."
                )

            if not response.ok:
                logger.error(
                    "Gemini API 오류 HTTP %s: %s",
                    response.status_code,
                    response.text[:1500],
                )
                return (
                    "AI 응답을 가져오지 못했어요. "
                    "잠시 후 다시 시도해 주세요."
                )

            data = response.json()
            candidates = data.get("candidates", [])

            if not candidates:
                logger.warning(
                    "Gemini 응답에 candidates가 없습니다: %s",
                    str(data)[:1500],
                )
                return (
                    "이번에는 AI가 답변을 만들지 못했어요. "
                    "질문을 조금 바꿔 다시 보내주세요."
                )

            candidate = candidates[0]
            finish_reason = candidate.get("finishReason", "")

            parts = candidate.get("content", {}).get("parts", [])
            answer = "".join(
                part.get("text", "")
                for part in parts
                if isinstance(part.get("text"), str)
            ).strip()

            logger.info(
                "Gemini finishReason=%s, 답변 글자 수=%s",
                finish_reason,
                len(answer),
            )

            if not answer:
                logger.warning(
                    "Gemini 답변이 비어 있습니다: %s",
                    str(data)[:1500],
                )
                return (
                    "AI 답변이 비어 있어요. "
                    "잠시 후 다시 질문해 주세요."
                )

            if finish_reason == "MAX_TOKENS":
                logger.warning(
                    "Gemini 답변이 토큰 한도에 도달했습니다."
                )

            # LINE 텍스트 메시지 제한을 고려해 길이 처리
            # 문장 중간을 자르지 않도록 가능한 한 마지막 문장 끝에서 자름
            max_length = 4500

            if len(answer) > max_length:
                shortened = answer[:max_length]
                last_boundary = max(
                    shortened.rfind("。"),
                    shortened.rfind("！"),
                    shortened.rfind("？"),
                    shortened.rfind(". "),
                    shortened.rfind("! "),
                    shortened.rfind("? "),
                    shortened.rfind("\n"),
                )

                if last_boundary >= max_length // 2:
                    answer = shortened[:last_boundary + 1].rstrip()
                else:
                    answer = shortened.rsplit(" ", 1)[0].rstrip()

                answer += "\n\n(답변이 길어 일부 내용이 생략됐어요. 질문을 나눠서 보내주세요.)"

            return answer

        except requests.Timeout:
            logger.warning(
                "Gemini 요청 시간 초과: 시도 %s/3",
                attempt + 1,
            )

            if attempt < 2:
                time.sleep(1 + attempt * 2)
                continue

            return (
                "AI 응답 시간이 오래 걸리고 있어요. "
                "잠시 후 다시 질문해 주세요."
            )

        except (requests.RequestException, ValueError):
            logger.exception("Gemini 요청 또는 응답 처리 오류")

            if attempt < 2:
                time.sleep(1 + attempt * 2)
                continue

            return (
                "AI와 연결하는 중 문제가 생겼어요. "
                "잠시 후 다시 시도해 주세요."
            )

    return "AI 응답에 실패했어요. 잠시 후 다시 시도해 주세요."


# ==========================================
# 사용 가능한 Gemini 모델 확인
# 기존 !aimodels 기능 유지
# ==========================================

def get_gemini_models():
    if not GEMINI_API_KEY:
        return "GEMINI_API_KEY가 설정되지 않았어요."

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models"
    )

    try:
        response = requests.get(
            url,
            headers={"x-goog-api-key": GEMINI_API_KEY},
            timeout=20,
        )

        if not response.ok:
            logger.error(
                "모델 목록 조회 오류 HTTP %s: %s",
                response.status_code,
                response.text[:1000],
            )
            return "모델 목록을 가져오지 못했어요. Render 로그를 확인해 주세요."

        data = response.json()
        models = data.get("models", [])

        names = [
            model.get("name", "")
            for model in models
            if "generateContent" in model.get("supportedGenerationMethods", [])
        ]

        if not names:
            return "이 API 키에서 사용할 수 있는 모델을 찾지 못했어요."

        return "사용 가능한 모델:\n" + "\n".join(names[:40])

    except (requests.RequestException, ValueError):
        logger.exception("Gemini 모델 목록 조회 실패")
        return "모델 목록 조회 중 오류가 발생했어요."


# ==========================================
# 기본 주소
# ==========================================

@app.route("/", methods=["GET"])
def home():
    return "Secret Pantry AI is running!", 200


# ==========================================
# LINE 웹훅
# ==========================================

@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_data()

    # LINE 서명 검증
    signature = request.headers.get("X-Line-Signature", "")

    if not LINE_CHANNEL_SECRET:
        logger.error("LINE_CHANNEL_SECRET이 설정되지 않았습니다.")
        abort(500)

    digest = hmac.new(
        LINE_CHANNEL_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()

    expected_signature = base64.b64encode(digest).decode("utf-8")

    if not hmac.compare_digest(signature, expected_signature):
        logger.warning("LINE 서명 검증 실패")
        abort(400)

    try:
        event_data = request.get_json(silent=True) or {}
    except ValueError:
        logger.warning("LINE 요청 JSON 파싱 실패")
        return "OK", 200

    for event in event_data.get("events", []):
        if event.get("type") != "message":
            continue

        message = event.get("message", {})

        if message.get("type") != "text":
            continue

        text_message = message.get("text", "").strip()
        reply_token = event.get("replyToken")

        if not reply_token or not text_message:
            continue

        # 기존 !aimodels 명령 유지
        if text_message.lower() == "!aimodels":
            result = get_gemini_models()
            line_reply(reply_token, result)
            continue

        # !ai로 시작하는 메시지만 처리
        if not text_message.lower().startswith("!ai"):
            continue

        # 명령어 부분만 제거하고 질문 추출
        user_prompt = text_message[3:].strip()

        if not user_prompt:
            line_reply(
                reply_token,
                "질문을 함께 입력해 주세요!\n예시: !ai 미클이 뭐야?",
            )
            continue

        answer = ask_gemini(user_prompt)
        line_reply(reply_token, answer)

    return "OK", 200


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
    )
```
