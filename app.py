# 감정상담 챗봇 + PHQ-9 + GAD-7 평가 통합버전
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

# === 질문지 ===
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
    "1. 지난 2주 동안, 긴장하거나 초조했던 적이 얼마나 자주 있었나요?",
    "2. 걱정을 멈추거나 조절하기 어려웠던 적이 있었나요?",
    "3. 여러 가지 일에 대해 지나치게 걱정했던 적이 있었나요?",
    "4. 긴장으로 인해 쉬기 어려웠던 적이 있었나요?",
    "5. 안절부절 못하며 가만히 있지 못했던 적이 있었나요?",
    "6. 쉽게 짜증이 나거나 예민했던 적이 있었나요?",
    "7. 두려움에 사로잡힌 듯한 느낌이 있었나요?"
]
score_options = {
    "전혀 아님 (0점)": 0,
    "며칠 동안 (1점)": 1,
    "일주일 이상 (2점)": 2,
    "거의 매일 (3점)": 3
}

KST = timezone(timedelta(hours=9))

# === 피드백 생성 함수 ===
def get_phq9_feedback(score):
    if score <= 4:
        return "우울 증상이 거의 없거나 정상입니다. 생활 리듬을 유지하세요."
    elif score <= 9:
        return "경도 우울 증상입니다. 규칙적인 운동과 수면이 도움이 됩니다."
    elif score <= 14:
        return "중등도 우울 증상입니다. 전문가의 상담을 고려해보세요."
    elif score <= 19:
        return "중등도 이상 우울입니다. 정신건강 전문가와의 상담이 필요합니다."
    else:
        return "심한 우울 증상입니다. 조속히 전문 치료를 받는 것이 권장됩니다."

def get_gad7_feedback(score):
    if score <= 4:
        return "불안 수준이 정상 범위입니다."
    elif score <= 9:
        return "경도 불안 증상입니다. 마음챙김이나 명상이 도움이 될 수 있습니다."
    elif score <= 14:
        return "중등도 불안 증상입니다. 상담과 스트레스 관리가 필요합니다."
    else:
        return "심한 불안 증상입니다. 전문적 평가와 치료가 필요합니다."

# === 상태 초기화 ===
for key in ["messages", "phq9_scores", "gad7_scores", "feedback_text"]:
    if key not in st.session_state:
        st.session_state[key] = [] if 'scores' in key else ""

# === UI ===
st.title("🧠 감정상담 챗봇 + PHQ-9 & GAD-7 평가")
user_name = st.text_input("👤 상담자 이름을 입력해주세요:")
st.session_state.feedback_text = st.text_area("📝 상담 피드백을 자유롭게 남겨주세요:", value=st.session_state.feedback_text)

if st.button("피드백 제출") and st.session_state.feedback_text.strip():
    sheet_feedback.append_row(["피드백", user_name, st.session_state.feedback_text.strip(), datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")], value_input_option='USER_ENTERED')
    st.success("피드백 감사합니다!")

end_phrases = ["상담 종료", "그만할래", "끝낼게요", "이만 마칠게요", "종료하겠습니다", "그만두고 싶어", "이제 끝", "종료", "마무리할게요"]

if prompt := st.chat_input("지금 어떤 기분이신가요?"):
    st.session_state.messages.append({"role": "user", "content": prompt})

    if any(p in prompt.lower() for p in end_phrases):
        phq_total = sum(st.session_state.phq9_scores)
        gad_total = sum(st.session_state.gad7_scores)
        now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        phq_feedback = get_phq9_feedback(phq_total)
        gad_feedback = get_gad7_feedback(gad_total)

        sheet_result.append_row([
            user_name, phq_total, gad_total, f"{len(st.session_state.phq9_scores)}/9", f"{len(st.session_state.gad7_scores)}/7", now_kst,
            prompt, st.session_state.feedback_text.strip(), phq_feedback, gad_feedback
        ], value_input_option='USER_ENTERED')

        df = pd.DataFrame({
            "이름": [user_name],
            "PHQ-9 총점": [phq_total],
            "GAD-7 총점": [gad_total],
            "PHQ-9 피드백": [phq_feedback],
            "GAD-7 피드백": [gad_feedback],
            "상담 일시": [now_kst],
            "사용자 메시지": [prompt],
            "피드백": [st.session_state.feedback_text.strip()]
        })
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        st.download_button("📄 상담 리포트 다운로드", data=io.BytesIO(csv_buffer.getvalue().encode("utf-8-sig")), file_name=f"Report_{user_name}.csv")
        st.success("상담이 종료되었습니다. 언제든지 다시 찾아주세요.")

    else:
        with st.spinner("상담 중..."):
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "당신은 따뜻하고 공감하는 심리상담 챗봇입니다. 필요시 PHQ-9 또는 GAD-7 설문을 자연스럽게 안내하세요."},
                    *st.session_state.messages
                ]
            )
            reply = response.choices[0].message.content
            st.session_state.messages.append({"role": "assistant", "content": reply})

# === 메시지 출력 ===
for msg in st.session_state.messages:
    if msg["role"] != "system":
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

# === 설문 폼 ===
if user_name:
    with st.form("phq_gad_form"):
        st.subheader("📝 PHQ-9 설문")
        for i, q in enumerate(phq9_questions):
            st.session_state.phq9_scores.append(score_options[st.radio(q, list(score_options.keys()), key=f"phq{i}")])

        st.subheader("😟 GAD-7 설문")
        for i, q in enumerate(gad7_questions):
            st.session_state.gad7_scores.append(score_options[st.radio(q, list(score_options.keys()), key=f"gad{i}")])

        if st.form_submit_button("→ 설문 제출"):
            st.success("설문이 제출되었습니다. '상담 종료'를 입력하면 결과가 정리됩니다.")
