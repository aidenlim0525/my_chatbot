import streamlit as st
import openai
import gspread
import json
import io
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# --- 환경설정 및 인증 ---
openai.api_key = st.secrets["OPENAI_API_KEY"]
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
gs_client = gspread.authorize(creds)
sheet_result = gs_client.open("PHQ9_결과_저장소").worksheet("Sheet1")
sheet_feedback = gs_client.open("PHQ9_결과_저장소").worksheet("Feedbacks")

KST = timezone(timedelta(hours=9))

phq9_questions = [
    "최근 2주간, 일상에 흥미나 즐거움을 느끼지 못한 적이 있었나요?",
    "우울하거나 슬픈 기분이 들었던 적이 있었나요?",
    "잠들기 어렵거나 자주 깼거나 너무 많이 잔 적이 있었나요?",
    "피곤하고 기운이 없다고 느낀 적이 있었나요?",
    "식욕이 줄었거나 과식한 적이 있었나요?",
    "자신에 대해 나쁘게 느끼거나, 실패자라고 느낀 적이 있었나요?",
    "집중하기 어렵다고 느낀 적이 있었나요?",
    "느리게 움직였거나, 지나치게 안절부절못한 적이 있었나요?",
    "차라리 죽는 게 낫겠다고 생각하거나 자해 생각을 한 적이 있었나요? (※ 생략 가능)"
]
gad7_questions = [
    "최근 2주간, 걱정을 너무 많이 하거나 멈출 수 없다고 느낀 적이 있었나요?",
    "여러 가지 다른 일에 대해 걱정한 적이 있었나요?",
    "긴장하거나 안절부절못한 느낌이 있었나요?",
    "짜증이 났거나 쉽게 화가 났던 적이 있었나요?",
    "무언가 끔찍한 일이 일어날 것 같은 느낌이 있었나요?",
    "불안으로 인해 편안히 쉬기 어려웠던 적이 있었나요?",
    "집중이 잘 되지 않았던 적이 있었나요?"
]
score_options = {"전혀 아님 (0점)":0, "며칠 동안 (1점)":1, "일주일 이상 (2점)":2, "거의 매일 (3점)":3}

for key in ["messages", "phq9_scores", "gad7_scores", "feedback_text"]:
    if key not in st.session_state:
        st.session_state[key] = [] if key.endswith("scores") else ""

st.title("🧠 감정상담 챗봇 + PHQ-9 & GAD-7 평가")
user_name = st.text_input("👤 상담자 이름을 입력해주세요:")

# 챗봇 입력
prompt = st.chat_input("무엇이든 이야기해 주세요.")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.spinner("답변 생성 중..."):
        # PHQ/GAD 점수 반영된 system 메시지
        phq_total = sum(st.session_state.phq9_scores) if st.session_state.phq9_scores else 0
        gad_total = sum(st.session_state.gad7_scores) if st.session_state.gad7_scores else 0
        context_msgs = [{"role": "system", "content": f"""
당신은 공감하는 심리상담 AI입니다.
사용자의 PHQ-9 점수는 {phq_total}점, GAD-7 점수는 {gad_total}점입니다.
점수에 따라 사용자가 느끼는 감정을 고려하여 공감적인 답변을 해주세요.
        """.strip()}] + st.session_state.messages

        try:
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=context_msgs
            )
            reply = response.choices[0].message.content.strip()
            st.session_state.messages.append({"role": "assistant", "content": reply})
        except Exception as e:
            st.error("GPT 오류")
            st.exception(e)

# 이전 메시지 출력
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 분석 함수
def analyze_scale(scores, scale):
    total = sum(scores)
    if scale == "PHQ":
        if total <= 4: return total, "정상"
        elif total <= 9: return total, "경도 우울"
        elif total <= 14: return total, "중등도 우울"
        elif total <= 19: return total, "중등도 이상 우울"
        else: return total, "심한 우울"
    if scale == "GAD":
        if total <= 4: return total, "정상"
        elif total <= 9: return total, "경도 불안"
        elif total <= 14: return total, "중등도 불안"
        else: return total, "심한 불안"

def medical_feedback(phq_score, gad_score):
    text = ""
    if phq_score >= 15:
        text += "- **우울:** 코르티솔 분비가 과도해 수면과 기분에 영향을 줄 수 있습니다. 규칙적인 수면, 햇빛 노출, 가벼운 운동이 도움이 됩니다.\n"
    if gad_score >= 10:
        text += "- **불안:** 아드레날린, 노르아드레날린이 과도하게 분비되어 심박수, 긴장감이 올라갑니다. 심호흡, 명상, 루틴화된 생활을 추천합니다.\n"
    if not text:
        text = "현재 전반적으로 정상 범위입니다. 수면, 식사, 운동의 균형을 지켜주세요."
    return text

def generate_pdf(name, phq_score, phq_level, gad_score, gad_level, medical_notes):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    y = 800
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, f"감정 상담 결과 리포트 - {name}")
    y -= 30
    c.setFont("Helvetica", 12)
    lines = [
        f"PHQ-9: {phq_score}점 ({phq_level})",
        f"GAD-7: {gad_score}점 ({gad_level})",
        "",
        "[의학적 설명 및 권장 사항]",
        *medical_notes.strip().split("\n"),
        "",
        "[일상 루틴 팁]",
        "- 매일 규칙적인 수면과 기상",
        "- 하루 20분 이상의 가벼운 유산소 운동",
        "- 카페인 섭취 줄이기",
        "- 가까운 사람과 감정 공유하기",
        "- 필요시 전문가 상담 받기"
    ]
    for line in lines:
        c.drawString(50, y, line)
        y -= 20
        if y < 50:
            c.showPage()
            y = 800
    c.save()
    buffer.seek(0)
    return buffer

# --- PHQ-9 설문 ---
with st.form("phq9_form"):
    st.subheader("📋 PHQ-9 설문")
    skip_q9 = st.checkbox("9번 문항(자살 관련)은 생략할게요.")
    phq_questions_to_ask = phq9_questions[:-1] if skip_q9 else phq9_questions

    phq_scores = []
    for i, q in enumerate(phq_questions_to_ask):
        score = st.radio(q, list(score_options.keys()), key=f"phq{i}")
        if score is None:
            st.warning("모든 문항에 응답해주세요.")
            st.stop()
        phq_scores.append(score_options[score])

    phq_submitted = st.form_submit_button("PHQ-9 제출")

if phq_submitted:
    st.session_state.phq9_scores = phq_scores
    phq_total, phq_level = analyze_scale(phq_scores, "PHQ")
    st.success(f"PHQ-9 총점: {phq_total}점 → {phq_level}")

# --- GAD-7 설문 ---
with st.form("gad7_form"):
    st.subheader("📋 GAD-7 설문")
    gad_scores = []
    for i, q in enumerate(gad7_questions):
        score = st.radio(q, list(score_options.keys()), key=f"gad{i}")
        if score is None:
            st.warning("모든 문항에 응답해주세요.")
            st.stop()
        gad_scores.append(score_options[score])

    gad_submitted = st.form_submit_button("GAD-7 제출")

if gad_submitted:
    st.session_state.gad7_scores = gad_scores
    gad_total, gad_level = analyze_scale(gad_scores, "GAD")
    st.success(f"GAD-7 총점: {gad_total}점 → {gad_level}")

# --- 리포트 생성 버튼 ---
if st.session_state.phq9_scores and st.session_state.gad7_scores:
    st.subheader("📄 리포트 생성")
    if st.button("지금까지 제출한 내용을 기반으로 리포트를 생성할까요?"):
        phq_total, phq_level = analyze_scale(st.session_state.phq9_scores, "PHQ")
        gad_total, gad_level = analyze_scale(st.session_state.gad7_scores, "GAD")
        med_note = medical_feedback(phq_total, gad_total)
        now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        sheet_result.append_row([
            user_name, phq_total, gad_total, now_kst, st.session_state.feedback_text.strip()
        ], value_input_option='USER_ENTERED')
        pdf = generate_pdf(user_name, phq_total, phq_level, gad_total, gad_level, med_note)
        st.download_button("📄 상담 리포트 PDF 다운로드", data=pdf, file_name=f"{user_name}_리포트.pdf")

# --- 피드백 제출 ---
st.subheader("💬 상담 피드백")
st.session_state.feedback_text = st.text_area("자유롭게 피드백을 남겨주세요:", value=st.session_state.feedback_text)
if st.button("피드백 제출"):
    sheet_feedback.append_row([
        "피드백", user_name, st.session_state.feedback_text.strip(), datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    ], value_input_option='USER_ENTERED')
    st.success("피드백 감사합니다!")
