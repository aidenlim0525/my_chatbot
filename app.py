# 감정상담 챗봇 + PHQ-9 & GAD-7 평가 (최종 통합)
import streamlit as st
import openai
import gspread
import json
import pandas as pd
import io
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone

# --- 환경설정 및 인증 ---
openai.api_key = st.secrets["OPENAI_API_KEY"]
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
gs_client = gspread.authorize(creds)
sheet_result = gs_client.open("PHQ9_결과_저장소").worksheet("Sheet1")
sheet_feedback = gs_client.open("PHQ9_결과_저장소").worksheet("Feedbacks")

KST = timezone(timedelta(hours=9))

# === 설문 문항 ===
phq9_questions = [
    "1. 최근 2주간, 일상에 흥미나 즐거움을 느끼지 못한 적이 있었나요?",
    "2. 우울하거나 슬픈 기분이 들었던 적이 있었나요?",
    "3. 잠들기 어렵거나 자주 깼거나 너무 많이 잔 적이 있었나요?",
    "4. 피곤하고 기운이 없다고 느낀 적이 있었나요?",
    "5. 식욕이 줄었거나 과식한 적이 있었나요?",
    "6. 자신에 대해 나쁘게 느끼거나, 실패자라고 느낀 적이 있었나요?",
    "7. 집중하기 어렵다고 느낀 적이 있었나요?",
    "8. 느리게 움직였거나, 지나치게 안절부절못한 적이 있었나요?",
    "9. 차라리 죽는 게 낫겠다고 생각하거나 자해 생각을 한 적이 있었나요? (※ 생략 가능)"
]
gad7_questions = [
    "1. 최근 2주간, 걱정을 너무 많이 하거나 멈출 수 없다고 느낀 적이 있었나요?",
    "2. 여러 가지 다른 일에 대해 걱정한 적이 있었나요?",
    "3. 긴장하거나 안절부절못한 느낌이 있었나요?",
    "4. 짜증이 났거나 쉽게 화가 났던 적이 있었나요?",
    "5. 무언가 끔찍한 일이 일어날 것 같은 느낌이 있었나요?",
    "6. 불안으로 인해 편안히 쉬기 어려웠던 적이 있었나요?",
    "7. 집중이 잘 되지 않았던 적이 있었나요?"
]
score_options = {
    "전혀 아님 (0점)": 0,
    "며칠 동안 (1점)": 1,
    "일주일 이상 (2점)": 2,
    "거의 매일 (3점)": 3
}

# === 분석 함수 ===
def analyze_phq9(scores):
    total = sum(scores)
    if total <= 4:
        level = "정상"
        feedback = "정상입니다. 정신건강 유지에 필요한 기본 생활 루틴을 지켜주세요."
    elif total <= 9:
        level = "경도 우울"
        feedback = "경미한 우울증입니다. 수면, 식사, 활동량을 조절하며 생활 습관 개선을 권장합니다."
    elif total <= 14:
        level = "중등도 우울"
        feedback = "중등도 우울 증상입니다. 상담 및 치료가 도움이 될 수 있습니다. 일상 속 소소한 보람을 쌓는 활동을 시도해보세요."
    elif total <= 19:
        level = "중등도 이상 우울"
        feedback = "심리적 부담이 크며 전문가의 상담이 필요할 수 있습니다. 규칙적인 생활과 스트레스 완화 전략이 필요합니다."
    else:
        level = "심한 우울"
        feedback = "즉각적인 정신건강 전문가의 도움이 필요합니다. 안전을 최우선으로 생각해주세요."
    return total, level, feedback

def analyze_gad7(scores):
    total = sum(scores)
    if total <= 4:
        level = "정상"
        feedback = "불안 수준은 정상입니다. 이 상태를 유지하기 위한 일상 관리가 중요합니다."
    elif total <= 9:
        level = "경도 불안"
        feedback = "가벼운 불안 상태입니다. 충분한 휴식과 이완 활동을 추천드립니다."
    elif total <= 14:
        level = "중등도 불안"
        feedback = "불안 증상이 명확하게 나타나고 있습니다. 이완훈련, 명상, 전문가 상담이 도움이 됩니다."
    else:
        level = "심한 불안"
        feedback = "지속적인 불안이 삶에 영향을 주고 있습니다. 적극적인 치료介入이 필요합니다."
    return total, level, feedback

# === 세션 초기화 ===
if "messages" not in st.session_state:
    st.session_state.messages = []
if "phq9_scores" not in st.session_state:
    st.session_state.phq9_scores = []
if "gad7_scores" not in st.session_state:
    st.session_state.gad7_scores = []
if "feedback_text" not in st.session_state:
    st.session_state.feedback_text = ""

# === UI ===
st.title("🧠 감정상담 챗봇 + PHQ-9 & GAD-7 평가")
user_name = st.text_input("👤 상담자 이름을 입력해주세요:")

# === 채팅 인터페이스 ===
prompt = st.chat_input("무엇이든 이야기해 주세요.")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.spinner("답변 생성 중..."):
        try:
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": "당신은 공감하는 심리상담 AI입니다."}] + st.session_state.messages
            )
            reply = response.choices[0].message.content.strip()
            st.session_state.messages.append({"role": "assistant", "content": reply})
        except Exception as e:
            st.error("GPT 응답 오류 발생")
            st.exception(e)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# === PHQ-9 설문 ===
with st.form("phq9_form"):
    st.subheader("📋 PHQ-9 설문")
    phq_scores = []
    for i, q in enumerate(phq9_questions):
        score = st.radio(q, list(score_options.keys()), key=f"phq{i}", index=0)
        phq_scores.append(score_options[score])
    phq_submitted = st.form_submit_button("PHQ-9 제출")

if phq_submitted:
    st.session_state.phq9_scores = phq_scores
    total, level, feedback = analyze_phq9(phq_scores)
    st.success(f"PHQ-9 총점: {total}점 → 우울 수준: {level}")
    st.info("의학적 피드백: " + feedback)

# === GAD-7 설문 ===
with st.form("gad7_form"):
    st.subheader("📋 GAD-7 설문")
    gad_scores = []
    for i, q in enumerate(gad7_questions):
        score = st.radio(q, list(score_options.keys()), key=f"gad{i}", index=0)
        gad_scores.append(score_options[score])
    gad_submitted = st.form_submit_button("GAD-7 제출")

if gad_submitted:
    st.session_state.gad7_scores = gad_scores
    total, level, feedback = analyze_gad7(gad_scores)
    st.success(f"GAD-7 총점: {total}점 → 불안 수준: {level}")
    st.info("의학적 피드백: " + feedback)

# === 피드백 및 저장 ===
st.subheader("💬 상담 피드백")
st.session_state.feedback_text = st.text_area("자유롭게 피드백을 남겨주세요:", value=st.session_state.feedback_text)
if st.button("피드백 제출"):
    if st.session_state.feedback_text.strip():
        try:
            sheet_feedback.append_row([
                "피드백", user_name, st.session_state.feedback_text.strip(), datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
            ], value_input_option='USER_ENTERED')
            st.success("피드백 감사합니다!")
        except Exception as e:
            st.error("❌ 피드백 저장 실패")
            st.exception(e)

# === 결과 저장 ===
if phq_submitted or gad_submitted:
    try:
        now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        sheet_result.append_row([
            user_name,
            sum(st.session_state.phq9_scores) if st.session_state.phq9_scores else "-",
            sum(st.session_state.gad7_scores) if st.session_state.gad7_scores else "-",
            now_kst,
            st.session_state.feedback_text.strip()
        ], value_input_option='USER_ENTERED')
        st.success("✅ Google Sheets에 저장 완료!")
    except Exception as e:
        st.error("❌ 저장 중 오류 발생")
        st.exception(e)
