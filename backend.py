import json
import os
import shutil
import tempfile
import traceback
import logging

from fastapi import FastAPI, File, UploadFile, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import fitz  # PyMuPDF
from dotenv import load_dotenv

from langchain.document_loaders import PyPDFium2Loader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import FAISS
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.schema import Document
from langchain.prompts import PromptTemplate

# Configuração de logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Carregar variáveis de ambiente (.env)
load_dotenv()
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# FastAPI app
app = FastAPI(title="Análise Tributária de Notas Fiscais")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modelo para texto puro
class TextoNF(BaseModel):
    conteudo: str

# Função para formatar percentuais de forma segura
def formatar_percentual(valor):
    if isinstance(valor, (float, int)):
        return f"{valor * 100:.2f}%"
    return valor

# Função para formatar item do CNAE em texto legível
def formatar_cnae_item(item):
    codigo_cnae_raw = item.get("Código CNAE 2.1", "")
    codigo_cnae = str(codigo_cnae_raw).split("T")[0] if codigo_cnae_raw else "Desconhecido"

    descricao_cnae = item.get("Descrição do Código CNAE 2.0", "") or "Sem descrição"
    descricao_item = item.get("Descrição do Item da Lista (LC Nº 116/2003)", "") or "Sem item"
    aliquota = item.get("ALIQUOTA", "-")
    aliquota_min = item.get("ALIQUOTA_MINIMA", "-")
    aliquota_max = item.get("ALIQUOTA_MAXIMA", "-")
    retencao_iss = item.get("Qual situação que retém o ISS?", "-")
    irrf = item.get("IRRF", "-")
    pcc = item.get("PCC", "-")
    inss = item.get("INSS", "-")
    observacao = item.get("Unnamed: 11", "")

    texto = (
        f"CNAE {codigo_cnae}: {descricao_cnae}\n"
        f"Descrição: {descricao_item}\n"
        f"Alíquota ISS: {formatar_percentual(aliquota)} "
        f"(mín: {formatar_percentual(aliquota_min)}, máx: {formatar_percentual(aliquota_max)})\n"
        f"Retenção ISS: {retencao_iss}\n"
        f"Outras retenções: IRRF - {irrf}, PCC - {pcc}, INSS - {inss}\n"
        f"Observação: {observacao}"
    )
    return texto

# Prompt personalizado com mensagem inicial configurável
def gerar_prompt_analise_nf(mensagem_inicial=None):
    mensagem = mensagem_inicial or (
        "Você é um contador experiente e detalhista, especializado em análise de notas fiscais eletrônicas."
    )
    prompt = f"""
{mensagem}

Analise os dados abaixo, considerando os dados da nota fiscal e também as regras da tabela CNAE:

{{context}}

Histórico da conversa (se houver):
{{chat_history}}

Nova solicitação do usuário:
{{question}}

Importante:
- Seja claro, objetivo e didático.
- Apresente possíveis erros ou inconsistências tributárias.
- Finalize com uma orientação útil (ex: consulte seu contador).
"""
    return PromptTemplate(
        input_variables=["chat_history", "question", "context"],
        template=prompt.strip()
    )

# Variáveis globais para memória e chain
CHAIN = None
MEMORY = None

# Carregando JSON CNAE no início
try:
    with open("json_cnae.json", "r", encoding="utf-8") as f:
        cnae_json = json.load(f)
    if not cnae_json:
        logger.warning("Tabela CNAE está vazia ou mal formatada. Verifique o arquivo json_cnae.json.")
except Exception as e:
    logger.error(f"Erro ao carregar json_cnae.json: {e}")
    cnae_json = []

# Função para processar documentos (nota fiscal + CNAE) e preparar chain
def processar_documento(documentos):
    global CHAIN, MEMORY

    if not documentos:
        raise ValueError("Nenhum conteúdo válido foi encontrado para análise.")

    splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=150)

    # Fragmenta documentos da NF
    docs_nf = splitter.split_documents(documentos)

    # Cria documentos formatados para CNAE
    cnae_docs = [
        Document(page_content=formatar_cnae_item(item), metadata={"source": "json_cnae.json"})
        for item in cnae_json
    ]
    docs_cnae = splitter.split_documents(cnae_docs)

    todos_docs = docs_nf + docs_cnae

    if not todos_docs:
        raise ValueError("Texto insuficiente para análise.")

    embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
    vector_store = FAISS.from_documents(todos_docs, embedding=embeddings)

    memory = ConversationBufferMemory(
        return_messages=True,
        memory_key="chat_history",
        output_key="answer"
    )

    retriever = vector_store.as_retriever()
    prompt_template = gerar_prompt_analise_nf()

    CHAIN = ConversationalRetrievalChain.from_llm(
        llm = ChatOpenAI(
model_name="gpt-3.5-turbo",
    temperature=0,
    openai_api_key=OPENAI_API_KEY
    ),
        memory=memory,
        retriever=retriever,
        return_source_documents=True,
        combine_docs_chain_kwargs={"prompt": prompt_template}
    )

    MEMORY = memory

# Endpoint para upload de arquivo PDF da NF
@app.post("/upload_nf/")
async def upload_nf(file: UploadFile = File(...)):
    if file.content_type != "application/pdf":
        return {"error": "O arquivo deve ser um PDF."}

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            path_pdf = os.path.join(tmpdir, file.filename)
            with open(path_pdf, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            try:
                loader = PyPDFium2Loader(path_pdf)
                documentos = loader.load()
            except Exception as e:
                logger.warning(f"Erro PyPDFium2Loader: {e}")
                documentos = []

            # Fallback para PyMuPDF se o PyPDFium2 falhar
            if not documentos:
                try:
                    with fitz.open(path_pdf) as doc:
                        texto = "".join([pagina.get_text() for pagina in doc])
                    if texto.strip():
                        documentos = [Document(page_content=texto, metadata={"source": file.filename})]
                except Exception as e:
                    return {"error": f"Erro ao ler PDF: {e}"}

            processar_documento(documentos)

            pergunta_padrao = (
                "Analise os dados da nota fiscal e me forneça um resumo claro e direto das alíquotas, "
                "impostos devidos e possíveis inconsistências."
            )
            resposta = CHAIN.run({"question": pergunta_padrao})

            return {
                "message": "Nota fiscal em PDF analisada com sucesso.",
                "resumo_tributario": resposta
            }

    except Exception as e:
        logger.error(f"Erro interno ao processar PDF: {traceback.format_exc()}")
        return {"error": "Erro interno ao processar a nota fiscal PDF."}

# Endpoint para upload de texto puro da NF, com pergunta opcional
@app.post("/upload_nf_texto/")
async def upload_nf_texto(dados: TextoNF, pergunta: str = Query(None, description="Pergunta personalizada para análise")):
    texto = dados.conteudo.strip()
    if not texto:
        return {"error": "O conteúdo textual está vazio."}

    try:
        documento = Document(page_content=texto, metadata={"source": "entrada_manual"})
        processar_documento([documento])

        pergunta_padrao = pergunta or (
            "Analise os dados da nota fiscal e me forneça um resumo claro e direto das alíquotas, "
            "impostos devidos e possíveis inconsistências."
        )

        resposta = await CHAIN.ainvoke({"question": pergunta_padrao})
        resumo = resposta.get("answer", "")

        return {
            "message": "Texto analisado com sucesso.",
            "resumo_tributario": resumo
        }

    except Exception as e:
        logger.error(f"Erro interno ao processar texto: {traceback.format_exc()}")
        return {"error": str(e)}
