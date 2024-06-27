# medical_pick.py
import nest_asyncio
from typing import List
from pydantic import BaseModel, Field, ValidationError
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.chains import LLMChain
from langchain.chat_models import ChatOpenAI
import json
import re
import yaml
import boto3
import os
from PIL import Image
import asyncio
from config import AI_CONFIG, AWS_CONFIG

class medical_pick:
    def __init__(self, max_experts: int = 5):
        self.fast_llm = ChatOpenAI(model="gpt-4o", openai_api_key=AI_CONFIG["openai"]["api_key"])
        self.max_experts = max_experts

        with open("prompts.yaml", "r", encoding='utf-8') as file:
            self.prompts = yaml.safe_load(file)

        self.gen_perspectives_prompt = self.create_prompt_template(self.prompts["gen_perspectives_prompt"])
        self.gen_question_prompt = self.create_prompt_template(self.prompts["gen_question_prompt"])
        self.gen_answer_prompt = self.create_prompt_template(self.prompts["gen_answer_prompt"])
        self.fill_study_design_prompt = self.create_prompt_template(self.prompts["fill_study_design_prompt"])
        self.generate_results_table_prompt = self.create_prompt_template(self.prompts["generate_results_table_prompt"])
        self.generate_conclusion_prompt = self.create_prompt_template(self.prompts["generate_conclusion_prompt"])

        self.gen_perspectives_chain = LLMChain(
            llm=self.fast_llm,
            prompt=self.gen_perspectives_prompt,
            output_parser=self.PerspectivesOutputParser(max_experts)
        )

        self.gen_question_chain = LLMChain(
            llm=self.fast_llm,
            prompt=self.gen_question_prompt,
        )

        self.gen_answer_chain = LLMChain(
            llm=self.fast_llm,
            prompt=self.gen_answer_prompt,
        )

        # Set up AWS S3 client
        self.s3 = boto3.client(
            's3',
            region_name=AWS_CONFIG['s3_bucket']['region'],
            aws_access_key_id=AWS_CONFIG['s3_bucket']['access_key_id'],
            aws_secret_access_key=AWS_CONFIG['s3_bucket']['secret_access_key']
        )

    def create_prompt_template(self, messages):
        prompt_messages = []
        for message in messages:
            if message['role'] == 'system':
                prompt_messages.append(SystemMessagePromptTemplate.from_template(message['content']))
            elif message['role'] == 'user':
                prompt_messages.append(HumanMessagePromptTemplate.from_template(message['content']))
        return ChatPromptTemplate(messages=prompt_messages)

    class Expert(BaseModel):
        name: str = Field(description="Name of the expert.", pattern=r"^[a-zA-Z0-9\s-]{1,64}$")
        affiliation: str = Field(description="Primary affiliation of the expert.")
        role: str = Field(description="Role of the expert.", default="Unknown")
        description: str = Field(description="Description of the expert's focus, concerns, and motives.")

        @property
        def persona(self) -> str:
            return f"Name: {self.name}\nRole: {self.role}\nAffiliation: {self.affiliation}\nDescription: {self.description}\n"

    class Perspectives(BaseModel):
        experts: List['medical_pick.Expert'] = Field(description="Comprehensive list of experts with their roles and affiliations.", max_items=5)

    class PerspectivesOutputParser:
        def __init__(self, max_experts: int):
            self.max_experts = max_experts

        def parse(self, text: str) -> 'medical_pick.Perspectives':
            if not text.strip():
                raise ValueError("Received empty response from OpenAI")
            try:
                json_start = text.find("[")
                json_end = text.rfind("]") + 1
                json_text = text[json_start:json_end].replace("```json", "").replace("```", "").strip()
                data = json.loads(json_text)

                for expert in data:
                    if 'field' in expert:
                        expert['role'] = expert.pop('field')
                    if 'role' not in expert:
                        expert['role'] = 'Unknown'
                    if 'affiliation' not in expert:
                        expert['affiliation'] = 'Unknown'
                    if 'description' not in expert:
                        expert['description'] = 'Unknown'
                    if not re.match(r"^[a-zA-Z0-9\s-]{1,64}$", expert['name']):
                        expert['name'] = re.sub(r"[^a-zA-Z0-9\s-]", "", expert['name'])

                if len(data) > self.max_experts:
                    data = data[:self.max_experts]

                return medical_pick.Perspectives(experts=data)
            except (json.JSONDecodeError, ValidationError, Exception) as e:
                print(f"Error: {e}")
                raise e

        def get_format_instructions(self) -> str:
            return "The output should be a JSON object that matches the Perspectives schema."

    async def generate_perspectives_for_paper(self, topic: str, paper_full_text: str) -> 'medical_pick.Perspectives':
        try:
            response = await self.gen_perspectives_chain.acall({"paper_full_text": paper_full_text, "topic": topic})
            return response
        except Exception as e:
            print(f"An error occurred: {e}")
            raise e

    def read_full_text(self, file_path: str) -> str:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()

    def extract_expert_info_from_text_as_dict(self, perspectives: 'medical_pick.Perspectives') -> List[dict]:
        return [expert.dict() for expert in perspectives['text'].experts]

    async def generate_conversation(self, expert_info_dict_list: List[dict], paper_full_text: str) -> List[dict]:
        conversation = []
        experts = [self.Expert(**info) for info in expert_info_dict_list]

        for i in range(len(experts) - 1):
            question_expert = experts[i]
            answer_expert = experts[i + 1]

            question_response = await self.gen_question_chain.acall({
                "persona": question_expert.persona,
                "paper_full_text": paper_full_text
            })
            question_text = question_response['text'].strip()

            answer_response = await self.gen_answer_chain.acall({
                "persona": answer_expert.persona,
                "paper_full_text": paper_full_text,
                "question": question_text
            })
            answer_text = answer_response['text'].strip()

            conversation.append({
                "question_expert": question_expert.name,
                "question_text": question_text,
                "answer_expert": answer_expert.name,
                "answer_text": answer_text
            })

        return conversation

    def extract_all_tables_from_file(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()

        tables = []
        table_start = None
        table_end = None
        table_count = 0

        for i, line in enumerate(lines):
            if line.startswith("Table"):
                table_count += 1
                if table_count == 2:
                    table_start = i - 1
            if table_start is not None and line.startswith("|"):
                table_end = i
            if table_start is not None and table_end is not None and not line.startswith("|"):
                table_content = lines[table_start:table_end+1]
                tables.append(''.join(table_content))
                table_start = None
                table_end = None
                table_count = 0

        return tables

    def extract_all_figures_from_file(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()

        figures = []
        figure_start = None
        figure_count = 0

        for i, line in enumerate(lines):
            if line.startswith("Figure"):
                figure_count += 1
                if figure_count == 2:
                    figure_start = i - 1
                    figure_count = 0

            if figure_start is not None and line.startswith("Figure"):
                figures.append(line.strip())

        return figures

    def generate_key_findings(self, full_text):
        prompt = f"""
        Based on the following full text about the study, please summarize the key findings in a concise manner:
        {full_text}
        ### Key Findings:
        1.
        2.
        3.
        4.
        """
        response = self.fast_llm.predict(prompt)
        key_findings = response.strip()
        results_text = "### Key Findings:\n" + key_findings
        return results_text

    def fill_study_design(self, dialogue, results_text):
        chain = LLMChain(llm=self.fast_llm, prompt=self.fill_study_design_prompt)
        return chain.run(dialogue=dialogue, results_text=results_text)

    def generate_results_table(self, dialogue, results_text, results_text_tables, results_text_figures):
        chain = LLMChain(llm=self.fast_llm, prompt=self.generate_results_table_prompt)
        return chain.run(dialogue=dialogue, results_text=results_text, results_text_tables=results_text_tables, results_text_figures=results_text_figures)

    def generate_conclusion(self, dialogue, results_text):
        chain = LLMChain(llm=self.fast_llm, prompt=self.generate_conclusion_prompt)
        return chain.run(dialogue=dialogue, results_text=results_text)

    def download_image_from_s3(self, s3_path, local_dir="images", height=600):
        if not os.path.exists(local_dir):
            os.makedirs(local_dir)
        s3_bucket = AWS_CONFIG['s3_bucket']['bucket_name']
        s3_key = s3_path.replace(f"s3://{s3_bucket}/", "")
        local_path = os.path.join(local_dir, os.path.basename(s3_key))
        self.s3.download_file(s3_bucket, s3_key, local_path)

        # Resize the image maintaining the aspect ratio
        with Image.open(local_path) as img:
            aspect_ratio = img.width / img.height
            new_width = int(height * aspect_ratio)
            img = img.resize((new_width, height), Image.LANCZOS)
            img.save(local_path)

        return local_path

    def update_paths_in_content(self, content):
        lines = content.split("\n")
        updated_lines = []
        for line in lines:
            if "s3://" in line:
                s3_path = line.split("(", 1)[-1].rstrip(")")
                local_path = self.download_image_from_s3(s3_path)
                line = line.replace(s3_path, local_path)
            if line.startswith("![Figure"):
                description = line.split("](", 1)[0].replace("![", "### ")
                updated_lines.append(description)
            updated_lines.append(line)
        return "\n".join(updated_lines)

    async def generate_full_document(self, file_path: str, example_topic: str):
        paper_full_text = self.read_full_text(file_path)
        perspectives = await self.generate_perspectives_for_paper(example_topic, paper_full_text)
        expert_info_dict_list = self.extract_expert_info_from_text_as_dict(perspectives)
        conversation = await self.generate_conversation(expert_info_dict_list, paper_full_text)

        tables = self.extract_all_tables_from_file(file_path)
        figures = self.extract_all_figures_from_file(file_path)

        results_text_tables = "\n".join([f"Table {idx + 1}:\n{table}\n" for idx, table in enumerate(tables)])
        results_text_figures = "\n".join([f"{figure}\n" for figure in figures])

        results_text = self.generate_key_findings(paper_full_text)

        conversation_text = ""
        for exchange in conversation:
            conversation_text += f"Question by {exchange['question_expert']}: {exchange['question_text']}\n"
            conversation_text += f"Answer by {exchange['answer_expert']}: {exchange['answer_text']}\n\n"

        study_design = self.fill_study_design(conversation_text, results_text)
        results_table = self.generate_results_table(conversation_text, results_text, results_text_tables, results_text_figures)
        conclusion = self.generate_conclusion(conversation_text, results_text)

        output = {
            "Study design\n": study_design,
            "Results\n": results_table,
            "Conclusion\n": conclusion
        }

        updated_output = {section: self.update_paths_in_content(content) for section, content in output.items()}

        markdown_document = "\n\n".join(updated_output.values())

        with open('output_4.md', 'w', encoding='utf-8') as file:
            file.write(markdown_document)

        return markdown_document
