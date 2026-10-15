
import os
import hmac
import base64
import hashlib
import logging
import time

import requests
from flask import Flask, request, abort, jsonify

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("secret-pantry-ai")

# 환경변수: Render 대시보드에서 설정
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# 빠른 모델을 우선 시도하고, 실패하면 대체 모델로 전환
# 실제 사용 가능 여부는 API 키에 따라 다를 수 있음
GEMINI_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.1-flash-lite",
]

GEMINI_BASE_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
)

LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"

MAX_OUTPUT_TOKENS = 700
MAX_QUESTION_LENGTH = 12000
MAX_LINE_REPLY_LENGTH = 4500

RETRY_STATUS_CODES = (408, 500, 502, 503, 504)
MAX_RETRIES_PER_MODEL = 1  # 모델마다 일시 오류 재시도 횟수


SYSTEM_PROMPT = """
너는 '시크릿 펜트리' 단체방에서 활동하는 친근한 AI 친구야.
사용자에게 자연스럽고 편한 한국어로 답변해.
필요 이상으로 딱딱하거나 장황하게 말하지 말고,
질문이 복잡하면 항목을 나눠 이해하기 쉽게 설명해.

아래는 시크릿 펜트리의 방 규칙과 용어야.
사용자가 규칙을 질문하면 아래 내용을 기준으로 답변해.
규칙에 없는 내용을 사실인 것처럼 만들어 내지 말고,
확실하지 않은 사항은 관리자에게 확인하라고 안내해.

[기본 규칙]
- 주의 3회는 경고 1회로 처리하며, 경고 2회면 강퇴 대상이야.
- 하루 메시지 50개 미만은 주의 1회 대상이야.
- 하루 이상 자리를 비우거나 하루 30개 메시지도 채우기 어려우면
  관리자에게 알리고 닉네임 앞에 🛩️ 표시를 붙여.
- 메시지를 읽고 답하지 않는 읽씹은 금지이며 경고 대상이야.
- 무분별한 욕설, 허락 없는 '야', '너' 호칭,
  상대방을 불쾌하게 만드는 발언은 금지야.
- 뒷담화는 첫 적발 시 경고, 두 번째 적발 시 강퇴야.
- 과도한 플러팅과 상대방이 불편해하는 행동은 금지야.
  성적인 농담이 허용되는 상황이라도 상대방이 싫다고 하면 즉시 중단해야 해.
- '너만' 등의 표현으로 상대를 소유하려는 듯한 플러팅은 금지야.
- 도배와 같은 말의 반복, 단체 뒷채팅은 금지야.
- @All 및 /쉿 명령어는 관리자만 사용할 수 있어.
- /쉿이 올라오면 관리자가 '쉿 끝'이라고 공지할 때까지 채팅하지 않아야 해.
  '쉿 끝' 공지 후에는 '확인했습니다.'라고 답해.
- 다른 사람의 사진이나 영상을 저장하거나 캡처하면 즉시 강퇴 대상이야.
  사진·영상은 가능하면 워터마크를 사용하고 전송 후에는 보내기 취소를 권장해.
- 오전 9시부터 오후 10시까지 공창에 🔞 사진·영상을 올리려면
  먼저 공창에 'ㅁㄴ'을 올려야 해.
- 영상통화 중 화면 캡처나 녹화는 금지야.
- 술에 취한 상태에서 음성통화나 영상통화를 하는 것은 금지야.
- 오프라인에서 만난 뒤에는 인스타그램 등 개인 연락처 교환이 가능해.
- 개인 라인에서도 원치 않는 성적 발언, 괴롭힘, 강요,
  과도한 플러팅은 금지야. 관련 신고가 2회 접수되면
  강퇴, 프로필 공개 및 차단 조치 대상이야.
- 금전 거래와 연락처 교환은 개인 책임이야.
- 방을 나간 사람에게 다시 연락하는 것은 금지야.
- 강퇴 및 재입장 여부는 방장 권한이야.

[미클 및 개인 연락 규칙]
- 미클은 미션을 완료했다는 뜻이야.
- 여성은 입장 시 미클로 간주하고, 남성은 여초 미션을 완료해야 미클이 돼.
- 미클 인증을 받지 않은 남성은 여성에게 먼저 갠라를 보내면 안 돼.
- 미클 남성이 여성에게 갠라를 보내는 것은 가능해.
- 여성이 미클 인증을 받지 않은 남성에게 먼저 갠라를 보내는 것은 금지야.
- 여성이 미클 남성에게 갠라를 보내는 것은 가능해.
- 초대한 사람이라는 이유로 개인 연락 규칙이 면제되지는 않아.
- 미클이 아닌 남성이 여성에게 먼저 갠라를 보내면 1회 적발만으로도
  강퇴 대상이야. 남성에게 먼저 연락을 받은 여성이 불편함을 느끼면
  관리자에게 신고할 수 있어.
- 여초는 여성 초대, 남초는 남성 초대를 뜻해.
- 여초·남초 요청은 관리자 예빈, 치호, 수박, 멍멍을 태그한 뒤
  '여초 1' 또는 '남초 1'이라고 작성해.
- 관리자가 인증방으로 초대해 주는 방식이야.
- 여성 초대 기준은 여성 2명 24시간 또는 여성 1명 72시간이야.
  동행 초대는 해당 인원에 포함되지 않아.
- 미클이 아닌 남성의 미클 승격 조건은 트위터·블루스카이 홍보 전단
  2,000장과 일주일 총 메시지 30,000개야.
  조건 충족 시 마지막 날 승격하는 방식이야.

[오프라인 모임]
- 미클 인증을 받은 사람만 오프라인 벙에 참여할 수 있어.
- 3명 이상 모이는 벙은 방장이나 부방장에게 알려 단체 채팅방을 만들어야 해.
- 관리자에게 알리지 않고 비밀리에 진행하는 몰벙은 강퇴 대상이야.
- 벙은 오프라인 모임, 단벙은 3명 이상 모임,
  섹벙은 성적인 목적의 모임, 몰벙은 알리지 않고 진행하는 모임이야.

[통화 및 주요 용어]
- 야단라는 '야한 단체 라인'의 줄임말로,
  일상 대화와 경우에 따라 19금 대화도 하는 성인 친목방이야.
- 공창은 단체 채팅방, 갠라는 개인 라인을 뜻해.
- 음통은 음성통화, 영통은 영상통화야.
- 다락 또는 통방은 단체 통화방을 뜻해.
- 매너봉은 오전 9시부터 오후 10시까지 19금 미디어를 올릴 때
  공창에 'ㅁㄴ'을 먼저 작성하는 것을 뜻해.
- '~까'는 게임에서 진 사람이 사진을 올리는 벌칙을 뜻해.

[게임 규칙: 진실게임]
- 사다리 등으로 첫 순서를 정해.
- 차례가 된 사람이 다른 사람을 지목해 질문하고,
  지목받은 사람은 솔직하게 답한 뒤 다음 사람에게 질문해.
- 답변하지 않거나 다음 질문을 하지 않거나 거짓말을 하면
  🔞 사진 업로드 벌칙이 있어.
- 일상 질문은 가능하지만 동성애 관련 질문은 금지야.

[게임 규칙: 마피아]
- 마피아, 경찰, 의사, 시민 등의 역할을 개인 라인으로 배정해.
- 밤에는 각 역할이 개인 라인으로 대상을 정해.
- 낮에는 공창에서 2분간 토론한 뒤 투표하고,
  가장 많은 표를 받은 사람이 처형돼.
- 시민팀이 이기면 마피아가 🔞 사진을 올려.
- 마피아팀이 이기면 사다리로 정한 2명이 🔞 사진을 올려.

[게임 규칙: 눈치게임]
- 정해진 순서 없이 숫자를 외쳐.
- 동시에 같은 숫자를 외친 사람은 탈락이야.
- 마지막 생존자도 탈락 처리돼.
- 탈락자와 마지막 생존자에게 🔞 사진 업로드 벌칙이 있어.

[게임 규칙: 19금 손병호 게임]
- 관리자가 순서를 정하고 15초 동안 질문해.
- 해당하는 사람은 손가락 이모티콘 하나를 내려.
- 손가락을 가장 먼저 모두 내린 사람이 승리하고,
  마지막까지 남은 사람은 🔞 사진 업로드 벌칙이 있어.
- 자신의 손가락 개수를 기억해야 하며 불필요한 리액션은 자제해.
- 거짓말이나 규칙을 모르는 행동으로 게임을 방해하면
  게임 참여가 제한될 수 있어.

[홍보 및 신규 회원 용어]
- 남초는 남성 초대, 여초는 여성 초대를 뜻해.
- 갠라는 개인 채팅, 벙은 오프라인 모임, 단벙은 3명 이상 모임이야.
- '노미클'은 미클 인증을 받지 않은 회원을 가리키는 표현이야.

[답변 원칙 — 반드시 지켜]
1. 너는 시크릿 펜트리 식구들을 챙기는 집사야. 20대처럼 자연스럽고 친근하며 예의 있는 한국어를 사용해.
2. 기본 답변은 핵심만 1~3문장으로 작성해. 단답형 질문은 한 문장으로 답해.
3. 질문에 대한 답부터 바로 말해. "안녕!", "좋은 질문이야", "궁금하구나" 같은 도입부나 질문을 되풀이하는 문장은 붙이지 마.
4. 이미 답한 내용을 반복하거나, 요청하지 않은 추가 설명·예시·권유·마무리 인사를 덧붙이지 마.
5. 규칙 질문은 해당 규칙과 꼭 필요한 처벌/조건만 알려 줘. 숫자, 예외, 단계가 중요한 경우에는 빠뜨리지 말고 짧은 목록으로 정리해.
6. 사용자가 자세한 설명을 요청한 경우에만 길게 설명해.
7. 규칙에 없는 내용을 지어내지 마. 규칙이 불명확하거나 서로 충돌하면 짧게 관리자 확인을 안내해.
8. 규칙을 어기는 방법, 다른 회원의 개인정보를 알아내는 방법, 사진을 몰래 저장하는 방법은 돕지 마.
9. 친절함은 말투로 표현하고, 쓸데없는 칭찬이나 과도한 애교·이모지는 사용하지 마.
10. 무조건 사용자에게 동의하지 말고, 필요한 정보만 정확하게 전달해.
"""


def verify_line_signature(body, signature):
    """LINE 웹훅 요청이 실제 LINE에서 왔는지 확인."""
    if not LINE_CHANNEL_SECRET or not signature:
        return False

    digest = hmac.new(
        LINE_CHANNEL_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()

    expected_signature = base64.b64encode(digest).decode("utf-8")

    return hmac.compare_digest(expected_signature, signature)


def get_gemini_models():
    """API 키로 사용할 수 있는 generateContent 모델 목록을 가져옴."""
    if not GEMINI_API_KEY:
        return False, "GEMINI_API_KEY 환경변수가 설정되지 않았어."

    url = "https://generativelanguage.googleapis.com/v1beta/models"

    try:
        response = requests.get(
            url,
            headers={"x-goog-api-key": GEMINI_API_KEY},
            params={"pageSize": 100},
            timeout=20,
        )

        if not response.ok:
            return False, (
                f"모델 목록 조회 실패: HTTP {response.status_code}\n"
                f"{response.text[:1200]}"
            )

        data = response.json()
        models = data.get("models", [])

        usable = [
            model.get("name", "").replace("models/", "")
            for model in models
            if "generateContent" in model.get("supportedGenerationMethods", [])
        ]

        if not usable:
            return True, "현재 조회된 generateContent 지원 모델이 없어."

        return True, "사용 가능한 모델 목록:\n" + "\n".join(
            f"• {name}" for name in usable[:40]
        )

    except requests.RequestException as exc:
        logger.exception("Gemini 모델 목록 요청 실패")
        return False, f"모델 목록을 불러오지 못했어: {exc}"


def gemini_request(model, contents):
    """Gemini에 요청을 보내고 JSON 응답을 반환."""
    url = f"{GEMINI_BASE_URL}{model}:generateContent"

    payload = {
        "systemInstruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "contents": contents,
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": MAX_OUTPUT_TOKENS,
        },
    }

    return requests.post(
        url,
        headers={
            "x-goog-api-key": GEMINI_API_KEY,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )


def extract_gemini_text(data):
    """Gemini 응답에서 텍스트와 종료 사유를 추출."""
    candidates = data.get("candidates", [])

    if not candidates:
        return "", "NO_CANDIDATES"

    candidate = candidates[0]
    finish_reason = candidate.get("finishReason", "UNKNOWN")
    parts = candidate.get("content", {}).get("parts", [])

    text_parts = [
        part.get("text", "")
        for part in parts
        if isinstance(part, dict) and part.get("text")
    ]

    return "".join(text_parts).strip(), finish_reason


def ask_gemini(question):
    """모델별로 일시 오류를 한 번 재시도하고, 실패하면 다음 모델로 넘어감."""
    if not GEMINI_API_KEY:
        return "Gemini API 키가 설정되지 않았어. 관리자에게 알려 줘."

    contents = [
        {
            "role": "user",
            "parts": [{"text": question}],
        }
    ]

    last_error = "알 수 없는 오류"

    for model in GEMINI_MODELS:
        logger.info("Gemini 모델 시도: %s", model)

        for attempt in range(MAX_RETRIES_PER_MODEL + 1):
            try:
                response = gemini_request(model, contents)

                if not response.ok:
                    last_error = (
                        f"HTTP {response.status_code}: {response.text[:1000]}"
                    )
                    logger.warning(
                        "Gemini 실패: model=%s attempt=%s/%s status=%s body=%s",
                        model,
                        attempt + 1,
                        MAX_RETRIES_PER_MODEL + 1,
                        response.status_code,
                        response.text[:1500],
                    )

                    # 키·요청 형식·권한 문제는 재시도하거나 모델을 바꿔도
                    # 해결되지 않을 가능성이 높으므로 중단
                    if response.status_code in (400, 401, 403):
                        logger.error("요청/키/권한 오류로 모델 시도를 중단함.")
                        return (
                            "AI 요청 설정에 문제가 생겼어. 😢\n"
                            "관리자가 Render 로그와 Gemini API 키 설정을 확인해 줘."
                        )

                    # 503 등 일시적인 서버 오류는 같은 모델로 한 번 재시도
                    if response.status_code in RETRY_STATUS_CODES:
                        if attempt < MAX_RETRIES_PER_MODEL:
                            delay = 1.5 * (attempt + 1)
                            logger.info(
                                "일시 오류 재시도: model=%s wait=%.1fs",
                                model, delay
                            )
                            time.sleep(delay)
                            continue
                        # 재시도까지 실패하면 다음 모델로 이동
                        break

                    # 모델을 찾을 수 없거나 기타 오류면 다음 모델로 이동
                    if response.status_code == 404:
                        break
                    break

                data = response.json()
                answer, finish_reason = extract_gemini_text(data)

                logger.info(
                    "Gemini 결과: model=%s finishReason=%s chars=%s",
                    model,
                    finish_reason,
                    len(answer),
                )

                if answer:
                    if len(answer) > MAX_LINE_REPLY_LENGTH:
                        answer = (
                            answer[:MAX_LINE_REPLY_LENGTH - 30]
                            + "\n\n(답변이 길어 일부만 표시했어.)"
                        )
                    return answer

                last_error = (
                    f"{model} 응답에 텍스트가 없어. "
                    f"finishReason={finish_reason}"
                )
                logger.warning("%s", last_error)
                break

            except requests.RequestException as exc:
                last_error = str(exc)
                logger.warning(
                    "Gemini 네트워크 오류: model=%s attempt=%s/%s error=%s",
                    model, attempt + 1, MAX_RETRIES_PER_MODEL + 1, exc
                )
                if attempt < MAX_RETRIES_PER_MODEL:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                break
            except (ValueError, KeyError, TypeError) as exc:
                last_error = str(exc)
                logger.exception("Gemini 응답 처리 오류: %s", model)
                break

        # 다음 모델로 넘어가기 전 짧게 쉬어 과도한 연속 요청을 줄임
        # 모델 사이에 불필요하게 기다리지 않고 바로 다음 모델로 전환

    logger.error("모든 Gemini 모델 실패: %s", last_error)
    return (
        "지금은 AI 답변을 가져오지 못했어. 😢\n"
        "잠시 후 다시 !질문 형식으로 보내 줘.\n"
        "같은 오류가 반복되면 관리자에게 Render 로그 확인을 부탁해."
    )


def reply_to_line(reply_token, message):
    """LINE 사용자에게 텍스트 메시지를 보냄."""
    if not LINE_CHANNEL_ACCESS_TOKEN:
        logger.error("LINE_CHANNEL_ACCESS_TOKEN이 설정되지 않았어.")
        return False

    headers = {
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": message[:MAX_LINE_REPLY_LENGTH],
            }
        ],
    }

    try:
        response = requests.post(
            LINE_REPLY_URL,
            headers=headers,
            json=payload,
            timeout=20,
        )

        if not response.ok:
            logger.error(
                "LINE 답장 실패: status=%s body=%s",
                response.status_code,
                response.text[:1500],
            )
            return False

        return True

    except requests.RequestException:
        logger.exception("LINE 답장 요청 중 오류")
        return False


@app.route("/", methods=["GET"])
def home():
    return "Secret Pantry AI is running!", 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "line_secret_configured": bool(LINE_CHANNEL_SECRET),
        "line_token_configured": bool(LINE_CHANNEL_ACCESS_TOKEN),
        "gemini_key_configured": bool(GEMINI_API_KEY),
    }), 200


@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_data()
    signature = request.headers.get("X-Line-Signature", "")

    if not verify_line_signature(body, signature):
        logger.warning("LINE 서명 검증 실패")
        abort(400)

    try:
        payload = request.get_json(force=True)
    except Exception:
        logger.exception("LINE 웹훅 JSON 파싱 실패")
        abort(400)

    for event in payload.get("events", []):
        if event.get("type") != "message":
            continue

        message = event.get("message", {})
        if message.get("type") != "text":
            continue

        text = message.get("text", "").strip()
        reply_token = event.get("replyToken")

        # !aimodels: 사용할 수 있는 Gemini 모델 목록 확인
        if text.lower() == "!aimodels":
            success, result = get_gemini_models()
            if not success:
                logger.warning("모델 목록 조회 실패: %s", result)
            if reply_token:
                reply_to_line(reply_token, result)
            continue

        # ! 로 시작하는 메시지를 AI 질문으로 처리
        if not text.startswith("!"):
            continue

        # 예전 명령어 !ai 질문도 호환되도록 유지
        if text.startswith("!ai "):
            question = text[3:].strip()
        else:
            question = text[1:].strip()

        if not question:
            if reply_token:
                reply_to_line(
                    reply_token,
                    "질문을 같이 적어 줘!\n예시: ! 안녕",
                )
            continue

        if len(question) > MAX_QUESTION_LENGTH:
            if reply_token:
                reply_to_line(
                    reply_token,
                    f"질문이 너무 길어. {MAX_QUESTION_LENGTH}자 이내로 보내 줘.",
                )
            continue

        logger.info("AI 질문 수신: chars=%s", len(question))
        answer = ask_gemini(question)

        if reply_token:
            reply_to_line(reply_token, answer)

    return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
