# 감정상담 챗봇 + PHQ-9 & GAD-7 평가 통합 버전
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

# === 상수 정의 ===
KST = timezone(timedelta(hours=9))
end_phrases = ["상담 종료", "그만할래", "끝낼게요", "이만 마칠게요", "종료하겠습니다", "그만두고 싶어", "이제 끝", "종료", "마무리할게요", "이제 그만"]

# === PHQ-9 및 GAD-7 질문 ===
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

# === 상태 초기화 ===
for key in ["messages", "phq9_scores", "gad7_scores", "feedback_text"]:
    if key not in st.session_state:
        st.session_state[key] = [] if 'scores' in key else ""

# === UI 시작 ===
st.title("🧠 감정상담 챗봇 + PHQ-9 / GAD-7 평가")
user_name = st.text_input("👤 상담자 이름을 입력해주세요:")

st.subheader("📝 상담 피드백")
st.session_state.feedback_text = st.text_area("자유롭게 피드백을 남겨주세요:", value=st.session_state.feedback_text)
if st.button("피드백 제출"):
    if st.session_state.feedback_text.strip():
        sheet_feedback.append_row(["피드백", user_name, st.session_state.feedback_text.strip(), datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")], value_input_option='USER_ENTERED')
        st.success("피드백 감사합니다!")
    else:
        st.warning("피드백 내용을 입력해주세요.")

# === 진단 피드백 함수 ===
def get_phq9_feedback(score):
    if score <= 4:
        return "정상"
    elif score <= 9:
        return "경도 우울"
    elif score <= 14:
        return "중등도 우울"
    elif score <= 19:
        return "중등도 이상 우울"
    else:
        return "심한 우울"

def get_gad7_feedback(score):
    if score <= 4:
        return "정상"
    elif score <= 9:
        return "경도 불안"
    elif score <= 14:
        return "중등도 불안"
    else:
        return "심한 불안"

# === 설문 ===
if user_name:
    st.subheader("📋 PHQ-9 설문")
    with st.form("phq9_form"):
        phq_scores = [score_options[st.radio(q, list(score_options.keys()), key=f"phq_{i}")] for i, q in enumerate(phq9_questions)]
        st.session_state.phq9_scores = phq_scores
        submitted1 = st.form_submit_button("PHQ-9 제출")

    st.subheader("📋 GAD-7 설문")
    with st.form("gad7_form"):
        gad_scores = [score_options[st.radio(q, list(score_options.keys()), key=f"gad_{i}")] for i, q in enumerate(gad7_questions)]
        st.session_state.gad7_scores = gad_scores
        submitted2 = st.form_submit_button("GAD-7 제출")

    if submitted1 or submitted2:
        phq_total = sum(st.session_state.phq9_scores)
        gad_total = sum(st.session_state.gad7_scores)
        phq_level = get_phq9_feedback(phq_total)
        gad_level = get_gad7_feedback(gad_total)

        # 결과 출력
        st.success(f"PHQ-9 총점: {phq_total}점 → 우울 수준: {phq_level}")
        st.success(f"GAD-7 총점: {gad_total}점 → 불안 수준: {gad_level}")

        # 자살 위험 경고
        if st.session_state.phq9_scores[8] >= 1:
            st.error("⚠️ 자살 관련 응답이 감지되었습니다. 이 챗봇은 상담도구일 뿐이며, 전문가와 꼭 이야기해보세요.")

        # 리포트 생성 및 다운로드
        now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        report_df = pd.DataFrame({
            "이름": [user_name],
            "PHQ-9 총점": [phq_total],
            "우울 수준": [phq_level],
            "GAD-7 총점": [gad_total],
            "불안 수준": [gad_level],
            "설문 일시": [now_kst],
            "피드백": [st.session_state.feedback_text.strip()]
        })
        csv_buffer = io.StringIO()
        report_df.to_csv(csv_buffer, index=False)
        st.download_button("📄 리포트 다운로드", data=io.BytesIO(csv_buffer.getvalue().encode("utf-8-sig")), file_name=f"mental_report_{user_name}.csv", mime="text/csv")

        # Google Sheets 저장
        sheet_result.append_row([
            user_name,
            phq_total,
            phq_level,
            gad_total,
            gad_level,
            now_kst,
            st.session_state.feedback_text.strip()
        ], value_input_option='USER_ENTERED')

        st.info("상담 결과가 저장되었습니다. 감사합니다.")
