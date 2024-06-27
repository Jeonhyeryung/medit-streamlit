import streamlit as st
import openai
from langchain.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import Chroma
from langchain.prompts import PromptTemplate
from langchain.schema.runnable import RunnablePassthrough
from langchain.chat_models import ChatOpenAI
from config import AI_CONFIG
import base64
import asyncio

def ai_service():
    # Initialize session state
    if "retriever" not in st.session_state:
        st.session_state.retriever = None
    if "pdf_file" not in st.session_state:
        st.session_state.pdf_file = None
    if "messages" not in st.session_state:
        st.session_state["messages"] = [{"role": "assistant", "content": "PDF 파일을 업로드하고 질문을 입력해주세요."}]
    if "ai_service_option" not in st.session_state:
        st.session_state.ai_service_option = False
    if "markdown_document" not in st.session_state:
        st.session_state.markdown_document = ""

    col1, col2 = st.columns(2)
    with col1:
        toggle = st.toggle("문서 생성 기능 사용", key="toggle_document_generation", help="Use Document Generation")

    if toggle:
        st.session_state.ai_service_option = True
    else:
        st.session_state.ai_service_option = False

    if st.session_state.ai_service_option:
        st.write("문서 생성 기능 페이지입니다.")

        if st.session_state.markdown_document:
            col1, col2 = st.columns([2, 3])

            with col1:
                st.header("💬 Chatbot")
                for msg in st.session_state.messages:
                    st.chat_message(msg["role"]).write(msg["content"])

                if prompt := st.chat_input("질문을 입력하세요..."):
                    openai_api_key = AI_CONFIG["openai"]["api_key"]
                    if not openai_api_key:
                        st.info("Please add your OpenAI API key to continue.")
                        st.stop()

                    st.session_state.messages.append({"role": "user", "content": prompt})
                    st.chat_message("user").write(prompt)

                    # LLM 설정
                    llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0, openai_api_key=openai_api_key)
                    # 프롬프트 템플릿 설정
                    template = """사용자의 요청 사항에 따라 아래 문서를 수정하시오.
                    오직 수정된 문서 결과만 output으로 제공하시오.
                    {context}
                    질문: {question}
                    수정된 문서:"""
                    rag_prompt_custom = PromptTemplate.from_template(template)

                    # RAG chain 설정
                    rag_chain = {"context": RunnablePassthrough(lambda: st.session_state.markdown_document), "question": RunnablePassthrough()} | rag_prompt_custom | llm
                    response = rag_chain.invoke(f'{prompt}')
                    msg = response.content

                    st.session_state.messages.append({"role": "assistant", "content": msg})
                    st.chat_message("assistant").write(msg)

                    # Update markdown document based on chatbot response
                    st.session_state.markdown_document = msg

            with col2:
                st.header("📄 PDF Viewer")
                markdown_document = st.session_state.markdown_document

                st.markdown(markdown_document)
                st.download_button("Download Updated Markdown", markdown_document, file_name="updated_output.md")

                with open("updated_output.md", "wb") as f:
                    f.write(markdown_document.encode('utf-8'))
                with open("updated_output.md", "rb") as f:
                    base64_pdf = base64.b64encode(f.read()).decode('utf-8')
                pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}#toolbar=0&navpanes=0&scrollbar=0" width="100%" height="500" type="application/pdf"></iframe>'
                st.markdown(pdf_display, unsafe_allow_html=True)
    else:
        col1, col2 = st.columns([3, 2])

        with col1:
            st.header("📄 PDF 업로드")
            uploaded_file = st.file_uploader("Upload a PDF file", type=("pdf"))
            process = st.button("PDF 처리하기")

            if process and uploaded_file:
                openai_api_key = AI_CONFIG["openai"]["api_key"]
                openai.api_key = openai_api_key

                # Save the uploaded file
                file_name = uploaded_file.name
                with open(file_name, "wb") as file:
                    file.write(uploaded_file.getvalue())

                # Store the file name in session state
                st.session_state.pdf_file = file_name

                # Load and split PDF
                loader = PyPDFLoader(file_name)
                pages = loader.load_and_split()

                # Split text into chunks
                text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=0)
                splits = text_splitter.split_documents(pages)

                # Set embedding model
                embedding_model = OpenAIEmbeddings(openai_api_key=openai_api_key)

                # Set up ChromaDB and retriever
                vectorstore = Chroma.from_documents(documents=splits, embedding=embedding_model)
                vectorstore_retriever = vectorstore.as_retriever()

                st.session_state.retriever = vectorstore_retriever
                st.success("PDF 파일이 성공적으로 처리되었습니다!")

        # Display the PDF viewer if a file has been processed
        if st.session_state.pdf_file:
            with open(st.session_state.pdf_file, "rb") as f:
                base64_pdf = base64.b64encode(f.read()).decode('utf-8')
            pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}#toolbar=0&navpanes=0&scrollbar=0" width="100%" height="500" type="application/pdf"></iframe>'
            col1.markdown(pdf_display, unsafe_allow_html=True)

        with col2:
            st.header("💬 Chatbot")
            if "messages" not in st.session_state:
                st.session_state["messages"] = [{"role": "assistant", "content": "PDF 파일을 업로드하고 질문을 입력해주세요."}]

            for msg in st.session_state.messages:
                st.chat_message(msg["role"]).write(msg["content"])

            if prompt := st.chat_input("질문을 입력하세요..."):
                openai_api_key = AI_CONFIG["openai"]["api_key"]
                if not openai_api_key:
                    st.info("Please add your OpenAI API key to continue.")
                    st.stop()

                st.session_state.messages.append({"role": "user", "content": prompt})
                st.chat_message("user").write(prompt)

                # LLM 설정
                llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0, openai_api_key=openai_api_key)
                # 프롬프트 템플릿 설정
                template = """다음과 같은 맥락을 사용하여 마지막 질문에 대답하십시오.
                만약 답을 모르면 모른다고만 말하고 답을 지어내려고 하지 마십시오.
                답변은 최대 세 문장으로 하고 가능한 한 간결하게 유지하십시오.
                항상 '질문해주셔서 감사합니다!'라고 답변 끝에 말하십시오.
                {context}
                질문: {question}
                도움이 되는 답변:"""
                rag_prompt_custom = PromptTemplate.from_template(template)

                # RAG chain 설정
                rag_chain = {"context": st.session_state.retriever, "question": RunnablePassthrough()} | rag_prompt_custom | llm
                response = rag_chain.invoke(f'{prompt}')
                msg = response.content
                st.session_state.messages.append({"role": "assistant", "content": msg})
                st.chat_message("assistant").write(msg)