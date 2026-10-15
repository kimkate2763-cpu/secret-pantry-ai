
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
항상 자연스럽고 편안한 한국어로 대화해.
친절하고 재치 있게 답변하되 지나치게 길게 말하지 마.
모르는 내용은 아는 척하지 말고 솔직하게 말해.
사용자가 고민을 이야기하면 공감하면서 현실적인 조언을 해줘.
"""

# 사용 가능한 모델 목록에 있는 Gemini 3.6 Flash 사용
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-3.6-flash:generateContent"
)

RETRY_STATUS_CODES = (408, 429, 500, 502, 503, 504)


@app.get("/")
def home():
    return "Secret Pantry AI is running!"


def get_available_models():
    response = requests.get(
        "https://generativelanguage.googleapis.com/v1beta/models",
        headers={"x-goog-api-key": GEMINI_API_KEY},
        params={"pageSize": 100},
        timeout=15,
    )
    response.raise_for_status()

    data = response.json()
    names = []

    for model in data.get("models", []):
        methods = model.get("supportedGenerationMethods", [])
        name = model.get("name", "")

        if "generateContent" in methods and name:
            names.append(name)

    return names


def ask_gemini(question):
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
                timeout=20,
            )

            if response.status_code in RETRY_STATUS_CODES:
                if attempt < 2:
                    wait_seconds = 2 ** (attempt + 1)
                    app.logger.warning(
                        "Gemini HTTP %s 오류. %s초 후 재시도 (%s/3)",
                        response.status_code,
                        wait_seconds,
                        attempt + 1,
                    )
                    time.sleep(wait_seconds)
                    continue

            if not response.ok:
                app.logger.error(
                    "Gemini API HTTP %s: %s",
                    response.status_code,
                    response.text[:1500],
                )

            response.raise_for_status()

            data = response.json()
            candidates = data.get("candidates", [])

            if not candidates:
                app.logger.error(
                    "Gemini 응답에 candidates가 없습니다: %s",
                    response.text[:1000],
                )
                return "이번에는 답변을 만들지 못했어. 다시 물어봐 줘!"

            parts = candidates[0].get("content", {}).get("parts", [])
            answer = "".join(
                part.get("text", "")
                for part in parts
                if part.get("text")
            ).strip()

            return answer or "이번에는 답변을 만들지 못했어. 다시 물어봐 줘!"

        except (requests.Timeout, requests.ConnectionError):
            app.logger.exception(
                "Gemini 연결 오류 (%s/3)", attempt + 1
            )

            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
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
        if not text:
            continue

        if text.lower() == "!aimodels":
            try:
                models = get_available_models()

                if models:
                    answer = (
                        "현재 조회 가능한 텍스트 생성 모델 목록:\n"
                        + "\n".join(models[:30])
                    )
                else:
                    answer = "텍스트 생성 지원 모델을 찾지 못했어."

            except Exception:
                app.logger.exception("Gemini 모델 목록 조회 실패")
                answer = "모델 목록 조회에 실패했어. Render 로그를 확인해 줘."

        elif text.lower().startswith("!ai"):
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
        else:
            continue

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
