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
                    vision_prompt = """
                    당신은 의료기기 광고 심의관입니다. 이 이미지가 '의료기기 광고 심의 규정'에 위배되는지 판단하세요.
                    특히 혐오감(개구기, 피, 장기), 과대광고(CG 효과), 비포애프터 비교 여부를 봅니다.
                    
                    만약 위반 사항이 있다면, 이를 대체할 수 있는 '안전하고 세련된 광고용 이미지'를 그리기 위한 
                    영어 프롬프트(DALL-E 3용)를 마지막에 작성해주세요.
                    
                    출력 형식:
                    1. **심의 판정**: [승인 / 반려]
                    2. **위반 이유**: (상세 설명)
                    3. **수정 가이드**: (어떻게 바꿔야 하는지 한글 설명)
                    ---
                    PROMPT: (여기에 DALL-E 3에게 줄 영문 프롬프트 작성.)
                    """

                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": vision_prompt},
                                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                                ],
                            }
                        ],
                    )
                    
                    result_text = response.choices[0].message.content
                    
                    # ========================================================
                    # ★ 여기가 바로 선생님이 원하시던 '이마젠 스타일' 적용 부분입니다!
                    # ========================================================
                    base_prompt = "A hyper-realistic 8k photography of a medical device marketing image. Canon EOS R5 style, minimal, bright clinical lighting, clear focus, professional Korean model looking trustworthy and smiling naturally. No text overlays."

                    if "PROMPT:" in result_text:
                        extracted = result_text.split("PROMPT:")[1].strip()
                        dalle_prompt = f"{extracted}, {base_prompt}"
                    else:
                        dalle_prompt = base_prompt
                    # ========================================================

                    with col_img1:
                        st.markdown("### 📋 분석 결과")
                        st.markdown(result_text.split("PROMPT:")[0]) # PROMPT 뒷부분은 숨김

                    # 2단계: 이미지 생성
                    with col_img2:
                        st.markdown("### ✨ AI 추천 대체 이미지 (고화질)")
                        if "반려" in result_text or "주의" in result_text or "위반" in result_text:
                            st.write("규정에 맞는 안전한 이미지를 생성 중입니다...")
                            
                            with st.spinner("최고 화질로 렌더링 중... (약 15초)"):
                                img_response = client.images.generate(
                                    model="dall-e-3",
                                    prompt=dalle_prompt,
                                    size="1024x1024",
                                    quality="hd", # 고화질 옵션
                                    style="natural",
                                    n=1,
                                )
                                image_url = img_response.data[0].url
                                st.image(image_url, caption="Safe & High Quality Image", use_container_width=True)
                                st.success("저작권 걱정 없는 광고용 이미지입니다.")
                        else:
                            st.success("이 이미지는 규정에 위배되지 않는 것으로 보입니다. (생성 생략)")

                except Exception as e:
                    st.error(f"오류가 발생했습니다: {e}")
