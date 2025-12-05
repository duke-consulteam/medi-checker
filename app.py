import streamlit as st
import openai
import base64
import streamlit_authenticator as stauth
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

# 비밀번호 해시
try:
    from streamlit_authenticator.utilities.hasher import Hasher
except ImportError:
    from streamlit_authenticator import Hasher

st.set_page_config(page_title="Medi-Check Pro", page_icon="🏥", layout="wide")

# --------------------------------------------------------
# 0. 구글 연결 설정
# --------------------------------------------------------
google_ready = False
imagen_model = None
google_error_msg = ""

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
    except Exception as e:
        google_error_msg = str(e)
else:
    google_error_msg = "Secrets에 [gcp] 섹션이 없습니다."

# --------------------------------------------------------
# 1. 데이터 저장 및 로그인
# --------------------------------------------------------
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

passwords_to_hash = ['123']
hashed_passwords = Hasher(passwords_to_hash).generate()

user_data = {
    'credentials': {
        'usernames': {
            'admin': {'name': '김대표', 'password': hashed_passwords[0], 'email': 'admin@consul.team'}
        }
    },
    'cookie': {'expiry_days': 0, 'key': 'secret_key', 'name': 'medi_cookie_final'},
    'preauthorized': {'emails': []}
}

authenticator = stauth.Authenticate(
    user_data['credentials'], user_data['cookie']['name'], user_data['cookie']['key'], 0, []
)
authenticator.login()

if st.session_state["authentication_status"] is False:
    st.error('비번 틀림'); st.stop()
elif st.session_state["authentication_status"] is None:
    st.stop()

# ----------


