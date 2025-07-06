# 감정상담 챗봇 + PHQ-9 평가 (최종 개선: 피드백 분리 + 한글 리포트 인코딩)
import streamlit as st
import openai
import gspread
import json
import pandas as pd
import io
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# === 설정 ===
openai.api_key = st.secrets["OPENAI_API_KEY"]
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
gs_client = gspread.authorize(creds)
sheet_result = gs_client.open("PHQ9_결과_저장소").worksheet("Sheet1")
sheet_feedback = gs_client.open("PHQ9_결과_저장소").worksheet("Feedbacks")  # 피드백 전용 시트 추가 필요

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

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "system", "content": "당신은 따뜻하고 공감하는 심리상담 챗봇입니다. 사용자 감정을 경청하세요. 단, PHQ-9 설문지는 챗봇이 직접 묻지 않고 Streamlit 앱이 제공합니다."}
    ]
if "phq9_scores" not in st.session_state:
    st.session_state.phq9_scores = []
if "asked_indices" not in st.session_state:
    st.session_state.asked_indices = set()

st.title("🧠 감정상담 챗봇 + PHQ-9 평가")
user_name = st.text_input("👤 상담자 이름을 입력해주세요:")

end_phrases = ["상담 종료", "그만할래", "끝낼게요", "이만 마칠게요", "종료하겠습니다"]

if prompt := st.chat_input("지금 어떤 기분이신가요?"):
    st.session_state.messages.append({"role": "user", "content": prompt})

    if any(p in prompt for p in end_phrases):
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
                    sheet_result.append_row([user_name, total, level, f"{answered}/9", "예측 점수 포함", datetime.now().strftime("%Y-%m-%d %H:%M:%S")], value_input_option='USER_ENTERED')
                    st.success("✅ Google Sheets에 저장 완료!")
                except Exception as e:
                    st.error("❌ 저장 중 오류 발생")
                    st.exception(e)

            # 리포트 다운로드 - UTF-8-sig로 Excel 호환
            csv_data = pd.DataFrame({
                "이름": [user_name],
                "총점": [total],
                "우울 수준": [level],
                "응답 수": [f"{answered}/9"],
                "상담 일시": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                "사용자 메시지": [prompt],
                "GPT 응답": ["-"],
                "감정 키워드": ["-"]
            })
            csv_buffer = io.StringIO()
            csv_data.to_csv(csv_buffer, index=False)
            csv_bytes = io.BytesIO(csv_buffer.getvalue().encode("utf-8-sig"))

            st.download_button("📄 상담 리포트 다운로드", data=csv_bytes, file_name=f"PHQ9_{user_name}.csv", mime="text/csv")

            # 피드백 수집
            st.subheader("📝 상담 피드백")
            feedback = st.radio("상담이 도움이 되었나요?", ["많이 도움이 되었어요", "보통이에요", "도움이 되지 않았어요"])
            if feedback:
                try:
                    sheet_feedback.append_row(["피드백", user_name, feedback, datetime.now().strftime("%Y-%m-%d %H:%M:%S")], value_input_option='USER_ENTERED')
                    st.success("피드백 감사합니다!")
                except Exception as e:
                    st.error("❌ 피드백 저장 실패")
                    st.exception(e)

    else:
        with st.spinner("상담 중..."):
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=st.session_state.messages
            )
            reply = response.choices[0].message.content
            if "yes/no" in reply.lower():
                st.warning("⚠️ 챗봇이 PHQ-9 질문을 직접 물었습니다. 이 질문은 무시하고 아래 선택지로 답변해 주세요.")
            st.session_state.messages.append({"role": "assistant", "content": reply})

        triggers = ["우울", "힘들", "슬퍼", "무기력", "죽고", "지쳤", "자살", "죽고싶다", "죽고 싶다", "끝내고 싶다"]
        trigger_phrases = ["phq", "설문", "검사", "질문해줘", "테스트"]

        if any(word in prompt for word in triggers) or any(p in prompt.lower() for p in trigger_phrases):
            next_q = len(st.session_state.phq9_scores)
            if next_q < 9 and next_q not in st.session_state.asked_indices:
                st.session_state.asked_indices.add(next_q)
                st.session_state.show_phq9 = True
                st.session_state.current_q = next_q

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if st.session_state.get("show_phq9") and user_name:
    q_idx = st.session_state.current_q
    if q_idx == 8:
        st.warning("⚠️ 이 문항은 민감할 수 있습니다. 원하지 않으면 건너뛸 수 있습니다.")
    score = st.radio(
        f"📍 추가 질문: {phq9_questions[q_idx]}",
        list(score_options.keys()),
        key=f"phq9_{q_idx}"
    )
    if st.button("→ 점수 제출", key=f"submit_{q_idx}"):
        st.session_state.phq9_scores.append(score_options[score])
        st.session_state.show_phq9 = False
    if q_idx == 8:
        if st.button("→ 이 문항 건너뛰기"):
            st.session_state.phq9_scores.append(0)
            st.session_state.show_phq9 = False
