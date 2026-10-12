import os
from fastapi import FastAPI, Form, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
from gtts import gTTS
from langdetect import detect
import base64

# We will securely inject your new API key in the Render dashboard later
API_KEY = os.environ.get("GEMINI_API_KEY")

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

chat_session = None 

HTML_PAGE = '''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Agentic AI Research Hub</title>
  <style>
    body { height: 100vh; margin: 0; background: #1c1c1e; display: flex; justify-content: center; align-items: center; font-family: -apple-system, sans-serif; box-sizing: border-box; overflow: hidden; }
    #app-container { width: 100%; max-width: 900px; height: 100vh; background: #f4f4f5; display: flex; flex-direction: column; box-shadow: 0 4px 25px rgba(0,0,0,0.3); overflow: hidden; }
    #top-bar { background: #2c2c2e; padding: 14px 20px; display: flex; justify-content: space-between; align-items: center; color: white; font-weight: bold; font-size: 16px; }
    .top-btn { background: none; border: none; font-size: 22px; cursor: pointer; color: white; }
    #chat-history { flex-grow: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 15px; background: #ffffff; }
    .msg { padding: 14px 20px; border-radius: 20px; max-width: 85%; font-size: 16px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
    .user { background: #007aff; color: white; align-self: flex-end; border-bottom-right-radius: 4px; }
    .agent { background: #e5e5ea; color: black; align-self: flex-start; border-bottom-left-radius: 4px; direction: rtl; }
    #input-bar { display: flex; align-items: center; padding: 14px 18px; background: white; border-top: 1px solid #ddd; gap: 12px; }
    input[type="text"] { flex-grow: 1; padding: 14px 18px; border: 1px solid #ccc; border-radius: 25px; outline: none; font-size: 16px; background: #f9f9f9; }
    .icon-btn { background: none; border: none; font-size: 26px; cursor: pointer; padding: 5px; opacity: 0.7; }
    .icon-btn:hover { opacity: 1; }
  </style>
</head>
<body>
  <div id="app-container">
    <div id="top-bar">
      <button id="clear-btn" class="top-btn" title="Clear Chat">🗑️</button>
      <span>Agentic Research Hub</span>
      <button id="download-btn" class="top-btn" title="Download Chat">💾</button>
    </div>
    <div id="chat-history"></div>
    <div id="input-bar">
      <label for="file-upload" class="icon-btn">📎</label>
      <input type="file" id="file-upload" style="display: none;" accept="image/*,audio/*">
      <input type="text" id="text-input" placeholder="Message AI...">
      <button id="mic-btn" class="icon-btn">🎤</button>
      <button id="speaker-btn" class="icon-btn" style="opacity: 0.5;">🔇</button>
      <button id="send-btn" class="icon-btn" style="color: #007aff; opacity: 1;">🚀</button>
    </div>
  </div>
  <audio id="ai-voice" autoplay hidden></audio>
  <script>
    const chatHistory = document.getElementById('chat-history');
    const textInput = document.getElementById('text-input');
    const fileInput = document.getElementById('file-upload');
    const sendBtn = document.getElementById('send-btn');
    const speakerBtn = document.getElementById('speaker-btn');

    let speakEnabled = false;
    speakerBtn.addEventListener('click', () => {
        speakEnabled = !speakEnabled;
        speakerBtn.textContent = speakEnabled ? "🔊" : "🔇";
        speakerBtn.style.opacity = speakEnabled ? "1" : "0.5";
    });

    sendBtn.addEventListener('click', async () => {
        const text = textInput.value; const file = fileInput.files[0];
        if(!text && !file) return;

        const userBubble = document.createElement('div'); userBubble.className = 'msg user';
        userBubble.textContent = text || "[File Attached]"; chatHistory.appendChild(userBubble);
        textInput.value = ''; fileInput.value = '';

        const formData = new FormData();
        if(text) formData.append('text', text);
        if(file) formData.append('file', file);
        formData.append('speak', speakEnabled);

        try {
            const res = await fetch('/api/chat', { method: 'POST', body: formData });
            const data = await res.json();
            const agentBubble = document.createElement('div'); agentBubble.className = 'msg agent';
            agentBubble.textContent = data.reply; chatHistory.appendChild(agentBubble);
            
            if(data.audio_base64) {
                const audio = document.getElementById('ai-voice');
                audio.src = "data:audio/mp3;base64," + data.audio_base64; audio.play();
            }
        } catch(err) {
            const errBubble = document.createElement('div'); errBubble.className = 'msg agent';
            errBubble.textContent = "🚨 Request failed."; chatHistory.appendChild(errBubble);
        }
    });
  </script>
</body>
</html>'''

@app.get("/", response_class=HTMLResponse)
async def get_ui():
    return HTML_PAGE

@app.post("/api/chat")
async def chat_endpoint(text: str = Form(None), file: UploadFile = Form(None), speak: str = Form("false")):
    global chat_session
    try:
        if chat_session is None:
            client = genai.Client(api_key=API_KEY)
            chat_session = client.chats.create(
                model='gemini-2.5-flash',
                config=types.GenerateContentConfig(
                    system_instruction="You are a proactive, critical, and subjective AI research agent. Do not act like a passive, agreeable assistant. Actively interrogate assumptions, argue against weak premises, provide rigorous pushback, and debate fiercely. Detect the language of the user's input (Persian, Norwegian, English, etc.) and always reply in that same language. You must conclude every single response with a provocative, challenging question that forces deeper intellectual friction."
                )
            )

        content_parts = []
        if text: 
            enforcer = "\n\n[STRICT DIRECTIVE: DO NOT be polite, neutral, or encyclopedic. Actively challenge, critique, and argue against my input. Be highly subjective and always end with a fierce, provocative question in my language.]"
            content_parts.append(text + enforcer)
            
        if file:
            client = genai.Client(api_key=API_KEY)
            temp = f"temp_{file.filename}"
            with open(temp, "wb") as f: f.write(await file.read())
            file_ref = client.files.upload(file=temp)
            content_parts.append(file_ref)
            os.remove(temp)

        response = chat_session.send_message(content_parts if len(content_parts) > 1 else content_parts[0])
        reply_text = response.text

        audio_base64 = None
        if speak == "true":
            try:
                lang_code = detect(reply_text)
                if lang_code not in ['fa', 'no', 'en', 'de', 'sv']: lang_code = 'en'
            except: lang_code = 'en'
            tts = gTTS(text=reply_text, lang=lang_code)
            tts.save("reply.mp3")
            with open("reply.mp3", "rb") as audio:
                audio_base64 = base64.b64encode(audio.read()).decode('utf-8')
        
        return {"reply": reply_text, "audio_base64": audio_base64}
    except Exception as e:
        return {"reply": f"🚨 Error: {str(e)}", "audio_base64": None}
