# 감정상담 챗봇 + PHQ-9 & GAD-7 평가 (완전 통합, rerun 제거)
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
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
gs_client = gspread.authorize(creds)
sheet_result = gs_client.open("PHQ9_결과_저장소").worksheet("Sheet1")
sheet_feedback = gs_client.open("PHQ9_결과_저장소").worksheet("Feedbacks")

# === 상수 및 질문지 정의 ===
KST = timezone(timedelta(hours=9))
END_PHRASES = ["상담 종료","그만할래","끝낼게요","이만 마칠게요","종료하겠습니다",
               "그만두고 싶어","이제 끝","종료","마무리할게요","이제 그만" ]
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
OPTIONS = ["전혀 아님 (0점)", "며칠 동안 (1점)", "일주일 이상 (2점)", "거의 매일 (3점)"]

# === 분석 함수 ===
def analyze_scores(scores, thresholds, levels, advices):
    total = sum(scores)
    for t, lvl, adv in zip(thresholds, levels, advices):
        if total <= t:
            return total, lvl, adv
    return total, levels[-1], advices[-1]

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
if 'phase' not in st.session_state:
    st.session_state.phase = 'chat'
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'scores' not in st.session_state:
    st.session_state.scores = []
if 'qtype' not in st.session_state:
    st.session_state.qtype = None
if 'qidx' not in st.session_state:
    st.session_state.qidx = 0

# === UI 렌더링 ===
st.title("🧠 감정상담 챗봇 + PHQ-9 & GAD-7")
user = st.text_input("👤 이름을 입력해주세요:")

# 상담 피드백 입력
st.subheader("📝 상담 피드백")
fb = st.text_area("자유롭게 피드백을 남겨주세요:")
if st.button("피드백 제출") and fb.strip():
    sheet_feedback.append_row(["피드백", user, fb.strip(), datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")],
                              value_input_option='USER_ENTERED')
    st.success("✅ 피드백 저장 완료")

# 이전 대화 출력
for msg in st.session_state.messages:
    with st.chat_message(msg['role']):
        st.markdown(msg['content'])

# 유저 입력 처리
if txt := st.chat_input("무엇이 궁금하신가요?"):
    st.session_state.messages.append({'role':'user','content':txt})
    # 상담 종료
    if any(e in txt for e in END_PHRASES):
        tp, lp, ap = analyze_scores(st.session_state.scores, PHQ_THRESH, PHQ_LEVELS, PHQ_ADVICE) if st.session_state.qtype=='PHQ' else (0,'','')
        tg, lg, ag = analyze_scores(st.session_state.scores, GAD_THRESH, GAD_LEVELS, GAD_ADVICE) if st.session_state.qtype=='GAD' else (0,'','')
        now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        # 저장 및 리포트
        sheet_result.append_row([user, tp, lp, tg, lg, now, txt, fb.strip(), ap+" | "+ag],
                                 value_input_option='USER_ENTERED')
        df = pd.DataFrame({
            '이름':[user],'PHQ-9':[tp],'우울 수준':[lp],'GAD-7':[tg],'불안 수준':[lg],
            '일시':[now],'피드백':[fb.strip()],'의학적 조언':[ap+" | "+ag]
        })
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        st.download_button("📄 상담 리포트 다운로드",buf.getvalue(),file_name=f"report_{user}.csv",mime="text/csv")
        st.info("상담이 종료되었습니다.")
        st.session_state.phase = 'done'
    # PHQ-9 설문 시작
    elif 'phq' in txt.lower():
        st.session_state.phase = 'survey'
        st.session_state.qtype = 'PHQ'
        st.session_state.scores = []
        st.session_state.qidx = 0
    # GAD-7 설문 시작
    elif 'gad' in txt.lower():
        st.session_state.phase = 'survey'
        st.session_state.qtype = 'GAD'
        st.session_state.scores = []
        st.session_state.qidx = 0
    # 일반 대화
    else:
        rsp = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{'role':'system','content':'당신은 공감적 상담 챗봇입니다.'}] + st.session_state.messages
        )
        reply = rsp.choices[0].message.content
        st.session_state.messages.append({'role':'assistant','content':reply})

# === 설문 흐름 ===
if st.session_state.phase == 'survey':
    questions = PHQ9 if st.session_state.qtype == 'PHQ' else GAD7
    idx = st.session_state.qidx
    total_q = len(questions)
    if idx < total_q:
        # 챗 메시지로 질문 표시
        with st.chat_message('assistant'):
            st.markdown(f"**{st.session_state.qtype}-설문 {idx+1}/{total_q}:** {questions[idx]}")
        # 폼으로 답변 수집
        form_key = f"form_{st.session_state.qtype}_{idx}"
        ans_key = f"ans_{st.session_state.qtype}_{idx}"
        with st.form(key=form_key):
            ans = st.radio("답변을 선택해주세요:", OPTIONS, key=ans_key)
            submitted = st.form_submit_button("제출")
            if submitted:
                # 응답 저장 및 다음 문항으로 이동
                st.session_state.scores.append(OPTIONS.index(ans))
                st.session_state.qidx += 1
                st.experimental_rerun()
    else:
        # 설문 완료 알림 후 챗 단계로 복귀
        st.session_state.messages.append({'role':'assistant', 'content':f"{st.session_state.qtype}-설문이 완료되었습니다. '상담 종료'를 입력하면 결과를 정리해드립니다."})
        st.session_state.phase = 'chat'
        st.experimental_rerun()
