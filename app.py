import streamlit as st
import openai
import base64
import streamlit_authenticator as stauth
import pandas as pd
from datetime import datetime
from PIL import Image

# --------------------------------------------------------
# ★ 비밀번호 암호화 및 설정
# --------------------------------------------------------
try:
    from streamlit_authenticator.utilities.hasher import Hasher
except ImportError:
    from streamlit_authenticator import Hasher

st.set_page_config(page_title="Medi-Check Pro", page_icon="🏥", layout="wide")

# 데이터 저장소
if 'history' not in st.session_state:
    st.session_state['history'] = []

def save_log(username, type, input_summary, result):
    st.session_state['history'].append({
        "날짜": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "사용자": username,
        "유형": type,
        "입력내용": input_summary,
        "판정결과": "반려" if "반려" in result else ("주의" if "주의" in result else "승인"),
        "상세결과": result
    })

# ==========================================
# 0. 로그인 시스템
# ==========================================
passwords_to_hash = ['123']
hashed_passwords = Hasher(passwords_to_hash).generate()

user_data = {
    'credentials': {
        'usernames': {
            'admin': {
                'name': '김대표',
                'password': hashed_passwords[0],
                'email': 'admin@consul.team',
            }
        }
    },
    'cookie': {'expiry_days': 0, 'key': 'secret_key', 'name': 'medi_cookie'},
    'preauthorized': {'emails': []}
}

authenticator = stauth.Authenticate(
    user_data['credentials'],
    user_data['cookie']['name'],
    user_data['cookie']['key'],
    user_data['cookie']['expiry_days'],
    user_data['preauthorized']
)

authenticator.login()

if st.session_state["authentication_status"] is False:
    st.error('아이디 또는 비밀번호가 틀렸습니다.')
    st.stop()
elif st.session_state["authentication_status"] is None:
    st.stop()

# ==========================================
# 1. 메인 화면
# ==========================================
user_name = st.session_state['name']
user_id = st.session_state['username']

with st.sidebar:
    st.title(f"👤 {user_name}님")
    menu = st.radio("메뉴 선택", ["📊 나의 대시보드", "✨ 새로운 검수 요청"])
    st.divider()
    authenticator.logout('로그아웃', 'sidebar')

api_key = st.secrets.get("OPENAI_API_KEY")
if not api_key:
    st.error("API 키 설정을 확인해주세요.")
    st.stop()
client = openai.OpenAI(api_key=api_key)

# ------------------------------------------------
# [메뉴 A] 대시보드
# ------------------------------------------------
if menu == "📊 나의 대시보드":
    st.title("📊 캠페인 관리 대시보드")
    df = pd.DataFrame(st.session_state['history'])
    if not df.empty:
        my_df = df[df['사용자'] == user_id]
        if not my_df.empty:
            col1, col2, col3 = st.columns(3)
            col1.metric("총 검수", f"{len(my_df)}건")
            col2.metric("반려/주의", f"{len(my_df[my_df['판정결과'] != '승인'])}건")
            col3.metric("오늘 날짜", datetime.now().strftime("%Y-%m-%d"))
            
            st.dataframe(my_df[["날짜", "유형", "판정결과", "입력내용"]], use_container_width=True)
            
            csv = my_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 엑셀 다운로드", csv, "history.csv", "text/csv")
        else:
            st.info("검수 기록이 없습니다.")
    else:
        st.info("검수 기록이 없습니다.")

# ------------------------------------------------
# [메뉴 B] 새로운 검수 요청
# ------------------------------------------------
elif menu == "✨ 새로운 검수 요청":
    st.title("✨ 새로운 광고 심의 요청")
    
    tab1, tab2 = st.tabs(["📄 텍스트 심의 (수정안 제안)", "🖼️ 이미지 보정 (원본 살리기)"])

    # --- 1. 텍스트 심의 & 수정안 제안 ---
    with tab1:
        col1, col2 = st.columns(2)
        with col1:
            ad_text = st.text_area("광고 문구를 입력하세요:", height=300, placeholder="예: 빨딱빨딱 80세까지 세워줘요")
        with col2:
            if st.button("텍스트 검수 및 수정안 받기", type="primary"):
                if not ad_text:
                    st.warning("문구를 입력하세요.")
                else:
                    with st.spinner("법령 분석 및 대체 문구 작성 중..."):
                        try:
                            # 프롬프트 업그레이드: 구체적인 수정안 요구
                            system_prompt = """
                            당신은 마케팅 감각이 뛰어난 의료기기 심의관입니다.
                            사용자의 문구가 의료기기법(과대광고, 절대적 표현)을 위반하는지 판단하고,
                            위반 시 **법을 지키면서도 소비자를 끌어당길 수 있는 매력적인 대체 문구**를 3가지 제안하세요.

                            [출력 형식]
                            1. **판정**: [승인 / 반려]
                            2. **위반 사유**: (법적 근거 설명)
                            3. **📝 추천 수정안 (3가지)**:
                               - 옵션 A: (안전하고 신뢰감 있는 톤)
                               - 옵션 B: (효능을 은유적으로 표현한 톤)
                               - 옵션 C: (팩트 중심의 톤)
                            """
                            response = client.chat.completions.create(
                                model="gpt-4o",
                                messages=[
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": ad_text}
                                ]
                            )
                            result = response.choices[0].message.content
                            st.success("분석 및 제안 완료")
                            st.markdown(result)
                            save_log(user_id, "텍스트", ad_text[:20], result)
                            
                        except Exception as e:
                            st.error(f"오류: {e}")

    # --- 2. 이미지 보정 (원본 유지 + 문제 제거) ---
    def encode_image(image_file):
        return base64.b64encode(image_file.getvalue()).decode('utf-8')

    with tab2:
        st.info("💡 뱀파이어 사진처럼 '피'나 '공포 분위기'가 있다면, **구도는 유지하되 문제점만 수정한** 이미지를 생성합니다.")
        uploaded_file = st.file_uploader("이미지 업로드", type=["jpg", "png", "jpeg"])

        if uploaded_file:
            col_img1, col_img2 = st.columns(2)
            with col_img1:
                st.image(uploaded_file, caption='업로드 원본', use_container_width=True)
                analyze_btn = st.button("이미지 분석 및 보정 시작", type="primary")

            if analyze_btn:
                with st.spinner("원본의 구도를 분석하고 문제점(피, 배경)을 제거 중입니다..."):
                    try:
                        base64_image = encode_image(uploaded_file)
                        
                        # ★ 핵심 프롬프트: 원본 보존 + 문제 해결 ★
                        vision_prompt = """
                        당신은 이미지 보정 전문가이자 의료기기 심의관입니다.
                        
                        [1단계: 분석]
                        이미지의 위반 요소(피, 개구기, 공포 분위기 등)를 찾으세요.

                        [2단계: 보정 프롬프트 작성 (중요)]
                        이 이미지를 DALL-E 3로 '다시 그리기(Recreation)' 위한 영어 프롬프트를 작성하세요.
                        단, **원본의 구도, 모델의 외모(인종, 머리스타일), 포즈, 옷차림은 최대한 똑같이 유지**해야 합니다.
                        
                        **반드시 수정해야 할 점:**
                        1. 피(Blood), 상처가 있다면 -> **깨끗한 피부(Clean skin)**로 변경.
                        2. 배경이 어둡거나 붉은 톤(공포)이라면 -> **밝고 전문적인 의료/병원 톤(Bright clinical blue/white background)**으로 변경.
                        3. 모델의 표정이 고통스럽거나 무섭다면 -> **신뢰감을 주는 편안한 미소**로 변경.

                        출력 형식:
                        1. **심의 판정**: [반려 / 승인]
                        2. **수정된 점**: (무엇을 지우고 배경을 어떻게 바꿨는지 설명)
                        ---
                        PROMPT: (DALL-E 3용 영어 프롬프트. 'Same pose, same composition, same model description...' 로 시작할 것)
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
                        
                        # 결과 파싱
                        if "PROMPT:" in result_text:
                            analysis_part = result_text.split("PROMPT:")[0]
                            extracted_prompt = result_text.split("PROMPT:")[1].strip()
                            # 퀄리티 업을 위한 마법의 주문 추가
                            dalle_prompt = f"{extracted_prompt}, hyper-realistic 8k photography, Canon EOS R5 quality"
                        else:
                            analysis_part = result_text
                            dalle_prompt = "A clean professional medical image, high quality."

                        save_log(user_id, "이미지", uploaded_file.name, analysis_part)

                        with col_img1:
                            st.markdown("### 📋 분석 및 보정 계획")
                            st.markdown(analysis_part)

                        with col_img2:
                            st.markdown("### ✨ 보정된 이미지 (Recreated)")
                            if "반려" in result_text or "주의" in result_text:
                                with st.spinner("수정된 컨셉으로 고화질 렌더링 중... (15초)"):
                                    img_response = client.images.generate(
                                        model="dall-e-3", 
                                        prompt=dalle_prompt, 
                                        size="1024x1024", 
                                        quality="hd", 
                                        style="natural", 
                                        n=1
                                    )
                                    st.image(img_response.data[0].url, caption="보정 완료된 이미지 (구도 유지 + 문제 제거)")
                                    st.success("피/공포 요소를 제거하고 배경 톤을 변경했습니다.")
                            else:
                                st.success("수정이 필요 없는 안전한 이미지입니다.")

                    except Exception as e:
                        st.error(f"오류: {e}")
