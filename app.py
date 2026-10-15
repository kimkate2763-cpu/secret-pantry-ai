
import os
import hmac
import hashlib
import base64
import requests

from flask import Flask, request, abort

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]
LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

SYSTEM_PROMPT = """
너는 LINE 단체 채팅방 시크릿 펜트리의 AI 도우미다.
자연스럽고 친근한 한국어로 짧고 재미있게 답한다.
게임 추천, 라이어 게임, 마피아 게임, 마니또 질문,
공창 주제와 일반적인 고민 상담을 도와준다.
모르는 사실은 지어내지 않는다.
개인정보를 공개하거나 특정 멤버를 괴롭히지 않는다.
"""

@app.get("/")
def home():
    return "Secret Pantry AI is running!"

@app.post("/callback")
def callback():
    body = request.get_data()
    signature = request.headers.get("X-Line-Signature", "")

    digest = base64.b64encode(
        hmac.new(
            LINE_CHANNEL_SECRET.encode(),
            body,
            hashlib.sha256
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

        if not text.lower().startswith("!ai"):
            continue

        question = text[3:].strip()

        if not question:
            answer = "무엇이 궁금해? !AI 뒤에 질문을 적어 줘!"
        else:
            try:
                
                  response = requests.post(
                    "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent",
                    headers={
                        "x-goog-api-key": GEMINI_API_KEY,
                        "Content-Type": "application/json"
                    },
                    json={
                        "system_instruction": {
                            "parts": [{"text": SYSTEM_PROMPT}]
                        },
                        "contents": [{
                            "parts": [{"text": question}]
                        }],
                        "generationConfig": {
                            "maxOutputTokens": 500
                        }
                    },
                    timeout=25
                )

                response.raise_for_status()
                data = response.json()
                answer = data["candidates"][0]["content"]["parts"][0]["text"]

            except Exception:
                app.logger.exception("Gemini response failed")
                answer = "잠깐 오류가 났어. 조금 뒤에 다시 물어봐 줘!"

        reply_token = event.get("replyToken")
        if not reply_token:
            continue

        try:
            line_response = requests.post(
                "https://api.line.me/v2/bot/message/reply",
                headers={
                    "Authorization":
                        f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
                    "Content-Type": "application/json"
                },
                json={
                    "replyToken": reply_token,
                    "messages": [{
                        "type": "text",
                        "text": answer[:4500]
                    }]
                },
                timeout=10
            )
            line_response.raise_for_status()

        except requests.RequestException:
            app.logger.exception("LINE reply failed")

    return "OK", 200
