# 감정상담 챗봇 + PHQ-9 & GAD-7 평가 (완전 통합 챗 기반 버전)
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

# === 상수 ===
KST = timezone(timedelta(hours=9))
end_phrases = ["상담 종료","그만할래","끝낼게요","이만 마칠게요","종료하겠습니다","그만두고 싶어","이제 끝","종료","마무리할게요","이제 그만"]

# === 질문 리스트 ===
phq9_questions = [
    "1. 최근 2주간, 일상에 흥미나 즐거움을 느끼지 못하셨나요?",
    "2. 우울하거나 슬픈 기분이 들었던 적이 있었나요?",
    "3. 잠들기 어렵거나 자주 깼거나 너무 많이 주무셨나요?",
    "4. 피곤하고 기운이 없음을 느끼셨나요?",
    "5. 식욕 변화(감소 또는 과식)가 있었나요?",
    "6. 자신을 실패자라고 느끼셨나요?",
    "7. 집중하기 어려움을 느끼셨나요?",
    "8. 느리게 움직이거나 안절부절못함이 있었나요?",
    "9. 차라리 죽는 것이 낫다고 느끼신 적이 있나요? (※ 생략 가능)"
]

gad7_questions = [
    "1. 지난 2주간 긴장하거나 불안하다고 느끼셨나요?",
    "2. 걱정을 멈추기 어려웠나요?",
    "3. 여러 가지를 지나치게 걱정하셨나요?",
    "4. 편안히 쉬기 어려웠나요?",
    "5. 가만히 있기 힘들 정도로 불안하셨나요?",
    "6. 쉽게 짜증이 나거나 예민해지셨나요?",
    "7. 끔찍한 일이 일어날 것 같다고 느끼셨나요?"
]

score_options = ["전혀 아님 (0점)","며칠 동안 (1점)","일주일 이상 (2점)","거의 매일 (3점)"]

# === 분석 함수 ===
def analyze_phq9(scores):
    total = sum(scores)
    if total <= 4: level, advice = "정상","건강한 생활습관을 유지하세요."
    elif total <= 9: level, advice = "경도 우울","충분한 수면과 사회적 교류를 권장합니다."
    elif total <= 14: level, advice = "중등도 우울","운동, 상담을 고려해보세요."
    elif total <= 19: level, advice = "중등도 이상 우울","전문가 상담 및 약물치료를 검토하세요."
    else: level, advice = "심한 우울","즉각적인 전문 개입이 필요합니다."
    return total, level, advice

def analyze_gad7(scores):
    total = sum(scores)
    if total <= 4: level, advice = "정상","현재 상태를 유지하세요."
    elif total <= 9: level, advice = "경도 불안","명상, 호흡훈련을 시도하세요."
    elif total <= 14: level, advice = "중등도 불안","심리상담과 루틴 개선이 필요합니다."
    else: level, advice = "심한 불안","전문 평가 및 치료가 필요합니다."
    return total, level, advice

# === 상태 초기화 ===
if 'messages' not in st.session_state: st.session_state.messages=[]
if 'phase' not in st.session_state: st.session_state.phase='chat'
if 'phq_scores' not in st.session_state: st.session_state.phq_scores=[]
if 'gad_scores' not in st.session_state: st.session_state.gad_scores=[]
if 'qindex' not in st.session_state: st.session_state.qindex=0

# === UI ===
st.title("🧠 감정상담 챗봇 + PHQ-9 & GAD-7")
user_name = st.text_input("👤 상담자 이름 입력:")
# 피드백
feedback = st.text_area("📝 상담 피드백을 남겨주세요:")
if st.button("피드백 제출") and feedback.strip():
    sheet_feedback.append_row(["피드백",user_name,feedback.strip(),datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")],value_input_option='USER_ENTERED')
    st.success("✅ 피드백 저장 완료")

# 챗 메시지 출력
for m in st.session_state.messages:
    with st.chat_message(m['role']): st.markdown(m['content'])

# 챗 입력 핸들링
if prompt := st.chat_input("무엇을 도와드릴까요?"):
    st.session_state.messages.append({'role':'user','content':prompt})
    # 종료
    if any(p in prompt for p in end_phrases):
        total_p, lvl_p, adv_p = analyze_phq9(st.session_state.phq_scores)
        total_g, lvl_g, adv_g = analyze_gad7(st.session_state.gad_scores)
        now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        # 저장
        sheet_result.append_row([user_name,total_p,lvl_p,total_g,lvl_g,now,prompt,feedback,adv_p+" | "+adv_g],value_input_option='USER_ENTERED')
        # 리포트
        df=pd.DataFrame({
            '이름':[user_name],'PHQ-9':[total_p],'우울 수준':[lvl_p],'GAD-7':[total_g],'불안 수준':[lvl_g],'일시':[now],'피드백':[feedback],'의학적 조언':[adv_p+" | "+adv_g]
        })
        buf=io.StringIO();df.to_csv(buf,index=False)
        st.download_button("📄 리포트 다운로드",buf.getvalue(),file_name=f"report_{user_name}.csv",mime="text/csv")
        st.info("상담이 종료되었습니다.")
        st.session_state.phase='done'
    # PHQ-9 요청
    elif 'phq' in prompt.lower():
        st.session_state.phase='phq'
        st.session_state.qindex=0
    # GAD-7 요청
    elif 'gad' in prompt.lower():
        st.session_state.phase='gad'
        st.session_state.qindex=0
    # 일반 대화
    else:
        rsp=openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{'role':'system','content':'당신은 공감적인 상담 챗봇입니다.'}]+st.session_state.messages
        )
        reply=rsp.choices[0].message.content
        st.session_state.messages.append({'role':'assistant','content':reply})
# 설문 흐름
if st.session_state.phase=='phq':
    idx=st.session_state.qindex
    if idx<len(phq9_questions):
        st.chat_message('assistant').markdown(f"**PHQ-9 문항 {idx+1}/9:** {phq9_questions[idx]}")
        ans = st.radio("답변",score_options,key=f"phq{idx}")
        if st.button("제출",key=f"subp{idx}"):
            st.session_state.phq_scores.append(score_options.index(ans))
            st.session_state.qindex+=1
    else:
        st.session_state.messages.append({'role':'assistant','content':'PHQ-9 설문을 모두 완료했습니다.'})
        st.session_state.phase='chat'
if st.session_state.phase=='gad':
    idx=st.session_state.qindex
    if idx<len(gad7_questions):
        st.chat_message('assistant').markdown(f"**GAD-7 문항 {idx+1}/7:** {gad7_questions[idx]}")
        ans = st.radio("답변",score_options,key=f"gad{idx}")
        if st.button("제출",key=f"subg{idx}"):
            st.session_state.gad_scores.append(score_options.index(ans))
            st.session_state.qindex+=1
    else:
        st.session_state.messages.append({'role':'assistant','content':'GAD-7 설문을 모두 완료했습니다.'})
        st.session_state.phase='chat'
