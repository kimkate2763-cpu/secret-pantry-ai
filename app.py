
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
logger = logging.getLogger("secret-pantry-ai")

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
GEMINI_BASE_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
)

# 첫 모델이 실패하면 다음 모델을 순서대로 시도
GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-2.5-pro",
]

MAX_OUTPUT_TOKENS = 4096
MAX_LINE_CHARS = 4500
MAX_CONTINUATIONS = 3

SYSTEM_PROMPT = r"""
너는 카카오톡이 아니라 LINE 단체방 '시크릿 펜트리'의
친목 및 규칙 안내 AI야. 사용자는 한국어를 사용해.

[반드시 지킬 답변 원칙]
1. 아래에 적힌 방 규칙을 최우선으로 적용해.
2. 규칙에 없는 내용을 추측해서 만들지 마.
3. 규칙 질문에는 정확하고 직접적으로 답해.
4. 답변은 자연스러운 완성 문장으로 작성해.
5. 제목만 나열하거나 문장 중간에서 끝내지 마.
6. 사용자가 짧게 답하라고 하면 짧게 답해.
7. 긴 답변은 제목과 항목으로 정리하되 결론까지 완성해.
8. 규칙끼리 충돌하거나 정보가 없으면 임의로 정하지 말고
   관리자에게 확인해야 한다고 알려줘.
9. 아래의 규칙을 다른 추측이나 일반적인 관행으로 바꾸지 마.

[방의 기본 용어]
- 야단라: 야한 단체 라인. 성인 친목방이며 일상 대화와
  19금 대화가 있을 수 있어.
- 미클: 미션 클리어.
- 노미클: 미클이 아닌 상태.
- 여성은 입장 시 미클이 돼.
- 남성은 여초 활동 등 정해진 미션을 완료한 뒤 미클이 돼.
- 공창: 단체 채팅방.
- 남초: 남성을 초대하는 활동.
- 여초: 여성을 초대하는 활동.
- 갠라: 개인 LINE 대화.
- 벙: 오프라인 모임.
- 단벙: 3명 이상이 모이는 모임.
- 섹벙: 성적인 목적의 모임.
- 몰벙: 관리자에게 알리지 않고 진행하는 비공개 모임.
- 음통: 음성 통화.
- 영통: 영상 통화.
- 다락/통방: 그룹 통화.
- 매너봉: 정해진 시간대에 19금 사진이나 영상을 올리기 전
  공창에 'ㅁㄴ'이라고 먼저 게시하는 것.
- '~까': 게임에서 진 사람이 사진을 올리는 벌칙을 뜻해.

[갠라 규칙 - 절대 혼동하지 말 것]
- 노미클 남성이 여성에게 먼저 개인 연락을 하는 것은 금지야.
  한 번 적발되면 즉시 강퇴 대상이야.
- 미클 남성은 여성에게 먼저 갠라를 할 수 있어.
- 여성은 미클 남성에게 갠라를 할 수 있어.
- 여성은 노미클 남성에게 먼저 갠라를 할 수 없어.
- 초대한 사람이라는 이유만으로 예외가 생기지 않아.
- 원치 않는 연락, 성적인 발언, 집착이나 강요는 금지야.
- 개인 연락에서 불편한 일이 생기면 관리자에게 신고할 수 있어.
- 개인 연락 관련 신고가 2회 접수되면 강퇴 및 프로필 공개,
  차단 조치 대상이야.

[경고 및 활동 규칙]
- 경고 2회면 강퇴야.
- 주의 3회는 경고 1회에 해당해.
- 읽씹 및 대화 무시는 금지이며 경고 대상이야.
- 하루 50개 이상 메시지를 보내야 해.
- 기준 미달 시 주의 1회야.
- 무분별한 욕설, 허락 없는 '야', '너' 호칭,
  상대방을 불쾌하게 하는 발언은 금지야.
- 뒷담화는 첫 적발 경고, 두 번째 적발 강퇴야.
- 과도한 플러팅과 '너만' 같은 독점적 플러팅은 금지야.
  상대방이 불편해하면 즉시 멈춰야 해.
- 성적인 플러팅은 허용되지만 상대방의 의사를 존중해야 해.
- 도배 및 같은 내용 반복 전송은 금지야.
- 단체방 뒷채팅방을 만드는 것은 금지야.
- 공지와 관리자 지시를 따라야 해.
- 하루 이상 자리를 비우거나 하루 30개 메시지도 어렵다면
  관리자에게 알리고 닉네임 앞에 🛩️를 붙여야 해.
- 활동량 기준이 서로 다르게 안내된 경우에는
  하루 50개 메시지 규칙을 기본 기준으로 설명하고,
  별도의 상황은 관리자에게 확인하라고 해.

[쉿 규칙]
- /쉿은 관리자만 사용할 수 있어.
- 관리자가 '쉿 끝'이라고 공지할 때까지 대화하지 않아야 해.
- 쉿이 끝나면 '확인했습니다'라고 답해야 해.
- @All도 관리자만 사용할 수 있어.

[미클 및 초대 규칙]
- 여성 초대 기준: 여성 2명은 24시간, 여성 1명은 72시간.
- 동반 초대는 초대 실적으로 인정되지 않아.
- 노미클 남성의 승격 조건은 일주일 내 트위터/블루스카이
  홍보글 2,000장 및 총 메시지 30,000개 달성이야.
- 승격 시점 등 구체적인 적용은 관리자에게 확인해.

[사진 및 영상 규칙]
- 다른 사람의 사진이나 영상을 저장하거나 캡처하면 안 돼.
- 적발 시 즉시 강퇴 대상이야.
- 사진과 영상은 가능한 한 워터마크를 사용하고,
  업로드 후에는 전송 취소를 활용해.
- 오전 9시부터 오후 10시까지 19금 사진이나 영상을
  공창에 올릴 때는 먼저 'ㅁㄴ'을 게시해야 해.
- 영상통화 중 화면 캡처나 녹화는 금지야.
- 술에 취한 상태에서 음성 또는 영상 통화를 하면 안 돼.

[벙 규칙]
- 미클 인증을 받은 멤버만 오프라인 모임에 참석할 수 있어.
- 3명 이상 모이는 모임은 방장 또는 부방장에게 알리고
  모임용 채팅방을 만들어야 해.
- 몰벙은 강퇴 대상이야.
- 금전 거래와 연락처 교환은 개인 책임이야.
- 방을 나간 멤버에게 연락하지 않아야 해.
- 강퇴 및 재입장 결정 권한은 방장에게 있어.

[초대 및 인증]
- 여초/남초 신청은 관리자 예빈, 치호, 수박, 멍멍을 태그하고
  각각 '여초 1', '남초 1'이라고 작성해.
- 관리자가 인증방으로 초대해.

[게임 규칙]
진실게임:
- 사다리로 순서를 정하고 사람을 지목해 질문해.
- 질문받은 사람은 솔직히 답하고 다음 사람에게 질문해.
- 답하지 않거나 거짓말을 하거나 다음 질문을 하지 않으면
  19금 사진 벌칙이 있어.
- 일상 질문은 가능하고 동성애 관련 질문은 금지야.

마피아:
- 마피아, 경찰, 의사, 시민 역할을 개인 연락으로 전달해.
- 밤에는 각 역할이 개인적으로 대상을 정해.
- 낮에는 2분 동안 공창에서 토론하고 투표해.
- 최다 득표자가 처형돼.
- 시민 팀이 이기면 마피아가 19금 사진을 올려.
- 마피아 팀이 이기면 사다리로 2명을 정해 19금 사진을 올려.

눈치게임:
- 순서 없이 숫자를 말해.
- 동시에 같은 숫자를 말하면 탈락이야.
- 마지막 생존자도 탈락 처리돼.
- 탈락자와 마지막 생존자는 19금 사진 벌칙이 있어.

19금 손병호:
- 관리자가 순서를 정하고 15초 동안 질문해.
- 해당하는 사람은 손가락 이모지를 하나씩 내려.
- 손가락을 먼저 모두 내린 사람이 승리하고,
  마지막 사람은 19금 사진 벌칙이 있어.
- 손가락 수를 기억해야 해.
- 거짓말이나 규칙을 모른다는 이유로 게임을 방해하면
  참여가 제한될 수 있어.

[답변 예시]
질문: 노미클 남성이 여성에게 먼저 갠라를 하면?
답변: 금지야. 한 번 적발되면 즉시 강퇴 대상이야.

질문: 미클 남성은 여성에게 갠라를 할 수 있어?
답변: 가능해. 다만 상대방이 불편해하는 연락이나
집착, 강요는 금지야.

질문: 규칙이 기억나지 않아.
답변: 현재 안내된 규칙만으로는 정확히 판단하기 어려워.
관리자에게 확인하는 게 좋아.
"""


def line_reply(reply_token, text):
    """LINE에 텍스트를 답장한다."""
    if not LINE_CHANNEL_ACCESS_TOKEN:
        logger.error("LINE_CHANNEL_ACCESS_TOKEN이 설정되지 않았습니다.")
        return False

    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text[:MAX_LINE_CHARS]}],
    }

    try:
        response = requests.post(
            LINE_REPLY_URL,
            headers=headers,
            json=payload,
            timeout=15,
        )
        if response.status_code >= 400:
            logger.error(
                "LINE reply 실패: status=%s body=%s",
                response.status_code,
                response.text[:1000],
            )
            return False
        return True
    except requests.RequestException:
        logger.exception("LINE reply 요청 중 예외 발생")
        return False


def gemini_request(model, contents, max_tokens=MAX_OUTPUT_TOKENS):
    """Gemini API를 한 번 호출한다."""
    url = f"{GEMINI_BASE_URL}{model}:generateContent"

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }

    payload = {
        "systemInstruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.2,
        },
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=35,
    )

    if response.status_code >= 400:
        logger.warning(
            "Gemini 실패: model=%s status=%s body=%s",
            model,
            response.status_code,
            response.text[:1200],
        )
        response.raise_for_status()

    data = response.json()
    candidates = data.get("candidates") or []

    if not candidates:
        feedback = data.get("promptFeedback", {})
        raise RuntimeError(f"Gemini 응답에 후보가 없습니다: {feedback}")

    candidate = candidates[0]
    parts = candidate.get("content", {}).get("parts", [])
    answer = "".join(
        part.get("text", "")
        for part in parts
        if isinstance(part, dict)
    ).strip()

    finish_reason = candidate.get("finishReason", "UNKNOWN")
    logger.info(
        "Gemini 결과: model=%s finishReason=%s chars=%s",
        model,
        finish_reason,
        len(answer),
    )

    if not answer:
        raise RuntimeError(
            f"Gemini 답변이 비었습니다. finishReason={finish_reason}"
        )

    return answer, finish_reason, candidate.get("content")


def ask_gemini(user_prompt):
    """모델을 순서대로 시도하고, 토큰 제한으로 끊기면 이어서 생성한다."""
    if not GEMINI_API_KEY:
        return "Gemini API 키가 설정되지 않았어. Render 환경 변수를 확인해 줘."

    if not user_prompt.strip():
        return "질문을 입력해 줘. 예: !ai 우리 방 규칙을 설명해 줘."

    last_error = None

    for model in GEMINI_MODELS:
        try:
            logger.info("Gemini 모델 시도: %s", model)

            contents = [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ]

            answer, finish_reason, response_content = gemini_request(
                model, contents
            )

            continuation_count = 0

            while (
                finish_reason == "MAX_TOKENS"
                and continuation_count < MAX_CONTINUATIONS
            ):
                continuation_count += 1
                logger.info(
                    "답변 이어쓰기: model=%s attempt=%s",
                    model,
                    continuation_count,
                )

                # 이전 답변과 이어쓰기 지시를 문맥에 포함
                contents.append({
                    "role": "model",
                    "parts": [{"text": answer}],
                })
                contents.append({
                    "role": "user",
                    "parts": [{
                        "text": (
                            "이전 답변이 길이 제한으로 끝났어. "
                            "이미 말한 내용을 반복하지 말고 바로 이어서 "
                            "완성해 줘. 문장을 끝까지 마무리하고 "
                            "남은 항목과 결론을 작성해 줘."
                        )
                    }],
                })

                next_answer, finish_reason, response_content = gemini_request(
                    model, contents
                )
                answer += "\n" + next_answer

            if finish_reason == "MAX_TOKENS":
                answer += (
                    "\n\n※ 답변이 길이 제한에 도달했어. "
                    "빠진 내용은 질문을 나눠서 물어봐 줘."
                )

            # LINE 단일 텍스트 메시지 길이 제한에 대비
            if len(answer) > MAX_LINE_CHARS:
                answer = answer[:MAX_LINE_CHARS - 40].rstrip()
                answer += "\n\n※ 답변이 길어 일부 내용이 생략됐어."

            return answer

        except requests.HTTPError as exc:
            last_error = exc
            status = (
                exc.response.status_code
                if exc.response is not None
                else None
            )

            # 인증/잘못된 요청 오류는 다른 모델로 바꿔도
            # 해결되지 않을 가능성이 높으므로 로그를 남기고 중단
            if status in (400, 401, 403):
                logger.exception(
                    "Gemini 요청 설정 또는 인증 오류: status=%s", status
                )
                break

        except (
            requests.Timeout,
            requests.ConnectionError,
            requests.RequestException,
            ValueError,
            RuntimeError,
        ) as exc:
            last_error = exc
            logger.warning(
                "Gemini 모델 처리 실패: model=%s error=%s",
                model,
                str(exc)[:500],
            )

        except Exception as exc:
            last_error = exc
            logger.exception("예상하지 못한 Gemini 오류")

        time.sleep(1)

    logger.error("모든 Gemini 모델 실패: %s", repr(last_error))
    return (
        "지금은 AI 답변을 가져오지 못했어. 잠시 후 다시 시도해 줘. "
        "같은 오류가 반복되면 관리자에게 알려 줘."
    )


def get_gemini_models():
    """API 키로 조회 가능한 모델 목록을 확인한다."""
    if not GEMINI_API_KEY:
        return "GEMINI_API_KEY가 설정되지 않았어."

    url = "https://generativelanguage.googleapis.com/v1beta/models"

    try:
        response = requests.get(
            url,
            headers={"x-goog-api-key": GEMINI_API_KEY},
            params={"pageSize": 100},
            timeout=20,
        )

        if response.status_code >= 400:
            logger.error(
                "모델 목록 조회 실패: status=%s body=%s",
                response.status_code,
                response.text[:1000],
            )
            return (
                f"모델 목록 조회에 실패했어. "
                f"HTTP 상태 코드: {response.status_code}"
            )

        data = response.json()
        models = []

        for item in data.get("models", []):
            supported = item.get("supportedGenerationMethods", [])
            name = item.get("name", "")

            if "generateContent" in supported and name:
                models.append(name)

        if not models:
            return "사용 가능한 생성 모델을 찾지 못했어."

        return "현재 조회 가능한 텍스트 생성 모델 목록:\n" + "\n".join(
            models[:40]
        )

    except requests.RequestException:
        logger.exception("모델 목록 조회 중 네트워크 오류")
        return "모델 목록 조회 중 네트워크 오류가 발생했어."


@app.route("/", methods=["GET"])
def home():
    return "Secret Pantry AI is running!", 200


@app.route("/health", methods=["GET"])
def health():
    return {
        "status": "ok",
        "line_token_configured": bool(LINE_CHANNEL_ACCESS_TOKEN),
        "line_secret_configured": bool(LINE_CHANNEL_SECRET),
        "gemini_key_configured": bool(GEMINI_API_KEY),
    }, 200


@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_data()

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
        payload = request.get_json(force=True)
    except Exception:
        logger.exception("LINE 요청 JSON 파싱 실패")
        abort(400)

    for event in payload.get("events", []):
        if event.get("type") != "message":
            continue

        message = event.get("message", {})
        if message.get("type") != "text":
            continue

        text_message = message.get("text", "").strip()
        reply_token = event.get("replyToken")

        if not reply_token:
            logger.warning("replyToken이 없는 이벤트")
            continue

        # 모델 목록 명령
        if text_message.lower() == "!aimodels":
            line_reply(reply_token, get_gemini_models())
            continue

        # !ai로 시작하는 메시지만 처리
        if not text_message.lower().startswith("!ai"):
            continue

        # !ai 뒤의 질문 부분만 추출
        user_prompt = text_message[3:].strip()

        if not user_prompt:
            line_reply(
                reply_token,
                "질문을 입력해 줘. 예: !ai 우리 방 규칙을 설명해 줘.",
            )
            continue

        logger.info(
            "AI 질문 수신: chars=%s",
            len(user_prompt),
        )

        answer = ask_gemini(user_prompt)
        line_reply(reply_token, answer)

    return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
