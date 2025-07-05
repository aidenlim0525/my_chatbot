import streamlit as st
import openai
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 페이지 제목
st.title("🧠 감정상담 챗봇 + PHQ-9 평가")

# 사용자 이름 입력
user_name = st.text_input("👤 상담자 이름을 입력해주세요:")

# OpenAI API 키 설정
openai.api_key = st.secrets["OPENAI_API_KEY"]

# 구글 시트 인증
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
gs_client = gspread.authorize(creds)
sheet = gs_client.open("PHQ9_결과_저장소").sheet1

# PHQ-9 질문
phq9_questions = [
    "1. 최근 2주간, 일상에 흥미나 즐거움을 느끼지 못한 적이 있었나요?",
    "2. 우울하거나 슬픈 기분이 들었던 적이 있었나요?",
    "3. 잠들기 어렵거나 자주 깼거나 너무 많이 잔 적이 있었나요?",
    "4. 피곤하고 기운이 없다고 느낀 적이 있었나요?",
    "5. 식욕이 줄었거나 과식한 적이 있었나요?",
    "6. 자신에 대해 나쁘게 느끼거나, 실패자라고 느낀 적이 있었나요?",
    "7. 집중하기 어렵다고 느낀 적이 있었나요?",
    "8. 다른 사람들이 알아차릴 정도로 느리게 움직였거나, 지나치게 안절부절못한 적이 있었나요?",
    "9. 차라리 죽는 게 낫겠다고 생각하거나 자해 생각을 한 적이 있었나요?"
]

score_options = {
    "전혀 아님 (0점)": 0,
    "며칠 동안 (1점)": 1,
    "일주일 이상 (2점)": 2,
    "거의 매일 (3점)": 3
}

# 챗봇 메시지 상태 초기화
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "system", "content": "당신은 공감 잘하는 따뜻한 심리상담 챗봇입니다. 사용자의 감정을 세심하게 파악하고, 우울감이 느껴지면 자연스럽게 PHQ-9 문항으로 이끌어주세요."}
    ]
if "phq9_scores" not in st.session_state:
    st.session_state.phq9_scores = []
if "asked_indices" not in st.session_state:
    st.session_state.asked_indices = set()

# 사용자 입력 받기
if prompt := st.chat_input("지금 어떤 기분이신가요?"):
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.spinner("상담 중..."):
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=st.session_state.messages
        )
        reply = response.choices[0].message.content
        st.session_state.messages.append({"role": "assistant", "content": reply})

        # 키워드 감지
        triggers = ["우울", "힘들", "슬퍼", "무기력", "죽고", "지쳤"]
        if any(word in prompt for word in triggers):
            next_q = len(st.session_state.phq9_scores)
            if next_q < len(phq9_questions) and next_q not in st.session_state.asked_indices:
                st.session_state.asked_indices.add(next_q)
                st.session_state.show_phq9 = True
                st.session_state.current_q = next_q

# 메시지 출력
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# PHQ-9 질문 출력
if st.session_state.get("show_phq9") and user_name:
    q_idx = st.session_state.current_q
    score = st.radio(
        f"📍 추가 질문: {phq9_questions[q_idx]}",
        list(score_options.keys()),
        key=f"phq9_{q_idx}"
    )
    if st.button("→ 점수 제출", key=f"submit_{q_idx}"):
        st.session_state.phq9_scores.append(score_options[score])
        st.session_state.show_phq9 = False

# 종료 후 결과 정리
if len(st.session_state.phq9_scores) == 9:
    total = sum(st.session_state.phq9_scores)
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

    st.success(f"총점: {total}점 → 우울 수준: {level}")
    if st.session_state.phq9_scores[8] >= 1:
        st.error("⚠️ 자살 관련 문항에 응답이 있습니다. 반드시 전문가 상담이 필요합니다.")

    # 시트 저장
    if user_name:
        sheet.append_row([user_name, total, level])
        st.balloons()
        st.info("구글 시트에 결과 저장 완료!")
