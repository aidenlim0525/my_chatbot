# 감정상담 챗봇 + PHQ-9 평가 (최종 개선)
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

# === PHQ-9 질문 ===
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

score_options = {
    "전혀 아님 (0점)": 0,
    "며칠 동안 (1점)": 1,
    "일주일 이상 (2점)": 2,
    "거의 매일 (3점)": 3
}

KST = timezone(timedelta(hours=9))

if "messages" not in st.session_state:
    st.session_state.messages = []
if "phq9_scores" not in st.session_state:
    st.session_state.phq9_scores = []
if "feedback_text" not in st.session_state:
    st.session_state.feedback_text = ""

st.title("🧠 감정상담 챗봇 + PHQ-9 평가")
user_name = st.text_input("👤 상담자 이름을 입력해주세요:")

# 피드백 입력 UI 항상 표시
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

if prompt := st.chat_input("지금 어떤 기분이신가요?"):
    st.session_state.messages.append({"role": "user", "content": prompt})

    if any(p in prompt.lower() for p in end_phrases):
        scores = st.session_state.phq9_scores
        answered = len(scores)

        if answered == 0:
            st.warning("PHQ-9 문항에 대한 답변이 없습니다.")
        else:
            avg_score = sum(scores) / answered
            predicted_scores = scores + [round(avg_score)] * (9 - answered)
            total = sum(predicted_scores)

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

            st.success(f"예측 총점: {total}점 → 우울 수준: {level} (답변 {answered}/9개 기준)")
            if len(predicted_scores) >= 9 and predicted_scores[8] >= 1:
                st.error("⚠️ 자살 관련 응답이 감지되었습니다. 이 챗봇은 상담도구일 뿐이며, 전문가와 꼭 이야기해보세요.")

            if user_name:
                try:
                    now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
                    sheet_result.append_row([
                        user_name, total, level, f"{answered}/9", now_kst,
                        prompt,
                        st.session_state.messages[-1]["content"] if st.session_state.messages else "-",
                        ", ".join([word for word in ["우울", "힘들", "죽고", "자살"] if word in prompt]),
                        st.session_state.feedback_text.strip()
                    ], value_input_option='USER_ENTERED')
                    st.success("✅ Google Sheets에 저장 완료!")
                except Exception as e:
                    st.error("❌ 저장 중 오류 발생")
                    st.exception(e)

            csv_data = pd.DataFrame({
                "이름": [user_name],
                "총점": [total],
                "우울 수준": [level],
                "응답 수": [f"{answered}/9"],
                "상담 일시": [datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")],
                "사용자 메시지": [prompt],
                "GPT 응답": [st.session_state.messages[-1]["content"] if st.session_state.messages else "-"],
                "감정 키워드": [", ".join([word for word in ["우울", "힘들", "죽고", "자살"] if word in prompt])],
                "피드백": [st.session_state.feedback_text.strip()]
            })
            csv_buffer = io.StringIO()
            csv_data.to_csv(csv_buffer, index=False)
            csv_bytes = io.BytesIO(csv_buffer.getvalue().encode("utf-8-sig"))

            st.download_button("📄 상담 리포트 다운로드", data=csv_bytes, file_name=f"PHQ9_{user_name}.csv", mime="text/csv")
            st.info("상담이 종료되었습니다. 언제든지 다시 찾아주세요.")

    else:
        with st.spinner("상담 중..."):
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "당신은 따뜻하고 공감하는 심리상담 챗봇입니다. 사용자의 감정에 공감하고, 필요 시 'PHQ-9 설문을 함께 시작해보자'고 자연스럽게 유도하세요."},
                    *st.session_state.messages
                ]
            )
            reply = response.choices[0].message.content
            reply = reply.replace("PHQ-9 설문을 진행할 수 없어요.", "PHQ-9 설문은 아래에서 진행하실 수 있어요. 함께 시작해봐요!")
            st.session_state.messages.append({"role": "assistant", "content": reply})

        triggers = ["우울", "힘들", "슬퍼", "무기력", "죽고", "지쳤", "자살", "죽고싶다", "죽고 싶다", "끝내고 싶다"]
        trigger_phrases = ["phq", "설문", "검사", "질문해줘", "테스트"]

        if any(word in prompt for word in triggers) or any(p in prompt.lower() for p in trigger_phrases):
            st.session_state.show_phq9 = True

for msg in st.session_state.messages:
    if msg["role"] != "system":
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

if st.session_state.get("show_phq9") and user_name:
    st.subheader("📝 PHQ-9 설문")
    with st.form("phq9_form"):
        scores = []
        for i, q in enumerate(phq9_questions):
            if i == 8:
                st.warning("⚠️ 마지막 문항은 민감할 수 있습니다. 원하지 않으면 생략 가능합니다.")
            score = st.radio(q, list(score_options.keys()), key=f"q{i}", index=0)
            scores.append(score_options[score])
        submitted = st.form_submit_button("→ 설문 제출")
        if submitted:
            st.session_state.phq9_scores = scores
            st.session_state.show_phq9 = False
            st.success("PHQ-9 설문이 제출되었습니다. '상담 종료'를 입력하면 결과가 정리됩니다.")