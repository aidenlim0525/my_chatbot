# 감정상담 챗봇 + PHQ-9 / GAD-7 평가 + 리포트 생성 + 피드백 저장
import streamlit as st
import openai
import gspread
import json
import pandas as pd
import io
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone

# === 설정 ===
openai.api_key = st.secrets["OPENAI_API_KEY"]
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
gs_client = gspread.authorize(creds)
sheet_result = gs_client.open("PHQ9_결과_저장소").worksheet("Sheet1")
sheet_feedback = gs_client.open("PHQ9_결과_저장소").worksheet("Feedbacks")

KST = timezone(timedelta(hours=9))
end_phrases = ["상담 종료", "그만할래", "끝낼게요", "이만 마칠게요", "종료하겠습니다", "그만두고 싶어", "이제 끝", "종료", "마무리할게요", "이제 그만"]

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
    "1. 긴장하거나 불안하다고 느낀 적이 있었나요?",
    "2. 걱정을 멈추거나 조절하기 어려웠던 적이 있었나요?",
    "3. 여러 가지를 지나치게 걱정한 적이 있었나요?",
    "4. 편안하게 쉬기가 어려웠던 적이 있었나요?",
    "5. 너무 초조하거나 안절부절 못했던 적이 있었나요?",
    "6. 쉽게 짜증이 나거나 쉽게 화가 났던 적이 있었나요?",
    "7. 끔찍한 일이 일어날 것 같다는 생각이 들었던 적이 있었나요?"
]

score_options = {
    "전혀 아님 (0점)": 0,
    "며칠 동안 (1점)": 1,
    "일주일 이상 (2점)": 2,
    "거의 매일 (3점)": 3
}

if "messages" not in st.session_state:
    st.session_state.messages = []
if "phq_scores" not in st.session_state:
    st.session_state.phq_scores = []
if "gad_scores" not in st.session_state:
    st.session_state.gad_scores = []
if "feedback_text" not in st.session_state:
    st.session_state.feedback_text = ""
if "current_questionnaire" not in st.session_state:
    st.session_state.current_questionnaire = None
if "current_question_index" not in st.session_state:
    st.session_state.current_question_index = 0
if "awaiting_answer" not in st.session_state:
    st.session_state.awaiting_answer = False

st.title("🧠 감정상담 챗봇 + PHQ-9 / GAD-7 평가")
user_name = st.text_input("👤 상담자 이름을 입력해주세요:")

st.subheader("📝 상담 피드백")
st.session_state.feedback_text = st.text_area("자유롭게 피드백을 남겨주세요:", value=st.session_state.feedback_text)
if st.button("피드백 제출"):
    if st.session_state.feedback_text.strip():
        sheet_feedback.append_row(["피드백", user_name, st.session_state.feedback_text.strip(), datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")], value_input_option='USER_ENTERED')
        st.success("피드백 감사합니다!")

if prompt := st.chat_input("지금 어떤 기분이신가요?"):
    st.session_state.messages.append({"role": "user", "content": prompt})

    if any(p in prompt for p in end_phrases):
        total_phq = sum(st.session_state.phq_scores)
        level_phq = get_phq9_feedback(total_phq)
        total_gad = sum(st.session_state.gad_scores)
        level_gad = get_gad7_feedback(total_gad)
        now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

        # 저장
        sheet_result.append_row([
            user_name,
            total_phq, level_phq, f"{len(st.session_state.phq_scores)}/9",
            total_gad, level_gad, f"{len(st.session_state.gad_scores)}/7",
            now_kst,
            prompt,
            st.session_state.feedback_text.strip()
        ], value_input_option='USER_ENTERED')

        # 리포트
        csv_data = pd.DataFrame({
            "이름": [user_name],
            "PHQ-9 총점": [total_phq],
            "PHQ-9 수준": [level_phq],
            "GAD-7 총점": [total_gad],
            "GAD-7 수준": [level_gad],
            "상담 일시": [now_kst],
            "상담 메시지": [prompt],
            "피드백": [st.session_state.feedback_text.strip()],
            "의학적 조언": [generate_medical_feedback(level_phq, level_gad)]
        })
        csv_buffer = io.StringIO()
        csv_data.to_csv(csv_buffer, index=False)
        st.download_button("📄 상담 리포트 다운로드", data=csv_buffer.getvalue(), file_name=f"Report_{user_name}.csv", mime="text/csv")

        st.info("상담이 종료되었습니다. 언제든지 다시 찾아주세요.")

    elif "phq" in prompt.lower():
        st.session_state.current_questionnaire = "PHQ"
        st.session_state.current_question_index = 0
        st.session_state.phq_scores = []
        st.session_state.awaiting_answer = True
    elif "gad" in prompt.lower():
        st.session_state.current_questionnaire = "GAD"
        st.session_state.current_question_index = 0
        st.session_state.gad_scores = []
        st.session_state.awaiting_answer = True
    else:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": "당신은 따뜻하고 공감하는 심리상담 챗봇입니다."}] + st.session_state.messages
        )
        reply = response.choices[0].message.content
        st.session_state.messages.append({"role": "assistant", "content": reply})

# === 설문 흐름 ===
if st.session_state.current_questionnaire == "PHQ" and st.session_state.awaiting_answer:
    i = st.session_state.current_question_index
    if i < len(phq9_questions):
        st.subheader(f"PHQ-9 문항 {i+1}/9")
        a = st.radio(phq9_questions[i], list(score_options.keys()), key=f"phq_{i}")
        if st.button("제출", key=f"submit_phq_{i}"):
            st.session_state.phq_scores.append(score_options[a])
            st.session_state.current_question_index += 1
    else:
        st.session_state.awaiting_answer = False

elif st.session_state.current_questionnaire == "GAD" and st.session_state.awaiting_answer:
    i = st.session_state.current_question_index
    if i < len(gad7_questions):
        st.subheader(f"GAD-7 문항 {i+1}/7")
        a = st.radio(gad7_questions[i], list(score_options.keys()), key=f"gad_{i}")
        if st.button("제출", key=f"submit_gad_{i}"):
            st.session_state.gad_scores.append(score_options[a])
            st.session_state.current_question_index += 1
    else:
        st.session_state.awaiting_answer = False

# === 결과 해석 함수 ===
def get_phq9_feedback(score):
    if score <= 4: return "정상"
    elif score <= 9: return "경도 우울"
    elif score <= 14: return "중등도 우울"
    elif score <= 19: return "중등도 이상 우울"
    else: return "심한 우울"

def get_gad7_feedback(score):
    if score <= 4: return "정상"
    elif score <= 9: return "경도 불안"
    elif score <= 14: return "중등도 불안"
    else: return "심한 불안"

def generate_medical_feedback(phq_level, gad_level):
    feedback = ""
    if phq_level != "정상":
        feedback += f"PHQ-9 ({phq_level}) 수준의 우울 증상은 세로토닌, 도파민과 같은 신경전달물질의 균형과 관련 있습니다. 충분한 수면, 규칙적 식사, 햇빛 노출, 가벼운 운동이 도움이 됩니다.\\n"
    if gad_level != "정상":
        feedback += f"GAD-7 ({gad_level}) 수준의 불안 증상은 코르티솔 증가, 자율신경계 항진과 관련이 있습니다. 명상, 호흡훈련, 일과표 정리, 사회적 지지망 확보가 중요합니다.\\n"
    if feedback == "":
        feedback = "현재 특별한 이상 소견은 없으며, 건강한 생활습관을 유지하시길 권장합니다."
    return feedback