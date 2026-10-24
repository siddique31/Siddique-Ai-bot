import os
import re
import requests
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from groq import Groq

app = Flask(__name__, template_folder='../templates')
CORS(app)

# ================= CONFIG =================
DISCLAIMER_UR = ("\n\n⚠️ Ye sirf aam maloomat hai, medical advice nahi. "
                 "Diagnosis aur ilaaj ke liye registered doctor/veterinarian se milo.")

DISCLAIMER_EN = ("\n\n⚠️ This is general information only, not medical advice. "
                 "Please consult a registered doctor/veterinarian for diagnosis and treatment.")

DOCTOR_LINE_UR = "\n\n👨‍⚕️ Behtar hoga ke aap registered doctor/veterinarian se rabta karein."
DOCTOR_LINE_EN = "\n\n👨‍⚕️ It is best to contact a registered doctor/veterinarian."

SYSTEM_RULES = """Tum "Siddique AI Chat Bot" ho — medical/veterinary information assistant.

Rules:
1. User ko aam maloomat ke saath general guidance/advice bhi do
   (jaise: "paani zyada pilayein", "aaram karayein", "safai ka khayal rakhein").
2. Kabhi bhi diagnosis na karo ("aapko ye bimari hai" — mana hai).
3. Dawa ka naam, dose, ya specific ilaaj ka plan kabhi na batao.
4. Personal case (mera kutta, meri bimari) par general advice do,
   lekin saath mein kaho: "Behtar hoga ke doctor ka check-up karwayein."
5. Emergency symptoms (saans, khoon, behoshi) par foran kaho:
   "Foran doctor ke paas jao."
6. Agar maloomat nahi to saaf kaho: "Is bare mein maloomat nahi hai."
7. User jis zubaan mein likhe (Urdu, Roman Urdu, English), usi mein jawab do.
8. Friendly aur helpful raho, lekin medical limits kabhi cross na karo.
"""

BIG_MODEL = "openai/gpt-oss-120b"
SMALL_MODEL = "openai/gpt-oss-20b"

_client = None

def get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY environment variable missing hai")
        _client = Groq(api_key=api_key)
    return _client

def ask_llm(prompt, model=None, temperature=0.3):
    if model is None:
        model = BIG_MODEL
    client = get_client()
    resp = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=model,
        temperature=temperature,
    )
    return resp.choices[0].message.content

# ================= LANGUAGE =================
URDU_WORDS = {"kya", "hai", "kaise", "batao", "karo", "mujhe", "mera", "meri",
              "kutta", "billi", "bimari", "bukhar", "dawa", "ilaaj", "kaun",
              "tum", "aap", "kab", "kahan", "kyun", "nahi", "haan", "acha",
              "banao", "dikhao", "samjhao", "chahiye", "kro", "kro"}

def is_urdu(msg):
    return any(w in msg.lower().split() for w in URDU_WORDS)

def get_disclaimer(msg):
    return DISCLAIMER_UR if is_urdu(msg) else DISCLAIMER_EN

def get_doctor_line(msg):
    return DOCTOR_LINE_UR if is_urdu(msg) else DOCTOR_LINE_EN

# ================= MEDICAL CHECK =================
MEDICAL_WORDS = {"bimari", "disease", "bukhar", "fever", "dawa", "medicine",
                 "kutta", "billi", "dog", "cat", "janwar", "animal",
                 "kidney", "heart", "sugar", "diabetes", "infection",
                 "alamat", "symptom", "ilaaj", "treatment", "doctor",
                 "vet", "veterinary", "sehat", "health", "pain", "dard",
                 "bimar", "beemar", "ilaj", "daktar", "microscope",
                 "anatomy", "organ", "cell", "blood", "bone", "muscle"}

def is_medical(msg):
    return any(w in msg.lower() for w in MEDICAL_WORDS)

# ================= SAFETY =================
UNSAFE = ["diagnose", "diagnosis", "dawa", "dose", "medicine", "tablet",
          "ilaaj", "prescribe", "kya bimari hai", "kya beemari hai"]

def is_unsafe(msg):
    return any(b in msg.lower() for b in UNSAFE)

# ================= INTENT =================
def detect_intent(msg):
    prompt = (f'User ka message: "{msg}"\n'
              f'Sirf ek word likho: DIAGRAM (flowchart/structure maange), '
              f'IMAGE (photo/picture maange), ya TEXT (baqi sab). Jawab:')
    try:
        out = ask_llm(prompt, model=SMALL_MODEL, temperature=0.0).strip().upper()
        if "DIAGRAM" in out: return "DIAGRAM"
        if "IMAGE" in out: return "IMAGE"
        return "TEXT"
    except:
        return "TEXT"

# ================= DIAGRAM (FIXED) =================
def clean_mermaid(code):
    """Mermaid code ko saaf karo — <br> ko newline banao, HTML tags hatao"""
    # code fences hatao
    code = code.replace("```mermaid", "").replace("```", "").strip()

    # <br> variants ko newline mein badlo (REMOVE nahi)
    code = re.sub(r'<br\s*/?>', '\n', code, flags=re.IGNORECASE)

    # koi bhi baqi HTML tag hatao
    code = re.sub(r'<[^>]+>', ' ', code)

    # agar "graph TD" ke baad turant text hai to newline lagao
    code = re.sub(r'(graph\s+(TD|LR|TB|RL|BT))\s*', r'\1\n', code, flags=re.IGNORECASE)

    # har line ko trim karo, khali lines hatao
    lines = [l.strip() for l in code.split("\n") if l.strip()]
    code = "\n".join(lines)

    # agar --> ke aas-paas ganda spacing hai to saaf karo
    code = re.sub(r'\s*-->\s*', ' --> ', code)

    # node labels ke andar special characters hatao ((), :, ;, quotes)
    # sirf [] ke andar ki cheez clean karo
    def clean_label(m):
        label = m.group(1)
        label = re.sub(r'[^\w\s\-/]', '', label)
        return f"[{label.strip()}]"
    code = re.sub(r'\[([^\]]*)\]', clean_label, code)

    return code

def make_diagram(msg):
    prompt = (f"{SYSTEM_RULES}\n\n"
              f"User diagram maang raha hai: \"{msg}\"\n"
              f"Sirf valid Mermaid code likho. Format BILKUL aisa ho:\n"
              f"graph TD\n"
              f"    A[Start] --> B[Step 1]\n"
              f"    B --> C[Step 2]\n"
              f"Har node ALAG line par ho. <br/> ya koi HTML tag BILKUL na lagao. "
              f"Node labels simple rakho — sirf letters, numbers, spaces, dash. "
              f"(), [], {{}}, :, ;, quotes bilkul na daalo. "
              f"Sirf code likho, ``` waghera na lagao.")
    code = ask_llm(prompt, model=BIG_MODEL, temperature=0.2)
    return clean_mermaid(code)

# ================= IMAGE =================
def make_image(msg):
    prompt = (f'Create a short English image prompt for this request: "{msg}". '
              f'Only the prompt text, nothing else.')
    img_prompt = ask_llm(prompt, model=SMALL_MODEL, temperature=0.4).strip().replace("\n", " ")
    return f"https://image.pollinations.ai/prompt/{requests.utils.quote(img_prompt)}"

# ================= ROUTES =================
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/health")
def health():
    return jsonify({"status": "ok", "bot": "Siddique AI Chat Bot"})

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        msg = data.get("message", "").strip()
        if not msg:
            return jsonify({"type": "text", "answer": "Sawal likho."})

        med = is_medical(msg)
        disc = get_disclaimer(msg) if med else ""
        doctor_line = get_doctor_line(msg) if med else ""

        # Safety refuse
        if is_unsafe(msg):
            return jsonify({
                "type": "refuse",
                "answer": ("Is sawal ke liye doctor ka check-up zaroori hai. "
                           "Main diagnosis ya dawa nahi bata sakta. "
                           "Registered doctor/vet se milo." + doctor_line)
            })

        intent = detect_intent(msg)

        if intent == "DIAGRAM":
            return jsonify({
                "type": "diagram",
                "code": make_diagram(msg),
                "disclaimer": disc + doctor_line
            })

        if intent == "IMAGE":
            return jsonify({
                "type": "image",
                "url": make_image(msg),
                "disclaimer": disc + doctor_line
            })

        answer = ask_llm(f"{SYSTEM_RULES}\n\nUser sawal: {msg}\n\nJawab:",
                         model=BIG_MODEL)
        return jsonify({"type": "text", "answer": answer + disc + doctor_line})

    except Exception as e:
        return jsonify({"type": "text", "answer": f"Error: {str(e)}"}), 500

# Vercel ke liye zaroori
handler = app
