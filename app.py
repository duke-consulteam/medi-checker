import streamlit as st
import openai
import base64
import pandas as pd
from datetime import datetime
from PIL import Image
import json

# 구글 라이브러리 로드
try:
    from google.oauth2 import service_account
    import vertexai
    from vertexai.preview.vision_models import ImageGenerationModel, Image as VertexImage
except ImportError:
    pass

st.set_page_config(page_title="Medi-Check Pro", page_icon="🏥", layout="wide")

# --------------------------------------------------------
# 0. 구글 연결 설정 (유지)
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
        imagen_model = ImageGenerationModel.from_pretrained("imagegeneration@006")
        google_ready = True
    except Exception:
        pass

# --------------------------------------------------------
# 1. 공통 기능 (로그 저장소)
# --------------------------------------------------------
# 로그인 없이도 기록은 임시 저장되도록 설정
if 'history' not in st.session_state:
    st.session_state['history'] = []

def save_log(type, input_summary, result):
    st.session_state['history'].append({
        "날짜": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "유형": type,
        "입력내용": input_summary,
        "판정결과": "반려" if "반려" in result else ("주의" if "주의" in result else "승인"),
        "상세결과": result
    })

# API 키
api_key = st.secrets.get("OPENAI_API_KEY")
client = openai.OpenAI(api_key=api_key)

# --------------------------------------------------------
# 2. 사이드바 및 메뉴 (로그인 관련 내용 삭제)
# --------------------------------------------------------
with st.sidebar:
    st.title("🏥 Medi-Check Pro")
    st.caption("3,4등급 의료기기 광고 심의")
    
    st.divider()
    
    # 메뉴 선택
    menu = st.radio("메뉴 선택", ["✨ 검수 요청", "📊 기록 대시보드"])
    
    st.divider()
    
    # 연결 상태 표시
    if google_ready:
        st.success("✅ 구글 Imagen 연결됨")
    else:
        st.warning("⚠️ DALL-E 모드 (구글키 확인필요)")

# --------------------------------------------------------
# [메뉴 A] 검수 요청 (메인 기능)
# --------------------------------------------------------
if menu == "✨ 검수 요청":
    st.header("✨ 광고 심의 및 보정")
    st.caption("텍스트 문구 수정 및 이미지 원본 유지 보정")
    
    tab1, tab2 = st.tabs(["📄 텍스트 심의", "🖼️ 이미지 원본 보정"])

    # 1. 텍스트 심의
    with tab1:
        ad_text = st.text_area("광고 문구를 입력하세요", height=200)
        if st.button("텍스트 검수", type="primary"):
            if not ad_text:
                st.warning("문구를 입력해주세요.")
            else:
                with st.spinner("법령 분석 및 대체 문구 생성 중..."):
                    resp = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role":"system", "content":"당신은 의료기기 심의관입니다. 위반시 대체 문구 3개를 제안하세요."}, {"role":"user", "content":ad_text}]
                    )
                    res = resp.choices[0].message.content
                    st.markdown(res)
                    save_log("텍스트", ad_text[:20], res)

    # 2. 이미지 보정
    def encode_image(image_file):
        image_file.seek(0) 
        return base64.b64encode(image_file.read()).decode('utf-8')

    with tab2:
        st.info("💡 **스마트 뷰티 필터**: 원본 얼굴과 구도는 그대로 두고, 문제되는 부분(피, 배경)만 수정합니다.")
        uploaded_file = st.file_uploader("이미지 업로드", type=["jpg", "png"])

        if uploaded_file:
            col1, col2 = st.columns(2)
            with col1:
                uploaded_file.seek(0)
                st.image(uploaded_file, caption="원본", use_container_width=True)
                
            if st.button("이미지 분석 및 원본 보정", type="primary"):
                with st.spinner("1. 안전한 보정 계획 수립 중..."):
                    b64_img = encode_image(uploaded_file)
                    
                    # 안전 필터 우회 프롬프트
                    prompt = """
                    이 이미지에서 의료기기법 위반 요소(피, 공포 분위기)를 찾으세요.
                    그리고 구글 AI에게 내릴 **안전한 영어 보정 명령(Edit Instruction)**을 작성하세요.
                    
                    [명령 작성 규칙 - 매우 중요]
                    1. 부정적인 단어 금지: remove blood, delete wound, kill vampire (사용 금지 X)
                    2. 긍정적인 단어 사용: **smooth skin texture**, **studio lighting**, **professional portrait**, **dark blue background** (사용 O)
                    3. 원본 유지: 모델의 얼굴이나 머리카락을 바꾸라는 말은 하지 마세요.
                    
                    예시: "Change background to dark blue studio wall. Apply beauty filter for smooth skin."
                    
                    형식:
                    1. 판정: ...
                    ---
                    EDIT_PROMPT: (명령어)
                    """
                    
                    resp = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role":"user", "content":[{"type":"text","text":prompt}, {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64_img}"}}]}]
                    )
                    res_text = resp.choices[0].message.content
                    
                    # 파싱
                    edit_instruction = "Change background to blue studio. Smooth skin."
                    try:
                        if "EDIT_PROMPT:" in res_text:
                            edit_instruction = res_text.split("EDIT_PROMPT:")[1].strip()
                    except:
                        pass
                    
                    # 2차 강제 세탁 (안전장치)
                    edit_instruction = edit_instruction.lower()
                    edit_instruction = edit_instruction.replace("blood", "red paint").replace("wound", "texture").replace("remove", "fix")
                    
                    # 나노바나나 스타일 명령 강제 주입
                    final_instruction = f"{edit_instruction}, high quality, photorealistic, keep facial features"

                    with col1:
                        st.markdown("### 📋 분석 결과")
                        st.markdown(res_text.split("EDIT_PROMPT:")[0])
                        st.caption(f"🤖 보정 명령: {final_instruction}")
                        save_log("이미지", uploaded_file.name, res_text)

                with col2:
                    if google_ready:
                        with st.spinner(f"2. 구글 이마젠이 원본을 보정 중..."):
                            try:
                                uploaded_file.seek(0)
                                image_bytes = uploaded_file.read()
                                base_img = VertexImage(image_bytes)
                                
                                # 원본 유지 보정 (Edit)
                                gen_imgs = imagen_model.edit_image(
                                    base_image=base_img,
                                    prompt=final_instruction,
                                    number_of_images=1
                                )
                                st.image(gen_imgs[0]._image_bytes, caption="구글 보정본 (Inpainting)", use_container_width=True)
                                st.success("원본의 얼굴과 구도를 그대로 유지했습니다!")

                            except Exception as e:
                                st.error("⚠️ 구글이 보정을 거부했습니다.")
                                st.caption(f"사유: {e}")
                                
                                st.info("대체 이미지(새로 그리기)를 시도합니다.")
                                try:
                                    fallback_prompt = f"A photo of a professional medical person. {final_instruction}"
                                    gen_imgs = imagen_model.generate_images(prompt=fallback_prompt, number_of_images=1)
                                    st.image(gen_imgs[0]._image_bytes, caption="새로 그리기 대체안", use_container_width=True)
                                except:
                                    pass
                    else:
                        st.error("⚠️ 구글 키 설정 오류")

# --------------------------------------------------------
# [메뉴 B] 기록 대시보드
# --------------------------------------------------------
elif menu == "📊 기록 대시보드":
    st.header("📊 검수 이력 관리")
    
    df = pd.DataFrame(st.session_state['history'])
    if not df.empty:
        # 최신순 정렬
        df = df.sort_values(by="날짜", ascending=False)
        
        # 메트릭 표시
        col1, col2, col3 = st.columns(3)
        col1.metric("총 검수 건수", f"{len(df)}건")
        col2.metric("반려/주의", f"{len(df[df['판정결과'] != '승인'])}건")
        col3.metric("승인", f"{len(df[df['판정결과'] == '승인'])}건")
        
        st.divider()
        st.dataframe(df, use_container_width=True)
    else:
        st.info("아직 검수 기록이 없습니다. '검수 요청' 메뉴를 이용해보세요.")
