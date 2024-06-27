import streamlit as st
import mysql.connector
from mysql.connector import Error
from config import DB_CONFIG, AI_CONFIG
import deepl
import random
import string
from datetime import datetime

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

def fetch_all_papers(member_no):
    connection = create_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            query = """
            SELECT 
                md.document_title, 
                md.document_author, 
                md.document_abstract, 
                md.document_pmid,
                sk.search_keyword
            FROM 
                tb_member_document md
            JOIN 
                tb_search_keyword sk ON md.search_keyword_no = sk.search_keyword_no
            WHERE 
                sk.member_no = %s
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

def search_papers(member_no, query, search_scope):
    connection = create_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            if search_scope == "제목":
                search_query = f"""
                SELECT 
                    md.document_title, 
                    md.document_author, 
                    md.document_abstract, 
                    md.document_pmid,
                    sk.search_keyword
                FROM 
                    tb_member_document md
                JOIN 
                    tb_search_keyword sk ON md.search_keyword_no = sk.search_keyword_no
                WHERE 
                    sk.member_no = %s AND md.document_title LIKE %s
                ORDER BY 
                    md.document_title
                """
                cursor.execute(search_query, (member_no, f"%{query}%"))
            elif search_scope == "제목+내용":
                search_query = f"""
                SELECT 
                    md.document_title, 
                    md.document_author, 
                    md.document_abstract, 
                    md.document_pmid,
                    sk.search_keyword
                FROM 
                    tb_member_document md
                JOIN 
                    tb_search_keyword sk ON md.search_keyword_no = sk.search_keyword_no
                WHERE 
                    sk.member_no = %s AND (
                        md.document_title LIKE %s OR 
                        md.document_abstract LIKE %s
                    )
                ORDER BY 
                    md.document_title
                """
                cursor.execute(search_query, (member_no, f"%{query}%", f"%{query}%"))
            elif search_scope == "저자":
                search_query = f"""
                SELECT 
                    md.document_title, 
                    md.document_author, 
                    md.document_abstract, 
                    md.document_pmid,
                    sk.search_keyword
                FROM 
                    tb_member_document md
                JOIN 
                    tb_search_keyword sk ON md.search_keyword_no = sk.search_keyword_no
                WHERE 
                    sk.member_no = %s AND md.document_author LIKE %s
                ORDER BY 
                    md.document_title
                """
                cursor.execute(search_query, (member_no, f"%{query}%"))
            
            records = cursor.fetchall()
            return records
        except Error as e:
            st.error(f"Error searching data: {e}")
            return []
        finally:
            cursor.close()
            connection.close()
    else:
        return []

def fetch_keywords(member_no):
    connection = create_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            query = """
            SELECT search_keyword 
            FROM tb_search_keyword
            WHERE member_no = %s
            """
            cursor.execute(query, (member_no,))
            records = cursor.fetchall()
            return [record['search_keyword'] for record in records]
        except Error as e:
            st.error(f"Error fetching keywords: {e}")
            return []
        finally:
            cursor.close()
            connection.close()
    else:
        return []

def generate_no():
    now = datetime.now()
    formattedData = now.strftime("%Y%m%d%H%M%S")
    secure_code = ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(6))
    number = formattedData + secure_code
    return number

def toggle_favorite(pmid, member_no):
    connection = create_connection()
    try:
        cursor = connection.cursor()
        # Check if the paper is already in the favorite list
        query = "SELECT COUNT(*) FROM tb_user_favorite WHERE document_pmid = %s AND member_no = %s"
        cursor.execute(query, (pmid, member_no))
        result = cursor.fetchone()

        if result and result[0] > 0:
            # If the paper is already in the favorite list, remove it
            delete_query = "DELETE FROM tb_user_favorite WHERE document_pmid = %s AND member_no = %s"
            cursor.execute(delete_query, (pmid, member_no))
        else:
            # If the paper is not in the favorite list, add it
            favorite_no = generate_no()
            insert_query = """
                INSERT INTO tb_user_favorite (user_favorite_no, document_pmid, member_no)
                VALUES (%s, %s, %s)
            """
            cursor.execute(insert_query, (favorite_no, pmid, member_no))
        connection.commit()
    except Error as e:
        st.error(f"Error toggling favorite: {e}")
    finally:
        cursor.close()
        connection.close()

def is_favorite(pmid, member_no):
    connection = create_connection()
    try:
        cursor = connection.cursor()
        query = "SELECT COUNT(*) FROM tb_user_favorite WHERE document_pmid = %s AND member_no = %s"
        cursor.execute(query, (pmid, member_no))
        result = cursor.fetchone()
        return result[0] > 0
    except Error as e:
        st.error(f"Error checking favorite: {e}")
        return False
    finally:
        cursor.close()
        connection.close()

def display_paper(record, translation_state, translated_abstract=None, idx=0):
    if translation_state and translated_abstract:
        title = translate(record['document_title'])
        abstract = translated_abstract
    else:
        title = record['document_title']
        abstract = record['document_abstract']

    pmid = record['document_pmid']
    member_no = st.session_state.member_no
    favorited = is_favorite(pmid, member_no)

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
        if st.button("Translate", key=f"translate_{pmid}_{idx}", help="Translate the abstract to Korean"):
            if not translation_state:
                translated_abstract = translate(record['document_abstract'])
                st.session_state["translated_abstracts"][pmid] = translated_abstract
                save_translation_to_db(pmid, translated_abstract)
            st.session_state["translation_states"][pmid] = not translation_state
            st.rerun()
    with col3:
        if st.button("💖" if favorited else "🤍", key=f"favorite_{pmid}_{idx}", help="Toggle favorite"):
            toggle_favorite(pmid, member_no)
            st.rerun()

def search_service():
    # 세션 상태 초기화
    if "search_mode" not in st.session_state:
        st.session_state["search_mode"] = False
    if "search_query" not in st.session_state:
        st.session_state["search_query"] = ""
    if "search_scope" not in st.session_state:
        st.session_state["search_scope"] = "제목"
    if "translation_states" not in st.session_state:
        st.session_state["translation_states"] = {}
    if "translated_abstracts" not in st.session_state:
        st.session_state["translated_abstracts"] = {}

    st.header("🔍 논문 검색")

    member_no = st.session_state.member_no

    col1, col2, col3 = st.columns([3, 2, 5])
    with col1:
        search_query = st.text_input("검색어를 입력하세요")
    with col2:
        search_scope = st.selectbox("검색 범위를 선택하세요", ["제목", "제목+내용", "저자"])
    with col3:
        st.write("")  
        st.write("") 
        search_button = st.button("검색")

    col1, col2 = st.columns([5, 5])
    with col1:
        with st.expander("**내 키워드 보기**"):
            keywords = fetch_keywords(member_no)
            for keyword in keywords:
                st.write(keyword)
    with col2:
        show_all_button = st.button("모든 논문 보기", key="show_all")

    if show_all_button:
        st.session_state["search_mode"] = False

    if search_button and search_query:
        st.session_state["search_mode"] = True
        st.session_state["search_query"] = search_query
        st.session_state["search_scope"] = search_scope

    if st.session_state["search_mode"]:
        search_query = st.session_state.get("search_query", "")
        search_scope = st.session_state.get("search_scope", "제목")
        results = search_papers(member_no, search_query, search_scope)
        st.write(f"총 {len(results)}개의 검색 결과가 있습니다.")
        for idx, record in enumerate(results):
            pmid = record['document_pmid']
            translation_state = st.session_state["translation_states"].get(pmid, False)
            translated_abstract = st.session_state["translated_abstracts"].get(pmid)
            display_paper(record, translation_state, translated_abstract, idx)
    else:
        st.write("#### 모든 논문 목록")
        papers = fetch_all_papers(member_no)

        for idx, paper in enumerate(papers):
            pmid = paper['document_pmid']
            translation_state = st.session_state["translation_states"].get(pmid, False)
            translated_abstract = st.session_state["translated_abstracts"].get(pmid)
            display_paper(paper, translation_state, translated_abstract, idx)

# Initialize session state variables
if "translation_states" not in st.session_state:
    st.session_state["translation_states"] = {}
if "translated_abstracts" not in st.session_state:
    st.session_state["translated_abstracts"] = {}






