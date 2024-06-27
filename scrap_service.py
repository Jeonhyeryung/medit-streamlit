import streamlit as st
import mysql.connector
from mysql.connector import Error
from config import DB_CONFIG, AI_CONFIG
import deepl
from datetime import datetime
import random
import string

def create_connection():
    try:
        connection = mysql.connector.connect(
            host=DB_CONFIG["host"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
            autocommit=DB_CONFIG["autocommit"]
        )
        return connection
    except Error as e:
        st.error(f"Error connecting to MySQL database: {e}")
        return None

def translate(text: str):
    try:
        translator = deepl.Translator(AI_CONFIG["deepl"]["api_key"])
        translated = translator.translate_text(text, target_lang="KO").text
        return translated
    except Exception as e:
        st.error(f"Translation error: {e}")
        return text

def generate_no():
    now = datetime.now()
    formatted_data = now.strftime("%Y%m%d%H%M%S")
    secure_code = ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(6))
    number = formatted_data + secure_code
    return number

def save_translation_to_db(pmid, translated_abstract):
    connection = create_connection()
    if connection:
        try:
            cursor = connection.cursor()
            query = "UPDATE tb_crawl_data SET crawl_data_abstract_ko = %s WHERE crawl_data_pmid = %s"
            cursor.execute(query, (translated_abstract, pmid))
            connection.commit()
        except Error as e:
            st.error(f"Error saving translation to database: {e}")
        finally:
            cursor.close()
            connection.close()

def fetch_scraped_papers(member_no):
    connection = create_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            query = """
            SELECT DISTINCT
                md.document_title, 
                md.document_author, 
                md.document_abstract, 
                md.document_pmid,
                sk.search_keyword
            FROM 
                tb_member_document md
            JOIN 
                tb_user_favorite uf ON md.document_pmid = uf.document_pmid
            JOIN 
                tb_search_keyword sk ON md.search_keyword_no = sk.search_keyword_no
            WHERE 
                uf.member_no = %s
            ORDER BY 
                md.document_title
            """
            cursor.execute(query, (member_no,))
            records = cursor.fetchall()
            return records
        except Error as e:
            st.error(f"Error fetching data: {e}")
            return []
        finally:
            cursor.close()
            connection.close()
    else:
        return []

def fetch_keywords_from_scraped_papers(papers):
    return list(set([paper['search_keyword'] for paper in papers]))

def is_favorited(member_no, pmid):
    connection = create_connection()
    if connection:
        try:
            cursor = connection.cursor()
            query = "SELECT COUNT(*) FROM tb_user_favorite WHERE member_no = %s AND document_pmid = %s"
            cursor.execute(query, (member_no, pmid))
            result = cursor.fetchone()
            return result[0] > 0
        except Error as e:
            st.error(f"Error checking favorite: {e}")
            return False
        finally:
            cursor.close()
            connection.close()
    else:
        return False

def toggle_favorite(member_no, pmid):
    connection = create_connection()
    if connection:
        try:
            cursor = connection.cursor()
            if is_favorited(member_no, pmid):
                query = "DELETE FROM tb_user_favorite WHERE member_no = %s AND document_pmid = %s"
                cursor.execute(query, (member_no, pmid))
            else:
                user_favorite_no = generate_no()
                query = "INSERT INTO tb_user_favorite (user_favorite_no, member_no, document_pmid) VALUES (%s, %s, %s)"
                cursor.execute(query, (user_favorite_no, member_no, pmid))
            connection.commit()
        except Error as e:
            st.error(f"Error toggling favorite: {e}")
        finally:
            cursor.close()
            connection.close()

def display_paper(record, translation_state, translated_abstract=None):
    if translation_state and translated_abstract:
        title = translate(record['document_title'])
        abstract = translated_abstract
    else:
        title = record['document_title']
        abstract = record['document_abstract']

    pmid = record['document_pmid']
    member_no = st.session_state.member_no
    favorited = is_favorited(member_no, pmid)

    st.markdown(
        f"""
        <div style="border: 2px solid #5b5b5b; padding: 10px; border-radius: 10px; margin-bottom: 10px; position: relative;">
            <h3>{title}</h3>
            <p><strong>Author:</strong> {record['document_author']}</p>
            <p><strong>Abstract:</strong> {abstract}</p>
            <p><strong>Keyword:</strong> {record['search_keyword']}</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    col1, col2, col3 = st.columns([18.2, 1.8, 1])
    with col2:
        if st.button("Translate", key=f"translate_{pmid}_{record['document_title']}", help="Translate the abstract to Korean"):
            if not translation_state:
                translated_abstract = translate(record['document_abstract'])
                st.session_state["translated_abstracts"][pmid] = translated_abstract
                save_translation_to_db(pmid, translated_abstract)
            st.session_state["translation_states"][pmid] = not translation_state
            st.rerun()
    with col3:
        if st.button("💖" if favorited else "🤍", key=f"favorite_{pmid}_{record['document_title']}", help="Toggle favorite"):
            toggle_favorite(member_no, pmid)
            st.rerun()

def scrap_service():
    st.header("💖 스크랩한 논문들")

    member_no = st.session_state.member_no

    papers = fetch_scraped_papers(member_no)
    keywords = fetch_keywords_from_scraped_papers(papers)

    col1, col2 = st.columns([3, 2])
    with col1:
        selected_keywords = st.multiselect("키워드로 필터링", ["전체"] + list(keywords), key="keyword_filter_scrap")
    
    if "전체" in selected_keywords:
        selected_keywords = keywords

    if selected_keywords:
        papers = [paper for paper in papers if paper['search_keyword'] in selected_keywords]

    for idx, paper in enumerate(papers):
        pmid = paper['document_pmid']
        translation_state = st.session_state["translation_states"].get(pmid, False)
        translated_abstract = st.session_state["translated_abstracts"].get(pmid)
        display_paper(paper, translation_state, translated_abstract)

# Initialize session state variables
if "translation_states" not in st.session_state:
    st.session_state["translation_states"] = {}
if "translated_abstracts" not in st.session_state:
    st.session_state["translated_abstracts"] = {}





