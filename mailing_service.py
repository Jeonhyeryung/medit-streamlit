import streamlit as st
import requests
from datetime import datetime
import mysql.connector
from mysql.connector import Error
from config import DB_CONFIG, AI_CONFIG
import deepl
from mysql_connector_pool import MysqlConnectorPool
from api_url import get_crawler_url

mysql = MysqlConnectorPool()

def fetch_keyword_alarmed(member_no):
    query = f"SELECT * FROM tb_search_keyword WHERE alarm_yn = 'Y' AND member_no = '{member_no}'"
    return mysql.read(query=query)

def send_message_to_queue(search_keyword, crawling_option, website, member_no):
    url = get_crawler_url(search_keyword, crawling_option, website, member_no)
    response = requests.get(url, timeout=10)  # Set a timeout of 10 seconds
    return response

def translate(text: str):
    try:
        translator = deepl.Translator(AI_CONFIG["deepl"]["api_key"])
        translated = translator.translate_text(text, target_lang="KO").text
        return translated
    except Exception as e:
        st.error(f"Translation error: {e}")
        return text
    
def save_translation_to_db(pmid, translated_abstract):
    query = "UPDATE tb_crawl_data SET crawl_data_abstract_ko = %s WHERE crawl_data_pmid = %s"
    params = (translated_abstract, pmid)
    mysql.write(query=query, params=params)

def display_mailing_service():
    st.header("📧 메일링 서비스")

    st.write(
        f"""
        
        아래 설명을 참고하여 키워드를 입력해주시고,
        입력한 키워드와 관련된 논문들을 메일로 받아보세요.

        **현재 사용자: {st.session_state.name}**
        """
    )

    # Initialize session state variables
    if "search_keyword" not in st.session_state:
        st.session_state["search_keyword"] = ""
    if "crawling_option" not in st.session_state:
        st.session_state["crawling_option"] = ""
    if "crawl_date" not in st.session_state:
        st.session_state["crawl_date"] = None
    if "crawl_hour" not in st.session_state:
        st.session_state["crawl_hour"] = datetime.now().hour
    if "crawl_minute" not in st.session_state:
        st.session_state["crawl_minute"] = datetime.now().minute
    if "page" not in st.session_state:
        st.session_state["page"] = 1
    if "start_page" not in st.session_state:
        st.session_state["start_page"] = 1
    if "translation_states" not in st.session_state:
        st.session_state["translation_states"] = {}
    if "translated_abstracts" not in st.session_state:
        st.session_state["translated_abstracts"] = {}

    # User input fields
    sk, cp = st.columns([3, 1])
    with sk:
        search_keyword = st.text_input("Enter search keyword", st.session_state["search_keyword"])
    with cp:
        crawling_option = st.selectbox("Select Option", ("Best Match", "Most Recent"))
        st.session_state["crawling_option"] = crawling_option

    # Default values for API call
    website = "pubmed"
    member_no = st.session_state.member_no

    # Send message button
    with st.container():
        if st.button("Start Crawling 🚀", use_container_width=True, key="start_crawling"):
            if search_keyword is not None:
                with st.spinner('Sending message to queue...'):
                    try:
                        response = send_message_to_queue(search_keyword, st.session_state["crawling_option"], website, member_no)
                        if response and response.status_code == 200:
                            st.success("Message sent successfully!")
                        else:
                            st.error(f"Failed to send message. Status code: {response.status_code}, Message: {response.text}")
                    except requests.exceptions.RequestException as e:
                        st.error(f"Failed to send message. Error: {str(e)}")

def set_mailing_scheduler():
    # st.markdown("<h3>알림 만들기</h3>", unsafe_allow_html=True)
    alarm_keyword = st.text_input(label="다음 키워드에 대한 알림 만들기")
    member_no = st.session_state.member_no
    alarmed_keywords = fetch_keyword_alarmed(member_no)
    st.markdown(f"""*알림이 설정된 키워드*&nbsp;⬇️""")
    for idx, keyword in enumerate(alarmed_keywords):
        with st.container():
            keyword_col, button_col = st.columns([3, 1])
            with keyword_col:
                st.markdown(f"""#### KEYWORD: {keyword['search_keyword']}""")
            with button_col:
                disable_button = st.button(label="Disable", key=f"disable_{idx}", use_container_width=True)
        if disable_button:
            query = f"""
                UPDATE tb_search_keyword 
                SET alarm_yn = 'N' 
                WHERE search_keyword='{keyword["search_keyword"]}' AND member_no='{member_no}' 
            """
            mysql.write(query=query)

    set_alarm_button = st.button("알림 설정 완료 📩", use_container_width=True, key="set_alarm_button")
    if set_alarm_button:
        # 중복 확인 쿼리
        check_query = f"""
            SELECT COUNT(*) as count FROM tb_search_keyword 
            WHERE search_keyword = '{alarm_keyword}' AND member_no = '{member_no}'
        """
        result = mysql.read(check_query)
        if result[0]['count'] == 0:
            # 중복이 아닐 때만 삽입
            query = f"""
                INSERT INTO tb_search_keyword (search_keyword_no, search_keyword, alarm_yn, member_no, insert_date)
                VALUES ('{mysql.generate_no()}', '{alarm_keyword}', 'Y', '{member_no}', NOW())
            """
            mysql.write(query)
            st.success("알림이 설정되었습니다!")
        else:
            # 중복일 때는 alarm_yn을 'Y'로 업데이트
            update_query = f"""
                UPDATE tb_search_keyword 
                SET alarm_yn = 'Y' 
                WHERE search_keyword = '{alarm_keyword}' AND member_no = '{member_no}'
            """
            mysql.write(update_query)
            st.success("기존 키워드에 대한 알림이 활성화되었습니다!")
        st.rerun()



