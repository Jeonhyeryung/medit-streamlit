import streamlit as st
import bcrypt
from config import DB_CONFIG 
import mysql.connector
from mysql.connector import Error
from mailing_service import display_mailing_service, set_mailing_scheduler
from ai_service import ai_service
from search_service import search_service
from scrap_service import scrap_service

def fetch_user_credentials():
    try:
        connection = mysql.connector.connect(
            host=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
            autocommit=DB_CONFIG["autocommit"]
        )
        cursor = connection.cursor(dictionary=True)
        query = "SELECT member_no, member_email, member_name, password FROM tb_member"
        cursor.execute(query)
        records = cursor.fetchall()
        return records
    except Error as e:
        print(f"Error fetching data: {e}")
        return []
    finally:
        cursor.close()
        connection.close()

user_records = fetch_user_credentials()

for record in user_records:
    if not record['password'].startswith('$2b$'):
        record['password'] = bcrypt.hashpw(record['password'].encode(), bcrypt.gensalt()).decode()

USERNAMES = [record['member_email'] for record in user_records]
NAMES = [record['member_name'] for record in user_records]
HASHED_PASSWORDS = [record['password'] for record in user_records]
MEMBER_NOS = {record['member_email']: record['member_no'] for record in user_records}

CREDENTIALS = {username: {"name": name, "password": hashed_password, "member_no": MEMBER_NOS[username]} for username, name, hashed_password in zip(USERNAMES, NAMES, HASHED_PASSWORDS)}

if 'authentication_status' not in st.session_state:
    st.session_state.authentication_status = None
if 'name' not in st.session_state:
    st.session_state.name = None
if 'username' not in st.session_state:
    st.session_state.username = None
if 'member_no' not in st.session_state:
    st.session_state.member_no = None

def authenticate(username, password):
    user = CREDENTIALS.get(username)
    if user and bcrypt.checkpw(password.encode(), user['password'].encode()):
        return user['name'], user['member_no']
    return None, None

@st.experimental_dialog("알림 만들기")
def show_mailing_scheduler():
    set_mailing_scheduler()

# 쿼리 매개변수에서 세션 상태 가져오기
query_params = st.query_params
if query_params:
    st.session_state.authentication_status = query_params.get('authentication_status', [None])[0] == 'True'
    st.session_state.name = query_params.get('name', [None])[0]
    st.session_state.username = query_params.get('username', [None])[0]
    st.session_state.member_no = query_params.get('member_no', [None])[0]


if st.session_state.authentication_status:
    st.set_page_config(page_title="Medit Login", page_icon="🔒", layout="wide")
    # 로그인 후 CSS 스타일 적용
    st.markdown(
        """
        <style>
        div[class^='block-container'] {
            padding-top: 2rem; 
            padding-left: 0.5rem;
            padding-right: 0.5rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<h1 style='text-align: center; font-size: 48px;'>Medit</h1>", unsafe_allow_html=True)

     # 로그인 후 레이아웃 설정
    col1, col2, col3 = st.columns([1, 12, 1])

    with col2:
        tab1, tab2, tab3, tab4 = st.tabs(["논문 검색 기능", "논문 스크랩 기능", "AI 서비스", "메일링 서비스"])

        with tab1:
            search_service()

        with tab2:
            scrap_service()

        with tab3:
            ai_service()
            
        with tab4:
            display_mailing_service()

            if st.button("알림 만들기", key="alert_button"):
                show_mailing_scheduler()

else:
    st.set_page_config(page_title="Medit main", page_icon="🔒", layout="centered")
    st.markdown("<h1 style='text-align: center; font-size: 60px;'>Medit</h1>", unsafe_allow_html=True)

    # 로그인 전 레이아웃 설정
    col1, col2, col3 = st.columns([1, 4, 1])
    with col2:
        # 이메일 입력 필드
        email = st.text_input("이메일", "", key="email")
        
        # 비밀번호 입력 필드
        password = st.text_input("비밀번호", "", type="password", key="password")
        
        # 여백 추가
        st.markdown("""
            <style>
            .stButton button {
                background-color: black;
                color: white;
                width: 100%;
                margin-top: 20px; 
            </style>
            """, unsafe_allow_html=True)
        
        # 로그인 버튼
        login_button = st.button("로그인", use_container_width=True)

        if login_button:
            user_name, member_no = authenticate(email, password)
            if user_name:
                st.session_state.authentication_status = True
                st.session_state.name = user_name
                st.session_state.username = email
                st.session_state.member_no = member_no
                st.rerun()  # 로그인 후 페이지를 다시 로드
            else:
                st.session_state.authentication_status = False

        # 로그인 실패 시 오류 메시지 표시
        if st.session_state.authentication_status == False:
            st.error('Username or password is incorrect')
        elif st.session_state.authentication_status == None:
            st.warning('Please enter your username and password')
