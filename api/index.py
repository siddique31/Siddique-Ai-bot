import os
import requests
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from groq import Groq

app = Flask(__name__, template_folder='../templates')
CORS(app)

# ---- CONFIG ----
DISCLAIMER = ("\n\n⚠️ Ye sirf aam maloomat hai, medical advice nahi. "
              "Diagnosis aur ilaaj ke liye registered doctor/veterinarian se milo.")

SYSTEM_RULES = """Tum "Siddique AI Chat Bot" ho — medical/veterinary information assistant.
Rules:
1. Sirf aam maloomat do. Diagnosis na karo ("aapko ye bimari hai" — mana hai).
2. Dawa ka naam, dose, ya ilaaj ka plan kabhi na batao.
3. Personal case (mera kutta, meri bimari) par kaho: "Doctor ka check-up zaroori hai."
4. Emergency par kaho: "Foran doctor ke paas jao."
5. Agar maloomat nahi to saaf kaho: "Is bare mein maloomat nahi hai."
"""

_client = None

def get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY environment variable missing hai")
        _client = Groq(api_key=api_key)
    return _client

def ask_llm(prompt, model="llama-3.3-70b-versatile"):
    client = get_client()
    resp = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=model,
        temperature=0.3,
    )
    return resp.choices[0].message.content

# ---- SAFETY ----
def is_unsafe(msg):
    bad = ["diagnose", "diagnosis", "dawa", "dose", "medicine", "tablet",
           "ilaaj", "prescribe", "kya bimari hai", "kya beemari hai"]
    return any(b in msg.lower() for b in bad)

# ---- INTENT ----
def detect_intent(msg):
    prompt = (f'User ka message: "{msg}"\n'
              f'Sirf ek word likho: DIAGRAM (flowchart/structure maange), '
              f'IMAGE (photo/picture maange), ya TEXT (baqi sab). Jawab:')
    try:
        out = ask_llm(prompt, model="llama-3.1-8b-instant").strip().upper()
        if "DIAGRAM" in out: return "DIAGRAM"
        if "IMAGE" in out: return "IMAGE"
        return "TEXT"
    except:
        return "TEXT"

# ---- DIAGRAM ----
def make_diagram(msg):
    prompt = (f"{SYSTEM_RULES}\n\n"
              f"User diagram maang raha hai: \"{msg}\"\n"
              f"Sirf valid Mermaid code likho (graph TD ...), kuch aur nahi. "
              f"``` waghera na lagao.")
    code = ask_llm(prompt)
    code = code.replace("```mermaid", "").replace("```", "").strip()
    return code

# ---- IMAGE ----
def make_image(msg):
    prompt = (f'Create a short English image prompt for this request: "{msg}". '
              f'Only the prompt text, nothing else.')
    img_prompt = ask_llm(prompt, model="llama-3.1-8b-instant").strip().replace("\n", " ")
    return f"https://image.pollinations.ai/prompt/{requests.utils.quote(img_prompt)}"

# ---- ROUTES ----
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        msg = data.get("message", "").strip()
        if not msg:
            return jsonify({"type": "text", "answer": "Sawal likho."})

        if is_unsafe(msg):
            return jsonify({
                "type": "refuse",
                "answer": ("Is sawal ke liye doctor ka check-up zaroori hai. "
                           "Main diagnosis ya dawa nahi bata sakta. "
                           "Registered doctor/vet se milo.")
            })

        intent = detect_intent(msg)

        if intent == "DIAGRAM":
            return jsonify({
                "type": "diagram",
                "code": make_diagram(msg),
                "disclaimer": DISCLAIMER
            })

        if intent == "IMAGE":
            return jsonify({
                "type": "image",
                "url": make_image(msg),
                "disclaimer": DISCLAIMER
            })

        answer = ask_llm(f"{SYSTEM_RULES}\n\nUser sawal: {msg}\n\nJawab:")
        return jsonify({"type": "text", "answer": answer + DISCLAIMER})

    except Exception as e:
        return jsonify({"type": "text", "answer": f"Error: {str(e)}"}), 500

# Vercel ke liye zaroori
handler = app
