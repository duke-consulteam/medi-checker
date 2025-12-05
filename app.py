import streamlit as st
import openai
import base64
from PIL import Image

# 페이지 설정
st.set_page_config(page_title="의료기기 광고 심의기(Premium)", page_icon="🏥", layout="wide")

# 제목
st.title("🏥 3,4등급 의료기기 광고 AI 검수기 (Premium)")
st.write("의료기기법을 기반으로 텍스트와 이미지를 정밀 분석하고, **대체 이미지**를 제안합니다.")

# API 키 설정
api_key = st.secrets.get("OPENAI_API_KEY")
if not api_key:
    st.error("API 키가 설정되지 않았습니다. 관리자에게 문의하세요.")
    st.stop()

client = openai.OpenAI(api_key=api_key)

# 탭 구성
tab1, tab2 = st.tabs(["📄 텍스트 정밀 검수", "🖼️ 이미지 분석 및 보완"])

# ==========================================
# 1. 텍스트 검수 (보여주신 부분이 바로 여깁니다)
# ==========================================
with tab1:
    st.subheader("광고 문구 법령 위반 여부 확인")
    col1, col2 = st.columns(2)
    with col1:
        ad_text = st.text_area("광고 문구를 입력하세요:", height=300, placeholder="예: 기적의 치료 효과! 단 1회 만에 통증 완벽 해결...")
    
    with col2:
        if st.button("텍스트 검수 시작", type="primary"):
            if not ad_text:
                st.warning("문구를 입력해주세요.")
            else:
                with st.spinner("식약처 기준(법 제24조) 대조 중..."):
                    regulations = """
                    당신은 대한민국 식약처(MFDS) 의료기기 광고 심의관입니다.
                    3,4등급 의료기기 광고 문구를 엄격하게 검수하세요.
                    
                    [체크리스트]
                    1. 금지 단어: 최고, 최상, 유일, 기적, 100%, 완치, 부작용 없음.
                    2. 필수 포함: 심의번호 기재란, 부작용 및 주의사항 문구.
                    3. 오인 금지: 의사/약사 추천, 체험담, 공산품으로 오인될 소지.
                    
                    결과는 [판정 / 위반사항 / 수정제안] 형식으로 명확히 출력하세요.
                    """
                    try:
                        response = client.chat.completions.create(
                            model="gpt-4o",
                            messages=[
                                {"role": "system", "content": regulations},
                                {"role": "user", "content": ad_text}
                            ],
                            temperature=0.1
                        )
                        st.success("분석 완료")
                        st.markdown(response.choices[0].message.content)
                    except Exception as e:
                        st.error(f"오류 발생: {e}")

# ==========================================
# 2. 이미지 분석 및 자동 보완 (여기가 고친 부분입니다!)
# ==========================================
def encode_image(image_file):
    return base64.b64encode(image_file.getvalue()).decode('utf-8')

with tab2:
    st.subheader("이미지 규정 위반 분석 및 대체안 생성")
    st.info("💡 개구기, 수술 장면, 피, 과도한 비포/애프터 등 문제가 될만한 이미지를 올려주세요.")
    
    uploaded_file = st.file_uploader("이미지 업로드", type=["jpg", "png", "jpeg"])

    if uploaded_file is not None:
        col_img1, col_img2 = st.columns(2)
        
        with col_img1:
            st.image(uploaded_file, caption='업로드한 원본', use_container_width=True)
            analyze_btn = st.button("이미지 정밀 분석 시작", type="primary")

        if analyze_btn:
            with st.spinner("AI가 이미지를 시각적으로 분석 중입니다..."):
                try:
                    base64_image = encode_image(uploaded_file)
                    
                    # 1단계: 이미지 분석 요청
                    # [정밀도를 높인 새로운 프롬프트]
                    vision_prompt = """
                    당신은 대한민국 식약처(MFDS)의 숙련된 의료기기 심의관입니다.
                    아래 이미지를 단계별로 정밀 분석하여 법령 위반 여부를 판단하세요.

                    [분석 단계 - 반드시 이 순서대로 생각할 것]
                    1. **시각적 요소 나열**: 이미지에 등장하는 모든 요소(사람, 표정, 도구, 텍스트, 신체 부위 등)를 있는 그대로 묘사하세요.
                    2. **위험 요소 탐지**: 특히 '개구기(입 벌리는 도구)', '주사기', '피(혈흔)', '절개된 환부', '수술 장면', '과도한 CG(빛이 나가는 효과)'가 있는지 확인하세요.
                    3. **규정 대조**: 의료기기법 시행규칙 별표7(혐오감 조성, 과대광고)에 해당하는지 대조하세요.
                    4. **최종 판정**: 위 분석을 토대로 승인/반려를 결정하세요.

                    [출력 형식]
                    1. **상세 묘사**: (AI가 본 것을 나열)
                    2. **심의 판정**: [승인 / 반려 / 주의]
                    3. **위반 사유**: (구체적으로 어떤 물체가 문제가 되는지 지적)
                    4. **수정 가이드**: (구체적인 개선 방향)
                    ---
                    PROMPT: (여기에 구글 이마젠 스타일의 실사 대체 이미지 프롬프트 작성)
                    """
