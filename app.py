# 감정상담 챗봇 + PHQ-9 & GAD-7 평가 (캔버스 최종 수정본)
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
    "1. 최근 2주간, 걱정이나 불안이 자주 있었나요?",
    "2. 여러 가지를 지나치게 걱정한 적이 있었나요?",
    "3. 걱정을 멈추기 힘들었던 적이 있었나요?",
    "4. 쉬거나 이완하는 것이 어려웠던 적이 있었나요?",
    "5. 초조하거나 가만히 있지 못한 적이 있었나요?",
    "6. 쉽게 짜증을 내거나 신경질적으로 느꼈던 적이 있었나요?",
    "7. 끔찍한 일이 일어날 것 같다고 느낀 적이 있었나요?"
]
score_options = {
    "전혀 아님 (0점)": 0,
    "며칠 동안 (1점)": 1,
    "일주일 이상 (2점)": 2,
    "거의 매일 (3점)": 3
}

# --- 분석 함수 ---
def analyze_phq9(scores):
    total = sum(scores)
    if total <= 4:
        level = "정상"
        feedback = "정상 범위입니다. 건강한 생활습관(충분한 수면, 규칙적인 식사, 사회활동)을 유지하세요."
    elif total <= 9:
        level = "경도 우울"
        feedback = "경미한 우울감입니다. 충분한 휴식과 스트레스 해소를 위한 운동, 대화, 취미생활을 권장합니다."
    elif total <= 14:
        level = "중등도 우울"
        feedback = "중등도의 우울감이 의심됩니다. 규칙적 운동과 루틴 관리, 필요하다면 전문가 상담을 권장합니다."
    elif total <= 19:
        level = "중등도 이상 우울"
        feedback = "우울감이 일상에 영향을 미칠 수 있습니다. 정신건강 전문가의 상담 및 약물치료가 필요할 수 있습니다."
    else:
        level = "심한 우울"
        feedback = "즉각적인 전문의 상담 및 치료가 필요합니다. 가까운 정신건강의학과를 방문하세요."
    if total >= 10:
        feedback += "\n\n- **의학적 참고**: 우울이 심할 때는 세로토닌, 도파민 등 신경전달물질의 불균형이 발생할 수 있습니다. 햇빛 쬐기, 산책, 영양 섭취가 뇌 호르몬 균형 유지에 도움이 됩니다.\n- 아침에 일찍 일어나기, 소소한 목표 세우기, 주변인과 대화, 자기 전 스마트폰 사용 줄이기 등도 추천합니다."
    return total, level, feedback

def analyze_gad7(scores):
    total = sum(scores)
    if total <= 4:
        level = "정상"
        feedback = "불안 수준이 정상 범위입니다. 규칙적인 생활과 충분한 수면을 유지하세요."
    elif total <= 9:
        level = "경도 불안"
        feedback = "경미한 불안이 있습니다. 심호흡, 명상, 가벼운 운동, 걱정거리를 노트에 적어보는 습관이 도움이 됩니다."
    elif total <= 14:
        level = "중등도 불안"
        feedback = "중등도의 불안이 있습니다. 정서적 지지와 전문가 상담, 필요 시 약물치료를 고려하세요."
    else:
        level = "심한 불안"
        feedback = "심한 불안 상태입니다. 즉시 정신건강 전문가와 상담을 권장합니다."
    if total >= 10:
        feedback += "\n\n- **의학적 참고**: 불안이 심하면 아드레날린, 코티솔 등 스트레스 호르몬이 과다 분비되어 심장 두근거림, 소화불량, 불면 등이 동반될 수 있습니다.\n- 규칙적 수면, 깊은 호흡, 디지털 디톡스, 운동, 현실적인 목표 설정 등을 실천하세요."
    return total, level, feedback

# === 세션 상태 ===
if "messages" not in st.session_state:
    st.session_state.messages = []
if "phq9_scores" not in st.session_state:
    st.session_state.phq9_scores = []
if "gad7_scores" not in st.session_state:
    st.session_state.gad7_scores = []
if "show_phq9" not in st.session_state:
    st.session_state.show_phq9 = False
if "show_gad7" not in st.session_state:
    st.session_state.show_gad7 = False
if "feedback_text" not in st.session_state:
    st.session_state.feedback_text = ""

# === UI ===
st.title("🧠 감정상담 챗봇 + PHQ-9 & GAD-7 평가")
user_name = st.text_input("👤 상담자 이름을 입력해주세요:")

# 피드백 입력
st.subheader("📝 상담 피드백")
st.session_state.feedback_text = st.text_area("자유롭게 피드백을 남겨주세요:", value=st.session_state.feedback_text)
if st.button("피드백 제출"):
    if st.session_state.feedback_text.strip():
        try:
            sheet_feedback.append_row(["피드백", user_name, st.session_state.feedback_text.strip(), datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")], value_input_option='USER_ENTERED')
            st.success("피드백 감사합니다!")
        except Exception as e:
            st.error("❌ 피드백 저장 실패")
            st.exception(e)
    else:
        st.warning("피드백 내용을 입력해주세요.")

end_phrases = ["상담 종료", "그만할래", "끝낼게요", "이만 마칠게요", "종료하겠습니다", "그만두고 싶어", "이제 끝", "종료", "마무리할게요", "이제 그만"]

# === 채팅 입력 ===
if prompt := st.chat_input("지금 어떤 기분이신가요?"):
    st.session_state.messages.append({"role": "user", "content": prompt})

    # 설문 키워드 감지(설문 플래그만 True로 세팅, assistant 호출X)
    if any(word in prompt.lower() for word in ["phq", "우울", "설문", "질문", "테스트"]):
        st.session_state.show_phq9 = True
    elif any(word in prompt.lower() for word in ["gad", "불안"]):
        st.session_state.show_gad7 = True
    # 상담 종료
    elif any(p in prompt.lower() for p in end_phrases):
        phq9_scores = st.session_state.phq9_scores
        gad7_scores = st.session_state.gad7_scores
        phq9_total, phq9_level, phq9_feedback = analyze_phq9(phq9_scores) if phq9_scores else (None, None, None)
        gad7_total, gad7_level, gad7_feedback = analyze_gad7(gad7_scores) if gad7_scores else (None, None, None)

        result_message = ""
        if phq9_total is not None:
            result_message += f"PHQ-9: {phq9_total}점 ({phq9_level})\n{phq9_feedback}\n\n"
            if len(phq9_scores) >= 9 and phq9_scores[8] >= 1:
                result_message += "⚠️ 자살 관련 응답이 감지되었습니다. 반드시 전문가와 직접 상담하세요.\n"
        if gad7_total is not None:
            result_message += f"GAD-7: {gad7_total}점 ({gad7_level})\n{gad7_feedback}\n\n"
        if not result_message:
            result_message = "아직 설문 응답이 입력되지 않았습니다."

        st.session_state.messages.append({"role": "assistant", "content": result_message})

        # Google 시트 저장
        if user_name:
            try:
                now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
                sheet_result.append_row([
                    user_name, phq9_total or "-", phq9_level or "-", gad7_total or "-", gad7_level or "-",
                    now_kst, prompt,
                    st.session_state.messages[-1]["content"],
                    st.session_state.feedback_text.strip()
                ], value_input_option='USER_ENTERED')
                st.success("✅ Google Sheets에 저장 완료!")
            except Exception as e:
                st.error("❌ 저장 중 오류 발생")
                st.exception(e)

        # 리포트 다운로드
        csv_data = pd.DataFrame({
            "이름": [user_name],
            "PHQ-9 총점": [phq9_total],
            "PHQ-9 우울 수준": [phq9_level],
            "GAD-7 총점": [gad7_total],
            "GAD-7 불안 수준": [gad7_level],
            "상담 일시": [datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")],
            "상담 요약": [prompt],
            "AI 피드백": [result_message],
            "피드백": [st.session_state.feedback_text.strip()]
        })
        csv_buffer = io.StringIO()
        csv_data.to_csv(csv_buffer, index=False)
        csv_bytes = io.BytesIO(csv_buffer.getvalue().encode("utf-8-sig"))

        st.download_button("📄 상담 리포트 다운로드", data=csv_bytes, file_name=f"PHQ9GAD7_{user_name}.csv", mime="text/csv")
        st.info("상담이 종료되었습니다. 언제든지 다시 찾아주세요.")

    # 일반 챗봇 대화 (설문, 종료 둘 다 아니면 assistant 반드시 호출)
    else:
        with st.spinner("상담 중..."):
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content":
                        "당신은 따뜻하고 공감하는 심리상담 챗봇입니다. 띄어쓰기, 맞춤법, 논리와 단정성을 유지하세요. 필요시 PHQ-9 또는 GAD-7 설문으로 자연스럽게 유도하고, 우울/불안/자살 위험이 언급되면 전문적인 조언과 함께 설문 응시를 권유하세요."},
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

# === PHQ-9 설문 (한 번에 form) ===
if st.session_state.get("show_phq9") and user_name:
    st.subheader("📝 PHQ-9 설문")
    with st.form("phq9_form"):
        scores = []
        for i, q in enumerate(phq9_questions):
            if i == 8:
                st.warning("⚠️ 마지막 문항은 민감할 수 있습니다. 원하지 않으면 생략 가능합니다.")
            score = st.radio(q, list(score_options.keys()), key=f"phq9_{i}", index=0)
            scores.append(score_options[score])
        submitted = st.form_submit_button("→ PHQ-9 설문 제출")
        if submitted:
            st.session_state.phq9_scores = scores
            st.session_state.show_phq9 = False
            st.success("PHQ-9 설문이 제출되었습니다. 추가로 불안이 있으시면 'GAD-7'을 입력해주세요. 상담 종료시 모든 결과가 안내됩니다.")

# === GAD-7 설문 (한 번에 form) ===
if st.session_state.get("show_gad7") and user_name:
    st.subheader("📝 GAD-7 설문")
    with st.form("gad7_form"):
        scores = []
        for i, q in enumerate(gad7_questions):
            score = st.radio(q, list(score_options.keys()), key=f"gad7_{i}", index=0)
            scores.append(score_options[score])
        submitted = st.form_submit_button("→ GAD-7 설문 제출")
        if submitted:
            st.session_state.gad7_scores = scores
            st.session_state.show_gad7 = False
            st.success("GAD-7 설문이 제출되었습니다. 상담 종료시 모든 결과가 안내됩니다.")
