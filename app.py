# 감정상담 챗봇 + PHQ-9 & GAD-7 평가 (완전 재구성)
import streamlit as st
import openai
import gspread
import json
import pandas as pd
import io
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone

# === 설정 및 인증 ===
openai.api_key = st.secrets["OPENAI_API_KEY"]
scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
gs_client = gspread.authorize(creds)
sheet_result = gs_client.open("PHQ9_결과_저장소").worksheet("Sheet1")
sheet_feedback = gs_client.open("PHQ9_결과_저장소").worksheet("Feedbacks")

# === 상수 ===
KST = timezone(timedelta(hours=9))
END_PHRASES = ["상담 종료","그만할래","끝낼게요","이만 마칠게요","종료하겠습니다","그만두고 싶어","이제 끝","종료","마무리할게요","이제 그만"]

# === 질문 리스트 ===
PHQ9 = [
    "최근 2주간, 일상에 흥미나 즐거움을 느끼지 못하셨나요?",
    "우울하거나 슬픈 기분이 들었던 적이 있으신가요?",
    "잠들기 어렵거나 자주 깨셨나요?",
    "피곤하고 기운이 없음을 느끼셨나요?",
    "식욕 변화(감소/증가)를 경험하셨나요?",
    "자신이 실패자라고 느끼신 적이 있으신가요?",
    "집중하기 어려움을 느끼셨나요?",
    "느리게 움직이거나 안절부절못함을 느끼셨나요?",
    "차라리 죽는 게 낫다고 생각하신 적이 있나요? (※ 생략 가능)"
]
GAD7 = [
    "긴장하거나 불안하다고 느끼신 적이 있으신가요?",
    "걱정을 멈추기 어려우셨나요?",
    "여러 가지를 지나치게 걱정하신 적이 있으신가요?",
    "편안히 쉬기 어려우셨나요?",
    "초조해서 가만히 있지 못하셨나요?",
    "쉽게 짜증이 나거나 예민해지셨나요?",
    "끔찍한 일이 일어날 것 같다고 느끼신 적이 있으신가요?"
]
OPTIONS = ["전혀 아님 (0점)","며칠 동안 (1점)","일주일 이상 (2점)","거의 매일 (3점)"]

# === 분석 함수 ===
def analyze_scores(scores, thresholds, levels, advices):
    total = sum(scores)
    for t, lvl, adv in zip(thresholds, levels, advices):
        if total <= t:
            return total, lvl, adv
    return total, levels[-1], advices[-1]

# PHQ-9: [4,9,14,19]; GAD-7: [4,9,14]
PHQ_THRESH = [4,9,14,19]
PHQ_LEVELS = ["정상","경도 우울","중등도 우울","중등도 이상 우울","심한 우울"]
PHQ_ADVICE = [
    "건강한 생활습관을 유지하세요.",
    "충분한 수면과 사회적 교류를 권장합니다.",
    "규칙적 운동과 상담을 고려하세요.",
    "전문가 상담 및 약물치료를 검토하세요.",
    "즉각적인 전문 개입이 필요합니다."
]

GAD_THRESH = [4,9,14]
GAD_LEVELS = ["정상","경도 불안","중등도 불안","심한 불안"]
GAD_ADVICE = [
    "현재 상태를 유지하세요.",
    "명상 및 호흡훈련을 시도하세요.",
    "심리상담과 루틴 개선이 필요합니다.",
    "전문 평가 및 치료가 필요합니다."
]

# === 세션 초기화 ===
if 'phase' not in st.session_state: st.session_state.phase='chat'
if 'messages' not in st.session_state: st.session_state.messages=[]
if 'scores' not in st.session_state: st.session_state.scores=[]
if 'qtype' not in st.session_state: st.session_state.qtype=None
if 'qidx' not in st.session_state: st.session_state.qidx=0

# === UI ===
st.title("🧠 감정상담 챗봇 + PHQ-9 & GAD-7")
user = st.text_input("👤 이름을 입력해주세요:")

# 상담 피드백
st.subheader("📝 상담 피드백")
fb = st.text_area("자유롭게 피드백을 남겨주세요:")
if st.button("피드백 제출") and fb.strip():
    sheet_feedback.append_row(["피드백",user,fb,datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")],value_input_option='USER_ENTERED')
    st.success("✅ 피드백 저장 완료")

# 챗 메시지 출력
for m in st.session_state.messages:
    with st.chat_message(m['role']): st.markdown(m['content'])

# 유저 입력 처리
if txt := st.chat_input("무엇이 궁금하신가요?"):
    st.session_state.messages.append({'role': 'user', 'content': txt})
    # 종료
    if any(e in txt for e in END_PHRASES):
        # ... existing termination logic ...
        st.session_state.phase = 'done'
        st.experimental_rerun()
    # PHQ-9 시작
    elif 'phq' in txt.lower():
        st.session_state.phase = 'survey'
        st.session_state.qtype = 'PHQ'
        st.session_state.scores = []
        st.session_state.qidx = 0
        st.experimental_rerun()
    # GAD-7 시작
    elif 'gad' in txt.lower():
        st.session_state.phase = 'survey'
        st.session_state.qtype = 'GAD'
        st.session_state.scores = []
        st.session_state.qidx = 0
        st.experimental_rerun()
    # 일반 대화
    else:
        res = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{'role': 'system', 'content': '당신은 따뜻하고 공감적인 상담 챗봇입니다.'}] + st.session_state.messages
        )
        rp = res.choices[0].message.content
        st.session_state.messages.append({'role': 'assistant', 'content': rp})
        st.experimental_rerun()

# 설문 흐름 처리
if st.session_state.phase == 'survey':
    qlist = PHQ9 if st.session_state.qtype == 'PHQ' else GAD7
    total_q = len(qlist)
    idx = st.session_state.qidx
    if idx < total_q:
        st.chat_message('assistant').markdown(f"**{st.session_state.qtype}-설문 {idx+1}/{total_q}:** {qlist[idx]}")
        ans = st.radio("답변", OPTIONS, key=f"ans{idx}")
        if st.button("제출", key=f"sub{idx}"):
            st.session_state.scores.append(OPTIONS.index(ans))
            st.session_state.qidx += 1
            st.experimental_rerun()
    else:
        st.session_state.messages.append({'role': 'assistant', 'content': f"{st.session_state.qtype}-설문이 완료되었습니다."})
        st.session_state.phase = 'chat'
        st.experimental_rerun()
if st.session_state.phase=='survey':
    qlist = PHQ9 if st.session_state.qtype=='PHQ' else GAD7
    total_q = len(qlist)
    idx=st.session_state.qidx
    if idx<total_q:
        st.chat_message('assistant').markdown(f"**{st.session_state.qtype}-설문 {idx+1}/{total_q}:** {qlist[idx]}")
        ans=st.radio("답변",OPTIONS,key=f"ans{idx}")
        if st.button("제출",key=f"sub{idx}"):
            st.session_state.scores.append(OPTIONS.index(ans))
            st.session_state.qidx+=1
    else:
        st.chat_message('assistant').markdown(f"{st.session_state.qtype}-설문이 완료되었습니다.")
        st.session_state.phase='chat'
