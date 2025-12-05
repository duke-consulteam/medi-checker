import streamlit as st
import openai
import base64
import pandas as pd
from datetime import datetime
from PIL import Image
import json

# 구글 라이브러리
try:
    from google.oauth2 import service_account
    import vertexai
    from vertexai.preview.vision_models import ImageGenerationModel, Image as VertexImage
except ImportError:
    pass

st.set_page_config(page_title="Medi-Check Pro", page_icon="🏥", layout="wide")

# --------------------------------------------------------
# 0. 구글 연결 설정
# --------------------------------------------------------
google_ready = False
imagen_model = None

if "gcp" in st.secrets:
    try:
        service_account_info = dict(st.secrets["gcp"])
        if "private_key" in service_account_info:
            service_account_info["private_key"] = service_account_info["private_key"].replace("\\n", "\n")
        if "token_uri" not in service_account_info:
            service_account_info["token_uri"] = "https://oauth2.googleapis.com/token"
        if "type" not in service_account_info:
            service_account_info["type"] = "service_account"

        credentials = service_account.Credentials.from_service_account_info(service_account_info)
        project_id = service_account_info["project_id"]
        vertexai.init(project=project_id, location="us-central1", credentials=credentials)
        
        try:
            imagen_model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-001")
        except:
            imagen_model = ImageGenerationModel.from_pretrained("imagegeneration@006")
            
        google_ready = True
    except Exception:
        pass

# --------------------------------------------------------
# 1. 공통 기능
# --------------------------------------------------------
if 'history' not in st.session_state:
    st.session_state['history'] = []

def save_log(type, input_summary, result):
    st.session_state['history'].append({
        "날짜": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "유형": type,
        "입력내용": input_summary,
        "판정결과": "완료",
        "상세결과": result
    })

api_key = st.secrets.get("OPENAI_API_KEY")
client = openai.OpenAI(api_key=api_key)

# --------------------------------------------------------
# 2. 사이드바
# --------------------------------------------------------
with st.sidebar:
    st.title("🏥 Medi-Check Pro")
    st.caption("Google Vertex AI (Edit Only)")
    st.divider()
    menu = st.radio("메뉴 선택", ["✨ 검수 및 보정", "📊 기록 대시보드"])
    st.divider()
    if google_ready:
        st.success("✅ 구글 엔진 연결됨")
    else:
        st.error("⚠️ 구글 키 설정 필요")

# --------------------------------------------------------
# [메뉴 A] 검수 및 보정
# --------------------------------------------------------
if menu == "✨ 검수 및 보정":
    st.header("✨ 의료기기 광고 심의 & 자동 보정")
    
    tab1, tab2 = st.tabs(["📄 텍스트 심의", "🖼️ 이미지 보정 (원본 수정)"])

    # 1. 텍스트
    with tab1:
        ad_text = st.text_area("문구 입력", height=150)
        if st.button("텍스트 검수"):
            resp = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role":"system", "content":"의료기기 심의관. 대체 문구 3개 제안."}, {"role":"user", "content":ad_text}]
            )
            res = resp.choices[0].message.content
            st.markdown(res)
            save_log("텍스트", ad_text[:20], res)

    # 2. 이미지
    def encode_image(image_file):
        image_file.seek(0) 
        return base64.b64encode(image_file.read()).decode('utf-8')

    with tab2:
        st.info("💡 **원본 유지 모드**: 이미지를 새로 그리지 않고, 원본 위에 수정 사항만 반영합니다.")
        uploaded_file = st.file_uploader("이미지 업로드", type=["jpg", "png"])

        if uploaded_file:
            col1, col2 = st.columns(2)
            with col1:
                uploaded_file.seek(0)
                st.image(uploaded_file, caption="원본", use_container_width=True)
            
            if st.button("AI 자동 분석 및 보정", type="primary"):
                if not google_ready:
                    st.error("구글 키 설정이 안 되어 있습니다.")
                else:
                    with st.spinner("1. 이미지 분석 중..."):
                        b64_img = encode_image(uploaded_file)
                        
                        prompt = """
                        이 이미지에서 의료기기법 위반 요소(주사기, 크림 바르는 손, 피 등)를 찾으세요.
                        그리고 구글 Imagen 3가 **원본을 수정할 때 사용할 프롬프트**를 작성하세요.
                        
                        [작성 요령]
                        1. **Target Description**: 수정이 완료된 후의 이미지를 묘사하세요.
                        2. **원본 유지**: 인물의 외모(눈, 코, 입, 머리스타일)는 원본과 똑같이 묘사해야 합니다.
                        3. **제거 대상**: 손(Hand), 장갑(Glove), 도구(Tool), 크림(Cream), 주사기(Syringe)는 묘사에서 빼고 **'Clean skin'**으로 대체하세요.
                        
                        형식:
                        PROMPT: (수정 후의 전체 이미지 묘사)
                        """
                        
                        resp = client.chat.completions.create(
                            model="gpt-4o",
                            messages=[{"role":"user", "content":[{"type":"text","text":prompt}, {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64_img}"}}]}]
                        )
                        res_text = resp.choices[0].message.content
                        
                        # 프롬프트 추출
                        edit_prompt = "Close up portrait of a woman with clean skin, professional photography."
                        try:
                            if "PROMPT:" in res_text:
                                edit_prompt = res_text.split("PROMPT:")[1].strip()
                        except:
                            pass
                        
                        # 안전 세탁
                        remove_words = ["blood", "syringe", "needle", "glove", "hand", "cream", "brush", "tool", "wound"]
                        for word in remove_words:
                            edit_prompt = edit_prompt.lower().replace(word, "")
                        
                        final_prompt = f"{edit_prompt}, exact same face, highly detailed, 8k, photorealistic"

                        with col1:
                            st.caption("✅ 분석 완료")
                            with st.expander("보정 명령어 보기"):
                                st.write(final_prompt)
                            save_log("이미지", uploaded_file.name, res_text)

                    with col2:
                        with st.spinner("2. 구글 엔진이 수정 중... (새로 그리기 X)"):
                            try:
                                uploaded_file.seek(0)
                                image_bytes = uploaded_file.read()
                                base_img = VertexImage(image_bytes)
                                
                                # 수정 요청
                                response = imagen_model.edit_image(
                                    base_image=base_img,
                                    prompt=final_prompt,
                                    number_of_images=1,
                                    guidance_scale=60,
                                )
                                
                                # ★★★ 에러 수정 완료 ★★★
                                # len(response) 대신 response.images를 확인
                                if response.images:
                                    st.image(response.images[0]._image_bytes, caption="AI 수정본 (Edit)", use_container_width=True)
                                    st.success("원본 위에서 수정했습니다.")
                                else:
                                    st.error("구글이 이미지를 반환하지 않았습니다.")

                            except Exception as e:
                                st.error("❌ 수정 실패")
                                st.error(f"구글 에러 메시지: {e}")
                                st.warning("TIP: '새로 그리기'로 전환되지 않고 종료되었습니다.")

# --------------------------------------------------------
# [메뉴 B] 대시보드
# --------------------------------------------------------
elif menu == "📊 기록 대시보드":
    st.header("📊 이력 관리")
    df = pd.DataFrame(st.session_state['history'])
    if not df.empty:
        st.dataframe(df, use_container_width=True)
    else:
        st.info("기록 없음")
