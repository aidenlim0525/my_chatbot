# 감정상담 챗봇 + PHQ-9 + GAD-7 평가
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

# === 질문 ===
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
    "1. 사소한 일에도 지나치게 걱정한 적이 있었나요?",
    "2. 여러 가지 일을 동시에 하기가 힘들었던 적이 있었나요?",
    "3. 과민하거나 쉽게 긴장했던 적이 있었나요?",
    "4. 긴장해서 근육이 뻣뻣했던 적이 있었나요?",
    "5. 걱정을 멈출 수 없었던 적이 있었나요?",
    "6. 안절부절 못하며 쉽게 놀랐던 적이 있었나요?",
    "7. 최악의 상황을 상상하며 불안했던 적이 있었나요?"
]
score_options = {
    "전혀 아님 (0점)": 0,
    "며칠 동안 (1점)": 1,
    "일주일 이상 (2점)": 2,
    "거의 매일 (3점)": 3
}

# === 세션 초기화 ===
if "messages" not in st.session_state:
    st.session_state.messages = []
if "phq9_scores" not in st.session_state:
    st.session_state.phq9_scores = []
if "gad7_scores" not in st.session_state:
    st.session_state.gad7_scores = []
if "feedback_text" not in st.session_state:
    st.session_state.feedback_text = ""

# === UI 구성 ===
st.title("🧠 감정상담 챗봇 + PHQ-9 + GAD-7 평가")
user_name = st.text_input("👤 상담자 이름을 입력해주세요:")

st.subheader("📝 상담 피드백")
st.session_state.feedback_text = st.text_area("자유롭게 피드백을 남겨주세요:", value=st.session_state.feedback_text)
if st.button("피드백 제출"):
    if st.session_state.feedback_text.strip():
        try:
            sheet_feedback.append_row([
                "피드백", user_name, st.session_state.feedback_text.strip(),
                datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
            ], value_input_option='USER_ENTERED')
            st.success("피드백 감사합니다!")
        except Exception as e:
            st.error("❌ 피드백 저장 실패")
            st.exception(e)
    else:
        st.warning("피드백 내용을 입력해주세요.")

# === 설문 실행 ===
st.subheader("📋 PHQ-9 우울 척도 설문")
with st.form("phq9_form"):
    for i, q in enumerate(phq9_questions):
        if i == 8:
            st.warning("⚠️ 마지막 문항은 민감할 수 있습니다. 원하지 않으면 생략 가능합니다.")
        score = st.radio(q, list(score_options.keys()), key=f"phq{i}")
        st.session_state.phq9_scores.append(score_options[score])
    st.form_submit_button("→ PHQ-9 제출")

st.subheader("📋 GAD-7 불안 척도 설문")
with st.form("gad7_form"):
    for i, q in enumerate(gad7_questions):
        score = st.radio(q, list(score_options.keys()), key=f"gad{i}")
        st.session_state.gad7_scores.append(score_options[score])
    st.form_submit_button("→ GAD-7 제출")

# === 결과 분석 ===
def analyze_phq9(scores):
    total = sum(scores)
    if total <= 4:
        level = "정상"
    elif total <= 9:
        level = "경도 우울"
    elif total <= 14:
        level = "중등도 우울"
    elif total <= 19:
        level = "중등도 이상 우울"
    else:
        level = "심한 우울"
    return total, level

def analyze_gad7(scores):
    total = sum(scores)
    if total <= 4:
        level = "정상"
    elif total <= 9:
        level = "경도 불안"
    elif total <= 14:
        level = "중등도 불안"
    else:
        level = "중증 불안"
    return total, level

if st.button("상담 종료 및 결과 요약"):
    phq_total, phq_level = analyze_phq9(st.session_state.phq9_scores)
    gad_total, gad_level = analyze_gad7(st.session_state.gad7_scores)

    st.success(f"PHQ-9 점수: {phq_total}점 → 우울 수준: {phq_level}")
    st.success(f"GAD-7 점수: {gad_total}점 → 불안 수준: {gad_level}")

    st.markdown("### 🔍 우울 분석 피드백")
    if phq_level in ["중등도 이상 우울", "심한 우울"]:
        st.write("- 세로토닌, 도파민 등의 신경전달물질 불균형이 의심됩니다.")
        st.write("- 규칙적인 수면, 햇빛 노출, 운동이 도움이 됩니다.")
        st.write("- 정신건강의학과 상담을 권장드립니다.")
    elif phq_level == "중등도 우울":
        st.write("- 스트레스 관리와 정서적 지지 확보가 중요합니다.")
    else:
        st.write("- 현재 상태는 양호하지만 꾸준한 자기관리가 필요합니다.")

    st.markdown("### 🔍 불안 분석 피드백")
    if gad_level in ["중등도 불안", "중증 불안"]:
        st.write("- 과도한 코르티솔 분비가 원인일 수 있습니다.")
        st.write("- 심호흡, 명상, 수면 개선이 효과적입니다.")
        st.write("- 필요 시 정신건강 전문가와 상의해주세요.")
    elif gad_level == "경도 불안":
        st.write("- 불안 유발 요인을 기록하고 점검해보는 것도 좋습니다.")
    else:
        st.write("- 불안 수준은 정상입니다. 꾸준한 루틴을 유지하세요.")

    # 결과 저장 및 다운로드
    if user_name:
        now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        try:
            sheet_result.append_row([
                user_name, phq_total, phq_level, f"{len(st.session_state.phq9_scores)}/9",
                gad_total, gad_level, now_kst, st.session_state.feedback_text.strip()
            ], value_input_option='USER_ENTERED')
            st.success("✅ Google Sheets 저장 완료")
        except Exception as e:
            st.error("❌ Google Sheets 저장 실패")
            st.exception(e)

        df = pd.DataFrame({
            "이름": [user_name],
            "PHQ-9 총점": [phq_total],
            "우울 수준": [phq_level],
            "GAD-7 총점": [gad_total],
            "불안 수준": [gad_level],
            "응답 수": [f"{len(st.session_state.phq9_scores)}/9"],
            "상담 일시": [now_kst],
            "피드백": [st.session_state.feedback_text.strip()]
        })
        buffer = io.StringIO()
        df.to_csv(buffer, index=False)
        bytes_io = io.BytesIO(buffer.getvalue().encode("utf-8-sig"))
        st.download_button("📄 상담 리포트 다운로드", data=bytes_io, file_name=f"report_{user_name}.csv")
