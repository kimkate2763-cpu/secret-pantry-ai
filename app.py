
import os
import hmac
import hashlib
import base64
import time
import requests
from flask import Flask, request, abort

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

SYSTEM_PROMPT = """
너는 시크릿 펜트리 단체방에서 활동하는 친근한 AI 친구야.

- 항상 자연스럽고 편안한 한국어로 대화해.
- 친절하고 재치 있게 답변하되, 지나치게 길게 말하지 마.
- 질문의 의도를 파악하고 이해하기 쉽게 설명해.
- 모르는 내용은 아는 척하지 말고 솔직하게 말해.
- 사용자가 장난을 치면 분위기에 맞춰 자연스럽게 받아줘.
- 사용자가 고민을 이야기하면 공감하면서 현실적인 조언을 해줘.
- 확인할 수 없는 단체방 대화나 개인 정보를 알고 있는 척하지 마.
- 특별한 요청이 없으면 간결하게 답변해.
"""

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-3.8-flash:generateContent"
)

RETRY_STATUS_CODES = (408, 429, 500, 502, 503, 504)


@app.get("/")
def home():
    return "Secret Pantry AI is running!"


def ask_gemini(question):
    """일시적인 오류가 발생하면 최대 3번 요청한다."""

    for attempt in range(3):
        try:
            response = requests.post(
                GEMINI_URL,
                headers={
                    "x-goog-api-key": GEMINI_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "system_instruction": {
                        "parts": [{"text": SYSTEM_PROMPT}]
                    },
                    "contents": [
                        {"parts": [{"text": question}]}
                    ],
                    "generationConfig": {
                        "maxOutputTokens": 500
                    },
                },
                timeout=12,
            )

            # 일시적인 서버 오류라면 잠시 기다렸다가 재시도
            if response.status_code in RETRY_STATUS_CODES:
                if attempt < 2:
                    wait_seconds = 2 ** attempt
                    app.logger.warning(
                        "Gemini 일시 오류: HTTP %s. "
                        "%s초 후 재시도합니다. (%s/3)",
                        response.status_code,
                        wait_seconds,
                        attempt + 1,
                    )
                    time.sleep(wait_seconds)
                    continue

            # 재시도로 해결되지 않은 오류 확인
            response.raise_for_status()

            data = response.json()
            candidates = data.get("candidates", [])

            if not candidates:
                app.logger.error(
                    "Gemini 응답에 candidates가 없습니다: %s",
                    response.text[:1000],
                )
                return "답변을 만들지 못했어. 질문을 조금 바꿔서 다시 물어봐 줘!"

            parts = candidates[0].get("content", {}).get("parts", [])
            answer = "".join(
                part.get("text", "")
                for part in parts
                if part.get("text")
            ).strip()

            if not answer:
                return "이번에는 답변을 만들지 못했어. 다시 물어봐 줘!"

            return answer

        except (requests.Timeout, requests.ConnectionError):
            app.logger.exception(
                "Gemini 연결 오류 (%s/3)", attempt + 1
            )

            if attempt < 2:
                time.sleep(2 ** attempt)
                continue

            raise

    raise RuntimeError("Gemini 재시도 횟수를 초과했습니다.")


@app.post("/callback")
def callback():
    body = request.get_data()
    signature = request.headers.get("X-Line-Signature", "")

    digest = base64.b64encode(
        hmac.new(
            LINE_CHANNEL_SECRET.encode(),
            body,
            hashlib.sha256,
        ).digest()
    ).decode()

    if not hmac.compare_digest(signature, digest):
        abort(400)

    payload = request.get_json(silent=True) or {}

    for event in payload.get("events", []):
        if event.get("type") != "message":
            continue

        message = event.get("message", {})

        if message.get("type") != "text":
            continue

        text = message.get("text", "").strip()

        # !AI로 시작하는 메시지에만 응답
        if not text.lower().startswith("!ai"):
            continue

        question = text[3:].strip()

        if not question:
            answer = "무엇이 궁금해? !AI 뒤에 질문을 적어 줘!"
        else:
            try:
                answer = ask_gemini(question)
            except Exception:
                app.logger.exception("Gemini 응답 최종 실패")
                answer = (
                    "구글 AI가 지금 답변을 처리하지 못하고 있어. "
                    "잠시 후 다시 물어봐 줘!"
                )

        reply_token = event.get("replyToken")

        if not reply_token:
            continue

        try:
            line_response = requests.post(
                "https://api.line.me/v2/bot/message/reply",
                headers={
                    "Authorization": (
                        f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
                    ),
                    "Content-Type": "application/json",
                },
                json={
                    "replyToken": reply_token,
                    "messages": [
                        {
                            "type": "text",
                            "text": answer[:4500],
                        }
                    ],
                },
                timeout=10,
            )

            line_response.raise_for_status()

        except requests.RequestException:
            app.logger.exception("LINE 답변 전송 실패")

    return "OK", 200
